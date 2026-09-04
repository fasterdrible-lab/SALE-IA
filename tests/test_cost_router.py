"""
Testes de api/cost_router.py (Cost Intelligence Fase 4, ATIVA em
producao desde V.1.4.61).

Run:
    python -m unittest tests.test_cost_router -v
"""

import os
import unittest
from unittest.mock import patch

from api import ai_features as feat
from api import cost_router
from api.cost_engine import ProviderUsage


class ClassificarComplexidadeTest(unittest.TestCase):
    def test_features_simples(self):
        for f in (feat.REALTIME_DISC, feat.REPORT_PERFIL_DISC, feat.TACTIQ_PERFIL_DISC):
            self.assertEqual(cost_router.classificar_complexidade(f), "simples")

    def test_features_complexas(self):
        for f in (feat.REPORT_DIAGNOSTICO_FINANCEIRO, feat.REPORT_RECAPITULACAO,
                   feat.PLAYBOOK_GERACAO, feat.KNOWLEDGE_COMPILER_EXTRACAO):
            self.assertEqual(cost_router.classificar_complexidade(f), "complexa")

    def test_features_padrao(self):
        for f in (feat.REALTIME_COACH, feat.REALTIME_FINANCE, feat.REALTIME_CLOSER):
            self.assertEqual(cost_router.classificar_complexidade(f), "padrao")

    def test_feature_desconhecida_cai_em_padrao(self):
        self.assertEqual(cost_router.classificar_complexidade("feature.nova.do.futuro"), "padrao")


class ModoAtualTest(unittest.TestCase):
    def setUp(self):
        cost_router._modo_cache["modo"] = None
        cost_router._modo_cache["ts"] = 0.0

    def test_sem_orcamento_configurado_e_sempre_normal(self):
        with patch("api.database.obter_orcamento_ia", return_value=None):
            self.assertEqual(cost_router.modo_atual(), "normal")

    def test_abaixo_de_80pct_e_normal(self):
        with patch("api.database.obter_orcamento_ia", return_value={"limite_mensal_usd": 100.0}), \
             patch("api.database.gasto_mes_usd", return_value=50.0):
            self.assertEqual(cost_router.modo_atual(), "normal")

    def test_80pct_ou_mais_e_economy(self):
        with patch("api.database.obter_orcamento_ia", return_value={"limite_mensal_usd": 100.0}), \
             patch("api.database.gasto_mes_usd", return_value=85.0):
            self.assertEqual(cost_router.modo_atual(), "economy")

    def test_100pct_ou_mais_e_critical(self):
        with patch("api.database.obter_orcamento_ia", return_value={"limite_mensal_usd": 100.0}), \
             patch("api.database.gasto_mes_usd", return_value=120.0):
            self.assertEqual(cost_router.modo_atual(), "critical")

    def test_banco_indisponivel_degrada_para_normal(self):
        with patch("api.database.obter_orcamento_ia", side_effect=RuntimeError("sem banco")):
            self.assertEqual(cost_router.modo_atual(), "normal")

    def test_resultado_e_cacheado_por_5min(self):
        with patch("api.database.obter_orcamento_ia", return_value={"limite_mensal_usd": 100.0}) as mock_orc, \
             patch("api.database.gasto_mes_usd", return_value=50.0):
            cost_router.modo_atual()
            cost_router.modo_atual()
            cost_router.modo_atual()
        mock_orc.assert_called_once()


class RecomendarModeloTest(unittest.TestCase):
    def test_deepseek_e_gemini_sem_variante_economy(self):
        self.assertEqual(cost_router.recomendar_modelo("deepseek", "deepseek-chat", feat.REALTIME_DISC, modo="critical"), "deepseek-chat")
        self.assertEqual(cost_router.recomendar_modelo("gemini", "gemini-2.0-flash", feat.REALTIME_DISC, modo="critical"), "gemini-2.0-flash")

    def test_critical_sempre_recomenda_economy(self):
        self.assertEqual(cost_router.recomendar_modelo("openai", "gpt-4o", feat.REPORT_RECAPITULACAO, modo="critical"), "gpt-4o-mini")

    def test_economy_recomenda_para_simples_e_padrao_nao_para_complexa(self):
        self.assertEqual(cost_router.recomendar_modelo("openai", "gpt-4o", feat.REALTIME_DISC, modo="economy"), "gpt-4o-mini")
        self.assertEqual(cost_router.recomendar_modelo("openai", "gpt-4o", feat.REALTIME_COACH, modo="economy"), "gpt-4o-mini")
        self.assertEqual(cost_router.recomendar_modelo("openai", "gpt-4o", feat.REPORT_RECAPITULACAO, modo="economy"), "gpt-4o")

    def test_normal_so_recomenda_para_simples(self):
        self.assertEqual(cost_router.recomendar_modelo("anthropic", "claude-sonnet-4-20250514", feat.REALTIME_DISC, modo="normal"), "claude-3-5-haiku-20241022")
        self.assertEqual(cost_router.recomendar_modelo("anthropic", "claude-sonnet-4-20250514", feat.REALTIME_COACH, modo="normal"), "claude-sonnet-4-20250514")


