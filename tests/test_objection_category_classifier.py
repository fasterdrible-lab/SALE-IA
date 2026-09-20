"""
Testes de agent/objection_category_classifier.py — Bloco 1 / Tarefa
1.2 de docs/tasks-sales-reasoning-engine-completo.md.

Mocka chamar_ia_com_fallback_claude — nunca chama IA real.

Run:
    python -m unittest tests.test_objection_category_classifier -v
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from agent.objection_category_classifier import classificar_categoria_objecao_async


class ClassificarCategoriaObjecaoTest(unittest.TestCase):
    def test_texto_vazio_nunca_chama_ia(self):
        ia_mock = AsyncMock()
        with patch("agent.objection_category_classifier.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(classificar_categoria_objecao_async(""))
        self.assertIsNone(resultado)
        ia_mock.assert_not_awaited()

    def test_categoria_valida_e_retornada(self):
        ia_mock = AsyncMock(return_value={"category": "PRICE"})
        with patch("agent.objection_category_classifier.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(classificar_categoria_objecao_async("Achei caro."))
        self.assertEqual(resultado, "PRICE")
        ia_mock.assert_awaited_once()

    def test_categoria_null_da_ia_vira_none(self):
        ia_mock = AsyncMock(return_value={"category": None})
        with patch("agent.objection_category_classifier.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(classificar_categoria_objecao_async("Preciso pensar melhor."))
        self.assertIsNone(resultado)

    def test_categoria_fora_do_vocabulario_vira_none(self):
        ia_mock = AsyncMock(return_value={"category": "CATEGORIA_INVENTADA"})
        with patch("agent.objection_category_classifier.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(classificar_categoria_objecao_async("Algo qualquer."))
        self.assertIsNone(resultado)

    def test_resposta_da_ia_sem_chave_category_vira_none(self):
        ia_mock = AsyncMock(return_value={})
        with patch("agent.objection_category_classifier.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(classificar_categoria_objecao_async("Algo qualquer."))
        self.assertIsNone(resultado)

    def test_falha_real_de_ia_propaga(self):
        ia_mock = AsyncMock(side_effect=RuntimeError("4 provedores esgotados"))
        with patch("agent.objection_category_classifier.chamar_ia_com_fallback_claude", new=ia_mock):
            with self.assertRaises(RuntimeError):
                asyncio.run(classificar_categoria_objecao_async("Achei caro."))

    def test_usuario_id_e_meeting_id_repassados(self):
        ia_mock = AsyncMock(return_value={"category": "TIMING"})
        with patch("agent.objection_category_classifier.chamar_ia_com_fallback_claude", new=ia_mock):
            asyncio.run(classificar_categoria_objecao_async("Agora não é a hora.", usuario_id="seller-1", meeting_id="m1"))
        kwargs = ia_mock.await_args.kwargs
        self.assertEqual(kwargs["meeting_id"], "m1")
        self.assertEqual(ia_mock.await_args.args[2], "seller-1")


if __name__ == "__main__":
    unittest.main()
