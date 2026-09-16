# -*- coding: utf-8 -*-
"""
Testes do Autonomy Policy — Fase 17 (Tarefa 17.1, Decision Boundaries)
do "PROMPT MESTRE — SALE-IA V2".

Função pura (agent/autonomy_policy_rules.py), sem IA/banco. Esta é a
"suite específica de policy tests" pedida literalmente pela Tarefa
17.1 — o núcleo é `GuardaContraContornoDePoliticaTest`, que confirma
que nenhum nível de autonomia (nem o máximo) contorna uma fronteira
que exige humano ou proíbe a ação.

Run:
    python -m unittest tests.test_autonomy_policy_rules -v
"""

import unittest

from agent.autonomy_policy_rules import (
    AUTONOMY_LEVELS,
    DECISION_BOUNDARIES,
    DECISION_BOUNDARIES_PADRAO,
    LIMITE_DESCONTO_POLICY_DEPENDENT_PADRAO,
    avaliar_acao,
    avaliar_desconto,
    pode_executar_autonomamente,
)


class NiveisEFronteirasTest(unittest.TestCase):
    def test_6_niveis_literais_na_ordem_do_prompt_mestre(self):
        self.assertEqual(
            AUTONOMY_LEVELS,
            (
                "OBSERVE", "RECOMMEND", "DRAFT",
                "EXECUTE_LOW_RISK", "EXECUTE_HUMAN_APPROVAL",
                "AUTONOMOUS_WITHIN_POLICY",
            ),
        )
        # indice == numero literal do nivel (0-5)
        self.assertEqual(AUTONOMY_LEVELS.index("OBSERVE"), 0)
        self.assertEqual(AUTONOMY_LEVELS.index("AUTONOMOUS_WITHIN_POLICY"), 5)

    def test_5_fronteiras_de_decisao_literais(self):
        self.assertEqual(
            set(DECISION_BOUNDARIES),
            {"AUTONOMOUS", "POLICY_DEPENDENT", "HUMAN_APPROVAL", "HUMAN_REQUIRED", "FORBIDDEN"},
        )


class ExemploLiteralDecisionBoundariesTest(unittest.TestCase):
    """Reproduz a tabela literal de exemplo da Tarefa 17.1."""

    def test_dar_informacao_publica_e_autonomous(self):
        self.assertEqual(avaliar_acao("dar_informacao_publica"), "AUTONOMOUS")

    def test_qualificar_e_autonomous(self):
        self.assertEqual(avaliar_acao("qualificar"), "AUTONOMOUS")

    def test_agendar_reuniao_e_autonomous(self):
        self.assertEqual(avaliar_acao("agendar_reuniao"), "AUTONOMOUS")

    def test_enviar_followup_e_autonomous(self):
        self.assertEqual(avaliar_acao("enviar_followup"), "AUTONOMOUS")

    def test_alteracao_juridica_e_human_required(self):
        self.assertEqual(avaliar_acao("alteracao_juridica"), "HUMAN_REQUIRED")

    def test_promessa_nao_documentada_e_forbidden(self):
        self.assertEqual(avaliar_acao("promessa_nao_documentada"), "FORBIDDEN")

    def test_desconto_ate_5_por_cento_e_policy_dependent(self):
        self.assertEqual(avaliar_desconto(5.0), "POLICY_DEPENDENT")
        self.assertEqual(avaliar_desconto(0), "POLICY_DEPENDENT")
        self.assertEqual(avaliar_desconto(3.2), "POLICY_DEPENDENT")

    def test_desconto_acima_de_5_por_cento_e_human_approval(self):
        self.assertEqual(avaliar_desconto(5.01), "HUMAN_APPROVAL")
        self.assertEqual(avaliar_desconto(20), "HUMAN_APPROVAL")

    def test_limite_de_desconto_e_configuravel(self):
        self.assertEqual(avaliar_desconto(8, limite=10), "POLICY_DEPENDENT")
        self.assertEqual(avaliar_desconto(11, limite=10), "HUMAN_APPROVAL")


class AvaliarAcaoFailClosedTest(unittest.TestCase):
    def test_acao_sem_mapeamento_levanta(self):
        with self.assertRaises(ValueError):
            avaliar_acao("acao_inventada_que_nao_existe")

    def test_percentual_none_levanta(self):
        with self.assertRaises(ValueError):
            avaliar_desconto(None)


