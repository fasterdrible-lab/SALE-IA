"""
Testes — POST /tempo-real, resolucao opcional de usuario_id via JWT

Login na extensao Chrome e opcional: o endpoint precisa continuar
funcionando identico para quem nao loga (anonimo, comportamento atual),
e resolver usuario_id sem quebrar a requisicao quando o JWT falta,
e invalido ou expirado (habilita o fallback pra conta Claude em
agent/multiagente/claude_fallback.py sem risco de derrubar o tempo real).

Run:
    python -m unittest tests.test_tempo_real_auth -v
"""

import unittest
from unittest.mock import AsyncMock, patch


class TempoRealAuthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import api.main as _main  # noqa: dispara setup a nivel de modulo

        cls._patches = []
        for target in (
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
        cls.token = _main._gerar_token("user-tr", "vendedor@saleia.app.br", "vendedor")

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)
        for p in cls._patches:
            p.stop()

    def _post(self, headers=None):
        with patch("agent.sessao_manager.salvar_transcricao_bruta"), \
             patch(
                 "api.processador_tempo_real.processar_fragmento_tempo_real",
                 new=AsyncMock(return_value={"status": "updated"}),
             ) as mock_proc, \
             patch("agent.sessao_manager.salvar_analise"):
            r = self.client.post(
                "/tempo-real",
                json={"transcricao_parcial": "ola tudo bem"},
                headers=headers or {},
            )
        return r, mock_proc

    def test_sem_authorization_segue_anonimo(self):
        r, mock_proc = self._post()
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(mock_proc.call_args.kwargs["usuario_id"])

    def test_com_jwt_valido_resolve_usuario_id(self):
        r, mock_proc = self._post(headers={"Authorization": f"Bearer {self.token}"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(mock_proc.call_args.kwargs["usuario_id"], "user-tr")

    def test_com_jwt_invalido_nao_quebra_fica_anonimo(self):
        r, mock_proc = self._post(headers={"Authorization": "Bearer token-invalido-ou-expirado"})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(mock_proc.call_args.kwargs["usuario_id"])


if __name__ == "__main__":
    unittest.main()
