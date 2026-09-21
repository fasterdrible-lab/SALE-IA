"""
Testes do catálogo de preços por modelo (Cost Intelligence Fase 1).

Run:
    python -m unittest tests.test_pricing_catalog -v
"""

import os
import unittest
from unittest.mock import patch

from api import pricing_catalog


class PricingCatalogTest(unittest.TestCase):
    def test_modelo_catalogado_retorna_preco_especifico(self):
        preco = pricing_catalog.obter_preco("openai", "gpt-4o")
        self.assertEqual(preco.provider, "openai")
        self.assertEqual(preco.model, "gpt-4o")
        self.assertEqual(preco.input_per_million, 2.50)
        self.assertEqual(preco.output_per_million, 10.0)
        self.assertEqual(preco.source, "openai_pricing_2026-05")

    def test_modelo_desconhecido_cai_no_fallback_do_provider(self):
        preco = pricing_catalog.obter_preco("openai", "gpt-99-nao-existe")
        self.assertEqual(preco.input_per_million, 5.0)
        self.assertEqual(preco.output_per_million, 15.0)
        self.assertEqual(preco.source, "fallback_provider_generico")

    def test_provider_desconhecido_cai_no_fallback_padrao(self):
        preco = pricing_catalog.obter_preco("provider-inexistente", "modelo-x")
        self.assertEqual(preco.source, "fallback_provider_generico")
        self.assertEqual(preco.input_per_million, pricing_catalog._DEFAULT_FALLBACK.input_per_million)

    def test_todos_os_precos_tem_proveniencia(self):
        for chave in (
            ("deepseek", "deepseek-chat"),
            ("anthropic", "claude-sonnet-4-20250514"),
            ("anthropic", "claude-sonnet-4-6"),
            ("gemini", "gemini-2.0-flash"),
        ):
            preco = pricing_catalog.obter_preco(*chave)
            self.assertTrue(preco.source)
            self.assertTrue(preco.effective_date)

    def test_env_override_tem_prioridade_sobre_catalogo(self):
        with patch.dict(os.environ, {"PRICE_OPENAI_GPT_4O_INPUT_PER_MILLION": "1.23"}, clear=False):
            preco = pricing_catalog.obter_preco("openai", "gpt-4o")
        self.assertEqual(preco.input_per_million, 1.23)
        self.assertEqual(preco.output_per_million, 10.0)  # não sobrescrito, mantém o catálogo
        self.assertEqual(preco.source, "env_override")

    def test_env_override_invalido_e_ignorado(self):
        with patch.dict(os.environ, {"PRICE_OPENAI_GPT_4O_INPUT_PER_MILLION": "nao-e-numero"}, clear=False):
            preco = pricing_catalog.obter_preco("openai", "gpt-4o")
        self.assertEqual(preco.input_per_million, 2.50)
        self.assertEqual(preco.source, "openai_pricing_2026-05")

    def test_cached_rate_efetivo_usa_taxa_propria_quando_existe(self):
        preco = pricing_catalog.obter_preco("openai", "gpt-4o")
        self.assertEqual(pricing_catalog.cached_rate_efetivo(preco), 1.25)

    def test_cached_rate_efetivo_usa_desconto_padrao_sem_taxa_propria(self):
        preco = pricing_catalog.obter_preco("openai", "gpt-99-nao-existe")
        self.assertIsNone(preco.cached_input_per_million)
        self.assertAlmostEqual(pricing_catalog.cached_rate_efetivo(preco), 5.0 * 0.1)

    # ── Variantes "economy" (Cost Router, Fase 4) ──

    def test_gpt_4o_mini_tem_preco_proprio(self):
        preco = pricing_catalog.obter_preco("openai", "gpt-4o-mini")
        self.assertEqual(preco.input_per_million, 0.15)
        self.assertEqual(preco.output_per_million, 0.60)
        self.assertNotEqual(preco.source, "fallback_provider_generico")

    def test_claude_haiku_tem_preco_proprio(self):
        preco = pricing_catalog.obter_preco("anthropic", "claude-3-5-haiku-20241022")
        self.assertEqual(preco.input_per_million, 0.80)
        self.assertEqual(preco.output_per_million, 4.00)
        self.assertNotEqual(preco.source, "fallback_provider_generico")


if __name__ == "__main__":
    unittest.main(verbosity=2)
