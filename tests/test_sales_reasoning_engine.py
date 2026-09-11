"""
Testes do SalesReasoningEngine — Fase 7 / Tarefa 7.1 do "PROMPT MESTRE
— SALE-IA V2".

Escopo desta rodada (decisão explícita do usuário): só o CONTRATO de
entrada/saída, sem nenhuma chamada de IA — reproduz o exemplo literal
de saída do prompt mestre, mas não implementa o raciocínio real (fica
para tarefa futura, junto do Golden Dataset de 50+ cenários pedido pelo
prompt mestre).

Run:
    python -m unittest tests.test_sales_reasoning_engine -v
"""

import unittest

from agent.sales_reasoning_engine import (
    SALES_REASONING_INPUT_CAMPOS,
    SALES_REASONING_OUTPUT_CAMPOS,
    construir_input_vazio,
    montar_saida_raciocinio,
    validar_input_raciocinio,
    validar_output_raciocinio,
)


class ContratoDeEntradaTest(unittest.TestCase):
    def test_os_11_campos_literais_do_prompt_mestre(self):
        self.assertEqual(
            SALES_REASONING_INPUT_CAMPOS,
            (
                "meeting_memory", "opportunity_memory", "opportunity_graph",
                "spin_state", "meddpicc_state", "buyer_motivation", "objections",
                "behavioral_signals", "rag_context", "seller_context", "historical_patterns",
            ),
        )

    def test_construir_input_vazio_tem_todos_os_campos_como_none(self):
        entrada = construir_input_vazio()
        self.assertEqual(set(entrada.keys()), set(SALES_REASONING_INPUT_CAMPOS))
        for campo in SALES_REASONING_INPUT_CAMPOS:
            self.assertIsNone(entrada[campo])

    def test_input_vazio_nao_levanta(self):
        validar_input_raciocinio(construir_input_vazio())

    def test_input_parcialmente_preenchido_nao_levanta(self):
        entrada = construir_input_vazio()
        entrada["spin_state"] = {"situation": {"known": [], "missing": ["team_size"]}}
        entrada["meddpicc_state"] = {"economic_buyer": {"status": "UNKNOWN"}}
        validar_input_raciocinio(entrada)

    def test_campo_desconhecido_levanta(self):
        entrada = construir_input_vazio()
        entrada["disc_state"] = {"perfil": "D"}
        with self.assertRaises(ValueError):
            validar_input_raciocinio(entrada)


class ContratoDeSaidaTest(unittest.TestCase):
    def test_os_10_campos_literais_do_prompt_mestre(self):
        self.assertEqual(
            SALES_REASONING_OUTPUT_CAMPOS,
            (
                "current_state", "hypotheses", "evidence", "missing_information",
                "recommended_framework", "next_best_action", "next_best_question",
                "avoid", "reason", "confidence",
            ),
        )

    def test_exemplo_literal_do_prompt_mestre(self):
        """Reproduz o exemplo exato da Tarefa 7.1 (sem next_best_question
        no exemplo original — aqui incluida pra exercitar o campo)."""
        saida = montar_saida_raciocinio(
            current_state="cliente reconhece dor, mas impacto econômico ainda não está claro",
            recommended_framework="SPIN_IMPLICATION",
            next_best_action="aprofundar impacto",
            next_best_question="Quanto esse problema afeta a operação por mês?",
            avoid=["não apresentar preço ainda"],
            reason="dor confirmada mas sem impacto financeiro mapeado ainda",
            confidence=0.86,
        )

        self.assertEqual(saida["recommended_framework"], "SPIN_IMPLICATION")
        self.assertEqual(saida["next_best_action"], "aprofundar impacto")
        self.assertEqual(saida["next_best_question"], "Quanto esse problema afeta a operação por mês?")
        self.assertEqual(saida["avoid"], ["não apresentar preço ainda"])
        self.assertEqual(saida["confidence"], 0.86)

    def test_campos_lista_default_para_lista_vazia(self):
        saida = montar_saida_raciocinio(
            current_state="abertura da reuniao, sem sinal estruturado ainda",
            recommended_framework="SPIN_SITUATION",
            next_best_action="mapear contexto do cliente",
            reason="nenhum dado estruturado disponivel ainda",
            confidence=0.3,
        )
        self.assertEqual(saida["hypotheses"], [])
        self.assertEqual(saida["evidence"], [])
        self.assertEqual(saida["missing_information"], [])
        self.assertEqual(saida["avoid"], [])

    def test_next_best_question_pode_ser_none(self):
        saida = montar_saida_raciocinio(
            current_state="cliente ja confirmou fechamento verbal",
            recommended_framework="CLOSING",
            next_best_action="enviar contrato",
            reason="todos os criterios MEDDPICC confirmados",
            confidence=0.9,
        )
        self.assertIsNone(saida["next_best_question"])

    def test_current_state_vazio_levanta(self):
        with self.assertRaises(ValueError):
            montar_saida_raciocinio(
                current_state="",
                recommended_framework="SPIN_SITUATION",
                next_best_action="mapear contexto",
                reason="motivo",
                confidence=0.5,
            )

    def test_recommended_framework_vazio_levanta(self):
        with self.assertRaises(ValueError):
            montar_saida_raciocinio(
                current_state="estado atual",
                recommended_framework="",
                next_best_action="mapear contexto",
                reason="motivo",
                confidence=0.5,
            )

    def test_confidence_fora_do_intervalo_levanta(self):
        with self.assertRaises(ValueError):
            montar_saida_raciocinio(
                current_state="estado atual",
                recommended_framework="SPIN_SITUATION",
                next_best_action="mapear contexto",
                reason="motivo",
                confidence=1.5,
            )

    def test_hypotheses_que_nao_e_lista_levanta_via_validar_output(self):
        saida_invalida = {
            "current_state": "estado atual",
            "hypotheses": "nao deveria ser string",
            "evidence": [],
            "missing_information": [],
            "recommended_framework": "SPIN_SITUATION",
            "next_best_action": "mapear contexto",
            "next_best_question": None,
            "avoid": [],
            "reason": "motivo",
            "confidence": 0.5,
        }
        with self.assertRaises(ValueError):
            validar_output_raciocinio(saida_invalida)

    def test_next_best_question_tipo_invalido_levanta(self):
        saida_invalida = {
            "current_state": "estado atual",
            "hypotheses": [],
            "evidence": [],
            "missing_information": [],
            "recommended_framework": "SPIN_SITUATION",
            "next_best_action": "mapear contexto",
            "next_best_question": 123,
            "avoid": [],
            "reason": "motivo",
            "confidence": 0.5,
        }
        with self.assertRaises(ValueError):
            validar_output_raciocinio(saida_invalida)


if __name__ == "__main__":
    unittest.main()
