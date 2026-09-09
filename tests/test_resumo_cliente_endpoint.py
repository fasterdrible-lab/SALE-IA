"""
Testes — GET /clientes/resumo-reuniao/{meeting_id} (Sales Brain, gap da
Tarefa 4.3: card "Resumo do Cliente" na tela de detalhe da reunião no
Dashboard — nunca em cenario.html, que é a tela do próprio cliente).

Não requer MySQL: `agent.client_intelligence.buscar_cliente_por_reuniao`/
`obter_cliente` são mockados (mesmo padrão de tests/test_admin_costs_endpoints.py
para o TestClient).

Run:
    python -m unittest tests.test_resumo_cliente_endpoint -v
"""

import logging
import unittest
from unittest.mock import patch

logging.disable(logging.CRITICAL)


class ResumoClienteEndpointSuite(unittest.TestCase):
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

        cls.token = _main._gerar_token("u1", "vendedor@saleia.app.br", "vendedor")
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)
        for p in cls._patches:
            p.stop()

    def test_sem_token_retorna_401(self):
        r = self.client.get("/clientes/resumo-reuniao/m1")
        self.assertEqual(r.status_code, 401)

    def test_reuniao_sem_cliente_vinculado(self):
        with patch("agent.client_intelligence.buscar_cliente_por_reuniao", return_value=None):
            r = self.client.get("/clientes/resumo-reuniao/m-sem-cliente", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"vinculado": False})

    def test_reuniao_com_cliente_vinculado_retorna_perfil(self):
        cliente_fake = {
            "id": "c1",
            "nome": "Cliente Teste",
            "disc_profile": "D",
            "score_medio": 72.5,
            "objecoes_recorrentes": ["Preço alto"],
            "dores_recorrentes": ["Sem visibilidade"],
            "reunioes": [{"meeting_id": "m1", "score": 70}, {"meeting_id": "m2", "score": 75}],
        }
        with patch("agent.client_intelligence.buscar_cliente_por_reuniao", return_value="c1"), \
             patch("agent.client_intelligence.obter_cliente", return_value=cliente_fake):
            r = self.client.get("/clientes/resumo-reuniao/m2", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["vinculado"])
        self.assertEqual(body["nome"], "Cliente Teste")
        self.assertEqual(len(body["reunioes"]), 2)

    def test_cliente_vinculado_mas_perfil_nao_encontrado(self):
        with patch("agent.client_intelligence.buscar_cliente_por_reuniao", return_value="c-orfao"), \
             patch("agent.client_intelligence.obter_cliente", return_value=None):
            r = self.client.get("/clientes/resumo-reuniao/m3", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"vinculado": False})


if __name__ == "__main__":
    unittest.main()
