"""
Testes unitários — services/embeddings e scripts/reindex_embeddings.

Não exigem rede nem banco de dados real: HTTP (Ollama) e o SDK OpenAI são
mockados; o script de reindexação é testado contra um "banco" falso em
memória. Mesmo padrão de tests/test_smoke.py (stdlib unittest + mock).

Run:
    python -m unittest tests.test_embeddings -v
"""
import json
import logging
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np

logging.disable(logging.CRITICAL)

from services.embeddings import (
    EmbeddingProviderError,
    EmbeddingResult,
    cosine_top_k,
    get_embedding_provider,
    get_fallback_provider,
    is_dimension_compatible,
    reset_provider_cache,
)
from services.embeddings.ollama_provider import OllamaEmbeddingProvider
from services.embeddings.openai_provider import OpenAIEmbeddingProvider


# ─────────────────────────────────────────────────────────
# Helpers puros: cosine_top_k / is_dimension_compatible
# ─────────────────────────────────────────────────────────

class TestCosineTopK(unittest.TestCase):
    def test_ranks_most_similar_first(self):
        query = np.array([1.0, 0.0], dtype=np.float32)
        matrix = np.array([
            [0.0, 1.0],   # ortogonal — sim 0
            [1.0, 0.0],   # idêntico — sim 1
            [0.9, 0.1],   # quase idêntico
        ], dtype=np.float32)
        resultados = cosine_top_k(query, matrix, k=2)
        indices = [idx for idx, _ in resultados]
        self.assertEqual(indices[0], 1)  # o idêntico vem primeiro
        self.assertIn(2, indices)

    def test_k_larger_than_matrix_does_not_crash(self):
        query = np.array([1.0, 0.0], dtype=np.float32)
        matrix = np.array([[1.0, 0.0]], dtype=np.float32)
        resultados = cosine_top_k(query, matrix, k=5)
        self.assertEqual(len(resultados), 1)


class TestDimensionCompatibility(unittest.TestCase):
    def test_none_query_dimension_is_incompatible(self):
        self.assertFalse(is_dimension_compatible(None, {"dim": 768}))

    def test_none_cache_meta_is_incompatible(self):
        self.assertFalse(is_dimension_compatible(768, None))

    def test_empty_cache_meta_is_incompatible(self):
        self.assertFalse(is_dimension_compatible(768, {}))

    def test_matching_dimension_is_compatible(self):
        self.assertTrue(is_dimension_compatible(768, {"dim": 768}))

    def test_mismatched_dimension_is_incompatible(self):
        self.assertFalse(is_dimension_compatible(1536, {"dim": 768}))


# ─────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────

