"""
Testes — Fase 24 ("PROMPT MESTRE — SALE-IA V2", Piloto) integrada em
agent/multiagente/orquestrador.py.

Cobre: feature flag PILOT_MODE (default `off`); modo `pilot_user`
(allowlist) e `100pct` de fato substituem `resultado["next_best_
action"]` pela saída de `raciocinar_async()`, sempre `await`ada (não
fire-and-forget); fail-open (falha do modelo novo ou do mapeamento
preserva a recomendação atual); mutuamente exclusivo com o Shadow Mode
(nunca chama a IA 2x no mesmo ciclo pro mesmo usuário); comparação
persistida com origem="piloto".

Mesmo padrão de tests/test_orquestrador_shadow_mode.py.

Run:
    python -m unittest tests.test_orquestrador_piloto -v
"""

import asyncio
import logging
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

logging.disable(logging.CRITICAL)

import agent.multiagente.orquestrador as orquestrador
from agent.multiagente.orquestrador import analisar_fragmento_multi


def _mock_rag():
    return (
        patch.object(orquestrador, "buscar_contexto_similar", new=AsyncMock(return_value=None)),
        patch("agent.sales_memory.buscar_contexto_para_reuniao", return_value=None),
        patch("api.database.buscar_conhecimento_compilado_similar", return_value=None),
    )


def _mock_agentes(nba=None):
    coach_result = {"next_best_action": nba} if nba is not None else {}
    return [
        patch.object(orquestrador, "analisar_coach", new=AsyncMock(return_value=coach_result)),
        patch.object(orquestrador, "analisar_disc", new=AsyncMock(return_value={})),
        patch.object(orquestrador, "analisar_finance", new=AsyncMock(return_value={})),
        patch.object(orquestrador, "analisar_closer", new=AsyncMock(return_value={})),
        patch.object(orquestrador, "analisar_bigfive", new=AsyncMock(return_value={})),
    ]


class PilotoDesligadoTest(unittest.TestCase):
    def test_off_por_padrao_nunca_chama_raciocinar_async(self):
        raciocinar_mock = AsyncMock(return_value={
            "current_state": "x", "recommended_framework": "CLOSING",
            "next_best_action": "y", "next_best_question": None,
            "reason": "z", "confidence": 0.9, "hypotheses": [], "evidence": [],
            "missing_information": [], "avoid": [],
        })
        nba_atual = {"type": "question", "message": "pergunta original"}
        rag_patches = _mock_rag()
        agente_patches = _mock_agentes(nba_atual)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PILOT_MODE", None)
            os.environ.pop("SHADOW_MODE_ENABLED", None)
            with patch("agent.sales_reasoning_engine.raciocinar_async", new=raciocinar_mock):
                for p in (*rag_patches, *agente_patches):
                    p.start()
                try:
                    resultado = asyncio.run(analisar_fragmento_multi("t", meeting_id="m1", usuario_id="seller-1"))
                finally:
                    for p in (*rag_patches, *agente_patches):
                        p.stop()

        raciocinar_mock.assert_not_awaited()
        self.assertEqual(resultado["next_best_action"], nba_atual)


