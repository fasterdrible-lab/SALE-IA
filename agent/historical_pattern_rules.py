"""Bloco 2 / Tarefa 2.1 de docs/tasks-sales-reasoning-engine-completo.md
— alimenta o campo `historical_patterns` do SalesReasoningEngine (Fase
7) com o insight de Win/Loss real (Fase 8/13) que bate com o estágio
atual da oportunidade vinculada à reunião.

Depende da Tarefa 3.1 (`agent/opportunity_link_rules.py`) já ter
vinculado a reunião a uma `Opportunity` — sem `opportunity_id`, este
módulo nunca tem o que filtrar.

**Só filtra por `stage`, nunca por `product`/`competitor`**: esses 2
campos só nascem quando a oportunidade fecha (`Opportunity.product`/
`competitor`, Fase 8) — uma oportunidade ainda aberta (o caso real de
toda reunião em andamento) nunca tem esses campos preenchidos.

**Nunca recalcula estatística** — reaproveita `agent/win_loss_
rules.py::comparar_por_variavel_categorica()` (Fase 8) e `agent/
sales_science_engine.py::insight_de_win_loss_analyzer()` (Fase 13)
exatamente como `agent/sales_science_insights_rules.py` (Fase 22/bloco
3) já faz — só que filtrado a 1 categoria (`stage`) em vez das 3
(`stage`/`product`/`competitor`) que `montar_sales_science_insights()`
computa de uma vez, para não recalcular win_loss/seasonality/
conversion_drivers inteiros a cada ciclo de `/tempo-real` sem
necessidade."""

from typing import Optional


def obter_historical_pattern_da_opportunity(opportunity_id: int) -> Optional[dict]:
    """Busca o insight de Win/Loss por `stage` relevante pra esta
    oportunidade. Retorna `None` (nunca fabrica sinal) quando: a
    oportunidade não existe, não tem `stage` definido, ou não há
    amostra estatística suficiente pra esse `stage` ainda
    (`amostra_suficiente=False` em `win_loss_rules`, Fase 8)."""
    from api.database import listar_opportunities, obter_opportunity
    from agent.sales_science_engine import insight_de_win_loss_analyzer
    from agent.win_loss_rules import comparar_por_variavel_categorica

    opportunity = obter_opportunity(opportunity_id)
    if not opportunity:
        return None

    stage = opportunity.get("stage")
    if not stage:
        return None

    opportunities = listar_opportunities(limit=5000)
    resultado = comparar_por_variavel_categorica(opportunities, "stage")
    grupo = resultado["grupos"].get(stage)
    if not grupo:
        return None

    return insight_de_win_loss_analyzer(grupo, "stage", stage)