class TestFactory(unittest.TestCase):
    def setUp(self):
        reset_provider_cache()

    def tearDown(self):
        reset_provider_cache()

    def test_default_provider_is_ollama(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EMBEDDING_PROVIDER", None)
            provider = get_embedding_provider(refresh=True)
            self.assertEqual(provider.provider_name, "ollama")

    def test_explicit_openai_provider(self):
        with patch.dict(os.environ, {"EMBEDDING_PROVIDER": "openai"}):
            provider = get_embedding_provider(refresh=True)
            self.assertEqual(provider.provider_name, "openai")

    def test_unknown_provider_raises_explicit_error(self):
        with patch.dict(os.environ, {"EMBEDDING_PROVIDER": "voyage"}):
            with self.assertRaises(EmbeddingProviderError):
                get_embedding_provider(refresh=True)

    def test_singleton_reused_when_config_unchanged(self):
        with patch.dict(os.environ, {"EMBEDDING_PROVIDER": "ollama"}):
            p1 = get_embedding_provider(refresh=True)
            p2 = get_embedding_provider()
            self.assertIs(p1, p2)

    def test_singleton_rebuilt_when_provider_changes(self):
        with patch.dict(os.environ, {"EMBEDDING_PROVIDER": "ollama"}):
            p1 = get_embedding_provider(refresh=True)
        with patch.dict(os.environ, {"EMBEDDING_PROVIDER": "openai"}):
            p2 = get_embedding_provider()
        self.assertIsNot(p1, p2)
        self.assertEqual(p2.provider_name, "openai")

    def test_fallback_none_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EMBEDDING_FALLBACK_PROVIDER", None)
            self.assertIsNone(get_fallback_provider())

    def test_fallback_explicit(self):
        with patch.dict(os.environ, {"EMBEDDING_FALLBACK_PROVIDER": "openai"}):
            fallback = get_fallback_provider()
            self.assertIsNotNone(fallback)
            self.assertEqual(fallback.provider_name, "openai")

    def test_fallback_invalid_value_ignored_not_raised(self):
        with patch.dict(os.environ, {"EMBEDDING_FALLBACK_PROVIDER": "voyage"}):
            self.assertIsNone(get_fallback_provider())


# ─────────────────────────────────────────────────────────
# OllamaEmbeddingProvider (HTTP mockado)
# ─────────────────────────────────────────────────────────

def _fake_ollama_response(status_code=200, embedding=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"embedding": embedding or [0.1, 0.2, 0.3]}
    resp.raise_for_status = MagicMock()
    return resp


class TestOllamaProvider(unittest.IsolatedAsyncioTestCase):
    async def test_embed_async_success(self):
        provider = OllamaEmbeddingProvider(base_url="http://fake:11434", model="embeddinggemma", timeout=5)
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_fake_ollama_response(embedding=[0.1] * 768))):
            resultado = await provider.embed_async("cliente achou caro")
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado.provider, "ollama")
        self.assertEqual(resultado.dimension, 768)
        self.assertEqual(provider.dimension, 768)

    async def test_embed_async_connection_error_returns_none(self):
        import httpx
        provider = OllamaEmbeddingProvider(base_url="http://fake:11434", timeout=1)
        with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=httpx.ConnectError("refused"))):
            resultado = await provider.embed_async("texto")
        self.assertIsNone(resultado)

    async def test_embed_async_model_not_found_returns_none(self):
        provider = OllamaEmbeddingProvider(base_url="http://fake:11434")
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_fake_ollama_response(status_code=404))):
            resultado = await provider.embed_async("texto")
        self.assertIsNone(resultado)

    def test_embed_batch_partial_failure_isolated(self):
        # Método SÍNCRONO de propósito (não async def): embed_batch() usa
        # asyncio.run() internamente, que não pode ser chamado de dentro de
        # um event loop já ativo — este teste precisa rodar fora de um.
        #
        # O item "b" falha em TODAS as tentativas (inclusive retries) para
        # provar isolamento real — uma falha transitória isolada seria
        # absorvida pelo retry (comportamento correto, mas não testaria
        # isolamento entre itens do lote).
        import httpx
        provider = OllamaEmbeddingProvider(base_url="http://fake:11434")

        async def _side_effect(url, json=None, timeout=None, **kwargs):
            if json.get("prompt") == "b":
                raise httpx.ConnectError("boom")
            return _fake_ollama_response(embedding=[0.5] * 768)

        with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=_side_effect)):
            resultados = provider.embed_batch(["a", "b", "c"])

        self.assertEqual(len(resultados), 3)
        self.assertIsNotNone(resultados[0])
        self.assertIsNone(resultados[1])
        self.assertIsNotNone(resultados[2])

    async def test_health_check_reports_dimension(self):
        provider = OllamaEmbeddingProvider(base_url="http://fake:11434")
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_fake_ollama_response(embedding=[0.1] * 384))):
            hc = await provider.health_check(timeout=2)
        self.assertTrue(hc["ok"])
        self.assertEqual(hc["dimension"], 384)

    async def test_health_check_reports_failure_without_raising(self):
        import httpx
        provider = OllamaEmbeddingProvider(base_url="http://fake:11434")
        with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=httpx.ConnectError("refused"))):
            hc = await provider.health_check(timeout=1)
        self.assertFalse(hc["ok"])
        self.assertIn("detalhe", hc)

    def test_never_imports_external_llm_sdks(self):
        import services.embeddings.ollama_provider as mod
        with open(mod.__file__, encoding="utf-8") as f:
            source = f.read()
        for forbidden in ("import openai", "import anthropic", "import google.generativeai"):
            self.assertNotIn(forbidden, source)


# ─────────────────────────────────────────────────────────
# OpenAIEmbeddingProvider (SDK mockado)
# ─────────────────────────────────────────────────────────

class TestOpenAIProvider(unittest.IsolatedAsyncioTestCase):
    def test_embed_without_api_key_raises_config_error(self):
        provider = OpenAIEmbeddingProvider(api_key="", model="text-embedding-3-small")
        with self.assertRaises(EmbeddingProviderError):
            provider.embed("texto")

    def test_embed_success_sync(self):
        provider = OpenAIEmbeddingProvider(api_key="sk-fake", model="text-embedding-3-small")
        fake_resp = MagicMock()
        fake_resp.data = [MagicMock(embedding=[0.1] * 1536)]
        with patch("openai.OpenAI") as MockClient:
            MockClient.return_value.embeddings.create.return_value = fake_resp
            resultado = provider.embed("cliente achou caro")
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado.dimension, 1536)
        self.assertEqual(resultado.provider, "openai")

    async def test_embed_async_success(self):
        provider = OpenAIEmbeddingProvider(api_key="sk-fake", model="text-embedding-3-small")
        fake_resp = MagicMock()
        fake_resp.data = [MagicMock(embedding=[0.2] * 1536)]

        with patch("openai.AsyncOpenAI") as MockClient:
            MockClient.return_value.embeddings.create = AsyncMock(return_value=fake_resp)
            resultado = await provider.embed_async("texto")
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado.dimension, 1536)

    def test_embed_swallows_transient_errors(self):
        provider = OpenAIEmbeddingProvider(api_key="sk-fake")
        with patch("openai.OpenAI") as MockClient:
            MockClient.return_value.embeddings.create.side_effect = RuntimeError("timeout")
            resultado = provider.embed("texto")
        self.assertIsNone(resultado)


