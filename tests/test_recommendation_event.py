"""
Testes do RecommendationEvent — Fase 10 / Tarefa 10.1 do "PROMPT
MESTRE — SALE-IA V2" (Strategy Effectiveness).

Persistência usa SQLite em memória (mesmo padrão de
tests/test_sales_event.py) — nunca toca no banco real do projeto.

Escopo desta tarefa: criar o schema/validação/CRUD do
RecommendationEvent — não a detecção de uso (Tarefa 10.2, estados
USED/PARTIALLY_USED/IGNORED/UNKNOWN) nem a medição de efetividade real
(Tarefa 10.3), nenhuma das duas pedida pelo enunciado da Tarefa 10.1.

Run:
    python -m unittest tests.test_recommendation_event -v
"""

import unittest

from sqlmodel import SQLModel, create_engine
from unittest.mock import patch

from agent.recommendation_rules import validar_recommendation_event
from api import database


class ValidarRecommendationEventTest(unittest.TestCase):
    def _dados_validos(self, **overrides):
        dados = {
            "meeting_id": "reuniao-1",
            "strategy": "SPIN_IMPLICATION",
            "recommendation": "Pergunte sobre impacto financeiro.",
            "reason": "Cliente ainda não quantificou o custo do problema.",
        }
        dados.update(overrides)
        return dados

    def test_dados_validos_nao_levantam(self):
        validar_recommendation_event(self._dados_validos())  # não deve levantar

    def test_sem_meeting_id_levanta(self):
        with self.assertRaises(ValueError):
            validar_recommendation_event(self._dados_validos(meeting_id=""))

    def test_sem_strategy_levanta(self):
        with self.assertRaises(ValueError):
            validar_recommendation_event(self._dados_validos(strategy=None))

    def test_sem_recommendation_levanta(self):
        with self.assertRaises(ValueError):
            validar_recommendation_event(self._dados_validos(recommendation=""))

    def test_sem_reason_levanta(self):
        with self.assertRaises(ValueError):
            validar_recommendation_event(self._dados_validos(reason=""))


class RecommendationEventPersistenciaTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_criar_e_obter_recommendation_event(self):
        criado = database.criar_recommendation_event(
            meeting_id="reuniao-1",
            strategy="SPIN_IMPLICATION",
            recommendation="Pergunte sobre impacto financeiro.",
            reason="Cliente ainda não quantificou o custo do problema.",
        )
        self.assertIsNotNone(criado["id"])
        self.assertIsNone(criado["used_at"])
        self.assertIsNone(criado["seller_action"])

        lido = database.obter_recommendation_event(criado["id"])
        self.assertEqual(lido["strategy"], "SPIN_IMPLICATION")
        self.assertEqual(lido["recommendation"], "Pergunte sobre impacto financeiro.")

    def test_criar_com_dados_invalidos_levanta_e_nada_persiste(self):
        with self.assertRaises(ValueError):
            database.criar_recommendation_event(
                meeting_id="reuniao-1", strategy="", recommendation="x", reason="y",
            )
        self.assertEqual(database.listar_recommendation_events(meeting_id="reuniao-1"), [])

    def test_opportunity_id_e_outcome_window_opcionais(self):
        criado = database.criar_recommendation_event(
            meeting_id="reuniao-1",
            strategy="CASE_SIMILAR",
            recommendation="Compartilhe o case do Cliente X.",
            reason="Mesmo segmento e mesma objeção de preço.",
            opportunity_id=42,
            outcome_window="7d",
        )
        self.assertEqual(criado["opportunity_id"], 42)
        self.assertEqual(criado["outcome_window"], "7d")

    def test_listar_filtra_por_meeting_e_opportunity(self):
        database.criar_recommendation_event(
            meeting_id="reuniao-1", strategy="A", recommendation="r1", reason="m1", opportunity_id=1,
        )
        database.criar_recommendation_event(
            meeting_id="reuniao-1", strategy="B", recommendation="r2", reason="m2", opportunity_id=2,
        )
        database.criar_recommendation_event(
            meeting_id="reuniao-2", strategy="C", recommendation="r3", reason="m3", opportunity_id=1,
        )

        self.assertEqual(len(database.listar_recommendation_events(meeting_id="reuniao-1")), 2)
        self.assertEqual(len(database.listar_recommendation_events(opportunity_id=1)), 2)
        self.assertEqual(len(database.listar_recommendation_events(meeting_id="reuniao-2", opportunity_id=1)), 1)

    def test_registrar_uso_grava_seller_action_e_used_at_uma_vez(self):
        criado = database.criar_recommendation_event(
            meeting_id="reuniao-1", strategy="A", recommendation="Pergunte sobre impacto financeiro.", reason="m",
        )
        atualizado = database.registrar_uso_recommendation_event(
            criado["id"], seller_action="Quanto vocês estimam que isso custa todo mês?",
        )
        self.assertIsNotNone(atualizado["used_at"])
        self.assertEqual(atualizado["seller_action"], "Quanto vocês estimam que isso custa todo mês?")
        primeiro_used_at = atualizado["used_at"]

        # segunda chamada nao deve sobrescrever
        atualizado2 = database.registrar_uso_recommendation_event(criado["id"], seller_action="outra fala")
        self.assertEqual(atualizado2["used_at"], primeiro_used_at)
        self.assertEqual(atualizado2["seller_action"], "Quanto vocês estimam que isso custa todo mês?")

    def test_registrar_uso_sem_seller_action_levanta(self):
        criado = database.criar_recommendation_event(
            meeting_id="reuniao-1", strategy="A", recommendation="r", reason="m",
        )
        with self.assertRaises(ValueError):
            database.registrar_uso_recommendation_event(criado["id"], seller_action="")

    def test_registrar_uso_em_evento_inexistente_retorna_none(self):
        self.assertIsNone(database.registrar_uso_recommendation_event(999, seller_action="x"))


if __name__ == "__main__":
    unittest.main()
