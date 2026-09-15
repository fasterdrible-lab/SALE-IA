# -*- coding: utf-8 -*-
"""
Testes de agent/conversation_metrics_rules.py — Fase 11 / Tarefa 11.1
do "PROMPT MESTRE — SALE-IA V2" (Conversation Metrics), inicio da Fase
11 (Seller Coaching).

Modulo puro (sem IA, sem banco) — mesmo padrao de
tests/test_recommendation_effectiveness_rules.py. Segue a instrucao
literal da Tarefa 11.1: "Criar transcricoes temporizadas conhecidas.
Comparar calculo esperado com calculo real."

Run:
    python -m unittest tests.test_conversation_metrics_rules -v
"""

import random
import unittest

from agent.conversation_metrics_rules import calcular_metricas_conversa


def _turn(speaker, start, end, text="", **flags):
    turn = {"speaker": speaker, "start": start, "end": end, "text": text}
    turn.update(flags)
    return turn


# Transcricao temporizada conhecida, com valores esperados calculados a
# mao (ver comentarios) — usada por varios testes abaixo.
TRANSCRICAO_CONHECIDA = [
    _turn("vendedor", 0, 5, "Oi, tudo bem?"),
    _turn("cliente", 5, 15, "Tudo bem sim, e você?"),
    _turn("vendedor", 15, 20, "Qual o principal desafio de vocês hoje?"),
    _turn("cliente", 20, 60, "Nosso principal desafio é o follow-up lento."),
    _turn("vendedor", 60, 65, "Entendi, e isso já causou perda de contrato recentemente?"),
    _turn("cliente", 65, 200, "Sim, perdemos um contrato grande em março por causa disso."),
    _turn("vendedor", 200, 260, "Isso realmente é grave. Deixa eu te mostrar como resolvemos.", is_presentation_mention=True),
    _turn("cliente", 260, 262, "Faz sentido, mas quanto isso custa?"),
    _turn("vendedor", 262, 290, "O investimento mensal fica em torno de dois mil reais.", is_price_mention=True),
    _turn("cliente", 288, 295, "Espera, deixa eu..."),
    _turn("vendedor", 295, 300, "Claro, pode falar."),
]


class TalkRatioTest(unittest.TestCase):
    def test_ratios_batem_com_calculo_manual(self):
        # tempo_vendedor = 5+5+5+60+28+5 = 108 ; tempo_cliente = 10+40+135+2+7 = 194
        resumo = calcular_metricas_conversa(TRANSCRICAO_CONHECIDA)
        self.assertAlmostEqual(resumo["seller_talk_ratio"], 108 / 302)
        self.assertAlmostEqual(resumo["customer_talk_ratio"], 194 / 302)
        self.assertAlmostEqual(resumo["seller_talk_ratio"] + resumo["customer_talk_ratio"], 1.0)

    def test_sem_nenhum_turno_de_vendedor_ou_cliente_ratio_e_none(self):
        turns = [_turn("incerto", 0, 10, "algo inaudível")]
        resumo = calcular_metricas_conversa(turns)
        self.assertIsNone(resumo["seller_talk_ratio"])
        self.assertIsNone(resumo["customer_talk_ratio"])

    def test_turno_de_falante_incerto_nao_entra_no_denominador(self):
        turns = [
            _turn("vendedor", 0, 10),
            _turn("incerto", 10, 1000),  # duração enorme, não deve distorcer o ratio
        ]
        resumo = calcular_metricas_conversa(turns)
        self.assertAlmostEqual(resumo["seller_talk_ratio"], 1.0)
        self.assertAlmostEqual(resumo["customer_talk_ratio"], 0.0)


class QuestionsTest(unittest.TestCase):
    def test_contagem_e_classificacao_batem_com_calculo_manual(self):
        # 3 perguntas do vendedor: "Oi, tudo bem?" (fechada), "Qual...?" (aberta),
        # "...recentemente?" (fechada) -- perguntas do cliente não contam.
        resumo = calcular_metricas_conversa(TRANSCRICAO_CONHECIDA)
        self.assertEqual(resumo["questions_total"], 3)
        self.assertEqual(resumo["open_questions"], 1)
        self.assertEqual(resumo["closed_questions"], 2)

    def test_pergunta_do_cliente_nao_conta(self):
        turns = [_turn("cliente", 0, 5, "Quanto custa?")]
        resumo = calcular_metricas_conversa(turns)
        self.assertEqual(resumo["questions_total"], 0)

    def test_turno_sem_interrogacao_nao_conta_como_pergunta(self):
        turns = [_turn("vendedor", 0, 5, "Isso é ótimo.")]
        resumo = calcular_metricas_conversa(turns)
        self.assertEqual(resumo["questions_total"], 0)


