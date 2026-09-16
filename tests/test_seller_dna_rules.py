# -*- coding: utf-8 -*-
"""
Testes do Seller DNA — Fase 15 (Tarefas 15.1 e 15.2) do "PROMPT
MESTRE — SALE-IA V2".

Função pura (agent/seller_dna_rules.py), sem IA/banco. Cobre a guarda
de amostra mínima (Tarefa 15.1) e a guarda contra alegação de eficácia
(Tarefa 15.2) — "André costuma fazer X" != "X funciona".

Run:
    python -m unittest tests.test_seller_dna_rules -v
"""

import unittest

from agent.seller_dna_rules import (
    SELLER_DNA_AMOSTRA_MINIMA_PADRAO,
    SELLER_DNA_CAMPOS,
    TERMOS_ALEGACAO_EFICACIA,
    amostra_suficiente_seller_dna,
    campos_sem_observacao,
    construir_seller_dna,
    validar_sem_alegacao_de_eficacia,
)


class VocabularioTest(unittest.TestCase):
    def test_12_campos_literais_do_prompt_mestre(self):
        self.assertEqual(
            SELLER_DNA_CAMPOS,
            (
                "communication_style", "opening_patterns", "discovery_style",
                "question_patterns", "storytelling_patterns", "negotiation_patterns",
                "objection_patterns", "pricing_style", "closing_patterns",
                "language_patterns", "preferred_phrases", "forbidden_phrases",
            ),
        )


class AmostraMinimaTest(unittest.TestCase):
    """Regra literal: 'não clonar personalidade a partir de poucas
    conversas, exigir amostra mínima configurável'."""

    def test_amostra_abaixo_do_minimo_padrao_e_insuficiente(self):
        self.assertFalse(amostra_suficiente_seller_dna(3))

    def test_amostra_no_minimo_padrao_e_suficiente(self):
        self.assertTrue(amostra_suficiente_seller_dna(SELLER_DNA_AMOSTRA_MINIMA_PADRAO))

    def test_minimo_e_configuravel_por_chamada(self):
        self.assertTrue(amostra_suficiente_seller_dna(5, minimo=5))
        self.assertFalse(amostra_suficiente_seller_dna(4, minimo=5))

    def test_construir_seller_dna_recusa_com_poucas_reunioes(self):
        with self.assertRaises(ValueError):
            construir_seller_dna(seller_id="vendedor_1", n_reunioes_analisadas=2)

    def test_construir_seller_dna_aceita_minimo_configurado_mais_baixo(self):
        perfil = construir_seller_dna(seller_id="vendedor_1", n_reunioes_analisadas=3, minimo_amostra=3)
        self.assertEqual(perfil["n_reunioes_analisadas"], 3)

    def test_n_reunioes_negativo_levanta(self):
        with self.assertRaises(ValueError):
            construir_seller_dna(seller_id="vendedor_1", n_reunioes_analisadas=-1)

    def test_seller_id_vazio_levanta(self):
        with self.assertRaises(ValueError):
            construir_seller_dna(seller_id="", n_reunioes_analisadas=20)


class ConstruirSellerDnaTest(unittest.TestCase):
    def test_perfil_completo_com_amostra_suficiente(self):
        perfil = construir_seller_dna(
            seller_id="vendedor_1",
            n_reunioes_analisadas=15,
            observacoes_por_campo={
                "communication_style": "Direto, frases curtas, vai ao ponto rapidamente",
                "opening_patterns": "Costuma abrir perguntando sobre o dia do cliente antes da pauta",
                "preferred_phrases": ["Faz sentido pra você?", "Deixa eu te mostrar uma coisa"],
                "forbidden_phrases": ["Confia em mim"],
            },
        )
        self.assertEqual(perfil["seller_id"], "vendedor_1")
        self.assertEqual(perfil["n_reunioes_analisadas"], 15)
        self.assertEqual(
            perfil["campos"]["communication_style"],
            "Direto, frases curtas, vai ao ponto rapidamente",
        )
        # Campo nao observado ainda vem None, nunca inventado
        self.assertIsNone(perfil["campos"]["pricing_style"])

    def test_campo_fora_do_vocabulario_levanta(self):
        with self.assertRaises(ValueError):
            construir_seller_dna(
                seller_id="vendedor_1",
                n_reunioes_analisadas=15,
                observacoes_por_campo={"personalidade_geral": "extrovertido"},
            )

    def test_campos_sem_observacao_lista_os_ausentes(self):
        perfil = construir_seller_dna(
            seller_id="vendedor_1",
            n_reunioes_analisadas=15,
            observacoes_por_campo={"communication_style": "direto"},
        )
        ausentes = campos_sem_observacao(perfil)
        self.assertIn("pricing_style", ausentes)
        self.assertNotIn("communication_style", ausentes)
        self.assertEqual(len(ausentes), len(SELLER_DNA_CAMPOS) - 1)


class GuardaContraAlegacaoDeEficaciaTest(unittest.TestCase):
    """Regra central da Tarefa 15.2: 'André costuma fazer X' não
    significa 'X funciona'. SellerDNA registra comportamento, Sales
    Science mede eficácia — nunca misturar os dois."""

    def test_descricao_pura_de_comportamento_e_aceita(self):
        validar_sem_alegacao_de_eficacia(
            "opening_patterns", "André costuma abrir perguntando sobre a rotina do cliente"
        )  # não deve levantar

    def test_alegacao_de_eficacia_e_recusada(self):
        with self.assertRaises(ValueError):
            validar_sem_alegacao_de_eficacia("opening_patterns", "Essa abertura funciona muito bem")

    def test_cada_termo_proibido_individualmente_e_recusado(self):
        for termo in TERMOS_ALEGACAO_EFICACIA:
            with self.assertRaises(ValueError):
                validar_sem_alegacao_de_eficacia("pricing_style", f"Essa tática {termo} sempre")

    def test_valor_none_e_aceito(self):
        validar_sem_alegacao_de_eficacia("pricing_style", None)  # não deve levantar

    def test_lista_de_frases_tambem_e_verificada(self):
        with self.assertRaises(ValueError):
            validar_sem_alegacao_de_eficacia(
                "preferred_phrases", ["Faz sentido pra você?", "essa frase comprovado que vende mais"]
            )

    def test_construir_seller_dna_propaga_a_guarda(self):
        with self.assertRaises(ValueError):
            construir_seller_dna(
                seller_id="vendedor_1",
                n_reunioes_analisadas=15,
                observacoes_por_campo={"closing_patterns": "Esse fechamento funciona sempre"},
            )


if __name__ == "__main__":
    unittest.main()
