"""
SALEIA — agent/opportunity_memory_rules.py

Regras puras da OpportunityMemory (FASE 2 / TAREFA 2.1 do "PROMPT
MESTRE — SALE-IA V2"). Nenhuma chamada de IA, nenhum acesso a banco —
mesmo padrão de agent/sales_event_rules.py e
agent/sales_evidence_rules.py.

Regra central do prompt mestre: "informações históricas não desaparecem;
contradições são registradas e não silenciosamente sobrescritas". Cada
categoria da OpportunityMemory é tratada como uma lista **append-only**
de insights — `adicionar_insight()` nunca remove nem edita uma entrada
existente, só adiciona uma nova. Quando o `campo` (aspecto opcional
dentro da categoria, ex.: "orcamento_mensal" dentro de `metrics`) já
tinha um valor diferente registrado antes, a entrada nova aponta
`contradiz` para o id da entrada anterior — ambas ficam visíveis.
"""

from datetime import datetime
from typing import Optional

# As 13 categorias do modelo de conhecimento agregado (TAREFA 2.1).
OPPORTUNITY_MEMORY_CATEGORIES = frozenset({
    "pain_points",
    "business_impact",
    "goals",
    "objections",
    "competitors",
    "decision_process",
    "stakeholders",
    "champion",
    "economic_buyer",
    "metrics",
    "next_steps",
    "risks",
    "unknowns",
})

OPPORTUNITY_STATUSES = frozenset({"open", "won", "lost"})


def validar_status(status: str) -> None:
    if status not in OPPORTUNITY_STATUSES:
        raise ValueError(f"status inválido: {status!r} (esperado um de {sorted(OPPORTUNITY_STATUSES)})")


def adicionar_insight(
    insights_existentes: list,
    *,
    meeting_id: str,
    valor,
    campo: Optional[str] = None,
    evidence: Optional[str] = None,
    confidence: float = 1.0,
    timestamp: Optional[datetime] = None,
) -> tuple[list, Optional[dict]]:
    """Retorna (nova_lista, contradicao_ou_None) — nunca muta
    `insights_existentes` in-place nem remove/edita entradas antigas.

    `contradicao_ou_None` é a entrada anterior com o mesmo `campo` mas
    `valor` diferente, quando existir (para o chamador logar/alertar);
    de qualquer forma, ambas as entradas permanecem na lista retornada.
    """
    if not meeting_id:
        raise ValueError("meeting_id é obrigatório para registrar um insight")

    try:
        confidence_valor = float(confidence)
    except (TypeError, ValueError):
        raise ValueError(f"confidence inválida: {confidence!r} (esperado float entre 0 e 1)")
    if not (0.0 <= confidence_valor <= 1.0):
        raise ValueError(f"confidence fora do intervalo [0, 1]: {confidence_valor!r}")

    contradicao = None
    if campo:
        for existente in reversed(insights_existentes):
            if existente.get("campo") == campo:
                if existente.get("valor") != valor:
                    contradicao = existente
                break  # só compara com a entrada mais recente do mesmo campo

    novo_id = (max((i.get("id", 0) for i in insights_existentes), default=0)) + 1
    nova_entrada = {
        "id": novo_id,
        "meeting_id": meeting_id,
        "campo": campo,
        "valor": valor,
        "evidence": evidence,
        "confidence": confidence_valor,
        "timestamp": (timestamp or datetime.now()).isoformat(),
        "contradiz": contradicao["id"] if contradicao else None,
    }

    nova_lista = [*insights_existentes, nova_entrada]
    return nova_lista, contradicao
