"""
Testes — GET/POST /opportunities, lista e criação de oportunidades
(pré-requisito real pra Opportunity Intelligence ficar utilizável,
sequência do bloco 2 da Fase 22 do "PROMPT MESTRE — SALE-IA V2").

Mesmo padrão de tests/test_opportunity_intelligence_endpoint.py
(TestClient real + SQLite em memória).

Run:
    python -m unittest tests.test_opportunities_list_create_endpoint -v
"""
import logging
import unittest
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

logging.disable(logging.CRITICAL)


class OpportunitiesListCreateEndpointTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import api.main as _main
        from api import database

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
        cls._database = database

        cls.admin_token = _main._gerar_token("admin-1", "admin@saleia.app.br", "admin")
        cls.admin_headers = {"Authorization": f"Bearer {cls.admin_token}"}
        cls.vendedor_a_token = _main._gerar_token("seller-a", "a@saleia.app.br", "vendedor")
        cls.vendedor_a_headers = {"Authorization": f"Bearer {cls.vendedor_a_token}"}
        cls.vendedor_b_token = _main._gerar_token("seller-b", "b@saleia.app.br", "vendedor")
        cls.vendedor_b_headers = {"Authorization": f"Bearer {cls.vendedor_b_token}"}

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)
        for p in cls._patches:
            p.stop()

    def setUp(self):
        self._engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(self._engine)
        self._engine_patch = patch.object(self._database, "engine", self._engine)
        self._engine_patch.start()
        self.addCleanup(self._engine_patch.stop)

    # ── POST /opportunities ──────────────────────────────

    def test_criar_sem_token_401(self):
        r = self.client.post("/opportunities", json={"client_id": "c1"})
        self.assertEqual(r.status_code, 401)

    def test_criar_sem_client_id_400(self):
        r = self.client.post("/opportunities", json={}, headers=self.vendedor_a_headers)
        self.assertEqual(r.status_code, 400)

    def test_criar_estimated_value_invalido_400(self):
        r = self.client.post(
            "/opportunities",
            json={"client_id": "c1", "estimated_value": "abacate"},
            headers=self.vendedor_a_headers,
        )
        self.assertEqual(r.status_code, 400)

    def test_criar_seller_id_vem_sempre_do_token_nunca_do_body(self):
        r = self.client.post(
            "/opportunities",
            json={"client_id": "c1", "seller_id": "seller-outro-forjado", "stage": "descoberta", "estimated_value": 1000},
            headers=self.vendedor_a_headers,
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["seller_id"], "seller-a")
        self.assertEqual(body["client_id"], "c1")
        self.assertEqual(body["stage"], "descoberta")
        self.assertEqual(body["status"], "open")

    # ── GET /opportunities ───────────────────────────────

    def test_listar_sem_token_401(self):
        r = self.client.get("/opportunities")
        self.assertEqual(r.status_code, 401)

    def test_vendedor_so_ve_as_proprias(self):
        self.client.post("/opportunities", json={"client_id": "c1"}, headers=self.vendedor_a_headers)
        self.client.post("/opportunities", json={"client_id": "c2"}, headers=self.vendedor_b_headers)

        r = self.client.get("/opportunities", headers=self.vendedor_a_headers)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["opportunities"][0]["client_id"], "c1")

    def test_admin_ve_todas(self):
        self.client.post("/opportunities", json={"client_id": "c1"}, headers=self.vendedor_a_headers)
        self.client.post("/opportunities", json={"client_id": "c2"}, headers=self.vendedor_b_headers)

        r = self.client.get("/opportunities", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 2)

    def test_lista_vazia_quando_nao_ha_oportunidade(self):
        r = self.client.get("/opportunities", headers=self.vendedor_a_headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"total": 0, "opportunities": []})


if __name__ == "__main__":
    unittest.main()
