"""
SALEIA — agent/contextual_seasonality_rules.py

Regras puras de Sazonalidade Contextual (FASE 9 / TAREFA 9.3 do
"PROMPT MESTRE — SALE-IA V2"). Nenhuma chamada de IA, nenhum acesso a
banco, zero numpy/scipy — mesmo padrão de agent/seasonality_rules.py
(Tarefa 9.2), cujas primitivas estatísticas (`amostra_suficiente`,
`intervalo_confianca_wilson`, ambas de agent/win_loss_rules.py) são
reaproveitadas aqui, nunca duplicadas.

Estende a Tarefa 9.2 (sazonalidade só por calendário) combinando um
período temporal com uma dimensão de contexto (segment/product/origin/
ticket/client_type/objection_type/opportunity_stage — os 7 campos
literais do prompt mestre, reaproveitando os mesmos nomes já usados em
`data_warehouse_rules.DIMENSOES_DATASET` onde já existem, mais
`client_type` como novo, ainda não rastreado por nenhuma Opportunity).

**Cada descoberta usa os 6 campos literais do prompt mestre**
(`sample_size`, `baseline`, `observed`, `difference`, `confidence`,
`period`) — schema de saída, não um detalhe de implementação.

Regra científica herdada da Tarefa 8.2: nunca causa, sempre associação.
"""

from agent.win_loss_rules import amostra_suficiente, intervalo_confianca_wilson, AMOSTRA_MINIMA_PADRAO
from agent.seasonality_rules import DIMENSOES_TEMPORAIS

# Os 7 campos literais do prompt mestre. `client_type` é o único ainda
# não rastreado por `data_warehouse_rules.DIMENSOES_DATASET` (Tarefa
# 9.1) — os outros 6 reaproveitam os mesmos nomes de lá.
DIMENSOES_CONTEXTO = frozenset({
    "segment", "product", "origin", "ticket", "client_type",
    "objection_type", "opportunity_stage",
})

TEMPLATE_SAZONALIDADE_CONTEXTUAL = (
    "Em {dimensao_temporal}={period!r} × {dimensao_contexto}={context_value!r}, "
    "a conversão está associada a uma diferença de {difference:+.0%} em relação "
    "ao baseline geral ({observed:.0%} vs {baseline:.0%} de baseline, "
    "sample_size={sample_size})."
)


def detectar_sazonalidade_contextual(
    linhas_analiticas: list,
    dimensao_temporal: str,
    dimensao_contexto: str,
    minimo_amostra: int = AMOSTRA_MINIMA_PADRAO,
    confianca: float = 0.95,
) -> list:
    """Combina um período temporal (Tarefa 9.2) com um valor de
    contexto (`dimensao_contexto`) e reporta só as combinações
    (período, contexto) cuja taxa de conversão diverge do **mesmo
    baseline geral (global)** usado na Tarefa 9.2 — não o baseline
    daquele contexto isolado, para que "Q4 × segmento SaaS" seja
    comparável com qualquer outra descoberta na mesma lista.

    Retorna uma lista (não um dict por período/contexto) já ordenada
    pela magnitude da diferença — a forma mais direta de responder "o
    que descobrimos" sem o chamador precisar iterar uma estrutura
    aninhada."""
    if dimensao_temporal not in DIMENSOES_TEMPORAIS:
        raise ValueError(f"dimensão temporal inválida: {dimensao_temporal!r} (esperado um de {sorted(DIMENSOES_TEMPORAIS)})")
    if not dimensao_contexto:
        raise ValueError("dimensao_contexto é obrigatória")

    baseline_won = sum(1 for l in linhas_analiticas if l.get("won"))
    baseline_lost = sum(1 for l in linhas_analiticas if l.get("lost"))
    baseline_total = baseline_won + baseline_lost
    baseline_taxa = (baseline_won / baseline_total) if baseline_total else None

    contagens: dict = {}
    for linha in linhas_analiticas:
        won, lost = linha.get("won"), linha.get("lost")
        if not won and not lost:
            continue
        periodo = linha.get(dimensao_temporal)
        contexto = linha.get(dimensao_contexto)
        if periodo is None or contexto is None:
            continue
        chave = (periodo, contexto)
        c = contagens.setdefault(chave, {"won": 0, "lost": 0})
        c["won" if won else "lost"] += 1

    descobertas = []
    if baseline_taxa is not None:
        for (periodo, contexto), c in contagens.items():
            total = c["won"] + c["lost"]
            if not amostra_suficiente(total, minimo_amostra):
                continue
            observed = c["won"] / total
            ic = intervalo_confianca_wilson(c["won"], total, confianca)
            if ic[0] <= baseline_taxa <= ic[1]:
                continue  # dentro do IC -- nao e uma descoberta significativa

            difference = observed - baseline_taxa
            descobertas.append({
                "sample_size": total,
                "baseline": baseline_taxa,
                "observed": observed,
                "difference": difference,
                "confidence": confianca,
                "period": periodo,
                "context_field": dimensao_contexto,
                "context_value": contexto,
                "afirmacao": TEMPLATE_SAZONALIDADE_CONTEXTUAL.format(
                    dimensao_temporal=dimensao_temporal, period=periodo,
                    dimensao_contexto=dimensao_contexto, context_value=contexto,
                    difference=difference, observed=observed, baseline=baseline_taxa,
                    sample_size=total,
                ),
            })

    descobertas.sort(key=lambda d: abs(d["difference"]), reverse=True)
    return descobertas
