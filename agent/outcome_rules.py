"""
SALEIA — agent/outcome_rules.py

Regras puras de Outcome Tracking (FASE 8 / TAREFA 8.1 do "PROMPT
MESTRE — SALE-IA V2"). Nenhuma chamada de IA, nenhum acesso a banco —
mesmo padrão de agent/deal_risk_rules.py e agent/meddpicc_rules.py.

Toda Opportunity eventualmente recebe um desfecho: WON, LOST, ou
ABANDONED (além de OPEN, já existente desde a Fase 2 / Tarefa 2.1 em
agent/opportunity_memory_rules.py — o vocabulário de `status` inteiro
mora lá, este módulo só valida os dados extras exigidos por cada
desfecho).

Schema literal do prompt mestre:
- WON: value, product, close_date, cycle_days
- LOST: reason, competitor, stage, lost_at

`stage`/`reason`/`lost_at` para LOST reaproveitam os campos já
existentes em `Opportunity` (`stage`, `loss_reason`, `lost_at`) — não
duplicados aqui, mesmo princípio de "não duplicar contexto" já usado em
`KnowledgeItem` (não mapeado para `sales_memory`) e no Knowledge Graph
(evidence nunca redundante). `cycle_days` é sempre calculado, nunca
aceito como input do chamador (evita inconsistência entre o valor
informado e as datas reais).
"""

from datetime import datetime
from typing import Optional


def calcular_cycle_days(created_at: datetime, close_date: datetime) -> int:
    """Dias entre a criação da oportunidade e o fechamento (WON/LOST).
    Nunca negativo — `close_date` anterior a `created_at` é erro do
    chamador, não um ciclo de venda "negativo"."""
    if close_date < created_at:
        raise ValueError("close_date não pode ser anterior a created_at")
    return (close_date - created_at).days


def validar_dados_won(dados: dict) -> None:
    """`dados` esperado: {"value": float, "product": str, "close_date": datetime}.
    `cycle_days` nunca é validado aqui — é sempre derivado de
    `calcular_cycle_days()`, nunca informado pelo chamador."""
    value = dados.get("value")
    if value is None or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"value inválido para desfecho WON: {value!r} (esperado número >= 0)")

    product = dados.get("product")
    if not product or not isinstance(product, str):
        raise ValueError("product é obrigatório para desfecho WON")

    close_date = dados.get("close_date")
    if not isinstance(close_date, datetime):
        raise ValueError("close_date é obrigatório (datetime) para desfecho WON")


def validar_dados_lost(dados: dict) -> None:
    """`dados` esperado: {"reason": str, "competitor": Optional[str]}.
    `stage`/`lost_at` reaproveitam campos já existentes em `Opportunity`
    — não fazem parte deste dict de validação."""
    reason = dados.get("reason")
    if not reason or not isinstance(reason, str):
        raise ValueError("reason é obrigatório para desfecho LOST")

    competitor = dados.get("competitor")
    if competitor is not None and not isinstance(competitor, str):
        raise ValueError(f"competitor inválido: {competitor!r} (esperado str ou None)")


def esta_fechada(status: str) -> bool:
    """True para qualquer desfecho final (won/lost/abandoned) — False
    só para "open". Usado para nunca contar uma oportunidade encerrada
    como aberta em estatísticas (regra de teste explícita da Tarefa
    8.1)."""
    return status in ("won", "lost", "abandoned")


def resumo_por_status(opportunities: list[dict]) -> dict:
    """Agregação pura: contagem por status + abertas/fechadas. Recebe
    uma lista de dicts com pelo menos a chave "status" (mesmo formato
    de `api.database.listar_opportunities()`), nunca acessa o banco."""
    contagem: dict = {"open": 0, "won": 0, "lost": 0, "abandoned": 0}
    for opp in opportunities:
        status = opp.get("status")
        if status in contagem:
            contagem[status] += 1

    abertas = contagem["open"]
    fechadas = contagem["won"] + contagem["lost"] + contagem["abandoned"]
    return {
        "por_status": contagem,
        "abertas": abertas,
        "fechadas": fechadas,
        "total": abertas + fechadas,
    }
