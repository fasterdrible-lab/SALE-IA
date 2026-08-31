"""
Testes do cost engine (Cost Intelligence Fase 1).

Run:
    python -m unittest tests.test_cost_engine -v
"""

import unittest

from api.cost_engine import ProviderUsage, calcular_custo, estimar_usage


class CostEngineCalculoTest(unittest.TestCase):
    def test_calculo_input_output_sem_cache(self):
        usage = ProviderUsage(input_tokens=1_000_000, output_tokens=500_000)
        resultado = calcular_custo("openai", "gpt-4o", usage, "provider")
        # 1_000_000 * 2.50/1M + 500_000 * 10.0/1M = 2.50 + 5.00
        self.assertAlmostEqual(resultado.cost_usd, 7.50, places=6)
        self.assertEqual(resultado.currency, "USD")
        self.assertEqual(resultado.usage_source, "provider")
        self.assertEqual(resultado.price_source, "openai_pricing_2026-05")

    def test_calculo_com_cache_usa_taxa_propria_do_modelo(self):
        usage = ProviderUsage(input_tokens=1_000_000, output_tokens=0, cached_input_tokens=500_000)
        resultado = calcular_custo("openai", "gpt-4o", usage, "provider")
        # 500_000 nao-cache * 2.50/1M + 500_000 cache * 1.25/1M = 1.25 + 0.625
        self.assertAlmostEqual(resultado.cost_usd, 1.875, places=6)
        self.assertEqual(resultado.cached_input_tokens, 500_000)

    def test_calculo_com_cache_sem_taxa_propria_usa_desconto_padrao(self):
        usage = ProviderUsage(input_tokens=1_000_000, output_tokens=0, cached_input_tokens=1_000_000)
        resultado = calcular_custo("openai", "gpt-99-nao-existe", usage, "provider")
        # fallback generico: input=5.0/1M, sem taxa de cache propria -> 10% de 5.0 = 0.5/1M
        self.assertAlmostEqual(resultado.cost_usd, 0.5, places=6)

    def test_cached_tokens_maior_que_input_e_limitado(self):
        usage = ProviderUsage(input_tokens=100, output_tokens=0, cached_input_tokens=999)
        resultado = calcular_custo("openai", "gpt-4o", usage, "provider")
        self.assertEqual(resultado.cached_input_tokens, 100)

    def test_reasoning_tokens_cobrados_como_output(self):
        usage = ProviderUsage(input_tokens=0, output_tokens=0, reasoning_output_tokens=1_000_000)
        resultado = calcular_custo("openai", "gpt-4o", usage, "provider")
        self.assertAlmostEqual(resultado.cost_usd, 10.0, places=6)

    def test_custo_zero_para_usage_zerado(self):
        usage = ProviderUsage(input_tokens=0, output_tokens=0)
        resultado = calcular_custo("deepseek", "deepseek-chat", usage, "estimated")
        self.assertEqual(resultado.cost_usd, 0.0)


class CostEngineEstimativaTest(unittest.TestCase):
    def test_estimativa_char4_identica_a_logica_antiga(self):
        system_prompt = "a" * 40  # 40 chars
        user_content = "b" * 40   # 40 chars -> total 80+1(\n) chars
        resultado_vazio = {}
        usage = estimar_usage(system_prompt, user_content, resultado_vazio)
        texto = f"{system_prompt}\n{user_content}"
        esperado_entrada = max(1, round(len(texto) / 4))
        self.assertEqual(usage.input_tokens, esperado_entrada)
        self.assertEqual(usage.cached_input_tokens, 0)

    def test_estimativa_com_prompts_vazios_retorna_minimo_de_um_token(self):
        # "" + "\n" + "" = "\n" (1 char) -> nunca fica em zero, mesmo comportamento
        # do _estimate_token_count original em api/ai_router.py (max(1, ...)).
        usage = estimar_usage("", "", {})
        self.assertEqual(usage.input_tokens, 1)


    def test_estimativa_usada_em_calcular_custo_produz_usage_source_estimated(self):
        usage = estimar_usage("system", "user", {"ok": True})
        resultado = calcular_custo("gemini", "gemini-2.0-flash", usage, "estimated")
        self.assertEqual(resultado.usage_source, "estimated")
        self.assertGreater(resultado.cost_usd, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
