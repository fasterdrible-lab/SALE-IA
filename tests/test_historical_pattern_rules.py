"""
Testes de agent/historical_pattern_rules.py — Bloco 2 / Tarefa 2.1 de
docs/tasks-sales-reasoning-engine-completo.md.

SQLite em memória (mesmo padrão de tests/test_opportunity_link_rules.py).

Run:
    python -m unittest tests.test_historical_pattern_rules -v
"""

import unittest
from unittest.mock import patch

from sqlmodel import SQLModel, create_engine

from api import database
from agent.historical_pattern_rules import obter_historical_pattern_da_opportunity


class ObterHistoricalPatternDaOpportunityTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def _fechar(self, opportunity_id, status, **kwargs):
        if status == "won":
            database.atualizar_status_opportunity(
                opportunity_id, "won", None, value=1000.0, product="Plano Pro", **kwargs,
            )
        else:
            database.atualizar_status_opportunity(
                opportunity_id, "lost", "Sem orçamento", **kwargs,
            )

    def test_opportunity_inexistente_retorna_none(self):
        r = obter_historical_pattern_da_opportunity(999999)
        self.assertIsNone(r)

    def test_opportunity_sem_stage_retorna_none(self):
        opp = database.criar_opportunity(client_id="c1", seller_id="s1")
        r = obter_historical_pattern_da_opportunity(opp["id"])
        self.assertIsNone(r)

    def test_amostra_insuficiente_retorna_none(self):
        opp = database.criar_opportunity(client_id="c1", seller_id="s1", stage="negociacao")
        # so 1 oportunidade no estagio - bem abaixo do minimo de amostra
        r = obter_historical_pattern_da_opportunity(opp["id"])
        self.assertIsNone(r)

    def test_com_amostra_suficiente_retorna_insight_real(self):
        # 40 oportunidades no estagio "negociacao": 32 won, 8 lost (80%)
        for i in range(40):
            opp = database.criar_opportunity(client_id=f"c{i}", seller_id="s1", stage="negociacao")
            if i < 32:
                self._fechar(opp["id"], "won")
            else:
                self._fechar(opp["id"], "lost")

        opp_atual = database.criar_opportunity(client_id="c-atual", seller_id="s1", stage="negociacao")
        r = obter_historical_pattern_da_opportunity(opp_atual["id"])

        self.assertIsNotNone(r)
        self.assertIn("insight", r)
        self.assertEqual(r["evidence"]["valor"], "negociacao")
        # so as 40 fechadas contam — comparar_por_variavel_categorica()
        # (Fase 8) ignora oportunidades ainda abertas no agrupamento
        # won/lost, a atual (opp_atual, status="open") nunca entra.
        self.assertEqual(r["sample"], 40)

    def test_estagio_diferente_do_com_amostra_retorna_none(self):
        for i in range(40):
            opp = database.criar_opportunity(client_id=f"c{i}", seller_id="s1", stage="negociacao")
            self._fechar(opp["id"], "won")

        opp_atual = database.criar_opportunity(client_id="c-atual", seller_id="s1", stage="descoberta")
        r = obter_historical_pattern_da_opportunity(opp_atual["id"])
        self.assertIsNone(r)


if __name__ == "__main__":
    unittest.main()
