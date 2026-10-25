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

Objection Trends (B4, 24/10/2026) usa as SalesEvidence `OBJECTION:*`
gravadas pelo ciclo de tempo real (A2) — ver `montar_objection_trends`.

Seller Benchmark (B5, 24/10/2026) classifica o vendedor pela taxa real
de conversão — ver `montar_seller_benchmark`.

Os demais ficam como gap explícito — Best Strategies e Recommendation
Effectiveness não são questão de
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
        "Nenhuma objeção classificada registrada ainda (SalesEvidence "
        "OBJECTION:<categoria>, gravada pelo ciclo de tempo real desde a A2)."
    ),
}

# B4: o período da tendência é a semana ISO da 1ª vez que a categoria
# apareceu na reunião. Semana, não mês: o histórico real recomeçou em
# 11/10/2026 (reset), por mês não haveria 2 períodos por um bom tempo.
_PREFIXO_OBJECAO = "OBJECTION:"
_MIN_PERIODOS = 2


def _semana_iso(valor) -> str | None:
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(str(valor))
    except (TypeError, ValueError):
        return None
    ano, semana, _ = dt.isocalendar()
    return f"{ano}-W{semana:02d}"


def eventos_de_objecao(evidencias: list) -> list:
    """Converte SalesEvidence `OBJECTION:<categoria>` em eventos
    `{"category", "period"}` de `objection_trend_analyzer`. Conta **uma
    vez por (reunião, categoria)**: a mesma objeção volta com citações
    diferentes a cada ciclo (a transcrição é acumulada e a legenda vem em
    pedaços), e contar citação inflaria a categoria das reuniões longas."""
    primeiras = {}
    for ev in evidencias or []:
        tipo = str(ev.get("type") or "")
        if not tipo.startswith(_PREFIXO_OBJECAO):
            continue
        categoria = tipo[len(_PREFIXO_OBJECAO):].strip()
        periodo = _semana_iso(ev.get("timestamp") or ev.get("created_at"))
        if not categoria or not periodo:
            continue
        chave = (ev.get("meeting_id"), categoria)
        if chave not in primeiras or periodo < primeiras[chave]:
            primeiras[chave] = periodo
    return [{"category": cat, "period": per} for (_m, cat), per in primeiras.items()]


def montar_objection_trends(evidencias: list) -> dict:
    """B4: Objection Trends com dado real. Sem objeção → gap; só 1
    semana → indisponível por volume (mostra a distribuição mesmo
    assim); 2+ semanas → `calcular_tendencias` e só as categorias
    significativas viram insight."""
    from agent.objection_trend_analyzer import calcular_tendencias
    from agent.sales_science_engine import insight_de_objection_trend_analyzer

    eventos = eventos_de_objecao(evidencias)
    if not eventos:
        return dict(OBJECTION_TRENDS_NAO_DISPONIVEL)

    distribuicao = {}
    for e in eventos:
        distribuicao[e["category"]] = distribuicao.get(e["category"], 0) + 1
    distribuicao = dict(sorted(distribuicao.items(), key=lambda kv: (-kv[1], kv[0])))
    periodos = sorted({e["period"] for e in eventos})
    base = {"total_objecoes": len(eventos), "periodos": periodos, "distribuicao": distribuicao}

    if len(periodos) < _MIN_PERIODOS:
        return {
            "disponivel": False,
            "motivo": (
                f"{len(eventos)} objeção(ões) classificada(s), todas na semana "
                f"{periodos[0]} — a tendência precisa de pelo menos "
                f"{_MIN_PERIODOS} semanas com objeção registrada."
            ),
            **base,
        }

    resultado = calcular_tendencias(eventos, periodos)
    insights = []
    for categoria, cat_resultado in resultado["categorias"].items():
        insight = insight_de_objection_trend_analyzer(cat_resultado, categoria)
        if insight:
            insights.append(insight)
    return {
        "disponivel": True,
        "total_inicio": resultado["total_inicio"],
        "total_fim": resultado["total_fim"],
        "insights": insights,
        **base,
    }


# B5: tier do vendedor pela taxa real de conversão (won/(won+lost)) das
# oportunidades dele. Mínimo por vendedor para entrar no ranking e mínimo
# de vendedores para haver top/median/low.
MIN_FECHADAS_POR_VENDEDOR = 10
MIN_VENDEDORES_BENCHMARK = 3
CONTROLES_BENCHMARK = ("product", "ticket")


def _faixa_ticket(valor, cortes):
    if valor is None or cortes is None:
        return None
    if valor <= cortes[0]:
        return "baixo"
    if valor <= cortes[1]:
        return "médio"
    return "alto"


