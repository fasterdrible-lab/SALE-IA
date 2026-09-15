# -*- coding: utf-8 -*-
"""
Testes de agent/sales_science_engine.py — Fase 13 do "PROMPT MESTRE —
SALE-IA V2" (Sales Science Engine).

Módulo puro (sem IA, sem banco). Os testes chamam os módulos reais das
Fases 8-12 (win_loss_rules, seasonality_rules, seller_benchmark_rules,
recommendation_effectiveness_rules, pattern_discovery_rules) para
gerar os resultados de entrada dos wrappers — mesmo padrão de
integração real (sem mock) já usado em outros testes deste roadmap.

Run:
    python -m unittest tests.test_sales_science_engine -v
"""

import unittest

from agent.pattern_discovery_rules import descobrir_padrao
from agent.recommendation_effectiveness_rules import calcular_efetividade_por_estrategia
from agent.sales_science_engine import (
    RECOMMENDED_TEST_PADRAO,
    SALES_SCIENCE_SUBMODULOS,
    SUBMODULOS_IMPLEMENTADOS,
    SUBMODULOS_PENDENTES,
    insight_de_pattern_discovery,
    insight_de_seasonality_engine,
    insight_de_seller_benchmark,
    insight_de_strategy_effectiveness,
    insight_de_win_loss_analyzer,
    montar_insight,
)
from agent.seasonality_rules import detectar_sazonalidade
from agent.seller_benchmark_rules import benchmark_controlado
from agent.win_loss_rules import comparar_por_variavel_categorica


def _opp(status, **campos):
    return {"status": status, **campos}


class VocabularioTest(unittest.TestCase):
    def test_5_implementados_mais_2_pendentes_cobrem_os_7_literais(self):
        self.assertEqual(SUBMODULOS_IMPLEMENTADOS | SUBMODULOS_PENDENTES, set(SALES_SCIENCE_SUBMODULOS))
        self.assertEqual(SUBMODULOS_IMPLEMENTADOS & SUBMODULOS_PENDENTES, set())
        self.assertEqual(len(SALES_SCIENCE_SUBMODULOS), 7)
        self.assertEqual(len(SUBMODULOS_IMPLEMENTADOS), 5)
        self.assertEqual(len(SUBMODULOS_PENDENTES), 2)
        self.assertIn("objection_trend_analyzer", SUBMODULOS_PENDENTES)
        self.assertIn("conversion_driver_analyzer", SUBMODULOS_PENDENTES)


class MontarInsightContratoTest(unittest.TestCase):
    """Regra literal: 'Saída nunca deve ser apenas descobrimos isso'."""

    def _kwargs_validos(self):
        return dict(
            submodulo="win_loss_analyzer",
            insight="X está associado a Y nesta amostra.",
            evidence={"won": 10, "lost": 5},
            sample=15,
            possible_confounders=[],
            recommended_test="Rodar A/B controlado.",
        )

    def test_insight_valido_contem_os_6_campos_literais(self):
        resultado = montar_insight(**self._kwargs_validos())
        for campo in ("insight", "evidence", "sample", "confidence", "possible_confounders", "recommended_test"):
            self.assertIn(campo, resultado)

    def test_submodulo_invalido_levanta(self):
        kwargs = self._kwargs_validos()
        kwargs["submodulo"] = "chutometro"
        with self.assertRaises(ValueError):
            montar_insight(**kwargs)

    def test_insight_vazio_levanta(self):
        kwargs = self._kwargs_validos()
        kwargs["insight"] = ""
        with self.assertRaises(ValueError):
            montar_insight(**kwargs)

    def test_evidence_vazia_levanta(self):
        kwargs = self._kwargs_validos()
        kwargs["evidence"] = {}
        with self.assertRaises(ValueError):
            montar_insight(**kwargs)

    def test_sample_menor_que_1_levanta(self):
        kwargs = self._kwargs_validos()
        kwargs["sample"] = 0
        with self.assertRaises(ValueError):
            montar_insight(**kwargs)

    def test_possible_confounders_ausente_levanta(self):
        kwargs = self._kwargs_validos()
        kwargs["possible_confounders"] = None
        with self.assertRaises(ValueError):
            montar_insight(**kwargs)

    def test_recommended_test_vazio_levanta(self):
        kwargs = self._kwargs_validos()
        kwargs["recommended_test"] = ""
        with self.assertRaises(ValueError):
            montar_insight(**kwargs)

    def test_confidence_fora_de_0_1_levanta(self):
        kwargs = self._kwargs_validos()
        kwargs["confidence"] = 1.5
        with self.assertRaises(ValueError):
            montar_insight(**kwargs)

    def test_confidence_none_e_aceito(self):
        resultado = montar_insight(confidence=None, **self._kwargs_validos())
        self.assertIsNone(resultado["confidence"])


class WinLossAnalyzerWrapperTest(unittest.TestCase):
    def test_grupo_com_amostra_suficiente_vira_insight(self):
        opportunities = (
            [_opp("won", segment="a") for _ in range(35)] + [_opp("lost", segment="a") for _ in range(5)]
        )
        comparacao = comparar_por_variavel_categorica(opportunities, campo="segment")
        resultado = insight_de_win_loss_analyzer(comparacao["grupos"]["a"], campo="segment", valor="a")
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado["submodulo"], "win_loss_analyzer")
        self.assertEqual(resultado["sample"], 40)
        self.assertEqual(resultado["confidence"], 0.95)

    def test_grupo_com_amostra_insuficiente_retorna_none(self):
        opportunities = [_opp("won", segment="a"), _opp("lost", segment="a")]
        comparacao = comparar_por_variavel_categorica(opportunities, campo="segment")
        resultado = insight_de_win_loss_analyzer(comparacao["grupos"]["a"], campo="segment", valor="a")
        self.assertIsNone(resultado)


