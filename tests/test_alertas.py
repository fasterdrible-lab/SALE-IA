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


if __name__ == "__main__":
    unittest.main(verbosity=2)
