"""
Testes — funções de banco e endpoint da Fase 19 (Observabilidade) do
"PROMPT MESTRE — SALE-IA V2".

Cobre:
- api/database.py::latencia_por_feature/custo_medio_por_reuniao/
  custo_medio_por_opportunity/taxa_resposta_recomendacoes (funções
  novas, SQLite em memória, mesmo padrão de tests/test_audit_trail.py).
- GET /admin/observabilidade/metricas (mesmo padrão de
  tests/test_admin_costs_endpoints.py).

Run:
    python -m unittest tests.test_observability_endpoint -v
"""
import logging
import unittest
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

logging.disable(logging.CRITICAL)


class ObservabilityDbFunctionsTest(unittest.TestCase):
    def setUp(self):
        from api import database
        self._database = database
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_latencia_por_feature_ignora_eventos_sem_latencia_ou_falhos(self):
        self._database.registrar_evento_uso_ia(
            feature="realtime.coach", provider="deepseek", model="deepseek-chat",
            input_tokens=10, output_tokens=5, usage_source="provider",
            cost_usd=0.01, latency_ms=200, success=True, meeting_id="m1",
        )
        self._database.registrar_evento_uso_ia(
            feature="realtime.coach", provider="deepseek", model="deepseek-chat",
            input_tokens=10, output_tokens=5, usage_source="provider",
            cost_usd=0.01, latency_ms=400, success=True, meeting_id="m1",
        )
        # falha: nunca chegou a chamar o provedor de verdade -> sem latencia
        self._database.registrar_evento_uso_ia(
            feature="realtime.coach", provider="deepseek", model="deepseek-chat",
            input_tokens=0, output_tokens=0, usage_source="estimated",
            cost_usd=0.0, latency_ms=None, success=False, meeting_id="m1",
        )
        # cache hit: sucesso mas sem latencia real
        self._database.registrar_evento_uso_ia(
            feature="realtime.disc", provider="deepseek", model="deepseek-chat",
            input_tokens=0, output_tokens=0, usage_source="cache",
            cost_usd=0.0, latency_ms=None, success=True, meeting_id="m1",
        )

        resultado = self._database.latencia_por_feature()
        por_feature = {r["feature"]: r for r in resultado}

        self.assertEqual(por_feature["realtime.coach"]["amostra"], 2)
        self.assertEqual(por_feature["realtime.coach"]["media_ms"], 300.0)
        self.assertNotIn("realtime.disc", por_feature)  # só tinha evento sem latência

    def test_custo_medio_por_reuniao_ignora_eventos_sem_meeting_id(self):
        self._database.registrar_evento_uso_ia(
            feature="realtime.coach", provider="deepseek", model="deepseek-chat",
            input_tokens=1, output_tokens=1, usage_source="provider",
            cost_usd=0.10, success=True, meeting_id="m1",
        )
        self._database.registrar_evento_uso_ia(
            feature="realtime.coach", provider="deepseek", model="deepseek-chat",
            input_tokens=1, output_tokens=1, usage_source="provider",
            cost_usd=0.30, success=True, meeting_id="m2",
        )
        self._database.registrar_evento_uso_ia(
            feature="skill.geracao", provider="deepseek", model="deepseek-chat",
            input_tokens=1, output_tokens=1, usage_source="provider",
            cost_usd=999.0, success=True, meeting_id=None,
        )

        resultado = self._database.custo_medio_por_reuniao()
        self.assertEqual(resultado["reunioes_com_custo"], 2)
        self.assertAlmostEqual(resultado["custo_medio_usd"], 0.20, places=6)
        self.assertAlmostEqual(resultado["custo_total_usd"], 0.40, places=6)

    def test_custo_medio_por_opportunity_cruza_meeting_memory(self):
        from api.database import MeetingMemory
        from sqlmodel import Session

        with Session(self._engine) as session:
            session.add(MeetingMemory(meeting_id="m1", opportunity_id=10))
            session.add(MeetingMemory(meeting_id="m2", opportunity_id=10))
            session.add(MeetingMemory(meeting_id="m3", opportunity_id=20))
            session.commit()

        self._database.registrar_evento_uso_ia(
            feature="x", provider="deepseek", model="m", input_tokens=1, output_tokens=1,
            usage_source="provider", cost_usd=0.10, success=True, meeting_id="m1",
        )
        self._database.registrar_evento_uso_ia(
            feature="x", provider="deepseek", model="m", input_tokens=1, output_tokens=1,
            usage_source="provider", cost_usd=0.20, success=True, meeting_id="m2",
        )
        self._database.registrar_evento_uso_ia(
            feature="x", provider="deepseek", model="m", input_tokens=1, output_tokens=1,
            usage_source="provider", cost_usd=0.50, success=True, meeting_id="m3",
        )
        self._database.registrar_evento_uso_ia(
            feature="x", provider="deepseek", model="m", input_tokens=1, output_tokens=1,
            usage_source="provider", cost_usd=999.0, success=True, meeting_id="reuniao-sem-oportunidade",
        )

        resultado = self._database.custo_medio_por_opportunity()
        self.assertEqual(resultado["oportunidades_com_custo"], 2)
        self.assertAlmostEqual(resultado["custo_total_usd"], 0.80, places=6)
        self.assertAlmostEqual(resultado["custo_medio_usd"], 0.40, places=6)

    def test_custo_medio_por_reuniao_sem_dado_retorna_none(self):
        resultado = self._database.custo_medio_por_reuniao()
        self.assertEqual(resultado["reunioes_com_custo"], 0)
        self.assertIsNone(resultado["custo_medio_usd"])

    def test_taxa_resposta_recomendacoes(self):
        c1 = self._database.criar_recommendation_event(
            meeting_id="m1", strategy="A", recommendation="r1", reason="m",
        )
        self._database.criar_recommendation_event(
            meeting_id="m1", strategy="B", recommendation="r2", reason="m",
        )
        self._database.registrar_uso_recommendation_event(c1["id"], seller_action="respondeu")

        resultado = self._database.taxa_resposta_recomendacoes()
        self.assertEqual(resultado["total_recomendacoes"], 2)
        self.assertEqual(resultado["com_resposta_do_vendedor"], 1)
        self.assertEqual(resultado["taxa_resposta"], 0.5)

    def test_taxa_resposta_recomendacoes_sem_dado_retorna_none(self):
        resultado = self._database.taxa_resposta_recomendacoes()
        self.assertEqual(resultado["total_recomendacoes"], 0)
        self.assertIsNone(resultado["taxa_resposta"])


