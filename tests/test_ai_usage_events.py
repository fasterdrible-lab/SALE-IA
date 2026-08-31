"""
Testes de ai_usage_events / registrar_evento_uso_ia / custo_por_reuniao
(Cost Intelligence Fase 1).

Usa engine SQLite em memoria isolado por teste — nunca toca no banco real
do projeto.

Run:
    python -m unittest tests.test_ai_usage_events -v
"""

import unittest
from unittest.mock import patch

from sqlmodel import SQLModel, create_engine

from api import database


class AiUsageEventsTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_registrar_evento_grava_todos_os_campos(self):
        database.registrar_evento_uso_ia(
            feature="realtime.coach",
            provider="deepseek",
            model="deepseek-chat",
            input_tokens=100,
            output_tokens=50,
            cached_input_tokens=10,
            usage_source="provider",
            cost_usd=0.001234,
            latency_ms=250,
            success=True,
            fallback_used=False,
            meeting_id="meeting-abc",
            usuario_id="user-1",
        )

        resultado = database.custo_por_reuniao("meeting-abc")
        self.assertEqual(resultado["total_eventos"], 1)
        self.assertAlmostEqual(resultado["total_usd"], 0.001234, places=6)
        self.assertEqual(resultado["por_feature"]["realtime.coach"]["chamadas"], 1)
        self.assertEqual(resultado["por_feature"]["realtime.coach"]["tokens_entrada"], 100)
        self.assertEqual(resultado["por_provider"]["deepseek"]["chamadas"], 1)
        self.assertEqual(resultado["por_provider"]["deepseek"]["falhas"], 0)

    def test_registrar_evento_nunca_lanca_excecao_mesmo_com_engine_quebrado(self):
        with patch.object(database, "Session", side_effect=RuntimeError("banco fora do ar")):
            try:
                database.registrar_evento_uso_ia(
                    feature="unspecified",
                    provider="openai",
                    model="gpt-4o",
                    input_tokens=1,
                    output_tokens=1,
                    usage_source="estimated",
                    cost_usd=0.0,
                    success=False,
                )
            except Exception as exc:  # pragma: no cover - falha do teste se propagar
                self.fail(f"registrar_evento_uso_ia propagou excecao: {exc}")

    def test_custo_por_reuniao_agrega_multiplos_eventos_features_e_providers(self):
        database.registrar_evento_uso_ia(
            feature="realtime.coach", provider="deepseek", model="deepseek-chat",
            input_tokens=100, output_tokens=50, usage_source="provider",
            cost_usd=0.01, success=True, meeting_id="m1",
        )
        database.registrar_evento_uso_ia(
            feature="realtime.disc", provider="openai", model="gpt-4o",
            input_tokens=200, output_tokens=100, usage_source="estimated",
            cost_usd=0.02, success=False, meeting_id="m1",
        )
        # evento de outra reuniao — nao deve entrar na agregacao de m1
        database.registrar_evento_uso_ia(
            feature="realtime.coach", provider="deepseek", model="deepseek-chat",
            input_tokens=999, output_tokens=999, usage_source="provider",
            cost_usd=99.0, success=True, meeting_id="m2",
        )

        resultado = database.custo_por_reuniao("m1")
        self.assertEqual(resultado["total_eventos"], 2)
        self.assertAlmostEqual(resultado["total_usd"], 0.03, places=6)
        self.assertIn("realtime.coach", resultado["por_feature"])
        self.assertIn("realtime.disc", resultado["por_feature"])
        self.assertEqual(resultado["por_provider"]["openai"]["falhas"], 1)
        self.assertEqual(resultado["por_provider"]["deepseek"]["falhas"], 0)

    def test_custo_por_reuniao_sem_eventos_retorna_zero(self):
        resultado = database.custo_por_reuniao("reuniao-inexistente")
        self.assertEqual(resultado["total_eventos"], 0)
        self.assertEqual(resultado["total_usd"], 0.0)
        self.assertEqual(resultado["por_feature"], {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
