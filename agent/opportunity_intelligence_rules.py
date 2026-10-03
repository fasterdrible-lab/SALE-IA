"""Fase 22 (Frontend) / bloco "Opportunity Intelligence" do "PROMPT MESTRE —
SALE-IA V2". Função pura — zero IA/banco — que monta o payload dos 12 campos
literais (Opportunity Health, SPIN Coverage, MEDDPICC, Pain, Impact, Champion,
Economic Buyer, Decision Process, Objections, Competitors, Risks, Next Steps)
a partir de dados já persistidos (Opportunity + OpportunityMemory, Fase 2).

9 campos são pass-through direto de categorias já existentes em
`OpportunityMemory` (dado real, nunca inventado). SPIN Coverage, MEDDPICC e
os riscos *calculados* (`deal_risk_rules.calcular_riscos`) ficam como gap
explícito: nenhuma função do sistema traduz hoje um insight genérico de
`OpportunityMemory` para o formato de fato que essas engines exigem (SPIN
precisa de `stage`/`campo` no vocabulário situation/problem/implication/
need_payoff; MEDDPICC precisa de `status` UNKNOWN/PARTIAL/CONFIRMED por
item; `calcular_riscos()` precisa de sinais — próximo passo, objeções de
preço, concorrente em vantagem, dias parado — que não são calculados em
nenhum lugar do sistema ainda). Mesma disciplina de honestidade já usada em
`observability_metrics_rules.py` (Fase 19) e `quality_monitoring_rules.py`
(Fase 19.1): documentar o gap, nunca fabricar número.
"""

SPIN_COVERAGE_NAO_DISPONIVEL = {
    "disponivel": False,
    "motivo": (
        "SPIN Coverage exige fatos classificados por estágio "
        "(situation/problem/implication/need_payoff) com evidence_quote — "
        "OpportunityMemory guarda insights por categoria de negócio "
        "(pain_points/champion/etc.), não por estágio SPIN. Nenhuma função "
        "traduz um formato para o outro ainda."
    ),
}

MEDDPICC_NAO_DISPONIVEL = {
    "disponivel": False,
    "motivo": (
        "MEDDPICC exige status (UNKNOWN/PARTIAL/CONFIRMED) por item — "
        "OpportunityMemory só guarda a presença de um insight, sem essa "
        "classificação de status. Nenhuma função traduz um formato para o "
        "outro ainda."
    ),
}

RISCOS_CALCULADOS_NAO_DISPONIVEL = {
    "disponivel": False,
    "motivo": (
        "calcular_riscos() (agent/deal_risk_rules.py) exige sinais — "
        "próximo passo definido, contagem de objeções de preço, concorrente "
        "em vantagem, dias desde a última atividade — que não são "
        "calculados em nenhum lugar do sistema ainda."
    ),
}


def montar_opportunity_intelligence(
    opportunity: dict,
    opportunity_memory: dict,
    reunioes: list | None = None,
) -> dict:
    """Monta o payload de Opportunity Intelligence a partir de uma
    `Opportunity` e sua `OpportunityMemory` já buscadas no banco (ambas no
    formato de dict retornado por `api/database.py`). Nunca acessa banco ou
    chama IA — puramente transformação de dado já existente.

    Tarefa A6: com `reunioes` (as reuniões vinculadas, formato de
    `listar_meetings_da_opportunity()`), `risks_calculados` passa a ser
    real (`agent/deal_risk_signals_rules.py`); sem elas, continua o gap
    explícito de antes."""
    if reunioes is not None:
        from agent.deal_risk_signals_rules import montar_riscos_calculados
        riscos_calculados = montar_riscos_calculados(opportunity, opportunity_memory, reunioes)
    else:
        riscos_calculados = dict(RISCOS_CALCULADOS_NAO_DISPONIVEL)
    return {
        "opportunity_health": {
            "stage": opportunity.get("stage") or None,
            "status": opportunity.get("status"),
            "estimated_value": opportunity.get("estimated_value"),
            "outcome_value": opportunity.get("outcome_value"),
            "cycle_days": opportunity.get("cycle_days"),
        },
        "spin_coverage": dict(SPIN_COVERAGE_NAO_DISPONIVEL),
        "meddpicc": dict(MEDDPICC_NAO_DISPONIVEL),
        "pain": opportunity_memory.get("pain_points", []),
        "impact": opportunity_memory.get("business_impact", []),
        "champion": opportunity_memory.get("champion", []),
        "economic_buyer": opportunity_memory.get("economic_buyer", []),
        "decision_process": opportunity_memory.get("decision_process", []),
        "objections": opportunity_memory.get("objections", []),
        "competitors": opportunity_memory.get("competitors", []),
        "risks_relatados": opportunity_memory.get("risks", []),
        "risks_calculados": riscos_calculados,
        "next_steps": opportunity_memory.get("next_steps", []),
    }
