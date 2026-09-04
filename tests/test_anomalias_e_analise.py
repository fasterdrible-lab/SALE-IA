"""
Testes de api/database.py::detectar_anomalias_custo e
analise_custo_latencia_qualidade (Cost Intelligence Fase 5).

Usa engine SQLite em memoria isolado por teste — mesmo harness de
tests/test_cost_aggregation.py.

Run:
    python -m unittest tests.test_anomalias_e_analise -v
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlmodel import Session, SQLModel, create_engine

from api import database


class DetectarAnomaliasTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def _evento_em(self, feature, cost_usd, dias_atras):
        with Session(self._engine) as session:
            session.add(database.AiUsageEvent(
                feature=feature, provider="openai", cost_usd=cost_usd,
                criado_em=datetime.now() - timedelta(days=dias_atras),
            ))
            session.commit()

    def test_sem_amostra_suficiente_nao_alarma(self):
        for _ in range(3):
            self._evento_em("realtime.coach", 0.01, dias_atras=1)
            self._evento_em("realtime.coach", 0.01, dias_atras=10)
        anomalias = database.detectar_anomalias_custo(dias_janela=7)
        self.assertEqual(anomalias, [])

    def test_custo_estavel_nao_alarma(self):
        for _ in range(6):
            self._evento_em("realtime.coach", 0.01, dias_atras=1)
            self._evento_em("realtime.coach", 0.01, dias_atras=10)
        anomalias = database.detectar_anomalias_custo(dias_janela=7, limiar_multiplicador=3.0)
        self.assertEqual(anomalias, [])

    def test_custo_disparado_alarma(self):
        for _ in range(6):
            self._evento_em("realtime.coach", 0.30, dias_atras=1)  # janela atual — caro
            self._evento_em("realtime.coach", 0.01, dias_atras=10)  # janela anterior — barato

        anomalias = database.detectar_anomalias_custo(dias_janela=7, limiar_multiplicador=3.0)
        self.assertEqual(len(anomalias), 1)
        self.assertEqual(anomalias[0]["feature"], "realtime.coach")
        self.assertGreaterEqual(anomalias[0]["multiplicador"], 3.0)

    def test_feature_fora_do_multiplicador_nao_alarma(self):
        for _ in range(6):
            self._evento_em("realtime.coach", 0.015, dias_atras=1)  # so 1.5x, abaixo do limiar 3.0
            self._evento_em("realtime.coach", 0.01, dias_atras=10)
        anomalias = database.detectar_anomalias_custo(dias_janela=7, limiar_multiplicador=3.0)
        self.assertEqual(anomalias, [])

    def test_sem_nenhum_evento_retorna_lista_vazia(self):
        self.assertEqual(database.detectar_anomalias_custo(), [])


class AnaliseCustoLatenciaQualidadeTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def _evento(self, **overrides):
        base = dict(
            feature="realtime.coach", provider="deepseek", model="deepseek-chat",
            input_tokens=100, output_tokens=50, usage_source="provider",
            cost_usd=0.01, success=True, latency_ms=500,
        )
        base.update(overrides)
        database.registrar_evento_uso_ia(**base)

    def test_agrupa_por_provider_e_model_com_medias(self):
        self._evento(provider="deepseek", model="deepseek-chat", cost_usd=0.01, latency_ms=400)
        self._evento(provider="deepseek", model="deepseek-chat", cost_usd=0.03, latency_ms=600)
        self._evento(provider="openai", model="gpt-4o", cost_usd=0.50, latency_ms=1000)

        r = database.analise_custo_latencia_qualidade()
        por_chave = {(c["provider"], c["model"]): c for c in r["custo_latencia"]}
        self.assertAlmostEqual(por_chave[("deepseek", "deepseek-chat")]["custo_medio_usd"], 0.02, places=6)
        self.assertAlmostEqual(por_chave[("deepseek", "deepseek-chat")]["latencia_media_ms"], 500.0, places=1)
        self.assertEqual(por_chave[("openai", "gpt-4o")]["eventos"], 1)
        # ordenado por custo medio desc
        self.assertEqual(r["custo_latencia"][0]["provider"], "openai")

    def test_ignora_eventos_com_falha(self):
        self._evento(success=True, cost_usd=0.01)
        self._evento(success=False, cost_usd=99.0)
        r = database.analise_custo_latencia_qualidade()
        self.assertEqual(len(r["custo_latencia"]), 1)
        self.assertAlmostEqual(r["custo_latencia"][0]["custo_medio_usd"], 0.01, places=6)

    def test_qualidade_claude_account_degrada_sem_quebrar(self):
        with patch.object(database, "metricas_claude_account", side_effect=RuntimeError("boom")):
            r = database.analise_custo_latencia_qualidade()
        self.assertEqual(r["qualidade_claude_account"], {})

    def test_sem_eventos_retorna_lista_vazia(self):
        r = database.analise_custo_latencia_qualidade()
        self.assertEqual(r["custo_latencia"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