class RouterAtivoTest(unittest.TestCase):
    def test_default_e_true(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COST_ROUTER_ATIVO", None)
            self.assertTrue(cost_router.router_ativo())

    def test_desligavel_via_env(self):
        with patch.dict(os.environ, {"COST_ROUTER_ATIVO": "false"}):
            self.assertFalse(cost_router.router_ativo())


class ModeloAUsarTest(unittest.TestCase):
    def setUp(self):
        cost_router._modo_cache["modo"] = None
        cost_router._modo_cache["ts"] = 0.0

    def test_ativo_aplica_recomendacao(self):
        with patch("api.database.obter_orcamento_ia", return_value=None), \
             patch.dict(os.environ, {"COST_ROUTER_ATIVO": "true"}):
            self.assertEqual(
                cost_router.modelo_a_usar("openai", "gpt-4o", feat.REALTIME_DISC),
                "gpt-4o-mini",  # normal+simples -> economy
            )

    def test_desativado_devolve_model_padrao_inalterado(self):
        with patch("api.database.obter_orcamento_ia", return_value=None), \
             patch.dict(os.environ, {"COST_ROUTER_ATIVO": "false"}):
            self.assertEqual(
                cost_router.modelo_a_usar("openai", "gpt-4o", feat.REALTIME_DISC),
                "gpt-4o",
            )


class RegistrarDecisaoTest(unittest.TestCase):
    def setUp(self):
        cost_router._modo_cache["modo"] = None
        cost_router._modo_cache["ts"] = 0.0
        self._usage = ProviderUsage(input_tokens=1000, output_tokens=500)

    def test_desabilitado_via_env_nao_grava(self):
        with patch.dict(os.environ, {"COST_ROUTER_ATIVO": "false"}), \
             patch("api.database.registrar_decisao_router") as mock_reg:
            cost_router.registrar_decisao(
                feature=feat.REALTIME_DISC, provider="openai", model_real="gpt-4o-mini",
                usage=self._usage, usage_source="provider",
            )
        mock_reg.assert_not_called()

    def test_habilitado_grava_comparacao(self):
        with patch("api.database.obter_orcamento_ia", return_value=None), \
             patch("api.database.registrar_decisao_router") as mock_reg:
            cost_router.registrar_decisao(
                feature=feat.REALTIME_DISC, provider="openai", model_real="gpt-4o",
                usage=self._usage, usage_source="provider",
            )
        mock_reg.assert_called_once()
        kwargs = mock_reg.call_args.kwargs
        self.assertEqual(kwargs["feature"], feat.REALTIME_DISC)
        self.assertEqual(kwargs["complexidade"], "simples")
        self.assertEqual(kwargs["model_real"], "gpt-4o")
        self.assertEqual(kwargs["model_recomendado"], "gpt-4o-mini")  # normal+simples -> economy
        self.assertFalse(kwargs["concordou"])
        self.assertLess(kwargs["custo_recomendado_usd"], kwargs["custo_real_usd"])

    def test_quando_model_real_ja_e_o_recomendado_concordou_true(self):
        """Com o router ativo, chamar_ia ja passa o modelo recomendado
        como model_real — o caso comum apos a ativacao real."""
        with patch("api.database.obter_orcamento_ia", return_value=None), \
             patch("api.database.registrar_decisao_router") as mock_reg:
            cost_router.registrar_decisao(
                feature=feat.REALTIME_DISC, provider="openai", model_real="gpt-4o-mini",
                usage=self._usage, usage_source="provider",
            )
        kwargs = mock_reg.call_args.kwargs
        self.assertEqual(kwargs["model_recomendado"], "gpt-4o-mini")
        self.assertTrue(kwargs["concordou"])
        self.assertEqual(kwargs["custo_recomendado_usd"], kwargs["custo_real_usd"])

    def test_nunca_lanca_mesmo_com_banco_quebrado(self):
        with patch("api.database.obter_orcamento_ia", side_effect=RuntimeError("boom")), \
             patch("api.database.registrar_decisao_router", side_effect=RuntimeError("boom2")):
            try:
                cost_router.registrar_decisao(
                    feature=feat.REALTIME_DISC, provider="openai", model_real="gpt-4o",
                    usage=self._usage, usage_source="provider",
                )
            except Exception as exc:  # pragma: no cover - falha do teste se propagar
                self.fail(f"registrar_decisao propagou excecao: {exc}")


class ConfigRouterTest(unittest.TestCase):
    def test_config_router_formato(self):
        with patch("api.database.obter_orcamento_ia", return_value=None):
            d = cost_router.config_router()
        self.assertIn("ativo", d)
        self.assertIn("modo_atual", d)
        self.assertIn("modelos_economy", d)
        self.assertIn("classificacao", d)
        self.assertIn("simples", d["classificacao"])
        self.assertIn("complexa", d["classificacao"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
