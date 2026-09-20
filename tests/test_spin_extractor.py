"""
Testes de agent/spin_extractor.py — Bloco 4 / Tarefa 4.1 de docs/
tasks-sales-reasoning-engine-completo.md.

Mocka chamar_ia_com_fallback_claude — nunca chama IA real.

Run:
    python -m unittest tests.test_spin_extractor -v
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from agent.spin_extractor import extrair_spin_state_async

_HISTORICO = "Vendedor: bom dia! Me conta um pouco da operação de vocês."
_TRANSCRICAO = 'Cliente: hoje somos 8 pessoas no time comercial, usamos planilha mesmo, nada de CRM. Cliente: nosso maior problema é que os leads esfriam antes de a gente ligar.'


def _mock_ia(fatos):
    return AsyncMock(return_value={"fatos": fatos})


class ExtrairSpinStateAsyncGoldenExamplesTest(unittest.TestCase):
    """1 exemplo golden por estágio SPIN — trecho conhecido -> fato esperado."""

    def test_situation_team_size_extraido_corretamente(self):
        ia_mock = _mock_ia([{
            "stage": "situation", "campo": "team_size", "valor": "8 pessoas",
            "evidence_quote": "hoje somos 8 pessoas no time comercial",
        }])
        with patch("agent.spin_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            cobertura = asyncio.run(extrair_spin_state_async(_TRANSCRICAO, _HISTORICO))
        self.assertEqual(len(cobertura["situation"]["known"]), 1)
        self.assertEqual(cobertura["situation"]["known"][0]["campo"], "team_size")
        self.assertIn("crm_tool", cobertura["situation"]["missing"])

    def test_problem_main_pain_extraido_corretamente(self):
        ia_mock = _mock_ia([{
            "stage": "problem", "campo": "main_pain", "valor": "leads esfriam antes do contato",
            "evidence_quote": "nosso maior problema é que os leads esfriam antes de a gente ligar",
        }])
        with patch("agent.spin_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            cobertura = asyncio.run(extrair_spin_state_async(_TRANSCRICAO, _HISTORICO))
        self.assertEqual(cobertura["problem"]["known"][0]["campo"], "main_pain")
        self.assertEqual(cobertura["problem"]["missing"], [])

    def test_implication_financial_impact_extraido_corretamente(self):
        texto = "Cliente: isso já nos custou uns R$50 mil em vendas perdidas esse trimestre."
        ia_mock = _mock_ia([{
            "stage": "implication", "campo": "financial_impact", "valor": "R$50 mil no trimestre",
            "evidence_quote": "isso já nos custou uns R$50 mil em vendas perdidas esse trimestre",
        }])
        with patch("agent.spin_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            cobertura = asyncio.run(extrair_spin_state_async(texto, ""))
        self.assertEqual(cobertura["implication"]["known"][0]["campo"], "financial_impact")
        self.assertIn("conversion_impact", cobertura["implication"]["missing"])

    def test_need_payoff_solution_value_extraido_corretamente(self):
        texto = "Cliente: se resolvêssemos isso, acho que dava pra dobrar a conversão."
        ia_mock = _mock_ia([{
            "stage": "need_payoff", "campo": "solution_value", "valor": "dobrar a conversão",
            "evidence_quote": "se resolvêssemos isso, acho que dava pra dobrar a conversão",
        }])
        with patch("agent.spin_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            cobertura = asyncio.run(extrair_spin_state_async(texto, ""))
        self.assertEqual(cobertura["need_payoff"]["known"][0]["campo"], "solution_value")


class ExtrairSpinStateAsyncGuardasTest(unittest.TestCase):
    def test_sem_sinal_claro_retorna_cobertura_vazia_nunca_none(self):
        ia_mock = _mock_ia([])
        with patch("agent.spin_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            cobertura = asyncio.run(extrair_spin_state_async("Cliente: oi, tudo bem?", ""))
        self.assertIsNotNone(cobertura)
        for stage in ("situation", "problem", "implication", "need_payoff"):
            self.assertEqual(cobertura[stage]["known"], [])

    def test_evidence_quote_que_nao_existe_na_conversa_e_descartada(self):
        ia_mock = _mock_ia([{
            "stage": "situation", "campo": "team_size", "valor": "8 pessoas",
            "evidence_quote": "frase que a IA inventou e não está na conversa real",
        }])
        with patch("agent.spin_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            cobertura = asyncio.run(extrair_spin_state_async(_TRANSCRICAO, _HISTORICO))
        self.assertEqual(cobertura["situation"]["known"], [])
        self.assertIn("team_size", cobertura["situation"]["missing"])

    def test_stage_invalido_e_descartado(self):
        ia_mock = _mock_ia([{
            "stage": "estagio_inventado", "campo": "team_size", "valor": "8",
            "evidence_quote": "hoje somos 8 pessoas no time comercial",
        }])
        with patch("agent.spin_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            cobertura = asyncio.run(extrair_spin_state_async(_TRANSCRICAO, _HISTORICO))
        self.assertEqual(cobertura["situation"]["known"], [])

    def test_campo_fora_do_checklist_do_estagio_e_descartado(self):
        ia_mock = _mock_ia([{
            "stage": "situation", "campo": "campo_inventado", "valor": "x",
            "evidence_quote": "hoje somos 8 pessoas no time comercial",
        }])
        with patch("agent.spin_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            cobertura = asyncio.run(extrair_spin_state_async(_TRANSCRICAO, _HISTORICO))
        self.assertEqual(cobertura["situation"]["known"], [])

    def test_campo_duplicado_mantem_so_primeira_ocorrencia(self):
        ia_mock = _mock_ia([
            {"stage": "situation", "campo": "team_size", "valor": "8 pessoas",
             "evidence_quote": "hoje somos 8 pessoas no time comercial"},
            {"stage": "situation", "campo": "team_size", "valor": "outro valor",
             "evidence_quote": "hoje somos 8 pessoas no time comercial"},
        ])
        with patch("agent.spin_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            cobertura = asyncio.run(extrair_spin_state_async(_TRANSCRICAO, _HISTORICO))
        self.assertEqual(len(cobertura["situation"]["known"]), 1)

    def test_valor_vazio_e_descartado(self):
        ia_mock = _mock_ia([{
            "stage": "situation", "campo": "team_size", "valor": "",
            "evidence_quote": "hoje somos 8 pessoas no time comercial",
        }])
        with patch("agent.spin_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            cobertura = asyncio.run(extrair_spin_state_async(_TRANSCRICAO, _HISTORICO))
        self.assertEqual(cobertura["situation"]["known"], [])

    def test_falha_real_de_ia_propaga(self):
        ia_mock = AsyncMock(side_effect=RuntimeError("4 provedores esgotados"))
        with patch("agent.spin_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            with self.assertRaises(RuntimeError):
                asyncio.run(extrair_spin_state_async(_TRANSCRICAO, _HISTORICO))

    def test_multiplos_fatos_validos_em_estagios_diferentes(self):
        ia_mock = _mock_ia([
            {"stage": "situation", "campo": "team_size", "valor": "8 pessoas",
             "evidence_quote": "hoje somos 8 pessoas no time comercial"},
            {"stage": "problem", "campo": "main_pain", "valor": "leads esfriam",
             "evidence_quote": "nosso maior problema é que os leads esfriam antes de a gente ligar"},
        ])
        with patch("agent.spin_extractor.chamar_ia_com_fallback_claude", new=ia_mock):
            cobertura = asyncio.run(extrair_spin_state_async(_TRANSCRICAO, _HISTORICO))
        self.assertEqual(len(cobertura["situation"]["known"]), 1)
        self.assertEqual(len(cobertura["problem"]["known"]), 1)


if __name__ == "__main__":
    unittest.main()
