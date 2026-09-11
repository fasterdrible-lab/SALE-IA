"""
SALEIA — agent/buyer_motivation_rules.py

Buyer Motivation Engine (FASE 5 / TAREFA 5.1 do "PROMPT MESTRE —
SALE-IA V2"). Função pura, nenhuma chamada de IA, nenhum acesso a
banco — mesmo padrão de agent/meddpicc_rules.py/spin_coverage_rules.py:
computa/valida a partir de hipóteses JÁ estruturadas e evidenciadas,
nunca extrai a partir de transcrição livre (fora do enunciado da
Tarefa 5.1).

Regra explícita do prompt mestre — "DISC nunca deverá ser tratado como
motivação": garantida por construção, não só por convenção de código —
este módulo não importa nem lê nenhum campo relacionado a DISC (ver
`tests/test_buyer_motivation_rules.py::GuardaArquiteturalTest`, mesmo
padrão de `agent/signo_solar_rules.py` pra astrologia vs. DISC/Big
Five).

Escopo desta tarefa: só o motor de motivação (taxonomia + validação +
leitura da motivação predominante). Tarefa 5.2 (Behavioral Signal
Engine) NÃO começou.
"""

from typing import Optional

# Os 12 motivadores possíveis (TAREFA 5.1), taxonomia controlada — não é
# texto livre, uma hipótese só é válida se `motivation` for um destes.
MOTIVATION_TIPOS = frozenset({
    "GROWTH",
    "SECURITY",
    "CONTROL",
    "STATUS",
    "CONVENIENCE",
    "SPEED",
    "COST_REDUCTION",
    "REVENUE_GAIN",
    "RISK_REDUCTION",
    "PRODUCTIVITY",
    "RECOGNITION",
    "SIMPLICITY",
})


def _validar_hipotese(hipotese: dict) -> None:
    motivation = hipotese.get("motivation")
    if motivation not in MOTIVATION_TIPOS:
        raise ValueError(f"motivation inválida: {motivation!r} (esperado um de {sorted(MOTIVATION_TIPOS)})")

    confidence = hipotese.get("confidence")
    try:
        confidence_valor = float(confidence)
    except (TypeError, ValueError):
        raise ValueError(f"confidence inválida: {confidence!r} (esperado float entre 0 e 1)")
    if not (0.0 <= confidence_valor <= 1.0):
        raise ValueError(f"confidence fora do intervalo [0, 1]: {confidence_valor!r}")

    evidence = hipotese.get("evidence")
    if not isinstance(evidence, list) or not evidence or not any((quote or "").strip() for quote in evidence):
        raise ValueError(
            f"evidence[] obrigatória e não pode ser vazia para motivation={motivation!r} "
            "(hipótese de motivação sem evidência não pode existir)"
        )


def validar_hipoteses_motivacao(hipoteses: list) -> None:
    """Valida uma lista de hipóteses de motivação (`{"motivation",
    "confidence", "evidence"}` cada) — `ValueError` propaga na primeira
    violação, nenhuma hipótese entra parcialmente."""
    for hipotese in hipoteses:
        _validar_hipotese(hipotese)


def motivacao_dominante(hipoteses: list) -> Optional[dict]:
    """Valida `hipoteses` e retorna a de maior `confidence` — leitura
    corrente da motivação predominante do comprador nesse ponto da
    conversa, ou `None` se a lista estiver vazia. Empate: mantém a
    ordem de chegada (a primeira das maiores `confidence` vence)."""
    validar_hipoteses_motivacao(hipoteses)
    if not hipoteses:
        return None
    melhor = hipoteses[0]
    for hipotese in hipoteses[1:]:
        if hipotese["confidence"] > melhor["confidence"]:
            melhor = hipotese
    return melhor
