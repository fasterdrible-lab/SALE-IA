"""
Testes de api/otimizacao_shadow.py (Cost Intelligence Fase 5, shadow mode).

Run:
    python -m unittest tests.test_otimizacao_shadow -v
"""

import os
import unittest
from unittest.mock import patch

from api import otimizacao_shadow as ot
from api.cost_engine import ProviderUsage


class CacheShadowTest(unittest.TestCase):
    def setUp(self):
        ot._cache_respostas.clear()

    def test_primeira_chamada_nunca_e_hit(self):
        d = ot._avaliar_cache_shadow("feat.x", "system", "user", 0.01)
        self.assertIsNone(d)

    def test_chamada_identica_repetida_e_hit(self):
        ot._avaliar_cache_shadow("feat.x", "system", "user", 0.01)
        d = ot._avaliar_cache_shadow("feat.x", "system", "user", 0.02)
        self.assertIsNotNone(d)
        self.assertEqual(d["tipo"], "cache_hit")
        self.assertEqual(d["economia_estimada_usd"], 0.02)  # economiza o custo da chamada ATUAL

    def test_chamada_com_conteudo_diferente_nao_e_hit(self):
        ot._avaliar_cache_shadow("feat.x", "system", "user A", 0.01)
        d = ot._avaliar_cache_shadow("feat.x", "system", "user B", 0.01)
        self.assertIsNone(d)

    def test_chamada_expirada_fora_do_ttl_nao_e_hit(self):
        ot._avaliar_cache_shadow("feat.x", "system", "user", 0.01)
        chave = ot._chave_cache("feat.x", "system", "user")
        ot._cache_respostas[chave]["ts"] -= (ot._CACHE_TTL_S + 1)
        d = ot._avaliar_cache_shadow("feat.x", "system", "user", 0.02)
        self.assertIsNone(d)

    def test_cache_respeita_tamanho_maximo(self):
        for i in range(ot._CACHE_MAX_ENTRIES + 10):
            ot._avaliar_cache_shadow(f"feat.{i}", "system", f"user{i}", 0.01)
        self.assertLessEqual(len(ot._cache_respostas), ot._CACHE_MAX_ENTRIES)


class ContextoShadowTest(unittest.TestCase):
    def test_abaixo_do_limite_nao_gera_decisao(self):
        with patch.dict(os.environ, {"OTIMIZACAO_CONTEXTO_MAX_CHARS": "1000"}):
            usage = ProviderUsage(input_tokens=100, output_tokens=50)
            d = ot._avaliar_contexto_shadow("openai", "gpt-4o", "s" * 100, "u" * 100, usage, "provider", 0.01)
        self.assertIsNone(d)

    def test_acima_do_limite_calcula_economia_via_cost_engine(self):
        with patch.dict(os.environ, {"OTIMIZACAO_CONTEXTO_MAX_CHARS": "100"}):
            usage = ProviderUsage(input_tokens=1000, output_tokens=500)
            d = ot._avaliar_contexto_shadow("openai", "gpt-4o", "s" * 100, "u" * 900, usage, "provider", 1.0)
        self.assertIsNotNone(d)
        self.assertEqual(d["tipo"], "contexto_truncado")
        self.assertGreater(d["economia_estimada_usd"], 0)
        self.assertLess(d["economia_estimada_usd"], 1.0)  # nunca economiza mais que o custo real total


