"""
Testes de agent/outcome_rules.py — Fase 8 / Tarefa 8.1 do "PROMPT
MESTRE — SALE-IA V2" (Outcome Tracking).

Módulo puro (sem IA, sem banco) — mesmo padrão de
tests/test_deal_risk_rules.py / tests/test_meddpicc_rules.py.

Run:
    python -m unittest tests.test_outcome_rules -v
"""

import unittest
from datetime import datetime, timedelta

from agent.outcome_rules import (
    calcular_cycle_days,
    esta_fechada,
    resumo_por_status,
    validar_dados_lost,
    validar_dados_won,
)


class CalcularCycleDaysTest(unittest.TestCase):
    def test_calcula_dias_corretamente(self):
        criada = datetime(2026, 1, 1)
        fechada = datetime(2026, 1, 31)
        self.assertEqual(calcular_cycle_days(criada, fechada), 30)

    def test_mesmo_dia_e_zero(self):
        agora = datetime(2026, 1, 1, 10, 0)
        self.assertEqual(calcular_cycle_days(agora, agora), 0)

    def test_close_date_antes_de_created_at_levanta(self):
        criada = datetime(2026, 1, 31)
        fechada = datetime(2026, 1, 1)
        with self.assertRaises(ValueError):
            calcular_cycle_days(criada, fechada)


class ValidarDadosWonTest(unittest.TestCase):
    def test_dados_completos_nao_levanta(self):
        validar_dados_won({"value": 15000.0, "product": "SALEIA Enterprise", "close_date": datetime.now()})

    def test_sem_value_levanta(self):
        with self.assertRaises(ValueError):
            validar_dados_won({"product": "SALEIA Enterprise", "close_date": datetime.now()})

    def test_value_negativo_levanta(self):
        with self.assertRaises(ValueError):
            validar_dados_won({"value": -100, "product": "SALEIA Enterprise", "close_date": datetime.now()})

    def test_value_zero_nao_levanta(self):
        validar_dados_won({"value": 0, "product": "Plano Gratuito", "close_date": datetime.now()})

    def test_sem_product_levanta(self):
        with self.assertRaises(ValueError):
            validar_dados_won({"value": 100, "product": "", "close_date": datetime.now()})

    def test_sem_close_date_levanta(self):
        with self.assertRaises(ValueError):
            validar_dados_won({"value": 100, "product": "SALEIA Enterprise", "close_date": None})

    def test_close_date_como_string_levanta(self):
        with self.assertRaises(ValueError):
            validar_dados_won({"value": 100, "product": "SALEIA Enterprise", "close_date": "2026-01-01"})


class ValidarDadosLostTest(unittest.TestCase):
    def test_dados_completos_nao_levanta(self):
        validar_dados_lost({"reason": "Sem orcamento", "competitor": "ConcorrenteX"})

    def test_sem_competitor_nao_levanta(self):
        """Nem toda perda vai para um concorrente identificado."""
        validar_dados_lost({"reason": "Projeto cancelado internamente", "competitor": None})

    def test_sem_reason_levanta(self):
        with self.assertRaises(ValueError):
            validar_dados_lost({"reason": "", "competitor": None})

    def test_competitor_tipo_invalido_levanta(self):
        with self.assertRaises(ValueError):
            validar_dados_lost({"reason": "Preco alto", "competitor": 123})


class EstaFechadaTest(unittest.TestCase):
    def test_open_nao_esta_fechada(self):
        self.assertFalse(esta_fechada("open"))

    def test_won_lost_abandoned_estao_fechadas(self):
        for status in ("won", "lost", "abandoned"):
            self.assertTrue(esta_fechada(status))


class ResumoPorStatusTest(unittest.TestCase):
    def test_oportunidade_encerrada_nao_conta_como_aberta(self):
        """Regra de teste literal da Tarefa 8.1: 'uma oportunidade
        encerrada precisa deixar de entrar como aberta em
        estatísticas'."""
        opportunities = [
            {"status": "open"},
            {"status": "open"},
            {"status": "won"},
            {"status": "lost"},
            {"status": "abandoned"},
        ]
        resumo = resumo_por_status(opportunities)
        self.assertEqual(resumo["abertas"], 2)
        self.assertEqual(resumo["fechadas"], 3)
        self.assertEqual(resumo["total"], 5)
        self.assertEqual(resumo["por_status"], {"open": 2, "won": 1, "lost": 1, "abandoned": 1})

    def test_lista_vazia(self):
        resumo = resumo_por_status([])
        self.assertEqual(resumo["abertas"], 0)
        self.assertEqual(resumo["fechadas"], 0)
        self.assertEqual(resumo["total"], 0)

    def test_status_desconhecido_e_ignorado_sem_levantar(self):
        resumo = resumo_por_status([{"status": "qualificando"}])
        self.assertEqual(resumo["total"], 0)


if __name__ == "__main__":
    unittest.main()
