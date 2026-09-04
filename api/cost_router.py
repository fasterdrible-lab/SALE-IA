"""
SALEIA — api/cost_router.py
Cost Router — Cost Intelligence Fase 4, ATIVO em producao desde V.1.4.61.

Quando `router_ativo()` (env COST_ROUTER_ATIVO, default true), o router
substitui de verdade o modelo usado dentro do provedor que ja venceu a
chamada real (ver api/ai_router.py::chamar_ia::modelo_a_usar) — nunca
mexe em ordem/escolha de provedor, circuit breaker ou fallback, so no
modelo dentro do provedor. Kill-switch: COST_ROUTER_ATIVO=false no .env
+ systemctl restart saleia volta ao modelo padrao configurado, sem
reverter deploy.

`registrar_decisao()` grava a comparacao real x recomendado pra
auditoria — e sempre melhor esforco, nunca deve poder derrubar uma
chamada de IA real.
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


def router_ativo() -> bool:
    return os.getenv("COST_ROUTER_ATIVO", "true").strip().lower() not in ("false", "0", "")


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


def modelo_a_usar(provider: str, model_padrao: str, feature: str) -> str:
    """Modelo que api/ai_router.py::chamar_ia deve usar de verdade dentro
    do provedor que ja venceu — aplica a recomendacao do router quando
    `router_ativo()`, senao devolve `model_padrao` inalterado (kill-switch
    desligado = comportamento identico a antes da Fase 4 existir)."""
    if not router_ativo():
        return model_padrao
    return recomendar_modelo(provider, model_padrao, feature)


def registrar_decisao(
    *,
    feature: str,
    provider: str,
    model_real: str,
    usage: ProviderUsage,
    usage_source: str,
) -> None:
    """Registra, para auditoria, a decisao do router para essa chamada de
    IA real ja concluida (o `model_real` ja e o modelo recomendado quando
    o router esta ativo) — melhor esforco, nunca lanca. Chamado de dentro
    de api/ai_router.py::chamar_ia DEPOIS do resultado real ja ter sido
    decidido; uma falha aqui jamais deve ser visivel pra chamada real."""
    if not router_ativo():
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
    """Config legivel do router para o painel admin."""
    return {
        "ativo": router_ativo(),
        "modo_atual": modo_atual(),
        "modelos_economy": dict(MODELOS_ECONOMY),
        "classificacao": {
            "simples": sorted(_FEATURES_SIMPLES),
            "complexa": sorted(_FEATURES_COMPLEXAS),
        },
    }
