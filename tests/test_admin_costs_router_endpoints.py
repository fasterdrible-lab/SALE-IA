"""
Testes — GET /admin/costs/router/shadow|config (Cost Intelligence Fase 4,
Cost Router em shadow mode).

Mesmo padrao de tests/test_admin_costs_endpoints.py: engine SQLModel
trocado por SQLite em memoria (StaticPool + check_same_thread=False) e
agent.sessao_manager._get_conn mockado pra falhar rapido.

Run:
    python -m unittest tests.test_admin_costs_router_endpoints -v
"""

import logging
import unittest
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

from api import cost_router

logging.disable(logging.CRITICAL)


class AdminCostsRouterEndpointsSuite(unittest.TestCase):
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
        cls.vendedor_token = _main._gerar_token("u1", "vendedor@saleia.app.br", "vendedor")
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

        self._conn_patch = patch(
            "agent.sessao_manager._get_conn", side_effect=RuntimeError("sem banco nos testes")
        )
        self._conn_patch.start()
        self.addCleanup(self._conn_patch.stop)

        cost_router._modo_cache["modo"] = None
        cost_router._modo_cache["ts"] = 0.0

        self._database.registrar_decisao_router(
            feature="realtime.disc", complexidade="simples", modo="normal",
            provider="openai", model_real="gpt-4o", custo_real_usd=0.01,
            model_recomendado="gpt-4o-mini", custo_recomendado_usd=0.002,
            concordou=False,
        )
        self._database.registrar_decisao_router(
            feature="realtime.coach", complexidade="padrao", modo="normal",
            provider="openai", model_real="gpt-4o", custo_real_usd=0.02,
            model_recomendado="gpt-4o", custo_recomendado_usd=0.02,
            concordou=True,
        )

    # ── Autenticacao ──

    def test_shadow_sem_token_401(self):
        r = self.client.get("/admin/costs/router/shadow")
        self.assertEqual(r.status_code, 401)

    def test_shadow_nao_admin_403(self):
        r = self.client.get("/admin/costs/router/shadow", headers=self.vendedor_headers)
        self.assertEqual(r.status_code, 403)

    def test_config_sem_token_401(self):
        r = self.client.get("/admin/costs/router/config")
        self.assertEqual(r.status_code, 401)

    # ── /admin/costs/router/shadow ──

    def test_shadow_200_formato_e_agregados(self):
        r = self.client.get("/admin/costs/router/shadow", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["total_decisoes"], 2)
        self.assertEqual(d["pct_concordancia"], 50.0)
        self.assertAlmostEqual(d["custo_real_usd"], 0.03, places=6)
        self.assertAlmostEqual(d["custo_recomendado_usd"], 0.022, places=6)
        self.assertAlmostEqual(d["economia_potencial_usd"], 0.008, places=6)
        self.assertEqual(d["por_modo"], {"normal": 2})
        self.assertEqual(d["por_complexidade"]["simples"], 1)
        self.assertEqual(d["por_complexidade"]["padrao"], 1)

    def test_shadow_sem_decisoes_nao_quebra(self):
        # engine novo, sem os 2 registros do setUp
        engine2 = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine2)
        with patch.object(self._database, "engine", engine2):
            r = self.client.get("/admin/costs/router/shadow", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["total_decisoes"], 0)
        self.assertIsNone(d["pct_concordancia"])
        self.assertIsNone(d["economia_potencial_pct"])

    # ── /admin/costs/router/config ──

    def test_config_200_formato(self):
        with patch("api.database.obter_orcamento_ia", return_value=None):
            r = self.client.get("/admin/costs/router/config", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn("shadow_habilitado", d)
        self.assertIn("modo_atual", d)
        self.assertEqual(d["modo_atual"], "normal")
        self.assertIn("modelos_economy", d)
        self.assertEqual(d["modelos_economy"]["openai"], "gpt-4o-mini")
        self.assertIn("classificacao", d)


if __name__ == "__main__":
    unittest.main(verbosity=2)
