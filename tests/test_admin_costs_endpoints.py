"""
Testes — GET /admin/costs/* (Cost Intelligence Fase 2).

Cobre autenticacao (401 sem token, 403 nao-admin), formato de resposta de
cada endpoint, exportacao CSV/JSON e validacao de data/formato invalidos.

Nao requer MySQL: `api.database.engine` e trocado por SQLite em memoria
(mesmo padrao de tests/test_cost_aggregation.py) e
`agent.sessao_manager._get_conn` e mockado para falhar rapido — o
enriquecimento de nome/cliente so precisa se provar resiliente a isso
(retorna None, nunca quebra o endpoint).

Run:
    python -m unittest tests.test_admin_costs_endpoints -v
"""

import csv
import io
import logging
import unittest
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

logging.disable(logging.CRITICAL)


class AdminCostsEndpointsSuite(unittest.TestCase):
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
        # StaticPool + check_same_thread=False: o TestClient roda o endpoint
        # numa worker thread diferente desta (setUp) — sem isso, o SQLite
        # :memory: padrao (1 conexao por thread) daria "no such table" porque
        # a worker thread veria um banco em memoria vazio e diferente.
        self._engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(self._engine)
        self._engine_patch = patch.object(self._database, "engine", self._engine)
        self._engine_patch.start()
        self.addCleanup(self._engine_patch.stop)

        # sessao_manager._get_conn sem MySQL disponivel: enriquecimento deve
        # degradar (None) sem quebrar o endpoint — nunca deve demorar 10s
        # tentando conectar de verdade.
        self._conn_patch = patch(
            "agent.sessao_manager._get_conn", side_effect=RuntimeError("sem banco nos testes")
        )
        self._conn_patch.start()
        self.addCleanup(self._conn_patch.stop)

        self._database.registrar_evento_uso_ia(
            feature="realtime.coach", provider="deepseek", model="deepseek-chat",
            input_tokens=100, output_tokens=50, usage_source="provider",
            cost_usd=0.10, success=True, fallback_used=False,
            meeting_id="meeting-abc", usuario_id="user-1",
        )
        self._database.registrar_evento_uso_ia(
            feature="realtime.disc", provider="openai", model="gpt-4o",
            input_tokens=200, output_tokens=100, usage_source="estimated",
            cost_usd=0.50, success=False, fallback_used=True,
            meeting_id="meeting-xyz", usuario_id=None,
        )

    # ── Autenticacao (representativo — mesma _req_admin em todos os endpoints) ──

    def test_resumo_sem_token_401(self):
        r = self.client.get("/admin/costs/resumo")
        self.assertEqual(r.status_code, 401)

    def test_resumo_token_nao_admin_403(self):
        r = self.client.get("/admin/costs/resumo", headers=self.vendedor_headers)
        self.assertEqual(r.status_code, 403)

    # ── /admin/costs/resumo ──

    def test_resumo_admin_200_formato(self):
        r = self.client.get("/admin/costs/resumo", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertAlmostEqual(d["total_usd"], 0.60, places=6)
        self.assertEqual(d["total_eventos"], 2)
        self.assertEqual(d["eventos_falha"], 1)
        self.assertEqual(d["fallback_eventos"], 1)
        self.assertIn("por_provider", d)
        self.assertIn("periodo", d)

    def test_resumo_data_invalida_400(self):
        r = self.client.get("/admin/costs/resumo?date_from=31-12-2026", headers=self.admin_headers)
        self.assertEqual(r.status_code, 400)

    # ── /admin/costs/por-usuario ──

    def test_por_usuario_admin_200_enriquecimento_degrada_sem_quebrar(self):
        r = self.client.get("/admin/costs/por-usuario", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(len(d["usuarios"]), 1)
        self.assertEqual(d["usuarios"][0]["usuario_id"], "user-1")
        self.assertIsNone(d["usuarios"][0]["nome"])  # sem MySQL — degrada, nao quebra
        self.assertIsNotNone(d["anonimo"])
        self.assertAlmostEqual(d["anonimo"]["total_usd"], 0.50, places=6)

    # ── /admin/costs/reunioes ──

    def test_reunioes_admin_200(self):
        r = self.client.get("/admin/costs/reunioes", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(len(d["reunioes"]), 2)
        self.assertEqual(d["reunioes"][0]["meeting_id"], "meeting-xyz")  # maior custo primeiro
        self.assertIn("cliente_nome", d["reunioes"][0])

    # ── /admin/costs/reunioes/{meeting_id} ──

    def test_reuniao_detalhe_admin_200(self):
        r = self.client.get("/admin/costs/reunioes/meeting-abc", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["resumo"]["total_eventos"], 1)
        self.assertEqual(len(d["eventos"]), 1)
        self.assertEqual(d["eventos"][0]["feature"], "realtime.coach")

    def test_reuniao_detalhe_aceita_meeting_id_fora_do_padrao_meet(self):
        """meeting_id tambem carrega chaves como 'knowledge_source:5' (Fase 2 da
        Biblioteca de Inteligencia) — nao pode ser rejeitado por regex de Meet."""
        self._database.registrar_evento_uso_ia(
            feature="knowledge_compiler.extracao", provider="deepseek", model="deepseek-chat",
            input_tokens=10, output_tokens=10, usage_source="provider",
            cost_usd=0.01, success=True, meeting_id="knowledge_source:5",
        )
        r = self.client.get("/admin/costs/reunioes/knowledge_source:5", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["resumo"]["total_eventos"], 1)

    # ── /admin/costs/export ──

    def test_export_json_200(self):
        r = self.client.get("/admin/costs/export?formato=json", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["total"], 2)
        self.assertEqual(len(d["eventos"]), 2)

    def test_export_csv_200_content_type_e_cabecalho(self):
        r = self.client.get("/admin/costs/export?formato=csv", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r.headers["content-type"])
        self.assertIn("attachment", r.headers["content-disposition"])

        linhas = list(csv.reader(io.StringIO(r.text)))
        self.assertEqual(
            linhas[0],
            [
                "criado_em", "meeting_id", "usuario_id", "feature", "provider", "model",
                "input_tokens", "output_tokens", "cached_input_tokens", "usage_source",
                "cost_usd", "latency_ms", "success", "fallback_used",
            ],
        )
        self.assertEqual(len(linhas) - 1, 2)  # 2 eventos + cabecalho

    def test_export_formato_invalido_400(self):
        r = self.client.get("/admin/costs/export?formato=xml", headers=self.admin_headers)
        self.assertEqual(r.status_code, 400)

    def test_export_limit_respeitado(self):
        r = self.client.get("/admin/costs/export?formato=json&limit=1", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
