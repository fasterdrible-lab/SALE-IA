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
    agregar_observacoes_por_campo,
    amostra_suficiente_seller_dna,
    campos_sem_observacao,
    construir_seller_dna,
    construir_seller_dna_de_observacoes,
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


class AgregarObservacoesPorCampoTest(unittest.TestCase):
    """Bloco 5 / Tarefa 5.1 (docs/tasks-sales-reasoning-engine-
    completo.md) — agregação de observações persistidas (uma linha por
    reunião+campo) no formato que construir_seller_dna() já espera."""

    def test_agrupa_por_campo_mantendo_valores_distintos(self):
        observacoes = [
            {"meeting_id": "m1", "campo": "opening_patterns", "valor": "Abre perguntando sobre a rotina"},
            {"meeting_id": "m2", "campo": "opening_patterns", "valor": "Abre confirmando a pauta"},
            {"meeting_id": "m1", "campo": "pricing_style", "valor": "Fala preço só no fim"},
        ]
        agregado = agregar_observacoes_por_campo(observacoes)
        self.assertEqual(
            agregado["opening_patterns"],
            ["Abre perguntando sobre a rotina", "Abre confirmando a pauta"],
        )
        self.assertEqual(agregado["pricing_style"], ["Fala preço só no fim"])

    def test_valor_repetido_nao_duplica(self):
        observacoes = [
            {"meeting_id": "m1", "campo": "closing_patterns", "valor": "Sempre propõe próximo passo"},
            {"meeting_id": "m2", "campo": "closing_patterns", "valor": "Sempre propõe próximo passo"},
        ]
        agregado = agregar_observacoes_por_campo(observacoes)
        self.assertEqual(agregado["closing_patterns"], ["Sempre propõe próximo passo"])

    def test_campo_fora_do_vocabulario_e_ignorado(self):
        observacoes = [{"meeting_id": "m1", "campo": "personalidade_geral", "valor": "extrovertido"}]
        self.assertEqual(agregar_observacoes_por_campo(observacoes), {})

    def test_lista_vazia_retorna_dict_vazio(self):
        self.assertEqual(agregar_observacoes_por_campo([]), {})


class ConstruirSellerDnaDeObservacoesTest(unittest.TestCase):
    def test_conta_reunioes_distintas_nao_linhas(self):
        """10 observações, mas só 3 reuniões distintas -> amostra
        insuficiente (mínimo padrão é 10 REUNIÕES, não observações)."""
        observacoes = [
            {"meeting_id": mid, "campo": "closing_patterns", "valor": f"padrao-{mid}"}
            for mid in ["m1"] * 4 + ["m2"] * 3 + ["m3"] * 3
        ]
        with self.assertRaises(ValueError):
            construir_seller_dna_de_observacoes("vendedor_1", observacoes)

    def test_10_reunioes_distintas_monta_perfil(self):
        observacoes = [
            {"meeting_id": f"m{i}", "campo": "closing_patterns", "valor": "Sempre propõe próximo passo"}
            for i in range(10)
        ]
        perfil = construir_seller_dna_de_observacoes("vendedor_1", observacoes)
        self.assertEqual(perfil["n_reunioes_analisadas"], 10)
        self.assertEqual(perfil["campos"]["closing_patterns"], ["Sempre propõe próximo passo"])
        self.assertIsNone(perfil["campos"]["pricing_style"])  # sem observação ainda

    def test_guarda_contra_alegacao_de_eficacia_continua_valendo(self):
        observacoes = [
            {"meeting_id": f"m{i}", "campo": "closing_patterns", "valor": "Esse fechamento funciona sempre"}
            for i in range(10)
        ]
        with self.assertRaises(ValueError):
            construir_seller_dna_de_observacoes("vendedor_1", observacoes)


if __name__ == "__main__":
    unittest.main()
