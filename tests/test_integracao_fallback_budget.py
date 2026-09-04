"""
Testes de integracao ponta a ponta (Cost Intelligence Fase 6):
diferente dos testes de cada fase (que mockam a escrita), estes gravam
de verdade num banco de teste e leem de volta pela agregacao real —
provam que os caminhos de fallback/orcamento/anomalia batem certo do
outro lado da agregacao, nao so isoladamente.

Usa o mesmo harness SQLite em memoria de tests/test_cost_aggregation.py.

Run:
    python -m unittest tests.test_integracao_fallback_budget -v
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlmodel import Session, SQLModel, create_engine

from agent import alertas
from api import database


class IntegracaoFallbackTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_fallback_claude_account_reflete_no_resumo_real(self):
        # Grava de verdade (sem mockar registrar_evento_uso_ia), exatamente
        # como agent/multiagente/claude_fallback.py faz quando o fallback
        # dispara de verdade.
        database.registrar_evento_uso_ia(
            feature="realtime.coach", provider="claude_account", model=None,
            input_tokens=0, output_tokens=0, usage_source="provider",
            cost_usd=0.0387, success=True, fallback_used=True,
            usuario_id="user-1", meeting_id="m1",
        )
        database.registrar_evento_uso_ia(
            feature="realtime.disc", provider="claude_account", model=None,
            input_tokens=0, output_tokens=0, usage_source="provider",
            cost_usd=0.0296, success=True, fallback_used=True,
            usuario_id="user-1", meeting_id="m1",
        )

        resumo = database.custos_resumo()
        self.assertEqual(resumo["fallback_eventos"], 2)
        self.assertAlmostEqual(resumo["fallback_usd"], 0.0683, places=6)
        por_provider = {p["provider"]: p for p in resumo["por_provider"]}
        self.assertIn("claude_account", por_provider)
        self.assertEqual(por_provider["claude_account"]["eventos"], 2)

    def test_todos_provedores_falhando_reflete_em_eventos_falha(self):
        # Mesmo formato que api/ai_router.py::chamar_ia grava quando todos
        # os provedores falham (provider="none", success=False).
        database.registrar_evento_uso_ia(
            feature="realtime.coach", provider="none", model=None,
            input_tokens=0, output_tokens=0, usage_source="unavailable",
            cost_usd=0.0, success=False, error_message="todos os provedores falharam",
        )
        database.registrar_evento_uso_ia(
            feature="realtime.coach", provider="deepseek", model="deepseek-chat",
            input_tokens=100, output_tokens=50, usage_source="provider",
            cost_usd=0.01, success=True,
        )

        resumo = database.custos_resumo()
        self.assertEqual(resumo["total_eventos"], 2)
        self.assertEqual(resumo["eventos_falha"], 1)
        self.assertEqual(resumo["eventos_sucesso"], 1)


class IntegracaoOrcamentoTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)
        alertas._last_alerta.clear()

    def test_gasto_real_cruzando_100pct_dispara_alerta_critico_ponta_a_ponta(self):
        database.definir_orcamento_ia(10.0, "admin-1", "admin@saleia.app.br")

        agora = datetime.now()
        database.registrar_evento_uso_ia(
            feature="realtime.coach", provider="openai", model="gpt-4o",
            input_tokens=100, output_tokens=50, usage_source="provider",
            cost_usd=12.0, success=True,
        )

        gasto = database.gasto_mes_usd(agora.year, agora.month)
        orcamento = database.obter_orcamento_ia()
        self.assertAlmostEqual(gasto, 12.0, places=6)

        with patch.object(alertas, "alertar") as mock_alertar:
            alertas.verificar_orcamento(gasto, orcamento["limite_mensal_usd"])
        mock_alertar.assert_called_once()
        args, kwargs = mock_alertar.call_args
        self.assertEqual(kwargs.get("nivel"), "🔴")

    def test_gasto_real_abaixo_do_limite_nao_dispara(self):
        database.definir_orcamento_ia(100.0, "admin-1", "admin@saleia.app.br")
        agora = datetime.now()
        database.registrar_evento_uso_ia(
            feature="realtime.coach", provider="deepseek", model="deepseek-chat",
            input_tokens=100, output_tokens=50, usage_source="provider",
            cost_usd=1.0, success=True,
        )
        gasto = database.gasto_mes_usd(agora.year, agora.month)
        orcamento = database.obter_orcamento_ia()

        with patch.object(alertas, "alertar") as mock_alertar:
            alertas.verificar_orcamento(gasto, orcamento["limite_mensal_usd"])
        mock_alertar.assert_not_called()


class IntegracaoAnomaliaTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)
        alertas._last_alerta.clear()

    def _evento_em(self, feature, cost_usd, dias_atras):
        with Session(self._engine) as session:
            session.add(database.AiUsageEvent(
                feature=feature, provider="openai", cost_usd=cost_usd,
                criado_em=datetime.now() - timedelta(days=dias_atras),
            ))
            session.commit()

    def test_anomalia_real_detectada_dispara_alerta_ponta_a_ponta(self):
        for _ in range(6):
            self._evento_em("realtime.finance", 0.30, dias_atras=1)   # janela atual — caro
            self._evento_em("realtime.finance", 0.01, dias_atras=10)  # janela anterior — barato

        anomalias = database.detectar_anomalias_custo(dias_janela=7, limiar_multiplicador=3.0)
        self.assertEqual(len(anomalias), 1)

        with patch.object(alertas, "alertar") as mock_alertar:
            for a in anomalias:
                alertas.verificar_anomalia(a["feature"], a["media_atual_usd"], a["media_anterior_usd"], a["multiplicador"])
        mock_alertar.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
