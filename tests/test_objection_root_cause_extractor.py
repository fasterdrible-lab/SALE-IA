"""
Testes de agent/objection_root_cause_extractor.py — Bloco 4 / Tarefa
4.4 de docs/tasks-sales-reasoning-engine-completo.md.

Mocka chamar_ia_com_fallback_claude — nunca chama IA real.

Run:
    python -m unittest tests.test_objection_root_cause_extractor -v
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from agent.objection_root_cause_extractor import investigar_causa_raiz_async


def _objection_spoken(**overrides):
    base = {"category": "PRICE", "evidence_quote": "Achei caro pra ser sincero."}
    base.update(overrides)
    return base


class InvestigarCausaRaizAsyncTest(unittest.TestCase):
    def test_hipotese_real_com_evidencia_distinta_e_aceita(self):
        ia_mock = AsyncMock(return_value={
            "hypothesis": "SEM_ORCAMENTO_APROVADO",
            "evidence_quote": "Ainda não fechamos o orçamento desse trimestre.",
            "confidence": 0.8,
        })
        with patch("agent.objection_root_cause_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(investigar_causa_raiz_async(
                _objection_spoken(), "transcricao...", "historico...",
            ))
        self.assertEqual(resultado, {
            "hypothesis": "SEM_ORCAMENTO_APROVADO",
            "evidence_quote": "Ainda não fechamos o orçamento desse trimestre.",
            "confidence": 0.8,
        })

    def test_padrao_proibido_hipotese_igual_categoria_mesma_evidencia_e_descartado(self):
        """O exemplo literal do prompt mestre: "Está caro." não pode virar
        automaticamente root_cause=PRICE com a mesma evidência."""
        ia_mock = AsyncMock(return_value={
            "hypothesis": "PRICE",
            "evidence_quote": "Achei caro pra ser sincero.",
            "confidence": 1.0,
        })
        with patch("agent.objection_root_cause_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(investigar_causa_raiz_async(
                _objection_spoken(), "transcricao...", "historico...",
            ))
        self.assertIsNone(resultado)

    def test_padrao_proibido_case_insensitive(self):
        ia_mock = AsyncMock(return_value={
            "hypothesis": "price",
            "evidence_quote": "Outra frase qualquer.",
            "confidence": 0.9,
        })
        with patch("agent.objection_root_cause_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(investigar_causa_raiz_async(
                _objection_spoken(), "transcricao...", "historico...",
            ))
        self.assertIsNone(resultado)

    def test_hipotese_nula_da_ia_vira_none(self):
        ia_mock = AsyncMock(return_value={"hypothesis": None, "evidence_quote": None, "confidence": None})
        with patch("agent.objection_root_cause_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(investigar_causa_raiz_async(
                _objection_spoken(), "transcricao...", "historico...",
            ))
        self.assertIsNone(resultado)

    def test_evidencia_igual_a_objecao_mesmo_com_hipotese_diferente_e_descartado(self):
        ia_mock = AsyncMock(return_value={
            "hypothesis": "ADOPTION_RISK",
            "evidence_quote": "Achei caro pra ser sincero.",
            "confidence": 0.9,
        })
        with patch("agent.objection_root_cause_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(investigar_causa_raiz_async(
                _objection_spoken(), "transcricao...", "historico...",
            ))
        self.assertIsNone(resultado)

    def test_confidence_fora_do_intervalo_vira_none(self):
        ia_mock = AsyncMock(return_value={
            "hypothesis": "SEM_ORCAMENTO_APROVADO", "evidence_quote": "Outra frase real.", "confidence": 1.5,
        })
        with patch("agent.objection_root_cause_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(investigar_causa_raiz_async(
                _objection_spoken(), "transcricao...", "historico...",
            ))
        self.assertIsNone(resultado)

    def test_confidence_invalida_vira_none(self):
        ia_mock = AsyncMock(return_value={
            "hypothesis": "SEM_ORCAMENTO_APROVADO", "evidence_quote": "Outra frase real.", "confidence": "alta",
        })
        with patch("agent.objection_root_cause_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(investigar_causa_raiz_async(
                _objection_spoken(), "transcricao...", "historico...",
            ))
        self.assertIsNone(resultado)

    def test_objection_spoken_sem_categoria_nunca_chama_ia(self):
        ia_mock = AsyncMock()
        with patch("agent.objection_root_cause_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(investigar_causa_raiz_async(
                {"category": None, "evidence_quote": "x"}, "transcricao...", "historico...",
            ))
        self.assertIsNone(resultado)
        ia_mock.assert_not_awaited()

    def test_falha_real_de_ia_propaga(self):
        ia_mock = AsyncMock(side_effect=RuntimeError("4 provedores esgotados"))
        with patch("agent.objection_root_cause_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            with self.assertRaises(RuntimeError):
                asyncio.run(investigar_causa_raiz_async(
                    _objection_spoken(), "transcricao...", "historico...",
                ))


if __name__ == "__main__":
    unittest.main()
