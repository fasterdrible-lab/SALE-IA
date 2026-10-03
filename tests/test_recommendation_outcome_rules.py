"""
Testes — Tarefa B2 (docs/tasks-prompt-mestre-v2-restante.md): captura de
`stage_advanced` e `opportunity_result` por RecommendationEvent +
histórico de estágio da Opportunity.

Persistência usa SQLite em memória — nunca toca no banco real.

Run:
    python -m unittest tests.test_recommendation_outcome_rules -v
"""

import unittest
from datetime import datetime
from unittest.mock import patch

from sqlmodel import Session, SQLModel, create_engine

from agent.recommendation_effectiveness_rules import calcular_efetividade_por_estrategia
from agent.recommendation_outcome_rules import (
    anexar_resultados,
    calcular_stage_advanced,
    estagio_em,
    proxima_reuniao,
    resultado_da_oportunidade,
    resultados_do_evento,
)
from api import database

HIST = [
    {"stage": "descoberta", "changed_at": "2026-09-01T10:00:00"},
    {"stage": "proposta", "changed_at": "2026-09-10T18:00:00"},
]
REUNIOES = [
    {"meeting_id": "m1", "created_at": "2026-09-05T10:00:00"},
    {"meeting_id": "m2", "created_at": "2026-09-08T10:00:00"},
    {"meeting_id": "m3", "created_at": "2026-09-12T10:00:00"},
]


class EstagioEmTest(unittest.TestCase):
    def test_estagio_vigente_no_momento(self):
        self.assertEqual(estagio_em(HIST, "2026-09-05T10:00:00"), "descoberta")
        self.assertEqual(estagio_em(HIST, "2026-09-10T18:00:00"), "proposta")
        self.assertEqual(estagio_em(HIST, datetime(2026, 9, 20)), "proposta")

    def test_momento_antes_do_historico_ou_invalido(self):
        self.assertIsNone(estagio_em(HIST, "2026-08-01T10:00:00"))
        self.assertIsNone(estagio_em(HIST, None))
        self.assertIsNone(estagio_em([], "2026-09-05T10:00:00"))


class ProximaReuniaoTest(unittest.TestCase):
    def test_primeira_reuniao_depois(self):
        self.assertEqual(proxima_reuniao(REUNIOES, "m1")["meeting_id"], "m2")
        self.assertEqual(proxima_reuniao(list(reversed(REUNIOES)), "m2")["meeting_id"], "m3")

    def test_ultima_reuniao_ou_desconhecida(self):
        self.assertIsNone(proxima_reuniao(REUNIOES, "m3"))
        self.assertIsNone(proxima_reuniao(REUNIOES, "outra"))


class StageAdvancedTest(unittest.TestCase):
    def test_mudou_de_estagio_ate_a_reuniao_seguinte(self):
        self.assertTrue(calcular_stage_advanced(HIST, "2026-09-08T10:30:00", "2026-09-12T10:00:00"))

    def test_mesmo_estagio_e_false(self):
        self.assertFalse(calcular_stage_advanced(HIST, "2026-09-05T10:30:00", "2026-09-08T10:00:00"))

    def test_sem_reuniao_seguinte_ou_sem_historico_e_none(self):
        self.assertIsNone(calcular_stage_advanced(HIST, "2026-09-12T10:30:00", None))
        self.assertIsNone(calcular_stage_advanced([], "2026-09-05T10:30:00", "2026-09-08T10:00:00"))

    def test_perdida_antes_da_reuniao_seguinte_e_false(self):
        self.assertFalse(calcular_stage_advanced(HIST, "2026-09-08T10:30:00", "2026-09-12T10:00:00",
                                                 lost_at="2026-09-11T09:00:00"))


class ResultadoTest(unittest.TestCase):
    def test_so_won_e_lost_sao_desfecho(self):
        self.assertEqual(resultado_da_oportunidade("won"), "won")
        self.assertEqual(resultado_da_oportunidade("lost"), "lost")
        self.assertIsNone(resultado_da_oportunidade("open"))
        self.assertIsNone(resultado_da_oportunidade("abandoned"))

    def test_evento_sem_oportunidade(self):
        self.assertEqual(resultados_do_evento({"meeting_id": "m1"}, None, [], []),
                         {"stage_advanced": None, "opportunity_result": None})


