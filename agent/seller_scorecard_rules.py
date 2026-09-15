# -*- coding: utf-8 -*-
"""
SALEIA — agent/seller_scorecard_rules.py

Seller Scorecard (FASE 11 / TAREFA 11.2 do "PROMPT MESTRE — SALE-IA
V2"), fecha a Fase 11 (Seller Coaching). Função pura (sem IA/banco),
mesmo padrão de `conversation_metrics_rules.py`/`deal_risk_rules.py`
— genérica sobre evidências já classificadas pelo chamador (de
`conversation_metrics_rules.py`/Tarefa 11.1, `spin_coverage_rules.py`/
Fase 3, `meddpicc_rules.py`/Fase 4, `objection_rules.py`/`negotiation_
rules.py`/Fase 6, etc.) — nunca decide sozinha o que conta como
evidência de cada dimensão.

**Regra literal da Tarefa 11.2, imposta estruturalmente — "Não criar
score arbitrário"**: cada dimensão do scorecard é uma fração
transparente `criterios_atendidos / total_criterios` sobre a lista de
evidências recebida — nunca um peso/fórmula inventada, nunca combinada
com as outras 6 dimensões numa nota geral única (essa combinação nem
existe na API deste módulo — `GuardaContraScoreArbitrarioTest`, em
`tests/test_seller_scorecard_rules.py`, confirma que nenhuma chave de
"score geral" é produzida). Dimensão sem nenhuma evidência recebida
nunca vira `0` por omissão — vem como `None` (mesmo princípio de
`conversation_metrics_rules.py`/`recommendation_effectiveness_
rules.py`).

**"Cada score precisa apontar evidências"**: o resultado de cada
dimensão sempre inclui a lista de evidências que o compõe (nunca só o
número) — cada evidência é `{"criterio": str, "atendido": bool,
"quote": Optional[str]}`; `criterio` (o que foi avaliado) é sempre
obrigatório, `quote` é opcional porque nem toda evidência vem de uma
fala literal (ex.: `customer_talk_ratio` de `conversation_metrics_
rules.py` é um sinal estrutural, não uma citação).
"""

from typing import Optional

SCORECARD_DIMENSOES = (
    "Discovery",
    "Listening",
    "Qualification",
    "Value Building",
    "Negotiation",
    "Closing",
    "Next Step Discipline",
)


def validar_evidencia(evidencia: dict) -> None:
    """Levanta ValueError quando a evidência não tem o mínimo pra
    justificar um score — `criterio` (o que foi avaliado) obrigatório
    e não-vazio, `atendido` obrigatoriamente booleano."""
    if not evidencia.get("criterio"):
        raise ValueError("evidencia sem 'criterio' — todo score precisa apontar o que foi avaliado")
    if not isinstance(evidencia.get("atendido"), bool):
        raise ValueError(f"evidencia com 'atendido' inválido: {evidencia.get('atendido')!r} (esperado bool)")


def calcular_scorecard(evidencias_por_dimensao: Optional[dict] = None) -> dict:
    """Calcula o Seller Scorecard das 7 dimensões literais da Tarefa
    11.2 a partir de evidências já classificadas pelo chamador.

    `evidencias_por_dimensao`: dict opcional `{dimensao: [evidencia,
    ...]}` — chave fora de `SCORECARD_DIMENSOES` levanta `ValueError`
    (vocabulário fechado, mesma disciplina de `OBJECTION_TIPOS`/
    `MOTIVATION_TIPOS`). Dimensão ausente do dict é tratada como "sem
    evidência ainda", não como erro.

    Retorna um dict com as 7 dimensões, cada uma
    `{"score": Optional[float], "criterios_atendidos": int,
    "total_criterios": int, "evidencias": list}` — `score` é sempre
    `criterios_atendidos / total_criterios`, ou `None` quando
    `total_criterios == 0` (nunca `0` por omissão). Não existe nenhuma
    chave de score combinado/geral neste retorno — ver regra "não
    criar score arbitrário" no docstring do módulo.
    """
    evidencias_por_dimensao = evidencias_por_dimensao or {}

    for dimensao in evidencias_por_dimensao:
        if dimensao not in SCORECARD_DIMENSOES:
            raise ValueError(f"dimensão inválida: {dimensao!r} (esperada uma de {SCORECARD_DIMENSOES})")

    scorecard = {}
    for dimensao in SCORECARD_DIMENSOES:
        evidencias = list(evidencias_por_dimensao.get(dimensao, []))
        for evidencia in evidencias:
            validar_evidencia(evidencia)

        total = len(evidencias)
        atendidos = sum(1 for e in evidencias if e["atendido"])
        score = (atendidos / total) if total > 0 else None

        scorecard[dimensao] = {
            "score": score,
            "criterios_atendidos": atendidos,
            "total_criterios": total,
            "evidencias": evidencias,
        }

    return scorecard


def dimensoes_sem_evidencia(scorecard: dict) -> list:
    """Lista as dimensões cujo `score` veio `None` (nenhuma evidência
    recebida ainda) — útil pro Dashboard sinalizar "dado insuficiente"
    em vez de esconder a dimensão."""
    return [dimensao for dimensao, resultado in scorecard.items() if resultado["score"] is None]
