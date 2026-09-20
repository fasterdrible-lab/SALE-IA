"""
Testes — Fase 23 ("PROMPT MESTRE — SALE-IA V2", Teste em Shadow Mode)
integrada em agent/multiagente/orquestrador.py.

Cobre: kill-switch SHADOW_MODE_ENABLED (default `false`) — desligado,
`raciocinar_async()` nunca é chamado, zero custo extra; ligado, roda
como fire-and-forget (asyncio.create_task) sem nunca atrasar/mudar o
`resultado` real, e persiste a comparação via
`agent/shadow_mode_rules.py::montar_registro_shadow()`.

Mesmo padrão de tests/test_orquestrador_bigfive.py — mocka os 5 agentes
+ as 3 buscas de RAG, nunca toca MySQL/rede real. Como a task de shadow
mode é fire-and-forget (não aguardada por analisar_fragmento_multi),
os testes que precisam confirmar seu efeito aguardam explicitamente
`orquestrador._SHADOW_MODE_TASKS` antes de asserir.

Run:
    python -m unittest tests.test_orquestrador_shadow_mode -v
"""

import asyncio
import logging
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

logging.disable(logging.CRITICAL)

import agent.multiagente.orquestrador as orquestrador
from agent.multiagente.orquestrador import analisar_fragmento_multi, shadow_mode_ativo


def _mock_rag():
    return (
        patch.object(orquestrador, "buscar_contexto_similar", new=AsyncMock(return_value=None)),
        patch("agent.sales_memory.buscar_contexto_para_reuniao", return_value=None),
        patch("api.database.buscar_conhecimento_compilado_similar", return_value=None),
    )


def _mock_agentes(nba=None, finance_result=None):
    coach_result = {"next_best_action": nba} if nba is not None else {}
    return [
        patch.object(orquestrador, "analisar_coach", new=AsyncMock(return_value=coach_result)),
        patch.object(orquestrador, "analisar_disc", new=AsyncMock(return_value={})),
        patch.object(orquestrador, "analisar_finance", new=AsyncMock(return_value=finance_result or {})),
        patch.object(orquestrador, "analisar_closer", new=AsyncMock(return_value={})),
        patch.object(orquestrador, "analisar_bigfive", new=AsyncMock(return_value={})),
    ]


async def _rodar_e_esperar_shadow(coro):
    """Roda `coro` (analisar_fragmento_multi) e, se alguma task de
    shadow mode foi agendada, aguarda ela terminar antes de retornar —
    sem isso, o teste terminaria antes do fire-and-forget rodar."""
    resultado = await coro
    tasks = list(orquestrador._SHADOW_MODE_TASKS)
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    return resultado


