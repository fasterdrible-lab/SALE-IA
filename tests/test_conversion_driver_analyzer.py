# -*- coding: utf-8 -*-
"""
Testes de agent/conversion_driver_analyzer.py — submódulo do
SalesScienceEngine (Fase 13 do "PROMPT MESTRE — SALE-IA V2").

Módulo puro (sem IA, sem banco) — mesmo padrão de
tests/test_win_loss_rules.py, cujas primitivas este módulo reaproveita
diretamente.

Run:
    python -m unittest tests.test_conversion_driver_analyzer -v
"""

import unittest

from agent.conversion_driver_analyzer import TEMPLATE_DRIVER, ranquear_drivers


def _dataset():
    # segment: enterprise 70/30 (70%), smb 30/70 (30%) -- baseline geral 50%.
    # product: A e B ficam exatamente no baseline (50%) por construção --
    # nao devem aparecer no ranking (sem sinal real).
    opportunities = (
        [{"status": "won", "segment": "enterprise"} for _ in range(70)]
        + [{"status": "lost", "segment": "enterprise"} for _ in range(30)]
        + [{"status": "won", "segment": "smb"} for _ in range(30)]
        + [{"status": "lost", "segment": "smb"} for _ in range(70)]
    )
    for i, o in enumerate(opportunities):
        o["product"] = "A" if i % 2 == 0 else "B"
    return opportunities


class RankingTest(unittest.TestCase):
    def test_enterprise_e_smb_aparecem_no_ranking_ordenados_por_magnitude(self):
        drivers = ranquear_drivers(_dataset(), campos=["segment", "product"])
        campos_valores = [(d["campo"], d["valor"]) for d in drivers]
        self.assertIn(("segment", "enterprise"), campos_valores)
        self.assertIn(("segment", "smb"), campos_valores)

    def test_product_sem_sinal_real_nao_entra_no_ranking(self):
        drivers = ranquear_drivers(_dataset(), campos=["segment", "product"])
        campos = {d["campo"] for d in drivers}
        self.assertNotIn("product", campos)

    def test_diferenca_vs_baseline_bate_com_calculo_manual(self):
        drivers = ranquear_drivers(_dataset(), campos=["segment"])
        por_valor = {d["valor"]: d for d in drivers}
        self.assertAlmostEqual(por_valor["enterprise"]["diferenca_vs_baseline"], 0.2)
        self.assertAlmostEqual(por_valor["smb"]["diferenca_vs_baseline"], -0.2)
        self.assertAlmostEqual(por_valor["enterprise"]["baseline_taxa_conversao"], 0.5)

    def test_ranking_ordenado_por_magnitude_absoluta_decrescente(self):
        drivers = ranquear_drivers(_dataset(), campos=["segment"])
        magnitudes = [abs(d["diferenca_vs_baseline"]) for d in drivers]
        self.assertEqual(magnitudes, sorted(magnitudes, reverse=True))

    def test_afirmacao_nunca_declara_causalidade(self):
        drivers = ranquear_drivers(_dataset(), campos=["segment"])
        for d in drivers:
            self.assertNotIn("causa", d["afirmacao"].lower())


class SemBaselineTest(unittest.TestCase):
    def test_sem_nenhum_won_lost_retorna_lista_vazia(self):
        opportunities = [{"status": "open", "segment": "enterprise"}]
        drivers = ranquear_drivers(opportunities, campos=["segment"])
        self.assertEqual(drivers, [])

    def test_lista_de_oportunidades_vazia_retorna_lista_vazia(self):
        self.assertEqual(ranquear_drivers([], campos=["segment"]), [])


class TemplateTest(unittest.TestCase):
    def test_template_existe(self):
        self.assertTrue(TEMPLATE_DRIVER)


if __name__ == "__main__":
    unittest.main()
