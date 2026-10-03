"""
scripts/transcription_benchmark_run.py — Fase 25 ("o que falta pra
ligar", item 4/5) — roda o dataset de 8 falas
(`evals/datasets/transcription_benchmark/gabarito.yaml`) contra os 3
provedores reais de transcrição do projeto
(`api/main.py::_transcrever_via_openai`/`_transcrever_via_groq`/
`_transcrever_via_whisper_local`), calculando WER/latência via
`agent/transcription_benchmark_rules.py` (V.1.4.133).

**Custa dinheiro real** (Groq e OpenAI Whisper cobram por chamada;
`whisper_local` é grátis, roda no processo). `--dry-run` (padrão) só
mostra o que rodaria, ZERO custo — sempre confirme o `--dry-run` antes
de rodar com `--real`.

Exige `GROQ_API_KEY`/`OPENAI_API_KEY` no `.env` (mesmas variáveis já
usadas por `/audio-transcricao` em produção) e o modelo
`faster-whisper` já baixado pra `whisper_local` funcionar — ver
`agent/whisper_local.py`.

Uso:
    python -m scripts.transcription_benchmark_run              # dry-run, sem custo
    python -m scripts.transcription_benchmark_run --real       # roda de verdade (custo real)
    python -m scripts.transcription_benchmark_run --real --out relatorio.json
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

DATASET_DIR = Path(__file__).parent.parent / "evals" / "datasets" / "transcription_benchmark"
PROVIDERS = ("whisper", "groq", "whisper_local")


def carregar_gabarito(dataset_dir: Path = DATASET_DIR) -> list[dict]:
    """Carrega o dataset de falas do disco. Nunca chama IA — leitura
    pura."""
    with open(dataset_dir / "gabarito.yaml", encoding="utf-8") as f:
        itens = yaml.safe_load(f) or []
    for item in itens:
        item["_audio_path"] = str(dataset_dir / item["audio"])
    return itens


def _dry_run() -> None:
    itens = carregar_gabarito()
    print(f"[DRY-RUN] {len(itens)} falas carregadas de {DATASET_DIR / 'gabarito.yaml'}")
    print(f"[DRY-RUN] provedores: {', '.join(PROVIDERS)}")
    print(f"[DRY-RUN] total de chamadas de transcrição se rodar com --real: {len(itens) * len(PROVIDERS)}")
    print("[DRY-RUN] Nenhuma chamada de transcrição foi feita.")


def _transcrever(provider: str, caminho: str) -> str:
    if provider == "whisper":
        from api.main import _transcrever_via_openai
        texto, _ = _transcrever_via_openai(caminho)
    elif provider == "groq":
        from api.main import _transcrever_via_groq
        texto, _ = _transcrever_via_groq(caminho)
    elif provider == "whisper_local":
        from api.main import _transcrever_via_whisper_local
        texto, _ = _transcrever_via_whisper_local(caminho)
    else:
        raise ValueError(f"provider desconhecido: {provider!r}")
    return texto


def _real_run(out_path: str | None) -> None:
    from agent.transcription_benchmark_rules import comparar_provedores, montar_resultado_transcricao

    itens = carregar_gabarito()
    print(f"Rodando {len(itens)} falas x {len(PROVIDERS)} provedores contra transcrição real...")

    resultados: list[dict] = []
    erros: list[str] = []

    for item in itens:
        for provider in PROVIDERS:
            inicio = time.monotonic()
            try:
                hipotese = _transcrever(provider, item["_audio_path"])
                latencia_ms = (time.monotonic() - inicio) * 1000
            except Exception as e:
                hipotese = ""
                latencia_ms = None
                erros.append(f"{item['id']}/{provider}: {type(e).__name__}: {e}")

            resultado = montar_resultado_transcricao(
                provider, item["texto"], hipotese, latencia_ms=latencia_ms,
            )
            resultado["frase_id"] = item["id"]
            resultados.append(resultado)

    resumo = comparar_provedores(resultados)
    relatorio = {"resumo_por_provider": resumo, "resultados": resultados, "erros": erros}

    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    if erros:
        print(f"\n{len(erros)} erro(s) durante a execução (não derrubaram o script):")
        for erro in erros:
            print(f"  - {erro}")

    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(relatorio, f, ensure_ascii=False, indent=2)
        print(f"\nRelatório salvo em {out_path}")

    # Tarefa D1: registra o WER do provider ativo para GET /admin/readiness.
    try:
        import os

        from agent.readiness_rules import medicao_da_transcricao
        from api.database import registrar_readiness_medicao
        provider_ativo = os.getenv("TRANSCRICAO_PROVEDOR", "whisper").strip().lower()
        medicao = medicao_da_transcricao(resumo, provider_ativo)
        if medicao:
            registrar_readiness_medicao(fonte="scripts/transcription_benchmark_run.py", **medicao)
            print(f"WER de {provider_ativo} registrado no painel de prontidão (/admin/readiness).")
        else:
            print(f"Sem WER para o provider ativo ({provider_ativo}) — nada registrado no painel de prontidão.")
    except Exception as e:
        print(f"Aviso: não foi possível registrar no painel de prontidão: {type(e).__name__}: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", action="store_true", help="Roda de verdade contra os 3 provedores (custo real em Groq/OpenAI). Sem esta flag, só dry-run.")
    parser.add_argument("--out", default=None, help="Caminho pra salvar o relatório JSON (opcional).")
    args = parser.parse_args()

    if not args.real:
        _dry_run()
        return

    _real_run(args.out)


if __name__ == "__main__":
    main()
