"""
services/embeddings/ollama_provider.py — Embeddings locais via Ollama

Não importa openai/anthropic/google.generativeai — nenhum texto passado
a este provedor sai da máquina onde o Ollama está rodando (localhost por
padrão, ou o host configurado em OLLAMA_BASE_URL).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

import httpx

from .provider import EmbeddingProvider, EmbeddingProviderError, EmbeddingResult

logger = logging.getLogger("saleia.embeddings.ollama")

_TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504}
_MAX_RETRIES = 2
_RETRY_BACKOFF_BASE = 0.5  # segundos


class OllamaEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        batch_size: Optional[int] = None,
    ):
        self._base_url = (base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self._model = model or os.environ.get("OLLAMA_EMBEDDING_MODEL", "embeddinggemma")
        self._timeout = timeout if timeout is not None else float(os.environ.get("EMBEDDING_TIMEOUT", "30"))
        self._batch_size = batch_size or int(os.environ.get("EMBEDDING_BATCH_SIZE", "32"))
        # Dimensão só é conhecida após uma chamada real bem-sucedida —
        # nunca hardcoded (modelos/quantizações diferentes podem variar).
        self._dimension: Optional[int] = None

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> Optional[int]:
        return self._dimension

    def _endpoint(self) -> str:
        return f"{self._base_url}/api/embeddings"

    async def _post_embedding(self, client: httpx.AsyncClient, text: str) -> list[float]:
        last_error: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = await client.post(
                    self._endpoint(),
                    json={"model": self._model, "prompt": text},
                    timeout=self._timeout,
                )
                if resp.status_code in _TRANSIENT_STATUS and attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_BACKOFF_BASE * (attempt + 1))
                    continue
                if resp.status_code == 404:
                    raise RuntimeError(
                        f"Modelo '{self._model}' não encontrado no Ollama — "
                        f"rode: ollama pull {self._model}"
                    )
                resp.raise_for_status()
                data = resp.json()
                vec = data.get("embedding")
                if not vec or not isinstance(vec, list):
                    raise RuntimeError(f"Resposta do Ollama sem 'embedding' válido: {data!r}")
                return vec
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_error = e
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_BACKOFF_BASE * (attempt + 1))
                    continue
                raise RuntimeError(f"Ollama inacessível em {self._base_url}: {e}") from e
        if last_error:
            raise RuntimeError(f"Ollama inacessível em {self._base_url}: {last_error}")
        raise RuntimeError("Falha desconhecida ao chamar Ollama")

    async def embed_async(self, text: str) -> Optional[EmbeddingResult]:
        try:
            async with httpx.AsyncClient() as client:
                vec = await self._post_embedding(client, text)
        except Exception as e:
            logger.warning("[Ollama] Erro ao gerar embedding: %s", e)
            return None
        self._dimension = len(vec)
        return EmbeddingResult(vector=vec, provider=self.provider_name, model=self._model, dimension=len(vec))

    def embed(self, text: str) -> Optional[EmbeddingResult]:
        try:
            return asyncio.run(self.embed_async(text))
        except RuntimeError as e:
            if "asyncio.run() cannot be called" in str(e):
                # Já existe um event loop rodando (contexto async chamando código sync) —
                # não há como bloquear nele; falha explícita em vez de deadlock silencioso.
                logger.error("[Ollama] embed() síncrono chamado dentro de um event loop ativo: %s", e)
                return None
            logger.warning("[Ollama] Erro ao gerar embedding: %s", e)
            return None

    def embed_batch(self, texts: list[str]) -> list[Optional[EmbeddingResult]]:
        if not texts:
            return []

        async def _run_batch() -> list[Optional[EmbeddingResult]]:
            results: list[Optional[EmbeddingResult]] = [None] * len(texts)
            async with httpx.AsyncClient() as client:
                sem = asyncio.Semaphore(self._batch_size)

                async def _one(idx: int, text: str):
                    async with sem:
                        try:
                            vec = await self._post_embedding(client, text)
                            self._dimension = len(vec)
                            results[idx] = EmbeddingResult(
                                vector=vec, provider=self.provider_name,
                                model=self._model, dimension=len(vec),
                            )
                        except Exception as e:
                            logger.warning("[Ollama] Erro no item %d do lote: %s", idx, e)

                await asyncio.gather(*(_one(i, t) for i, t in enumerate(texts)))
            return results

        try:
            return asyncio.run(_run_batch())
        except RuntimeError as e:
            logger.error("[Ollama] embed_batch() síncrono chamado dentro de um event loop ativo: %s", e)
            return [None] * len(texts)

    async def health_check(self, timeout: float = 5.0) -> dict:
        start = time.monotonic()
        try:
            async with httpx.AsyncClient() as client:
                vec = await asyncio.wait_for(self._post_embedding(client, "ping"), timeout=timeout)
            latency_ms = (time.monotonic() - start) * 1000
            self._dimension = len(vec)
            return {"ok": True, "detalhe": "online", "dimension": len(vec), "latency_ms": round(latency_ms, 1)}
        except Exception as e:
            latency_ms = (time.monotonic() - start) * 1000
            return {"ok": False, "detalhe": str(e), "dimension": self._dimension, "latency_ms": round(latency_ms, 1)}
