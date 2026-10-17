"""Fase 22 (Frontend) / bloco "Seller Coaching", último bloco de Dashboard
da Fase 22 do "PROMPT MESTRE — SALE-IA V2". Função pura — zero IA/banco —
que monta os 8 campos literais (Talk Ratio, Question Quality, SPIN
Coverage, Qualification, Objection Handling, Negotiation, Next Step
Discipline, Trend).

Diferente dos outros 2 blocos da Fase 22 (Opportunity Intelligence, 9/12
campos reais; Sales Science, 3/7 campos reais), investigação prévia
confirmada com o usuário antes de codar achou que **nenhum dos 8 campos
tem dado real hoje**:

- Talk Ratio / Question Quality / Next Step Discipline exigem uma lista
  de `turns` com speaker/start/end/text (agent/conversation_metrics_
  rules.py, Fase 11.1) — nada no sistema captura transcrição estruturada
  por turno (confirmado por grep em api/processador_tempo_real.py e
  api/webhook_tactiq.py: só texto corrido, sem timestamp por falante).
- SPIN Coverage / Qualification exigem fatos já classificados com
  evidence_quote (agent/spin_coverage_rules.py, Fase 3;
  agent/meddpicc_rules.py, Fase 4.1) — mesmo gap já documentado em
  agent/opportunity_intelligence_rules.py (Fase 22/bloco 2): nenhuma
  função extrai isso de transcrição livre.
- Objection Handling / Negotiation exigem objeção falada + causa raiz
  já classificadas (agent/objection_rules.py/agent/negotiation_rules.py,
  Fase 6) — a classificação nunca roda em produção.
- Trend exigiria histórico de Seller Scorecard (agent/
  seller_scorecard_rules.py, Fase 11.2) persistido ao longo do tempo —
  o módulo existe e é puro, mas nunca foi chamado com dado real nem
  persistido em nenhuma tabela.

Usuário escolheu, depois dessa investigação, **só o contrato — os 8
campos como gap explícito, sem dado real nesta rodada** — mesma
disciplina de honestidade de agent/observability_metrics_rules.py
(Fase 19), agent/quality_monitoring_rules.py (Fase 19.1) e
agent/opportunity_intelligence_rules.py/agent/
sales_science_insights_rules.py (Fase 22, blocos 2/3). Fecha a Fase 22
(Frontend) por completo.
"""

SELLER_COACHING_CAMPOS = (
    "talk_ratio",
    "question_quality",
    "spin_coverage",
    "qualification",
    "objection_handling",
    "negotiation",
    "next_step_discipline",
    "trend",
)

TALK_RATIO_NAO_DISPONIVEL = {
    "disponivel": False,
    "motivo": (
        "Nenhuma reunião sua nos últimos 30 dias com falas temporizadas "
        "(turnos com tempo existem desde a extensão 1.4.37 / V.1.4.187, A8)."
    ),
}

QUESTION_QUALITY_NAO_DISPONIVEL = {
    "disponivel": False,
    "motivo": (
        "Question Quality (perguntas abertas/fechadas do vendedor) vem das "
        "mesmas falas temporizadas de Talk Ratio — nenhuma pergunta sua "
        "registrada nos últimos 30 dias."
    ),
}

SPIN_COVERAGE_NAO_DISPONIVEL = {
    "disponivel": False,
    "motivo": (
        "SPIN Coverage exige fatos classificados por estágio com "
        "evidence_quote (agent/spin_coverage_rules.py, Fase 3) — mesmo "
        "gap já documentado em agent/opportunity_intelligence_rules.py: "
        "nenhuma função extrai isso de transcrição livre."
    ),
}

QUALIFICATION_NAO_DISPONIVEL = {
    "disponivel": False,
    "motivo": (
        "Qualification (MEDDPICC) exige status UNKNOWN/PARTIAL/CONFIRMED "
        "por item com evidence_quote (agent/meddpicc_rules.py, Fase 4.1) "
        "— mesmo gap já documentado em agent/"
        "opportunity_intelligence_rules.py."
    ),
}

OBJECTION_HANDLING_NAO_DISPONIVEL = {
    "disponivel": False,
    "motivo": (
        "Objection Handling exige objeção falada + hipótese de causa "
        "raiz já classificadas (agent/objection_rules.py, Fase 6.1) — a "
        "classificação nunca roda em produção."
    ),
}

NEGOTIATION_NAO_DISPONIVEL = {
    "disponivel": False,
    "motivo": (
        "Negotiation exige a mesma classificação de objeção de Objection "
        "Handling como entrada (agent/negotiation_rules.py, Fase 6.2) — "
        "sem ela, não há estratégia pra avaliar."
    ),
}

NEXT_STEP_DISCIPLINE_NAO_DISPONIVEL = {
    "disponivel": False,
    "motivo": (
        "Next Step Discipline exige saber se um próximo passo foi "
        "proposto em cada reunião (classificação de conteúdo, não só "
        "tempo de fala) — ainda não existe."
    ),
}

TREND_NAO_DISPONIVEL = {
    "disponivel": False,
    "motivo": (
        "Trend exigiria histórico de Seller Scorecard (agent/"
        "seller_scorecard_rules.py, Fase 11.2) persistido ao longo do "
        "tempo — o módulo existe e é puro, mas nunca foi chamado com "
        "dado real nem persistido em nenhuma tabela."
    ),
}

SELLER_COACHING_GAPS = {
    "talk_ratio": TALK_RATIO_NAO_DISPONIVEL,
    "question_quality": QUESTION_QUALITY_NAO_DISPONIVEL,
    "spin_coverage": SPIN_COVERAGE_NAO_DISPONIVEL,
    "qualification": QUALIFICATION_NAO_DISPONIVEL,
    "objection_handling": OBJECTION_HANDLING_NAO_DISPONIVEL,
    "negotiation": NEGOTIATION_NAO_DISPONIVEL,
    "next_step_discipline": NEXT_STEP_DISCIPLINE_NAO_DISPONIVEL,
    "trend": TREND_NAO_DISPONIVEL,
}


def montar_seller_coaching(seller_id: str, conversa: dict | None = None) -> dict:
    """Monta o payload de Seller Coaching pra um vendedor. Nunca acessa
    banco ou chama IA. `conversa` (A8, V.1.4.187) = agregado de
    `agent.turnos_rules.agregar_vendedor` das reuniões recentes — quando
    tem dado, Talk Ratio e Question Quality saem do gap; o resto continua
    gap explícito (ver docstring do módulo)."""
    resultado = {
        "seller_id": seller_id,
        **{campo: dict(SELLER_COACHING_GAPS[campo]) for campo in SELLER_COACHING_CAMPOS},
    }
    c = conversa or {}
    if c.get("seller_talk_ratio") is not None:
        resultado["talk_ratio"] = {
            "disponivel": True,
            "seller_talk_ratio": c["seller_talk_ratio"],
            "tempo_vendedor_s": c.get("tempo_vendedor_s"),
            "tempo_cliente_s": c.get("tempo_cliente_s"),
            "monologues": c.get("monologues"),
            "reunioes": c.get("reunioes"),
            "dias": c.get("dias"),
            "papeis_inferidos": bool(c.get("papeis_inferidos")),
        }
    if c.get("questions_total"):
        resultado["question_quality"] = {
            "disponivel": True,
            "questions_total": c["questions_total"],
            "open_questions": c.get("open_questions"),
            "closed_questions": c.get("closed_questions"),
            "open_question_rate": c.get("open_question_rate"),
            "reunioes": c.get("reunioes"),
            "dias": c.get("dias"),
        }
    return resultado
