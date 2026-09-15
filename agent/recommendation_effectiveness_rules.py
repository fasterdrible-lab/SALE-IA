"""
SALEIA — agent/recommendation_effectiveness_rules.py

Recommendation Effectiveness (FASE 10 / TAREFA 10.3 do "PROMPT MESTRE
— SALE-IA V2"), fecha a Fase 10. Constrói sobre os estados da Tarefa
10.2 (`agent/recommendation_usage_rules.py`) — arquivo próprio, mesmo
padrão de cada Tarefa ganhar seu módulo mesmo construindo sobre a
anterior (`deal_risk_rules.py` sobre `meddpicc_rules.py`, Fase 4).

Cadeia do prompt mestre: recommendation → seller used → conversation
reaction → stage advancement → opportunity result. Esta função é
genérica sobre listas de dicts já estruturados pelo chamador (mesmo
princípio de `win_loss_rules.comparar_por_variavel_categorica`, Fase
8, e `data_warehouse_rules`/`seasonality_rules`, Fase 9) — não decide
COMO detectar "conversation reaction" ou "stage advancement" a partir
de uma reunião real; isso é integração futura não pedida por esta
tarefa (mede efetividade a partir de sinais já classificados, não os
extrai).

**Regra "Importante" do prompt mestre, imposta estruturalmente**: nunca
confundir "avanço imediato" (`taxa_avanco`) com "causa da venda"
(`taxa_desfecho_positivo`) — são **dois números sempre separados**,
nunca combinados numa única métrica ou numa afirmação causal. Mesma
disciplina "nunca causa, sempre associação" de `win_loss_rules.py`
(Fase 8) e `seasonality_rules.py`/`contextual_seasonality_rules.py`
(Fase 9): único texto livre vem de `TEMPLATE_EFETIVIDADE`, guardado por
`GuardaContraCausalidadeTest`.
"""

from typing import Optional

from agent.recommendation_usage_rules import RECOMMENDATION_USAGE_STATES
from agent.win_loss_rules import AMOSTRA_MINIMA_PADRAO, amostra_suficiente

# Estados da Tarefa 10.2 que contam como "uso" pro dashboard da Tarefa
# 10.3 (schema literal: "187 usos") — decisão desta rodada:
# PARTIALLY_USED ainda é algum grau de uso real; IGNORED/UNKNOWN não.
ESTADOS_CONTADOS_COMO_USO = frozenset({"USED", "PARTIALLY_USED"})

TEMPLATE_EFETIVIDADE = (
    "{strategy!r} foi usada {usos} vezes nesta amostra; {taxa_avanco:.0%} "
    "desses usos estão associados a avanço de estágio logo em seguida. "
    "Isso mede avanço imediato — não é o mesmo que dizer que a "
    "recomendação causou a venda: o resultado final da oportunidade "
    "(ganha/perdida) é medido separadamente, nunca combinado com este "
    "número."
)


def calcular_efetividade_por_estrategia(
    eventos: list,
    minimo_amostra: int = AMOSTRA_MINIMA_PADRAO,
) -> dict:
    """Agrupa eventos de recomendação por `strategy` e mede efetividade
    a partir de sinais já classificados pelo chamador — nunca extrai
    nada de uma transcrição real.

    Cada item de `eventos` é um dict:
      - `strategy` (str, obrigatório)
      - `state` (um de `RECOMMENDATION_USAGE_STATES`, Tarefa 10.2 —
        obrigatório; evento fora do vocabulário levanta `ValueError`)
      - `stage_advanced` (`Optional[bool]`): se a conversa avançou de
        estágio logo após o uso — `None` quando esse dado não existe
        pra este evento (nunca vira `False` por omissão)
      - `opportunity_result` (`Optional["won"|"lost"]`): resultado
        final da oportunidade associada — `None` quando ainda aberta
        ou desconhecida

    Retorna, por `strategy`: `usos` (contagem, schema literal do
    prompt mestre), `taxa_avanco` (associação com avanço imediato) e
    `taxa_desfecho_positivo` (associação com resultado final) — **dois
    números sempre calculados e reportados separadamente**, nunca
    combinados numa métrica ou afirmação causal única."""
    por_estrategia: dict = {}

    for evento in eventos:
        strategy = evento.get("strategy")
        if not strategy:
            continue

        estado = evento.get("state")
        if estado not in RECOMMENDATION_USAGE_STATES:
            raise ValueError(f"state inválido: {estado!r} (esperado um de {sorted(RECOMMENDATION_USAGE_STATES)})")
        if estado not in ESTADOS_CONTADOS_COMO_USO:
            continue

        grupo = por_estrategia.setdefault(strategy, {
            "usos": 0, "avancos": 0, "com_avanco_dado": 0, "won": 0, "lost": 0,
        })
        grupo["usos"] += 1

        stage_advanced = evento.get("stage_advanced")
        if stage_advanced is not None:
            grupo["com_avanco_dado"] += 1
            if stage_advanced:
                grupo["avancos"] += 1

        resultado = evento.get("opportunity_result")
        if resultado == "won":
            grupo["won"] += 1
        elif resultado == "lost":
            grupo["lost"] += 1

    resumo = {}
    for strategy, g in por_estrategia.items():
        taxa_avanco: Optional[float] = (g["avancos"] / g["com_avanco_dado"]) if g["com_avanco_dado"] else None
        total_desfecho = g["won"] + g["lost"]
        taxa_desfecho_positivo: Optional[float] = (g["won"] / total_desfecho) if total_desfecho else None

        afirmacao = None
        if taxa_avanco is not None:
            afirmacao = TEMPLATE_EFETIVIDADE.format(strategy=strategy, usos=g["usos"], taxa_avanco=taxa_avanco)

        resumo[strategy] = {
            "usos": g["usos"],
            "taxa_avanco": taxa_avanco,
            "amostra_avanco_suficiente": amostra_suficiente(g["com_avanco_dado"], minimo_amostra),
            "taxa_desfecho_positivo": taxa_desfecho_positivo,
            "amostra_desfecho_suficiente": amostra_suficiente(total_desfecho, minimo_amostra),
            "afirmacao": afirmacao,
        }

    return resumo
