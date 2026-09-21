"""
Testes de agent/buyer_motivation_extractor.py — Bloco 4 / Tarefa 4.3
de docs/tasks-sales-reasoning-engine-completo.md.

Mocka chamar_ia_com_fallback_claude — nunca chama IA real.

Run:
    python -m unittest tests.test_buyer_motivation_extractor -v
"""

import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agent.buyer_motivation_extractor import extrair_buyer_motivation_async

_HISTORICO = "Vendedor: me conta, o que motivou vocês a olhar isso agora?"
_TRANSCRICAO = "Cliente: estamos gastando muito com isso hoje, queremos cortar esse custo. Cliente: também não podemos correr o risco de isso falhar de novo."


def _mock_ia(hipoteses):
    return AsyncMock(return_value={"hipoteses": hipoteses})


class ExtrairBuyerMotivationAsyncGoldenExamplesTest(unittest.TestCase):
    def test_cost_reduction_extraido_corretamente(self):
        ia_mock = _mock_ia([{
            "motivation": "COST_REDUCTION", "confidence": 0.8,
            "evidence": ["estamos gastando muito com isso hoje, queremos cortar esse custo"],
        }])
        with patch("agent.buyer_motivation_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(extrair_buyer_motivation_async(_TRANSCRICAO, _HISTORICO))
        self.assertEqual(resultado["motivation"], "COST_REDUCTION")
        self.assertEqual(resultado["confidence"], 0.8)

    def test_dominante_e_a_de_maior_confidence(self):
        ia_mock = _mock_ia([
            {"motivation": "COST_REDUCTION", "confidence": 0.5,
             "evidence": ["estamos gastando muito com isso hoje, queremos cortar esse custo"]},
            {"motivation": "RISK_REDUCTION", "confidence": 0.9,
             "evidence": ["também não podemos correr o risco de isso falhar de novo"]},
        ])
        with patch("agent.buyer_motivation_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(extrair_buyer_motivation_async(_TRANSCRICAO, _HISTORICO))
        self.assertEqual(resultado["motivation"], "RISK_REDUCTION")


class ExtrairBuyerMotivationAsyncGuardasTest(unittest.TestCase):
    def test_sem_sinal_claro_retorna_none(self):
        ia_mock = _mock_ia([])
        with patch("agent.buyer_motivation_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(extrair_buyer_motivation_async("Cliente: oi, tudo bem?", ""))
        self.assertIsNone(resultado)

    def test_motivation_fora_do_vocabulario_e_descartada(self):
        ia_mock = _mock_ia([{
            "motivation": "MOTIVACAO_INVENTADA", "confidence": 0.9,
            "evidence": ["estamos gastando muito com isso hoje, queremos cortar esse custo"],
        }])
        with patch("agent.buyer_motivation_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(extrair_buyer_motivation_async(_TRANSCRICAO, _HISTORICO))
        self.assertIsNone(resultado)

    def test_citacao_que_nao_existe_na_conversa_e_removida_da_evidence(self):
        ia_mock = _mock_ia([{
            "motivation": "COST_REDUCTION", "confidence": 0.8,
            "evidence": ["frase inventada que não está na conversa"],
        }])
        with patch("agent.buyer_motivation_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(extrair_buyer_motivation_async(_TRANSCRICAO, _HISTORICO))
        self.assertIsNone(resultado)  # sem nenhuma citação real, hipótese inteira descartada

    def test_evidence_mista_mantem_so_as_citacoes_reais(self):
        ia_mock = _mock_ia([{
            "motivation": "COST_REDUCTION", "confidence": 0.8,
            "evidence": [
                "estamos gastando muito com isso hoje, queremos cortar esse custo",
                "frase inventada que não está na conversa",
            ],
        }])
        with patch("agent.buyer_motivation_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(extrair_buyer_motivation_async(_TRANSCRICAO, _HISTORICO))
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado["evidence"], ["estamos gastando muito com isso hoje, queremos cortar esse custo"])

    def test_confidence_fora_do_intervalo_e_descartada(self):
        ia_mock = _mock_ia([{
            "motivation": "COST_REDUCTION", "confidence": 1.5,
            "evidence": ["estamos gastando muito com isso hoje, queremos cortar esse custo"],
        }])
        with patch("agent.buyer_motivation_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(extrair_buyer_motivation_async(_TRANSCRICAO, _HISTORICO))
        self.assertIsNone(resultado)

    def test_evidence_nao_e_lista_e_descartada(self):
        ia_mock = _mock_ia([{
            "motivation": "COST_REDUCTION", "confidence": 0.8,
            "evidence": "estamos gastando muito com isso hoje, queremos cortar esse custo",
        }])
        with patch("agent.buyer_motivation_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            resultado = asyncio.run(extrair_buyer_motivation_async(_TRANSCRICAO, _HISTORICO))
        self.assertIsNone(resultado)

    def test_falha_real_de_ia_propaga(self):
        ia_mock = AsyncMock(side_effect=RuntimeError("4 provedores esgotados"))
        with patch("agent.buyer_motivation_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            with self.assertRaises(RuntimeError):
                asyncio.run(extrair_buyer_motivation_async(_TRANSCRICAO, _HISTORICO))


class GuardaArquiteturalTest(unittest.TestCase):
    """"DISC nunca deverá ser tratado como motivação" — garantida por
    construção: este módulo nunca importa nem lê nenhum campo
    relacionado a DISC. Mesma checagem (termos proibidos, não a
    palavra "DISC" isolada — a docstring do próprio módulo cita a
    regra por nome, igual `agent/buyer_motivation_rules.py`) de
    `tests/test_buyer_motivation_rules.py::GuardaArquiteturalTest`."""

    _TERMOS_PROIBIDOS = ["disc_agent", "perfil_disc", '"disc"', "'disc'", "import disc"]

    def test_modulo_nao_referencia_disc(self):
        codigo = Path("agent/buyer_motivation_extractor.py").read_text(encoding="utf-8").lower()
        for termo in self._TERMOS_PROIBIDOS:
            self.assertNotIn(termo, codigo, f"buyer_motivation_extractor.py não deveria referenciar '{termo}'")

    def test_prompt_nao_referencia_disc(self):
        prompt = Path("agent/prompt_templates/buyer_motivation_extractor.txt").read_text(encoding="utf-8").lower()
        for termo in self._TERMOS_PROIBIDOS:
            self.assertNotIn(termo, prompt, f"buyer_motivation_extractor.txt não deveria referenciar '{termo}'")


if __name__ == "__main__":
    unittest.main()
