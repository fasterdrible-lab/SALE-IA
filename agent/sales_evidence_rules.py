"""
SALEIA — agent/sales_evidence_rules.py

Validação pura do SalesEvidence (FASE 1 / TAREFA 1.2 do "PROMPT MESTRE —
SALE-IA V2"). Nenhuma chamada de IA, nenhum acesso a banco — mesmo padrão
de agent/sales_event_rules.py (Tarefa 1.1).

O objetivo da Tarefa 1.2 é separar interpretação de evidência: nunca
salvar só "cliente está inseguro" (interpretação solta) — sempre
"type=ADOPTION_RISK" + "quote='Tenho medo da minha equipe não usar'"
(hipótese apontando para a fala real que a sustenta). Essa regra é
imposta aqui tornando `quote` obrigatória e não-vazia — uma hipótese
sem evidência (`quote` ausente/em branco) nunca é um SalesEvidence
válido, e `api/database.py::criar_sales_evidence()` propaga o
ValueError em vez de descartar silenciosamente.
"""


def validar_sales_evidence(dados: dict) -> None:
    """Valida os campos de um SalesEvidence antes de persistir.

    Levanta ValueError com mensagem clara na primeira regra violada; não
    retorna nada em caso de sucesso (mesma convenção de
    agent/sales_event_rules.py::validar_sales_event)."""
    tipo = dados.get("type")
    if not (tipo or "").strip():
        raise ValueError("type (hipótese/interpretação) é obrigatório e não pode ser vazio")

    quote = dados.get("quote")
    if not (quote or "").strip():
        raise ValueError(
            f"quote (evidência) é obrigatória — hipótese {tipo!r} não pode existir sem a fala que a sustenta"
        )

    confidence = dados.get("confidence")
    try:
        confidence_valor = float(confidence)
    except (TypeError, ValueError):
        raise ValueError(f"confidence inválida: {confidence!r} (esperado float entre 0 e 1)")
    if not (0.0 <= confidence_valor <= 1.0):
        raise ValueError(f"confidence fora do intervalo [0, 1]: {confidence_valor!r}")