def classificar_vendedores(opportunities: list, minimo_fechadas: int = MIN_FECHADAS_POR_VENDEDOR) -> list:
    """Taxa de conversão por `seller_id` (só won/lost) e tier por terço
    do ranking entre os vendedores com `minimo_fechadas`: 1º terço `top`,
    último `low`, resto `median`. Abaixo do mínimo o vendedor aparece com
    `tier: None` — nunca classificado com amostra pequena."""
    from agent.win_loss_rules import calcular_taxa_conversao

    por_vendedor = {}
    for o in opportunities:
        if o.get("seller_id") and o.get("status") in ("won", "lost"):
            por_vendedor.setdefault(o["seller_id"], []).append(o)

    linhas = []
    for seller_id, opps in por_vendedor.items():
        taxa = calcular_taxa_conversao(opps)
        linhas.append({"seller_id": seller_id, **taxa, "tier": None})

    elegiveis = sorted(
        (l for l in linhas if l["total"] >= minimo_fechadas),
        key=lambda l: (-l["taxa_conversao"], l["seller_id"]),
    )
    if len(elegiveis) >= MIN_VENDEDORES_BENCHMARK:
        terco = max(1, len(elegiveis) // 3)
        for i, linha in enumerate(elegiveis):
            if i < terco:
                linha["tier"] = "top"
            elif i >= len(elegiveis) - terco:
                linha["tier"] = "low"
            else:
                linha["tier"] = "median"
    return sorted(linhas, key=lambda l: (-l["total"], l["seller_id"]))


def montar_seller_benchmark(opportunities: list) -> dict:
    """B5: Seller Benchmark com `seller_tier` real. Compara a conversão
    por tier e checa (paradoxo de Simpson, `benchmark_controlado`) se a
    vantagem top × low se mantém dentro de cada produto e faixa de ticket.
    O tier sai da própria taxa de conversão, então "top converte mais" é
    esperado por construção — o que informa é a checagem por controle
    (vendedor que só parece melhor porque pega produto/ticket melhor)."""
    from agent.seller_benchmark_rules import benchmark_controlado, comparar_tiers
    from agent.sales_science_engine import insight_de_seller_benchmark, insight_de_win_loss_analyzer
    from agent.win_loss_rules import _percentil

    vendedores = classificar_vendedores(opportunities)
    tiers = {l["seller_id"]: l["tier"] for l in vendedores if l["tier"]}
    if not tiers:
        elegiveis = sum(1 for l in vendedores if l["total"] >= MIN_FECHADAS_POR_VENDEDOR)
        return {
            "disponivel": False,
            "motivo": (
                f"{elegiveis} vendedor(es) com pelo menos {MIN_FECHADAS_POR_VENDEDOR} "
                f"oportunidades fechadas (ganha/perdida) — o benchmark precisa de "
                f"{MIN_VENDEDORES_BENCHMARK} para separar top/median/low."
            ),
            "vendedores": vendedores,
        }

    valores = sorted(
        o["estimated_value"] for o in opportunities
        if o.get("seller_id") in tiers and o.get("status") in ("won", "lost") and o.get("estimated_value") is not None
    )
    cortes = (_percentil(valores, 100 / 3), _percentil(valores, 200 / 3)) if len(valores) >= 3 else None
    linhas = [
        {**o, "seller_tier": tiers[o["seller_id"]], "ticket": _faixa_ticket(o.get("estimated_value"), cortes)}
        for o in opportunities if o.get("seller_id") in tiers
    ]

    insights = []
    for tier, grupo in comparar_tiers(linhas)["grupos"].items():
        insight = insight_de_win_loss_analyzer(grupo, "seller_tier", tier)
        if insight:
            insights.append(insight)
    confundimentos = []
    try:
        resultado = benchmark_controlado(linhas, "top", "low", campos_controle=CONTROLES_BENCHMARK)
        for campo in CONTROLES_BENCHMARK:
            insight = insight_de_seller_benchmark(resultado, campo)
            if insight:
                confundimentos.append(insight)
    except ValueError:
        pass  # sem estratos comparáveis — nada a afirmar sobre confundimento
    return {
        "disponivel": True,
        "vendedores": vendedores,
        "insights": insights,
        "confundimentos": confundimentos,
    }


def montar_sales_science_insights(opportunities: list, evidencias_objecao: list | None = None) -> dict:
    """Monta o payload de Sales Science a partir de uma lista de
    `Opportunity` já buscada no banco (formato de dict de
    `api/database.py`). Nunca acessa banco ou chama IA — puramente
    orquestra os motores estatísticos já prontos. `evidencias_objecao`
    (B4): SalesEvidence `OBJECTION:*` já buscadas, para Objection Trends."""
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
        "seller_benchmark": montar_seller_benchmark(opportunities),
        "strategy_effectiveness": dict(STRATEGY_EFFECTIVENESS_NAO_DISPONIVEL),
        "objection_trends": montar_objection_trends(evidencias_objecao),
    }