class LoopCaroShadowTest(unittest.TestCase):
    def setUp(self):
        ot._custo_reuniao_cache.clear()

    def test_sem_env_configurado_nunca_ativa(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OTIMIZACAO_LOOP_MAX_CUSTO_USD", None)
            with patch("api.database.custo_por_reuniao", return_value={"total_usd": 999.0}):
                d = ot._avaliar_loop_caro_shadow("m1", "realtime.coach")
        self.assertIsNone(d)

    def test_sem_meeting_id_nunca_ativa(self):
        with patch.dict(os.environ, {"OTIMIZACAO_LOOP_MAX_CUSTO_USD": "1.0"}):
            d = ot._avaliar_loop_caro_shadow(None, "realtime.coach")
        self.assertIsNone(d)

    def test_abaixo_do_limite_nao_ativa(self):
        with patch.dict(os.environ, {"OTIMIZACAO_LOOP_MAX_CUSTO_USD": "10.0"}):
            with patch("api.database.custo_por_reuniao", return_value={"total_usd": 1.0}):
                d = ot._avaliar_loop_caro_shadow("m1", "realtime.coach")
        self.assertIsNone(d)

    def test_acima_do_limite_ativa(self):
        with patch.dict(os.environ, {"OTIMIZACAO_LOOP_MAX_CUSTO_USD": "1.0"}):
            with patch("api.database.custo_por_reuniao", return_value={"total_usd": 5.0}) as mock_custo:
                d = ot._avaliar_loop_caro_shadow("m1", "realtime.coach")
        self.assertIsNotNone(d)
        self.assertEqual(d["tipo"], "loop_bloqueado")
        mock_custo.assert_called_once()

    def test_custo_por_reuniao_e_cacheado_60s(self):
        with patch.dict(os.environ, {"OTIMIZACAO_LOOP_MAX_CUSTO_USD": "1.0"}):
            with patch("api.database.custo_por_reuniao", return_value={"total_usd": 5.0}) as mock_custo:
                ot._avaliar_loop_caro_shadow("m1", "realtime.coach")
                ot._avaliar_loop_caro_shadow("m1", "realtime.coach")
                ot._avaliar_loop_caro_shadow("m1", "realtime.coach")
        mock_custo.assert_called_once()


class AvaliarOtimizacoesShadowTest(unittest.TestCase):
    def setUp(self):
        ot._cache_respostas.clear()
        ot._custo_reuniao_cache.clear()
        self._usage = ProviderUsage(input_tokens=1000, output_tokens=500)

    def test_nunca_lanca_mesmo_com_banco_quebrado(self):
        with patch("api.database.registrar_decisao_otimizacao", side_effect=RuntimeError("boom")):
            try:
                ot.avaliar_otimizacoes_shadow(
                    feature="realtime.coach", provider="openai", model="gpt-4o",
                    system_prompt="s", user_content="u", usage=self._usage,
                    usage_source="provider", custo_real_usd=0.01, meeting_id="m1",
                )
            except Exception as exc:  # pragma: no cover
                self.fail(f"avaliar_otimizacoes_shadow propagou excecao: {exc}")

    def test_registra_cache_hit_na_segunda_chamada_identica(self):
        with patch("api.database.registrar_decisao_otimizacao") as mock_reg:
            ot.avaliar_otimizacoes_shadow(
                feature="realtime.disc", provider="openai", model="gpt-4o",
                system_prompt="s", user_content="u", usage=self._usage,
                usage_source="provider", custo_real_usd=0.01,
            )
            mock_reg.reset_mock()
            ot.avaliar_otimizacoes_shadow(
                feature="realtime.disc", provider="openai", model="gpt-4o",
                system_prompt="s", user_content="u", usage=self._usage,
                usage_source="provider", custo_real_usd=0.02,
            )
        tipos = [c.kwargs["tipo"] for c in mock_reg.call_args_list]
        self.assertIn("cache_hit", tipos)

    def test_sem_nenhuma_condicao_nao_registra_nada(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OTIMIZACAO_LOOP_MAX_CUSTO_USD", None)
            os.environ["OTIMIZACAO_CONTEXTO_MAX_CHARS"] = "999999"
            with patch("api.database.registrar_decisao_otimizacao") as mock_reg:
                ot.avaliar_otimizacoes_shadow(
                    feature="realtime.coach", provider="openai", model="gpt-4o",
                    system_prompt="s", user_content="u", usage=self._usage,
                    usage_source="provider", custo_real_usd=0.01,
                )
        mock_reg.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
