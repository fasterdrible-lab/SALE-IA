# -*- coding: utf-8 -*-
"""
Testes de agent/objection_trend_analyzer.py — submódulo do
SalesScienceEngine (Fase 13 do "PROMPT MESTRE — SALE-IA V2").

Módulo puro (sem IA, sem banco) — mesmo padrão de
tests/test_seasonality_rules.py, cujas primitivas de win_loss_rules.py
este módulo também reaproveita.

Run:
    python -m unittest tests.test_objection_trend_analyzer -v
"""

import unittest

from agent.objection_trend_analyzer import TEMPLATE_TENDENCIA_OBJECAO, calcular_tendencias


def _evt(category, period):
    return {"category": category, "period": period}


class TendenciaCrescenteEDecrescenteTest(unittest.TestCase):
    """PRICE cresce (20% -> 75% das objeções), TRUST cai (80% -> 25%)
    entre o período inicial (meses 1-3) e o final (meses 4-6)."""

    def setUp(self):
        self.eventos = (
            [_evt("PRICE", 1) for _ in range(10)] + [_evt("TRUST", 1) for _ in range(40)]
            + [_evt("PRICE", 4) for _ in range(45)] + [_evt("TRUST", 4) for _ in range(15)]
        )
        self.ordem_periodos = [1, 2, 3, 4, 5, 6]

    def test_price_significativo_e_crescente(self):
        resultado = calcular_tendencias(self.eventos, self.ordem_periodos)
        price = resultado["categorias"]["PRICE"]
        self.assertTrue(price["significativo"])
        self.assertEqual(price["direcao"], "crescente")
        self.assertAlmostEqual(price["proporcao_inicio"], 0.2)
        self.assertAlmostEqual(price["proporcao_fim"], 0.75)
        self.assertIsNotNone(price["afirmacao"])

    def test_trust_significativo_e_decrescente(self):
        resultado = calcular_tendencias(self.eventos, self.ordem_periodos)
        trust = resultado["categorias"]["TRUST"]
        self.assertTrue(trust["significativo"])
        self.assertEqual(trust["direcao"], "decrescente")

    def test_totais_por_periodo_batem(self):
        resultado = calcular_tendencias(self.eventos, self.ordem_periodos)
        self.assertEqual(resultado["total_inicio"], 50)
        self.assertEqual(resultado["total_fim"], 60)

    def test_afirmacao_nunca_declara_causalidade(self):
        resultado = calcular_tendencias(self.eventos, self.ordem_periodos)
        afirmacao = resultado["categorias"]["PRICE"]["afirmacao"].lower()
        self.assertNotIn("causa", afirmacao)


class SemTendenciaRealTest(unittest.TestCase):
    def test_proporcao_estavel_nao_e_significativa(self):
        eventos = (
            [_evt("TIMING", 1) for _ in range(26)] + [_evt("OUTRO", 1) for _ in range(24)]
            + [_evt("TIMING", 4) for _ in range(24)] + [_evt("OUTRO", 4) for _ in range(26)]
        )
        resultado = calcular_tendencias(eventos, [1, 2, 3, 4, 5, 6])
        self.assertFalse(resultado["categorias"]["TIMING"]["significativo"])
        self.assertIsNone(resultado["categorias"]["TIMING"]["afirmacao"])


class AmostraInsuficienteTest(unittest.TestCase):
    def test_amostra_pequena_nao_e_significativa_mesmo_com_diferenca_grande(self):
        eventos = [_evt("PRICE", 1) for _ in range(8)] + [_evt("PRICE", 4) for _ in range(2)] + [_evt("OUTRO", 4) for _ in range(8)]
        resultado = calcular_tendencias(eventos, [1, 2, 3, 4, 5, 6])
        self.assertFalse(resultado["categorias"]["PRICE"]["significativo"])


class ValidacaoTest(unittest.TestCase):
    def test_menos_de_2_periodos_levanta(self):
        with self.assertRaises(ValueError):
            calcular_tendencias([_evt("PRICE", 1)], [1])

    def test_lista_de_periodos_vazia_levanta(self):
        with self.assertRaises(ValueError):
            calcular_tendencias([], [])


class TemplateTest(unittest.TestCase):
    def test_template_existe(self):
        self.assertTrue(TEMPLATE_TENDENCIA_OBJECAO)


if __name__ == "__main__":
    unittest.main()
