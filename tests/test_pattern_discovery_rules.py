# -*- coding: utf-8 -*-
"""
Testes de agent/pattern_discovery_rules.py — Fase 12 / Tarefa 12.2 do
"PROMPT MESTRE — SALE-IA V2" (Descoberta de Padrões), fecha a Fase 12
(Collective Sales Intelligence).

Módulo puro (sem IA, sem banco) — mesmo padrão de
tests/test_seller_benchmark_rules.py, cujas primitivas de
win_loss_rules.py este módulo também reaproveita.

Run:
    python -m unittest tests.test_pattern_discovery_rules -v
"""

import unittest

from agent.pattern_discovery_rules import (
    TEMPLATE_PADRAO_DESCOBERTO,
    TEMPLATE_PADRAO_SEM_SINAL,
    descobrir_padrao,
)

HIPOTESE_LITERAL = "Vendedores de alta conversão exploram implicação antes de apresentar solução."


def _obs(group, exhibited):
    return {"group": group, "exhibited": exhibited}


class ExemploLiteralDoPromptMestreTest(unittest.TestCase):
    def test_hipotese_confirmada_com_diferenca_significativa(self):
        observacoes = (
            [_obs("top", True) for _ in range(40)] + [_obs("top", False) for _ in range(10)]
            + [_obs("control", True) for _ in range(15)] + [_obs("control", False) for _ in range(35)]
        )
        resultado = descobrir_padrao(observacoes, hipotese=HIPOTESE_LITERAL)

        self.assertEqual(resultado["hipotese"], HIPOTESE_LITERAL)
        self.assertEqual(resultado["sample"], 100)
        self.assertAlmostEqual(resultado["top_group"]["taxa_conversao"], 0.8)
        self.assertAlmostEqual(resultado["control_group"]["taxa_conversao"], 0.3)
        self.assertAlmostEqual(resultado["difference"], 0.5)
        self.assertEqual(resultado["confidence"], 0.95)
        self.assertTrue(resultado["diferenca_significativa"])
        self.assertIn(HIPOTESE_LITERAL, resultado["afirmacao"])

    def test_afirmacao_nunca_declara_causalidade(self):
        observacoes = (
            [_obs("top", True) for _ in range(40)] + [_obs("top", False) for _ in range(10)]
            + [_obs("control", True) for _ in range(15)] + [_obs("control", False) for _ in range(35)]
        )
        resultado = descobrir_padrao(observacoes, hipotese=HIPOTESE_LITERAL)
        afirmacao = resultado["afirmacao"].lower()
        self.assertNotIn("causa", afirmacao)
        self.assertNotIn("causou", afirmacao)


class SemSinalRealTest(unittest.TestCase):
    def test_taxas_parecidas_nao_sinaliza_diferenca_significativa(self):
        observacoes = (
            [_obs("top", True) for _ in range(26)] + [_obs("top", False) for _ in range(24)]
            + [_obs("control", True) for _ in range(24)] + [_obs("control", False) for _ in range(26)]
        )
        resultado = descobrir_padrao(observacoes, hipotese="hipótese qualquer")
        self.assertFalse(resultado["diferenca_significativa"])
        self.assertEqual(resultado["afirmacao"], TEMPLATE_PADRAO_SEM_SINAL.format(hipotese="hipótese qualquer"))


class AmostraInsuficienteTest(unittest.TestCase):
    def test_diferenca_grande_mas_amostra_pequena_nao_e_significativa(self):
        # top 8/10 (80%) vs control 2/10 (20%) -- diferença grande, mas n<30.
        observacoes = (
            [_obs("top", True) for _ in range(8)] + [_obs("top", False) for _ in range(2)]
            + [_obs("control", True) for _ in range(2)] + [_obs("control", False) for _ in range(8)]
        )
        resultado = descobrir_padrao(observacoes, hipotese="x")
        self.assertFalse(resultado["top_group"]["amostra_suficiente"])
        self.assertFalse(resultado["diferenca_significativa"])
        self.assertAlmostEqual(resultado["difference"], 0.6)  # a diferença ainda é calculada, só não é "significativa"


class GrupoAusenteTest(unittest.TestCase):
    def test_sem_nenhuma_observacao_de_control_group_fica_vazio(self):
        observacoes = [_obs("top", True) for _ in range(5)]
        resultado = descobrir_padrao(observacoes, hipotese="x")
        self.assertEqual(resultado["control_group"]["total"], 0)
        self.assertIsNone(resultado["control_group"]["taxa_conversao"])
        self.assertIsNone(resultado["difference"])
        self.assertFalse(resultado["diferenca_significativa"])

    def test_lista_vazia_nao_quebra(self):
        resultado = descobrir_padrao([], hipotese="x")
        self.assertEqual(resultado["sample"], 0)
        self.assertIsNone(resultado["difference"])
        self.assertFalse(resultado["diferenca_significativa"])


class ValidacaoTest(unittest.TestCase):
    def test_group_invalido_levanta(self):
        with self.assertRaises(ValueError):
            descobrir_padrao([_obs("mediano", True)])

    def test_exhibited_nao_booleano_levanta(self):
        with self.assertRaises(ValueError):
            descobrir_padrao([{"group": "top", "exhibited": "sim"}])


class ConfiancaCustomizadaTest(unittest.TestCase):
    def test_nivel_de_confianca_customizado_e_respeitado(self):
        observacoes = (
            [_obs("top", True) for _ in range(40)] + [_obs("top", False) for _ in range(10)]
            + [_obs("control", True) for _ in range(15)] + [_obs("control", False) for _ in range(35)]
        )
        resultado = descobrir_padrao(observacoes, hipotese="x", confianca=0.90)
        self.assertEqual(resultado["confidence"], 0.90)


if __name__ == "__main__":
    unittest.main()
