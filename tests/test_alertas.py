"""
Testes de agent/alertas.py::verificar_orcamento (Budget Guard, Cost
Intelligence Fase 3).

Run:
    python -m unittest tests.test_alertas -v
"""

import unittest
from unittest.mock import patch

from agent import alertas


class VerificarOrcamentoTest(unittest.TestCase):
    def setUp(self):
        # cooldown e por-processo (dict em modulo) — isola entre testes
        alertas._last_alerta.clear()

    def test_sem_limite_configurado_nao_alerta(self):
        with patch.object(alertas, "alertar") as m:
            alertas.verificar_orcamento(gasto_mes_usd=999.0, limite_usd=None)
            alertas.verificar_orcamento(gasto_mes_usd=999.0, limite_usd=0)
            alertas.verificar_orcamento(gasto_mes_usd=999.0, limite_usd=-5)
        m.assert_not_called()

    def test_abaixo_de_80pct_nao_alerta(self):
        with patch.object(alertas, "alertar") as m:
            alertas.verificar_orcamento(gasto_mes_usd=50.0, limite_usd=100.0)
        m.assert_not_called()

    def test_80pct_dispara_aviso(self):
        with patch.object(alertas, "alertar") as m:
            alertas.verificar_orcamento(gasto_mes_usd=80.0, limite_usd=100.0)
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertIn("80%", args[0])
        self.assertEqual(kwargs.get("nivel"), "⚠️")

    def test_100pct_dispara_critico_nao_aviso(self):
        with patch.object(alertas, "alertar") as m:
            alertas.verificar_orcamento(gasto_mes_usd=120.0, limite_usd=100.0)
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertEqual(kwargs.get("nivel"), "🔴")

    def test_cooldown_evita_alerta_repetido(self):
        with patch.object(alertas, "alertar") as m:
            alertas.verificar_orcamento(gasto_mes_usd=80.0, limite_usd=100.0)
            alertas.verificar_orcamento(gasto_mes_usd=85.0, limite_usd=100.0)
        m.assert_called_once()

    def test_100pct_e_80pct_sao_chaves_de_cooldown_independentes(self):
        with patch.object(alertas, "alertar") as m:
            alertas.verificar_orcamento(gasto_mes_usd=80.0, limite_usd=100.0)  # dispara 80%
            alertas.verificar_orcamento(gasto_mes_usd=101.0, limite_usd=100.0)  # dispara 100% (chave diferente)
        self.assertEqual(m.call_count, 2)


class VerificarAnomaliaTest(unittest.TestCase):
    def setUp(self):
        alertas._last_alerta.clear()

    def test_dispara_alerta(self):
        with patch.object(alertas, "alertar") as m:
            alertas.verificar_anomalia("realtime.coach", media_atual=0.30, media_anterior=0.01, multiplicador=30.0)
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertIn("realtime.coach", args[0])
        self.assertEqual(kwargs.get("nivel"), "🟠")

    def test_cooldown_e_por_feature(self):
        with patch.object(alertas, "alertar") as m:
            alertas.verificar_anomalia("realtime.coach", 0.30, 0.01, 30.0)
            alertas.verificar_anomalia("realtime.coach", 0.31, 0.01, 31.0)  # mesma feature — cooldown
            alertas.verificar_anomalia("realtime.disc", 0.30, 0.01, 30.0)  # feature diferente — dispara
        self.assertEqual(m.call_count, 2)


class EscalarParaHumanoTest(unittest.TestCase):
    def setUp(self):
        alertas._last_alerta.clear()

    def test_dispara_alerta_com_urgencia_do_escalonamento(self):
        escalonamento = {
            "acao": "enviar_followup",
            "fronteira": "HUMAN_APPROVAL",
            "motivo": "desconto de 15% acima do limite de 5%",
            "urgencia": "⚠️",
            "contexto": {},
        }
        with patch.object(alertas, "alertar") as m:
            alertas.escalar_para_humano(escalonamento)
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertIn("enviar_followup", args[0])
        self.assertIn("HUMAN_APPROVAL", args[0])
        self.assertIn("desconto de 15%", args[0])
        self.assertEqual(kwargs.get("nivel"), "⚠️")

    def test_contexto_aparece_na_mensagem(self):
        escalonamento = {
            "acao": "alteracao_juridica",
            "fronteira": "HUMAN_REQUIRED",
            "motivo": "cláusula contratual não padrão",
            "urgencia": "🔴",
            "contexto": {"opportunity_id": 42},
        }
        with patch.object(alertas, "alertar") as m:
            alertas.escalar_para_humano(escalonamento)
        args, _ = m.call_args
        self.assertIn("opportunity_id=42", args[0])

    def test_nunca_tem_cooldown_dispara_toda_vez(self):
        escalonamento = {
            "acao": "promessa_nao_documentada",
            "fronteira": "FORBIDDEN",
            "motivo": "IA tentou prometer resultado sem base",
            "urgencia": "🔴",
            "contexto": {},
        }
        with patch.object(alertas, "alertar") as m:
            alertas.escalar_para_humano(escalonamento)
            alertas.escalar_para_humano(escalonamento)
            alertas.escalar_para_humano(escalonamento)
        self.assertEqual(m.call_count, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
