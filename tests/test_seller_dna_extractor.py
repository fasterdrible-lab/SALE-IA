"""
Testes de agent/seller_dna_extractor.py — Bloco 5 / Tarefa 5.1 de
docs/tasks-sales-reasoning-engine-completo.md.

Mocka chamar_ia_com_fallback_claude e api.database — nunca chama IA
real nem toca banco real.

Run:
    python -m unittest tests.test_seller_dna_extractor -v
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.seller_dna_extractor import (
    extrair_e_salvar_seller_dna_observacoes,
    extrair_observacoes_seller_dna_async,
)

_TRANSCRICAO = (
    "Vendedor: antes de mais nada, me conta como está sendo o dia a dia de vocês aí. "
    "Cliente: tem sido corrido. Vendedor: deixa eu te mostrar uma coisa rápida."
)


def _mock_ia(observacoes):
    return AsyncMock(return_value={"observacoes": observacoes})


class ExtrairObservacoesSellerDnaAsyncGoldenExamplesTest(unittest.TestCase):
    def test_observacao_valida_extraida_corretamente(self):
        ia_mock = _mock_ia([{
            "campo": "opening_patterns",
            "valor": "Abre perguntando sobre a rotina do time antes da pauta.",
            "evidence_quote": "antes de mais nada, me conta como está sendo o dia a dia de vocês aí",
        }])
        with patch("agent.seller_dna_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(extrair_observacoes_seller_dna_async(_TRANSCRICAO, "vendedor-1"))
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["campo"], "opening_patterns")

    def test_multiplas_observacoes_na_mesma_reuniao(self):
        ia_mock = _mock_ia([
            {
                "campo": "opening_patterns",
                "valor": "Abre perguntando sobre a rotina.",
                "evidence_quote": "antes de mais nada, me conta como está sendo o dia a dia de vocês aí",
            },
            {
                "campo": "storytelling_patterns",
                "valor": "Usa exemplo rápido antes de detalhar.",
                "evidence_quote": "deixa eu te mostrar uma coisa rápida",
            },
        ])
        with patch("agent.seller_dna_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(extrair_observacoes_seller_dna_async(_TRANSCRICAO, "vendedor-1"))
        self.assertEqual(len(resultado), 2)


class ExtrairObservacoesSellerDnaAsyncGuardasTest(unittest.TestCase):
    def test_sem_sinal_claro_retorna_lista_vazia(self):
        ia_mock = _mock_ia([])
        with patch("agent.seller_dna_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(extrair_observacoes_seller_dna_async("Vendedor: oi.", "vendedor-1"))
        self.assertEqual(resultado, [])

    def test_campo_fora_do_vocabulario_e_descartado(self):
        ia_mock = _mock_ia([{
            "campo": "personalidade_geral", "valor": "extrovertido",
            "evidence_quote": "antes de mais nada, me conta como está sendo o dia a dia de vocês aí",
        }])
        with patch("agent.seller_dna_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(extrair_observacoes_seller_dna_async(_TRANSCRICAO, "vendedor-1"))
        self.assertEqual(resultado, [])

    def test_evidence_quote_que_nao_existe_na_transcricao_e_descartada(self):
        ia_mock = _mock_ia([{
            "campo": "opening_patterns", "valor": "x",
            "evidence_quote": "frase inventada que não está na transcrição",
        }])
        with patch("agent.seller_dna_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(extrair_observacoes_seller_dna_async(_TRANSCRICAO, "vendedor-1"))
        self.assertEqual(resultado, [])

    def test_alegacao_de_eficacia_e_descartada(self):
        """Fase 15.2, reaproveitada aqui — SellerDNA registra
        comportamento, nunca eficácia."""
        ia_mock = _mock_ia([{
            "campo": "opening_patterns", "valor": "Essa abertura funciona muito bem",
            "evidence_quote": "antes de mais nada, me conta como está sendo o dia a dia de vocês aí",
        }])
        with patch("agent.seller_dna_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(extrair_observacoes_seller_dna_async(_TRANSCRICAO, "vendedor-1"))
        self.assertEqual(resultado, [])

    def test_uma_observacao_invalida_nao_derruba_as_outras(self):
        ia_mock = _mock_ia([
            {"campo": "campo_invalido", "valor": "x", "evidence_quote": "y"},
            {
                "campo": "opening_patterns",
                "valor": "Abre perguntando sobre a rotina.",
                "evidence_quote": "antes de mais nada, me conta como está sendo o dia a dia de vocês aí",
            },
        ])
        with patch("agent.seller_dna_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(extrair_observacoes_seller_dna_async(_TRANSCRICAO, "vendedor-1"))
        self.assertEqual(len(resultado), 1)

    def test_falha_real_de_ia_propaga(self):
        ia_mock = AsyncMock(side_effect=RuntimeError("4 provedores esgotados"))
        with patch("agent.seller_dna_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            with self.assertRaises(RuntimeError):
                asyncio.run(extrair_observacoes_seller_dna_async(_TRANSCRICAO, "vendedor-1"))


class ExtrairESalvarSellerDnaObservacoesTest(unittest.TestCase):
    """Pipeline completo pós-reunião — resolve seller_id via
    MeetingMemory, extrai e persiste. Melhor esforço absoluto: nunca
    propaga exceção."""

    def test_sem_meeting_id_retorna_lista_vazia(self):
        resultado = asyncio.run(extrair_e_salvar_seller_dna_observacoes({}, _TRANSCRICAO, None))
        self.assertEqual(resultado, [])

    def test_sem_meeting_memory_resolvivel_nao_salva_nada(self):
        with patch("api.database.obter_meeting_memory", return_value=None):
            resultado = asyncio.run(
                extrair_e_salvar_seller_dna_observacoes({}, _TRANSCRICAO, "m1")
            )
        self.assertEqual(resultado, [])

    def test_meeting_memory_sem_usuario_id_nao_salva_nada(self):
        with patch("api.database.obter_meeting_memory", return_value={"usuario_id": None}):
            resultado = asyncio.run(
                extrair_e_salvar_seller_dna_observacoes({}, _TRANSCRICAO, "m1")
            )
        self.assertEqual(resultado, [])

    def test_com_seller_resolvido_extrai_e_persiste(self):
        ia_mock = _mock_ia([{
            "campo": "opening_patterns",
            "valor": "Abre perguntando sobre a rotina.",
            "evidence_quote": "antes de mais nada, me conta como está sendo o dia a dia de vocês aí",
        }])
        criar_mock = MagicMock(side_effect=lambda **kw: {**kw, "id": 1})
        with patch("api.database.obter_meeting_memory", return_value={"usuario_id": "vendedor-1"}), \
             patch("api.database.criar_seller_dna_observacao", new=criar_mock), \
             patch("agent.seller_dna_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(
                extrair_e_salvar_seller_dna_observacoes({}, _TRANSCRICAO, "m1")
            )
        self.assertEqual(len(resultado), 1)
        criar_mock.assert_called_once()
        self.assertEqual(criar_mock.call_args.kwargs["seller_id"], "vendedor-1")
        self.assertEqual(criar_mock.call_args.kwargs["meeting_id"], "m1")

    def test_falha_de_ia_nunca_propaga_melhor_esforco(self):
        ia_mock = AsyncMock(side_effect=RuntimeError("4 provedores esgotados"))
        with patch("api.database.obter_meeting_memory", return_value={"usuario_id": "vendedor-1"}), \
             patch("agent.seller_dna_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(
                extrair_e_salvar_seller_dna_observacoes({}, _TRANSCRICAO, "m1")
            )
        self.assertEqual(resultado, [])

    def test_falha_ao_persistir_uma_observacao_nao_derruba_as_outras(self):
        ia_mock = _mock_ia([
            {
                "campo": "opening_patterns", "valor": "x",
                "evidence_quote": "antes de mais nada, me conta como está sendo o dia a dia de vocês aí",
            },
            {
                "campo": "storytelling_patterns", "valor": "y",
                "evidence_quote": "deixa eu te mostrar uma coisa rápida",
            },
        ])
        criar_mock = MagicMock(side_effect=[ValueError("campo inválido"), {"id": 2}])
        with patch("api.database.obter_meeting_memory", return_value={"usuario_id": "vendedor-1"}), \
             patch("api.database.criar_seller_dna_observacao", new=criar_mock), \
             patch("agent.seller_dna_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(
                extrair_e_salvar_seller_dna_observacoes({}, _TRANSCRICAO, "m1")
            )
        self.assertEqual(len(resultado), 1)


if __name__ == "__main__":
    unittest.main()