class PilotoLigadoTest(unittest.TestCase):
    def _rodar(self, env, raciocinar_mock, criar_comparison_mock, nba_atual, usuario_id="seller-1"):
        rag_patches = _mock_rag()
        agente_patches = _mock_agentes(nba_atual)
        with patch.dict(os.environ, env):
            with patch("agent.sales_reasoning_engine.raciocinar_async", new=raciocinar_mock), \
                 patch("api.database.criar_shadow_mode_comparison", new=criar_comparison_mock), \
                 patch("api.database.obter_ultimo_ai_usage_event", return_value=None):
                for p in (*rag_patches, *agente_patches):
                    p.start()
                try:
                    return asyncio.run(analisar_fragmento_multi("t", meeting_id="m1", usuario_id=usuario_id))
                finally:
                    for p in (*rag_patches, *agente_patches):
                        p.stop()

    def test_pilot_user_dentro_da_allowlist_substitui_recomendacao(self):
        raciocinar_mock = AsyncMock(return_value={
            "current_state": "Cliente sem orçamento validado.", "recommended_framework": "MEDDPICC_QUALIFICATION",
            "next_best_action": "Pergunte sobre o orçamento.", "next_best_question": "Qual o orçamento disponível?",
            "reason": "MEDDPICC Metrics ausente.", "confidence": 0.8, "hypotheses": [], "evidence": [],
            "missing_information": [], "avoid": [],
        })
        criar_comparison_mock = MagicMock(return_value=None)
        nba_atual = {"type": "question", "message": "pergunta do modelo atual"}
        resultado = self._rodar(
            {"PILOT_MODE": "pilot_user", "PILOT_USER_IDS": "seller-1,seller-2"},
            raciocinar_mock, criar_comparison_mock, nba_atual,
        )

        raciocinar_mock.assert_awaited_once()
        self.assertEqual(resultado["next_best_action"]["message"], "Qual o orçamento disponível?")
        self.assertEqual(resultado["next_best_action"]["type"], "question")
        self.assertNotEqual(resultado["next_best_action"], nba_atual)

    def test_pilot_user_fora_da_allowlist_mantem_modelo_atual(self):
        raciocinar_mock = AsyncMock(return_value={
            "current_state": "x", "recommended_framework": "CLOSING",
            "next_best_action": "y", "next_best_question": None,
            "reason": "z", "confidence": 0.9, "hypotheses": [], "evidence": [],
            "missing_information": [], "avoid": [],
        })
        criar_comparison_mock = MagicMock(return_value=None)
        nba_atual = {"type": "question", "message": "pergunta original"}
        resultado = self._rodar(
            {"PILOT_MODE": "pilot_user", "PILOT_USER_IDS": "outro-vendedor"},
            raciocinar_mock, criar_comparison_mock, nba_atual, usuario_id="seller-1",
        )

        raciocinar_mock.assert_not_awaited()
        self.assertEqual(resultado["next_best_action"], nba_atual)

    def test_modo_100pct_qualquer_usuario_entra(self):
        raciocinar_mock = AsyncMock(return_value={
            "current_state": "x", "recommended_framework": "CLOSING",
            "next_best_action": "Feche a venda.", "next_best_question": None,
            "reason": "z", "confidence": 0.95, "hypotheses": [], "evidence": [],
            "missing_information": [], "avoid": ["prometer desconto"],
        })
        criar_comparison_mock = MagicMock(return_value=None)
        nba_atual = {"type": "next_step", "message": "acao original"}
        resultado = self._rodar(
            {"PILOT_MODE": "100pct"}, raciocinar_mock, criar_comparison_mock, nba_atual, usuario_id="qualquer-id",
        )

        raciocinar_mock.assert_awaited_once()
        self.assertEqual(resultado["next_best_action"]["message"], "Feche a venda.")
        self.assertEqual(resultado["next_best_action"]["evite"], "prometer desconto")

    def test_falha_do_modelo_novo_preserva_recomendacao_atual_fail_open(self):
        raciocinar_mock = AsyncMock(side_effect=ValueError("resposta malformada"))
        criar_comparison_mock = MagicMock(return_value=None)
        nba_atual = {"type": "insight", "message": "recomendacao original preservada"}
        resultado = self._rodar(
            {"PILOT_MODE": "100pct"}, raciocinar_mock, criar_comparison_mock, nba_atual,
        )

        self.assertEqual(resultado["next_best_action"], nba_atual)
        criar_comparison_mock.assert_called_once()
        self.assertEqual(criar_comparison_mock.call_args.kwargs["origem"], "piloto")
        self.assertIn("resposta malformada", criar_comparison_mock.call_args.kwargs["erro"])

    def test_persiste_comparacao_com_origem_piloto(self):
        raciocinar_mock = AsyncMock(return_value={
            "current_state": "x", "recommended_framework": "SPIN_PROBLEM",
            "next_best_action": "y", "next_best_question": "Qual o problema principal?",
            "reason": "z", "confidence": 0.7, "hypotheses": [], "evidence": [],
            "missing_information": [], "avoid": [],
        })
        criar_comparison_mock = MagicMock(return_value=None)
        nba_atual = {"type": "question", "message": "..."}
        self._rodar({"PILOT_MODE": "100pct"}, raciocinar_mock, criar_comparison_mock, nba_atual)

        criar_comparison_mock.assert_called_once()
        kwargs = criar_comparison_mock.call_args.kwargs
        self.assertEqual(kwargs["origem"], "piloto")
        self.assertEqual(kwargs["meeting_id"], "m1")
        self.assertTrue(kwargs["concordancia"])

    def test_mutuamente_exclusivo_com_shadow_mode_nunca_chama_ia_duas_vezes(self):
        """Mesmo com SHADOW_MODE_ENABLED=true e PILOT_MODE=100pct juntos,
        raciocinar_async() só é chamado 1 vez por ciclo — piloto vence,
        shadow mode nunca é agendado nesse cenário."""
        raciocinar_mock = AsyncMock(return_value={
            "current_state": "x", "recommended_framework": "CLOSING",
            "next_best_action": "y", "next_best_question": None,
            "reason": "z", "confidence": 0.9, "hypotheses": [], "evidence": [],
            "missing_information": [], "avoid": [],
        })
        criar_comparison_mock = MagicMock(return_value=None)
        nba_atual = {"type": "insight", "message": "..."}
        rag_patches = _mock_rag()
        agente_patches = _mock_agentes(nba_atual)
        with patch.dict(os.environ, {"PILOT_MODE": "100pct", "SHADOW_MODE_ENABLED": "true"}):
            with patch("agent.sales_reasoning_engine.raciocinar_async", new=raciocinar_mock), \
                 patch("api.database.criar_shadow_mode_comparison", new=criar_comparison_mock), \
                 patch("api.database.obter_ultimo_ai_usage_event", return_value=None):
                for p in (*rag_patches, *agente_patches):
                    p.start()
                try:
                    asyncio.run(analisar_fragmento_multi("t", meeting_id="m1", usuario_id="seller-1"))
                finally:
                    for p in (*rag_patches, *agente_patches):
                        p.stop()

        # nenhuma task de shadow mode deve ter sido agendada — o ramo
        # piloto foi tomado, o ramo shadow (fire-and-forget) nem executou.
        self.assertEqual(len(orquestrador._SHADOW_MODE_TASKS), 0)
        raciocinar_mock.assert_awaited_once()
        criar_comparison_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
