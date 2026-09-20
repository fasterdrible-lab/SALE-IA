"""
Testes de agent/seller_coaching_rules.py — Fase 22 (Frontend) / bloco
"Seller Coaching" do "PROMPT MESTRE — SALE-IA V2".

Módulo puro (sem IA, sem banco) — mesmo padrão de
tests/test_opportunity_intelligence_rules.py. Diferente daquele módulo,
aqui os 8 campos são SEMPRE gap (investigação prévia confirmou que
nenhum tem dado real hoje).

Run:
    python -m unittest tests.test_seller_coaching_rules -v
"""

import unittest

from agent.seller_coaching_rules import (
    NEGOTIATION_NAO_DISPONIVEL,
    NEXT_STEP_DISCIPLINE_NAO_DISPONIVEL,
    OBJECTION_HANDLING_NAO_DISPONIVEL,
    QUALIFICATION_NAO_DISPONIVEL,
    QUESTION_QUALITY_NAO_DISPONIVEL,
    SELLER_COACHING_CAMPOS,
    SPIN_COVERAGE_NAO_DISPONIVEL,
    TALK_RATIO_NAO_DISPONIVEL,
    TREND_NAO_DISPONIVEL,
    montar_seller_coaching,
)


class EstruturaCompletaTest(unittest.TestCase):
    def test_todas_as_8_chaves_literais_presentes_mais_seller_id(self):
        resultado = montar_seller_coaching("seller-1")
        chaves_esperadas = set(SELLER_COACHING_CAMPOS) | {"seller_id"}
        self.assertEqual(set(resultado.keys()), chaves_esperadas)

    def test_exatamente_8_campos_literais(self):
        self.assertEqual(len(SELLER_COACHING_CAMPOS), 8)

    def test_seller_id_ecoado(self):
        resultado = montar_seller_coaching("seller-xyz")
        self.assertEqual(resultado["seller_id"], "seller-xyz")


class TodosOsCamposSaoGapTest(unittest.TestCase):
    """Nenhum dos 8 campos tem dado real hoje — todos vêm sempre com o
    mesmo dict de gap, disponivel=False e motivo não vazio."""

    def test_todos_os_campos_sao_gap_explicito(self):
        resultado = montar_seller_coaching("seller-1")
        for campo in SELLER_COACHING_CAMPOS:
            self.assertFalse(resultado[campo]["disponivel"], campo)
            self.assertTrue(resultado[campo]["motivo"], campo)

    def test_valores_batem_com_as_constantes_literais(self):
        resultado = montar_seller_coaching("seller-1")
        self.assertEqual(resultado["talk_ratio"], TALK_RATIO_NAO_DISPONIVEL)
        self.assertEqual(resultado["question_quality"], QUESTION_QUALITY_NAO_DISPONIVEL)
        self.assertEqual(resultado["spin_coverage"], SPIN_COVERAGE_NAO_DISPONIVEL)
        self.assertEqual(resultado["qualification"], QUALIFICATION_NAO_DISPONIVEL)
        self.assertEqual(resultado["objection_handling"], OBJECTION_HANDLING_NAO_DISPONIVEL)
        self.assertEqual(resultado["negotiation"], NEGOTIATION_NAO_DISPONIVEL)
        self.assertEqual(resultado["next_step_discipline"], NEXT_STEP_DISCIPLINE_NAO_DISPONIVEL)
        self.assertEqual(resultado["trend"], TREND_NAO_DISPONIVEL)

    def test_gaps_sao_copias_nunca_a_mesma_referencia_mutavel(self):
        r1 = montar_seller_coaching("seller-1")
        r1["talk_ratio"]["motivo"] = "mutado"
        r2 = montar_seller_coaching("seller-1")
        self.assertNotEqual(r2["talk_ratio"]["motivo"], "mutado")

    def test_chamadas_diferentes_seller_id_nao_compartilham_estado(self):
        r1 = montar_seller_coaching("seller-a")
        r2 = montar_seller_coaching("seller-b")
        r1["spin_coverage"]["motivo"] = "mutado"
        self.assertNotEqual(r2["spin_coverage"]["motivo"], "mutado")


if __name__ == "__main__":
    unittest.main()
