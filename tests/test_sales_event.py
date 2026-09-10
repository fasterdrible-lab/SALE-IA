"""
Testes do SalesEvent — Fase 1 / Tarefa 1.1 do "PROMPT MESTRE — SALE-IA V2"
(modelo canônico da venda).

Persistência usa SQLite em memória (mesmo padrão de
tests/test_ai_usage_events.py) — nunca toca no banco real do projeto.

Escopo desta tarefa: criar o schema/validação do SalesEvent, não uma
extração automática a partir de transcrição livre (isso não está no
enunciado da Tarefa 1.1 — só o schema e a regra de evidência). O teste
de integração abaixo reproduz o exemplo literal do prompt mestre
("Achei caro." -> OBJECTION_RAISED/category=PRICE/evidence="Achei caro")
chamando `criar_sales_event()` diretamente com esses valores, provando
que o schema e a validação suportam esse cenário de ponta a ponta via
persistência real — a extração automática desse evento a partir do
texto bruto da transcrição fica para uma tarefa futura.

Run:
    python -m unittest tests.test_sales_event -v
"""

import unittest

from sqlmodel import SQLModel, create_engine
from unittest.mock import patch

from agent.sales_event_rules import SALES_EVENT_TYPES, validar_sales_event
from api import database


class ValidarSalesEventTest(unittest.TestCase):
    def test_evento_valido_nao_levanta(self):
        validar_sales_event({
            "event_type": "OBJECTION_RAISED",
            "source": "conversation",
            "confidence": 0.9,
            "evidence_quote": "Achei caro",
        })  # não deve levantar

    def test_evento_de_conversa_sem_evidencia_levanta(self):
        with self.assertRaises(ValueError):
            validar_sales_event({
                "event_type": "OBJECTION_RAISED",
                "source": "conversation",
                "confidence": 0.9,
                "evidence_quote": "",
            })

    def test_evento_de_conversa_sem_campo_evidencia_levanta(self):
        with self.assertRaises(ValueError):
            validar_sales_event({
                "event_type": "OBJECTION_RAISED",
                "source": "conversation",
                "confidence": 0.9,
            })

    def test_confidence_fora_de_0_1_levanta(self):
        with self.assertRaises(ValueError):
            validar_sales_event({
                "event_type": "OBJECTION_RAISED",
                "source": "conversation",
                "confidence": 1.5,
                "evidence_quote": "Achei caro",
            })
        with self.assertRaises(ValueError):
            validar_sales_event({
                "event_type": "OBJECTION_RAISED",
                "source": "conversation",
                "confidence": -0.1,
                "evidence_quote": "Achei caro",
            })

    def test_event_type_desconhecido_levanta(self):
        with self.assertRaises(ValueError):
            validar_sales_event({
                "event_type": "NAO_EXISTE",
                "source": "conversation",
                "confidence": 0.9,
                "evidence_quote": "Achei caro",
            })

    def test_fonte_nao_conversacional_dispensa_evidencia(self):
        validar_sales_event({
            "event_type": "NEXT_STEP_AGREED",
            "source": "manual",
            "confidence": 1.0,
        })  # não deve levantar — só source="conversation" exige evidência

    def test_todos_os_14_tipos_sao_aceitos(self):
        self.assertEqual(len(SALES_EVENT_TYPES), 14)
        for tipo in SALES_EVENT_TYPES:
            validar_sales_event({
                "event_type": tipo,
                "source": "manual",
                "confidence": 0.5,
            })


class CriarSalesEventPersistenciaTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_criar_evento_valido_persiste_e_le_de_volta(self):
        criado = database.criar_sales_event(
            meeting_id="meeting-abc",
            event_type="BUYING_SIGNAL",
            source="conversation",
            confidence=0.8,
            evidence_quote="Quando conseguimos começar?",
            speaker="cliente",
        )
        self.assertIsNotNone(criado["id"])

        lido = database.obter_sales_event(criado["id"])
        self.assertEqual(lido["meeting_id"], "meeting-abc")
        self.assertEqual(lido["event_type"], "BUYING_SIGNAL")
        self.assertEqual(lido["evidence_quote"], "Quando conseguimos começar?")
        self.assertEqual(lido["speaker"], "cliente")

    def test_criar_evento_invalido_nao_persiste_nada(self):
        with self.assertRaises(ValueError):
            database.criar_sales_event(
                meeting_id="meeting-abc",
                event_type="OBJECTION_RAISED",
                source="conversation",
                confidence=0.9,
                evidence_quote="",
            )
        self.assertEqual(database.listar_sales_events(meeting_id="meeting-abc"), [])

    def test_confidence_invalida_nao_persiste_nada(self):
        with self.assertRaises(ValueError):
            database.criar_sales_event(
                meeting_id="meeting-abc",
                event_type="OBJECTION_RAISED",
                confidence=2.0,
                evidence_quote="Achei caro",
            )
        self.assertEqual(database.listar_sales_events(meeting_id="meeting-abc"), [])

    def test_listar_filtra_por_meeting_id_e_event_type(self):
        database.criar_sales_event(
            meeting_id="m1", event_type="PRICE_DISCUSSION",
            evidence_quote="Vamos falar de valores",
        )
        database.criar_sales_event(
            meeting_id="m1", event_type="OBJECTION_RAISED",
            evidence_quote="Achei caro",
        )
        database.criar_sales_event(
            meeting_id="m2", event_type="OBJECTION_RAISED",
            evidence_quote="Muito caro pra nós",
        )

        self.assertEqual(len(database.listar_sales_events(meeting_id="m1")), 2)
        self.assertEqual(len(database.listar_sales_events(event_type="OBJECTION_RAISED")), 2)
        self.assertEqual(
            len(database.listar_sales_events(meeting_id="m1", event_type="OBJECTION_RAISED")), 1,
        )

    def test_integracao_exemplo_do_prompt_mestre_achei_caro(self):
        """Reproduz literalmente o exemplo de Integração da Tarefa 1.1:
        transcrição "Achei caro." deve virar um SalesEvent
        OBJECTION_RAISED, category=PRICE, evidence="Achei caro" —
        persistido e recuperável via SalesEvent, sem perder a evidência.
        """
        evento = database.criar_sales_event(
            meeting_id="meeting-real-123",
            event_type="OBJECTION_RAISED",
            source="conversation",
            confidence=0.95,
            evidence_quote="Achei caro",
            speaker="cliente",
            metadata={"category": "PRICE"},
        )

        lido = database.obter_sales_event(evento["id"])
        self.assertEqual(lido["event_type"], "OBJECTION_RAISED")
        self.assertEqual(lido["evidence_quote"], "Achei caro")
        self.assertEqual(lido["metadata"]["category"], "PRICE")
        self.assertEqual(lido["source"], "conversation")


if __name__ == "__main__":
    unittest.main()
