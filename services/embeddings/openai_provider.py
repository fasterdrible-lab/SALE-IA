"""
services/embeddings/openai_provider.py — Embeddings via OpenAI (opcional)

Wrapper fino sobre o SDK openai já usado no restante do projeto para
chat completions. Mantém o comportamento e o modelo padrão que o
SALEIA já usava antes da introdução do EmbeddingProvider.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

from .provider import EmbeddingProvider, EmbeddingProviderError, EmbeddingResult

logger = logging.getLogger("saleia.embeddings.openai")

# Dimensões conhecidas dos modelos de embedding OpenAI mais comuns.
_KNOWN_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self._api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
        self._model = model or os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        self._timeout = timeout if timeout is not None else float(os.environ.get("EMBEDDING_TIMEOUT", "30"))
        self._dimension = _KNOWN_DIMENSIONS.get(self._model, 1536)

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> Optional[int]:
        return self._dimension

    def _require_key(self) -> str:
        if not self._api_key:
            raise EmbeddingProviderError("OPENAI_API_KEY não configurada para EMBEDDING_PROVIDER=openai")
        return self._api_key

    def embed(self, text: str) -> Optional[EmbeddingResult]:
        try:
            api_key = self._require_key()
        except EmbeddingProviderError:
            raise
        try:
            from openai import OpenAI
            with OpenAI(api_key=api_key, timeout=self._timeout) as client:
                resp = client.embeddings.create(model=self._model, input=text)
            vec = resp.data[0].embedding
        except EmbeddingProviderError:
            raise
        except Exception as e:
            logger.warning("[OpenAI] Erro ao gerar embedding: %s", e)
            return None
        self._dimension = len(vec)
        return EmbeddingResult(vector=vec, provider=self.provider_name, model=self._model, dimension=len(vec))

    async def embed_async(self, text: str) -> Optional[EmbeddingResult]:
        try:
            api_key = self._require_key()
        except EmbeddingProviderError:
            raise
        try:
            from openai import AsyncOpenAI
            async with AsyncOpenAI(api_key=api_key, timeout=self._timeout) as client:
                resp = await client.embeddings.create(model=self._model, input=text)
            vec = resp.data[0].embedding
        except EmbeddingProviderError:
            raise
        except Exception as e:
            logger.warning("[OpenAI] Erro ao gerar embedding (async): %s", e)
            return None
        self._dimension = len(vec)
        return EmbeddingResult(vector=vec, provider=self.provider_name, model=self._model, dimension=len(vec))

    def embed_batch(self, texts: list[str]) -> list[Optional[EmbeddingResult]]:
        if not texts:
            return []
        try:
            api_key = self._require_key()
        except EmbeddingProviderError:
            raise
        try:
            from openai import OpenAI
            with OpenAI(api_key=api_key, timeout=self._timeout) as client:
                resp = client.embeddings.create(model=self._model, input=texts)
            results: list[Optional[EmbeddingResult]] = []
            for item in resp.data:
                vec = item.embedding
                self._dimension = len(vec)
                results.append(EmbeddingResult(
                    vector=vec, provider=self.provider_name, model=self._model, dimension=len(vec),
                ))
            return results
        except EmbeddingProviderError:
            raise
        except Exception as e:
            logger.warning("[OpenAI] Erro ao gerar embeddings em lote: %s", e)
            return [None] * len(texts)

    async def health_check(self, timeout: float = 5.0) -> dict:
        start = time.monotonic()
        try:
            result = await self.embed_async("ping")
        except EmbeddingProviderError as e:
            return {"ok": False, "detalhe": str(e), "dimension": None, "latency_ms": None}
        latency_ms = (time.monotonic() - start) * 1000
        if result is None:
            return {"ok": False, "detalhe": "falha ao gerar embedding de teste", "dimension": None,
                     "latency_ms": round(latency_ms, 1)}
        return {"ok": True, "detalhe": "online", "dimension": result.dimension, "latency_ms": round(latency_ms, 1)}
