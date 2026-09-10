"""
Testes do SalesEvidence — Fase 1 / Tarefa 1.2 do "PROMPT MESTRE —
SALE-IA V2" (separar interpretação de evidência).

Persistência usa SQLite em memória (mesmo padrão de
tests/test_sales_event.py / tests/test_ai_usage_events.py) — nunca toca
no banco real do projeto.

Escopo desta tarefa (mesma disciplina da Tarefa 1.1): criar o
schema/validação do SalesEvidence, não uma extração automática de
hipóteses a partir de transcrição livre. O teste de integração abaixo
reproduz o exemplo literal do prompt mestre (nunca salvar só "cliente
está inseguro" — sempre type=ADOPTION_RISK + quote="Tenho medo da minha
equipe não usar") chamando `criar_sales_evidence()` diretamente.

Run:
    python -m unittest tests.test_sales_evidence -v
"""

import unittest

from sqlmodel import SQLModel, create_engine
from unittest.mock import patch

from agent.sales_evidence_rules import validar_sales_evidence
from api import database


class ValidarSalesEvidenceTest(unittest.TestCase):
    def test_evidencia_valida_nao_levanta(self):
        validar_sales_evidence({
            "type": "ADOPTION_RISK",
            "quote": "Tenho medo da minha equipe não usar",
            "confidence": 0.85,
        })  # não deve levantar

    def test_hipotese_sem_evidencia_levanta(self):
        """A regra central da Tarefa 1.2: nunca salvar só a interpretação
        ("cliente está inseguro") sem a fala que a sustenta."""
        with self.assertRaises(ValueError):
            validar_sales_evidence({
                "type": "ADOPTION_RISK",
                "quote": "",
                "confidence": 0.85,
            })

    def test_hipotese_sem_campo_quote_levanta(self):
        with self.assertRaises(ValueError):
            validar_sales_evidence({"type": "ADOPTION_RISK", "confidence": 0.85})

    def test_type_vazio_levanta(self):
        with self.assertRaises(ValueError):
            validar_sales_evidence({
                "type": "",
                "quote": "Tenho medo da minha equipe não usar",
                "confidence": 0.85,
            })

    def test_confidence_fora_de_0_1_levanta(self):
        with self.assertRaises(ValueError):
            validar_sales_evidence({
                "type": "ADOPTION_RISK",
                "quote": "Tenho medo da minha equipe não usar",
                "confidence": 1.5,
            })
        with self.assertRaises(ValueError):
            validar_sales_evidence({
                "type": "ADOPTION_RISK",
                "quote": "Tenho medo da minha equipe não usar",
                "confidence": -0.1,
            })


class CriarSalesEvidencePersistenciaTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_criar_evidencia_valida_persiste_e_le_de_volta(self):
        criada = database.criar_sales_evidence(
            meeting_id="meeting-abc",
            type="ADOPTION_RISK",
            quote="Tenho medo da minha equipe não usar",
            speaker="cliente",
            confidence=0.85,
        )
        self.assertIsNotNone(criada["id"])

        lida = database.obter_sales_evidence(criada["id"])
        self.assertEqual(lida["meeting_id"], "meeting-abc")
        self.assertEqual(lida["type"], "ADOPTION_RISK")
        self.assertEqual(lida["quote"], "Tenho medo da minha equipe não usar")
        self.assertEqual(lida["speaker"], "cliente")

    def test_hipotese_sem_evidencia_nao_persiste_nada(self):
        with self.assertRaises(ValueError):
            database.criar_sales_evidence(
                meeting_id="meeting-abc",
                type="ADOPTION_RISK",
                quote="",
            )
        self.assertEqual(database.listar_sales_evidences(meeting_id="meeting-abc"), [])

    def test_confidence_invalida_nao_persiste_nada(self):
        with self.assertRaises(ValueError):
            database.criar_sales_evidence(
                meeting_id="meeting-abc",
                type="ADOPTION_RISK",
                quote="Tenho medo da minha equipe não usar",
                confidence=2.0,
            )
        self.assertEqual(database.listar_sales_evidences(meeting_id="meeting-abc"), [])

    def test_listar_filtra_por_meeting_id_e_type(self):
        database.criar_sales_evidence(
            meeting_id="m1", type="ADOPTION_RISK", quote="Tenho medo da equipe não usar",
        )
        database.criar_sales_evidence(
            meeting_id="m1", type="PRICE_SENSITIVITY", quote="Achei caro",
        )
        database.criar_sales_evidence(
            meeting_id="m2", type="ADOPTION_RISK", quote="Não sei se vamos adotar",
        )

        self.assertEqual(len(database.listar_sales_evidences(meeting_id="m1")), 2)
        self.assertEqual(len(database.listar_sales_evidences(type="ADOPTION_RISK")), 2)
        self.assertEqual(
            len(database.listar_sales_evidences(meeting_id="m1", type="ADOPTION_RISK")), 1,
        )

    def test_integracao_exemplo_do_prompt_mestre_adoption_risk(self):
        """Reproduz literalmente o exemplo da Tarefa 1.2: nunca salvar só
        "cliente está inseguro" — sempre hypothesis (type) + evidence
        (quote) juntos, persistidos e recuperáveis sem perder a fala."""
        evidencia = database.criar_sales_evidence(
            meeting_id="meeting-real-456",
            type="ADOPTION_RISK",
            quote="Tenho medo da minha equipe não usar",
            speaker="cliente",
            confidence=0.9,
        )

        lida = database.obter_sales_evidence(evidencia["id"])
        self.assertEqual(lida["type"], "ADOPTION_RISK")
        self.assertEqual(lida["quote"], "Tenho medo da minha equipe não usar")
        self.assertEqual(lida["source"], "conversation")


if __name__ == "__main__":
    unittest.main()
