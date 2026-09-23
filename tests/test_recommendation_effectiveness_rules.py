"""
Testes de agent/recommendation_effectiveness_rules.py — Fase 10 /
Tarefa 10.3 do "PROMPT MESTRE — SALE-IA V2" (Recommendation
Effectiveness), fecha a Fase 10.

Módulo puro (sem IA, sem banco) — mesmo padrão de
tests/test_win_loss_rules.py.

Run:
    python -m unittest tests.test_recommendation_effectiveness_rules -v
"""

import unittest

from agent.recommendation_effectiveness_rules import (
    TEMPLATE_EFETIVIDADE,
    calcular_efetividade_por_estrategia,
    resumir_uso_geral,
)


def _evento(strategy, state="USED", stage_advanced=None, opportunity_result=None):
    return {"strategy": strategy, "state": state, "stage_advanced": stage_advanced, "opportunity_result": opportunity_result}


class ExemploLiteralDoPromptMestreTest(unittest.TestCase):
    """Dashboard futuro do prompt mestre:
    SPIN Implication — 187 usos — 61% avanço
    Case Similar — 153 usos — 66% avanço
    """

    def test_spin_implication_e_case_similar_batem_com_o_exemplo(self):
        eventos = []
        # SPIN Implication: 187 usos, 114 com avanço (114/187 ~= 61%)
        eventos += [_evento("SPIN Implication", stage_advanced=True) for _ in range(114)]
        eventos += [_evento("SPIN Implication", stage_advanced=False) for _ in range(187 - 114)]
        # Case Similar: 153 usos, 101 com avanço (101/153 ~= 66%)
        eventos += [_evento("Case Similar", stage_advanced=True) for _ in range(101)]
        eventos += [_evento("Case Similar", stage_advanced=False) for _ in range(153 - 101)]

        resumo = calcular_efetividade_por_estrategia(eventos)

        self.assertEqual(resumo["SPIN Implication"]["usos"], 187)
        self.assertAlmostEqual(round(resumo["SPIN Implication"]["taxa_avanco"], 2), 0.61)

        self.assertEqual(resumo["Case Similar"]["usos"], 153)
        self.assertAlmostEqual(round(resumo["Case Similar"]["taxa_avanco"], 2), 0.66)


class ContagemDeUsosTest(unittest.TestCase):
    def test_ignored_e_unknown_nao_contam_como_uso(self):
        eventos = (
            [_evento("A", state="USED")]
            + [_evento("A", state="PARTIALLY_USED")]
            + [_evento("A", state="IGNORED")]
            + [_evento("A", state="UNKNOWN")]
        )
        resumo = calcular_efetividade_por_estrategia(eventos)
        self.assertEqual(resumo["A"]["usos"], 2)  # so USED + PARTIALLY_USED

    def test_evento_sem_strategy_e_ignorado(self):
        eventos = [{"strategy": None, "state": "USED"}, _evento("A")]
        resumo = calcular_efetividade_por_estrategia(eventos)
        self.assertEqual(list(resumo.keys()), ["A"])

    def test_state_invalido_levanta(self):
        with self.assertRaises(ValueError):
            calcular_efetividade_por_estrategia([_evento("A", state="MAYBE")])


class TaxaAvancoTest(unittest.TestCase):
    def test_stage_advanced_none_nao_conta_no_denominador(self):
        eventos = [
            _evento("A", stage_advanced=True),
            _evento("A", stage_advanced=None),  # sem dado -- nunca vira False
        ]
        resumo = calcular_efetividade_por_estrategia(eventos)
        self.assertEqual(resumo["A"]["usos"], 2)
        self.assertAlmostEqual(resumo["A"]["taxa_avanco"], 1.0)  # 1/1, o None foi excluido

    def test_sem_nenhum_dado_de_avanco_taxa_e_none(self):
        eventos = [_evento("A", stage_advanced=None)]
        resumo = calcular_efetividade_por_estrategia(eventos)
        self.assertIsNone(resumo["A"]["taxa_avanco"])
        self.assertIsNone(resumo["A"]["afirmacao"])


