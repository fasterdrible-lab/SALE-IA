"""
Testes do Question Gap Engine — Fase 3 / Tarefa 3.2 do "PROMPT MESTRE
— SALE-IA V2".

Função pura (agent/question_gap_rules.py), sem IA/banco — constrói
sobre a cobertura SPIN da Tarefa 3.1 (agent/spin_coverage_rules.py).
Reproduz o exemplo literal da Tarefa 3.2: gap "economic impact"
(financial_impact) → recomendação "Quanto esse problema custa
atualmente?".

Run:
    python -m unittest tests.test_question_gap_rules -v
"""

import unittest

from agent.question_gap_rules import (
    PRIORIDADE_ORDEM,
    STAGE_PRIORIDADE_PADRAO,
    calcular_gaps_priorizados,
    proximo_gap,
)
from agent.spin_coverage_rules import calcular_cobertura_spin


def _fato(stage, campo, valor, evidence="evidencia generica"):
    return {"stage": stage, "campo": campo, "valor": valor, "evidence_quote": evidence}


class CalcularGapsPriorizadosTest(unittest.TestCase):
    def test_exemplo_literal_do_prompt_mestre(self):
        """Situation/Problem cobertos, Implication e Need Payoff
        faltantes — o gap 'economic impact' (financial_impact) deve
        vir com a recomendação exata do prompt mestre."""
        fatos = [
            _fato("situation", "team_size", "12 vendedores"),
            _fato("situation", "crm_tool", "HubSpot"),
            _fato("problem", "main_pain", "follow-up lento"),
        ]
        cobertura = calcular_cobertura_spin(fatos)
        gaps = calcular_gaps_priorizados(cobertura)

        gap_impacto_financeiro = next(g for g in gaps if g["campo"] == "financial_impact")
        self.assertEqual(gap_impacto_financeiro["stage"], "implication")
        self.assertEqual(gap_impacto_financeiro["pergunta"], "Quanto esse problema custa atualmente?")

    def test_pergunta_relacionada_ao_gap_detectado(self):
        """Regra central da Tarefa 3.2: a pergunta recomendada precisa
        estar relacionada ao campo do gap, nunca a outro."""
        cobertura = calcular_cobertura_spin([], checklist={
            "situation": [], "problem": [], "implication": [], "need_payoff": ["solution_value"],
        })
        gaps = calcular_gaps_priorizados(cobertura)
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["campo"], "solution_value")
        self.assertIn("valeria", gaps[0]["pergunta"].lower())

    def test_prioridade_critical_high_medium_low_na_ordem_correta(self):
        """As 4 prioridades usadas pelo prompt mestre, em ordem —
        critical primeiro, low por último."""
        cobertura = calcular_cobertura_spin([])
        gaps = calcular_gaps_priorizados(cobertura)

        prioridades_presentes = [gap["priority"] for gap in gaps]
        for prioridade in prioridades_presentes:
            self.assertIn(prioridade, PRIORIDADE_ORDEM)

        indices = [PRIORIDADE_ORDEM.index(p) for p in prioridades_presentes]
        self.assertEqual(indices, sorted(indices))

    def test_gap_de_implication_e_critical_por_padrao(self):
        cobertura = calcular_cobertura_spin([], checklist={
            "situation": [], "problem": [], "implication": ["financial_impact"], "need_payoff": [],
        })
        gaps = calcular_gaps_priorizados(cobertura)
        self.assertEqual(gaps[0]["priority"], "critical")

    def test_prioridade_por_stage_customizada_e_respeitada(self):
        cobertura = calcular_cobertura_spin([], checklist={
            "situation": ["team_size"], "problem": [], "implication": [], "need_payoff": [],
        })
        prioridade_custom = {**STAGE_PRIORIDADE_PADRAO, "situation": "critical"}
        gaps = calcular_gaps_priorizados(cobertura, prioridade_por_stage=prioridade_custom)
        self.assertEqual(gaps[0]["priority"], "critical")
        self.assertEqual(gaps[0]["campo"], "team_size")

    def test_prioridade_invalida_levanta(self):
        cobertura = calcular_cobertura_spin([])
        with self.assertRaises(ValueError):
            calcular_gaps_priorizados(cobertura, prioridade_por_stage={"situation": "urgentissimo"})

    def test_stage_invalido_em_prioridade_por_stage_levanta(self):
        cobertura = calcular_cobertura_spin([])
        with self.assertRaises(ValueError):
            calcular_gaps_priorizados(cobertura, prioridade_por_stage={"descoberta": "critical"})

    def test_sem_gaps_quando_cobertura_completa(self):
        checklist = {"situation": [], "problem": [], "implication": [], "need_payoff": []}
        cobertura = calcular_cobertura_spin([], checklist=checklist)
        self.assertEqual(calcular_gaps_priorizados(cobertura), [])


class ProximoGapTest(unittest.TestCase):
    def test_retorna_o_primeiro_gap_da_lista_priorizada(self):
        cobertura = calcular_cobertura_spin([])
        gaps = calcular_gaps_priorizados(cobertura)
        self.assertEqual(proximo_gap(gaps), gaps[0])
        self.assertEqual(proximo_gap(gaps)["priority"], "critical")

    def test_none_quando_lista_vazia(self):
        self.assertIsNone(proximo_gap([]))


if __name__ == "__main__":
    unittest.main()
