# -*- coding: utf-8 -*-
"""
SALEIA — agent/sales_science_engine.py

Sales Science Engine (FASE 13 do "PROMPT MESTRE — SALE-IA V2"). Função
pura (sem IA/banco) — **não recalcula nada**: consolida, sob um
contrato de saída único, os resultados que os módulos estatísticos das
Fases 8-12 já produzem.

Escopo original (confirmado com o usuário): só o **contrato** de
saída (`montar_insight()`) + **wrappers dos 5 submódulos que já
existiam** — mesmo padrão de "contrato primeiro, motor depois" já
usado na Fase 7 (`sales_reasoning_engine.py`, V.1.4.84 antes da
V.1.4.85). **Fechado nesta rodada** (usuário confirmou "fechar 2
módulos pendentes"): os 2 submódulos que faltavam,
`agent/objection_trend_analyzer.py` e
`agent/conversion_driver_analyzer.py` (novos, mesma disciplina de
reuso das primitivas de `win_loss_rules.py`), com seus próprios
wrappers abaixo — os 7 submódulos literais do prompt mestre estão
todos implementados agora.

**Regra literal do prompt mestre, imposta estruturalmente — "Saída
nunca deve ser apenas 'descobrimos isso'"**: `montar_insight()` exige
`insight` + `evidence` + `sample` + `possible_confounders` +
`recommended_test` sempre presentes (não vazios) — `ValueError` em
qualquer um faltando. Um "insight" sem evidência, sem tamanho de
amostra, sem lista de possíveis confundidores considerados e sem uma
próxima validação sugerida nunca é aceito por este módulo, mesmo
disciplina de evidência obrigatória já usada em `SalesEvent`/
`SalesEvidence` (Fase 1) e nos guardas de causalidade das Fases 8-9.

**Cada wrapper só reshape o resultado que o submódulo correspondente
já calculou** — nenhum cálculo estatístico novo mora aqui:
- `insight_de_win_loss_analyzer` ← `win_loss_rules.comparar_por_
  variavel_categorica()` (Fase 8)
- `insight_de_seasonality_engine` ← `seasonality_rules.
  detectar_sazonalidade()` (Fase 9)
- `insight_de_seller_benchmark` ← `seller_benchmark_rules.
  benchmark_controlado()` (Fase 12.1) — único wrapper onde
  `possible_confounders` é populado automaticamente (a variável de
  controle É o confundidor identificado), os outros exigem a lista
  do chamador.
- `insight_de_strategy_effectiveness` ← `recommendation_
  effectiveness_rules.calcular_efetividade_por_estrategia()` (Fase 10.3)
- `insight_de_pattern_discovery` ← `pattern_discovery_rules.
  descobrir_padrao()` (Fase 12.2)
- `insight_de_objection_trend_analyzer` ← `objection_trend_analyzer.
  calcular_tendencias()` (novo, esta rodada)
- `insight_de_conversion_driver_analyzer` ← `conversion_driver_
  analyzer.ranquear_drivers()` (novo, esta rodada)

Cada wrapper retorna `None` (não um insight vazio) quando o submódulo
de origem não encontrou sinal estatisticamente defensável — nunca
força um "insight" a partir de ruído.
"""

from typing import Optional

# As 7 submódulos literais do prompt mestre — documentação do
# vocabulário completo do serviço, não travado ao que já foi
# implementado (`SUBMODULOS_IMPLEMENTADOS` abaixo é o subconjunto real).
SALES_SCIENCE_SUBMODULOS = (
    "pattern_discovery",
    "seasonality_engine",
    "win_loss_analyzer",
    "seller_benchmark",
    "strategy_effectiveness",
    "objection_trend_analyzer",
    "conversion_driver_analyzer",
)

SUBMODULOS_IMPLEMENTADOS = frozenset({
    "pattern_discovery", "seasonality_engine", "win_loss_analyzer",
    "seller_benchmark", "strategy_effectiveness",
    "objection_trend_analyzer", "conversion_driver_analyzer",
})

# Os 7 submódulos literais do prompt mestre estão todos implementados
# desde esta rodada — mantido como frozenset vazio (em vez de remover
# a constante) para não quebrar quem já importa `SUBMODULOS_PENDENTES`.
SUBMODULOS_PENDENTES = frozenset()

RECOMMENDED_TEST_PADRAO = (
    "Rodar um experimento controlado (Fase 14 / Experiment Engine) "
    "antes de mudar o comportamento de todos os vendedores com base "
    "só nesta observação."
)


