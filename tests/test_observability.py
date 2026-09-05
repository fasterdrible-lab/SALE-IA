"""
Testes unitários — services/observability (Sprint 1 — Langfuse).

O SDK do Langfuse nunca é chamado de verdade: `langfuse.Langfuse` e
`langfuse.propagate_attributes` são mockados. Mesmo padrão de
tests/test_embeddings.py (stdlib unittest + mock).

Run:
    python -m unittest tests.test_observability -v
"""
import asyncio
import logging
import os
import unittest
from unittest.mock import MagicMock, patch

logging.disable(logging.CRITICAL)

from services.observability import (
    ObservabilityProvider,
    ObservabilityProviderError,
    get_current_observation,
    get_observability_provider,
    reset_provider_cache,
)
from services.observability.noop_provider import NoOpObservabilityProvider
from services.observability.langfuse_provider import LangfuseObservabilityProvider
from services.observability.provider import _current_observation


def _clear_env(*names):
    return patch.dict(os.environ, {n: "" for n in names}, clear=False)


class NoOpProviderTest(unittest.TestCase):
    def setUp(self):
        reset_provider_cache()
        self.addCleanup(reset_provider_cache)
        # ContextVar e global ao contexto do thread de teste — sem isto, um
        # start_trace/start_span sem end_* correspondente (ou rodando fora de
        # ordem) vaza pro proximo teste (achado real: test_capture_transcript_
        # flag_controls_raw_text_presence nao fecha a trace que abre).
        self.addCleanup(_current_observation.set, None)

    def test_disabled_by_default_returns_noop(self):
        with patch.dict(os.environ, {"OBSERVABILITY_ENABLED": "false"}, clear=False):
            reset_provider_cache()
            provider = get_observability_provider()
        self.assertIsInstance(provider, NoOpObservabilityProvider)

    def test_noop_never_imports_langfuse(self):
        # Remove o modulo do cache pra garantir que o teste detecta um import real.
        import sys
        sys.modules.pop("langfuse", None)
        with patch.dict(os.environ, {"OBSERVABILITY_ENABLED": "false"}, clear=False):
            reset_provider_cache()
            provider = get_observability_provider()
            provider.start_trace(name="x")
            provider.record_generation(feature="f", provider="p", model="m", success=True)
        self.assertNotIn("langfuse", sys.modules)

    def test_all_methods_accept_garbage_without_raising(self):
        provider = NoOpObservabilityProvider()
        trace = provider.start_trace(name="t", meeting_id=None, usuario_id=None, input=None, metadata=None)
        span = provider.start_span(name="s", parent=None, meeting_id=None, input=None, metadata=None)
        provider.record_generation(feature="f", provider="p", model=None, success=False, error="boom")
        provider.record_retrieval(source="x", query="", result_count=0, preview=None)
        provider.record_score(name="n", value=0.0, comment=None)
        provider.end_span(span, output=None, success=False, error="boom")
        provider.end_trace(trace, output=None, success=False, error="boom")

    def test_handles_pop_context_on_end(self):
        provider = NoOpObservabilityProvider()
        trace = provider.start_trace(name="t")
        self.assertIs(get_current_observation(), trace)
        provider.end_trace(trace)
        self.assertIsNone(get_current_observation())

    def test_nesting_under_concurrent_gather_never_interferes(self):
        # Smoke test de concorrencia real (nao NoOp-specifico, mas prova que
        # o wrapper roda sob asyncio.gather sem excecao/cross-talk).
        provider = NoOpObservabilityProvider()

        async def agente(nome):
            span = provider.start_span(name=f"agent.{nome}")
            atual = get_current_observation()
            self.assertIs(atual, span)
            await asyncio.sleep(0.001)
            # Ainda deve ser o mesmo span apos o await (contexto isolado por task)
            self.assertIs(get_current_observation(), span)
            provider.end_span(span)
            return nome

        async def main():
            return await asyncio.gather(
                agente("coach"), agente("disc"), agente("finance"), agente("closer"),
            )

        resultado = asyncio.run(main())
        self.assertEqual(resultado, ["coach", "disc", "finance", "closer"])


class FactoryTest(unittest.TestCase):
    def setUp(self):
        reset_provider_cache()
        self.addCleanup(reset_provider_cache)

    def test_unknown_provider_with_enabled_raises(self):
        with patch.dict(os.environ, {
            "OBSERVABILITY_ENABLED": "true",
            "OBSERVABILITY_PROVIDER": "algo_desconhecido",
        }, clear=False):
            reset_provider_cache()
            with self.assertRaises(ObservabilityProviderError):
                get_observability_provider()

    def test_singleton_stable_for_same_config(self):
        with patch.dict(os.environ, {"OBSERVABILITY_ENABLED": "false"}, clear=False):
            reset_provider_cache()
            p1 = get_observability_provider()
            p2 = get_observability_provider()
        self.assertIs(p1, p2)

    def test_refresh_rebuilds_instance(self):
        with patch.dict(os.environ, {"OBSERVABILITY_ENABLED": "false"}, clear=False):
            reset_provider_cache()
            p1 = get_observability_provider()
            p2 = get_observability_provider(refresh=True)
        self.assertIsNot(p1, p2)

    def test_enabled_langfuse_with_keys_builds_langfuse_provider(self):
        with patch.dict(os.environ, {
            "OBSERVABILITY_ENABLED": "true",
            "OBSERVABILITY_PROVIDER": "langfuse",
            "LANGFUSE_PUBLIC_KEY": "pk-test",
            "LANGFUSE_SECRET_KEY": "sk-test",
        }, clear=False):
            with patch("langfuse.Langfuse") as MockLangfuse:
                MockLangfuse.return_value = MagicMock()
                reset_provider_cache()
                provider = get_observability_provider()
        self.assertIsInstance(provider, LangfuseObservabilityProvider)