class InterruptionsTest(unittest.TestCase):
    def test_uma_interrupcao_detectada_no_exemplo_conhecido(self):
        # turno do cliente (288-295) começa antes do turno anterior do
        # vendedor terminar (262-290) -> 1 interrupção.
        resumo = calcular_metricas_conversa(TRANSCRICAO_CONHECIDA)
        self.assertEqual(resumo["interruptions"], 1)

    def test_turnos_encadeados_sem_sobreposicao_nao_contam(self):
        turns = [_turn("vendedor", 0, 10), _turn("cliente", 10, 20)]
        resumo = calcular_metricas_conversa(turns)
        self.assertEqual(resumo["interruptions"], 0)

    def test_sobreposicao_do_mesmo_falante_nao_conta(self):
        turns = [_turn("vendedor", 0, 10), _turn("vendedor", 8, 15)]
        resumo = calcular_metricas_conversa(turns)
        self.assertEqual(resumo["interruptions"], 0)

    def test_sobreposicao_envolvendo_falante_incerto_nao_conta(self):
        turns = [_turn("vendedor", 0, 10), _turn("incerto", 5, 15)]
        resumo = calcular_metricas_conversa(turns)
        self.assertEqual(resumo["interruptions"], 0)


class MonologuesTest(unittest.TestCase):
    def test_um_monologo_detectado_no_exemplo_conhecido(self):
        # só o turno do cliente de 65-200 (135s) passa do limiar padrão (90s).
        resumo = calcular_metricas_conversa(TRANSCRICAO_CONHECIDA)
        self.assertEqual(resumo["monologues"], 1)

    def test_turnos_consecutivos_do_mesmo_falante_sao_mesclados(self):
        # dois turnos seguidos do vendedor (sem fala do cliente entre eles)
        # somam 100s -- deve contar como 1 monólogo só, não 2.
        turns = [
            _turn("vendedor", 0, 50),
            _turn("vendedor", 50, 100),
            _turn("cliente", 100, 105),
        ]
        resumo = calcular_metricas_conversa(turns)
        self.assertEqual(resumo["monologues"], 1)

    def test_limiar_customizado(self):
        turns = [_turn("vendedor", 0, 30)]
        self.assertEqual(calcular_metricas_conversa(turns, limiar_monologo_segundos=60.0)["monologues"], 0)
        self.assertEqual(calcular_metricas_conversa(turns, limiar_monologo_segundos=20.0)["monologues"], 1)


class TimingTest(unittest.TestCase):
    def test_price_e_presentation_timing_batem_com_o_turno_marcado(self):
        resumo = calcular_metricas_conversa(TRANSCRICAO_CONHECIDA)
        self.assertEqual(resumo["presentation_timing"], 200.0)
        self.assertEqual(resumo["price_timing"], 262.0)

    def test_sem_nenhum_turno_marcado_timing_e_none(self):
        turns = [_turn("vendedor", 0, 10, "Sem menção a preço ou apresentação.")]
        resumo = calcular_metricas_conversa(turns)
        self.assertIsNone(resumo["price_timing"])
        self.assertIsNone(resumo["presentation_timing"])

    def test_usa_o_primeiro_turno_marcado_quando_ha_mais_de_um(self):
        turns = [
            _turn("vendedor", 50, 55, is_price_mention=True),
            _turn("vendedor", 10, 15, is_price_mention=True),
        ]
        resumo = calcular_metricas_conversa(turns)
        self.assertEqual(resumo["price_timing"], 10.0)


class ObjectionExplorationRateTest(unittest.TestCase):
    def test_taxa_bate_com_calculo_manual(self):
        objections = [{"explored": True}, {"explored": False}, {"explored": True}]
        resumo = calcular_metricas_conversa([], objections=objections)
        self.assertAlmostEqual(resumo["objection_exploration_rate"], 2 / 3)

    def test_sem_nenhuma_objecao_taxa_e_none(self):
        resumo = calcular_metricas_conversa([], objections=None)
        self.assertIsNone(resumo["objection_exploration_rate"])

        resumo_vazio = calcular_metricas_conversa([], objections=[])
        self.assertIsNone(resumo_vazio["objection_exploration_rate"])


class NextStepRateTest(unittest.TestCase):
    def test_none_quando_dado_nao_existe(self):
        resumo = calcular_metricas_conversa([], next_step_proposto=None)
        self.assertIsNone(resumo["next_step_rate"])

    def test_verdadeiro_vira_1_falso_vira_0(self):
        self.assertEqual(calcular_metricas_conversa([], next_step_proposto=True)["next_step_rate"], 1.0)
        self.assertEqual(calcular_metricas_conversa([], next_step_proposto=False)["next_step_rate"], 0.0)


class OrdemDosTurnosTest(unittest.TestCase):
    def test_funcao_ordena_internamente_por_start(self):
        embaralhado = list(TRANSCRICAO_CONHECIDA)
        random.Random(7).shuffle(embaralhado)
        resumo_embaralhado = calcular_metricas_conversa(embaralhado)
        resumo_ordenado = calcular_metricas_conversa(TRANSCRICAO_CONHECIDA)
        self.assertEqual(resumo_embaralhado, resumo_ordenado)


class TranscricaoVaziaTest(unittest.TestCase):
    def test_transcricao_vazia_nao_quebra(self):
        resumo = calcular_metricas_conversa([])
        self.assertIsNone(resumo["seller_talk_ratio"])
        self.assertIsNone(resumo["customer_talk_ratio"])
        self.assertEqual(resumo["questions_total"], 0)
        self.assertEqual(resumo["interruptions"], 0)
        self.assertEqual(resumo["monologues"], 0)
        self.assertIsNone(resumo["price_timing"])
        self.assertIsNone(resumo["presentation_timing"])
        self.assertIsNone(resumo["objection_exploration_rate"])
        self.assertIsNone(resumo["next_step_rate"])


if __name__ == "__main__":
    unittest.main()
