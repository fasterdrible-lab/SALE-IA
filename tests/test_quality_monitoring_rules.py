"""
Testes — agent/quality_monitoring_rules.py

Tarefa 19.1 do "PROMPT MESTRE — SALE-IA V2" (Quality Monitoring).

Run:
    python -m unittest tests.test_quality_monitoring_rules -v
"""
import unittest

from agent.quality_monitoring_rules import (
    QUALITY_METRIC_SEM_GABARITO,
    calcular_event_precision,
    calcular_evidence_coverage,
    calcular_framework_accuracy,
    calcular_hallucination_rate,
    calcular_objection_precision,
    calcular_recommendation_relevance,
)


class GapSemGabaritoTest(unittest.TestCase):
    """As 6 métricas exigem gabarito real (Fase 20) — nenhuma pode
    virar número inventado."""

    def test_sinaliza_indisponivel_com_motivo(self):
        self.assertFalse(QUALITY_METRIC_SEM_GABARITO["disponivel"])
        self.assertTrue(QUALITY_METRIC_SEM_GABARITO["motivo"])


class CalcularEventPrecisionTest(unittest.TestCase):
    def test_precisao_normal(self):
        self.assertEqual(calcular_event_precision(8, 2), 0.8)

    def test_sem_predicoes_retorna_none(self):
        self.assertIsNone(calcular_event_precision(0, 0))

    def test_todas_erradas_precisao_zero(self):
        self.assertEqual(calcular_event_precision(0, 5), 0.0)

    def test_todas_certas_precisao_um(self):
        self.assertEqual(calcular_event_precision(5, 0), 1.0)


class CalcularObjectionPrecisionTest(unittest.TestCase):
    def test_mesma_formula_de_event_precision_dominio_diferente(self):
        self.assertEqual(calcular_objection_precision(3, 1), 0.75)


class CalcularFrameworkAccuracyTest(unittest.TestCase):
    def test_acuracia_normal(self):
        self.assertEqual(calcular_framework_accuracy(7, 10), 0.7)

    def test_sem_avaliacoes_retorna_none(self):
        self.assertIsNone(calcular_framework_accuracy(0, 0))


class CalcularRecommendationRelevanceTest(unittest.TestCase):
    def test_relevancia_normal(self):
        self.assertEqual(calcular_recommendation_relevance(9, 12), 0.75)

    def test_sem_avaliacoes_retorna_none(self):
        self.assertIsNone(calcular_recommendation_relevance(0, 0))


class CalcularHallucinationRateTest(unittest.TestCase):
    def test_taxa_normal(self):
        self.assertEqual(calcular_hallucination_rate(2, 20), 0.1)

    def test_zero_alucinacao(self):
        self.assertEqual(calcular_hallucination_rate(0, 20), 0.0)

    def test_sem_afirmacoes_retorna_none(self):
        self.assertIsNone(calcular_hallucination_rate(0, 0))


class CalcularEvidenceCoverageTest(unittest.TestCase):
    def test_cobertura_normal(self):
        self.assertEqual(calcular_evidence_coverage(18, 20), 0.9)

    def test_cobertura_total(self):
        self.assertEqual(calcular_evidence_coverage(20, 20), 1.0)

    def test_sem_afirmacoes_retorna_none(self):
        self.assertIsNone(calcular_evidence_coverage(0, 0))


if __name__ == "__main__":
    unittest.main()
