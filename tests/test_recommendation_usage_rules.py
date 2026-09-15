"""
Testes de agent/recommendation_usage_rules.py — Fase 10 / Tarefa 10.2
do "PROMPT MESTRE — SALE-IA V2" (Detectar se o vendedor utilizou a
recomendação).

`detectar_uso_recomendacao()` mocka `get_embedding_provider()` (mesmo
padrão de tests/test_embeddings.py, que mocka a camada HTTP em vez de
depender de um Ollama real rodando) — nunca chama um provedor de
embedding de verdade.

Run:
    python -m unittest tests.test_recommendation_usage_rules -v
"""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agent.recommendation_usage_rules import (
    RECOMMENDATION_USAGE_STATES,
    classificar_uso_por_similaridade,
    cosine_similarity,
    detectar_uso_recomendacao,
)


class CosineSimilarityTest(unittest.TestCase):
    def test_vetores_identicos_similaridade_1(self):
        self.assertAlmostEqual(cosine_similarity([1, 0, 0], [1, 0, 0]), 1.0)

    def test_vetores_ortogonais_similaridade_0(self):
        self.assertAlmostEqual(cosine_similarity([1, 0], [0, 1]), 0.0)

    def test_vetores_opostos_similaridade_menos_1(self):
        self.assertAlmostEqual(cosine_similarity([1, 0], [-1, 0]), -1.0)

    def test_vetor_zero_retorna_0_sem_levantar(self):
        self.assertEqual(cosine_similarity([0, 0, 0], [1, 2, 3]), 0.0)


class ClassificarUsoPorSimilaridadeTest(unittest.TestCase):
    def test_sem_seller_action_e_unknown(self):
        self.assertEqual(classificar_uso_por_similaridade(0.99, None), "UNKNOWN")
        self.assertEqual(classificar_uso_por_similaridade(0.99, ""), "UNKNOWN")

    def test_similaridade_none_e_unknown_mesmo_com_seller_action(self):
        self.assertEqual(classificar_uso_por_similaridade(None, "algo foi dito"), "UNKNOWN")

    def test_similaridade_alta_e_used(self):
        self.assertEqual(classificar_uso_por_similaridade(0.80, "fala"), "USED")
        self.assertEqual(classificar_uso_por_similaridade(0.55, "fala"), "USED")  # limiar inclusivo

    def test_similaridade_media_e_partially_used(self):
        self.assertEqual(classificar_uso_por_similaridade(0.45, "fala"), "PARTIALLY_USED")
        self.assertEqual(classificar_uso_por_similaridade(0.35, "fala"), "PARTIALLY_USED")  # limiar inclusivo

    def test_similaridade_baixa_e_ignored(self):
        self.assertEqual(classificar_uso_por_similaridade(0.10, "fala totalmente nao relacionada"), "IGNORED")
        self.assertEqual(classificar_uso_por_similaridade(0.0, "fala"), "IGNORED")

    def test_limiares_customizados(self):
        self.assertEqual(
            classificar_uso_por_similaridade(0.60, "fala", limiar_used=0.9, limiar_partially_used=0.5),
            "PARTIALLY_USED",
        )


def _fake_embedding_result(vector):
    """Simula EmbeddingResult — só o campo `.vector` importa aqui."""
    return SimpleNamespace(vector=vector)


class DetectarUsoRecomendacaoTest(unittest.IsolatedAsyncioTestCase):
    async def test_sem_seller_action_e_unknown_sem_chamar_embedding(self):
        with patch("agent.recommendation_usage_rules.get_embedding_provider") as mock_provider:
            resultado = await detectar_uso_recomendacao("Pergunte sobre impacto financeiro.", None)
        self.assertEqual(resultado["state"], "UNKNOWN")
        self.assertIsNone(resultado["similarity"])
        mock_provider.assert_not_called()

    async def test_exemplo_literal_do_prompt_mestre_e_reconhecido_como_used(self):
        """'Pergunte sobre impacto financeiro.' -> 'Quanto vocês estimam
        que isso custa todo mês?' deve ser reconhecida como utilizada
        — mesmo sem nenhuma palavra em comum. O embedding real (Ollama)
        reconheceria essa proximidade semântica; aqui simulamos esse
        resultado com vetores próximos (mesmo espírito de mockar a
        camada HTTP em tests/test_embeddings.py)."""
        provider_mock = AsyncMock()
        provider_mock.embed_async.side_effect = [
            _fake_embedding_result([0.9, 0.1, 0.0]),  # recommendation
            _fake_embedding_result([0.85, 0.15, 0.05]),  # seller_action (semanticamente proximo)
        ]
        with patch("agent.recommendation_usage_rules.get_embedding_provider", return_value=provider_mock):
            resultado = await detectar_uso_recomendacao(
                "Pergunte sobre impacto financeiro.",
                "Quanto vocês estimam que isso custa todo mês?",
            )
        self.assertEqual(resultado["state"], "USED")
        self.assertGreaterEqual(resultado["similarity"], 0.55)

    async def test_fala_nao_relacionada_e_ignored(self):
        provider_mock = AsyncMock()
        provider_mock.embed_async.side_effect = [
            _fake_embedding_result([1.0, 0.0, 0.0]),
            _fake_embedding_result([0.0, 1.0, 0.0]),  # ortogonal -- nada a ver
        ]
        with patch("agent.recommendation_usage_rules.get_embedding_provider", return_value=provider_mock):
            resultado = await detectar_uso_recomendacao("Pergunte sobre impacto financeiro.", "Que dia é hoje?")
        self.assertEqual(resultado["state"], "IGNORED")

    async def test_falha_de_embedding_vira_unknown_nunca_ignored(self):
        provider_mock = AsyncMock()
        provider_mock.embed_async.return_value = None  # falha de rede/timeout
        with patch("agent.recommendation_usage_rules.get_embedding_provider", return_value=provider_mock):
            resultado = await detectar_uso_recomendacao("recomendação", "fala do vendedor")
        self.assertEqual(resultado["state"], "UNKNOWN")
        self.assertIsNotNone(resultado["reason"])


class EstadosTest(unittest.TestCase):
    def test_4_estados_literais_do_prompt_mestre(self):
        self.assertEqual(RECOMMENDATION_USAGE_STATES, {"USED", "PARTIALLY_USED", "IGNORED", "UNKNOWN"})


if __name__ == "__main__":
    unittest.main()
