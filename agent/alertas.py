"""
Módulo de alertas SALEIA.
Envia notificações Telegram quando eventos críticos ocorrem no backend.

Variáveis necessárias no .env:
  TELEGRAM_TOKEN   — token do bot (obtido via @BotFather)
  TELEGRAM_CHAT_ID — ID do chat ou grupo que recebe os alertas
"""
import logging
import os
import time

logger = logging.getLogger("saleia.alertas")

# Cooldown por tipo de alerta — evita spam (1h entre alertas do mesmo tipo)
_last_alerta: dict[str, float] = {}
_COOLDOWN_S = 3600


def alertar(mensagem: str, nivel: str = "⚠️") -> None:
    """Envia alerta Telegram de forma síncrona e silenciosa em caso de falha."""
    token   = os.getenv("TELEGRAM_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        import httpx
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": f"{nivel} *SALEIA*\n{mensagem}",
                "parse_mode": "Markdown",
            },
            timeout=5,
        )
    except Exception as exc:
        logger.warning("Falha ao enviar alerta Telegram: %s", exc)


def _pode_alertar(chave: str) -> bool:
    """True se o cooldown do tipo de alerta já expirou."""
    agora = time.time()
    if agora - _last_alerta.get(chave, 0) >= _COOLDOWN_S:
        _last_alerta[chave] = agora
        return True
    return False


def verificar_thresholds(metricas_ia: dict, banco: dict) -> None:
    """
    Verifica thresholds e envia alertas Telegram se excedidos.
    Chamado a cada snapshot (~60s). Cada tipo de alerta tem cooldown de 1h.

    Thresholds:
      - Banco offline (erro não nulo)
      - Banco lento (latência > 1500 ms)
      - Taxa de erro IA > 30 % (mínimo 10 chamadas desde o restart)
      - Fallback rate alto > 50 % das chamadas com sucesso
    """
    # ── Banco offline ──────────────────────────────────────────
    banco_erro = banco.get("erro")
    if banco_erro and _pode_alertar("banco_offline"):
        alertar(
            f"🗄️ Banco offline\nErro: `{str(banco_erro)[:200]}`",
            nivel="🔴",
        )

    # ── Banco lento ────────────────────────────────────────────
    lat = banco.get("latencia_ms") or 0
    if lat > 1500 and not banco_erro and _pode_alertar("banco_lento"):
        alertar(
            f"🗄️ Banco lento: *{lat} ms* de latência (threshold: 1500 ms)",
            nivel="⚠️",
        )

    # ── Taxa de erro IA alta ───────────────────────────────────
    total = metricas_ia.get("chamadas_total") or 0
    falha = metricas_ia.get("chamadas_falha") or 0
    if total >= 10 and falha / total > 0.30 and _pode_alertar("erro_ia_alto"):
        taxa = round(falha / total * 100)
        alertar(
            f"🤖 Taxa de erro IA alta: *{taxa}%* ({falha}/{total} chamadas falharam desde o restart)",
            nivel="🔴",
        )

    # ── Fallback rate alto ─────────────────────────────────────
    fallbacks = metricas_ia.get("fallbacks") or 0
    sucesso   = metricas_ia.get("chamadas_sucesso") or 0
    if sucesso >= 10 and fallbacks / sucesso > 0.50 and _pode_alertar("fallback_alto"):
        taxa = round(fallbacks / sucesso * 100)
        alertar(
            f"🔄 Fallback rate alto: *{taxa}%* das chamadas usaram provedor backup",
            nivel="⚠️",
        )
