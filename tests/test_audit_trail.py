"""
Testes do AuditTrailEntry — Fase 18 / Tarefa 18.4 do "PROMPT MESTRE —
SALE-IA V2" (fecha a Fase 18 — Segurança).

Persistência usa SQLite em memória (mesmo padrão de
tests/test_recommendation_event.py) — nunca toca no banco real do
projeto.

Escopo desta tarefa: criar o schema/validação/CRUD do AuditTrailEntry —
sem integração automática com nenhum fluxo real (chamar_ia,
SalesReasoningEngine, AutonomyPolicy) ainda; quem decidir gravar uma
entrada é código futuro, mesma disciplina "contrato primeiro" das
Fases 1-17.

Run:
    python -m unittest tests.test_audit_trail -v
"""
import unittest

from sqlmodel import SQLModel, create_engine
from unittest.mock import patch

from agent.audit_trail_rules import validar_audit_trail_entry
from api import database


class ValidarAuditTrailEntryTest(unittest.TestCase):
    def _dados_validos(self, **overrides):
        dados = {
            "actor": "sales_reasoning_engine",
            "action": "recomendacao_gerada",
            "reason": "SPIN Implication ausente para esta oportunidade.",
            "result": "Pergunte sobre impacto financeiro.",
        }
        dados.update(overrides)
        return dados

    def test_dados_validos_nao_levantam(self):
        validar_audit_trail_entry(self._dados_validos())  # não deve levantar

    def test_sem_actor_levanta(self):
        with self.assertRaises(ValueError):
            validar_audit_trail_entry(self._dados_validos(actor=""))

    def test_sem_action_levanta(self):
        with self.assertRaises(ValueError):
            validar_audit_trail_entry(self._dados_validos(action=None))

    def test_sem_reason_levanta(self):
        with self.assertRaises(ValueError):
            validar_audit_trail_entry(self._dados_validos(reason=""))

    def test_sem_result_levanta(self):
        with self.assertRaises(ValueError):
            validar_audit_trail_entry(self._dados_validos(result="   "))


class AuditTrailEntryPersistenciaTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_criar_e_obter_audit_trail_entry(self):
        criado = database.criar_audit_trail_entry(
            actor="sales_reasoning_engine",
            action="recomendacao_gerada",
            reason="SPIN Implication ausente para esta oportunidade.",
            result="Pergunte sobre impacto financeiro.",
        )
        self.assertIsNotNone(criado["id"])
        self.assertIsNone(criado["meeting_id"])
        self.assertIsNone(criado["model"])
        self.assertIsNone(criado["data_used"])

        lido = database.obter_audit_trail_entry(criado["id"])
        self.assertEqual(lido["actor"], "sales_reasoning_engine")
        self.assertEqual(lido["action"], "recomendacao_gerada")
        self.assertEqual(lido["result"], "Pergunte sobre impacto financeiro.")

    def test_criar_com_dados_invalidos_levanta_e_nada_persiste(self):
        with self.assertRaises(ValueError):
            database.criar_audit_trail_entry(actor="", action="x", reason="y", result="z")
        self.assertEqual(database.listar_audit_trail_entries(), [])

    def test_campos_opcionais_completos(self):
        criado = database.criar_audit_trail_entry(
            actor="vendedor-123",
            action="desconto_aprovado",
            reason="Cliente ameaçou cancelar; margem ainda positiva.",
            result="Desconto de 10% aplicado.",
            meeting_id="reuniao-1",
            opportunity_id=42,
            data_used={"margem_atual": 0.35, "historico_cliente": "3 anos"},
            model="claude-sonnet-5",
            prompt_version="sales_reasoning_engine.v3",
            rule_version="autonomy_policy_rules.v1",
        )
        self.assertEqual(criado["meeting_id"], "reuniao-1")
        self.assertEqual(criado["opportunity_id"], 42)
        self.assertEqual(criado["data_used"], {"margem_atual": 0.35, "historico_cliente": "3 anos"})
        self.assertEqual(criado["model"], "claude-sonnet-5")
        self.assertEqual(criado["prompt_version"], "sales_reasoning_engine.v3")
        self.assertEqual(criado["rule_version"], "autonomy_policy_rules.v1")

    def test_listar_filtra_por_meeting_actor_e_action(self):
        database.criar_audit_trail_entry(
            actor="a1", action="recomendacao_gerada", reason="m1", result="r1", meeting_id="reuniao-1",
        )
        database.criar_audit_trail_entry(
            actor="a2", action="recomendacao_gerada", reason="m2", result="r2", meeting_id="reuniao-1",
        )
        database.criar_audit_trail_entry(
            actor="a1", action="desconto_aprovado", reason="m3", result="r3", meeting_id="reuniao-2",
        )

        self.assertEqual(len(database.listar_audit_trail_entries(meeting_id="reuniao-1")), 2)
        self.assertEqual(len(database.listar_audit_trail_entries(actor="a1")), 2)
        self.assertEqual(len(database.listar_audit_trail_entries(action="desconto_aprovado")), 1)
        self.assertEqual(
            len(database.listar_audit_trail_entries(meeting_id="reuniao-1", actor="a1")), 1,
        )

    def test_listar_filtra_por_opportunity_id(self):
        database.criar_audit_trail_entry(
            actor="a1", action="x", reason="m", result="r", opportunity_id=1,
        )
        database.criar_audit_trail_entry(
            actor="a1", action="x", reason="m", result="r", opportunity_id=2,
        )
        self.assertEqual(len(database.listar_audit_trail_entries(opportunity_id=1)), 1)

    def test_obter_entry_inexistente_retorna_none(self):
        self.assertIsNone(database.obter_audit_trail_entry(999))


if __name__ == "__main__":
    unittest.main()
