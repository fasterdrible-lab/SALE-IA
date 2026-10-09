"""
Testes unitários — agent/whisper_local.py (Fase 3 do PROMPT MESTRE — Meetily).

Nunca baixa nem carrega um modelo Whisper real: o pacote `faster_whisper`
é mockado via `sys.modules`, mesmo espírito de tests/test_embeddings.py
(SDKs externos sempre mockados nos testes unitários).

Run:
    python -m unittest tests.test_whisper_local -v
"""
import logging
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

logging.disable(logging.CRITICAL)

import agent.whisper_local as whisper_local


def _fake_faster_whisper_module(model_factory):
    """Cria um módulo fake 'faster_whisper' com WhisperModel = model_factory."""
    mod = types.ModuleType("faster_whisper")
    mod.WhisperModel = model_factory
    return mod


class WhisperLocalModelSingletonTest(unittest.TestCase):
    def setUp(self):
        whisper_local.reset_model_cache()
        self._env_backup = dict(os.environ)

    def tearDown(self):
        whisper_local.reset_model_cache()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_model_loaded_once_when_config_unchanged(self):
        constructor = MagicMock(return_value=MagicMock())
        fake_mod = _fake_faster_whisper_module(constructor)
        with patch.dict(sys.modules, {"faster_whisper": fake_mod}):
            whisper_local._get_model()
            whisper_local._get_model()
        self.assertEqual(constructor.call_count, 1)

    def test_model_reloaded_when_config_changes(self):
        constructor = MagicMock(return_value=MagicMock())
        fake_mod = _fake_faster_whisper_module(constructor)
        with patch.dict(sys.modules, {"faster_whisper": fake_mod}):
            os.environ["WHISPER_LOCAL_MODEL"] = "small"
            whisper_local._get_model()
            os.environ["WHISPER_LOCAL_MODEL"] = "medium"
            whisper_local._get_model()
        self.assertEqual(constructor.call_count, 2)
        _, kwargs = constructor.call_args_list[-1]
        self.assertEqual(constructor.call_args_list[-1][0][0], "medium")

    def test_defaults_when_no_env_configured(self):
        for var in ("WHISPER_LOCAL_MODEL", "WHISPER_LOCAL_DEVICE", "WHISPER_LOCAL_COMPUTE_TYPE"):
            os.environ.pop(var, None)
        model_size, device, compute_type = whisper_local._current_config_key()
        self.assertEqual(model_size, "small")
        self.assertEqual(device, "cpu")
        self.assertEqual(compute_type, "int8")


class WhisperLocalTranscreverTest(unittest.TestCase):
    def setUp(self):
        whisper_local.reset_model_cache()

    def tearDown(self):
        whisper_local.reset_model_cache()

    def test_transcrever_joins_segments_text(self):
        seg1 = MagicMock(text=" Ola, ")
        seg2 = MagicMock(text="tudo bem? ")
        instancia = MagicMock()
        instancia.transcribe.return_value = ([seg1, seg2], MagicMock())
        constructor = MagicMock(return_value=instancia)
        fake_mod = _fake_faster_whisper_module(constructor)

        with patch.dict(sys.modules, {"faster_whisper": fake_mod}):
            texto = whisper_local.transcrever("/tmp/fake.webm", idioma="pt")

        self.assertEqual(texto, "Ola, tudo bem?")
        instancia.transcribe.assert_called_once()
        _, kwargs = instancia.transcribe.call_args
        self.assertEqual(kwargs.get("language"), "pt")
        self.assertTrue(kwargs.get("vad_filter"))

    def test_transcrever_passa_vocabulario_como_initial_prompt(self):
        instancia = MagicMock()
        instancia.transcribe.return_value = ([], MagicMock())
        fake_mod = _fake_faster_whisper_module(MagicMock(return_value=instancia))

        with patch.dict(sys.modules, {"faster_whisper": fake_mod}):
            whisper_local.transcrever("/tmp/fake.webm", prompt="Termos: SALEIA.")

        self.assertEqual(instancia.transcribe.call_args.kwargs.get("initial_prompt"), "Termos: SALEIA.")

    def test_transcrever_empty_segments_returns_empty_string(self):
        instancia = MagicMock()
        instancia.transcribe.return_value = ([], MagicMock())
        constructor = MagicMock(return_value=instancia)
        fake_mod = _fake_faster_whisper_module(constructor)

        with patch.dict(sys.modules, {"faster_whisper": fake_mod}):
            texto = whisper_local.transcrever("/tmp/fake.webm")

        self.assertEqual(texto, "")

    def test_transcrever_propagates_exception_never_falls_back_silently(self):
        # TAREFA 3.11 do PROMPT MESTRE: se o local falhar, mostrar erro —
        # nunca trocar silenciosamente para um provedor pago.
        constructor = MagicMock(side_effect=RuntimeError("modelo indisponivel"))
        fake_mod = _fake_faster_whisper_module(constructor)

        with patch.dict(sys.modules, {"faster_whisper": fake_mod}):
            with self.assertRaises(RuntimeError):
                whisper_local.transcrever("/tmp/fake.webm")


class WhisperLocalHealthCheckTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        whisper_local.reset_model_cache()

    def tearDown(self):
        whisper_local.reset_model_cache()

    async def test_health_check_ok_when_model_loads(self):
        constructor = MagicMock(return_value=MagicMock())
        fake_mod = _fake_faster_whisper_module(constructor)

        with patch.dict(sys.modules, {"faster_whisper": fake_mod}):
            resultado = await whisper_local.health_check()

        self.assertTrue(resultado["ok"])
        self.assertIn("modelo", resultado)

    async def test_health_check_fails_gracefully_never_raises(self):
        constructor = MagicMock(side_effect=RuntimeError("sem memoria"))
        fake_mod = _fake_faster_whisper_module(constructor)

        with patch.dict(sys.modules, {"faster_whisper": fake_mod}):
            resultado = await whisper_local.health_check()

        self.assertFalse(resultado["ok"])
        self.assertIn("sem memoria", resultado["detalhe"])


if __name__ == "__main__":
    unittest.main()