class GuardaContraConfusaoCausalTest(unittest.TestCase):
    """Regra 'Importante' literal da Tarefa 10.3: não confundir avanço
    imediato com causa da venda."""

    def test_template_traz_aviso_explicito_contra_causalidade(self):
        template_lower = TEMPLATE_EFETIVIDADE.lower()
        self.assertIn("não é o mesmo que", template_lower)
        self.assertIn("causou", template_lower)

    def test_taxa_avanco_e_taxa_desfecho_positivo_sao_calculadas_independentemente(self):
        """As duas métricas vêm de dados diferentes (stage_advanced vs.
        opportunity_result) e nunca podem ser combinadas numa fórmula
        só — construímos um cenário onde divergem bastante pra provar
        isso."""
        eventos = (
            [_evento("X", stage_advanced=True, opportunity_result="lost") for _ in range(9)]
            + [_evento("X", stage_advanced=False, opportunity_result="won")]
        )
        resumo = calcular_efetividade_por_estrategia(eventos)
        self.assertAlmostEqual(resumo["X"]["taxa_avanco"], 0.9)
        self.assertAlmostEqual(resumo["X"]["taxa_desfecho_positivo"], 0.1)

    def test_opportunity_result_none_nao_conta_no_denominador_do_desfecho(self):
        eventos = [
            _evento("A", opportunity_result="won"),
            _evento("A", opportunity_result=None),  # ainda aberta
        ]
        resumo = calcular_efetividade_por_estrategia(eventos)
        self.assertAlmostEqual(resumo["A"]["taxa_desfecho_positivo"], 1.0)

    def test_sem_nenhum_resultado_de_oportunidade_taxa_desfecho_e_none(self):
        eventos = [_evento("A", opportunity_result=None)]
        resumo = calcular_efetividade_por_estrategia(eventos)
        self.assertIsNone(resumo["A"]["taxa_desfecho_positivo"])


class ResumirUsoGeralTest(unittest.TestCase):
    """Fase 25 ("o que falta pra ligar") — agregado simples de uso
    real, sem quebrar por estratégia."""

    def test_conta_cada_estado(self):
        estados = ["USED", "USED", "PARTIALLY_USED", "IGNORED", "UNKNOWN"]
        resumo = resumir_uso_geral(estados)
        self.assertEqual(resumo["total"], 5)
        self.assertEqual(resumo["por_estado"]["USED"], 2)
        self.assertEqual(resumo["por_estado"]["PARTIALLY_USED"], 1)
        self.assertEqual(resumo["por_estado"]["IGNORED"], 1)
        self.assertEqual(resumo["por_estado"]["UNKNOWN"], 1)

    def test_taxa_uso_real_exclui_unknown_do_denominador(self):
        # 2 USED + 1 IGNORED conhecidos, 1 UNKNOWN fora da conta —
        # taxa = 2/3, não 2/4.
        estados = ["USED", "USED", "IGNORED", "UNKNOWN"]
        resumo = resumir_uso_geral(estados)
        self.assertAlmostEqual(resumo["taxa_uso_real"], 2 / 3)

    def test_partially_used_conta_como_uso(self):
        estados = ["PARTIALLY_USED", "IGNORED"]
        resumo = resumir_uso_geral(estados)
        self.assertAlmostEqual(resumo["taxa_uso_real"], 0.5)

    def test_todos_unknown_taxa_e_none_nunca_inventa_numero(self):
        estados = ["UNKNOWN", "UNKNOWN"]
        resumo = resumir_uso_geral(estados)
        self.assertIsNone(resumo["taxa_uso_real"])

    def test_lista_vazia_nunca_quebra(self):
        resumo = resumir_uso_geral([])
        self.assertEqual(resumo["total"], 0)
        self.assertIsNone(resumo["taxa_uso_real"])

    def test_estado_invalido_levanta(self):
        with self.assertRaises(ValueError):
            resumir_uso_geral(["ESTADO_QUE_NAO_EXISTE"])

    def test_todos_os_4_estados_sempre_presentes_no_por_estado(self):
        resumo = resumir_uso_geral(["USED"])
        self.assertEqual(set(resumo["por_estado"].keys()), {"USED", "PARTIALLY_USED", "IGNORED", "UNKNOWN"})


if __name__ == "__main__":
    unittest.main()
