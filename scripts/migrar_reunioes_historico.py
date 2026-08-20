"""
scripts/migrar_reunioes_historico.py — Migração de reuniões históricas para Sales Memory

Processa um lote de transcrições de reuniões antigas (ex: exportadas do
Google Drive/Gemini Notes) pelo MESMO pipeline que uma reunião ao vivo usa
quando colada manualmente no dashboard (`POST /recapitulacao-manual`):
gera o relatório completo (recapitulação + DISC + diagnóstico financeiro +
propensão), salva em `data/relatorios/`, e dispara em background a
extração de Sales Memory (`extrair_e_salvar_memorias`) — e também gera
Playbook automaticamente se a reunião for identificada como "ganha".

Não duplica a lógica do endpoint — chama a API HTTP real (local ou
remota), então precisa de um servidor SALEIA rodando e com pelo menos um
provedor de IA configurado.

Entrada: uma pasta com um arquivo .txt ou .docx por reunião (nome do
arquivo vira o título; pode ser um transcript bruto ou o texto exportado
do Gemini Notes — o prompt de recapitulação lida bem com ambos os
formatos). .docx é lido direto (sem depender de python-docx — um .docx é
só um zip com XML; o texto é extraído via zipfile + xml da stdlib).

Idempotente: cada arquivo gera um meeting_id estável (hash do nome do
arquivo) registrado em um arquivo de estado local — reexecutar o script
pula o que já foi migrado com sucesso.

Uso:
    python -m scripts.migrar_reunioes_historico --pasta caminho/para/transcricoes [--dry-run]
                                                  [--base-url http://127.0.0.1:8000]
                                                  [--estado-file data/migracao_reunioes_estado.json]
                                                  [--forcar]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx

# Console do Windows (cp1252) não decodifica os emojis usados no progresso —
# força UTF-8 na saída para evitar UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

PASTA_ESTADO_PADRAO = Path("data/migracao_reunioes_estado.json")

_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_SUFIXO_GEMINI = " - Anotações do Gemini"

# Boilerplate fixo que o Google Meet/Gemini repete em TODO documento de notas
# — não tem sinal nenhum pra recapitulação/Sales Memory, só consome tokens.
_BOILERPLATE_GEMINI = (
    "Revise as anotações do Gemini",
    "Como está a qualidade de",
    "Esta transcrição editável foi gerada por computador",
    "Acesse a Central de Ajuda",
)


def _extrair_texto_docx(caminho: Path) -> str:
    """Extrai o texto de um .docx sem depender de python-docx — um .docx é
    um zip com word/document.xml; concatena o texto de cada parágrafo,
    preservando quebras de linha (uma por parágrafo), e remove o boilerplate
    fixo de pesquisa/disclaimer que o Gemini repete em todo documento."""
    with zipfile.ZipFile(caminho) as z:
        xml_bytes = z.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    paragrafos = []
    for p in root.iter(f"{_WORD_NS}p"):
        texto_paragrafo = "".join(node.text or "" for node in p.iter(f"{_WORD_NS}t"))
        if texto_paragrafo.strip() and any(b in texto_paragrafo for b in _BOILERPLATE_GEMINI):
            continue
        paragrafos.append(texto_paragrafo)
    return "\n".join(paragrafos)


@dataclass
class ResultadoMigracao:
    total_arquivos: int = 0
    ja_migrados: int = 0
    sucesso: int = 0
    falha: int = 0
    erros: list = field(default_factory=list)  # [{"arquivo":, "erro":}]
    dry_run: bool = False

    def to_dict(self) -> dict:
        return {
            "total_arquivos": self.total_arquivos,
            "ja_migrados": self.ja_migrados,
            "sucesso": self.sucesso,
            "falha": self.falha,
            "erros": self.erros,
            "dry_run": self.dry_run,
        }


def _meeting_id_para_arquivo(nome_arquivo: str) -> str:
    """meeting_id estável a partir do nome do arquivo — mesma entrada sempre
    gera o mesmo id, então reexecutar o script é seguro (idempotente)."""
    h = hashlib.sha1(nome_arquivo.encode("utf-8")).hexdigest()[:16]
    return f"hist_{h}"


def _carregar_estado(caminho: Path) -> dict:
    if caminho.exists():
        try:
            return json.loads(caminho.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _salvar_estado(caminho: Path, estado: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")


def _titulo_a_partir_do_nome(nome_arquivo: str) -> str:
    import re

    nome = Path(nome_arquivo).stem
    nome = re.sub(r"\(\d+\)$", "", nome).strip()  # duplicata do Drive: "...Gemini(1)"
    if nome.endswith(_SUFIXO_GEMINI):
        nome = nome[: -len(_SUFIXO_GEMINI)]
    return nome.replace("_", " ").strip()


def migrar_pasta(
    pasta: Path,
    base_url: str,
    estado_file: Path,
    dry_run: bool = False,
    forcar: bool = False,
    timeout_s: float = 300.0,  # algumas reunioes tem 200k+ chars — 3 chamadas de IA sequenciais no /recapitulacao-manual
    delay_s: float = 5.0,  # intervalo entre reunioes — evita sobrecarregar o circuit breaker de IA
) -> ResultadoMigracao:
    resultado = ResultadoMigracao(dry_run=dry_run)
    estado = _carregar_estado(estado_file)

    arquivos = sorted(list(pasta.glob("*.txt")) + list(pasta.glob("*.docx")))
    resultado.total_arquivos = len(arquivos)

    if not arquivos:
        print(f"Nenhum arquivo .txt/.docx encontrado em {pasta}")
        return resultado

    cliente = httpx.Client(base_url=base_url, timeout=timeout_s)

    for arquivo in arquivos:
        meeting_id = _meeting_id_para_arquivo(arquivo.name)
        titulo = _titulo_a_partir_do_nome(arquivo.name)

        if not forcar and estado.get(meeting_id, {}).get("status") == "sucesso":
            resultado.ja_migrados += 1
            print(f"⏭  já migrado — {arquivo.name} ({meeting_id})")
            continue

        try:
            if arquivo.suffix.lower() == ".docx":
                transcricao = _extrair_texto_docx(arquivo).strip()
            else:
                transcricao = arquivo.read_text(encoding="utf-8", errors="replace").strip()
        except Exception as e:
            resultado.falha += 1
            resultado.erros.append({"arquivo": arquivo.name, "erro": f"falha ao ler arquivo: {e}"})
            print(f"❌ {arquivo.name}: falha ao ler arquivo: {e}")
            continue
        if not transcricao:
            resultado.falha += 1
            resultado.erros.append({"arquivo": arquivo.name, "erro": "arquivo vazio"})
            print(f"❌ {arquivo.name}: arquivo vazio")
            continue

        if dry_run:
            print(f"[dry-run] processaria {arquivo.name} → meeting_id={meeting_id}, "
                  f"titulo='{titulo}', {len(transcricao)} chars")
            continue

        ultimo_erro = None
        for tentativa in range(1, 3):  # 1 tentativa + 1 retry em 503/504 (provedores em cooldown)
            try:
                r = cliente.post(
                    "/recapitulacao-manual",
                    json={
                        "transcricao": transcricao,
                        "titulo_reuniao": titulo,
                        "meeting_id": meeting_id,
                    },
                )
                r.raise_for_status()
                dados = r.json()
                propensao = (dados.get("recapitulacao") or {}).get("propensao", {})
                estado[meeting_id] = {
                    "status": "sucesso",
                    "arquivo": arquivo.name,
                    "titulo": titulo,
                    "propensao": propensao.get("nivel"),
                    "processado_em": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                resultado.sucesso += 1
                print(f"✅ {arquivo.name} → propensão: {propensao.get('nivel', '?')}")
                ultimo_erro = None
                break
            except httpx.HTTPStatusError as e:
                ultimo_erro = e
                if e.response.status_code in (503, 504) and tentativa == 1:
                    print(f"⏳ {arquivo.name}: {e.response.status_code}, provedores possivelmente em "
                          f"cooldown — aguardando 30s e tentando mais uma vez")
                    time.sleep(30)
                    continue
                break
            except Exception as e:
                ultimo_erro = e
                break

        if ultimo_erro is not None:
            estado[meeting_id] = {
                "status": "falha",
                "arquivo": arquivo.name,
                "titulo": titulo,
                "erro": str(ultimo_erro),
            }
            resultado.falha += 1
            resultado.erros.append({"arquivo": arquivo.name, "erro": str(ultimo_erro)})
            print(f"❌ {arquivo.name}: {ultimo_erro}")

        _salvar_estado(estado_file, estado)  # salva progresso a cada arquivo

        if delay_s > 0:
            time.sleep(delay_s)  # dá tempo do circuit breaker de IA se recuperar entre chamadas

    cliente.close()
    return resultado


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pasta", required=True, help="Pasta com arquivos .txt/.docx (1 reunião por arquivo)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="URL do backend SALEIA")
    parser.add_argument("--estado-file", default=str(PASTA_ESTADO_PADRAO), help="Arquivo de estado (idempotência)")
    parser.add_argument("--dry-run", action="store_true", help="Só lista o que seria processado, sem chamar a API")
    parser.add_argument("--forcar", action="store_true", help="Reprocessa mesmo arquivos já migrados com sucesso")
    parser.add_argument("--delay-s", type=float, default=5.0, help="Segundos de espera entre reuniões (evita sobrecarregar o circuit breaker de IA)")
    args = parser.parse_args()

    pasta = Path(args.pasta)
    if not pasta.is_dir():
        print(f"Pasta não encontrada: {pasta}", file=sys.stderr)
        return 1

    resultado = migrar_pasta(
        pasta=pasta,
        base_url=args.base_url,
        estado_file=Path(args.estado_file),
        dry_run=args.dry_run,
        forcar=args.forcar,
        delay_s=args.delay_s,
    )

    print("\n--- Resumo ---")
    print(json.dumps(resultado.to_dict(), ensure_ascii=False, indent=2))
    return 0 if resultado.falha == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