class KillSwitchTest(unittest.TestCase):
    def test_desligado_por_padrao(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SHADOW_MODE_ENABLED", None)
            self.assertFalse(shadow_mode_ativo())

    def test_ligado_com_true(self):
        with patch.dict(os.environ, {"SHADOW_MODE_ENABLED": "true"}):
            self.assertTrue(shadow_mode_ativo())

    def test_desligado_com_qualquer_outro_valor(self):
        with patch.dict(os.environ, {"SHADOW_MODE_ENABLED": "1"}):
            self.assertFalse(shadow_mode_ativo())


class ShadowModeDesligadoTest(unittest.TestCase):
    def test_raciocinar_async_nunca_e_chamado_com_kill_switch_off(self):
        raciocinar_mock = AsyncMock(return_value={"next_best_action": "x", "next_best_question": None})
        rag_patches = _mock_rag()
        agente_patches = _mock_agentes({"type": "question"})
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SHADOW_MODE_ENABLED", None)
            with patch("agent.sales_reasoning_engine.raciocinar_async", new=raciocinar_mock):
                for p in (*rag_patches, *agente_patches):
                    p.start()
                try:
                    resultado = asyncio.run(_rodar_e_esperar_shadow(
                        analisar_fragmento_multi("transcricao", meeting_id="m1")
                    ))
                finally:
                    for p in (*rag_patches, *agente_patches):
                        p.stop()

        raciocinar_mock.assert_not_awaited()
        self.assertIn("next_best_action", resultado)
        self.assertEqual(len(orquestrador._SHADOW_MODE_TASKS), 0)


class ShadowModeLigadoTest(unittest.TestCase):
    def _rodar(self, raciocinar_mock, criar_comparison_mock, nba_atual, finance_result=None, spin_mock=None):
        rag_patches = _mock_rag()
        agente_patches = _mock_agentes(nba_atual, finance_result=finance_result)
        with patch.dict(os.environ, {"SHADOW_MODE_ENABLED": "true"}):
            with patch("agent.sales_reasoning_engine.raciocinar_async", new=raciocinar_mock), \
                 patch("api.database.criar_shadow_mode_comparison", new=criar_comparison_mock), \
                 patch("api.database.obter_ultimo_ai_usage_event", return_value=None), \
                 patch("agent.spin_extractor.extrair_spin_state_async", new=spin_mock or AsyncMock(return_value=None)):
                for p in (*rag_patches, *agente_patches):
                    p.start()
                try:
                    return asyncio.run(_rodar_e_esperar_shadow(
                        analisar_fragmento_multi("transcricao", meeting_id="m1", usuario_id="seller-1")
                    ))
                finally:
                    for p in (*rag_patches, *agente_patches):
                        p.stop()

    def test_objecao_detectada_pelo_finance_vira_objections_na_entrada(self):
        raciocinar_mock = AsyncMock(return_value={
            "current_state": "x", "recommended_framework": "OBJECTION_INVESTIGATION",
            "next_best_action": "y", "next_best_question": None,
            "reason": "z", "confidence": 0.6, "hypotheses": [], "evidence": [],
            "missing_information": [], "avoid": [],
        })
        criar_comparison_mock = MagicMock(return_value=None)
        classificador_mock = AsyncMock(return_value="PRICE")
        nba_atual = {"type": "insight", "message": "..."}
        finance_result = {"objecao_detectada": {"objecao": "Achei caro pra ser sincero.", "resposta_pronta": "..."}}

        with patch("agent.objection_category_classifier.classificar_categoria_objecao_async", new=classificador_mock), \
             patch("agent.objection_root_cause_extractor.investigar_causa_raiz_async", new=AsyncMock(return_value=None)):
            self._rodar(raciocinar_mock, criar_comparison_mock, nba_atual, finance_result=finance_result)

        raciocinar_mock.assert_awaited_once()
        entrada = raciocinar_mock.await_args.args[0]
        self.assertEqual(len(entrada["objections"]), 1)
        self.assertEqual(entrada["objections"][0]["objection_spoken"]["category"], "PRICE")
        self.assertEqual(entrada["objections"][0]["objection_spoken"]["evidence_quote"], "Achei caro pra ser sincero.")

    def test_opportunity_vinculada_com_historical_pattern_preenche_entrada(self):
        raciocinar_mock = AsyncMock(return_value={
            "current_state": "x", "recommended_framework": "CLOSING",
            "next_best_action": "y", "next_best_question": None,
            "reason": "z", "confidence": 0.6, "hypotheses": [], "evidence": [],
            "missing_information": [], "avoid": [],
        })
        criar_comparison_mock = MagicMock(return_value=None)
        nba_atual = {"type": "insight", "message": "..."}
        insight = {"insight": "Estágio negociação converte 81%.", "evidence": {"valor": "negociacao"}, "sample": 60}

        with patch("agent.opportunity_link_rules.vincular_automaticamente_se_possivel", return_value=42), \
             patch("agent.historical_pattern_rules.obter_historical_pattern_da_opportunity", return_value=insight):
            self._rodar(raciocinar_mock, criar_comparison_mock, nba_atual)

        entrada = raciocinar_mock.await_args.args[0]
        self.assertEqual(entrada["historical_patterns"], insight)

    def test_sem_opportunity_vinculada_historical_patterns_fica_none(self):
        raciocinar_mock = AsyncMock(return_value={
            "current_state": "x", "recommended_framework": "CLOSING",
            "next_best_action": "y", "next_best_question": None,
            "reason": "z", "confidence": 0.6, "hypotheses": [], "evidence": [],
            "missing_information": [], "avoid": [],
        })
        criar_comparison_mock = MagicMock(return_value=None)
        nba_atual = {"type": "insight", "message": "..."}

        with patch("agent.opportunity_link_rules.vincular_automaticamente_se_possivel", return_value=None):
            self._rodar(raciocinar_mock, criar_comparison_mock, nba_atual)

        entrada = raciocinar_mock.await_args.args[0]
        self.assertIsNone(entrada["historical_patterns"])

    def test_spin_state_real_chega_na_entrada(self):
        raciocinar_mock = AsyncMock(return_value={
            "current_state": "x", "recommended_framework": "SPIN_PROBLEM",
            "next_best_action": "y", "next_best_question": None,
            "reason": "z", "confidence": 0.6, "hypotheses": [], "evidence": [],
            "missing_information": [], "avoid": [],
        })
        criar_comparison_mock = MagicMock(return_value=None)
        nba_atual = {"type": "insight", "message": "..."}
        cobertura = {
            "situation": {"known": [{"stage": "situation", "campo": "team_size", "valor": "8", "evidence_quote": "..."}], "missing": ["crm_tool"]},
            "problem": {"known": [], "missing": ["main_pain"]},
            "implication": {"known": [], "missing": ["financial_impact", "conversion_impact"]},
            "need_payoff": {"known": [], "missing": ["solution_value"]},
        }
        spin_mock = AsyncMock(return_value=cobertura)

        self._rodar(raciocinar_mock, criar_comparison_mock, nba_atual, spin_mock=spin_mock)

        entrada = raciocinar_mock.await_args.args[0]
        self.assertEqual(entrada["spin_state"], cobertura)

    def test_falha_na_extracao_de_spin_state_nunca_derruba_ciclo(self):
        raciocinar_mock = AsyncMock(return_value={
            "current_state": "x", "recommended_framework": "CLOSING",
            "next_best_action": "y", "next_best_question": None,
            "reason": "z", "confidence": 0.6, "hypotheses": [], "evidence": [],
            "missing_information": [], "avoid": [],
        })
        criar_comparison_mock = MagicMock(return_value=None)
        nba_atual = {"type": "insight", "message": "..."}
        spin_mock = AsyncMock(side_effect=RuntimeError("4 provedores esgotados"))

        resultado = self._rodar(raciocinar_mock, criar_comparison_mock, nba_atual, spin_mock=spin_mock)

        self.assertIn("next_best_action", resultado)
        entrada = raciocinar_mock.await_args.args[0]
        self.assertIsNone(entrada["spin_state"])

    def test_sem_objecao_detectada_objections_fica_none(self):
        raciocinar_mock = AsyncMock(return_value={
            "current_state": "x", "recommended_framework": "CLOSING",
            "next_best_action": "y", "next_best_question": None,
            "reason": "z", "confidence": 0.6, "hypotheses": [], "evidence": [],
            "missing_information": [], "avoid": [],
        })
        criar_comparison_mock = MagicMock(return_value=None)
        nba_atual = {"type": "insight", "message": "..."}

        self._rodar(raciocinar_mock, criar_comparison_mock, nba_atual)

        entrada = raciocinar_mock.await_args.args[0]
        self.assertIsNone(entrada["objections"])

    def test_resultado_real_nunca_muda_mesmo_com_shadow_ligado(self):
        raciocinar_mock = AsyncMock(return_value={
            "current_state": "x", "recommended_framework": "SPIN_PROBLEM",
            "next_best_action": "Pergunte sobre o problema.", "next_best_question": "Qual o problema?",
            "reason": "y", "confidence": 0.7, "hypotheses": [], "evidence": [],
            "missing_information": [], "avoid": [],
        })
        criar_comparison_mock = MagicMock(return_value=None)
        nba_atual = {"type": "question", "message": "O que motivou vocês a buscar isso agora?"}
        resultado = self._rodar(raciocinar_mock, criar_comparison_mock, nba_atual)

        # o resultado real devolvido ao vendedor e o de sempre — o shadow
        # mode nunca sobrescreve next_best_action nem nenhum outro campo.
        self.assertEqual(resultado["next_best_action"], nba_atual)
        raciocinar_mock.assert_awaited_once()

    def test_persiste_comparacao_com_concordancia_calculada(self):
        raciocinar_mock = AsyncMock(return_value={
            "current_state": "x", "recommended_framework": "SPIN_PROBLEM",
            "next_best_action": "Pergunte sobre o problema.", "next_best_question": "Qual o problema?",
            "reason": "y", "confidence": 0.7, "hypotheses": [], "evidence": [],
            "missing_information": [], "avoid": [],
        })
        criar_comparison_mock = MagicMock(return_value=None)
        nba_atual = {"type": "question", "message": "..."}
        self._rodar(raciocinar_mock, criar_comparison_mock, nba_atual)

        criar_comparison_mock.assert_called_once()
        kwargs = criar_comparison_mock.call_args.kwargs
        self.assertEqual(kwargs["meeting_id"], "m1")
        self.assertEqual(kwargs["usuario_id"], "seller-1")
        self.assertTrue(kwargs["concordancia"])  # ambos recomendam pergunta

    def test_causa_raiz_real_chega_na_objection_da_entrada(self):
        raciocinar_mock = AsyncMock(return_value={
            "current_state": "x", "recommended_framework": "NEGOTIATION",
            "next_best_action": "y", "next_best_question": None,
            "reason": "z", "confidence": 0.6, "hypotheses": [], "evidence": [],
            "missing_information": [], "avoid": [],
        })
        criar_comparison_mock = MagicMock(return_value=None)
        classificador_mock = AsyncMock(return_value="PRICE")
        causa_raiz_mock = AsyncMock(return_value={
            "hypothesis": "SEM_ORCAMENTO_APROVADO",
            "evidence_quote": "Ainda não fechamos o orçamento desse trimestre.",
            "confidence": 0.8,
        })
        nba_atual = {"type": "insight", "message": "..."}
        finance_result = {"objecao_detectada": {"objecao": "Achei caro pra ser sincero.", "resposta_pronta": "..."}}

        with patch("agent.objection_category_classifier.classificar_categoria_objecao_async", new=classificador_mock), \
             patch("agent.objection_root_cause_extractor.investigar_causa_raiz_async", new=causa_raiz_mock):
            self._rodar(raciocinar_mock, criar_comparison_mock, nba_atual, finance_result=finance_result)

        entrada = raciocinar_mock.await_args.args[0]
        objecao = entrada["objections"][0]
        self.assertEqual(objecao["root_cause_hypothesis"]["hypothesis"], "SEM_ORCAMENTO_APROVADO")
        self.assertFalse(objecao["precisa_investigar"])

    def test_falha_do_modelo_novo_persiste_erro_nunca_derruba_ciclo(self):
        raciocinar_mock = AsyncMock(side_effect=ValueError("resposta da IA malformada"))
        criar_comparison_mock = MagicMock(return_value=None)
        nba_atual = {"type": "insight", "message": "..."}
        resultado = self._rodar(raciocinar_mock, criar_comparison_mock, nba_atual)

        self.assertIn("next_best_action", resultado)  # ciclo real nao quebrou
        criar_comparison_mock.assert_called_once()
        kwargs = criar_comparison_mock.call_args.kwargs
        self.assertIsNone(kwargs["concordancia"])
        self.assertIn("resposta da IA malformada", kwargs["erro"])

    def test_falha_ao_persistir_nunca_quebra_o_ciclo(self):
        raciocinar_mock = AsyncMock(return_value={
            "current_state": "x", "recommended_framework": "CLOSING",
            "next_best_action": "Feche.", "next_best_question": None,
            "reason": "y", "confidence": 0.9, "hypotheses": [], "evidence": [],
            "missing_information": [], "avoid": [],
        })
        criar_comparison_mock = MagicMock(side_effect=RuntimeError("banco indisponível"))
        nba_atual = {"type": "next_step", "message": "..."}
        # nao deve levantar
        resultado = self._rodar(raciocinar_mock, criar_comparison_mock, nba_atual)
        self.assertIn("next_best_action", resultado)


if __name__ == "__main__":
    unittest.main()
