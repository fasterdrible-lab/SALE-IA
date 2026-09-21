"""
Catálogo central de preços de IA — Cost Intelligence Fase 1.

Preço é indexado por (provider, model), não só por provider — dois modelos
do mesmo provider podem ter custos reais bem diferentes (ex.: gpt-4o vs.
gpt-4o-mini). Quando o modelo configurado não está catalogado (ex.: alguém
troca OPENAI_MODEL via .env para algo novo), cai num fallback genérico por
provider — mesmas taxas que já existiam hardcoded em api/ai_router.py antes
desta fase, preservando o comportamento anterior sem quebrar nada.

Preços podem ser sobrescritos via variável de ambiente, sem precisar de
deploy: PRICE_<PROVIDER>_<MODELO_SANITIZADO>_<CAMPO>_PER_MILLION.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Cache hit sem taxa própria publicada pelo provider: assume 10% do preço de
# input normal (ordem de grandeza comum entre os providers que documentam
# cache hoje — DeepSeek e OpenAI ficam perto disso).
_CACHED_DISCOUNT_DEFAULT = 0.1


@dataclass(frozen=True)
class ModelPrice:
    provider: str
    model: str
    input_per_million: float
    output_per_million: float
    cached_input_per_million: float | None
    source: str
    effective_date: str


# Catálogo específico por modelo. Não pretende ser exaustivo nem eterno —
# `source`/`effective_date` deixam explícito de onde veio cada preço, para
# quem for atualizar não precisar adivinhar se ainda está correto.
_CATALOG: dict[tuple[str, str], ModelPrice] = {
    ("deepseek", "deepseek-chat"): ModelPrice(
        "deepseek", "deepseek-chat", 0.14, 0.28, 0.014,
        "deepseek_pricing_2026-06", "2026-06-01",
    ),
    ("openai", "gpt-4o"): ModelPrice(
        "openai", "gpt-4o", 2.50, 10.0, 1.25,
        "openai_pricing_2026-05", "2026-05-01",
    ),
    # claude-sonnet-4-20250514 entrou em EOL (15/06/2026) e não é mais o
    # default de api/ai_router.py — entrada mantida só como registro
    # histórico (algum AiUsageEvent antigo ou ANTHROPIC_MODEL customizado
    # ainda pode referenciar esse id).
    ("anthropic", "claude-sonnet-4-20250514"): ModelPrice(
        "anthropic", "claude-sonnet-4-20250514", 3.0, 15.0, 0.30,
        "anthropic_pricing_2025-05", "2025-05-14",
    ),
    # Preço herdado do tier anterior (claude-sonnet-4-20250514) — mesmo
    # valor que já caía aqui via _PROVIDER_FALLBACK["anthropic"], nunca
    # reverificado direto com a tabela de preços da Anthropic pra este id
    # especificamente. Atualizar quando/se o preço real divergir.
    ("anthropic", "claude-sonnet-4-6"): ModelPrice(
        "anthropic", "claude-sonnet-4-6", 3.0, 15.0, 0.30,
        "anthropic_pricing_herdado_sonnet4_nao_reverificado", "2026-09-21",
    ),
    ("gemini", "gemini-2.0-flash"): ModelPrice(
        "gemini", "gemini-2.0-flash", 0.10, 0.40, 0.025,
        "gemini_pricing_2026-01", "2026-01-01",
    ),
    # Variantes "economy" — usadas pelo Cost Router (Fase 4, shadow mode)
    # para estimar economia real ao recomendar um modelo mais barato do
    # mesmo provedor. Sem preco proprio aqui, cairiam no fallback generico
    # do provedor (mais caro que o preco real desses modelos) e invalidariam
    # a comparacao.
    ("openai", "gpt-4o-mini"): ModelPrice(
        "openai", "gpt-4o-mini", 0.15, 0.60, 0.075,
        "openai_pricing_2026-05", "2026-05-01",
    ),
    ("anthropic", "claude-3-5-haiku-20241022"): ModelPrice(
        "anthropic", "claude-3-5-haiku-20241022", 0.80, 4.00, 0.08,
        "anthropic_pricing_2025-05", "2025-05-14",
    ),
}

# Fallback por-provider — preserva as taxas que já existiam hardcoded em
# api/ai_router.py (ESTIMATED_COST_INPUT_PER_MILLION/OUTPUT) antes desta
# fase, para qualquer modelo fora do catálogo específico acima.
_PROVIDER_FALLBACK: dict[str, ModelPrice] = {
    "deepseek": ModelPrice("deepseek", "*", 0.14, 0.28, None, "fallback_provider_generico", "2026-08-31"),
    "openai": ModelPrice("openai", "*", 5.0, 15.0, None, "fallback_provider_generico", "2026-08-31"),
    "anthropic": ModelPrice("anthropic", "*", 3.0, 15.0, None, "fallback_provider_generico", "2026-08-31"),
    "gemini": ModelPrice("gemini", "*", 0.35, 1.05, None, "fallback_provider_generico", "2026-08-31"),
}

_DEFAULT_FALLBACK = _PROVIDER_FALLBACK["openai"]


def _sanitizar_para_env(texto: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in texto.upper())


def _env_override(provider: str, model: str, campo: str) -> float | None:
    chave_modelo = _sanitizar_para_env(model)
    env_key = f"PRICE_{provider.upper()}_{chave_modelo}_{campo.upper()}_PER_MILLION"
    valor = os.getenv(env_key)
    if valor in (None, ""):
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def obter_preco(provider: str, model: str) -> ModelPrice:
    """Resolve o preço para (provider, model): catálogo específico → fallback
    genérico do provider → override por variável de ambiente, nessa ordem
    de precedência crescente (env sempre vence quando presente)."""
    base = _CATALOG.get((provider, model)) or _PROVIDER_FALLBACK.get(provider) or _DEFAULT_FALLBACK

    input_ov = _env_override(provider, model, "input")
    output_ov = _env_override(provider, model, "output")
    cached_ov = _env_override(provider, model, "cached")

    if input_ov is None and output_ov is None and cached_ov is None:
        return base

    return ModelPrice(
        provider=provider,
        model=model,
        input_per_million=input_ov if input_ov is not None else base.input_per_million,
        output_per_million=output_ov if output_ov is not None else base.output_per_million,
        cached_input_per_million=cached_ov if cached_ov is not None else base.cached_input_per_million,
        source="env_override",
        effective_date="runtime",
    )


def cached_rate_efetivo(preco: ModelPrice) -> float:
    """Taxa de cache a usar no cálculo — desconto padrão quando o provider
    não publica uma taxa própria de cache."""
    if preco.cached_input_per_million is not None:
        return preco.cached_input_per_million
    return preco.input_per_million * _CACHED_DISCOUNT_DEFAULT
