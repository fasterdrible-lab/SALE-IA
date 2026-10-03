"""
Testes — Fase 10 (Tarefas 10.1 + 10.2, "PROMPT MESTRE — SALE-IA V2")
ligadas em produção via agent/multiagente/orquestrador.py.

Cobre: kill-switch RECOMMENDATION_TRACKING_ENABLED (default `true`);
_rastrear_recomendacao() gravando um RecommendationEvent novo só quando
a recomendação muda de ciclo pra ciclo; classificação de uso da
recomendação PENDENTE anterior via detectar_uso_recomendacao()
(embeddings, Fase 10.2) contra a fala nova do vendedor; reunião
anônima/"default" nunca grava nada; e best-effort absoluto (falha em
qualquer chamada nunca derruba o ciclo real).

Run:
    python -m unittest tests.test_orquestrador_recommendation_tracking -v
"""

import asyncio
import logging
import os
import unittest
from unittest.mock import AsyncMock, patch

logging.disable(logging.CRITICAL)

import agent.multiagente.orquestrador as orquestrador
from agent.multiagente.orquestrador import (
    _rastrear_recomendacao,
    analisar_fragmento_multi,
    recommendation_tracking_ativo,
)


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


class KillSwitchTest(unittest.TestCase):
    def test_ligado_por_padrao(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RECOMMENDATION_TRACKING_ENABLED", None)
            self.assertTrue(recommendation_tracking_ativo())

    def test_desligado_com_false(self):
        with patch.dict(os.environ, {"RECOMMENDATION_TRACKING_ENABLED": "false"}):
            self.assertFalse(recommendation_tracking_ativo())

    def test_desligado_com_qualquer_valor_nao_false(self):
        with patch.dict(os.environ, {"RECOMMENDATION_TRACKING_ENABLED": "true"}):
            self.assertTrue(recommendation_tracking_ativo())


_VERSOES = {"reasoning_engine_version": "multiagente@abc", "policy_version": "policy@def",
            "knowledge_version": "knowledge@123", "model_version": "deepseek/deepseek-chat"}


class RastrearRecomendacaoTest(unittest.TestCase):
    def _run(self, resultado, transcricao_parcial="", meeting_id="m1"):
        # Tarefa D6: versões fixas — o cálculo real consulta o banco.
        with patch("agent.intelligence_version_rules.versoes_da_inteligencia", return_value=dict(_VERSOES)):
            return asyncio.run(_rastrear_recomendacao(resultado, transcricao_parcial, meeting_id))

    def test_meeting_id_default_nunca_grava_nada(self):
        with patch("api.database.listar_recommendation_events") as mock_listar, \
             patch("api.database.criar_recommendation_event") as mock_criar:
            self._run({"next_best_action": {"message": "x", "category": "y", "reason": "z"}}, meeting_id="default")
        mock_listar.assert_not_called()
        mock_criar.assert_not_called()

    def test_meeting_id_ausente_nunca_grava_nada(self):
        with patch("api.database.criar_recommendation_event") as mock_criar:
            self._run({"next_best_action": {"message": "x"}}, meeting_id=None)
        mock_criar.assert_not_called()

    def test_desligado_pelo_kill_switch_nunca_grava(self):
        with patch.dict(os.environ, {"RECOMMENDATION_TRACKING_ENABLED": "false"}), \
             patch("api.database.criar_recommendation_event") as mock_criar:
            self._run({"next_best_action": {"message": "x"}})
        mock_criar.assert_not_called()

    def test_cria_evento_quando_nao_existe_nenhum_anterior(self):
        with patch("api.database.listar_recommendation_events", return_value=[]), \
             patch("api.database.criar_recommendation_event") as mock_criar:
            self._run({
                "next_best_action": {
                    "message": "Pergunte sobre o impacto financeiro.",
                    "category": "descoberta_dor",
                    "reason": "implicacao ainda nao mapeada",
                },
            })
        mock_criar.assert_called_once_with(
            meeting_id="m1",
            strategy="descoberta_dor",
            recommendation="Pergunte sobre o impacto financeiro.",
            reason="implicacao ainda nao mapeada",
            versoes=_VERSOES,
        )

    def test_nao_duplica_evento_quando_recomendacao_nao_mudou(self):
        anterior = [{
            "id": 1, "recommendation": "Pergunte sobre o impacto financeiro.",
            "used_at": None,
        }]
        with patch("api.database.listar_recommendation_events", return_value=anterior), \
             patch("api.database.criar_recommendation_event") as mock_criar, \
             patch("api.database.registrar_uso_recommendation_event"), \
             patch("agent.recommendation_usage_rules.detectar_uso_recomendacao", new=AsyncMock(return_value={"state": "UNKNOWN", "similarity": None})):
            self._run({
                "next_best_action": {"message": "Pergunte sobre o impacto financeiro.", "category": "x", "reason": "y"},
            })
        mock_criar.assert_not_called()

    def test_cria_evento_novo_quando_recomendacao_mudou(self):
        anterior = [{
            "id": 1, "recommendation": "Pergunte sobre o impacto financeiro.",
            "used_at": "2026-09-22T10:00:00",
        }]
        with patch("api.database.listar_recommendation_events", return_value=anterior), \
             patch("api.database.criar_recommendation_event") as mock_criar:
            self._run({
                "next_best_action": {"message": "Investigue quem é o decisor.", "category": "qualificacao", "reason": "sem decisor mapeado"},
            })
        mock_criar.assert_called_once_with(
            meeting_id="m1",
            strategy="qualificacao",
            recommendation="Investigue quem é o decisor.",
            reason="sem decisor mapeado",
            versoes=_VERSOES,
        )

    def test_classifica_uso_da_pendente_com_fala_nova(self):
        anterior = [{"id": 42, "recommendation": "Pergunte sobre o impacto financeiro.", "used_at": None}]
        detectar_mock = AsyncMock(return_value={"state": "USED", "similarity": 0.71})
        with patch("api.database.listar_recommendation_events", return_value=anterior), \
             patch("api.database.criar_recommendation_event"), \
             patch("api.database.registrar_uso_recommendation_event") as mock_registrar, \
             patch("agent.recommendation_usage_rules.detectar_uso_recomendacao", new=detectar_mock):
            self._run(
                {"next_best_action": {"message": "Pergunte sobre o impacto financeiro.", "category": "x", "reason": "y"}},
                transcricao_parcial="Acho que isso custa uns R$20 mil por mes pra gente.",
            )
        detectar_mock.assert_awaited_once_with(
            "Pergunte sobre o impacto financeiro.", "Acho que isso custa uns R$20 mil por mes pra gente.",
        )
        mock_registrar.assert_called_once_with(42, seller_action="Acho que isso custa uns R$20 mil por mes pra gente.")

    def test_nao_classifica_quando_nao_ha_pendente(self):
        anterior = [{"id": 1, "recommendation": "x", "used_at": "2026-09-22T10:00:00"}]
        with patch("api.database.listar_recommendation_events", return_value=anterior), \
             patch("api.database.criar_recommendation_event"), \
             patch("agent.recommendation_usage_rules.detectar_uso_recomendacao", new=AsyncMock()) as detectar_mock:
            self._run({"next_best_action": {"message": "x", "category": "c", "reason": "r"}}, transcricao_parcial="fala nova")
        detectar_mock.assert_not_awaited()

    def test_nao_classifica_sem_fala_nova(self):
        anterior = [{"id": 1, "recommendation": "outra coisa", "used_at": None}]
        with patch("api.database.listar_recommendation_events", return_value=anterior), \
             patch("api.database.criar_recommendation_event"), \
             patch("agent.recommendation_usage_rules.detectar_uso_recomendacao", new=AsyncMock()) as detectar_mock:
            self._run({"next_best_action": {"message": "x", "category": "c", "reason": "r"}}, transcricao_parcial="   ")
        detectar_mock.assert_not_awaited()

    def test_falha_ao_listar_eventos_nunca_levanta(self):
        with patch("api.database.listar_recommendation_events", side_effect=Exception("db indisponivel")):
            try:
                self._run({"next_best_action": {"message": "x", "category": "c", "reason": "r"}})
            except Exception as e:  # pragma: no cover - só falha o teste se levantar
                self.fail(f"_rastrear_recomendacao nao deveria propagar excecao: {e}")

    def test_falha_ao_classificar_uso_nao_impede_criar_evento_novo(self):
        anterior = [{"id": 1, "recommendation": "recomendacao antiga", "used_at": None}]
        with patch("api.database.listar_recommendation_events", return_value=anterior), \
             patch("api.database.criar_recommendation_event") as mock_criar, \
             patch("agent.recommendation_usage_rules.detectar_uso_recomendacao", new=AsyncMock(side_effect=Exception("embedding falhou"))):
            self._run(
                {"next_best_action": {"message": "recomendacao nova", "category": "c", "reason": "r"}},
                transcricao_parcial="fala nova",
            )
        mock_criar.assert_called_once()

    def test_sem_next_best_action_nao_grava(self):
        with patch("api.database.listar_recommendation_events", return_value=[]), \
             patch("api.database.criar_recommendation_event") as mock_criar:
            self._run({})
        mock_criar.assert_not_called()


class IntegracaoComOCicloRealTest(unittest.TestCase):
    """Confirma que analisar_fragmento_multi() de fato chama
    _rastrear_recomendacao() no ciclo real, sem quebrar o resultado
    retornado ao vendedor mesmo se o tracking falhar."""

    def setUp(self):
        # Tarefa D6: versões fixas — o cálculo real consulta o banco.
        p = patch("agent.intelligence_version_rules.versoes_da_inteligencia", return_value=dict(_VERSOES))
        p.start()
        self.addCleanup(p.stop)

    def test_wired_no_ciclo_e_nao_quebra_resultado_em_falha(self):
        rag_patches = _mock_rag()
        agente_patches = _mock_agentes({"message": "Pergunte sobre o impacto.", "category": "x", "reason": "y"})
        with patch("api.database.listar_recommendation_events", side_effect=Exception("db indisponivel")):
            for p in (*rag_patches, *agente_patches):
                p.start()
            try:
                resultado = asyncio.run(analisar_fragmento_multi("transcricao", meeting_id="m1"))
            finally:
                for p in (*rag_patches, *agente_patches):
                    p.stop()
        self.assertEqual(resultado["status"], "updated")
        self.assertIn("next_best_action", resultado)

    def test_cria_evento_de_verdade_no_ciclo_real(self):
        rag_patches = _mock_rag()
        agente_patches = _mock_agentes({"message": "Pergunte sobre o impacto.", "category": "x", "reason": "y"})
        with patch("api.database.listar_recommendation_events", return_value=[]), \
             patch("api.database.criar_recommendation_event") as mock_criar:
            for p in (*rag_patches, *agente_patches):
                p.start()
            try:
                asyncio.run(analisar_fragmento_multi("transcricao", meeting_id="m1"))
            finally:
                for p in (*rag_patches, *agente_patches):
                    p.stop()
        mock_criar.assert_called_once()

    def test_classificacao_usa_transcricao_nova_nao_a_acumulada(self):
        # Achado real (Fase 25, 23/09/2026): usar transcricao_parcial
        # (acumulada, até 6.000 chars) como seller_action diluía a
        # similaridade sistematicamente. A classificação precisa
        # receber transcricao_nova (o delta real), nunca o transcript
        # inteiro passado como `transcricao_parcial` pro resto do
        # ciclo (RAG/agentes).
        rag_patches = _mock_rag()
        agente_patches = _mock_agentes({"message": "Pergunte sobre o impacto.", "category": "x", "reason": "y"})
        pendente = {"id": 1, "recommendation": "Pergunta anterior", "used_at": None}
        with patch("api.database.listar_recommendation_events", return_value=[pendente]), \
             patch("api.database.registrar_uso_recommendation_event") as mock_registrar, \
             patch(
                 "agent.recommendation_usage_rules.detectar_uso_recomendacao",
                 new=AsyncMock(return_value={"state": "USED", "similarity": 0.9}),
             ) as mock_detectar:
            for p in (*rag_patches, *agente_patches):
                p.start()
            try:
                asyncio.run(analisar_fragmento_multi(
                    "transcricao acumulada gigante, muitos topicos nao relacionados",
                    meeting_id="m1",
                    transcricao_nova="fala nova curta do vendedor",
                ))
            finally:
                for p in (*rag_patches, *agente_patches):
                    p.stop()

        mock_detectar.assert_awaited_once_with("Pergunta anterior", "fala nova curta do vendedor")
        mock_registrar.assert_called_once_with(1, seller_action="fala nova curta do vendedor")


if __name__ == "__main__":
    unittest.main()
