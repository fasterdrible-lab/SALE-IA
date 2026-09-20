"""
Testes de agent/shadow_mode_rules.py — Fase 23 do "PROMPT MESTRE —
SALE-IA V2" (Teste em Shadow Mode).

Módulo puro (sem IA, sem banco) — mesmo padrão de
tests/test_opportunity_intelligence_rules.py.

Run:
    python -m unittest tests.test_shadow_mode_rules -v
"""

import unittest

from agent.shadow_mode_rules import (
    QUALITY_NAO_DISPONIVEL,
    avaliar_concordancia_estrutural,
    montar_registro_shadow,
    resumir_comparacoes,
)


class AvaliarConcordanciaEstruturalTest(unittest.TestCase):
    def test_ambos_recomendam_pergunta_concorda(self):
        atual = {"type": "question"}
        nova = {"next_best_question": "Quanto isso custa hoje?"}
        r = avaliar_concordancia_estrutural(atual, nova)
        self.assertTrue(r["concordancia"])
        self.assertTrue(r["atual_e_pergunta"])
        self.assertTrue(r["novo_e_pergunta"])

    def test_ambos_nao_recomendam_pergunta_concorda(self):
        atual = {"type": "warning"}
        nova = {"next_best_question": None}
        r = avaliar_concordancia_estrutural(atual, nova)
        self.assertTrue(r["concordancia"])
        self.assertFalse(r["atual_e_pergunta"])
        self.assertFalse(r["novo_e_pergunta"])

    def test_um_recomenda_pergunta_outro_nao_discorda(self):
        atual = {"type": "insight"}
        nova = {"next_best_question": "Qual o orçamento disponível?"}
        r = avaliar_concordancia_estrutural(atual, nova)
        self.assertFalse(r["concordancia"])

    def test_next_best_question_string_vazia_conta_como_sem_pergunta(self):
        atual = {"type": "question"}
        nova = {"next_best_question": "   "}
        r = avaliar_concordancia_estrutural(atual, nova)
        self.assertFalse(r["novo_e_pergunta"])
        self.assertFalse(r["concordancia"])

    def test_recomendacao_nova_none_nunca_vira_discordancia(self):
        r = avaliar_concordancia_estrutural({"type": "question"}, None)
        self.assertIsNone(r["concordancia"])
        self.assertIsNone(r["atual_e_pergunta"])
        self.assertIsNone(r["novo_e_pergunta"])

    def test_recomendacao_atual_none_nunca_quebra(self):
        r = avaliar_concordancia_estrutural(None, {"next_best_question": None})
        self.assertFalse(r["atual_e_pergunta"])


class MontarRegistroShadowTest(unittest.TestCase):
    def test_estrutura_completa(self):
        r = montar_registro_shadow(
            {"type": "question"}, {"next_best_question": "X?"}, 850, 0.0021, None,
        )
        chaves_esperadas = {
            "recomendacao_atual", "recomendacao_nova", "concordancia",
            "atual_e_pergunta", "novo_e_pergunta", "latency_ms", "cost_usd",
            "erro", "quality",
        }
        self.assertEqual(set(r.keys()), chaves_esperadas)

    def test_quality_e_sempre_gap_explicito(self):
        r = montar_registro_shadow({}, {"next_best_question": None}, 100, 0.001, None)
        self.assertEqual(r["quality"], QUALITY_NAO_DISPONIVEL)
        self.assertFalse(r["quality"]["disponivel"])

    def test_erro_preenchido_recomendacao_nova_none(self):
        r = montar_registro_shadow({"type": "question"}, None, None, None, "ValueError: JSON inválido")
        self.assertIsNone(r["recomendacao_nova"])
        self.assertIsNone(r["concordancia"])
        self.assertEqual(r["erro"], "ValueError: JSON inválido")

    def test_gaps_sao_copias_nunca_a_mesma_referencia_mutavel(self):
        r1 = montar_registro_shadow({}, {"next_best_question": None}, 1, 1, None)
        r1["quality"]["motivo"] = "mutado"
        r2 = montar_registro_shadow({}, {"next_best_question": None}, 1, 1, None)
        self.assertNotEqual(r2["quality"]["motivo"], "mutado")


class ResumirComparacoesTest(unittest.TestCase):
    def _comparacao(self, **overrides):
        base = {"concordancia": True, "latency_ms": 800, "cost_usd": 0.002, "erro": None}
        base.update(overrides)
        return base

    def test_lista_vazia_nunca_quebra(self):
        r = resumir_comparacoes([])
        self.assertEqual(r["total_comparacoes"], 0)
        self.assertIsNone(r["agreement_rate"])
        self.assertIsNone(r["error_rate"])
        self.assertEqual(r["cost_usd_total"], 0.0)

    def test_agreement_rate_so_conta_comparaveis(self):
        comparacoes = [
            self._comparacao(concordancia=True),
            self._comparacao(concordancia=True),
            self._comparacao(concordancia=False),
            self._comparacao(concordancia=None, erro="TimeoutError"),  # erro, nunca entra no denominador
        ]
        r = resumir_comparacoes(comparacoes)
        self.assertEqual(r["total_comparacoes"], 4)
        self.assertEqual(r["comparaveis"], 3)
        self.assertAlmostEqual(r["agreement_rate"], 2 / 3)
        self.assertAlmostEqual(r["disagreement_rate"], 1 / 3)

    def test_error_rate_conta_sobre_o_total(self):
        comparacoes = [
            self._comparacao(),
            self._comparacao(concordancia=None, erro="ValueError"),
        ]
        r = resumir_comparacoes(comparacoes)
        self.assertAlmostEqual(r["error_rate"], 0.5)

    def test_latencia_e_custo_ignoram_none(self):
        comparacoes = [
            self._comparacao(latency_ms=1000, cost_usd=0.01),
            self._comparacao(latency_ms=None, cost_usd=None, concordancia=None, erro="X"),
        ]
        r = resumir_comparacoes(comparacoes)
        self.assertEqual(r["latency_ms_media"], 1000)
        self.assertEqual(r["cost_usd_total"], 0.01)

    def test_quality_sempre_gap_no_resumo(self):
        r = resumir_comparacoes([self._comparacao()])
        self.assertFalse(r["quality"]["disponivel"])


if __name__ == "__main__":
    unittest.main()
