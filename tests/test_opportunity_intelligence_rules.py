"""
Testes de agent/opportunity_intelligence_rules.py — Fase 22 (Frontend) /
bloco "Opportunity Intelligence" do "PROMPT MESTRE — SALE-IA V2".

Módulo puro (sem IA, sem banco) — mesmo padrão de
tests/test_recommendation_effectiveness_rules.py.

Run:
    python -m unittest tests.test_opportunity_intelligence_rules -v
"""

import unittest

from agent.opportunity_intelligence_rules import (
    MEDDPICC_NAO_DISPONIVEL,
    RISCOS_CALCULADOS_NAO_DISPONIVEL,
    SPIN_COVERAGE_NAO_DISPONIVEL,
    montar_opportunity_intelligence,
)


def _opportunity(**overrides):
    base = {
        "id": 1,
        "client_id": "client-1",
        "seller_id": "seller-1",
        "stage": "proposta",
        "status": "open",
        "estimated_value": 50000.0,
        "outcome_value": None,
        "cycle_days": None,
    }
    base.update(overrides)
    return base


def _insight(campo, valor, evidence="evidência real", confidence=0.9):
    return {"id": 1, "meeting_id": "m1", "campo": campo, "valor": valor, "evidence": evidence, "confidence": confidence, "timestamp": "2026-09-19T00:00:00", "contradiz": None}


class EstruturaCompletaTest(unittest.TestCase):
    def test_todas_as_12_chaves_literais_presentes(self):
        resultado = montar_opportunity_intelligence(_opportunity(), {})
        chaves_esperadas = {
            "opportunity_health", "spin_coverage", "meddpicc", "pain", "impact",
            "champion", "economic_buyer", "decision_process", "objections",
            "competitors", "risks_relatados", "risks_calculados", "next_steps",
        }
        self.assertEqual(set(resultado.keys()), chaves_esperadas)

    def test_opportunity_memory_ausente_nunca_quebra_nunca_vira_none(self):
        resultado = montar_opportunity_intelligence(_opportunity(), {})
        for campo in ("pain", "impact", "champion", "economic_buyer", "decision_process", "objections", "competitors", "risks_relatados", "next_steps"):
            self.assertEqual(resultado[campo], [])


class OpportunityHealthTest(unittest.TestCase):
    def test_reflete_campos_reais_da_opportunity(self):
        opp = _opportunity(stage="negociacao", status="open", estimated_value=120000.0, outcome_value=None, cycle_days=None)
        resultado = montar_opportunity_intelligence(opp, {})
        self.assertEqual(resultado["opportunity_health"], {
            "stage": "negociacao", "status": "open", "estimated_value": 120000.0,
            "outcome_value": None, "cycle_days": None,
        })

    def test_stage_vazio_vira_none_nunca_string_vazia(self):
        opp = _opportunity(stage="")
        resultado = montar_opportunity_intelligence(opp, {})
        self.assertIsNone(resultado["opportunity_health"]["stage"])


class GapsExplicitosTest(unittest.TestCase):
    """SPIN Coverage, MEDDPICC e riscos calculados nunca fabricam dado —
    sempre o mesmo dict de gap, com disponivel=False e motivo."""

    def test_spin_coverage_e_sempre_gap(self):
        resultado = montar_opportunity_intelligence(_opportunity(), {})
        self.assertEqual(resultado["spin_coverage"], SPIN_COVERAGE_NAO_DISPONIVEL)
        self.assertFalse(resultado["spin_coverage"]["disponivel"])

    def test_meddpicc_e_sempre_gap(self):
        resultado = montar_opportunity_intelligence(_opportunity(), {})
        self.assertEqual(resultado["meddpicc"], MEDDPICC_NAO_DISPONIVEL)
        self.assertFalse(resultado["meddpicc"]["disponivel"])

    def test_riscos_calculados_e_sempre_gap(self):
        resultado = montar_opportunity_intelligence(_opportunity(), {})
        self.assertEqual(resultado["risks_calculados"], RISCOS_CALCULADOS_NAO_DISPONIVEL)
        self.assertFalse(resultado["risks_calculados"]["disponivel"])

    def test_gaps_sao_copias_nunca_a_mesma_referencia_mutavel(self):
        r1 = montar_opportunity_intelligence(_opportunity(), {})
        r1["spin_coverage"]["motivo"] = "mutado"
        r2 = montar_opportunity_intelligence(_opportunity(), {})
        self.assertNotEqual(r2["spin_coverage"]["motivo"], "mutado")


class PassThroughOpportunityMemoryTest(unittest.TestCase):
    """9 campos vêm direto das categorias já existentes de
    OpportunityMemory (Fase 2) — dado real, nunca transformado/inventado."""

    def test_mapeamento_de_categoria_para_campo_literal(self):
        memoria = {
            "pain_points": [_insight("dor", "leads esquecidos")],
            "business_impact": [_insight("impacto", "R$20.000/mês")],
            "champion": [_insight("nome", "Marcos Lima")],
            "economic_buyer": [_insight("nome", "Ana Souza")],
            "decision_process": [_insight("etapas", "comitê mensal")],
            "objections": [_insight("categoria", "PRICE")],
            "competitors": [_insight("nome", "Concorrente X")],
            "risks": [_insight("risco", "sem próximo passo definido")],
            "next_steps": [_insight("acao", "enviar proposta")],
            # categorias de OpportunityMemory que NÃO fazem parte dos 12
            # campos literais da Fase 22 — nunca devem vazar na resposta
            "goals": [_insight("meta", "crescer 20%")],
            "stakeholders": [_insight("nome", "outro contato")],
            "metrics": [_insight("kpi", "conversão")],
            "unknowns": [_insight("duvida", "orçamento real")],
        }
        resultado = montar_opportunity_intelligence(_opportunity(), memoria)

        self.assertEqual(resultado["pain"], memoria["pain_points"])
        self.assertEqual(resultado["impact"], memoria["business_impact"])
        self.assertEqual(resultado["champion"], memoria["champion"])
        self.assertEqual(resultado["economic_buyer"], memoria["economic_buyer"])
        self.assertEqual(resultado["decision_process"], memoria["decision_process"])
        self.assertEqual(resultado["objections"], memoria["objections"])
        self.assertEqual(resultado["competitors"], memoria["competitors"])
        self.assertEqual(resultado["risks_relatados"], memoria["risks"])
        self.assertEqual(resultado["next_steps"], memoria["next_steps"])

        # goals/stakeholders/metrics/unknowns não fazem parte do contrato
        for chave_nao_pedida in ("goals", "stakeholders", "metrics", "unknowns"):
            self.assertNotIn(chave_nao_pedida, resultado)


if __name__ == "__main__":
    unittest.main()
