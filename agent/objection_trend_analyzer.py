# -*- coding: utf-8 -*-
"""
SALEIA — agent/objection_trend_analyzer.py

Objection Trend Analyzer (submódulo do `SalesScienceEngine`, FASE 13
do "PROMPT MESTRE — SALE-IA V2"). Função pura (sem IA/banco) —
reaproveita `win_loss_rules.amostra_suficiente`/`intervalo_confianca_
wilson` (Fase 8) em vez de duplicar estatística, mesmo princípio de
`seasonality_rules.py` (Fase 9)/`pattern_discovery_rules.py` (Fase
12.2).

Objetivo: detectar se a participação de uma categoria de objeção (ex.:
`PRICE`, `TRUST` — vocabulário de `objection_rules.OBJECTION_TIPOS`,
Fase 6.1, embora este módulo não trave a categoria a essa lista) vem
crescendo ou diminuindo ao longo do tempo, comparando um período
inicial contra um período final.

**Quem monta os eventos e decide os períodos**: cada evento é
`{"category": str, "period": <valor comparável>}` — a classificação
da categoria (Fase 6.1) e a extração do período (calendário real,
`data_warehouse_rules`/`seasonality_rules`, Fase 9) são feitas pelo
chamador; este módulo nunca extrai objeção de transcrição livre.
`ordem_periodos` é a lista de períodos já ordenada cronologicamente
pelo chamador — o módulo só divide essa lista ao meio (primeira
metade = "início", segunda metade = "fim"), nunca decide sozinho o
que é "recente".

Significância sem scipy — mesma disciplina honesta de
`seasonality_rules.py`: a diferença de participação só é reportada
como `significativo` quando ambos os totais (início/fim) têm amostra
suficiente **e** os intervalos de confiança de Wilson da proporção em
cada período não se sobrepõem.
"""

from typing import Optional

from agent.win_loss_rules import AMOSTRA_MINIMA_PADRAO, amostra_suficiente, intervalo_confianca_wilson

TEMPLATE_TENDENCIA_OBJECAO = (
    "A objeção {categoria!r} representou {inicio:.0%} das objeções no "
    "período inicial e {fim:.0%} no período final ({direcao}), uma "
    "diferença de {diferenca:+.0%} nesta amostra (n_início={n_inicio}, "
    "n_fim={n_fim}) — associação observada nesta amostra, nunca "
    "confirmação de mecanismo."
)


def calcular_tendencias(
    eventos: list,
    ordem_periodos: list,
    minimo_amostra: int = AMOSTRA_MINIMA_PADRAO,
    confianca: float = 0.95,
) -> dict:
    """Compara a participação de cada categoria de objeção entre a
    primeira e a segunda metade de `ordem_periodos`.

    `eventos`: lista de `{"category": str, "period": valor}` — um item
    por objeção já classificada e datada pelo chamador.
    `ordem_periodos`: períodos distintos já ordenados
    cronologicamente (precisa ter pelo menos 2 — levanta `ValueError`
    caso contrário).

    Retorna `{"total_inicio", "total_fim", "categorias": {categoria:
    {...}}}` — cada categoria com `n_inicio`/`n_fim`/
    `proporcao_inicio`/`proporcao_fim`/`diferenca`/`significativo`/
    `direcao`/`afirmacao`. `afirmacao`/`direcao` só vêm preenchidos
    quando `significativo` é `True`.
    """
    if len(ordem_periodos) < 2:
        raise ValueError("ordem_periodos precisa ter pelo menos 2 períodos para detectar tendência")

    meio = len(ordem_periodos) // 2
    periodos_inicio = set(ordem_periodos[:meio])
    periodos_fim = set(ordem_periodos[meio:])

    eventos_inicio = [e for e in eventos if e.get("period") in periodos_inicio]
    eventos_fim = [e for e in eventos if e.get("period") in periodos_fim]
    total_inicio = len(eventos_inicio)
    total_fim = len(eventos_fim)

    categorias = sorted({e["category"] for e in eventos if e.get("category") is not None})

    resultado = {}
    for categoria in categorias:
        n_inicio = sum(1 for e in eventos_inicio if e["category"] == categoria)
        n_fim = sum(1 for e in eventos_fim if e["category"] == categoria)

        proporcao_inicio: Optional[float] = (n_inicio / total_inicio) if total_inicio else None
        proporcao_fim: Optional[float] = (n_fim / total_fim) if total_fim else None

        suficiente = amostra_suficiente(total_inicio, minimo_amostra) and amostra_suficiente(total_fim, minimo_amostra)
        significativo = False
        if suficiente and proporcao_inicio is not None and proporcao_fim is not None:
            ic_inicio = intervalo_confianca_wilson(n_inicio, total_inicio, confianca)
            ic_fim = intervalo_confianca_wilson(n_fim, total_fim, confianca)
            significativo = (ic_inicio[0] > ic_fim[1]) or (ic_fim[0] > ic_inicio[1])

        diferenca: Optional[float] = (
            (proporcao_fim - proporcao_inicio) if (proporcao_inicio is not None and proporcao_fim is not None) else None
        )

        direcao = None
        afirmacao = None
        if significativo:
            direcao = "crescente" if diferenca > 0 else "decrescente"
            afirmacao = TEMPLATE_TENDENCIA_OBJECAO.format(
                categoria=categoria, inicio=proporcao_inicio, fim=proporcao_fim,
                direcao=direcao, diferenca=diferenca, n_inicio=n_inicio, n_fim=n_fim,
            )

        resultado[categoria] = {
            "n_inicio": n_inicio, "n_fim": n_fim,
            "proporcao_inicio": proporcao_inicio, "proporcao_fim": proporcao_fim,
            "diferenca": diferenca, "significativo": significativo,
            "direcao": direcao, "afirmacao": afirmacao,
        }

    return {"total_inicio": total_inicio, "total_fim": total_fim, "categorias": resultado}