class SeasonalityEngineWrapperTest(unittest.TestCase):
    def test_periodo_significativo_vira_insight(self):
        # mes 3 elevado (70%, n=100); meses 6-9 no baseline (50%, n=100 cada)
        # -- baseline geral (54%) cai fora do IC de Wilson do mes 3.
        linhas = [{"month": 3, "won": True, "lost": False} for _ in range(70)] + [{"month": 3, "won": False, "lost": True} for _ in range(30)]
        for mes in (6, 7, 8, 9):
            linhas += [{"month": mes, "won": True, "lost": False} for _ in range(50)] + [{"month": mes, "won": False, "lost": True} for _ in range(50)]
        sazonalidade = detectar_sazonalidade(linhas, dimensao="month")
        resultado = insight_de_seasonality_engine(sazonalidade["periodos"][3], dimensao="month", periodo=3)
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado["submodulo"], "seasonality_engine")

    def test_periodo_nao_significativo_retorna_none(self):
        linhas = [{"month": 3, "won": True, "lost": False} for _ in range(15)] + [{"month": 3, "won": False, "lost": True} for _ in range(15)]
        sazonalidade = detectar_sazonalidade(linhas, dimensao="month")
        resultado = insight_de_seasonality_engine(sazonalidade["periodos"][3], dimensao="month", periodo=3)
        self.assertIsNone(resultado)


class SellerBenchmarkWrapperTest(unittest.TestCase):
    def _dataset_com_confundimento(self):
        def linhas(tier, segmento, won, lost):
            return [_opp("won", seller_tier=tier, segment=segmento) for _ in range(won)] + [_opp("lost", seller_tier=tier, segment=segmento) for _ in range(lost)]
        return (
            linhas("top", "pequeno", 81, 6) + linhas("top", "grande", 192, 71)
            + linhas("low", "pequeno", 234, 36) + linhas("low", "grande", 55, 25)
        )

    def test_confundimento_detectado_vira_insight_com_confounder_identificado(self):
        resultado_benchmark = benchmark_controlado(self._dataset_com_confundimento(), tier_a="top", tier_b="low", campos_controle=("segment",))
        resultado = insight_de_seller_benchmark(resultado_benchmark, campo_controle="segment")
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado["possible_confounders"], ["segment"])
        self.assertEqual(resultado["submodulo"], "seller_benchmark")

    def test_sem_confundimento_retorna_none(self):
        def linhas(tier, segmento, won, lost):
            return [_opp("won", seller_tier=tier, segment=segmento) for _ in range(won)] + [_opp("lost", seller_tier=tier, segment=segmento) for _ in range(lost)]
        opportunities = linhas("top", "s", 40, 10) + linhas("top", "g", 35, 15) + linhas("low", "s", 20, 30) + linhas("low", "g", 15, 35)
        resultado_benchmark = benchmark_controlado(opportunities, tier_a="top", tier_b="low", campos_controle=("segment",))
        resultado = insight_de_seller_benchmark(resultado_benchmark, campo_controle="segment")
        self.assertIsNone(resultado)


class StrategyEffectivenessWrapperTest(unittest.TestCase):
    def _evento(self, strategy, stage_advanced):
        return {"strategy": strategy, "state": "USED", "stage_advanced": stage_advanced, "opportunity_result": None}

    def test_estrategia_com_amostra_suficiente_vira_insight(self):
        eventos = [self._evento("SPIN Implication", True) for _ in range(25)] + [self._evento("SPIN Implication", False) for _ in range(10)]
        resumo = calcular_efetividade_por_estrategia(eventos)
        resultado = insight_de_strategy_effectiveness(resumo["SPIN Implication"], strategy="SPIN Implication")
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado["submodulo"], "strategy_effectiveness")
        self.assertEqual(resultado["sample"], 35)

    def test_estrategia_com_amostra_insuficiente_retorna_none(self):
        eventos = [self._evento("Case Similar", True) for _ in range(2)]
        resumo = calcular_efetividade_por_estrategia(eventos)
        resultado = insight_de_strategy_effectiveness(resumo["Case Similar"], strategy="Case Similar")
        self.assertIsNone(resultado)


class PatternDiscoveryWrapperTest(unittest.TestCase):
    def _obs(self, group, exhibited):
        return {"group": group, "exhibited": exhibited}

    def test_diferenca_significativa_vira_insight(self):
        observacoes = (
            [self._obs("top", True) for _ in range(40)] + [self._obs("top", False) for _ in range(10)]
            + [self._obs("control", True) for _ in range(15)] + [self._obs("control", False) for _ in range(35)]
        )
        resultado_padrao = descobrir_padrao(observacoes, hipotese="hipótese de teste")
        resultado = insight_de_pattern_discovery(resultado_padrao)
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado["submodulo"], "pattern_discovery")
        self.assertEqual(resultado["confidence"], 0.95)

    def test_sem_diferenca_significativa_retorna_none(self):
        observacoes = [self._obs("top", True) for _ in range(25)] + [self._obs("top", False) for _ in range(25)] + [self._obs("control", True) for _ in range(24)] + [self._obs("control", False) for _ in range(26)]
        resultado_padrao = descobrir_padrao(observacoes, hipotese="hipótese de teste")
        resultado = insight_de_pattern_discovery(resultado_padrao)
        self.assertIsNone(resultado)


class RecommendedTestPadraoTest(unittest.TestCase):
    def test_template_padrao_existe_e_nao_e_vazio(self):
        self.assertTrue(RECOMMENDED_TEST_PADRAO)
        self.assertIsInstance(RECOMMENDED_TEST_PADRAO, str)


if __name__ == "__main__":
    unittest.main()
