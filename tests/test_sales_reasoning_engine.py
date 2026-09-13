"""
Testes do SalesReasoningEngine — Fase 7 / Tarefa 7.1 do "PROMPT MESTRE
— SALE-IA V2".

Cobre o CONTRATO de entrada/saída (rodada anterior) e o motor real
`raciocinar_async()` (esta rodada) — mesmo padrão de mock de
tests/test_bigfive_agent.py, no nível de `chamar_ia_com_fallback_claude`
(ponto de entrada real do motor). Golden Dataset de 50+ cenários fica em
`evals/datasets/sales_reasoning/` (harness Promptfoo, custa dinheiro
real por cenário — nunca roda dentro da suíte unittest).

Run:
    python -m unittest tests.test_sales_reasoning_engine -v
"""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from agent.sales_reasoning_engine import (
    SALES_REASONING_FRAMEWORKS,
    SALES_REASONING_INPUT_CAMPOS,
    SALES_REASONING_OUTPUT_CAMPOS,
    construir_input_vazio,
    montar_saida_raciocinio,
    raciocinar_async,
    validar_input_raciocinio,
    validar_output_raciocinio,
)
from api import ai_features


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


class RaciocinarAsyncTest(unittest.TestCase):
    """Motor real (esta rodada) — mocka chamar_ia_com_fallback_claude, mesmo
    padrão de tests/test_bigfive_agent.py/test_closer_agent equivalente."""

    def _run(self, entrada=None, **kwargs):
        return asyncio.run(raciocinar_async(entrada if entrada is not None else {}, **kwargs))

    def _resposta_valida(self, **overrides):
        base = dict(
            current_state="cliente reconhece dor, mas impacto econômico ainda não está claro",
            recommended_framework="SPIN_IMPLICATION",
            next_best_action="aprofundar impacto",
            next_best_question="Quanto esse problema afeta a operação por mês?",
            avoid=["não apresentar preço ainda"],
            reason="dor confirmada mas sem impacto financeiro mapeado ainda",
            confidence=0.86,
        )
        base.update(overrides)
        return base

    def test_usa_feature_sales_reasoning_raciocinio(self):
        with patch(
            "agent.sales_reasoning_engine.chamar_ia_com_fallback_claude",
            new=AsyncMock(return_value=self._resposta_valida()),
        ) as mock_chamar:
            resultado = self._run(usuario_id="u1", meeting_id="m1")

        self.assertEqual(resultado["recommended_framework"], "SPIN_IMPLICATION")
        _, kwargs = mock_chamar.call_args
        self.assertEqual(kwargs.get("feature"), ai_features.SALES_REASONING_RACIOCINIO)
        self.assertEqual(kwargs.get("meeting_id"), "m1")

    def test_entrada_vazia_nao_levanta_e_serializa_null(self):
        with patch(
            "agent.sales_reasoning_engine.chamar_ia_com_fallback_claude",
            new=AsyncMock(return_value=self._resposta_valida()),
        ) as mock_chamar:
            self._run({})

        args, _ = mock_chamar.call_args
        _system, prompt, *_ = args
        for campo in SALES_REASONING_INPUT_CAMPOS:
            self.assertNotIn("{" + campo + "}", prompt)
        self.assertIn("null", prompt)

    def test_campos_preenchidos_sao_serializados_no_prompt(self):
        entrada = {
            "spin_state": {"implication": {"known": [], "missing": ["impacto_financeiro"]}},
            "objections": [{"objection_spoken": {"category": "PRICE"}, "precisa_investigar": True}],
        }
        with patch(
            "agent.sales_reasoning_engine.chamar_ia_com_fallback_claude",
            new=AsyncMock(return_value=self._resposta_valida()),
        ) as mock_chamar:
            self._run(entrada)

        args, _ = mock_chamar.call_args
        _system, prompt, *_ = args
        self.assertIn(json.dumps(entrada["spin_state"], ensure_ascii=False), prompt)
        self.assertIn(json.dumps(entrada["objections"], ensure_ascii=False), prompt)

    def test_campo_desconhecido_na_entrada_levanta(self):
        with patch(
            "agent.sales_reasoning_engine.chamar_ia_com_fallback_claude",
            new=AsyncMock(return_value=self._resposta_valida()),
        ):
            with self.assertRaises(ValueError):
                self._run({"disc_state": {"perfil": "D"}})

    def test_resposta_da_ia_e_validada_contra_o_contrato_de_saida(self):
        resposta_invalida = self._resposta_valida(current_state="")
        with patch(
            "agent.sales_reasoning_engine.chamar_ia_com_fallback_claude",
            new=AsyncMock(return_value=resposta_invalida),
        ):
            with self.assertRaises(ValueError):
                self._run({})

    def test_resposta_sem_campos_lista_normaliza_para_lista_vazia(self):
        resposta_minima = {
            "current_state": "abertura, sem sinal estruturado ainda",
            "recommended_framework": "SPIN_SITUATION",
            "next_best_action": "mapear contexto do cliente",
            "reason": "nenhum dado estruturado disponivel ainda",
            "confidence": 0.3,
        }
        with patch(
            "agent.sales_reasoning_engine.chamar_ia_com_fallback_claude",
            new=AsyncMock(return_value=resposta_minima),
        ):
            resultado = self._run({})

        self.assertEqual(resultado["hypotheses"], [])
        self.assertEqual(resultado["evidence"], [])
        self.assertEqual(resultado["missing_information"], [])
        self.assertEqual(resultado["avoid"], [])
        self.assertIsNone(resultado["next_best_question"])

    def test_frameworks_fechados_incluem_os_9_do_prompt(self):
        self.assertEqual(
            SALES_REASONING_FRAMEWORKS,
            (
                "SPIN_SITUATION", "SPIN_PROBLEM", "SPIN_IMPLICATION", "SPIN_NEED_PAYOFF",
                "MEDDPICC_QUALIFICATION", "OBJECTION_INVESTIGATION", "NEGOTIATION",
                "RISK_MITIGATION", "CLOSING",
            ),
        )


if __name__ == "__main__":
    unittest.main()
