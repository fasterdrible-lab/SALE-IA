"""
Testes de agent/objecao_detectada_para_objection_rules.py — Bloco 1 /
Tarefa 1.2 de docs/tasks-sales-reasoning-engine-completo.md.

montar_objection_spoken() é pura. extrair_objecao_do_ciclo() mocka
agent.objection_category_classifier.classificar_categoria_objecao_async
— nunca chama IA real.

Run:
    python -m unittest tests.test_objecao_detectada_para_objection_rules -v
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from agent.objecao_detectada_para_objection_rules import (
    extrair_objecao_do_ciclo,
    montar_objection_spoken,
)


class MontarObjectionSpokenTest(unittest.TestCase):
    def test_categoria_valida_monta_registro(self):
        r = montar_objection_spoken("Achei caro pra ser sincero.", "PRICE")
        self.assertEqual(r, {"category": "PRICE", "evidence_quote": "Achei caro pra ser sincero."})

    def test_texto_vazio_levanta(self):
        with self.assertRaises(ValueError):
            montar_objection_spoken("", "PRICE")

    def test_categoria_invalida_levanta(self):
        with self.assertRaises(ValueError):
            montar_objection_spoken("Achei caro.", "CATEGORIA_INVENTADA")


class ExtrairObjecaoDoCicloTest(unittest.TestCase):
    def test_sem_objecao_detectada_retorna_none_sem_chamar_classificador(self):
        classificador_mock = AsyncMock()
        with patch("agent.objection_category_classifier.classificar_categoria_objecao_async", new=classificador_mock):
            resultado = asyncio.run(extrair_objecao_do_ciclo({"objecao": None}))
        self.assertIsNone(resultado)
        classificador_mock.assert_not_awaited()

    def test_objecao_detectada_none_retorna_none(self):
        resultado = asyncio.run(extrair_objecao_do_ciclo(None))
        self.assertIsNone(resultado)

    def test_com_categoria_classificada_monta_registro_completo(self):
        classificador_mock = AsyncMock(return_value="PRICE")
        with patch("agent.objection_category_classifier.classificar_categoria_objecao_async", new=classificador_mock):
            resultado = asyncio.run(extrair_objecao_do_ciclo(
                {"objecao": "Achei caro pra ser sincero.", "resposta_pronta": "..."},
                usuario_id="seller-1", meeting_id="m1",
            ))
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado["objection_spoken"]["category"], "PRICE")
        self.assertEqual(resultado["objection_spoken"]["evidence_quote"], "Achei caro pra ser sincero.")
        self.assertIsNone(resultado["root_cause_hypothesis"])
        self.assertTrue(resultado["precisa_investigar"])  # sem root_cause_hypothesis, sempre True

    def test_classificador_sem_categoria_retorna_none(self):
        classificador_mock = AsyncMock(return_value=None)
        with patch("agent.objection_category_classifier.classificar_categoria_objecao_async", new=classificador_mock):
            resultado = asyncio.run(extrair_objecao_do_ciclo({"objecao": "Algo ambíguo."}))
        self.assertIsNone(resultado)

    def test_classificador_repassa_usuario_id_e_meeting_id(self):
        classificador_mock = AsyncMock(return_value="TIMING")
        with patch("agent.objection_category_classifier.classificar_categoria_objecao_async", new=classificador_mock):
            asyncio.run(extrair_objecao_do_ciclo(
                {"objecao": "Agora não é a hora."}, usuario_id="seller-9", meeting_id="m9",
            ))
        classificador_mock.assert_awaited_once_with("Agora não é a hora.", usuario_id="seller-9", meeting_id="m9")


if __name__ == "__main__":
    unittest.main()
