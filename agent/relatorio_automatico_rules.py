"""Relatório pós-reunião automático (V.1.4.185).

Análise de 16/10/2026: desde o reset de 11/10, 33 reuniões (24 com
vendedor logado) e **0 relatórios** — o relatório só era gerado colando a
transcrição em Dashboard → Relatórios (o fluxo automático antigo era o
webhook do Tactiq). Tudo o que nasce do relatório parou junto: cliente e
oportunidade automáticos (B7), memórias comerciais, playbook, indexação
semântica e as observações do Seller DNA (0 gravadas).

Agora o servidor gera o relatório sozinho quando a reunião termina:
sessão encerrada pela extensão (`/encerrar-sessao`, ext ≥ 1.4.32) há
`ESPERA_APOS_FIM_S`, ou parada há `INATIVA_S` (extensão antiga, que não
avisa a saída). Uma vez por sessão.

Funções puras — zero IA, zero banco.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

ESPERA_APOS_FIM_S = 120          # o vendedor pode voltar logo para a chamada
INATIVA_S = 30 * 60              # extensão antiga não avisa que saiu
MIN_CARACTERES = 1500            # ~2-3 min de conversa
MIN_FALAS = 8
LIMITE_CARACTERES = 150_000      # cabe com folga no contexto dos provedores
INICIO_PRESERVADO = 40_000

STATUS_ANTERIOR = "anterior"     # sessões que já existiam antes do recurso
STATUS_GERANDO = "gerando"
STATUS_OK = "ok"
STATUS_PULADO = "pulado"
STATUS_ERRO = "erro"


def habilitado(env: dict | None = None) -> bool:
    env = os.environ if env is None else env
    return str(env.get("RELATORIO_AUTOMATICO_ENABLED", "true")).strip().lower() in ("1", "true", "yes")


def sessao_pronta(encerrada_em: datetime | None, updated_at: datetime | None, agora: datetime) -> bool:
    """A reunião acabou? Encerrada há ESPERA_APOS_FIM_S ou parada há INATIVA_S."""
    if encerrada_em and agora - encerrada_em >= timedelta(seconds=ESPERA_APOS_FIM_S):
        return True
    return bool(updated_at and agora - updated_at >= timedelta(seconds=INATIVA_S))


def vale_gerar(transcricao: str | None) -> tuple[bool, str]:
    """Reunião com conversa suficiente para um relatório? Evita cliente e
    oportunidade inventados a partir de teste ou de abrir e fechar a sala."""
    texto = (transcricao or "").strip()
    if len(texto) < MIN_CARACTERES:
        return False, f"curta ({len(texto)} caracteres)"
    falas = [l for l in texto.splitlines() if ":" in l and l.split(":", 1)[1].strip()]
    if len(falas) < MIN_FALAS:
        return False, f"poucas falas ({len(falas)})"
    return True, "ok"


def transcricao_para_relatorio(transcricao: str, limite: int = LIMITE_CARACTERES,
                               inicio: int = INICIO_PRESERVADO) -> str:
    """Até `limite` caracteres: preserva o começo (abertura, apresentação do
    cliente) e o fim (proposta, objeções finais, próximos passos). Falas
    seguidas da mesma pessoa viram uma linha só (V.1.4.186)."""
    from agent.transcript_dedup_rules import juntar_falas_seguidas
    texto = juntar_falas_seguidas((transcricao or "").strip())
    if len(texto) <= limite:
        return texto
    fim = limite - inicio
    return texto[:inicio] + "\n\n[... trecho do meio da reunião omitido por tamanho ...]\n\n" + texto[-fim:]


def titulo_da_reuniao(meeting_id: str, inicio: datetime | None) -> str:
    quando = f" — {inicio:%d/%m/%Y %H:%M} UTC" if inicio else ""
    return f"Reunião {meeting_id}{quando}"
