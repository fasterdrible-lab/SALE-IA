"""
Módulo de alertas SALEIA.
Envia notificações Telegram quando eventos críticos ocorrem no backend.

Variáveis necessárias no .env:
  TELEGRAM_TOKEN   — token do bot (obtido via @BotFather)
  TELEGRAM_CHAT_ID — ID do chat ou grupo que recebe os alertas
"""
import logging
import os
import threading
import time

logger = logging.getLogger("saleia.alertas")
# Logger dedicado a eventos financeiros (Cost Intelligence Fase 6) — filho
# de "saleia", herda o _JsonFormatter de api/main.py de graca.
logger_financeiro = logging.getLogger("saleia.financeiro")

# Cooldown por tipo de alerta — evita spam (1h entre alertas do mesmo tipo)
_last_alerta: dict[str, float] = {}
_COOLDOWN_S = 3600


def _enviar_telegram(token: str, chat_id: str, texto: str) -> bool:
    """Envio real (bloqueante). D13 (V.1.4.164):

    - **IPv4 forçado** (`local_address="0.0.0.0"`): da VPS, o IPv6 até
      api.telegram.org trava às vezes (1 em 5 tentativas sem conectar em
      20s, medido em 05/10), e o httpx prefere IPv6 — origem de ~3.400
      "read operation timed out" em 14 dias. IPv4: 0 falhas, ~0,1s.
    - **Resposta conferida**: antes, HTTP 400/401 do Telegram passava como
      sucesso. Agora vira warning com a `description` (nunca o token).
    - **Markdown inválido** (ex.: `_` solto em nome de feature) faz o
      Telegram recusar com 400 "can't parse entities": reenvia sem
      `parse_mode` em vez de perder o alerta.
    """
    import httpx

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with httpx.Client(
            transport=httpx.HTTPTransport(local_address="0.0.0.0", retries=1),
            timeout=10,
        ) as client:
            r = client.post(url, json={"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"})
            if r.status_code == 400 and "parse" in r.text.lower():
                r = client.post(url, json={"chat_id": chat_id, "text": texto})
            if r.status_code != 200:
                try:
                    descricao = r.json().get("description")
                except ValueError:
                    descricao = r.text[:200]
                logger.warning("Telegram recusou o alerta: HTTP %s %s", r.status_code, descricao)
                return False
            return True
    except Exception as exc:
        logger.warning("Falha ao enviar alerta Telegram: %s", exc)
        return False


def alertar(mensagem: str, nivel: str = "⚠️") -> None:
    """Envia alerta Telegram em segundo plano — nunca bloqueia quem chama
    (D13: o circuit breaker chamava isto de dentro do caminho de IA de uma
    reunião ao vivo, travando a requisição até o timeout). Silencioso em
    caso de falha (só loga)."""
    token   = os.getenv("TELEGRAM_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    threading.Thread(
        target=_enviar_telegram,
        args=(token, chat_id, f"{nivel} *SALEIA*\n{mensagem}"),
        name="saleia-alerta-telegram",
        daemon=True,
    ).start()


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


def verificar_orcamento(gasto_mes_usd: float, limite_usd: float | None) -> None:
    """Budget Guard (Cost Intelligence Fase 3): alerta quando o gasto de IA
    do mes corrente cruza 80% (aviso) ou 100%+ (critico) do orcamento
    configurado. Nao faz nada se limite_usd for None/<=0 (orcamento
    desativado — o admin nunca configurou um limite).

    Mesmo mecanismo de cooldown de verificar_thresholds — 1h entre
    alertas do mesmo tipo, para nao repetir a cada checagem do loop.
    """
    if not limite_usd or limite_usd <= 0:
        return

    pct = gasto_mes_usd / limite_usd * 100

    if pct >= 100 and _pode_alertar("orcamento_100"):
        alertar(
            f"💰 Orçamento de IA estourado: *US$ {gasto_mes_usd:.2f}* de "
            f"US$ {limite_usd:.2f} ({pct:.0f}%) já gastos este mês",
            nivel="🔴",
        )
        logger_financeiro.info(
            "Orcamento estourado: gasto=%.2f limite=%.2f pct=%.0f",
            gasto_mes_usd, limite_usd, pct,
        )
    elif pct >= 80 and _pode_alertar("orcamento_80"):
        alertar(
            f"💰 Orçamento de IA em *{pct:.0f}%*: US$ {gasto_mes_usd:.2f} "
            f"de US$ {limite_usd:.2f} gastos este mês",
            nivel="⚠️",
        )
        logger_financeiro.info(
            "Orcamento em aviso: gasto=%.2f limite=%.2f pct=%.0f",
            gasto_mes_usd, limite_usd, pct,
        )


def escalar_para_humano(escalonamento: dict) -> None:
    """Dispara o alerta Telegram real de 1 escalonamento — Fase 25
    (Critério para iniciar o Digital Sales Twin), item 5/5
    (`human escalation functional`). `escalonamento` vem de
    `agent/human_escalation_rules.py::montar_escalonamento()`.

    Diferente dos demais alertas deste módulo, **nunca tem cooldown**:
    um escalonamento real precisa notificar sempre, mesmo repetido —
    quem decide ignorar é o humano, nunca o sistema silenciosamente.
    """
    acao = escalonamento["acao"]
    fronteira = escalonamento["fronteira"]
    motivo = escalonamento["motivo"]
    nivel = escalonamento.get("urgencia", "⚠️")
    contexto = escalonamento.get("contexto") or {}

    linhas = [
        "🙋 Escalonamento humano necessário",
        f"Ação: *{acao}*",
        f"Fronteira: `{fronteira}`",
        f"Motivo: {motivo}",
    ]
    if contexto:
        detalhes = ", ".join(f"{k}={v}" for k, v in contexto.items())
        linhas.append(f"Contexto: {detalhes}")

    alertar("\n".join(linhas), nivel=nivel)
    logger.info(
        "Escalonamento humano: acao=%s fronteira=%s motivo=%s",
        acao, fronteira, motivo,
    )


def verificar_anomalia(feature: str, media_atual: float, media_anterior: float, multiplicador: float) -> None:
    """Alerta quando o custo medio por chamada de uma feature dispara em
    relacao a janela anterior (Cost Intelligence Fase 5). Cooldown de 1h
    por feature (mesmo mecanismo de _pode_alertar dos demais alertas)."""
    if not _pode_alertar(f"anomalia_{feature}"):
        return
    alertar(
        f"📈 Custo anômalo em *{feature}*: US$ {media_atual:.4f}/chamada "
        f"(era US$ {media_anterior:.4f} — {multiplicador:.1f}x)",
        nivel="🟠",
    )
    logger_financeiro.info(
        "Anomalia de custo: feature=%s media_atual=%.4f media_anterior=%.4f multiplicador=%.1f",
        feature, media_atual, media_anterior, multiplicador,
    )
