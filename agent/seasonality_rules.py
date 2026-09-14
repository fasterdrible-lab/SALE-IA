"""
SALEIA — agent/seasonality_rules.py

Regras puras de Sazonalidade Temporal (FASE 9 / TAREFA 9.2 do "PROMPT
MESTRE — SALE-IA V2"). Nenhuma chamada de IA, nenhum acesso a banco,
zero numpy/scipy — mesmo padrão de agent/win_loss_rules.py, cujas
primitivas estatísticas (`amostra_suficiente`,
`intervalo_confianca_wilson`) são reaproveitadas aqui em vez de
duplicadas.

Opera sobre linhas do dataset analítico construído por
`agent.data_warehouse_rules.construir_dataset_analitico()` (Tarefa
9.1) — cada linha já tem as dimensões de calendário e os flags
`won`/`lost`.

Regra científica herdada da Tarefa 8.2 (Win/Loss Intelligence): nunca
declarar causalidade, sempre associação — mesma disciplina de template
fixo + `GuardaContraCausalidadeTest`.

Critério de significância: um período é "significativo" quando a
amostra é suficiente **e** a taxa de conversão geral (baseline) cai
*fora* do intervalo de confiança de Wilson daquele período — não um
teste de hipótese formal (qui-quadrado etc., exigiria scipy), mas uma
forma honesta e auto-calibrada de nunca apontar sazonalidade que os
próprios dados não sustentam: em dados sem sazonalidade real, o
baseline cai dentro do IC do período na esmagadora maioria das vezes
por construção estatística.
"""

from typing import Optional

from agent.win_loss_rules import AMOSTRA_MINIMA_PADRAO, amostra_suficiente, intervalo_confianca_wilson

# As 5 dimensões temporais literais da Tarefa 9.2. "date" (a 6ª
# dimensão de calendário, da Tarefa 9.1) fica de fora de propósito —
# granularidade única por linha, quase nunca se repete o suficiente
# pra "sazonalidade" (recorrência) fazer sentido.
DIMENSOES_TEMPORAIS = frozenset({"month", "quarter", "week", "weekday", "hour"})

TEMPLATE_SAZONALIDADE = (
    "No período {dimensao}={periodo!r}, a conversão está associada a uma "
    "diferença de {diferenca:+.0%} em relação ao baseline geral "
    "({taxa:.0%} vs {baseline:.0%} de baseline, n={n})."
)


def taxa_conversao_por_periodo(linhas_analiticas: list, dimensao: str) -> dict:
    """Agrupa linhas do dataset analítico (Tarefa 9.1) pelo valor de
    `dimensao` e calcula won/(won+lost) por período. Linha sem `won`
    nem `lost` (oportunidade ainda aberta) não entra na comparação —
    mesmo princípio de `win_loss_rules.comparar_por_variavel_categorica`."""
    if dimensao not in DIMENSOES_TEMPORAIS:
        raise ValueError(f"dimensão inválida: {dimensao!r} (esperado um de {sorted(DIMENSOES_TEMPORAIS)})")

    contagens: dict = {}
    for linha in linhas_analiticas:
        won, lost = linha.get("won"), linha.get("lost")
        if not won and not lost:
            continue
        periodo = linha.get(dimensao)
        if periodo is None:
            continue
        c = contagens.setdefault(periodo, {"won": 0, "lost": 0})
        c["won" if won else "lost"] += 1

    resultado = {}
    for periodo, c in contagens.items():
        total = c["won"] + c["lost"]
        resultado[periodo] = {
            "won": c["won"], "lost": c["lost"], "total": total,
            "taxa_conversao": (c["won"] / total) if total else None,
        }
    return resultado


def detectar_sazonalidade(
    linhas_analiticas: list,
    dimensao: str,
    minimo_amostra: int = AMOSTRA_MINIMA_PADRAO,
    confianca: float = 0.95,
) -> dict:
    """Detecta períodos (mês/trimestre/semana/dia da semana/horário)
    cuja taxa de conversão diverge do baseline geral de forma
    estatisticamente defensável. Nunca declara causalidade — só
    associação (`TEMPLATE_SAZONALIDADE`, mesma disciplina da Tarefa
    8.2)."""
    por_periodo = taxa_conversao_por_periodo(linhas_analiticas, dimensao)

    baseline_won = sum(c["won"] for c in por_periodo.values())
    baseline_total = sum(c["total"] for c in por_periodo.values())
    baseline_taxa = (baseline_won / baseline_total) if baseline_total else None

    periodos = {}
    for periodo, c in por_periodo.items():
        suficiente = amostra_suficiente(c["total"], minimo_amostra)
        ic = None
        diferenca = None
        significativo = False
        afirmacao = None

        if suficiente and baseline_taxa is not None:
            ic = intervalo_confianca_wilson(c["won"], c["total"], confianca)
            diferenca = c["taxa_conversao"] - baseline_taxa
            significativo = not (ic[0] <= baseline_taxa <= ic[1])
            if significativo:
                afirmacao = TEMPLATE_SAZONALIDADE.format(
                    dimensao=dimensao, periodo=periodo, diferenca=diferenca,
                    taxa=c["taxa_conversao"], baseline=baseline_taxa, n=c["total"],
                )

        periodos[periodo] = {
            **c,
            "amostra_suficiente": suficiente,
            "intervalo_confianca": ic,
            "diferenca_vs_baseline": diferenca,
            "significativo": significativo,
            "afirmacao": afirmacao,
        }

    return {
        "dimensao": dimensao,
        "baseline_taxa_conversao": baseline_taxa,
        "baseline_total": baseline_total,
        "periodos": periodos,
    }