def montar_insight(
    submodulo: str,
    insight: str,
    evidence,
    sample: int,
    possible_confounders: list,
    recommended_test: str,
    confidence: Optional[float] = None,
) -> dict:
    """Monta um insight no contrato de saída literal da Fase 13 —
    `INSIGHT`/`EVIDENCE`/`SAMPLE`/`CONFIDENCE`/`POSSIBLE_CONFOUNDERS`/
    `RECOMMENDED_TEST`. Levanta `ValueError` quando qualquer campo
    obrigatório (tudo exceto `confidence`, que pode ser `None` quando
    o submódulo de origem não produz um intervalo de confiança
    formal) está ausente/vazio — "nunca apenas 'descobrimos isso'"
    imposto estruturalmente, não só por instrução."""
    if submodulo not in SALES_SCIENCE_SUBMODULOS:
        raise ValueError(f"submodulo inválido: {submodulo!r} (esperado um de {SALES_SCIENCE_SUBMODULOS})")
    if not insight or not isinstance(insight, str):
        raise ValueError("insight é obrigatório e não pode ser vazio")
    if not evidence:
        raise ValueError("evidence é obrigatória e não pode ser vazia — insight sem evidência nunca é aceito")
    if not isinstance(sample, int) or sample < 1:
        raise ValueError(f"sample precisa ser um inteiro >= 1, recebido {sample!r}")
    if possible_confounders is None or not isinstance(possible_confounders, list):
        raise ValueError("possible_confounders é obrigatória (lista — pode ser vazia se nenhum foi identificado, mas precisa ser considerada explicitamente)")
    if not recommended_test or not isinstance(recommended_test, str):
        raise ValueError("recommended_test é obrigatório e não pode ser vazio")
    if confidence is not None and not (0.0 <= confidence <= 1.0):
        raise ValueError(f"confidence precisa estar em [0,1] ou ser None, recebido {confidence!r}")

    return {
        "submodulo": submodulo,
        "insight": insight,
        "evidence": evidence,
        "sample": sample,
        "confidence": confidence,
        "possible_confounders": possible_confounders,
        "recommended_test": recommended_test,
    }


def insight_de_win_loss_analyzer(
    grupo: dict,
    campo: str,
    valor,
    confianca: float = 0.95,
    possible_confounders: Optional[list] = None,
    recommended_test: str = RECOMMENDED_TEST_PADRAO,
) -> Optional[dict]:
    """Reshape de UM grupo já calculado por `win_loss_rules.
    comparar_por_variavel_categorica(opportunities, campo)["grupos"]
    [valor]`. `confianca` precisa bater com o valor usado na chamada
    original (a função de origem não devolve isso no resultado).
    Retorna `None` quando o grupo não tem amostra suficiente — nada a
    reportar ainda."""
    if not grupo.get("amostra_suficiente"):
        return None
    return montar_insight(
        submodulo="win_loss_analyzer",
        insight=grupo["afirmacao"],
        evidence={"won": grupo["won"], "lost": grupo["lost"], "campo": campo, "valor": valor},
        sample=grupo["total"],
        possible_confounders=possible_confounders if possible_confounders is not None else [
            f"não controlado por outras variáveis além de {campo!r} — considerar seller_benchmark_rules.benchmark_controlado() antes de agir"
        ],
        recommended_test=recommended_test,
        confidence=confianca,
    )


def insight_de_seasonality_engine(
    periodo_resultado: dict,
    dimensao: str,
    periodo,
    confianca: float = 0.95,
    possible_confounders: Optional[list] = None,
    recommended_test: str = RECOMMENDED_TEST_PADRAO,
) -> Optional[dict]:
    """Reshape de UM período já calculado por `seasonality_rules.
    detectar_sazonalidade(linhas, dimensao)["periodos"][periodo]`.
    Retorna `None` quando o período não foi marcado `significativo`."""
    if not periodo_resultado.get("significativo"):
        return None
    return montar_insight(
        submodulo="seasonality_engine",
        insight=periodo_resultado["afirmacao"],
        evidence={"won": periodo_resultado["won"], "lost": periodo_resultado["lost"], "dimensao": dimensao, "periodo": periodo},
        sample=periodo_resultado["total"],
        possible_confounders=possible_confounders if possible_confounders is not None else [
            f"não controlado por segmento/produto — considerar contextual_seasonality_rules.detectar_sazonalidade_contextual() antes de agir"
        ],
        recommended_test=recommended_test,
        confidence=confianca,
    )


def insight_de_seller_benchmark(
    resultado_benchmark: dict,
    campo_controle: str,
    recommended_test: str = RECOMMENDED_TEST_PADRAO,
) -> Optional[dict]:
    """Reshape do controle de UMA variável já calculado por
    `seller_benchmark_rules.benchmark_controlado()["controles"]
    [campo_controle]`. Único wrapper onde `possible_confounders` é
    preenchido automaticamente — a própria variável de controle É o
    confundidor identificado. Retorna `None` quando nenhum
    confundimento foi detectado (`possivel_simpsons_paradox=False`) —
    esse é o resultado "limpo", não um insight novo a reportar."""
    controle = resultado_benchmark["controles"][campo_controle]
    if not controle.get("possivel_simpsons_paradox"):
        return None
    sample = sum(g["total"] for g in resultado_benchmark["comparacao_bruta"]["grupos"].values())
    return montar_insight(
        submodulo="seller_benchmark",
        insight=controle["afirmacao"],
        evidence={"direcoes_por_segmento": controle["direcoes_por_segmento"], "direcao_agregada": controle["direcao_agregada"]},
        sample=sample,
        possible_confounders=[campo_controle],
        recommended_test=recommended_test,
    )


