"""
Cost engine — Cost Intelligence Fase 1.

Cálculo de custo puro e determinístico: provider + model + usage -> USD.
Sem I/O, sem chamada de rede, sem acesso a banco. A estimativa char/4 (Task
5 do prompt de Cost Intelligence) continua existindo aqui como fallback,
usada só quando o provider não devolve uso real de tokens.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from api.pricing_catalog import cached_rate_efetivo, obter_preco


@dataclass(frozen=True)
class ProviderUsage:
    """Adapter comum de uso de tokens — cada provider popula isto a partir
    do seu próprio formato de `usage`/`usage_metadata`."""

    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0
    reasoning_output_tokens: int = 0
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CostResult:
    cost_usd: float
    currency: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    usage_source: str  # "provider" | "estimated"
    price_source: str


def _estimar_tokens_por_caracteres(texto: str) -> int:
    texto = texto or ""
    if not texto:
        return 0
    return max(1, int(round(len(texto) / 4)))


def estimar_usage(system_prompt: str, user_content: str, resultado: dict) -> ProviderUsage:
    """Fallback char/4 — mesma heurística já usada antes desta fase, agora
    isolada aqui para ser reaproveitada quando o provider não retorna uso
    real de tokens."""
    entrada = _estimar_tokens_por_caracteres(f"{system_prompt or ''}\n{user_content or ''}")
    saida = _estimar_tokens_por_caracteres(json.dumps(resultado or {}, ensure_ascii=False))
    return ProviderUsage(input_tokens=entrada, output_tokens=saida, cached_input_tokens=0)


def calcular_custo(provider: str, model: str, usage: ProviderUsage, usage_source: str) -> CostResult:
    """Função pura: não faz chamada de rede nem acessa banco/env dinamicamente
    além da leitura de preço (já resolvida por api.pricing_catalog)."""
    preco = obter_preco(provider, model)
    cached_tokens = min(usage.cached_input_tokens, usage.input_tokens)
    billable_input = max(usage.input_tokens - cached_tokens, 0)
    cached_rate = cached_rate_efetivo(preco)

    custo = (
        billable_input * preco.input_per_million
        + cached_tokens * cached_rate
        + (usage.output_tokens + usage.reasoning_output_tokens) * preco.output_per_million
    ) / 1_000_000

    return CostResult(
        cost_usd=round(custo, 6),
        currency="USD",
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cached_input_tokens=cached_tokens,
        usage_source=usage_source,
        price_source=preco.source,
    )
