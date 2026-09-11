"""
SALEIA — agent/objection_rules.py

Taxonomia de Objeções (FASE 6 / TAREFA 6.1 do "PROMPT MESTRE — SALE-IA
V2"). Função pura, nenhuma chamada de IA, nenhum acesso a banco — mesmo
padrão de agent/behavioral_signal_rules.py (Fase 5).

Objetivo central do prompt mestre: separar o que o cliente literalmente
FALOU (`objection_spoken`, taxonomia fechada de 13 categorias) da
HIPÓTESE de causa raiz (`root_cause_hypothesis`, vocabulário mais livre
— o exemplo do prompt mestre usa `ADOPTION_RISK`, que nem está nas 13
categorias de `objection_spoken`) — os dois nunca podem ser fundidos
automaticamente.

Regra de teste explícita do prompt mestre: o caso "Está caro." NÃO pode
resultar automaticamente em `root_cause = PRICE, confidence 100%` — o
sistema deve primeiro recomendar investigação. Este módulo não faz
nenhuma inferência (mesma disciplina das Fases 1-5: schema/regra
primeiro, extração via IA é tarefa futura) — a garantia é estrutural:
`precisa_investigar()` sinaliza exatamente o padrão proibido (hipótese
que só repete a categoria falada, com a mesma evidência, sem
investigação real por trás).
"""

from typing import Optional

# As 13 categorias de objeção literalmente faladas pelo cliente
# (TAREFA 6.1) — vocabulário fechado, `objection_spoken` só aceita um
# destes.
OBJECTION_TIPOS = frozenset({
    "PRICE",
    "VALUE",
    "BUDGET",
    "TIMING",
    "TRUST",
    "ADOPTION",
    "COMPETITOR",
    "AUTHORITY",
    "PRIORITY",
    "IMPLEMENTATION",
    "LEGAL",
    "PROCUREMENT",
    "SECURITY",
})

# Confidence mínima para uma hipótese de causa raiz ser considerada
# "investigada o suficiente" — abaixo disso, `precisa_investigar()`
# sempre retorna True. Decisão desta rodada (o prompt mestre não define
# o número exato, só a regra "não pode ser 100% automático").
LIMIAR_CONFIANCA_MINIMA_ROOT_CAUSE = 0.7


def _validar_objection_spoken(spoken: dict) -> None:
    categoria = spoken.get("category")
    if categoria not in OBJECTION_TIPOS:
        raise ValueError(f"category de objection_spoken inválida: {categoria!r} (esperado um de {sorted(OBJECTION_TIPOS)})")
    if not (spoken.get("evidence_quote") or "").strip():
        raise ValueError("evidence_quote obrigatória em objection_spoken — nenhuma objeção pode existir sem a fala real")


def _validar_root_cause_hypothesis(hipotese: dict) -> None:
    if not (hipotese.get("hypothesis") or "").strip():
        raise ValueError("hypothesis obrigatória em root_cause_hypothesis (vocabulário livre, ex.: 'ADOPTION_RISK')")

    confidence = hipotese.get("confidence")
    try:
        confidence_valor = float(confidence)
    except (TypeError, ValueError):
        raise ValueError(f"confidence inválida: {confidence!r} (esperado float entre 0 e 1)")
    if not (0.0 <= confidence_valor <= 1.0):
        raise ValueError(f"confidence fora do intervalo [0, 1]: {confidence_valor!r}")

    if not (hipotese.get("evidence_quote") or "").strip():
        raise ValueError("evidence_quote obrigatória em root_cause_hypothesis")


def precisa_investigar(objection_spoken: dict, root_cause_hypothesis: Optional[dict] = None) -> bool:
    """Regra central da Tarefa 6.1 — reproduz o exemplo literal do
    prompt mestre: "Está caro." não pode virar `root_cause = PRICE,
    confidence 100%` automaticamente; o sistema deve recomendar
    investigação primeiro.

    Retorna `True` (recomenda investigação) quando:
    - nenhuma hipótese de causa raiz foi levantada ainda (só o que foi
      falado, isso sozinho nunca é suficiente);
    - a hipótese tem `confidence` abaixo de `LIMIAR_CONFIANCA_MINIMA_
      ROOT_CAUSE`;
    - a hipótese apenas repete a categoria falada (`hypothesis ==
      objection_spoken["category"]`) usando a MESMA `evidence_quote` do
      spoken — sinal direto de que a causa raiz foi assumida por
      espelhamento, não investigada de verdade."""
    _validar_objection_spoken(objection_spoken)

    if root_cause_hypothesis is None:
        return True

    _validar_root_cause_hypothesis(root_cause_hypothesis)

    if root_cause_hypothesis["confidence"] < LIMIAR_CONFIANCA_MINIMA_ROOT_CAUSE:
        return True

    mesma_categoria = root_cause_hypothesis["hypothesis"] == objection_spoken["category"]
    mesma_evidencia = root_cause_hypothesis["evidence_quote"] == objection_spoken["evidence_quote"]
    if mesma_categoria and mesma_evidencia:
        return True

    return False


def registrar_objecao(objection_spoken: dict, root_cause_hypothesis: Optional[dict] = None) -> dict:
    """Valida e monta o registro completo de uma objeção — sempre com
    `objection_spoken` (o que foi dito) e `root_cause_hypothesis` (a
    hipótese de causa, opcional) como campos separados, nunca fundidos,
    mais `precisa_investigar` (ver `precisa_investigar()`)."""
    precisa = precisa_investigar(objection_spoken, root_cause_hypothesis)
    return {
        "objection_spoken": dict(objection_spoken),
        "root_cause_hypothesis": dict(root_cause_hypothesis) if root_cause_hypothesis else None,
        "precisa_investigar": precisa,
    }
