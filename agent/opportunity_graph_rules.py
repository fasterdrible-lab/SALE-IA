"""
SALEIA — agent/opportunity_graph_rules.py

Validação pura do Opportunity Graph (FASE 2 / TAREFA 2.2 do "PROMPT
MESTRE — SALE-IA V2"). Nenhuma chamada de IA, nenhum acesso a banco —
mesmo padrão de agent/opportunity_memory_rules.py (Tarefa 2.1).

Os nós do grafo (`CLIENT` + as 8 categorias qualitativas do prompt
mestre) e a regra "cada relação deve conter source/evidence/confidence/
timestamp, sem perder a origem" — imposta aqui tornando `evidence`
obrigatória, mesma disciplina de `agent/sales_evidence_rules.py`
(Tarefa 1.2): uma relação sem a evidência que a sustenta nunca é uma
aresta válida.
"""

NODE_TYPES = frozenset({
    "CLIENT",
    "PAIN",
    "IMPACT",
    "GOAL",
    "OBJECTION",
    "STAKEHOLDER",
    "COMPETITOR",
    "DECISION",
    "NEXT_STEP",
})


def validar_aresta(dados: dict) -> None:
    """Valida os campos de uma aresta do Opportunity Graph antes de
    persistir. Levanta ValueError com mensagem clara na primeira regra
    violada; não retorna nada em caso de sucesso."""
    from_type = dados.get("from_type")
    if from_type not in NODE_TYPES:
        raise ValueError(f"from_type inválido: {from_type!r} (esperado um de {sorted(NODE_TYPES)})")

    to_type = dados.get("to_type")
    if to_type not in NODE_TYPES:
        raise ValueError(f"to_type inválido: {to_type!r} (esperado um de {sorted(NODE_TYPES)})")

    if not str(dados.get("from_id") or "").strip():
        raise ValueError("from_id é obrigatório e não pode ser vazio")
    if not str(dados.get("to_id") or "").strip():
        raise ValueError("to_id é obrigatório e não pode ser vazio")

    if not (dados.get("relation") or "").strip():
        raise ValueError("relation é obrigatória e não pode ser vazia")

    if not (dados.get("evidence") or "").strip():
        raise ValueError("evidence é obrigatória — uma relação não pode existir sem a origem que a sustenta")

    confidence = dados.get("confidence")
    try:
        confidence_valor = float(confidence)
    except (TypeError, ValueError):
        raise ValueError(f"confidence inválida: {confidence!r} (esperado float entre 0 e 1)")
    if not (0.0 <= confidence_valor <= 1.0):
        raise ValueError(f"confidence fora do intervalo [0, 1]: {confidence_valor!r}")
