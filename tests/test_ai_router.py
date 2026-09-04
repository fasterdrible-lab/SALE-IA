import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from api import ai_router


class AiRouterTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        ai_router.STATE_FILE = Path(self._tmpdir.name) / "ai_provider_order.json"
        ai_router.resetar_estado_ia_para_testes()

    def _provider(self, name, env_key, caller):
        return ai_router.Provider(
            name=name,
            env_keys=(env_key,),
            model_env=f"{name.upper()}_MODEL",
            default_model=f"{name}-model",
            caller=caller,
        )

    def test_uses_first_available_provider(self):
        def openai_caller(*args):
            return {"ok": True}, None

        providers = {
            "openai": self._provider("openai", "OPENAI_API_KEY", openai_caller),
        }

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test", "AI_PROVIDER_ORDER": "openai"}, clear=False):
            with patch.object(ai_router, "PROVIDERS", providers):
                result = ai_router.chamar_ia("system", "user")

        self.assertTrue(result["ok"])
        self.assertEqual(result["_provedor_ia"], "openai")
        self.assertEqual(result["_tentativas_ia"][0]["status"], "success")
        self.assertIn("_custo_estimado_ia", result)
        self.assertGreater(result["_custo_estimado_ia"], 0)
        self.assertEqual(result["_usage_source_ia"], "estimated")

    def test_uses_provider_real_usage_when_caller_returns_it(self):
        from api.cost_engine import ProviderUsage

        def openai_caller(*args):
            return {"ok": True}, ProviderUsage(input_tokens=1000, output_tokens=500)

        providers = {
            "openai": self._provider("openai", "OPENAI_API_KEY", openai_caller),
        }

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test", "AI_PROVIDER_ORDER": "openai"}, clear=False):
            with patch.object(ai_router, "PROVIDERS", providers):
                result = ai_router.chamar_ia("system", "user")

        self.assertEqual(result["_usage_source_ia"], "provider")
        self.assertEqual(result["_tokens_entrada_ia"], 1000)
        self.assertEqual(result["_tokens_saida_ia"], 500)

    def test_uses_deepseek_when_configured_first(self):
        def deepseek_caller(*args):
            return {"ok": True}, None

        def openai_caller(*args):
            return {"ok": True}, None

        providers = {
            "deepseek": self._provider("deepseek", "DEEPSEEK_API_KEY", deepseek_caller),
            "openai": self._provider("openai", "OPENAI_API_KEY", openai_caller),
        }

        env = {
            "DEEPSEEK_API_KEY": "test-deepseek",
            "OPENAI_API_KEY": "test-openai",
            "AI_PROVIDER_ORDER": "deepseek,openai",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch.object(ai_router, "PROVIDERS", providers):
                result = ai_router.chamar_ia("system", "user")

        self.assertEqual(result["_provedor_ia"], "deepseek")
        self.assertEqual(result["_tentativas_ia"][0]["provider"], "deepseek")
        self.assertGreater(result["_custo_estimado_ia"], 0)

    def test_falls_back_after_provider_error(self):
        def openai_caller(*args):
            raise RuntimeError("rate limit for sk-secret-token")

        def anthropic_caller(*args):
            return {"resposta": "ok"}, None

        providers = {
            "openai": self._provider("openai", "OPENAI_API_KEY", openai_caller),
            "anthropic": self._provider("anthropic", "ANTHROPIC_API_KEY", anthropic_caller),
        }

        env = {
            "OPENAI_API_KEY": "test-openai",
            "ANTHROPIC_API_KEY": "test-anthropic",
            "AI_PROVIDER_ORDER": "openai,anthropic",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch.object(ai_router, "PROVIDERS", providers):
                result = ai_router.chamar_ia("system", "user")

        self.assertEqual(result["_provedor_ia"], "anthropic")
        self.assertEqual(result["_tentativas_ia"][0]["status"], "failed")
        self.assertIn("[redacted]", result["_tentativas_ia"][0]["error"])
        self.assertEqual(result["_tentativas_ia"][1]["status"], "success")

    def test_skips_provider_without_api_key(self):
        def openai_caller(*args):
            raise AssertionError("OpenAI should be skipped without a key")

        def anthropic_caller(*args):
            return {"resposta": "fallback"}, None

        providers = {
            "openai": self._provider("openai", "OPENAI_API_KEY", openai_caller),
            "anthropic": self._provider("anthropic", "ANTHROPIC_API_KEY", anthropic_caller),
        }

        env = {
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "test-anthropic",
            "AI_PROVIDER_ORDER": "openai,anthropic",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch.object(ai_router, "PROVIDERS", providers):
                result = ai_router.chamar_ia("system", "user")

        self.assertEqual(result["_provedor_ia"], "anthropic")
        self.assertEqual(result["_tentativas_ia"][0]["status"], "missing_api_key")

    def test_raises_503_when_all_providers_fail(self):
        def failing_caller(*args):
            raise TimeoutError("provider timed out")

        providers = {
            "openai": self._provider("openai", "OPENAI_API_KEY", failing_caller),
            "anthropic": self._provider("anthropic", "ANTHROPIC_API_KEY", failing_caller),
        }

        env = {
            "OPENAI_API_KEY": "test-openai",
            "ANTHROPIC_API_KEY": "test-anthropic",
            "AI_PROVIDER_ORDER": "openai,anthropic",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch.object(ai_router, "PROVIDERS", providers):
                with self.assertRaises(HTTPException) as context:
                    ai_router.chamar_ia("system", "user")

        self.assertEqual(context.exception.status_code, 503)
        self.assertEqual(len(context.exception.detail["provedores_tentados"]), 2)

    def test_rotates_provider_order_and_persists_state(self):
        def openai_caller(*args):
            return {"resposta": "openai"}, None

        def anthropic_caller(*args):
            return {"resposta": "anthropic"}, None

        providers = {
            "openai": self._provider("openai", "OPENAI_API_KEY", openai_caller),
            "anthropic": self._provider("anthropic", "ANTHROPIC_API_KEY", anthropic_caller),
        }

        env = {
            "OPENAI_API_KEY": "test-openai",
            "ANTHROPIC_API_KEY": "test-anthropic",
            "AI_PROVIDER_ORDER": "openai,anthropic",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch.object(ai_router, "PROVIDERS", providers):
                resultado = ai_router.rotacionar_provedor_preferido()

        self.assertEqual(resultado["provedor_preferido"], "anthropic")
        self.assertEqual(resultado["ordem_ia"], ["anthropic", "openai"])
        self.assertTrue(ai_router.STATE_FILE.exists())
        self.assertEqual(ai_router.ordem_provedores(), ["anthropic", "openai"])

    def test_defines_preferred_provider_manually(self):
        def openai_caller(*args):
            return {"resposta": "openai"}, None

        def anthropic_caller(*args):
            return {"resposta": "anthropic"}, None

        providers = {
            "openai": self._provider("openai", "OPENAI_API_KEY", openai_caller),
            "anthropic": self._provider("anthropic", "ANTHROPIC_API_KEY", anthropic_caller),
        }

        env = {
            "OPENAI_API_KEY": "test-openai",
            "ANTHROPIC_API_KEY": "test-anthropic",
            "AI_PROVIDER_ORDER": "openai,anthropic",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch.object(ai_router, "PROVIDERS", providers):
                resultado = ai_router.definir_provedor_preferido("claude")

        self.assertEqual(resultado["provedor_preferido"], "anthropic")
        self.assertEqual(resultado["ordem_ia"], ["anthropic", "openai"])

    def test_ignores_corrupted_order_file_and_uses_env_order(self):
        ai_router.STATE_FILE.write_text("not-json", encoding="utf-8")

        def openai_caller(*args):
            return {"resposta": "ok"}, None

        def anthropic_caller(*args):
            return {"resposta": "ok"}, None

        providers = {
            "openai": self._provider("openai", "OPENAI_API_KEY", openai_caller),
            "anthropic": self._provider("anthropic", "ANTHROPIC_API_KEY", anthropic_caller),
        }

        env = {
            "OPENAI_API_KEY": "test-openai",
            "ANTHROPIC_API_KEY": "test-anthropic",
            "AI_PROVIDER_ORDER": "openai,anthropic",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch.object(ai_router, "PROVIDERS", providers):
                ordem = ai_router.ordem_provedores()

        self.assertEqual(ordem, ["openai", "anthropic"])

    def test_rotation_with_single_provider_keeps_order(self):
        def openai_caller(*args):
            return {"resposta": "ok"}, None

        providers = {
            "openai": self._provider("openai", "OPENAI_API_KEY", openai_caller),
        }

        env = {
            "OPENAI_API_KEY": "test-openai",
            "AI_PROVIDER_ORDER": "openai",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch.object(ai_router, "PROVIDERS", providers):
                resultado = ai_router.rotacionar_provedor_preferido()

        self.assertEqual(resultado["provedor_preferido"], "openai")
        self.assertEqual(resultado["ordem_ia"], ["openai"])


class CallAnthropicContentParsingTest(unittest.TestCase):
    """content[0] nem sempre e texto (ex.: claude-sonnet-5 antepondo um bloco
    de thinking) — _call_anthropic precisa achar o bloco de texto certo."""

    def _fake_block(self, type_, text=None):
        block = type("Block", (), {})()
        block.type = type_
        if text is not None:
            block.text = text
        return block

    def test_skips_non_text_blocks_before_text(self):
        thinking_block = self._fake_block("thinking")  # sem atributo .text
        text_block = self._fake_block("text", text='{"ok": true}')

        fake_response = type("Response", (), {"content": [thinking_block, text_block]})()
        fake_client = type("Client", (), {
            "messages": type("Messages", (), {"create": lambda self, **kw: fake_response})(),
            "__enter__": lambda self: self,
            "__exit__": lambda self, *exc: False,
        })()

        with patch("anthropic.Anthropic", return_value=fake_client):
            resultado, usage = ai_router._call_anthropic("system", "user", "fake-key", "claude-sonnet-5", 30)

        self.assertEqual(resultado, {"ok": True})
        self.assertIsNone(usage)  # fake_response nao tem atributo `usage`

    def test_raises_when_no_text_block_present(self):
        thinking_block = self._fake_block("thinking")

        fake_response = type("Response", (), {"content": [thinking_block]})()
        fake_client = type("Client", (), {
            "messages": type("Messages", (), {"create": lambda self, **kw: fake_response})(),
            "__enter__": lambda self: self,
            "__exit__": lambda self, *exc: False,
        })()

        with patch("anthropic.Anthropic", return_value=fake_client):
            with self.assertRaises(RuntimeError):
                ai_router._call_anthropic("system", "user", "fake-key", "claude-sonnet-5", 30)


class UsageExtractorsTest(unittest.TestCase):
    """Cost Intelligence Fase 1 — extracao de usage real por provider."""

    def _obj(self, **campos):
        return type("Obj", (), campos)()

    def test_usage_from_openai_like_le_prompt_e_completion_tokens(self):
        usage = self._obj(prompt_tokens=100, completion_tokens=50)
        response = self._obj(usage=usage)
        resultado = ai_router._usage_from_openai_like(response)
        self.assertEqual(resultado.input_tokens, 100)
        self.assertEqual(resultado.output_tokens, 50)
        self.assertEqual(resultado.cached_input_tokens, 0)

    def test_usage_from_openai_like_le_cache_do_deepseek(self):
        usage = self._obj(prompt_tokens=100, completion_tokens=50, prompt_cache_hit_tokens=30)
        response = self._obj(usage=usage)
        resultado = ai_router._usage_from_openai_like(response)
        self.assertEqual(resultado.cached_input_tokens, 30)

    def test_usage_from_openai_like_sem_usage_retorna_none(self):
        response = self._obj()
        self.assertIsNone(ai_router._usage_from_openai_like(response))

    def test_usage_from_anthropic_le_input_output_e_cache(self):
        usage = self._obj(input_tokens=200, output_tokens=80, cache_read_input_tokens=20)
        response = self._obj(usage=usage)
        resultado = ai_router._usage_from_anthropic(response)
        self.assertEqual(resultado.input_tokens, 200)
        self.assertEqual(resultado.output_tokens, 80)
        self.assertEqual(resultado.cached_input_tokens, 20)

    def test_usage_from_gemini_le_prompt_e_candidates_token_count(self):
        meta = self._obj(prompt_token_count=300, candidates_token_count=120)
        response = self._obj(usage_metadata=meta)
        resultado = ai_router._usage_from_gemini(response)
        self.assertEqual(resultado.input_tokens, 300)
        self.assertEqual(resultado.output_tokens, 120)

    def test_usage_from_gemini_sem_metadata_retorna_none(self):
        response = self._obj()
        self.assertIsNone(ai_router._usage_from_gemini(response))


class RegistrarEventoUsoIaTest(unittest.TestCase):
    """Confirma que chamar_ia grava um evento de uso a cada chamada (Fase 1)."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        ai_router.STATE_FILE = Path(self._tmpdir.name) / "ai_provider_order.json"
        ai_router.resetar_estado_ia_para_testes()

    def _provider(self, name, env_key, caller):
        return ai_router.Provider(
            name=name, env_keys=(env_key,), model_env=f"{name.upper()}_MODEL",
            default_model=f"{name}-model", caller=caller,
        )

    def test_grava_evento_no_sucesso_com_feature_e_meeting_id(self):
        def openai_caller(*args):
            return {"ok": True}, None

        providers = {"openai": self._provider("openai", "OPENAI_API_KEY", openai_caller)}
        env = {"OPENAI_API_KEY": "test", "AI_PROVIDER_ORDER": "openai"}

        with patch("api.database.registrar_evento_uso_ia") as mock_registrar:
            with patch.dict(os.environ, env, clear=False):
                with patch.object(ai_router, "PROVIDERS", providers):
                    ai_router.chamar_ia("system", "user", feature="teste.feature", meeting_id="m1", usuario_id="u1")

        mock_registrar.assert_called_once()
        kwargs = mock_registrar.call_args.kwargs
        self.assertEqual(kwargs["feature"], "teste.feature")
        self.assertEqual(kwargs["meeting_id"], "m1")
        self.assertEqual(kwargs["usuario_id"], "u1")
        self.assertTrue(kwargs["success"])

    def test_grava_evento_de_falha_quando_todos_os_providers_falham(self):
        def failing_caller(*args):
            raise TimeoutError("timeout")

        providers = {"openai": self._provider("openai", "OPENAI_API_KEY", failing_caller)}
        env = {"OPENAI_API_KEY": "test", "AI_PROVIDER_ORDER": "openai"}

        with patch("api.database.registrar_evento_uso_ia") as mock_registrar:
            with patch.dict(os.environ, env, clear=False):
                with patch.object(ai_router, "PROVIDERS", providers):
                    with self.assertRaises(HTTPException):
                        ai_router.chamar_ia("system", "user", feature="teste.feature")

        mock_registrar.assert_called_once()
        kwargs = mock_registrar.call_args.kwargs
        self.assertFalse(kwargs["success"])
        self.assertEqual(kwargs["provider"], "none")

    def test_falha_ao_gravar_evento_nao_quebra_chamar_ia(self):
        def openai_caller(*args):
            return {"ok": True}, None

        providers = {"openai": self._provider("openai", "OPENAI_API_KEY", openai_caller)}
        env = {"OPENAI_API_KEY": "test", "AI_PROVIDER_ORDER": "openai"}

        with patch("api.database.registrar_evento_uso_ia", side_effect=RuntimeError("banco fora do ar")):
            with patch.dict(os.environ, env, clear=False):
                with patch.object(ai_router, "PROVIDERS", providers):
                    result = ai_router.chamar_ia("system", "user")

        self.assertTrue(result["ok"])


class CostRouterShadowHookTest(unittest.TestCase):
    """Cost Router (Fase 4, shadow mode): o hook em chamar_ia nunca pode
    afetar o resultado real de uma chamada de IA."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        ai_router.STATE_FILE = Path(self._tmpdir.name) / "ai_provider_order.json"
        ai_router.resetar_estado_ia_para_testes()

    def _provider(self, name, env_key, caller):
        return ai_router.Provider(
            name=name, env_keys=(env_key,), model_env=f"{name.upper()}_MODEL",
            default_model=f"{name}-model", caller=caller,
        )

    def test_falha_no_shadow_hook_nao_quebra_chamar_ia(self):
        def openai_caller(*args):
            return {"ok": True}, None

        providers = {"openai": self._provider("openai", "OPENAI_API_KEY", openai_caller)}
        env = {"OPENAI_API_KEY": "test", "AI_PROVIDER_ORDER": "openai"}

        with patch("api.cost_router.avaliar_shadow", side_effect=RuntimeError("router quebrado")):
            with patch.dict(os.environ, env, clear=False):
                with patch.object(ai_router, "PROVIDERS", providers):
                    result = ai_router.chamar_ia("system", "user")

        self.assertTrue(result["ok"])
        self.assertEqual(result["_provedor_ia"], "openai")

    def test_shadow_hook_e_chamado_mas_nao_altera_o_result(self):
        def openai_caller(*args):
            return {"ok": True}, None

        providers = {"openai": self._provider("openai", "OPENAI_API_KEY", openai_caller)}
        env = {"OPENAI_API_KEY": "test", "AI_PROVIDER_ORDER": "openai"}

        with patch("api.cost_router.avaliar_shadow") as mock_shadow:
            with patch.dict(os.environ, env, clear=False):
                with patch.object(ai_router, "PROVIDERS", providers):
                    result = ai_router.chamar_ia("system", "user", feature="teste.feature")

        mock_shadow.assert_called_once()
        kwargs = mock_shadow.call_args.kwargs
        self.assertEqual(kwargs["feature"], "teste.feature")
        self.assertEqual(kwargs["provider"], "openai")
        # o resultado real da IA nao ganha nenhum campo novo por causa do router shadow
        self.assertEqual(set(result.keys()) & {"_router_recomendado", "_router_modo"}, set())


class OtimizacaoShadowHookTest(unittest.TestCase):
    """Otimizacao (Fase 5, shadow mode): o hook em chamar_ia nunca pode
    afetar o resultado real de uma chamada de IA."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        ai_router.STATE_FILE = Path(self._tmpdir.name) / "ai_provider_order.json"
        ai_router.resetar_estado_ia_para_testes()

    def _provider(self, name, env_key, caller):
        return ai_router.Provider(
            name=name, env_keys=(env_key,), model_env=f"{name.upper()}_MODEL",
            default_model=f"{name}-model", caller=caller,
        )

    def test_falha_no_hook_de_otimizacao_nao_quebra_chamar_ia(self):
        def openai_caller(*args):
            return {"ok": True}, None

        providers = {"openai": self._provider("openai", "OPENAI_API_KEY", openai_caller)}
        env = {"OPENAI_API_KEY": "test", "AI_PROVIDER_ORDER": "openai"}

        with patch("api.otimizacao_shadow.avaliar_otimizacoes_shadow", side_effect=RuntimeError("otimizacao quebrada")):
            with patch.dict(os.environ, env, clear=False):
                with patch.object(ai_router, "PROVIDERS", providers):
                    result = ai_router.chamar_ia("system", "user")

        self.assertTrue(result["ok"])

    def test_hook_de_otimizacao_e_chamado_com_os_argumentos_certos(self):
        def openai_caller(*args):
            return {"ok": True}, None

        providers = {"openai": self._provider("openai", "OPENAI_API_KEY", openai_caller)}
        env = {"OPENAI_API_KEY": "test", "AI_PROVIDER_ORDER": "openai"}

        with patch("api.otimizacao_shadow.avaliar_otimizacoes_shadow") as mock_ot:
            with patch.dict(os.environ, env, clear=False):
                with patch.object(ai_router, "PROVIDERS", providers):
                    ai_router.chamar_ia("system", "user", feature="teste.feature", meeting_id="m1")

        mock_ot.assert_called_once()
        kwargs = mock_ot.call_args.kwargs
        self.assertEqual(kwargs["feature"], "teste.feature")
        self.assertEqual(kwargs["meeting_id"], "m1")
        self.assertEqual(kwargs["provider"], "openai")


if __name__ == "__main__":
    unittest.main()