# ─────────────────────────────────────────────────────────
# scripts/reindex_embeddings — validação de vetor
# ─────────────────────────────────────────────────────────

class TestReindexValidacaoVetor(unittest.TestCase):
    def setUp(self):
        from scripts.reindex_embeddings import _vetor_valido
        self._vetor_valido = _vetor_valido

    def test_empty_vector_invalid(self):
        self.assertFalse(self._vetor_valido([]))

    def test_all_zero_vector_invalid(self):
        self.assertFalse(self._vetor_valido([0.0, 0.0, 0.0]))

    def test_nan_vector_invalid(self):
        self.assertFalse(self._vetor_valido([0.1, float("nan"), 0.3]))

    def test_normal_vector_valid(self):
        self.assertTrue(self._vetor_valido([0.1, 0.2, 0.3]))


class _FakeCursor:
    def __init__(self, store: list):
        self._store = store
        self._result = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        s = sql.strip()
        if s.upper().startswith("SHOW COLUMNS"):
            self._result = ("ja_existe",)  # sempre "existe" — migração vira no-op
        elif s.upper().startswith("CREATE TABLE") or s.upper().startswith("ALTER TABLE"):
            self._result = None
        elif s.upper().startswith("SELECT COUNT(*)"):
            self._result = (len(self._store),)
        elif s.upper().startswith("SELECT ID, TEXTO"):
            limit, offset = params
            rows = self._store[offset:offset + limit]
            self._result = [
                (r["id"], r["texto"], r["embedding_provider"], r["embedding_model"]) for r in rows
            ]
        elif s.upper().startswith("UPDATE BASE_CONHECIMENTO"):
            embedding_json, provider, model, dim, rid = params
            for r in self._store:
                if r["id"] == rid:
                    r["embedding"] = embedding_json
                    r["embedding_provider"] = provider
                    r["embedding_model"] = model
                    r["embedding_dim"] = dim
        else:
            self._result = None

    def fetchone(self):
        if isinstance(self._result, list):
            return self._result[0] if self._result else None
        return self._result

    def fetchall(self):
        return self._result if isinstance(self._result, list) else []


class _FakeConn:
    def __init__(self, store: list):
        self._store = store

    def cursor(self):
        return _FakeCursor(self._store)

    def commit(self):
        pass

    def close(self):
        pass


class _FakeProvider:
    provider_name = "ollama"
    model_name = "embeddinggemma"

    def embed_batch(self, texts):
        return [
            EmbeddingResult(vector=[0.1, 0.2, 0.3], provider="ollama", model="embeddinggemma", dimension=3)
            for _ in texts
        ]


class TestReindexBaseConhecimentoLogicaMockDB(unittest.TestCase):
    def _store(self):
        return [
            {"id": 1, "texto": "objeção de preço", "embedding": None,
             "embedding_provider": None, "embedding_model": None},
            {"id": 2, "texto": "já indexado", "embedding": "[0.1,0.2,0.3]",
             "embedding_provider": "ollama", "embedding_model": "embeddinggemma"},
        ]

    def test_skips_rows_already_current(self):
        store = self._store()
        conn = _FakeConn(store)
        with patch("agent.sessao_manager._get_conn", return_value=conn), \
             patch("agent.sessao_manager.migrar_colunas_embedding_metadata_base_conhecimento", lambda: None), \
             patch("agent.base_conhecimento.invalidar_cache", lambda: None):
            from scripts.reindex_embeddings import _reindexar_base_conhecimento
            resultado = _reindexar_base_conhecimento(_FakeProvider(), batch_size=10, dry_run=False, limit=None)

        self.assertEqual(resultado.total, 2)
        self.assertEqual(resultado.ja_atual, 1)
        self.assertEqual(resultado.sucesso, 1)
        self.assertEqual(store[0]["embedding_provider"], "ollama")
        self.assertEqual(store[0]["embedding_model"], "embeddinggemma")

    def test_dry_run_never_mutates_store(self):
        store = self._store()
        conn = _FakeConn(store)
        with patch("agent.sessao_manager._get_conn", return_value=conn), \
             patch("agent.sessao_manager.migrar_colunas_embedding_metadata_base_conhecimento", lambda: None), \
             patch("agent.base_conhecimento.invalidar_cache", lambda: None):
            from scripts.reindex_embeddings import _reindexar_base_conhecimento
            resultado = _reindexar_base_conhecimento(_FakeProvider(), batch_size=10, dry_run=True, limit=None)

        self.assertEqual(resultado.sucesso, 1)
        # dry-run não deve ter alterado a linha pendente
        self.assertIsNone(store[0]["embedding_provider"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
