"""
services/observability/factory.py — Seleção do provedor de observabilidade

get_observability_provider() é o único ponto que módulos de negócio devem
chamar. A seleção acontece exclusivamente aqui, via OBSERVABILITY_ENABLED
+ OBSERVABILITY_PROVIDER. Nenhum módulo de domínio deve instanciar
LangfuseObservabilityProvider/NoOpObservabilityProvider diretamente.

Chamadores nunca cacheiam a instância — chamam get_observability_provider()
inline, dentro do próprio try/except Exception, a cada uso (mesma
convenção de services/embeddings/factory.py).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from .provider import ObservabilityProvider, ObservabilityProviderError

logger = logging.getLogger("saleia.observability.factory")

_KNOWN_PROVIDERS = {"langfuse"}

_instance: Optional[ObservabilityProvider] = None
_instance_key: Optional[tuple] = None


def _observability_habilitada() -> bool:
    return os.getenv("OBSERVABILITY_ENABLED", "false").strip().lower() in ("1", "true", "yes")


def _build_provider(provider_name: str, enabled: bool) -> ObservabilityProvider:
    if not enabled:
        from .noop_provider import NoOpObservabilityProvider
        return NoOpObservabilityProvider()
    if provider_name == "langfuse":
        from .langfuse_provider import LangfuseObservabilityProvider
        return LangfuseObservabilityProvider()
    raise ObservabilityProviderError(
        f"OBSERVABILITY_PROVIDER desconhecido: '{provider_name}'. "
        f"Valores válidos: {', '.join(sorted(_KNOWN_PROVIDERS))}."
    )


def _current_config_key() -> tuple:
    if not _observability_habilitada():
        return ("noop",)
    return (
        "langfuse",
        os.environ.get("OBSERVABILITY_PROVIDER", "langfuse").strip().lower(),
        os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
        os.environ.get("LANGFUSE_HOST", ""),
    )


def get_observability_provider(refresh: bool = False) -> ObservabilityProvider:
    """
    Retorna o ObservabilityProvider configurado. Desligado por padrão
    (OBSERVABILITY_ENABLED=false) -> NoOpObservabilityProvider. Ligado
    com OBSERVABILITY_PROVIDER desconhecido levanta ObservabilityProviderError
    (erro de config — sem fallback silencioso pra outro provider).

    Singleton por processo; refresh=True força reconstrução.
    """
    global _instance, _instance_key

    config_key = _current_config_key()
    if not refresh and _instance is not None and _instance_key == config_key:
        return _instance

    enabled = _observability_habilitada()
    provider_name = os.environ.get("OBSERVABILITY_PROVIDER", "langfuse").strip().lower()
    instance = _build_provider(provider_name, enabled)
    _instance = instance
    _instance_key = config_key
    if enabled:
        logger.info("[Observability] Provider ativo: %s", provider_name)
    return instance


def reset_provider_cache() -> None:
    """Força a próxima chamada a get_observability_provider() a
    reconstruir o singleton. Usado por testes."""
    global _instance, _instance_key
    _instance = None
    _instance_key = None
