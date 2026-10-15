"""
Testes — /admin/transcricao/* e /audio-transcricao, cobrindo o novo
provedor "whisper_local" (Fase 3 do PROMPT MESTRE — Meetily).

Nunca escreve no .env real: api.main._ler_env / _salvar_env_key são
sempre mockados aqui (a implementação real grava no arquivo .env do
disco — ver api/main.py::_salvar_env_key). Nunca baixa/carrega um modelo
Whisper real: agent.whisper_local é sempre mockado.

Run:
    python -m unittest tests.test_transcricao_config -v
"""
import base64
import logging
import unittest
from unittest.mock import AsyncMock, patch

logging.disable(logging.CRITICAL)


class TranscricaoConfigSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import api.main as _main

        cls._patches = []
        for target in (
            "api.database.criar_tabelas",
            "agent.sessao_manager.criar_tabela_sessoes",
            "agent.sessao_manager.criar_tabela_usuarios",
            "agent.visual_scenario.criar_tabela_visual_scenarios",
            "agent.sales_memory.criar_tabela_sales_memories",
        ):
            try:
                p = patch(target)
                p.start()
                cls._patches.append(p)
            except Exception:
                pass

        from fastapi.testclient import TestClient
        cls._ctx = TestClient(_main.app)
        cls.client = cls._ctx.__enter__()
        cls._main = _main

        cls.admin_token = _main._gerar_token("admin-1", "admin@saleia.app.br", "admin")
        cls.admin_headers = {"Authorization": f"Bearer {cls.admin_token}"}

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)
        for p in cls._patches:
            p.stop()

    def test_get_config_lists_whisper_local_sem_exigir_chave(self):
        with patch.object(self._main, "_ler_env", return_value={"TRANSCRICAO_PROVEDOR": "whisper"}):
            r = self.client.get("/admin/transcricao/config", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        provedores = {p["id"]: p for p in r.json()["provedores"]}
        self.assertIn("whisper_local", provedores)
        self.assertTrue(provedores["whisper_local"]["tem_chave"])
        self.assertFalse(provedores["whisper_local"]["ativo"])

    def test_ativar_whisper_local_nao_exige_chave(self):
        with patch.object(self._main, "_ler_env", return_value={}), \
             patch.object(self._main, "_salvar_env_key") as mock_salvar:
            r = self.client.post(
                "/admin/transcricao/config",
                json={"provedor": "whisper_local"},
                headers=self.admin_headers,
            )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        mock_salvar.assert_called_once_with("TRANSCRICAO_PROVEDOR", "whisper_local")

    def test_ativar_groq_sem_chave_continua_bloqueado(self):
        # Regressao: providers com env_key ainda devem exigir a chave —
        # a mudanca pra whisper_local nao deve afrouxar isso.
        with patch.object(self._main, "_ler_env", return_value={}):
            r = self.client.post(
                "/admin/transcricao/config",
                json={"provedor": "groq"},
                headers=self.admin_headers,
            )
        self.assertEqual(r.status_code, 400)

    def test_testar_whisper_local_chama_health_check(self):
        fake_health = AsyncMock(return_value={"ok": True, "detalhe": "Modelo 'small' carregado.", "modelo": "small"})
        with patch("agent.whisper_local.health_check", fake_health):
            r = self.client.post(
                "/admin/transcricao/teste",
                json={"provedor": "whisper_local"},
                headers=self.admin_headers,
            )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["modelo"], "small")
        fake_health.assert_awaited_once()

    def test_audio_transcricao_dispatches_to_whisper_local(self):
        audio_bytes = b"0" * 1024  # so precisa passar do limiar de 512 bytes
        payload_b64 = "data:audio/webm;base64," + base64.b64encode(audio_bytes).decode()

        with patch("agent.whisper_local.transcrever", return_value="ola mundo") as fake_transcrever, \
             patch.dict("os.environ", {"TRANSCRICAO_PROVEDOR": "whisper_local", "TRANSCRICAO_TEMPO_REAL_ATIVA": "true"}):
            r = self.client.post(
                "/audio-transcricao",
                json={"audio_base64": payload_b64, "mime_type": "audio/webm", "meeting_id": "default"},
            )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["texto"], "ola mundo")
        self.assertEqual(body["provedor"], "whisper_local")
        fake_transcrever.assert_called_once()


if __name__ == "__main__":
    unittest.main()