class LangfuseProviderTest(unittest.TestCase):
    def setUp(self):
        self.addCleanup(_current_observation.set, None)

    def _env(self, **extra):
        base = {
            "OBSERVABILITY_ENABLED": "true",
            "LANGFUSE_PUBLIC_KEY": "pk-test",
            "LANGFUSE_SECRET_KEY": "sk-test",
        }
        base.update(extra)
        return patch.dict(os.environ, base, clear=False)

    def test_missing_keys_raises_config_error(self):
        with patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""}, clear=False):
            with self.assertRaises(ObservabilityProviderError):
                LangfuseObservabilityProvider()

    def test_start_trace_calls_sdk_with_expected_kwargs(self):
        with self._env():
            with patch("langfuse.Langfuse") as MockLangfuse, patch("langfuse.propagate_attributes") as mock_prop:
                mock_client = MagicMock()
                MockLangfuse.return_value = mock_client
                provider = LangfuseObservabilityProvider()
                trace = provider.start_trace(name="tempo_real_cycle", meeting_id="m1", usuario_id="u1",
                                              input={"transcript_chars": 10})

        mock_prop.assert_called_once()
        _, kwargs = mock_prop.call_args
        self.assertEqual(kwargs["user_id"], "u1")
        self.assertEqual(kwargs["session_id"], "m1")
        mock_client.start_observation.assert_called_once()
        _, call_kwargs = mock_client.start_observation.call_args
        self.assertEqual(call_kwargs["name"], "tempo_real_cycle")
        self.assertEqual(call_kwargs["as_type"], "span")
        self.assertIsNotNone(trace._native)

    def test_record_generation_sets_usage_and_cost_details(self):
        with self._env():
            with patch("langfuse.Langfuse") as MockLangfuse, patch("langfuse.propagate_attributes"):
                mock_client = MagicMock()
                mock_span = MagicMock()
                mock_generation = MagicMock()
                mock_client.start_observation.return_value = mock_span
                mock_span.start_observation.return_value = mock_generation
                MockLangfuse.return_value = mock_client

                provider = LangfuseObservabilityProvider()
                trace = provider.start_trace(name="tempo_real_cycle", meeting_id="m1", usuario_id="u1")
                provider.record_generation(
                    feature="realtime.disc", provider="deepseek", model="deepseek-chat",
                    prompt_tokens=100, completion_tokens=50, cost_usd=0.01,
                    latency_ms=250, success=True, meeting_id="m1", usuario_id="u1",
                )
                provider.end_trace(trace, success=True)

        mock_span.start_observation.assert_called_once()
        _, gen_kwargs = mock_span.start_observation.call_args
        self.assertEqual(gen_kwargs["as_type"], "generation")
        self.assertEqual(gen_kwargs["model"], "deepseek-chat")
        mock_generation.update.assert_called_once()
        _, update_kwargs = mock_generation.update.call_args
        self.assertEqual(update_kwargs["usage_details"], {"input": 100, "output": 50})
        self.assertEqual(update_kwargs["cost_details"]["total"], 0.01)
        mock_generation.end.assert_called_once()

    def test_record_generation_without_current_observation_is_skipped(self):
        with self._env():
            with patch("langfuse.Langfuse") as MockLangfuse, patch("langfuse.propagate_attributes"):
                mock_client = MagicMock()
                MockLangfuse.return_value = mock_client
                provider = LangfuseObservabilityProvider()
                # Sem start_trace/start_span antes — fora do ciclo instrumentado.
                provider.record_generation(feature="f", provider="p", model="m", success=True)

        mock_client.start_observation.assert_not_called()

    def test_sdk_exception_is_swallowed_never_raises(self):
        with self._env():
            with patch("langfuse.Langfuse") as MockLangfuse, patch("langfuse.propagate_attributes") as mock_prop:
                mock_prop.side_effect = RuntimeError("rede fora do ar")
                mock_client = MagicMock()
                MockLangfuse.return_value = mock_client
                provider = LangfuseObservabilityProvider()
                try:
                    trace = provider.start_trace(name="t", meeting_id="m1")
                    provider.record_generation(feature="f", provider="p", model="m", success=True)
                    provider.record_retrieval(source="s", query="q", result_count=1)
                    provider.record_score(name="n", value=1.0)
                    provider.end_trace(trace)
                except Exception as exc:  # pragma: no cover - falha do teste se propagar
                    self.fail(f"LangfuseObservabilityProvider propagou excecao: {exc}")

    def test_capture_transcript_flag_controls_raw_text_presence(self):
        # A decisao de incluir texto bruto e do CHAMADOR (api/main.py), nao
        # do provider — o provider so registra o que recebe em `input`.
        # Aqui confirmamos que o provider passa `input` adiante sem alteracao.
        with self._env():
            with patch("langfuse.Langfuse") as MockLangfuse, patch("langfuse.propagate_attributes"):
                mock_client = MagicMock()
                MockLangfuse.return_value = mock_client
                provider = LangfuseObservabilityProvider()
                provider.start_trace(name="t", meeting_id="m1", input={"transcricao_parcial": "texto sensivel"})

        _, kwargs = mock_client.start_observation.call_args
        self.assertEqual(kwargs["input"], {"transcricao_parcial": "texto sensivel"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
