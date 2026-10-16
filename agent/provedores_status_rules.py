"""Painel de provedores de IA + avisos de saldo e de reserva (V.1.4.183).

Pedido do usuário (16/10/2026): ver no Dashboard o estado de cada API de
IA — saldo do DeepSeek, quanto resta do limite do Groq, qual provedor está
atendendo — e ser avisado no Telegram ANTES de a IA cair (em 14/10 o
DeepSeek zerou e só se soube pela queda). Em 16/10 o DeepSeek rodava com
US$ 7,48 de crédito de compensação e saldo pago de -US$ 0,01.

O que cada provedor deixa saber:
- DeepSeek: `GET /user/balance` (saldo pago + crédito concedido).
- Groq: cabeçalhos `x-ratelimit-*` em cada resposta (limite diário de
  pedidos e de tokens por minuto). Sem chamada recente, sem número.
- OpenAI, Anthropic, Gemini: nenhuma consulta de saldo pela chave de API —
  só o resultado da última chamada.

Funções puras — zero rede, zero banco, zero Telegram.
"""
from __future__ import annotations

SALDO_DEEPSEEK_ALERTA_PADRAO_USD = 2.0


def ler_saldo_deepseek(resposta: dict | None) -> dict | None:
    """Resposta de `/user/balance`:
    `{"is_available": bool, "balance_infos": [{"currency": "USD",
    "total_balance": "7.47", "granted_balance": "7.48",
    "topped_up_balance": "-0.01"}]}`. Prefere USD."""
    if not isinstance(resposta, dict):
        return None
    infos = resposta.get("balance_infos") or []
    if not isinstance(infos, list) or not infos:
        return None
    info = next((i for i in infos if str(i.get("currency", "")).upper() == "USD"), infos[0])

    def _num(campo):
        try:
            return round(float(info.get(campo)), 2)
        except (TypeError, ValueError):
            return None

    return {
        "disponivel": bool(resposta.get("is_available")),
        "moeda": str(info.get("currency") or ""),
        "total": _num("total_balance"),
        "credito_concedido": _num("granted_balance"),
        "pago": _num("topped_up_balance"),
    }


def saldo_baixo(saldo: dict | None, limite_usd: float) -> bool:
    if not saldo or saldo.get("total") is None:
        return False
    return saldo["total"] < limite_usd or not saldo.get("disponivel", True)


def ler_limites_groq(cabecalhos: dict | None) -> dict | None:
    """Cabeçalhos `x-ratelimit-*` da resposta do Groq (nomes em minúsculas).
    requests = por dia (RPD); tokens = por minuto (TPM)."""
    if not cabecalhos:
        return None
    h = {str(k).lower(): v for k, v in cabecalhos.items()}

    def _int(nome):
        try:
            return int(float(h.get(nome)))
        except (TypeError, ValueError):
            return None

    limites = {
        "pedidos_limite_dia": _int("x-ratelimit-limit-requests"),
        "pedidos_restantes_dia": _int("x-ratelimit-remaining-requests"),
        "tokens_limite_min": _int("x-ratelimit-limit-tokens"),
        "tokens_restantes_min": _int("x-ratelimit-remaining-tokens"),
        "pedidos_zeram_em": h.get("x-ratelimit-reset-requests") or None,
    }
    return limites if any(v is not None for v in limites.values()) else None


def provedor_em_uso(ultimos_sucessos: list[tuple[str, str]], ordem: list[str]) -> dict:
    """`ultimos_sucessos`: [(provider, iso)] do mais recente para o mais
    antigo (últimos minutos). Reserva = não é o 1º da ordem."""
    if not ultimos_sucessos:
        return {"provedor": None, "reserva": False, "desde": None}
    provedor, quando = ultimos_sucessos[0]
    principal = ordem[0] if ordem else None
    return {"provedor": provedor, "reserva": bool(principal and provedor != principal), "desde": quando}


def montar_alerta_saldo_baixo(saldo: dict, limite_usd: float) -> str:
    partes = [f"Saldo total: *US$ {saldo.get('total'):.2f}* (abaixo de US$ {limite_usd:.2f})"]
    if saldo.get("credito_concedido"):
        partes.append(f"Crédito concedido: US$ {saldo['credito_concedido']:.2f} · pago: US$ {saldo.get('pago') or 0:.2f}")
    return (
        "💰 *DeepSeek com saldo baixo*\n" + "\n".join(partes) +
        "\nQuando acabar, a IA cai para os provedores de reserva. Recarregar em platform.deepseek.com → Top up."
    )


def montar_alerta_reserva(provedor_reserva: str, causas_anteriores: dict[str, str]) -> str:
    falhas = ", ".join(f"{nome}: {causa.replace('_', ' ')}" for nome, causa in causas_anteriores.items()) or "indisponível"
    return (
        f"🔁 *IA usando reserva: {provedor_reserva}*\n"
        f"Os anteriores na ordem falharam ({falhas}). As reuniões seguem com análise, "
        "mas a reserva pode ter limite ou custo diferente."
    )
