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
        "Talk Ratio exige turnos com speaker/start/end (agent/"
        "conversation_metrics_rules.py, Fase 11.1) — nada no sistema "
        "captura transcrição estruturada por turno hoje."
    ),
}

QUESTION_QUALITY_NAO_DISPONIVEL = {
    "disponivel": False,
    "motivo": (
        "Question Quality (perguntas abertas/fechadas do vendedor) usa o "
        "mesmo motor e a mesma exigência de turnos estruturados de Talk "
        "Ratio — sem captura por turno, não há dado."
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
        "Next Step Discipline usa o mesmo motor e a mesma exigência de "
        "turnos estruturados de Talk Ratio (agent/conversation_metrics_"
        "rules.py) — sem captura por turno, não há dado."
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


def montar_seller_coaching(seller_id: str) -> dict:
    """Monta o payload de Seller Coaching pra um vendedor. Nunca acessa
    banco ou chama IA — hoje é puramente a documentação dos 8 gaps, já
    que nenhuma engine de origem tem dado real pra alimentar (ver
    docstring do módulo). `seller_id` é ecoado no payload por
    consistência com os outros 2 blocos da Fase 22, não usado em nenhum
    cálculo ainda."""
    return {
        "seller_id": seller_id,
        **{campo: dict(SELLER_COACHING_GAPS[campo]) for campo in SELLER_COACHING_CAMPOS},
    }
