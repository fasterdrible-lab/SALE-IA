"""
Testes de agent/opportunity_link_rules.py — Bloco 3 / Tarefa 3.1 de
docs/tasks-sales-reasoning-engine-completo.md.

escolher_opportunity_para_vincular() é pura. vincular_automaticamente_
se_possivel() usa SQLite em memória (mesmo padrão de tests/
test_audit_trail.py) e mocka agent.client_intelligence.
buscar_cliente_por_reuniao() (usa pymysql direto, sem fallback SQLite).

Run:
    python -m unittest tests.test_opportunity_link_rules -v
"""

import unittest
from unittest.mock import patch

from sqlmodel import SQLModel, create_engine

from api import database
from agent.opportunity_link_rules import (
    escolher_opportunity_para_vincular,
    vincular_automaticamente_se_possivel,
)


class EscolherOpportunityParaVincularTest(unittest.TestCase):
    def test_exatamente_uma_candidata_retorna_id(self):
        r = escolher_opportunity_para_vincular([{"id": 42}])
        self.assertEqual(r, 42)

    def test_nenhuma_candidata_retorna_none(self):
        r = escolher_opportunity_para_vincular([])
        self.assertIsNone(r)

    def test_duas_ou_mais_candidatas_retorna_none_ambiguidade(self):
        r = escolher_opportunity_para_vincular([{"id": 1}, {"id": 2}])
        self.assertIsNone(r)


class VincularAutomaticamenteSePossivelTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_sem_meeting_memory_retorna_none(self):
        with patch("agent.client_intelligence.buscar_cliente_por_reuniao", return_value="client-1"):
            r = vincular_automaticamente_se_possivel("meeting-inexistente")
        self.assertIsNone(r)

    def test_ja_vinculada_retorna_id_existente_sem_chamar_cliente(self):
        database.salvar_meeting_memory("m1", usuario_id="seller-1")
        database.vincular_meeting_opportunity("m1", 99)
        cliente_mock = patch("agent.client_intelligence.buscar_cliente_por_reuniao")
        mock = cliente_mock.start()
        self.addCleanup(cliente_mock.stop)
        try:
            r = vincular_automaticamente_se_possivel("m1")
        finally:
            cliente_mock.stop()
        self.assertEqual(r, 99)
        mock.assert_not_called()

    def test_sem_cliente_identificado_retorna_none(self):
        database.salvar_meeting_memory("m2", usuario_id="seller-1")
        with patch("agent.client_intelligence.buscar_cliente_por_reuniao", return_value=None):
            r = vincular_automaticamente_se_possivel("m2")
        self.assertIsNone(r)

    def test_com_uma_oportunidade_aberta_vincula_e_retorna_id(self):
        database.salvar_meeting_memory("m3", usuario_id="seller-1")
        opp = database.criar_opportunity(client_id="client-3", seller_id="seller-1", stage="descoberta")
        with patch("agent.client_intelligence.buscar_cliente_por_reuniao", return_value="client-3"):
            r = vincular_automaticamente_se_possivel("m3")
        self.assertEqual(r, opp["id"])
        memoria = database.obter_meeting_memory("m3")
        self.assertEqual(memoria["opportunity_id"], opp["id"])

    def test_com_duas_oportunidades_abertas_nunca_vincula(self):
        database.salvar_meeting_memory("m4", usuario_id="seller-1")
        database.criar_opportunity(client_id="client-4", seller_id="seller-1")
        database.criar_opportunity(client_id="client-4", seller_id="seller-1")
        with patch("agent.client_intelligence.buscar_cliente_por_reuniao", return_value="client-4"):
            r = vincular_automaticamente_se_possivel("m4")
        self.assertIsNone(r)
        memoria = database.obter_meeting_memory("m4")
        self.assertIsNone(memoria["opportunity_id"])

    def test_oportunidade_fechada_nunca_conta_como_candidata(self):
        database.salvar_meeting_memory("m5", usuario_id="seller-1")
        opp = database.criar_opportunity(client_id="client-5", seller_id="seller-1")
        database.atualizar_status_opportunity(
            opp["id"], "won", None, value=100.0, product="Plano Pro",
        )
        with patch("agent.client_intelligence.buscar_cliente_por_reuniao", return_value="client-5"):
            r = vincular_automaticamente_se_possivel("m5")
        self.assertIsNone(r)

    def test_nunca_sobrescreve_vinculo_existente_mesmo_com_nova_oportunidade(self):
        database.salvar_meeting_memory("m6", usuario_id="seller-1")
        database.vincular_meeting_opportunity("m6", 77)
        database.criar_opportunity(client_id="client-6", seller_id="seller-1")
        with patch("agent.client_intelligence.buscar_cliente_por_reuniao", return_value="client-6"):
            r = vincular_automaticamente_se_possivel("m6")
        self.assertEqual(r, 77)


if __name__ == "__main__":
    unittest.main()
