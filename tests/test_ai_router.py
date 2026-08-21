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
            return {"ok": True}

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

    def test_uses_deepseek_when_configured_first(self):
        def deepseek_caller(*args):
            return {"ok": True}

        def openai_caller(*args):
            return {"ok": True}

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
            return {"resposta": "ok"}

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
            return {"resposta": "fallback"}

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
            return {"resposta": "openai"}

        def anthropic_caller(*args):
            return {"resposta": "anthropic"}

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
            return {"resposta": "openai"}

        def anthropic_caller(*args):
            return {"resposta": "anthropic"}

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
            return {"resposta": "ok"}

        def anthropic_caller(*args):
            return {"resposta": "ok"}

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
            return {"resposta": "ok"}

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
            resultado = ai_router._call_anthropic("system", "user", "fake-key", "claude-sonnet-5", 30)

        self.assertEqual(resultado, {"ok": True})

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


if __name__ == "__main__":
    unittest.main()