def insight_de_strategy_effectiveness(
    resumo_estrategia: dict,
    strategy: str,
    possible_confounders: Optional[list] = None,
    recommended_test: str = RECOMMENDED_TEST_PADRAO,
) -> Optional[dict]:
    """Reshape do resumo de UMA estratégia já calculado por
    `recommendation_effectiveness_rules.
    calcular_efetividade_por_estrategia()[strategy]`. Retorna `None`
    quando a amostra de avanço não é suficiente (sem `afirmacao`)."""
    if not resumo_estrategia.get("amostra_avanco_suficiente") or not resumo_estrategia.get("afirmacao"):
        return None
    return montar_insight(
        submodulo="strategy_effectiveness",
        insight=resumo_estrategia["afirmacao"],
        evidence={"strategy": strategy, "taxa_desfecho_positivo": resumo_estrategia.get("taxa_desfecho_positivo")},
        sample=resumo_estrategia["usos"],
        possible_confounders=possible_confounders if possible_confounders is not None else [
            "não controlado por segmento/vendedor/ticket — taxa observada, não causal"
        ],
        recommended_test=recommended_test,
    )


def insight_de_pattern_discovery(
    resultado_padrao: dict,
    possible_confounders: Optional[list] = None,
    recommended_test: str = RECOMMENDED_TEST_PADRAO,
) -> Optional[dict]:
    """Reshape do resultado já calculado por `pattern_discovery_
    rules.descobrir_padrao()`. Retorna `None` quando `diferenca_
    significativa` é `False`."""
    if not resultado_padrao.get("diferenca_significativa"):
        return None
    return montar_insight(
        submodulo="pattern_discovery",
        insight=resultado_padrao["afirmacao"],
        evidence={"top_group": resultado_padrao["top_group"], "control_group": resultado_padrao["control_group"]},
        sample=resultado_padrao["sample"],
        possible_confounders=possible_confounders if possible_confounders is not None else [
            "grupo top/control não controlado por segmento/lead_source/ticket/produto — considerar seller_benchmark_rules antes de agir"
        ],
        recommended_test=recommended_test,
        confidence=resultado_padrao.get("confidence"),
    )


def insight_de_objection_trend_analyzer(
    categoria_resultado: dict,
    categoria: str,
    confianca: float = 0.95,
    possible_confounders: Optional[list] = None,
    recommended_test: str = RECOMMENDED_TEST_PADRAO,
) -> Optional[dict]:
    """Reshape de UMA categoria já calculada por `objection_trend_
    analyzer.calcular_tendencias(eventos, ordem_periodos)
    ["categorias"][categoria]`. `confianca` precisa bater com o valor
    usado na chamada original (o resultado de origem não devolve
    isso). Retorna `None` quando a categoria não foi marcada
    `significativo`."""
    if not categoria_resultado.get("significativo"):
        return None
    return montar_insight(
        submodulo="objection_trend_analyzer",
        insight=categoria_resultado["afirmacao"],
        evidence={"categoria": categoria, "n_inicio": categoria_resultado["n_inicio"], "n_fim": categoria_resultado["n_fim"]},
        sample=categoria_resultado["n_inicio"] + categoria_resultado["n_fim"],
        possible_confounders=possible_confounders if possible_confounders is not None else [
            "não controlado por segmento/produto/vendedor — mudança na mistura de clientes pode explicar a tendência, não só o comportamento de vendas"
        ],
        recommended_test=recommended_test,
        confidence=confianca,
    )


def insight_de_conversion_driver_analyzer(
    driver: dict,
    confianca: float = 0.95,
    possible_confounders: Optional[list] = None,
    recommended_test: str = RECOMMENDED_TEST_PADRAO,
) -> dict:
    """Reshape de UM driver já ranqueado por `conversion_driver_
    analyzer.ranquear_drivers()` — a função de origem já filtra por
    significância (não retorna drivers sem sinal), então este wrapper
    nunca retorna `None`, diferente dos outros."""
    return montar_insight(
        submodulo="conversion_driver_analyzer",
        insight=driver["afirmacao"],
        evidence={"campo": driver["campo"], "valor": driver["valor"], "taxa_conversao": driver["taxa_conversao"]},
        sample=driver["sample"],
        possible_confounders=possible_confounders if possible_confounders is not None else [
            f"driver isolado em {driver['campo']!r} — considerar seller_benchmark_rules.benchmark_controlado() se envolver comparação entre vendedores"
        ],
        recommended_test=recommended_test,
        confidence=confianca,
    )
