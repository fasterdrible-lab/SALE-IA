# -*- coding: utf-8 -*-
"""
Testes de agent/seller_benchmark_rules.py — Fase 12 / Tarefa 12.1 do
"PROMPT MESTRE — SALE-IA V2" (Benchmark dos Melhores Vendedores),
início da Fase 12 (Collective Sales Intelligence).

Módulo puro (sem IA, sem banco) — mesmo padrão de
tests/test_win_loss_rules.py, cujas primitivas este módulo reaproveita
diretamente.

Run:
    python -m unittest tests.test_seller_benchmark_rules -v
"""

import unittest

from agent.seller_benchmark_rules import (
    CONTROL_VARIABLES,
    PERFORMANCE_TIERS,
    benchmark_controlado,
    comparar_tiers,
)


def _opps(tier, segment, won, lost):
    return (
        [{"seller_tier": tier, "segment": segment, "status": "won"} for _ in range(won)]
        + [{"seller_tier": tier, "segment": segment, "status": "lost"} for _ in range(lost)]
    )


class ComparacaoBrutaTest(unittest.TestCase):
    def test_3_tiers_agrupados_corretamente(self):
        opportunities = (
            _opps("top", "s", won=40, lost=10)
            + _opps("median", "s", won=25, lost=25)
            + _opps("low", "s", won=10, lost=40)
        )
        resumo = comparar_tiers(opportunities)
        self.assertEqual(set(resumo["grupos"].keys()), set(PERFORMANCE_TIERS))
        self.assertAlmostEqual(resumo["grupos"]["top"]["taxa_conversao"], 0.8)
        self.assertAlmostEqual(resumo["grupos"]["median"]["taxa_conversao"], 0.5)
        self.assertAlmostEqual(resumo["grupos"]["low"]["taxa_conversao"], 0.2)


class ConfundimentoDetectadoTest(unittest.TestCase):
    """Reproduz o dataset sintético clássico já usado em
    test_win_loss_rules.py (Fase 8) — mesma estrutura, agora com
    seller_tier/segment: top parece pior no agregado (78,0% vs 82,6%
    do low), mas é melhor em CADA segmento (93,1%>86,7%; 73,0%>68,75%).
    Exatamente o cenário que a Tarefa 12.1 pede para nunca ser lido
    como "low é melhor vendedor" sem controlar por segmento."""

    def setUp(self):
        self.opportunities = (
            _opps("top", "pequeno", won=81, lost=6)
            + _opps("top", "grande", won=192, lost=71)
            + _opps("low", "pequeno", won=234, lost=36)
            + _opps("low", "grande", won=55, lost=25)
        )

    def test_comparacao_bruta_favorece_low(self):
        resultado = benchmark_controlado(self.opportunities, tier_a="top", tier_b="low")
        grupos = resultado["comparacao_bruta"]["grupos"]
        self.assertLess(grupos["top"]["taxa_conversao"], grupos["low"]["taxa_conversao"])

    def test_dentro_de_cada_segmento_top_e_melhor_confundimento_sinalizado(self):
        resultado = benchmark_controlado(self.opportunities, tier_a="top", tier_b="low", campos_controle=("segment",))
        controle_segment = resultado["controles"]["segment"]
        self.assertTrue(controle_segment["possivel_simpsons_paradox"])
        self.assertIsNotNone(controle_segment["afirmacao"])
        # dentro de cada segmento, top é quem converte mais (direção oposta ao agregado).
        self.assertEqual(set(controle_segment["direcoes_por_segmento"].values()), {"top"})

    def test_afirmacao_nunca_declara_causalidade(self):
        resultado = benchmark_controlado(self.opportunities, tier_a="top", tier_b="low", campos_controle=("segment",))
        afirmacao = resultado["controles"]["segment"]["afirmacao"].lower()
        self.assertNotIn("causa", afirmacao)


class VantagemRealConfirmadaTest(unittest.TestCase):
    """Cenário sem confundimento: top é melhor no agregado E dentro de
    cada segmento — não deve ser sinalizado como paradoxo."""

    def test_sem_reversao_nao_sinaliza_paradoxo(self):
        opportunities = (
            _opps("top", "s", won=40, lost=10)
            + _opps("top", "g", won=35, lost=15)
            + _opps("low", "s", won=20, lost=30)
            + _opps("low", "g", won=15, lost=35)
        )
        resultado = benchmark_controlado(opportunities, tier_a="top", tier_b="low", campos_controle=("segment",))
        self.assertFalse(resultado["controles"]["segment"]["possivel_simpsons_paradox"])
        self.assertIsNone(resultado["controles"]["segment"]["afirmacao"])


class ValidacaoTest(unittest.TestCase):
    def test_tier_invalido_levanta(self):
        with self.assertRaises(ValueError):
            benchmark_controlado([], tier_a="excelente", tier_b="low")

    def test_tiers_iguais_levanta(self):
        with self.assertRaises(ValueError):
            benchmark_controlado([], tier_a="top", tier_b="top")


class ControlesPadraoTest(unittest.TestCase):
    def test_as_4_variaveis_de_controle_literais_sao_usadas_por_padrao(self):
        opportunities = _opps("top", "s", won=1, lost=0) + _opps("low", "s", won=0, lost=1)
        resultado = benchmark_controlado(opportunities)
        self.assertEqual(set(resultado["controles"].keys()), set(CONTROL_VARIABLES))
        self.assertEqual(CONTROL_VARIABLES, ("segment", "lead_source", "ticket", "product"))

    def test_median_e_excluido_ao_comparar_top_x_low(self):
        opportunities = (
            _opps("top", "s", won=10, lost=0)
            + _opps("median", "s", won=999, lost=0)
            + _opps("low", "s", won=0, lost=10)
        )
        resultado = benchmark_controlado(opportunities, tier_a="top", tier_b="low", campos_controle=("segment",))
        grupos = resultado["comparacao_bruta"]["grupos"]
        self.assertNotIn("median", grupos)
        self.assertEqual(grupos["top"]["total"], 10)
        self.assertEqual(grupos["low"]["total"], 10)


if __name__ == "__main__":
    unittest.main()
