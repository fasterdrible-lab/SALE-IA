"""
SALEIA — agent/question_gap_rules.py

Question Gap Engine (FASE 3 / TAREFA 3.2 do "PROMPT MESTRE — SALE-IA
V2"). Função pura, nenhuma chamada de IA, nenhum acesso a banco — mesmo
padrão de agent/spin_coverage_rules.py (Tarefa 3.1), sobre o qual esta
tarefa constrói diretamente.

Objetivo do prompt mestre: "descobrir qual pergunta ainda precisa ser
feita" — a partir da cobertura SPIN já calculada (known[]/missing[] por
estágio, Tarefa 3.1), prioriza todos os gaps (critical/high/medium/low)
e recomenda, para cada um, a pergunta relacionada ao campo faltante
(reaproveita `SPIN_PERGUNTAS_PADRAO`, nunca inventa uma pergunta nova
desconectada do gap).
"""

from typing import Optional

from agent.spin_coverage_rules import SPIN_PERGUNTAS_PADRAO, SPIN_STAGES

# Ordem de prioridade — do mais urgente pro menos urgente.
PRIORIDADE_ORDEM = ("critical", "high", "medium", "low")

# Prioridade padrão por estágio SPIN — Implication expõe o custo/urgência
# do problema (o gap mais crítico de não perguntar) e Need Payoff sustenta
# o valor da solução (alta prioridade); Situation/Problem são fundação,
# menos urgentes quando já se avançou na conversa. Sobrescrevível por
# chamada (`prioridade_por_stage`) — não é vocabulário fechado do domínio,
# mesmo padrão de `checklist` em `spin_coverage_rules.calcular_cobertura_spin`.
STAGE_PRIORIDADE_PADRAO = {
    "situation": "low",
    "problem": "medium",
    "implication": "critical",
    "need_payoff": "high",
}


def _validar_prioridade_por_stage(prioridade_por_stage: dict) -> None:
    for stage, prioridade in prioridade_por_stage.items():
        if stage not in SPIN_STAGES:
            raise ValueError(f"stage inválido em prioridade_por_stage: {stage!r} (esperado um de {SPIN_STAGES})")
        if prioridade not in PRIORIDADE_ORDEM:
            raise ValueError(f"prioridade inválida para {stage!r}: {prioridade!r} (esperado um de {PRIORIDADE_ORDEM})")


def calcular_gaps_priorizados(cobertura: dict, prioridade_por_stage: Optional[dict] = None) -> list:
    """A partir da cobertura SPIN (`spin_coverage_rules.calcular_cobertura_
    spin`), retorna a lista de gaps (campos `missing`) com prioridade e
    pergunta recomendada — `[{"stage", "campo", "priority", "pergunta"}]`.

    Ordenada por prioridade (critical > high > medium > low); dentro da
    mesma prioridade, mantém a ordem SPIN (situation → need_payoff) e,
    dentro do mesmo estágio, a ordem em que os campos aparecem em
    `missing`."""
    prioridade_por_stage = prioridade_por_stage or STAGE_PRIORIDADE_PADRAO
    _validar_prioridade_por_stage(prioridade_por_stage)

    gaps = []
    for stage in SPIN_STAGES:
        missing = cobertura.get(stage, {}).get("missing", [])
        prioridade = prioridade_por_stage.get(stage, "low")
        for campo in missing:
            pergunta = SPIN_PERGUNTAS_PADRAO.get(campo, f"Pode me contar mais sobre {campo}?")
            gaps.append({"stage": stage, "campo": campo, "priority": prioridade, "pergunta": pergunta})

    ordem_prioridade = {prioridade: indice for indice, prioridade in enumerate(PRIORIDADE_ORDEM)}
    gaps.sort(key=lambda gap: ordem_prioridade[gap["priority"]])
    return gaps


def proximo_gap(gaps_priorizados: list) -> Optional[dict]:
    """Primeiro gap da lista já priorizada (ou `None` se não houver
    nenhum) — é a resposta direta a "qual pergunta ainda precisa ser
    feita" que o prompt mestre pede: o gap de maior prioridade, e dentro
    dela o que aparece primeiro na ordem SPIN."""
    return gaps_priorizados[0] if gaps_priorizados else None
