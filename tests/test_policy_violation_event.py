"""
Testes do PolicyViolationEvent — Fase 25 do "PROMPT MESTRE — SALE-IA
V2" (Critério para iniciar o Digital Sales Twin), alimenta o critério
`policy_violation = 0`.

Persistência usa SQLite em memória (mesmo padrão de
tests/test_audit_trail.py) — nunca toca no banco real do projeto.

Run:
    python -m unittest tests.test_policy_violation_event -v
"""
import unittest
from datetime import datetime, timedelta

from sqlmodel import SQLModel, create_engine
from unittest.mock import patch

from api import database


class PolicyViolationEventPersistenciaTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_criar_e_listar(self):
        criado = database.criar_policy_violation_event(
            tipo="PROMPT_INJECTION",
            trechos_detectados=["ignore as instruções"],
            meeting_id="reuniao-1",
            usuario_id="user-1",
            feature="realtime.coach",
        )
        self.assertIsNotNone(criado["id"])
        self.assertEqual(criado["tipo"], "PROMPT_INJECTION")
        self.assertEqual(criado["trechos_detectados"], ["ignore as instruções"])
        self.assertEqual(criado["meeting_id"], "reuniao-1")
        self.assertEqual(criado["usuario_id"], "user-1")
        self.assertEqual(criado["feature"], "realtime.coach")

        listados = database.listar_policy_violation_events()
        self.assertEqual(len(listados), 1)

    def test_campos_opcionais_ausentes(self):
        criado = database.criar_policy_violation_event(
            tipo="PROMPT_INJECTION", trechos_detectados=["x"],
        )
        self.assertIsNone(criado["meeting_id"])
        self.assertIsNone(criado["usuario_id"])
        self.assertIsNone(criado["feature"])

    def test_criar_com_dados_invalidos_levanta_e_nada_persiste(self):
        with self.assertRaises(ValueError):
            database.criar_policy_violation_event(tipo="ADVERSARIAL_SALES", trechos_detectados=["x"])
        self.assertEqual(database.listar_policy_violation_events(), [])

    def test_listar_filtra_por_meeting_id_e_tipo(self):
        database.criar_policy_violation_event(
            tipo="PROMPT_INJECTION", trechos_detectados=["a"], meeting_id="reuniao-1",
        )
        database.criar_policy_violation_event(
            tipo="PROMPT_INJECTION", trechos_detectados=["b"], meeting_id="reuniao-2",
        )
        self.assertEqual(len(database.listar_policy_violation_events(meeting_id="reuniao-1")), 1)
        self.assertEqual(len(database.listar_policy_violation_events(tipo="PROMPT_INJECTION")), 2)

    def test_contar_policy_violations_total(self):
        database.criar_policy_violation_event(tipo="PROMPT_INJECTION", trechos_detectados=["a"])
        database.criar_policy_violation_event(tipo="PROMPT_INJECTION", trechos_detectados=["b"])
        self.assertEqual(database.contar_policy_violations(), 2)

    def test_contar_policy_violations_vazio_e_zero_nunca_none(self):
        self.assertEqual(database.contar_policy_violations(), 0)

    def test_contar_policy_violations_filtra_por_periodo(self):
        agora = datetime.now()
        with database.Session(self._engine) as session:
            row = database.PolicyViolationEvent(
                tipo="PROMPT_INJECTION",
                trechos_detectados_json='["a"]',
                criado_em=agora - timedelta(days=10),
            )
            session.add(row)
            session.commit()

        database.criar_policy_violation_event(tipo="PROMPT_INJECTION", trechos_detectados=["b"])

        total_geral = database.contar_policy_violations()
        total_recente = database.contar_policy_violations(date_from=agora - timedelta(days=1))
        self.assertEqual(total_geral, 2)
        self.assertEqual(total_recente, 1)


if __name__ == "__main__":
    unittest.main()
