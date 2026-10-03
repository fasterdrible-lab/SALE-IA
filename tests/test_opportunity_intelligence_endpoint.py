"""
Testes — GET /opportunities/{id}/intelligence, Fase 22 (Frontend) / bloco
"Opportunity Intelligence" do "PROMPT MESTRE — SALE-IA V2".

Mesmo padrão de tests/test_observability_endpoint.py (TestClient real +
SQLite em memória) e tests/test_tenant_isolation.py (ownership via
_verificar_dono_ou_admin — seller_id da Opportunity é sempre obrigatório,
nunca nulo, então o teste de "sem dono" da Fase 18.1 não se aplica aqui).

Run:
    python -m unittest tests.test_opportunity_intelligence_endpoint -v
"""
import logging
import unittest
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

logging.disable(logging.CRITICAL)


class OpportunityIntelligenceEndpointTest(unittest.TestCase):
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
        cls.dono_token = _main._gerar_token("seller-dono", "dono@saleia.app.br", "vendedor")
        cls.dono_headers = {"Authorization": f"Bearer {cls.dono_token}"}
        cls.outro_token = _main._gerar_token("seller-outro", "outro@saleia.app.br", "vendedor")
        cls.outro_headers = {"Authorization": f"Bearer {cls.outro_token}"}

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

        self.opp = self._database.criar_opportunity(
            client_id="client-1", seller_id="seller-dono", stage="proposta", estimated_value=80000.0,
        )
        self._database.registrar_conhecimento_opportunity(
            self.opp["id"], "pain_points", meeting_id="m1", valor="leads esquecidos", evidence="a fala real",
        )
        self._database.registrar_conhecimento_opportunity(
            self.opp["id"], "champion", meeting_id="m1", valor="Marcos Lima", evidence="a fala real",
        )

    def test_sem_token_401(self):
        r = self.client.get(f"/opportunities/{self.opp['id']}/intelligence")
        self.assertEqual(r.status_code, 401)

    def test_opportunity_inexistente_404(self):
        r = self.client.get("/opportunities/999999/intelligence", headers=self.dono_headers)
        self.assertEqual(r.status_code, 404)

    def test_outro_vendedor_recebe_404_nunca_403(self):
        r = self.client.get(f"/opportunities/{self.opp['id']}/intelligence", headers=self.outro_headers)
        self.assertEqual(r.status_code, 404)

    def test_dono_acessa_200(self):
        r = self.client.get(f"/opportunities/{self.opp['id']}/intelligence", headers=self.dono_headers)
        self.assertEqual(r.status_code, 200)

    def test_admin_acessa_qualquer_opportunity_200(self):
        r = self.client.get(f"/opportunities/{self.opp['id']}/intelligence", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)

    def test_payload_reflete_dado_real_e_gaps_explicitos(self):
        r = self.client.get(f"/opportunities/{self.opp['id']}/intelligence", headers=self.dono_headers)
        body = r.json()

        self.assertEqual(body["opportunity_health"]["stage"], "proposta")
        self.assertEqual(body["opportunity_health"]["status"], "open")
        self.assertEqual(len(body["pain"]), 1)
        self.assertEqual(body["pain"][0]["valor"], "leads esquecidos")
        self.assertEqual(len(body["champion"]), 1)
        self.assertEqual(body["champion"][0]["valor"], "Marcos Lima")
        self.assertEqual(body["impact"], [])  # categoria sem insight nenhum

        self.assertFalse(body["spin_coverage"]["disponivel"])
        self.assertFalse(body["meddpicc"]["disponivel"])
        # Tarefa A6: riscos calculados passam a ser reais (champion sem
        # status MEDDPICC → não confirmado; sem reunião vinculada →
        # NO_NEXT_STEP não avaliado, nunca inventado).
        riscos = body["risks_calculados"]
        self.assertTrue(riscos["disponivel"])
        self.assertIn("NO_CHAMPION", riscos["riscos"])
        self.assertNotIn("NO_NEXT_STEP", riscos["riscos"])
        self.assertEqual({n["risco"] for n in riscos["nao_avaliados"]}, {"COMPETITOR_ADVANTAGE", "NO_NEXT_STEP"})

    def test_opportunity_sem_memoria_nenhuma_ainda_retorna_200_com_listas_vazias(self):
        opp2 = self._database.criar_opportunity(client_id="client-2", seller_id="seller-dono")
        r = self.client.get(f"/opportunities/{opp2['id']}/intelligence", headers=self.dono_headers)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        for campo in ("pain", "impact", "champion", "economic_buyer", "decision_process", "objections", "competitors", "risks_relatados", "next_steps"):
            self.assertEqual(body[campo], [])


if __name__ == "__main__":
    unittest.main()
