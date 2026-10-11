"""
Testes — agent/sessao_manager.py::acumular_transcricao.

Regressão de 11/10/2026: o teto de 60.000 caracteres cortava o início de
58 das 63 reuniões medidas (Sessões, exportação para o RAG e análise da
Conta Claude liam a versão cortada).

Run:
    python -m unittest tests.test_sessao_acumular_transcricao -v
"""

import unittest

from agent.sessao_manager import LIMITE_TRANSCRICAO_SESSAO, acumular_transcricao


class TestAcumularTranscricao(unittest.TestCase):
    def test_reuniao_longa_mantem_o_inicio(self):
        inicio = "João: Bom dia, vamos começar a reunião."
        texto = inicio
        for i in range(3000):  # ~180 mil caracteres, ~3h de reunião
            texto = acumular_transcricao(texto, f"Cliente: fala número {i} da reunião de hoje.")
        self.assertGreater(len(texto), 60000)
        self.assertTrue(texto.startswith(inicio))
        self.assertTrue(texto.endswith("fala número 2999 da reunião de hoje."))

    def test_sessao_vazia(self):
        self.assertEqual(acumular_transcricao(None, "João: oi"), "\n\nJoão: oi")
        self.assertEqual(acumular_transcricao("", "x"), "\n\nx")

    def test_teto_de_seguranca_descarta_o_inicio(self):
        atual = "a" * LIMITE_TRANSCRICAO_SESSAO
        nova = acumular_transcricao(atual, "fim")
        self.assertEqual(len(nova), LIMITE_TRANSCRICAO_SESSAO)
        self.assertTrue(nova.endswith("\n\nfim"))

    def test_teto_cabe_no_mediumtext(self):
        # MEDIUMTEXT = 16.777.215 bytes; utf8mb4 usa até 4 bytes por caractere
        self.assertLessEqual(LIMITE_TRANSCRICAO_SESSAO * 4, 16_777_215)


if __name__ == "__main__":
    unittest.main()
