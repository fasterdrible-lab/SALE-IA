"""Fase 22 (Frontend) / bloco "Sales Science" do "PROMPT MESTRE —
SALE-IA V2". Função pura — zero IA/banco — que monta os 8 campos
literais (Win/Loss, Seasonality, Objection Trends, Best Strategies,
Seller Benchmark, Conversion Drivers, Experiments, Recommendation
Effectiveness) a partir de uma lista de `Opportunity` já buscada no
banco (mesmo formato de `api.database.listar_opportunities()`).

3 campos são dado real, alimentados pelos únicos campos categóricos
livres que `Opportunity` já tem hoje (`stage`/`product`/`competitor`)
e pelas datas reais (`close_date`/`created_at`), reaproveitando os
motores estatísticos já prontos desde as Fases 8, 9 e 13
(`win_loss_rules`/`data_warehouse_rules`/`seasonality_rules`/
`conversion_driver_analyzer`, todos consolidados sob o contrato único
de `agent/sales_science_engine.py::montar_insight()`).

5 campos ficam como gap explícito — Seller Benchmark, Best Strategies,
Objection Trends e Recommendation Effectiveness não são questão de
"esperar volume" (diferente de Win/Loss/Seasonality/Conversion
Drivers, que só precisam de mais oportunidades reais pra passar de
`amostra_suficiente=False`): nenhuma função no sistema gera o dado
bruto que essas 4 engines exigem, independente de quantas reuniões
acontecerem. Experiments (Fase 14) é uma feature diferente por
natureza (configurador de hipótese A/B, não analisador de dado
existente) e não tem tabela no banco — fora de escopo desta rodada,
decisão confirmada com o usuário.
"""

CAMPOS_CATEGORICOS_PADRAO = ("stage", "product", "competitor")
DIMENSOES_TEMPORAIS_PADRAO = ("month", "quarter", "weekday")

SELLER_BENCHMARK_NAO_DISPONIVEL = {
    "disponivel": False,
    "motivo": (
        "Seller Benchmark exige um campo seller_tier (top/median/low) já "
        "classificado por oportunidade — nenhuma métrica de desempenho de "
        "vendedor é calculada em nenhum lugar do sistema ainda. Não é questão "
        "de volume: sem essa classificação, nenhuma comparação é possível."
    ),
}

STRATEGY_EFFECTIVENESS_NAO_DISPONIVEL = {
    "disponivel": False,
    "motivo": (
        "Best Strategies / Recommendation Effectiveness exigem "
        "RecommendationEvent com uso classificado (USED/PARTIALLY_USED/"
        "IGNORED via detectar_uso_recomendacao(), Fase 10.2) — essa "
        "classificação nunca roda em produção (não conectada ao fluxo de "
        "tempo real), então não há nenhum dado, independente do volume de "
        "reuniões."
    ),
}

OBJECTION_TRENDS_NAO_DISPONIVEL = {
    "disponivel": False,
    "motivo": (
        "Objection Trends exige objeções já classificadas por categoria e "
        "período — a classificação (agent/objection_rules.py, Fase 6.1) "
        "nunca é chamada durante uma reunião real, então não há eventos pra "
        "analisar, independente do volume de reuniões."
    ),
}


def montar_sales_science_insights(opportunities: list) -> dict:
    """Monta o payload de Sales Science a partir de uma lista de
    `Opportunity` já buscada no banco (formato de dict de
    `api/database.py`). Nunca acessa banco ou chama IA — puramente
    orquestra os motores estatísticos já prontos."""
    from agent.win_loss_rules import comparar_por_variavel_categorica
    from agent.data_warehouse_rules import construir_dataset_analitico
    from agent.seasonality_rules import detectar_sazonalidade
    from agent.conversion_driver_analyzer import ranquear_drivers
    from agent.sales_science_engine import (
        insight_de_conversion_driver_analyzer,
        insight_de_seasonality_engine,
        insight_de_win_loss_analyzer,
    )

    win_loss = {}
    for campo in CAMPOS_CATEGORICOS_PADRAO:
        resultado = comparar_por_variavel_categorica(opportunities, campo)
        insights = []
        for valor, grupo in resultado["grupos"].items():
            insight = insight_de_win_loss_analyzer(grupo, campo, valor)
            if insight:
                insights.append(insight)
        win_loss[campo] = insights

    linhas = construir_dataset_analitico(opportunities)
    seasonality = {}
    for dimensao in DIMENSOES_TEMPORAIS_PADRAO:
        resultado = detectar_sazonalidade(linhas, dimensao)
        insights = []
        for periodo, periodo_resultado in resultado["periodos"].items():
            insight = insight_de_seasonality_engine(periodo_resultado, dimensao, periodo)
            if insight:
                insights.append(insight)
        seasonality[dimensao] = insights

    drivers = ranquear_drivers(opportunities, list(CAMPOS_CATEGORICOS_PADRAO))
    conversion_drivers = [insight_de_conversion_driver_analyzer(d) for d in drivers]

    return {
        "amostra_total": len(opportunities),
        "win_loss": win_loss,
        "seasonality": seasonality,
        "conversion_drivers": conversion_drivers,
        "seller_benchmark": dict(SELLER_BENCHMARK_NAO_DISPONIVEL),
        "strategy_effectiveness": dict(STRATEGY_EFFECTIVENESS_NAO_DISPONIVEL),
        "objection_trends": dict(OBJECTION_TRENDS_NAO_DISPONIVEL),
    }
