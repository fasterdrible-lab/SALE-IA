"""
Testes — GET /sales-science/insights, Fase 22 (Frontend) / bloco
"Sales Science" do "PROMPT MESTRE — SALE-IA V2".

Mesmo padrão de tests/test_opportunity_intelligence_endpoint.py
(TestClient real + SQLite em memória). Admin-only, diferente de
GET /opportunities (que é filtrado por vendedor).

Run:
    python -m unittest tests.test_sales_science_endpoint -v
"""
import logging
import unittest
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

logging.disable(logging.CRITICAL)


class SalesScienceEndpointTest(unittest.TestCase):
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
        cls.vendedor_token = _main._gerar_token("seller-a", "a@saleia.app.br", "vendedor")
        cls.vendedor_headers = {"Authorization": f"Bearer {cls.vendedor_token}"}

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

    def test_sem_token_401(self):
        r = self.client.get("/sales-science/insights")
        self.assertEqual(r.status_code, 401)

    def test_vendedor_comum_403(self):
        r = self.client.get("/sales-science/insights", headers=self.vendedor_headers)
        self.assertEqual(r.status_code, 403)

    def test_admin_sem_oportunidade_nenhuma_200_com_gaps(self):
        r = self.client.get("/sales-science/insights", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["amostra_total"], 0)
        self.assertFalse(body["seller_benchmark"]["disponivel"])
        self.assertFalse(body["strategy_effectiveness"]["disponivel"])
        self.assertFalse(body["objection_trends"]["disponivel"])

    def test_admin_com_dado_real_agrega_de_todos_os_vendedores(self):
        for i in range(60):
            status = "won" if i < 40 else "lost"
            stage = "negociacao"
            self._database.criar_opportunity(client_id=f"c{i}", seller_id=f"s{i % 3}", stage=stage)
            opp = self._database.listar_opportunities(client_id=f"c{i}")[0]
            self._database.atualizar_status_opportunity(
                opp["id"], status,
                loss_reason="Sem orcamento" if status == "lost" else None,
                value=1000.0 if status == "won" else None,
                product="Plano Pro" if status == "won" else None,
            )

        r = self.client.get("/sales-science/insights", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["amostra_total"], 60)
        insights_stage = body["win_loss"]["stage"]
        self.assertEqual(len(insights_stage), 1)
        self.assertEqual(insights_stage[0]["sample"], 60)


if __name__ == "__main__":
    unittest.main()
