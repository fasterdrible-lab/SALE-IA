"""
SALEIA — agent/sales_event_rules.py

Validação pura do SalesEvent (FASE 1 / TAREFA 1.1 do "PROMPT MESTRE —
SALE-IA V2"). Nenhuma chamada de IA, nenhum acesso a banco — só as regras
de negócio que api/database.py::criar_sales_event() aplica antes de
persistir. Mesmo padrão de agent/propensao_rules.py e
agent/signo_solar_rules.py (função pura, testável isolada).

Diferente de AiUsageEvent/KnowledgeItem (escrita "melhor esforço", nunca
lança), SalesEvent é dado de domínio — entrada inválida deve falhar alto
e cedo (ValueError), nunca ser silenciosamente descartada ou corrigida.
"""

# As 14 categorias mínimas do modelo canônico da venda (TAREFA 1.1).
SALES_EVENT_TYPES = frozenset({
    "PAIN_DETECTED",
    "IMPACT_IDENTIFIED",
    "BUYING_SIGNAL",
    "OBJECTION_RAISED",
    "OBJECTION_RESOLVED",
    "PRICE_DISCUSSION",
    "COMPETITOR_MENTIONED",
    "DECISION_MAKER_IDENTIFIED",
    "CHAMPION_IDENTIFIED",
    "BUDGET_IDENTIFIED",
    "NEXT_STEP_AGREED",
    "DEAL_STALLED",
    "DEAL_WON",
    "DEAL_LOST",
})

# Origens cuja evidência (evidence_quote) é obrigatória — regra explícita
# do prompt mestre: "Nenhum evento pode existir sem evidência quando sua
# origem é uma conversa." Fontes não conversacionais (ex.: ajuste manual
# de um vendedor, evento derivado de outro evento já validado) ficam de
# fora da exigência.
SOURCES_QUE_EXIGEM_EVIDENCIA = frozenset({"conversation"})


def validar_sales_event(dados: dict) -> None:
    """Valida os campos de um SalesEvent antes de persistir.

    Levanta ValueError com mensagem clara na primeira regra violada; não
    retorna nada em caso de sucesso (mesma convenção de validação
    "fail-fast" — chamador decide o que fazer com a exceção)."""
    event_type = dados.get("event_type")
    if event_type not in SALES_EVENT_TYPES:
        raise ValueError(
            f"event_type inválido: {event_type!r} (esperado um de {sorted(SALES_EVENT_TYPES)})"
        )

    confidence = dados.get("confidence")
    try:
        confidence_valor = float(confidence)
    except (TypeError, ValueError):
        raise ValueError(f"confidence inválida: {confidence!r} (esperado float entre 0 e 1)")
    if not (0.0 <= confidence_valor <= 1.0):
        raise ValueError(f"confidence fora do intervalo [0, 1]: {confidence_valor!r}")

    source = dados.get("source")
    if source in SOURCES_QUE_EXIGEM_EVIDENCIA and not (dados.get("evidence_quote") or "").strip():
        raise ValueError(
            f"evidence_quote obrigatória quando source={source!r} (evento sem evidência de uma conversa)"
        )
