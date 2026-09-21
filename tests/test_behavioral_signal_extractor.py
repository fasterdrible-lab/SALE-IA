"""
Testes de agent/behavioral_signal_extractor.py — Bloco 4 / Tarefa 4.2
de docs/tasks-sales-reasoning-engine-completo.md.

Mocka chamar_ia_com_fallback_claude — nunca chama IA real.

Run:
    python -m unittest tests.test_behavioral_signal_extractor -v
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from agent.behavioral_signal_extractor import extrair_sinais_comportamentais_async

_HISTORICO = "Vendedor: e aí, o que achou da proposta?"
_TRANSCRICAO = "Cliente: o concorrente X cobra bem menos que isso pelo mesmo pacote. Cliente: prefiro não arriscar mudar de fornecedor agora, mesmo sabendo que temos esse problema."


def _mock_ia(sinais):
    return AsyncMock(return_value={"sinais": sinais})


class ExtrairSinaisComportamentaisAsyncGoldenExamplesTest(unittest.TestCase):
    def test_price_anchor_extraido_corretamente(self):
        ia_mock = _mock_ia([{
            "signal": "PRICE_ANCHOR",
            "evidence_quote": "o concorrente X cobra bem menos que isso pelo mesmo pacote",
        }])
        with patch("agent.behavioral_signal_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            sinais = asyncio.run(extrair_sinais_comportamentais_async(_TRANSCRICAO, _HISTORICO))
        self.assertEqual(len(sinais), 1)
        self.assertEqual(sinais[0]["signal"], "PRICE_ANCHOR")
        self.assertIn("descricao", sinais[0])

    def test_status_quo_bias_extraido_corretamente(self):
        ia_mock = _mock_ia([{
            "signal": "STATUS_QUO_BIAS",
            "evidence_quote": "prefiro não arriscar mudar de fornecedor agora, mesmo sabendo que temos esse problema",
        }])
        with patch("agent.behavioral_signal_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            sinais = asyncio.run(extrair_sinais_comportamentais_async(_TRANSCRICAO, _HISTORICO))
        self.assertEqual(sinais[0]["signal"], "STATUS_QUO_BIAS")

    def test_multiplos_sinais_na_mesma_conversa(self):
        ia_mock = _mock_ia([
            {"signal": "PRICE_ANCHOR", "evidence_quote": "o concorrente X cobra bem menos que isso pelo mesmo pacote"},
            {"signal": "STATUS_QUO_BIAS", "evidence_quote": "prefiro não arriscar mudar de fornecedor agora, mesmo sabendo que temos esse problema"},
        ])
        with patch("agent.behavioral_signal_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            sinais = asyncio.run(extrair_sinais_comportamentais_async(_TRANSCRICAO, _HISTORICO))
        self.assertEqual(len(sinais), 2)
        tipos = {s["signal"] for s in sinais}
        self.assertEqual(tipos, {"PRICE_ANCHOR", "STATUS_QUO_BIAS"})

    def test_descricao_e_sempre_a_canonica_nunca_texto_livre_da_ia(self):
        from agent.behavioral_signal_rules import DESCRICOES_SINAIS
        ia_mock = _mock_ia([{
            "signal": "PRICE_ANCHOR",
            "evidence_quote": "o concorrente X cobra bem menos que isso pelo mesmo pacote",
        }])
        with patch("agent.behavioral_signal_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            sinais = asyncio.run(extrair_sinais_comportamentais_async(_TRANSCRICAO, _HISTORICO))
        self.assertEqual(sinais[0]["descricao"], DESCRICOES_SINAIS["PRICE_ANCHOR"])


class ExtrairSinaisComportamentaisAsyncGuardasTest(unittest.TestCase):
    def test_sem_sinal_claro_retorna_lista_vazia_nunca_none(self):
        ia_mock = _mock_ia([])
        with patch("agent.behavioral_signal_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            sinais = asyncio.run(extrair_sinais_comportamentais_async("Cliente: oi, tudo bem?", ""))
        self.assertEqual(sinais, [])

    def test_evidence_quote_que_nao_existe_na_conversa_e_descartada(self):
        ia_mock = _mock_ia([{
            "signal": "PRICE_ANCHOR",
            "evidence_quote": "frase que a IA inventou e não está na conversa real",
        }])
        with patch("agent.behavioral_signal_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            sinais = asyncio.run(extrair_sinais_comportamentais_async(_TRANSCRICAO, _HISTORICO))
        self.assertEqual(sinais, [])

    def test_signal_fora_do_vocabulario_fechado_e_descartado(self):
        ia_mock = _mock_ia([{
            "signal": "SINAL_INVENTADO",
            "evidence_quote": "o concorrente X cobra bem menos que isso pelo mesmo pacote",
        }])
        with patch("agent.behavioral_signal_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            sinais = asyncio.run(extrair_sinais_comportamentais_async(_TRANSCRICAO, _HISTORICO))
        self.assertEqual(sinais, [])

    def test_evidence_quote_vazia_e_descartada(self):
        ia_mock = _mock_ia([{"signal": "PRICE_ANCHOR", "evidence_quote": ""}])
        with patch("agent.behavioral_signal_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            sinais = asyncio.run(extrair_sinais_comportamentais_async(_TRANSCRICAO, _HISTORICO))
        self.assertEqual(sinais, [])

    def test_falha_real_de_ia_propaga(self):
        ia_mock = AsyncMock(side_effect=RuntimeError("4 provedores esgotados"))
        with patch("agent.behavioral_signal_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            with self.assertRaises(RuntimeError):
                asyncio.run(extrair_sinais_comportamentais_async(_TRANSCRICAO, _HISTORICO))

    def test_um_valido_e_outro_invalido_mantem_so_o_valido(self):
        ia_mock = _mock_ia([
            {"signal": "PRICE_ANCHOR", "evidence_quote": "o concorrente X cobra bem menos que isso pelo mesmo pacote"},
            {"signal": "PRICE_ANCHOR", "evidence_quote": "frase inventada que não existe na conversa"},
        ])
        with patch("agent.behavioral_signal_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            sinais = asyncio.run(extrair_sinais_comportamentais_async(_TRANSCRICAO, _HISTORICO))
        self.assertEqual(len(sinais), 1)


if __name__ == "__main__":
    unittest.main()
