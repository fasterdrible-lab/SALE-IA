"""
SALEIA — agent/propensao_rules.py

Classificação determinística de Propensão de Compra a partir do score_compra
numérico já calculado pelo closer_agent. Único lugar com os limiares —
usado no tempo real para não gerar mais uma chamada de IA por fragmento
(o score interno continua existindo, só não é mais exibido ao usuário).
"""

LIMIAR_ALTA = 70
LIMIAR_MEDIA = 45


def classificar_propensao(score_valor) -> str:
    """Retorna 'alta' | 'media' | 'baixa' | 'nao_determinada' a partir do
    score_compra.valor (0-100). None/ausente => 'nao_determinada'."""
    if score_valor is None:
        return "nao_determinada"
    try:
        valor = float(score_valor)
    except (TypeError, ValueError):
        return "nao_determinada"
    if valor >= LIMIAR_ALTA:
        return "alta"
    if valor >= LIMIAR_MEDIA:
        return "media"
    return "baixa"
