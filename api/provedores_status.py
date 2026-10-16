"""Painel de provedores de IA + avisos de saldo baixo e de reserva em uso
(V.1.4.183). Regras puras em `agent/provedores_status_rules.py`.

O estado dos circuit breakers fica na memória de cada worker do uvicorn;
o uso por provedor vem de `ai_usage_events` (vale para os 2 workers). Os
limites do Groq e o carimbo dos avisos ficam em arquivos de `data/`, para
os 2 workers verem o mesmo valor e não avisarem em dobro.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from agent.provedores_status_rules import (
    SALDO_DEEPSEEK_ALERTA_PADRAO_USD,
    ler_limites_groq,
    ler_saldo_deepseek,
    montar_alerta_reserva,
    montar_alerta_saldo_baixo,
    provedor_em_uso,
    saldo_baixo,
)

logger = logging.getLogger("saleia.provedores")

DIR_DADOS = Path(os.getenv("PROVEDORES_STATUS_DIR") or "data")
ARQ_LIMITES_GROQ = "groq_limites.json"
SALDO_CACHE_S = 300
_saldo_cache: dict = {"em": 0.0, "valor": None, "erro": None}
_saldo_lock = threading.Lock()


def limite_alerta_saldo_usd() -> float:
    try:
        return float(os.getenv("SALDO_DEEPSEEK_ALERTA_USD", SALDO_DEEPSEEK_ALERTA_PADRAO_USD))
    except ValueError:
        return SALDO_DEEPSEEK_ALERTA_PADRAO_USD


# ── DeepSeek: saldo ─────────────────────────────────────────────────────

def saldo_deepseek(forcar: bool = False) -> dict:
    """{"saldo": {...} | None, "erro": str | None, "consultado_em": iso}.
    Cache de 5 min (o painel e o laço de alerta não martelam a API)."""
    with _saldo_lock:
        if not forcar and time.time() - _saldo_cache["em"] < SALDO_CACHE_S and _saldo_cache["em"]:
            return {"saldo": _saldo_cache["valor"], "erro": _saldo_cache["erro"],
                    "consultado_em": datetime.fromtimestamp(_saldo_cache["em"]).isoformat(timespec="seconds")}
    chave = os.getenv("DEEPSEEK_API_KEY", "")
    valor, erro = None, None
    if not chave:
        erro = "sem chave"
    else:
        try:
            base = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
            req = urllib.request.Request(base + "/user/balance",
                                         headers={"Authorization": "Bearer " + chave, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                valor = ler_saldo_deepseek(json.load(r))
            if valor is None:
                erro = "resposta sem saldo"
        except Exception as exc:
            erro = type(exc).__name__  # nunca a mensagem crua (pode ecoar a chave)
    with _saldo_lock:
        _saldo_cache.update(em=time.time(), valor=valor, erro=erro)
    return {"saldo": valor, "erro": erro, "consultado_em": datetime.now().isoformat(timespec="seconds")}


# ── Groq: limites vindos dos cabeçalhos ─────────────────────────────────

def registrar_limites_groq(cabecalhos) -> None:
    """Chamado por `api/ai_router.py::_call_groq` a cada resposta. Melhor
    esforço: nunca pode afetar a chamada de IA."""
    try:
        limites = ler_limites_groq(dict(cabecalhos or {}))
        if not limites:
            return
        limites["registrado_em"] = datetime.now().isoformat(timespec="seconds")
        DIR_DADOS.mkdir(parents=True, exist_ok=True)
        tmp = DIR_DADOS / (ARQ_LIMITES_GROQ + ".tmp")
        tmp.write_text(json.dumps(limites), encoding="utf-8")
        os.replace(tmp, DIR_DADOS / ARQ_LIMITES_GROQ)
    except Exception as exc:
        logger.debug("Limites do Groq não registrados: %s", exc)


def limites_groq() -> dict | None:
    try:
        return json.loads((DIR_DADOS / ARQ_LIMITES_GROQ).read_text(encoding="utf-8"))
    except Exception:
        return None


# ── Uso por provedor (ai_usage_events) ──────────────────────────────────

def _uso_recente(agora: datetime) -> tuple[dict, list]:
    from sqlalchemy import text
    from api.database import engine
    uso: dict = {}
    sucessos: list = []
    with engine.connect() as c:
        for prov, ok, falha, custo in c.execute(text(
                """SELECT provider, SUM(success), SUM(NOT success), SUM(cost_usd) FROM ai_usage_events
                   WHERE criado_em >= :desde AND provider NOT IN ('none', 'cache') GROUP BY provider"""),
                {"desde": agora - timedelta(hours=1)}):
            uso[prov] = {"ok_1h": int(ok or 0), "falhas_1h": int(falha or 0), "custo_1h_usd": round(float(custo or 0), 4)}
        for prov, quando in c.execute(text(
                """SELECT provider, MAX(criado_em) FROM ai_usage_events
                   WHERE success AND provider NOT IN ('none', 'cache') AND criado_em >= :desde GROUP BY provider"""),
                {"desde": agora - timedelta(days=7)}):
            uso.setdefault(prov, {"ok_1h": 0, "falhas_1h": 0, "custo_1h_usd": 0.0})["ultimo_sucesso"] = quando.isoformat(timespec="seconds")
        sucessos = [(p, q.isoformat(timespec="seconds")) for p, q in c.execute(text(
                """SELECT provider, criado_em FROM ai_usage_events
                   WHERE success AND provider NOT IN ('none', 'cache') AND criado_em >= :desde
                   ORDER BY criado_em DESC LIMIT 1"""), {"desde": agora - timedelta(minutes=15)})]
    return uso, sucessos


def painel_provedores() -> dict:
    """Tudo o que o card "Provedores de IA" do Dashboard mostra."""
    from agent.ia_indisponivel_rules import classificar_causa
    from api import ai_router

    ordem = ai_router.ordem_provedores()
    status = ai_router.status_provedores()
    agora = datetime.now()
    try:
        uso, sucessos = _uso_recente(agora)
    except Exception as exc:
        logger.warning("Uso por provedor indisponível: %s", exc)
        uso, sucessos = {}, []

    provedores = []
    for nome in ordem:
        s = status.get(nome, {})
        breaker = ai_router._breakers.get(nome)
        ultimo_erro = getattr(breaker, "last_error", "") if breaker else ""
        item = {
            "nome": nome,
            "modelo": s.get("modelo"),
            "configurado": s.get("configurado"),
            "status": s.get("status"),
            "falhas_consecutivas": s.get("falhas_consecutivas", 0),
            "causa": classificar_causa(ultimo_erro) if ultimo_erro else None,
            **uso.get(nome, {"ok_1h": 0, "falhas_1h": 0, "custo_1h_usd": 0.0}),
        }
        if nome == "deepseek":
            item["saldo"] = saldo_deepseek()
            item["saldo_alerta_usd"] = limite_alerta_saldo_usd()
        if nome == "groq":
            item["limites"] = limites_groq()
        provedores.append(item)
    return {
        "ordem": ordem,
        "em_uso": provedor_em_uso(sucessos, ordem),
        "provedores": provedores,
        "gerado_em": agora.isoformat(timespec="seconds"),
    }


# ── Avisos no Telegram (sem duplicar entre os 2 workers) ────────────────

def _pode_avisar(chave: str, intervalo_s: int) -> bool:
    """Carimbo em arquivo: o 1º worker que passar do intervalo avisa e
    grava; o outro lê o carimbo novo e não repete."""
    try:
        DIR_DADOS.mkdir(parents=True, exist_ok=True)
        arq = DIR_DADOS / f"aviso_{chave}.ts"
        agora = time.time()
        try:
            ultimo = float(arq.read_text(encoding="utf-8").strip() or 0)
        except Exception:
            ultimo = 0.0
        if agora - ultimo < intervalo_s:
            return False
        arq.write_text(str(agora), encoding="utf-8")
        return True
    except Exception:
        return False


def verificar_saldo_e_avisar() -> dict | None:
    """Laço de métricas, a cada ~30 min. Avisa no máximo 1x a cada 6 h."""
    r = saldo_deepseek(forcar=True)
    saldo = r.get("saldo")
    limite = limite_alerta_saldo_usd()
    if saldo_baixo(saldo, limite) and _pode_avisar("saldo_deepseek", 6 * 3600):
        from agent.alertas import alertar
        alertar(montar_alerta_saldo_baixo(saldo, limite), nivel="🟠")
    return saldo


def avisar_reserva_em_uso(provedor: str, tentativas: list[dict]) -> None:
    """`api/ai_router.py`: chamada atendida por quem não é o 1º da ordem.
    No máximo 1 aviso por hora. Melhor esforço."""
    try:
        if not _pode_avisar("reserva_em_uso", 3600):
            return
        from agent.ia_indisponivel_rules import classificar_causa
        causas = {}
        for t in tentativas:
            if t.get("provider") == provedor:
                break
            st = t.get("status")
            causas[t.get("provider")] = classificar_causa(t.get("error")) if st == "failed" else st
        from agent.alertas import alertar
        alertar(montar_alerta_reserva(provedor, causas), nivel="🟠")
    except Exception as exc:
        logger.debug("Aviso de reserva não enviado: %s", exc)
