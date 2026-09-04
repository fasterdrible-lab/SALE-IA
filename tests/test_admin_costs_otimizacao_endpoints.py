"""
Testes — GET /admin/costs/otimizacao|anomalias|analise (Cost
Intelligence Fase 5 — ATIVA em produção desde V.1.4.60).

Mesmo padrao das fases anteriores: engine SQLModel trocado por SQLite em
memoria (StaticPool + check_same_thread=False) e
agent.sessao_manager._get_conn mockado pra falhar rapido.

Run:
    python -m unittest tests.test_admin_costs_otimizacao_endpoints -v
"""

import logging
import unittest
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

logging.disable(logging.CRITICAL)


class AdminCostsOtimizacaoEndpointsSuite(unittest.TestCase):
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

        self._database.registrar_decisao_otimizacao(
            tipo="cache_hit", feature="realtime.disc", meeting_id="m1",
            prompt_hash="abc123", custo_real_usd=0.01, economia_estimada_usd=0.01,
            detalhe="teste",
        )
        self._database.registrar_decisao_otimizacao(
            tipo="contexto_truncado", feature="realtime.coach", meeting_id="m1",
            prompt_hash="def456", custo_real_usd=0.02, economia_estimada_usd=0.005,
            detalhe="teste",
        )
        self._database.registrar_evento_uso_ia(
            feature="realtime.coach", provider="deepseek", model="deepseek-chat",
            input_tokens=100, output_tokens=50, usage_source="provider",
            cost_usd=0.01, success=True, latency_ms=300,
        )

    # ── Autenticacao ──

    def test_otimizacao_sem_token_401(self):
        r = self.client.get("/admin/costs/otimizacao")
        self.assertEqual(r.status_code, 401)

    def test_otimizacao_nao_admin_403(self):
        r = self.client.get("/admin/costs/otimizacao", headers=self.vendedor_headers)
        self.assertEqual(r.status_code, 403)

    def test_anomalias_sem_token_401(self):
        r = self.client.get("/admin/costs/anomalias")
        self.assertEqual(r.status_code, 401)

    def test_analise_sem_token_401(self):
        r = self.client.get("/admin/costs/analise")
        self.assertEqual(r.status_code, 401)

    # ── /admin/costs/otimizacao ──

    def test_otimizacao_200_formato_e_agregados(self):
        r = self.client.get("/admin/costs/otimizacao", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["total_decisoes"], 2)
        self.assertAlmostEqual(d["economia_potencial_total_usd"], 0.015, places=6)
        self.assertIn("cache_hit", d["por_tipo"])
        self.assertIn("contexto_truncado", d["por_tipo"])
        self.assertEqual(d["por_tipo"]["cache_hit"]["eventos"], 1)

    def test_otimizacao_expoe_flags_ativo_por_padrao_true(self):
        r = self.client.get("/admin/costs/otimizacao", headers=self.admin_headers)
        d = r.json()
        self.assertEqual(d["ativo"], {"cache": True, "contexto": True, "loop": True})
        self.assertIsNone(d["loop_limite_usd"])  # ninguem configurou limite ainda

    def test_otimizacao_respeita_kill_switch_via_env(self):
        with patch.dict("os.environ", {"OTIMIZACAO_CACHE_ATIVO": "false"}):
            r = self.client.get("/admin/costs/otimizacao", headers=self.admin_headers)
        self.assertFalse(r.json()["ativo"]["cache"])

    # ── /admin/costs/anomalias ──

    def test_anomalias_200_lista_vazia_sem_historico_suficiente(self):
        r = self.client.get("/admin/costs/anomalias", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["anomalias"], [])

    # ── /admin/costs/analise ──

    def test_analise_200_formato(self):
        r = self.client.get("/admin/costs/analise", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn("custo_latencia", d)
        self.assertIn("qualidade_claude_account", d)
        self.assertEqual(len(d["custo_latencia"]), 1)
        self.assertEqual(d["custo_latencia"][0]["provider"], "deepseek")

    # ── /admin/costs/metricas (Fase 6 — contrato consolidado) ──

    def test_metricas_sem_token_401(self):
        r = self.client.get("/admin/costs/metricas")
        self.assertEqual(r.status_code, 401)

    def test_metricas_200_consolida_os_4_blocos(self):
        r = self.client.get("/admin/costs/metricas", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        for chave in ("periodo", "resumo", "router_shadow", "otimizacao", "anomalias"):
            self.assertIn(chave, d)
        self.assertEqual(d["resumo"]["total_eventos"], 1)
        self.assertEqual(d["otimizacao"]["total_decisoes"], 2)
        self.assertIn("ativo", d["otimizacao"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
