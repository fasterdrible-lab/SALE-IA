"""
Testes de persistência do ShadowModeComparison — Fase 23 do "PROMPT
MESTRE — SALE-IA V2" (Teste em Shadow Mode).

SQLite em memória (mesmo padrão de tests/test_audit_trail.py).

Run:
    python -m unittest tests.test_shadow_mode_persistencia -v
"""
import unittest
from unittest.mock import patch

from sqlmodel import SQLModel, create_engine

from api import database


class ShadowModeComparisonPersistenciaTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def _registro(self, **overrides):
        base = dict(
            meeting_id="reuniao-1",
            usuario_id="seller-1",
            recomendacao_atual={"type": "question", "message": "X?"},
            recomendacao_nova={"next_best_action": "Pergunte sobre impacto.", "next_best_question": "Quanto custa hoje?"},
            concordancia=True,
            atual_e_pergunta=True,
            novo_e_pergunta=True,
            latency_ms=820,
            cost_usd=0.0019,
            erro=None,
        )
        base.update(overrides)
        return base

    def test_criar_e_listar(self):
        criado = database.criar_shadow_mode_comparison(**self._registro())
        self.assertIsNotNone(criado["id"])
        self.assertEqual(criado["meeting_id"], "reuniao-1")
        self.assertEqual(criado["recomendacao_atual"]["type"], "question")
        self.assertEqual(criado["recomendacao_nova"]["next_best_question"], "Quanto custa hoje?")
        self.assertTrue(criado["concordancia"])

        listados = database.listar_shadow_mode_comparisons()
        self.assertEqual(len(listados), 1)

    def test_erro_persiste_recomendacao_nova_none(self):
        criado = database.criar_shadow_mode_comparison(
            **self._registro(recomendacao_nova=None, concordancia=None, atual_e_pergunta=None,
                              novo_e_pergunta=None, latency_ms=None, cost_usd=None, erro="TimeoutError: 45s"),
        )
        self.assertIsNone(criado["recomendacao_nova"])
        self.assertIsNone(criado["concordancia"])
        self.assertEqual(criado["erro"], "TimeoutError: 45s")

    def test_campo_quality_extra_e_ignorado_sem_quebrar(self):
        from agent.shadow_mode_rules import montar_registro_shadow
        registro = montar_registro_shadow({"type": "question"}, None, None, None, "erro qualquer")
        criado = database.criar_shadow_mode_comparison(meeting_id="m1", usuario_id="u1", **registro)
        self.assertIsNotNone(criado["id"])

    def test_listar_ordena_mais_recente_primeiro(self):
        database.criar_shadow_mode_comparison(**self._registro(meeting_id="reuniao-1"))
        database.criar_shadow_mode_comparison(**self._registro(meeting_id="reuniao-2"))
        listados = database.listar_shadow_mode_comparisons()
        self.assertEqual(listados[0]["meeting_id"], "reuniao-2")

    def test_obter_ultimo_ai_usage_event_sem_meeting_id_retorna_none(self):
        self.assertIsNone(database.obter_ultimo_ai_usage_event("qualquer.feature", None))

    def test_obter_ultimo_ai_usage_event_sem_evento_retorna_none(self):
        self.assertIsNone(database.obter_ultimo_ai_usage_event("qualquer.feature", "reuniao-inexistente"))

    def test_obter_ultimo_ai_usage_event_retorna_mais_recente(self):
        from api.database import AiUsageEvent, Session as _Session
        with _Session(self._engine) as session:
            session.add(AiUsageEvent(meeting_id="reuniao-1", feature="sales_reasoning.raciocinio",
                                      provider="anthropic", cost_usd=0.001, latency_ms=500, success=True))
            session.add(AiUsageEvent(meeting_id="reuniao-1", feature="sales_reasoning.raciocinio",
                                      provider="anthropic", cost_usd=0.002, latency_ms=600, success=True))
            session.commit()
        evento = database.obter_ultimo_ai_usage_event("sales_reasoning.raciocinio", "reuniao-1")
        self.assertEqual(evento["cost_usd"], 0.002)


if __name__ == "__main__":
    unittest.main()
