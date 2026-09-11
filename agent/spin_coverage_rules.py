"""
SALEIA — agent/spin_coverage_rules.py

SPIN Coverage Engine (FASE 3 / TAREFA 3.1 do "PROMPT MESTRE — SALE-IA
V2"). Função pura, nenhuma chamada de IA, nenhum acesso a banco — mesmo
padrão de agent/sales_event_rules.py e agent/opportunity_memory_rules.py.

Escopo desta tarefa: o motor de cobertura em si — computa known[]/
missing[] por estágio SPIN a partir de fatos JÁ estruturados e
evidenciados (ex.: SalesEvent/OpportunityMemory das Fases 1-2). Extração
automática de fatos a partir de transcrição livre via IA (interpretar
"nosso follow-up é lento" e classificar como `problem.main_pain`) NÃO
está no enunciado da Tarefa 3.1 ("criar cobertura real" a partir de
fatos) e fica para uma tarefa futura.

Regra explícita do prompt mestre — "Não permitir que a IA invente
informação faltante": aqui não há IA nenhuma nesta camada, mas a mesma
disciplina de evidência das Fases 1-2 é mantida — `calcular_cobertura_
spin()` recusa (`ValueError`) qualquer fato sem `evidence_quote`, então
nenhum "known" pode existir sem lastro real na conversa, mesmo quando
uma camada de extração por IA for construída depois.
"""

from typing import Optional

# Ordem SPIN — usada tanto para achar o "estágio atual" (primeiro com
# pendência) quanto para priorizar a próxima pergunta sugerida.
SPIN_STAGES = ("situation", "problem", "implication", "need_payoff")

# Checklist padrão por estágio — vocabulário mínimo inferido do exemplo
# literal do prompt mestre (equipe/CRM em Situation, a dor em Problem,
# custo financeiro/impacto em conversão em Implication, valor da solução
# em Need Payoff). Pode ser sobrescrito por chamada (ver `checklist` em
# `calcular_cobertura_spin`) — não é um vocabulário fechado do domínio,
# só o default sensato quando o chamador não fornece um mais específico
# pra aquela oportunidade.
SPIN_CHECKLIST_PADRAO = {
    "situation": ["team_size", "crm_tool"],
    "problem": ["main_pain"],
    "implication": ["financial_impact", "conversion_impact"],
    "need_payoff": ["solution_value"],
}

# Perguntas canônicas por campo — usadas por `sugerir_proxima_pergunta()`.
# Campos fora deste dict caem no fallback genérico (ver função).
SPIN_PERGUNTAS_PADRAO = {
    "team_size": "Quantas pessoas fazem parte da equipe hoje?",
    "crm_tool": "Qual ferramenta vocês usam hoje pra isso?",
    "main_pain": "Qual é o principal problema que vocês enfrentam hoje?",
    "financial_impact": "Quanto esse problema custa atualmente?",
    "conversion_impact": "Como isso afeta a conversão de vocês?",
    "solution_value": "O que resolver isso valeria pra vocês?",
}


def _validar_fato(fato: dict) -> None:
    stage = fato.get("stage")
    if stage not in SPIN_STAGES:
        raise ValueError(f"stage inválido: {stage!r} (esperado um de {SPIN_STAGES})")
    if not (fato.get("campo") or "").strip():
        raise ValueError("campo é obrigatório e não pode ser vazio")
    if not (fato.get("evidence_quote") or "").strip():
        raise ValueError(
            f"evidence_quote obrigatória — fato {fato.get('campo')!r} não pode ser "
            "considerado 'known' sem a fala que o sustenta (regra: a IA nunca pode "
            "inventar informação faltante)"
        )


def calcular_cobertura_spin(fatos_conhecidos: list, checklist: Optional[dict] = None) -> dict:
    """Computa known[]/missing[] por estágio SPIN.

    `fatos_conhecidos`: lista de {"stage", "campo", "valor",
    "evidence_quote"} — cada um validado (`ValueError` propaga na
    primeira violação, nenhum fato entra parcialmente). Fatos com
    `campo` fora do checklist ainda contam como `known` (cobertura
    real, só não reduzem `missing` além do checklist)."""
    checklist = checklist or SPIN_CHECKLIST_PADRAO

    for fato in fatos_conhecidos:
        _validar_fato(fato)

    cobertura = {}
    for stage in SPIN_STAGES:
        known_do_estagio = [f for f in fatos_conhecidos if f["stage"] == stage]
        campos_conhecidos = {f["campo"] for f in known_do_estagio}
        esperado = checklist.get(stage, [])
        missing_do_estagio = [campo for campo in esperado if campo not in campos_conhecidos]
        cobertura[stage] = {"known": known_do_estagio, "missing": missing_do_estagio}

    return cobertura


def estagio_atual(cobertura: dict) -> str:
    """Primeiro estágio SPIN (em ordem) que ainda tem pendência; se
    todos estiverem cobertos, retorna o último estágio (need_payoff) —
    a conversa "está" no estágio mais avançado já alcançado."""
    for stage in SPIN_STAGES:
        if cobertura.get(stage, {}).get("missing"):
            return stage
    return SPIN_STAGES[-1]


def sugerir_proxima_pergunta(cobertura: dict) -> Optional[dict]:
    """Retorna {"stage", "campo", "pergunta"} pro primeiro campo faltante
    (em ordem SPIN), ou None se a cobertura estiver completa."""
    for stage in SPIN_STAGES:
        missing = cobertura.get(stage, {}).get("missing", [])
        if missing:
            campo = missing[0]
            pergunta = SPIN_PERGUNTAS_PADRAO.get(campo, f"Pode me contar mais sobre {campo}?")
            return {"stage": stage, "campo": campo, "pergunta": pergunta}
    return None
