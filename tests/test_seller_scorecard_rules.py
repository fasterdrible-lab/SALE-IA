# -*- coding: utf-8 -*-
"""
Testes de agent/seller_scorecard_rules.py — Fase 11 / Tarefa 11.2 do
"PROMPT MESTRE — SALE-IA V2" (Seller Scorecard), fecha a Fase 11
(Seller Coaching).

Módulo puro (sem IA, sem banco) — mesmo padrão de
tests/test_conversation_metrics_rules.py.

Run:
    python -m unittest tests.test_seller_scorecard_rules -v
"""

import unittest

from agent.seller_scorecard_rules import (
    SCORECARD_DIMENSOES,
    calcular_scorecard,
    dimensoes_sem_evidencia,
    validar_evidencia,
)


def _ev(criterio, atendido, quote=None):
    return {"criterio": criterio, "atendido": atendido, "quote": quote}


class TodasAsDimensoesTest(unittest.TestCase):
    def test_as_7_dimensoes_literais_sempre_presentes_no_retorno(self):
        scorecard = calcular_scorecard({})
        self.assertEqual(set(scorecard.keys()), set(SCORECARD_DIMENSOES))
        self.assertEqual(len(SCORECARD_DIMENSOES), 7)

    def test_chamada_sem_argumento_nenhum_nao_quebra(self):
        scorecard = calcular_scorecard()
        for dimensao in SCORECARD_DIMENSOES:
            self.assertIsNone(scorecard[dimensao]["score"])
            self.assertEqual(scorecard[dimensao]["evidencias"], [])


class CalculoDoScoreTest(unittest.TestCase):
    def test_score_bate_com_calculo_manual(self):
        evidencias = [
            _ev("Explorou a situação atual do cliente", True, "Como funciona hoje o processo de vocês?"),
            _ev("Investigou implicação da dor", True, "Isso já custou algum contrato?"),
            _ev("Perguntou sobre necessidade/payoff", False),
        ]
        scorecard = calcular_scorecard({"Discovery": evidencias})
        self.assertEqual(scorecard["Discovery"]["criterios_atendidos"], 2)
        self.assertEqual(scorecard["Discovery"]["total_criterios"], 3)
        self.assertAlmostEqual(scorecard["Discovery"]["score"], 2 / 3)
        self.assertEqual(scorecard["Discovery"]["evidencias"], evidencias)

    def test_dimensao_sem_evidencia_tem_score_none_nunca_zero(self):
        scorecard = calcular_scorecard({"Discovery": [_ev("x", True)]})
        self.assertIsNone(scorecard["Listening"]["score"])
        self.assertEqual(scorecard["Listening"]["total_criterios"], 0)

    def test_todos_criterios_atendidos_da_score_1(self):
        evidencias = [_ev("a", True), _ev("b", True)]
        scorecard = calcular_scorecard({"Closing": evidencias})
        self.assertEqual(scorecard["Closing"]["score"], 1.0)

    def test_nenhum_criterio_atendido_da_score_0(self):
        evidencias = [_ev("a", False), _ev("b", False)]
        scorecard = calcular_scorecard({"Negotiation": evidencias})
        self.assertEqual(scorecard["Negotiation"]["score"], 0.0)


class ValidacaoTest(unittest.TestCase):
    def test_dimensao_fora_do_vocabulario_levanta(self):
        with self.assertRaises(ValueError):
            calcular_scorecard({"Empatia": [_ev("a", True)]})

    def test_evidencia_sem_criterio_levanta(self):
        with self.assertRaises(ValueError):
            calcular_scorecard({"Discovery": [{"atendido": True}]})

        with self.assertRaises(ValueError):
            validar_evidencia({"criterio": "", "atendido": True})

    def test_evidencia_com_atendido_nao_booleano_levanta(self):
        with self.assertRaises(ValueError):
            calcular_scorecard({"Discovery": [_ev("x", "sim")]})

    def test_evidencia_valida_nao_levanta(self):
        validar_evidencia(_ev("x", True))
        validar_evidencia(_ev("x", False))


class DimensoesSemEvidenciaTest(unittest.TestCase):
    def test_lista_so_as_dimensoes_sem_dado(self):
        scorecard = calcular_scorecard({
            "Discovery": [_ev("a", True)],
            "Closing": [_ev("b", False)],
        })
        faltantes = dimensoes_sem_evidencia(scorecard)
        self.assertNotIn("Discovery", faltantes)
        self.assertNotIn("Closing", faltantes)
        self.assertEqual(len(faltantes), 5)

    def test_todas_faltantes_quando_nenhuma_evidencia_e_passada(self):
        scorecard = calcular_scorecard({})
        self.assertEqual(set(dimensoes_sem_evidencia(scorecard)), set(SCORECARD_DIMENSOES))


class GuardaContraScoreArbitrarioTest(unittest.TestCase):
    """Regra literal da Tarefa 11.2: 'Não criar score arbitrário'."""

    def test_nenhuma_chave_de_score_combinado_e_produzida(self):
        scorecard = calcular_scorecard({
            "Discovery": [_ev("a", True)],
            "Listening": [_ev("b", True), _ev("c", False)],
        })
        self.assertNotIn("score_geral", scorecard)
        self.assertNotIn("overall_score", scorecard)
        self.assertNotIn("nota_geral", scorecard)
        # o dict inteiro só tem as 7 dimensões literais como chaves de topo.
        self.assertEqual(set(scorecard.keys()), set(SCORECARD_DIMENSOES))

    def test_score_de_cada_dimensao_e_sempre_recomputavel_a_partir_das_proprias_evidencias(self):
        evidencias = [_ev("a", True), _ev("b", True), _ev("c", True), _ev("d", False)]
        scorecard = calcular_scorecard({"Value Building": evidencias})
        atendidos_manual = sum(1 for e in evidencias if e["atendido"])
        self.assertEqual(scorecard["Value Building"]["score"], atendidos_manual / len(evidencias))

    def test_cada_score_vem_acompanhado_das_evidencias_que_o_justificam(self):
        evidencias = [_ev("Fez pergunta calibrada antes de negociar", True, "O que te faz hesitar no valor?")]
        scorecard = calcular_scorecard({"Negotiation": evidencias})
        self.assertTrue(len(scorecard["Negotiation"]["evidencias"]) > 0)
        self.assertEqual(scorecard["Negotiation"]["evidencias"][0]["criterio"], "Fez pergunta calibrada antes de negociar")


if __name__ == "__main__":
    unittest.main()
