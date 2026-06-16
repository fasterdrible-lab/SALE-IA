"""
T5.5 — Orquestrador Multiagente.

Roda Coach, DISC, Finance e Closer em paralelo via asyncio.gather e
consolida os resultados no mesmo schema JSON que o agente único produzia,
mantendo compatibilidade total com a extensão Chrome e o dashboard.
"""

import asyncio
import logging

from agent.base_conhecimento import buscar_contexto_similar
from agent.multiagente.coach_agent import analisar_coach
from agent.multiagente.disc_agent import analisar_disc
from agent.multiagente.finance_agent import analisar_finance
from agent.multiagente.closer_agent import analisar_closer

logger = logging.getLogger(__name__)

_FALLBACK_NBA = {
    "type": "question",
    "category": "descoberta_dor",
    "title": "Descoberta Inicial",
    "message": "Me conta um pouco mais sobre o que motivou voces a buscar uma solucao agora?",
    "objective": "Entender motivacao",
    "reason": "Contexto insuficiente para sugerir acao estrategica.",
    "expected_effect": "Abrir espaco para identificar a dor real",
    "risk_if_ignored": "A conversa pode nao avancar sem contexto do cliente.",
    "follow_up": None,
    "confidence": 0.5,
}

_FALLBACK_MATURITY = {
    "total": 0,
    "dor_identificada": 0,
    "impacto_quantificado": 0,
    "urgencia_identificada": 0,
    "budget_identificado": 0,
    "decisores_mapeados": 0,
    "valor_verbalizado_cliente": 0,
    "proximo_passo_claro": 0,
}


def _nba_para_nbq(nba: dict) -> dict:
    fbq = _FALLBACK_NBA["message"]
    return {
        "question": nba.get("message") or fbq,
        "category": nba.get("category") or "descoberta_dor",
        "objective": nba.get("objective") or "",
        "reason": nba.get("reason") or "",
        "expected_score_impact": "+10",
        "urgency_level": "high" if (nba.get("confidence") or 0) >= 0.8 else "medium",
        "follow_up_question": nba.get("follow_up"),
    }


def _safe(result, default=None):
    """Retorna result se for dict, caso contrário default."""
    if isinstance(result, Exception):
        return default if default is not None else {}
    if not isinstance(result, dict):
        return default if default is not None else {}
    return result


def _mesclar(coach: dict, disc: dict, finance: dict, closer: dict) -> dict:
    resultado: dict = {"status": "updated"}

    # T5.1 — Coach
    resultado["conversation_stage"] = coach.get("conversation_stage") or "abertura"
    resultado["next_best_action"]   = coach.get("next_best_action") or dict(_FALLBACK_NBA)
    resultado["alerta_urgente"]     = coach.get("alerta_urgente")
    resultado["dica_vendedor"]      = coach.get("dica_vendedor")
    resultado["filtro_cliente"]     = coach.get("filtro_cliente") or {}
    resultado["recapitulacao"]      = coach.get("recapitulacao")
    resultado["dado_esquecido"]     = coach.get("dado_esquecido")
    resultado["texto_falavel"]      = coach.get("texto_falavel") or coach.get("proxima_fala")
    resultado["proxima_fala"]       = resultado["texto_falavel"]
    resultado["key_moments"]        = coach.get("key_moments") or []
    resultado["eventos"]            = coach.get("eventos") or []
    resultado["events"]             = list(resultado["eventos"])

    # T5.2 — DISC
    resultado["perfil_disc"] = disc.get("perfil_disc") or {}
    resultado["kare_type"]   = disc.get("kare_type") or "attain"
    resultado["temperatura"] = disc.get("temperatura") or {}

    # T5.3 — Finance
    resultado["mapa_financeiro"]   = finance.get("mapa_financeiro") or {}
    resultado["objecao_detectada"] = finance.get("objecao_detectada") or {}

    # T5.4 — Closer
    resultado["score_compra"]    = closer.get("score_compra") or {"valor": None, "justificativa": None}
    resultado["maturity_score"]  = closer.get("maturity_score") or dict(_FALLBACK_MATURITY)
    resultado["resumo_vivo"]     = closer.get("resumo_vivo") or ""
    resultado["current_diagnosis"] = closer.get("current_diagnosis") or {}
    resultado["proxima_acao"]    = closer.get("proxima_acao") or closer.get("acao_recomendada")
    resultado["acao_recomendada"] = resultado["proxima_acao"]
    resultado["proxima_pergunta"] = closer.get("proxima_pergunta")

    # Cross-links para backward compat
    resultado["next_best_question"] = _nba_para_nbq(resultado["next_best_action"])
    if resultado["resumo_vivo"] and not resultado.get("recapitulacao"):
        resultado["recapitulacao"] = resultado["resumo_vivo"]
    resultado["historico_resumido"] = resultado.get("resumo_vivo") or ""

    # Garante maturity_score.total
    ms = resultado["maturity_score"]
    if not ms.get("total"):
        ms["total"] = sum(v for k, v in ms.items() if k != "total" and isinstance(v, (int, float)))

    return resultado


async def analisar_fragmento_multi(
    transcricao_parcial: str,
    historico: str = "Inicio da conversa",
    perfil_disc_atual: str = "Ainda nao identificado",
    mapa_financeiro: dict = None,
    resumo_vivo: str = "Resumo ainda nao disponivel",
    diagnostico_atual: dict = None,
    historico_scores: list = None,
    eventos: list = None,
    skill_context: str = "",
    client_context: str = "",
) -> dict:
    diag = diagnostico_atual or {}
    scores = historico_scores or []
    evts = eventos or []
    mapa = mapa_financeiro or {}
    rv = resumo_vivo or "Resumo ainda nao disponivel"

    # RAG context — busca uma vez e compartilha entre agentes via client_context
    try:
        rag = await buscar_contexto_similar(f"{transcricao_parcial} {historico}", top_k=3)
        if rag:
            client_context = (client_context or "") + f"\n\n{rag}"
    except Exception as _e:
        logger.debug("[Multiagente] RAG falhou: %s", _e)

    # Sales Memory — memórias comerciais extraídas de reuniões anteriores
    try:
        from agent.sales_memory import buscar_contexto_para_reuniao
        mem_ctx = buscar_contexto_para_reuniao(f"{transcricao_parcial} {historico}", top_k=3)
        if mem_ctx:
            client_context = (client_context or "") + f"\n\n{mem_ctx}"
    except Exception as _e:
        logger.debug("[Multiagente] Sales Memory falhou: %s", _e)

    coach_coro   = analisar_coach(transcricao_parcial, historico, rv, diag, evts, skill_context, client_context)
    disc_coro    = analisar_disc(transcricao_parcial, historico, perfil_disc_atual, diag)
    finance_coro = analisar_finance(transcricao_parcial, historico, mapa)
    closer_coro  = analisar_closer(transcricao_parcial, rv, scores, diag)

    resultados = await asyncio.gather(
        coach_coro, disc_coro, finance_coro, closer_coro,
        return_exceptions=True,
    )

    coach_r, disc_r, finance_r, closer_r = resultados

    for nome, res in [("Coach", coach_r), ("DISC", disc_r), ("Finance", finance_r), ("Closer", closer_r)]:
        if isinstance(res, Exception):
            logger.warning("[Multiagente] %s falhou: %s", nome, res)

    return _mesclar(
        _safe(coach_r),
        _safe(disc_r),
        _safe(finance_r),
        _safe(closer_r),
    )
