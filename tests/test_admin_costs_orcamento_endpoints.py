"""
Testes — GET/PATCH /admin/costs/orcamento|projecao|margem|planos/{p}/preco|
auditoria (Cost Intelligence Fase 3, Budget Guard).

Mesmo padrao de tests/test_admin_costs_endpoints.py: engine SQLModel
trocado por SQLite em memoria (StaticPool + check_same_thread=False, pois
o TestClient roda o endpoint numa worker thread diferente do teste) e
agent.sessao_manager._get_conn mockado pra falhar rapido (o
enriquecimento de nome/plano/usuarios-ativos deve degradar sem quebrar).

Run:
    python -m unittest tests.test_admin_costs_orcamento_endpoints -v
"""

import logging
import unittest
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

from agent import alertas

logging.disable(logging.CRITICAL)


class AdminCostsOrcamentoEndpointsSuite(unittest.TestCase):
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

        alertas._last_alerta.clear()

        self._database.registrar_evento_uso_ia(
            feature="realtime.coach", provider="deepseek", model="deepseek-chat",
            input_tokens=100, output_tokens=50, usage_source="provider",
            cost_usd=10.0, success=True, usuario_id="user-1",
        )

    # ── Autenticacao ──

    def test_orcamento_sem_token_401(self):
        r = self.client.get("/admin/costs/orcamento")
        self.assertEqual(r.status_code, 401)

    def test_orcamento_nao_admin_403(self):
        r = self.client.get("/admin/costs/orcamento", headers=self.vendedor_headers)
        self.assertEqual(r.status_code, 403)

    # ── /admin/costs/orcamento ──

    def test_orcamento_sem_configuracao(self):
        r = self.client.get("/admin/costs/orcamento", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIsNone(d["orcamento"])
        self.assertIsNone(d["pct_usado"])
        self.assertAlmostEqual(d["gasto_mes_atual_usd"], 10.0, places=6)

    def test_definir_orcamento_e_conferir_pct_usado(self):
        r = self.client.patch("/admin/costs/orcamento", json={"limite_mensal_usd": 20.0}, headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["limite_mensal_usd"], 20.0)

        r2 = self.client.get("/admin/costs/orcamento", headers=self.admin_headers)
        d = r2.json()
        self.assertEqual(d["orcamento"]["limite_mensal_usd"], 20.0)
        self.assertAlmostEqual(d["pct_usado"], 50.0, places=1)  # 10 de 20 = 50%

    # ── /admin/costs/projecao ──

    def test_projecao_200_formato(self):
        r = self.client.get("/admin/costs/projecao", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        for campo in ("mes", "dias_decorridos", "dias_no_mes", "gasto_atual_usd", "projecao_fim_mes_usd"):
            self.assertIn(campo, d)

    # ── /admin/costs/planos/{plano}/preco + /admin/costs/margem ──

    def test_definir_preco_plano_e_margem_reflete(self):
        r = self.client.patch("/admin/costs/planos/pro/preco", json={"preco_mensal_brl": 199.0}, headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)

        r2 = self.client.get("/admin/costs/margem", headers=self.admin_headers)
        self.assertEqual(r2.status_code, 200)
        d = r2.json()
        self.assertIn("taxa_usd_brl", d)
        planos = {p["plano"]: p for p in d["planos"]}
        self.assertIn("pro", planos)
        self.assertEqual(planos["pro"]["preco_mensal_brl"], 199.0)
        # sem MySQL nos testes, obter_usuarios_ativos_por_plano degrada pra {} —
        # 0 usuarios ativos, mas o endpoint nao deve quebrar
        self.assertEqual(planos["pro"]["usuarios_ativos"], 0)

    def test_margem_sem_preco_configurado_retorna_null(self):
        r = self.client.get("/admin/costs/margem", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        # usuario-1 nao tem plano resolvido (sem MySQL) -> cai em "sem_plano", sem preco
        planos = {p["plano"]: p for p in d["planos"]}
        for info in planos.values():
            if info["preco_mensal_brl"] is None:
                self.assertIsNone(info["margem_brl"])
                self.assertIsNone(info["receita_brl"])

    # ── /admin/costs/auditoria ──

    def test_auditoria_lista_mudancas(self):
        self.client.patch("/admin/costs/orcamento", json={"limite_mensal_usd": 30.0}, headers=self.admin_headers)
        self.client.patch("/admin/costs/planos/enterprise/preco", json={"preco_mensal_brl": 999.0}, headers=self.admin_headers)

        r = self.client.get("/admin/costs/auditoria", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        eventos = r.json()["eventos"]
        self.assertEqual(len(eventos), 2)
        tipos = {e["tipo"] for e in eventos}
        self.assertEqual(tipos, {"orcamento", "preco_plano"})
        self.assertTrue(all(e["usuario_email"] == "admin@saleia.app.br" for e in eventos))


if __name__ == "__main__":
    unittest.main(verbosity=2)