class AdminObservabilidadeEndpointTest(unittest.TestCase):
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

        self._database.registrar_evento_uso_ia(
            feature="realtime.coach", provider="deepseek", model="deepseek-chat",
            input_tokens=100, output_tokens=50, usage_source="provider",
            cost_usd=0.10, latency_ms=300, success=True, fallback_used=False,
            meeting_id="meeting-abc",
        )
        self._database.registrar_evento_uso_ia(
            feature="realtime.disc", provider="openai", model="gpt-4o",
            input_tokens=200, output_tokens=100, usage_source="estimated",
            cost_usd=0.50, latency_ms=None, success=False, fallback_used=True,
            meeting_id="meeting-xyz",
        )

    def test_sem_token_401(self):
        r = self.client.get("/admin/observabilidade/metricas")
        self.assertEqual(r.status_code, 401)

    def test_nao_admin_403(self):
        r = self.client.get("/admin/observabilidade/metricas", headers=self.vendedor_headers)
        self.assertEqual(r.status_code, 403)

    def test_admin_200_formato_e_gaps_documentados(self):
        r = self.client.get("/admin/observabilidade/metricas", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        d = r.json()

        self.assertIn("ai_latency_por_feature", d)
        self.assertIn("recommendation_latency_por_feature", d)
        self.assertIn("cost_per_meeting", d)
        self.assertIn("cost_per_opportunity", d)
        self.assertIn("tokens_por_provider", d)
        self.assertEqual(d["fallback_rate"], 0.5)
        self.assertEqual(d["error_rate"], 0.5)
        self.assertIn("recommendation_acceptance_rate", d)

        # gaps nunca viram numero inventado
        self.assertFalse(d["rag_latency"]["capturado"])
        self.assertFalse(d["recommendation_effectiveness"]["disponivel"])

    def test_recommendation_latency_filtra_so_features_de_recomendacao(self):
        r = self.client.get("/admin/observabilidade/metricas", headers=self.admin_headers)
        d = r.json()
        features = {item["feature"] for item in d["recommendation_latency_por_feature"]}
        self.assertIn("realtime.coach", features)
        self.assertNotIn("realtime.disc", features)


if __name__ == "__main__":
    unittest.main()
