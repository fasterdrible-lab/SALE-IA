# -*- coding: utf-8 -*-
"""
SALEIA — agent/conversion_driver_analyzer.py

Conversion Driver Analyzer (submódulo do `SalesScienceEngine`, FASE 13
do "PROMPT MESTRE — SALE-IA V2"). Função pura (sem IA/banco) —
reaproveita `win_loss_rules.calcular_taxa_conversao`/`comparar_por_
variavel_categorica` (Fase 8) em vez de duplicar estatística.

Objetivo: "o que mais impulsiona conversão nesta amostra" — ranqueia,
entre vários campos categóricos (`segment`/`lead_source`/`product`/
`objection`/etc.), os pares `(campo, valor)` cuja taxa de conversão
mais diverge do baseline geral, do maior desvio para o menor. Mesmo
princípio genérico de `win_loss_rules.WIN_LOSS_VARIAVEIS` — a lista de
campos a avaliar vem do chamador, este módulo não inventa quais
variáveis de negócio existem.

**Nunca causa, sempre associação** — mesma disciplina das Fases 8-9:
único texto livre vem de `TEMPLATE_DRIVER` (template fixo), guardado
por `GuardaContraCausalidadeTest`. Um driver no topo do ranking é uma
correlação forte nesta amostra, não uma prova de que mudar esse valor
aumenta conversão — para isso existe a Fase 14 (Experiment Engine).
"""

from agent.win_loss_rules import AMOSTRA_MINIMA_PADRAO, calcular_taxa_conversao, comparar_por_variavel_categorica

TEMPLATE_DRIVER = (
    "{campo}={valor!r} está associado a uma diferença de {diferenca:+.0%} "
    "em relação ao baseline geral ({taxa:.0%} vs {baseline:.0%}, n={n}) "
    "nesta amostra — associação observada, nunca confirmação de mecanismo."
)


def ranquear_drivers(
    opportunities: list,
    campos: list,
    minimo_amostra: int = AMOSTRA_MINIMA_PADRAO,
    confianca: float = 0.95,
) -> list:
    """Ranqueia `(campo, valor)` por desvio absoluto da taxa de
    conversão em relação ao baseline geral da amostra, do maior para o
    menor. Só inclui pares com amostra suficiente **e** cujo intervalo
    de confiança de Wilson não contém o baseline (mesmo critério
    honesto de significância já usado em `seasonality_rules.py`,
    Fase 9) — nunca inclui ruído no ranking.

    `campos`: lista de nomes de campo categóricos a avaliar (o
    chamador decide quais variáveis de negócio existem e fazem
    sentido comparar).

    Retorna uma lista de dicts `{"campo", "valor", "taxa_conversao",
    "baseline_taxa_conversao", "diferenca_vs_baseline", "sample",
    "afirmacao"}`, ordenada por `|diferenca_vs_baseline|` decrescente.
    """
    resumo_baseline = calcular_taxa_conversao(opportunities)
    baseline_taxa = resumo_baseline["taxa_conversao"]
    if baseline_taxa is None:
        return []

    drivers = []
    for campo in campos:
        comparacao = comparar_por_variavel_categorica(opportunities, campo, minimo_amostra, confianca)
        for valor, grupo in comparacao["grupos"].items():
            ic = grupo["intervalo_confianca"]
            if not grupo["amostra_suficiente"] or ic is None:
                continue
            significativo = not (ic[0] <= baseline_taxa <= ic[1])
            if not significativo:
                continue

            diferenca = grupo["taxa_conversao"] - baseline_taxa
            afirmacao = TEMPLATE_DRIVER.format(
                campo=campo, valor=valor, diferenca=diferenca,
                taxa=grupo["taxa_conversao"], baseline=baseline_taxa, n=grupo["total"],
            )
            drivers.append({
                "campo": campo,
                "valor": valor,
                "taxa_conversao": grupo["taxa_conversao"],
                "baseline_taxa_conversao": baseline_taxa,
                "diferenca_vs_baseline": diferenca,
                "sample": grupo["total"],
                "afirmacao": afirmacao,
            })

    drivers.sort(key=lambda d: abs(d["diferenca_vs_baseline"]), reverse=True)
    return drivers
