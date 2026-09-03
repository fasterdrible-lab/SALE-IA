"""
SALEIA — api/cost_router.py
Cost Router — Cost Intelligence Fase 4, SHADOW MODE.

IMPORTANTE: este modulo nunca altera qual provedor/modelo e usado numa
chamada de IA real. Ele calcula o que RECOMENDARIA e grava a comparacao
contra o que realmente aconteceu, para dar dados antes de qualquer
decisao futura de ativar o roteamento de verdade. `avaliar_shadow()` e
sempre melhor esforco — nunca deve poder derrubar uma chamada de IA real.

Escopo desta fase: o router so decide o MODELO dentro do provedor que ja
venceu de verdade (ver api/ai_router.py::chamar_ia) — nao mexe em ordem
ou escolha de provedor, nem em circuit breaker, nem em fallback.
"""

from __future__ import annotations

import os
import time

from api import ai_features as feat
from api.cost_engine import ProviderUsage, calcular_custo

# ─────────────────────────────────────────────
# Classificacao de complexidade por feature — heuristica de produto,
# ponto de partida ajustavel, nao verdade absoluta. Features fora dessas
# duas listas (incluindo futuras/desconhecidas) caem em "padrao".
# ─────────────────────────────────────────────
_FEATURES_SIMPLES = {
    feat.REALTIME_DISC,
    feat.REPORT_PERFIL_DISC,
    feat.TACTIQ_PERFIL_DISC,
}
_FEATURES_COMPLEXAS = {
    feat.REPORT_DIAGNOSTICO_FINANCEIRO,
    feat.REPORT_RECAPITULACAO,
    feat.TACTIQ_RECAPITULACAO,
    feat.TACTIQ_DIAGNOSTICO_FINANCEIRO,
    feat.PLAYBOOK_GERACAO,
    feat.KNOWLEDGE_EXTRACAO_MEMORIAS,
    feat.KNOWLEDGE_COMPILER_EXTRACAO,
}

# Modelo "economy" por provedor — DeepSeek e Gemini ja usam seus modelos
# mais baratos como padrao hoje, sem variante separada.
MODELOS_ECONOMY: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-20241022",
}

_MODO_CACHE_TTL_S = 300  # 5min — chamar_ia e um caminho muito mais quente que o loop de metricas
_modo_cache: dict = {"modo": None, "ts": 0.0}


def classificar_complexidade(feature: str) -> str:
    if feature in _FEATURES_SIMPLES:
        return "simples"
    if feature in _FEATURES_COMPLEXAS:
        return "complexa"
    return "padrao"


def _shadow_habilitado() -> bool:
    return os.getenv("COST_ROUTER_SHADOW_ENABLED", "true").strip().lower() not in ("false", "0", "")


def modo_atual() -> str:
    """"normal"/"economy"/"critical" a partir do % do orcamento mensal ja
    gasto (Fase 3) — mesmos limiares do Budget Guard (80%/100%). Cacheado
    em memoria por 5min para nao bater no MySQL a cada chamada de IA.
    Sem orcamento configurado -> sempre "normal" (nunca forca
    comportamento sem configuracao explicita do admin)."""
    agora = time.time()
    if _modo_cache["modo"] is not None and (agora - _modo_cache["ts"]) < _MODO_CACHE_TTL_S:
        return _modo_cache["modo"]

    modo = "normal"
    try:
        from api.database import gasto_mes_usd, obter_orcamento_ia
        from datetime import datetime

        orcamento = obter_orcamento_ia()
        limite = (orcamento or {}).get("limite_mensal_usd")
        if limite and limite > 0:
            hoje = datetime.now()
            gasto = gasto_mes_usd(hoje.year, hoje.month)
            pct = gasto / limite * 100
            if pct >= 100:
                modo = "critical"
            elif pct >= 80:
                modo = "economy"
    except Exception:
        modo = "normal"  # banco indisponivel -> nunca forca economy/critical sem certeza

    _modo_cache["modo"] = modo
    _modo_cache["ts"] = agora
    return modo


def recomendar_modelo(provider: str, modelo_real: str, feature: str, modo: str | None = None) -> str:
    """Modelo que o router recomendaria para esse provedor/feature, dado o
    modo atual — nunca muda o provedor, so o modelo dentro dele."""
    economy = MODELOS_ECONOMY.get(provider)
    if not economy:
        return modelo_real  # provedor sem variante economy separada (deepseek/gemini)

    modo = modo or modo_atual()
    complexidade = classificar_complexidade(feature)

    usar_economy = (
        modo == "critical"
        or (modo == "economy" and complexidade in ("simples", "padrao"))
        or (modo == "normal" and complexidade == "simples")
    )
    return economy if usar_economy else modelo_real


def avaliar_shadow(
    *,
    feature: str,
    provider: str,
    model_real: str,
    usage: ProviderUsage,
    usage_source: str,
) -> None:
    """Registra, em modo shadow, o que o router teria recomendado para essa
    chamada de IA real ja concluida — melhor esforco, nunca lanca. Chamado
    de dentro de api/ai_router.py::chamar_ia DEPOIS do resultado real ja
    ter sido decidido; uma falha aqui jamais deve ser visivel pra chamada
    real."""
    if not _shadow_habilitado():
        return
    try:
        modo = modo_atual()
        complexidade = classificar_complexidade(feature)
        model_recomendado = recomendar_modelo(provider, model_real, feature, modo=modo)

        custo_real = calcular_custo(provider, model_real, usage, usage_source)
        if model_recomendado == model_real:
            custo_recomendado_usd = custo_real.cost_usd
        else:
            custo_recomendado_usd = calcular_custo(provider, model_recomendado, usage, usage_source).cost_usd

        from api.database import registrar_decisao_router
        registrar_decisao_router(
            feature=feature,
            complexidade=complexidade,
            modo=modo,
            provider=provider,
            model_real=model_real,
            custo_real_usd=custo_real.cost_usd,
            model_recomendado=model_recomendado,
            custo_recomendado_usd=custo_recomendado_usd,
            concordou=(model_recomendado == model_real),
        )
    except Exception:
        pass  # melhor esforco absoluto — nunca deve afetar a chamada de IA real


def config_router() -> dict:
    """Config legivel do router para o painel admin (somente leitura —
    nao existe endpoint de ativacao nesta fase)."""
    return {
        "shadow_habilitado": _shadow_habilitado(),
        "modo_atual": modo_atual(),
        "modelos_economy": dict(MODELOS_ECONOMY),
        "classificacao": {
            "simples": sorted(_FEATURES_SIMPLES),
            "complexa": sorted(_FEATURES_COMPLEXAS),
        },
    }
