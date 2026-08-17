"""
services/embeddings/factory.py — Seleção do provedor de embedding

get_embedding_provider() é o único ponto que módulos de negócio devem
chamar. A seleção acontece exclusivamente aqui, via EMBEDDING_PROVIDER.
Nenhum módulo de domínio deve instanciar OllamaEmbeddingProvider ou
OpenAIEmbeddingProvider diretamente.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from .provider import EmbeddingProvider, EmbeddingProviderError

logger = logging.getLogger("saleia.embeddings.factory")

_KNOWN_PROVIDERS = {"ollama", "openai"}

# Singleton por processo — recriado apenas se a configuração relevante mudar
# (mesmo padrão do singleton _openai_client em agent/base_conhecimento.py,
# generalizado para qualquer provedor).
_instance: Optional[EmbeddingProvider] = None
_instance_key: Optional[tuple] = None


def _build_provider(provider_name: str) -> EmbeddingProvider:
    if provider_name == "ollama":
        from .ollama_provider import OllamaEmbeddingProvider
        return OllamaEmbeddingProvider()
    if provider_name == "openai":
        from .openai_provider import OpenAIEmbeddingProvider
        return OpenAIEmbeddingProvider()
    raise EmbeddingProviderError(
        f"EMBEDDING_PROVIDER desconhecido: '{provider_name}'. "
        f"Valores válidos: {', '.join(sorted(_KNOWN_PROVIDERS))}."
    )


def _current_config_key(provider_name: str) -> tuple:
    if provider_name == "ollama":
        return (
            "ollama",
            os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            os.environ.get("OLLAMA_EMBEDDING_MODEL", "embeddinggemma"),
        )
    if provider_name == "openai":
        return (
            "openai",
            os.environ.get("OPENAI_API_KEY", ""),
            os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        )
    return (provider_name,)


def get_embedding_provider(refresh: bool = False) -> EmbeddingProvider:
    """
    Retorna o EmbeddingProvider configurado via EMBEDDING_PROVIDER
    (padrão: "ollama"). Levanta EmbeddingProviderError se o valor for
    desconhecido — nunca escolhe silenciosamente outro provedor.

    Singleton por processo; refresh=True força reconstrução mesmo se a
    config aparentar não ter mudado (útil em testes).
    """
    global _instance, _instance_key

    provider_name = os.environ.get("EMBEDDING_PROVIDER", "ollama").strip().lower()
    config_key = _current_config_key(provider_name)

    if not refresh and _instance is not None and _instance_key == config_key:
        return _instance

    instance = _build_provider(provider_name)
    _instance = instance
    _instance_key = config_key
    logger.info("[Embeddings] Provider ativo: %s (modelo=%s)", instance.provider_name, instance.model_name)
    return instance


def get_fallback_provider() -> Optional[EmbeddingProvider]:
    """
    Retorna o provedor de fallback SOMENTE se EMBEDDING_FALLBACK_PROVIDER
    estiver explicitamente configurado. Por padrão (variável vazia/ausente)
    retorna None — não há fallback implícito. Não é usado pelos 4 pontos
    de produção (RAG, Sales Memory, /base, exportar-base); é utilitário
    para scripts/reindex_embeddings.py e para o endpoint de diagnóstico
    avaliarem se um fallback está disponível.
    """
    fallback_name = os.environ.get("EMBEDDING_FALLBACK_PROVIDER", "").strip().lower()
    if not fallback_name:
        return None
    if fallback_name not in _KNOWN_PROVIDERS:
        logger.warning("[Embeddings] EMBEDDING_FALLBACK_PROVIDER inválido ignorado: %s", fallback_name)
        return None
    return _build_provider(fallback_name)


def reset_provider_cache() -> None:
    """Força a próxima chamada a get_embedding_provider() a reconstruir o
    singleton. Usado por testes e por endpoints administrativos futuros."""
    global _instance, _instance_key
    _instance = None
    _instance_key = None
