"""
Testes — agent/observability_metrics_rules.py

Fase 19 do "PROMPT MESTRE — SALE-IA V2" (Observabilidade).

Run:
    python -m unittest tests.test_observability_metrics_rules -v
"""
import unittest

from agent.observability_metrics_rules import (
    RAG_LATENCY_NAO_CAPTURADA,
    RECOMMENDATION_EFFECTIVENESS_NAO_DISPONIVEL,
    calcular_estatisticas_latencia,
    calcular_taxa,
)


class CalcularEstatisticasLatenciaTest(unittest.TestCase):
    def test_lista_vazia_devolve_tudo_none(self):
        resultado = calcular_estatisticas_latencia([])
        self.assertEqual(resultado["amostra"], 0)
        self.assertIsNone(resultado["media_ms"])
        self.assertIsNone(resultado["p50_ms"])
        self.assertIsNone(resultado["p95_ms"])

    def test_lista_so_com_none_devolve_tudo_none(self):
        resultado = calcular_estatisticas_latencia([None, None])
        self.assertEqual(resultado["amostra"], 0)

    def test_ignora_none_misturado_com_valores_reais(self):
        resultado = calcular_estatisticas_latencia([100, None, 200])
        self.assertEqual(resultado["amostra"], 2)
        self.assertEqual(resultado["media_ms"], 150.0)

    def test_media_minimo_maximo(self):
        resultado = calcular_estatisticas_latencia([100, 200, 300])
        self.assertEqual(resultado["media_ms"], 200.0)
        self.assertEqual(resultado["minimo_ms"], 100)
        self.assertEqual(resultado["maximo_ms"], 300)

    def test_amostra_unica(self):
        resultado = calcular_estatisticas_latencia([500])
        self.assertEqual(resultado["amostra"], 1)
        self.assertEqual(resultado["media_ms"], 500.0)
        self.assertEqual(resultado["p50_ms"], 500)
        self.assertEqual(resultado["p95_ms"], 500)

    def test_p95_maior_ou_igual_a_p50(self):
        valores = list(range(1, 101))  # 1..100
        resultado = calcular_estatisticas_latencia(valores)
        self.assertGreaterEqual(resultado["p95_ms"], resultado["p50_ms"])
        self.assertEqual(resultado["amostra"], 100)


class CalcularTaxaTest(unittest.TestCase):
    def test_denominador_zero_retorna_none(self):
        self.assertIsNone(calcular_taxa(0, 0))
        self.assertIsNone(calcular_taxa(5, 0))

    def test_taxa_normal(self):
        self.assertEqual(calcular_taxa(1, 4), 0.25)

    def test_taxa_zero_numerador(self):
        self.assertEqual(calcular_taxa(0, 10), 0.0)

    def test_taxa_arredondada(self):
        self.assertEqual(calcular_taxa(1, 3), 0.3333)


class GapsDocumentadosTest(unittest.TestCase):
    """RAG latency e recommendation effectiveness nunca devem virar um
    numero inventado — sempre um dict explicito sinalizando o gap."""

    def test_rag_latency_sinaliza_nao_capturado(self):
        self.assertFalse(RAG_LATENCY_NAO_CAPTURADA["capturado"])
        self.assertTrue(RAG_LATENCY_NAO_CAPTURADA["motivo"])

    def test_recommendation_effectiveness_sinaliza_indisponivel(self):
        self.assertFalse(RECOMMENDATION_EFFECTIVENESS_NAO_DISPONIVEL["disponivel"])
        self.assertTrue(RECOMMENDATION_EFFECTIVENESS_NAO_DISPONIVEL["motivo"])


if __name__ == "__main__":
    unittest.main()