class GuardaContraContornoDePoliticaTest(unittest.TestCase):
    """Núcleo da suite de policy tests pedida pela Tarefa 17.1:
    'nenhum LLM pode contornar políticas' — nenhum nível de autonomia,
    nem o máximo (5, AUTONOMOUS_WITHIN_POLICY), muda o resultado para
    uma fronteira que exige humano ou proíbe a ação."""

    def test_forbidden_nunca_executa_em_nenhum_nivel(self):
        for nivel in range(len(AUTONOMY_LEVELS)):
            with self.subTest(nivel=nivel):
                self.assertFalse(pode_executar_autonomamente("FORBIDDEN", nivel))

    def test_human_required_nunca_executa_em_nenhum_nivel(self):
        for nivel in range(len(AUTONOMY_LEVELS)):
            with self.subTest(nivel=nivel):
                self.assertFalse(pode_executar_autonomamente("HUMAN_REQUIRED", nivel))

    def test_human_approval_nunca_executa_em_nenhum_nivel(self):
        for nivel in range(len(AUTONOMY_LEVELS)):
            with self.subTest(nivel=nivel):
                self.assertFalse(pode_executar_autonomamente("HUMAN_APPROVAL", nivel))

    def test_forbidden_no_nivel_maximo_continua_bloqueado(self):
        """O teste mais literal da regra: mesmo no nivel 5
        (AUTONOMOUS_WITHIN_POLICY, o mais alto possivel), uma acao
        FORBIDDEN jamais executa."""
        nivel_maximo = AUTONOMY_LEVELS.index("AUTONOMOUS_WITHIN_POLICY")
        self.assertFalse(pode_executar_autonomamente("FORBIDDEN", nivel_maximo))
        self.assertFalse(pode_executar_autonomamente("HUMAN_REQUIRED", nivel_maximo))

    def test_policy_dependente_sem_aprovacao_explicita_nunca_executa(self):
        for nivel in range(len(AUTONOMY_LEVELS)):
            with self.subTest(nivel=nivel):
                self.assertFalse(
                    pode_executar_autonomamente("POLICY_DEPENDENT", nivel, policy_dependente_aprovado=False)
                )

    def test_policy_dependente_com_aprovacao_e_nivel_suficiente_executa(self):
        nivel_suficiente = AUTONOMY_LEVELS.index("EXECUTE_LOW_RISK")
        self.assertTrue(
            pode_executar_autonomamente("POLICY_DEPENDENT", nivel_suficiente, policy_dependente_aprovado=True)
        )

    def test_policy_dependente_com_aprovacao_mas_nivel_insuficiente_nao_executa(self):
        nivel_insuficiente = AUTONOMY_LEVELS.index("DRAFT")
        self.assertFalse(
            pode_executar_autonomamente("POLICY_DEPENDENT", nivel_insuficiente, policy_dependente_aprovado=True)
        )

    def test_autonomous_em_nivel_baixo_nao_executa(self):
        for nome_nivel in ("OBSERVE", "RECOMMEND", "DRAFT"):
            with self.subTest(nivel=nome_nivel):
                self.assertFalse(
                    pode_executar_autonomamente("AUTONOMOUS", AUTONOMY_LEVELS.index(nome_nivel))
                )

    def test_autonomous_em_nivel_suficiente_executa(self):
        for nome_nivel in ("EXECUTE_LOW_RISK", "EXECUTE_HUMAN_APPROVAL", "AUTONOMOUS_WITHIN_POLICY"):
            with self.subTest(nivel=nome_nivel):
                self.assertTrue(
                    pode_executar_autonomamente("AUTONOMOUS", AUTONOMY_LEVELS.index(nome_nivel))
                )

    def test_fronteira_invalida_levanta(self):
        with self.assertRaises(ValueError):
            pode_executar_autonomamente("SEMPRE_PERMITIDO", 5)

    def test_nivel_fora_do_intervalo_levanta(self):
        with self.assertRaises(ValueError):
            pode_executar_autonomamente("AUTONOMOUS", 6)
        with self.assertRaises(ValueError):
            pode_executar_autonomamente("AUTONOMOUS", -1)


class DecisionBoundariesPadraoTest(unittest.TestCase):
    def test_tabela_padrao_tem_as_6_acoes_fixas_do_exemplo(self):
        self.assertEqual(
            set(DECISION_BOUNDARIES_PADRAO),
            {
                "dar_informacao_publica", "qualificar", "agendar_reuniao",
                "enviar_followup", "alteracao_juridica", "promessa_nao_documentada",
            },
        )

    def test_tabela_customizada_sobrescreve_a_padrao(self):
        boundaries_customizada = dict(DECISION_BOUNDARIES_PADRAO)
        boundaries_customizada["enviar_followup"] = "HUMAN_APPROVAL"
        self.assertEqual(avaliar_acao("enviar_followup", boundaries=boundaries_customizada), "HUMAN_APPROVAL")
        # a padrao global nao muda
        self.assertEqual(avaliar_acao("enviar_followup"), "AUTONOMOUS")


class LimiteDescontoPadraoTest(unittest.TestCase):
    def test_limite_padrao_e_5_por_cento(self):
        self.assertEqual(LIMITE_DESCONTO_POLICY_DEPENDENT_PADRAO, 5.0)


if __name__ == "__main__":
    unittest.main()