class _ComBancoEmMemoria(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        p = patch.object(database, "engine", self._engine)
        p.start()
        self.addCleanup(p.stop)


class HistoricoDeEstagioTest(_ComBancoEmMemoria):
    def test_criacao_e_mudancas_reais_entram_no_historico(self):
        opp = database.criar_opportunity(client_id="c1", seller_id="s1", stage="descoberta")
        database.atualizar_stage_opportunity(opp["id"], "descoberta")  # sem mudança
        database.atualizar_stage_opportunity(opp["id"], "proposta")
        self.assertEqual([h["stage"] for h in database.listar_stage_history_opportunity(opp["id"])],
                         ["descoberta", "proposta"])

    def test_oportunidade_anterior_a_b2_ganha_o_estagio_original(self):
        with Session(self._engine) as s:  # simula linha criada antes da B2 (sem histórico)
            row = database.Opportunity(client_id="c1", seller_id="s1", stage="qualificação",
                                       created_at=datetime(2026, 8, 1, 10, 0))
            s.add(row)
            s.commit()
            opp_id = row.id
        self.assertEqual(database.listar_stage_history_opportunity(opp_id), [])

        database.atualizar_stage_opportunity(opp_id, "negociação")
        historico = database.listar_stage_history_opportunity(opp_id)
        self.assertEqual([h["stage"] for h in historico], ["qualificação", "negociação"])
        self.assertEqual(historico[0]["changed_at"], "2026-08-01T10:00:00")


class AnexarResultadosTest(_ComBancoEmMemoria):
    def _reuniao(self, meeting_id, opp_id, quando):
        with Session(self._engine) as s:
            s.add(database.MeetingMemory(meeting_id=meeting_id, opportunity_id=opp_id,
                                         created_at=quando, updated_at=quando))
            s.commit()

    def _historico(self, opp_id, stage, quando):
        with Session(self._engine) as s:
            s.add(database.OpportunityStageHistory(opportunity_id=opp_id, stage=stage, changed_at=quando))
            s.commit()

    def test_ponta_a_ponta_ate_a_taxa_de_avanco(self):
        """Teste da Tarefa B2: com histórico + reuniões vinculadas +
        resultado, `taxa_avanco`/`taxa_desfecho_positivo` deixam de ser
        `None`."""
        opp = database.criar_opportunity(client_id="c1", seller_id="s1", stage="descoberta")
        opp_id = opp["id"]
        self._reuniao("m1", opp_id, datetime(2026, 9, 5, 10))
        self._reuniao("m2", opp_id, datetime(2026, 9, 12, 10))
        self._reuniao("sem-opp", None, datetime(2026, 9, 6, 10))
        self._historico(opp_id, "descoberta", datetime(2026, 9, 1, 10))
        self._historico(opp_id, "proposta", datetime(2026, 9, 10, 18))
        database.atualizar_status_opportunity(opp_id, "won", value=1000.0, product="Plano Pro")

        eventos = [
            {"id": 1, "meeting_id": "m1", "shown_at": "2026-09-05T10:30:00", "strategy": "SPIN_IMPLICATION", "state": "USED"},
            {"id": 2, "meeting_id": "m2", "shown_at": "2026-09-12T10:30:00", "strategy": "SPIN_IMPLICATION", "state": "USED"},
            {"id": 3, "meeting_id": "sem-opp", "shown_at": "2026-09-06T10:30:00", "strategy": "CASE", "state": "USED"},
        ]
        com_resultado = {e["id"]: e for e in anexar_resultados(eventos)}

        self.assertTrue(com_resultado[1]["stage_advanced"])
        self.assertEqual(com_resultado[1]["opportunity_result"], "won")
        self.assertIsNone(com_resultado[2]["stage_advanced"])  # sem reunião seguinte
        self.assertEqual(com_resultado[2]["opportunity_result"], "won")
        self.assertIsNone(com_resultado[3]["stage_advanced"])
        self.assertIsNone(com_resultado[3]["opportunity_result"])
        self.assertEqual(com_resultado[1]["strategy"], "SPIN_IMPLICATION")  # campos originais preservados

        efetividade = calcular_efetividade_por_estrategia(list(com_resultado.values()))
        self.assertEqual(efetividade["SPIN_IMPLICATION"]["taxa_avanco"], 1.0)
        self.assertEqual(efetividade["SPIN_IMPLICATION"]["taxa_desfecho_positivo"], 1.0)
        self.assertIsNone(efetividade["CASE"]["taxa_avanco"])


if __name__ == "__main__":
    unittest.main()
