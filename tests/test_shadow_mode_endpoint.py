"""
Testes — GET /admin/shadow-mode/resumo, Fase 23 ("PROMPT MESTRE —
SALE-IA V2", Teste em Shadow Mode).

Mesmo padrão de tests/test_sales_science_endpoint.py (TestClient real +
SQLite em memória, admin-only).

Run:
    python -m unittest tests.test_shadow_mode_endpoint -v
"""
import logging
import unittest
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

logging.disable(logging.CRITICAL)


class ShadowModeEndpointTest(unittest.TestCase):
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
        r = self.client.get("/admin/shadow-mode/resumo")
        self.assertEqual(r.status_code, 401)

    def test_vendedor_comum_403(self):
        r = self.client.get("/admin/shadow-mode/resumo", headers=self.vendedor_headers)
        self.assertEqual(r.status_code, 403)

    def test_admin_sem_nenhuma_comparacao_200_com_gap_de_quality(self):
        r = self.client.get("/admin/shadow-mode/resumo", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["total_comparacoes"], 0)
        self.assertIsNone(body["agreement_rate"])
        self.assertFalse(body["quality"]["disponivel"])

    def test_admin_com_comparacoes_reais_agrega_corretamente(self):
        for _ in range(3):
            self._database.criar_shadow_mode_comparison(
                meeting_id="m1", usuario_id="s1",
                recomendacao_atual={"type": "question"},
                recomendacao_nova={"next_best_question": "X?"},
                concordancia=True, atual_e_pergunta=True, novo_e_pergunta=True,
                latency_ms=800, cost_usd=0.002, erro=None,
            )
        self._database.criar_shadow_mode_comparison(
            meeting_id="m2", usuario_id="s2",
            recomendacao_atual={"type": "warning"}, recomendacao_nova=None,
            concordancia=None, atual_e_pergunta=None, novo_e_pergunta=None,
            latency_ms=None, cost_usd=None, erro="TimeoutError",
        )

        r = self.client.get("/admin/shadow-mode/resumo", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["total_comparacoes"], 4)
        self.assertEqual(body["comparaveis"], 3)
        self.assertEqual(body["agreement_rate"], 1.0)
        self.assertAlmostEqual(body["error_rate"], 0.25)
        self.assertAlmostEqual(body["cost_usd_total"], 0.006, places=6)


if __name__ == "__main__":
    unittest.main()
