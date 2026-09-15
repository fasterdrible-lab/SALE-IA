# -*- coding: utf-8 -*-
"""
SALEIA — agent/conversation_metrics_rules.py

Conversation Metrics (FASE 11 / TAREFA 11.1 do "PROMPT MESTRE — SALE-IA
V2", inicio da Fase 11 — Seller Coaching). Funcao pura (sem IA/banco),
mesmo padrao de `deal_risk_rules.py`/`win_loss_rules.py` — genérica
sobre uma transcricao ja temporizada e estruturada pelo chamador
(lista de "turns" com falante/inicio/fim/texto), nunca extrai nada de
audio bruto nem decide diarizacao.

**Disciplina de escopo, mesma das Fases 4-10**: metricas puramente
estruturais (talk ratio, interrupcoes, monologos) e a deteccao de
pergunta (via "?" no texto) sao calculadas diretamente da transcricao
temporizada — sao sinais objetivos, sem julgamento de conteudo de
negocio. Ja `price_timing`/`presentation_timing`/
`objection_exploration_rate`/`next_step_rate` dependem de classificacao
de negocio (isto e uma discussao de preco? isto e a apresentacao? esta
objecao foi explorada? um proximo passo foi proposto?) — esses sinais
sao SEMPRE recebidos ja classificados do chamador (flags `is_price_
mention`/`is_presentation_mention` por turno, lista `objections` com
`explored`, `next_step_proposto`), nunca inferidos por keyword matching
aqui dentro. Mesmo principio de `deal_risk_rules.calcular_riscos()`
(Fase 4.2): "de onde vem cada sinal em producao real e integracao
futura, fora do escopo desta tarefa".

Cada `turn` da transcricao e um dict:
    - `speaker` (str): "vendedor" | "cliente" | qualquer outro valor
      (ex.: "incerto") — falante nao identificado nunca conta nos
      ratios/interrupcoes (mesmo principio de "dado ausente nunca vira
      0/False por omissao" ja usado em `recommendation_effectiveness_
      rules.py`, Fase 10).
    - `start`/`end` (float, segundos desde o inicio da reuniao).
    - `text` (str, opcional, default ""): usado so para detectar "?"
      (pergunta) e sua abertura (aberta/fechada) — sinal estrutural do
      proprio texto do turno, nao uma classificacao de negocio.
    - `is_price_mention`/`is_presentation_mention` (bool, opcional,
      default False): flags ja classificadas pelo chamador.
"""

from typing import Optional

PALAVRAS_ABERTURA_PADRAO = frozenset({
    "o que", "que", "como", "por que", "por quê", "qual", "quais",
    "quando", "onde", "quem", "quanto", "quantos", "quanta", "quantas",
    "conte", "descreva", "explique", "fale",
})

LIMIAR_MONOLOGO_SEGUNDOS_PADRAO = 90.0


def _duracao(turn: dict) -> float:
    return max(0.0, float(turn.get("end", 0.0)) - float(turn.get("start", 0.0)))


def _eh_pergunta(texto: str) -> bool:
    return texto.strip().endswith("?")


def _tipo_pergunta(texto: str, palavras_abertura: frozenset) -> str:
    """'aberta' quando o texto comeca com uma das palavras de abertura
    (apos remover pontuacao inicial), senao 'fechada'. Heuristica
    determinística e sobrescrevivel — decisao desta rodada, o prompt
    mestre nao define a lista exata de palavras."""
    limpo = texto.strip().lstrip("¿¡").strip().lower()
    for palavra in sorted(palavras_abertura, key=len, reverse=True):
        if limpo.startswith(palavra):
            return "aberta"
    return "fechada"


def calcular_metricas_conversa(
    turns: list,
    objections: Optional[list] = None,
    next_step_proposto: Optional[bool] = None,
    palavras_abertura: frozenset = PALAVRAS_ABERTURA_PADRAO,
    limiar_monologo_segundos: float = LIMIAR_MONOLOGO_SEGUNDOS_PADRAO,
) -> dict:
    """Calcula as métricas literais da Tarefa 11.1 a partir de uma
    transcrição temporizada conhecida (`turns`, ordenados internamente
    por `start` — o chamador não precisa garantir ordem).

    `objections`: lista opcional de dicts `{"explored": bool}` (uma
    entrada por objeção já identificada na reunião, ex.: via
    `agent/objection_rules.py`, Fase 6) — usada só para
    `objection_exploration_rate`.

    `next_step_proposto`: `Optional[bool]` — `None` quando esse dado
    não foi determinado ainda (nunca vira "não propôs" por omissão).

    Retorna um dict com as 11 métricas literais do prompt mestre.
    Qualquer métrica sem amostra/dado suficiente vem como `None` —
    nunca `0`/`False` por omissão.
    """
    turns_ordenados = sorted(turns, key=lambda t: float(t.get("start", 0.0)))

    tempo_vendedor = sum(_duracao(t) for t in turns_ordenados if t.get("speaker") == "vendedor")
    tempo_cliente = sum(_duracao(t) for t in turns_ordenados if t.get("speaker") == "cliente")
    tempo_total = tempo_vendedor + tempo_cliente

    seller_talk_ratio = (tempo_vendedor / tempo_total) if tempo_total > 0 else None
    customer_talk_ratio = (tempo_cliente / tempo_total) if tempo_total > 0 else None

    questions_total = 0
    open_questions = 0
    closed_questions = 0
    for t in turns_ordenados:
        if t.get("speaker") != "vendedor":
            continue
        texto = t.get("text", "") or ""
        if not _eh_pergunta(texto):
            continue
        questions_total += 1
        if _tipo_pergunta(texto, palavras_abertura) == "aberta":
            open_questions += 1
        else:
            closed_questions += 1

    interruptions = 0
    for anterior, atual in zip(turns_ordenados, turns_ordenados[1:]):
        falantes_validos = anterior.get("speaker") in ("vendedor", "cliente") and atual.get("speaker") in ("vendedor", "cliente")
        if falantes_validos and atual.get("speaker") != anterior.get("speaker") and float(atual.get("start", 0.0)) < float(anterior.get("end", 0.0)):
            interruptions += 1

    monologues = 0
    bloco_falante = None
    bloco_duracao = 0.0
    for t in turns_ordenados + [None]:
        falante_atual = t.get("speaker") if t is not None else None
        if falante_atual == bloco_falante and t is not None:
            bloco_duracao += _duracao(t)
            continue
        if bloco_falante in ("vendedor", "cliente") and bloco_duracao >= limiar_monologo_segundos:
            monologues += 1
        bloco_falante = falante_atual
        bloco_duracao = _duracao(t) if t is not None else 0.0

    price_timing = next((float(t["start"]) for t in turns_ordenados if t.get("is_price_mention")), None)
    presentation_timing = next((float(t["start"]) for t in turns_ordenados if t.get("is_presentation_mention")), None)

    objection_exploration_rate = None
    if objections:
        total = len(objections)
        explorados = sum(1 for o in objections if o.get("explored"))
        objection_exploration_rate = explorados / total if total > 0 else None

    next_step_rate = None if next_step_proposto is None else (1.0 if next_step_proposto else 0.0)

    return {
        "seller_talk_ratio": seller_talk_ratio,
        "customer_talk_ratio": customer_talk_ratio,
        "questions_total": questions_total,
        "open_questions": open_questions,
        "closed_questions": closed_questions,
        "interruptions": interruptions,
        "monologues": monologues,
        "price_timing": price_timing,
        "presentation_timing": presentation_timing,
        "objection_exploration_rate": objection_exploration_rate,
        "next_step_rate": next_step_rate,
    }
