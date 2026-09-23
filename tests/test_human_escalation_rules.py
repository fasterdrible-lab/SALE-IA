"""
Testes de agent/human_escalation_rules.py — Fase 25 do "PROMPT MESTRE
— SALE-IA V2" (Critério para iniciar o Digital Sales Twin), item 5/5
("escalonamento humano").

Módulo puro (sem IA, sem banco, sem rede) — mesmo padrão de
tests/test_autonomy_policy_rules.py.

Run:
    python -m unittest tests.test_human_escalation_rules -v
"""

import unittest

from agent.human_escalation_rules import (
    URGENCIA_POR_FRONTEIRA,
    montar_escalonamento,
    precisa_escalar_para_humano,
)


class PrecisaEscalarParaHumanoTest(unittest.TestCase):
    def test_forbidden_sempre_escala(self):
        self.assertTrue(precisa_escalar_para_humano("FORBIDDEN"))

    def test_human_required_sempre_escala(self):
        self.assertTrue(precisa_escalar_para_humano("HUMAN_REQUIRED"))

    def test_human_approval_sempre_escala(self):
        self.assertTrue(precisa_escalar_para_humano("HUMAN_APPROVAL"))

    def test_policy_dependent_sem_aprovacao_escala(self):
        self.assertTrue(precisa_escalar_para_humano("POLICY_DEPENDENT", policy_dependente_aprovado=False))

    def test_policy_dependent_aprovado_nao_escala(self):
        self.assertFalse(precisa_escalar_para_humano("POLICY_DEPENDENT", policy_dependente_aprovado=True))

    def test_autonomous_nunca_escala(self):
        self.assertFalse(precisa_escalar_para_humano("AUTONOMOUS"))

    def test_fronteira_invalida_levanta(self):
        with self.assertRaises(ValueError):
            precisa_escalar_para_humano("QUALQUER_COISA")

    def test_decisao_independe_do_nivel_de_autonomia(self):
        # Regra de correção desta rodada: AUTONOMOUS nunca escala,
        # mesmo quando o sistema está em nível baixo (OBSERVE) — não
        # executar por falta de nível ligado não é motivo pra chamar
        # um humano, é decisão de operação.
        self.assertFalse(precisa_escalar_para_humano("AUTONOMOUS"))
        self.assertTrue(precisa_escalar_para_humano("HUMAN_REQUIRED"))


class MontarEscalonamentoTest(unittest.TestCase):
    def test_monta_registro_completo(self):
        registro = montar_escalonamento(
            acao="alteracao_juridica",
            fronteira="HUMAN_REQUIRED",
            motivo="cláusula contratual não padrão",
            contexto={"opportunity_id": 42},
        )
        self.assertEqual(registro["acao"], "alteracao_juridica")
        self.assertEqual(registro["fronteira"], "HUMAN_REQUIRED")
        self.assertEqual(registro["motivo"], "cláusula contratual não padrão")
        self.assertEqual(registro["urgencia"], "🔴")
        self.assertEqual(registro["contexto"], {"opportunity_id": 42})

    def test_contexto_default_dict_vazio(self):
        registro = montar_escalonamento("qualificar", "HUMAN_APPROVAL", "motivo real")
        self.assertEqual(registro["contexto"], {})

    def test_motivo_vazio_levanta(self):
        with self.assertRaises(ValueError):
            montar_escalonamento("acao", "HUMAN_REQUIRED", "")
        with self.assertRaises(ValueError):
            montar_escalonamento("acao", "HUMAN_REQUIRED", "   ")

    def test_acao_vazia_levanta(self):
        with self.assertRaises(ValueError):
            montar_escalonamento("", "HUMAN_REQUIRED", "motivo real")

    def test_fronteira_invalida_levanta(self):
        with self.assertRaises(ValueError):
            montar_escalonamento("acao", "NAO_EXISTE", "motivo real")

    def test_urgencia_desconhecida_cai_no_default(self):
        # Todas as 5 fronteiras literais têm entrada em
        # URGENCIA_POR_FRONTEIRA, exceto AUTONOMOUS (nunca escala, mas
        # montar_escalonamento() ainda aceita — quem decide se chama é
        # precisa_escalar_para_humano()).
        registro = montar_escalonamento("dar_informacao_publica", "AUTONOMOUS", "motivo qualquer")
        self.assertEqual(registro["urgencia"], "⚠️")


class VocabularioTest(unittest.TestCase):
    def test_urgencia_cobre_as_4_fronteiras_que_podem_escalar(self):
        for fronteira in ("FORBIDDEN", "HUMAN_REQUIRED", "HUMAN_APPROVAL", "POLICY_DEPENDENT"):
            self.assertIn(fronteira, URGENCIA_POR_FRONTEIRA)


if __name__ == "__main__":
    unittest.main(verbosity=2)
