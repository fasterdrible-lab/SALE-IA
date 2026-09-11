"""
Testes do Deal Risk Engine — Fase 4 / Tarefa 4.2 do "PROMPT MESTRE —
SALE-IA V2".

Função pura (agent/deal_risk_rules.py), sem IA/banco — constrói sobre o
estado MEDDPICC da Tarefa 4.1 (agent/meddpicc_rules.py). Reproduz o
exemplo literal da Tarefa 4.2: oportunidade com dor forte, sem decisor
e sem próxima reunião deve gerar pelo menos NO_ECONOMIC_BUYER e
NO_NEXT_STEP.

Run:
    python -m unittest tests.test_deal_risk_rules -v
"""

import unittest

from agent.deal_risk_rules import (
    DEAL_RISK_TIPOS,
    LIMIAR_DIAS_STALE_PADRAO,
    LIMIAR_OBJECOES_PRECO_PADRAO,
    calcular_riscos,
)
from agent.meddpicc_rules import calcular_qualificacao_meddpicc


def _fato_meddpicc(item, status, confidence=0.8, evidence="evidencia generica"):
    return {"item": item, "status": status, "confidence": confidence, "evidence_quote": evidence}


class CalcularRiscosTest(unittest.TestCase):
    def test_exemplo_literal_do_prompt_mestre(self):
        """Dor forte (identify_pain CONFIRMED), sem decisor (economic_buyer
        continua UNKNOWN) e sem proxima reuniao — deve gerar pelo menos
        NO_ECONOMIC_BUYER e NO_NEXT_STEP."""
        estado = calcular_qualificacao_meddpicc([
            _fato_meddpicc("identify_pain", "CONFIRMED", 0.9, "perdendo R$50.000/mes em leads esquecidos"),
        ])
        riscos = calcular_riscos(estado_meddpicc=estado, tem_proximo_passo=False)

        self.assertIn("NO_ECONOMIC_BUYER", riscos)
        self.assertIn("NO_NEXT_STEP", riscos)

    def test_oportunidade_saudavel_sem_nenhum_risco(self):
        estado = calcular_qualificacao_meddpicc([
            _fato_meddpicc("economic_buyer", "CONFIRMED", 0.9, "CFO aprovou o orcamento"),
            _fato_meddpicc("champion", "CONFIRMED", 0.9, "VP de vendas patrocina o projeto"),
            _fato_meddpicc("metrics", "CONFIRMED", 0.9, "meta de reducao de CAC confirmada"),
        ])
        riscos = calcular_riscos(
            estado_meddpicc=estado,
            tem_proximo_passo=True,
            total_objecoes_preco=0,
            competidor_em_vantagem=False,
            dias_desde_ultima_atividade=2,
        )
        self.assertEqual(riscos, [])

    def test_no_economic_buyer_quando_item_nao_confirmado(self):
        estado = calcular_qualificacao_meddpicc([
            _fato_meddpicc("economic_buyer", "PARTIAL", 0.4, "ainda precisa validar com a diretoria"),
        ])
        riscos = calcular_riscos(estado_meddpicc=estado)
        self.assertIn("NO_ECONOMIC_BUYER", riscos)

    def test_no_champion_quando_item_nao_confirmado(self):
        riscos = calcular_riscos(estado_meddpicc={})
        self.assertIn("NO_CHAMPION", riscos)

    def test_no_metrics_quando_item_nao_confirmado(self):
        riscos = calcular_riscos(estado_meddpicc=None)
        self.assertIn("NO_METRICS", riscos)

    def test_no_next_step_quando_sem_proximo_passo(self):
        riscos = calcular_riscos(tem_proximo_passo=False)
        self.assertIn("NO_NEXT_STEP", riscos)
        riscos_com_proximo_passo = calcular_riscos(tem_proximo_passo=True)
        self.assertNotIn("NO_NEXT_STEP", riscos_com_proximo_passo)

    def test_high_price_resistance_no_limiar_padrao(self):
        abaixo = calcular_riscos(total_objecoes_preco=LIMIAR_OBJECOES_PRECO_PADRAO - 1)
        self.assertNotIn("HIGH_PRICE_RESISTANCE", abaixo)
        no_limiar = calcular_riscos(total_objecoes_preco=LIMIAR_OBJECOES_PRECO_PADRAO)
        self.assertIn("HIGH_PRICE_RESISTANCE", no_limiar)

    def test_high_price_resistance_com_limiar_customizado(self):
        riscos = calcular_riscos(total_objecoes_preco=2, limiar_objecoes_preco=2)
        self.assertIn("HIGH_PRICE_RESISTANCE", riscos)

    def test_competitor_advantage_quando_sinal_explicito(self):
        riscos = calcular_riscos(competidor_em_vantagem=True)
        self.assertIn("COMPETITOR_ADVANTAGE", riscos)
        riscos_sem_sinal = calcular_riscos(competidor_em_vantagem=False)
        self.assertNotIn("COMPETITOR_ADVANTAGE", riscos_sem_sinal)

    def test_stale_opportunity_no_limiar_padrao(self):
        abaixo = calcular_riscos(dias_desde_ultima_atividade=LIMIAR_DIAS_STALE_PADRAO - 1)
        self.assertNotIn("STALE_OPPORTUNITY", abaixo)
        no_limiar = calcular_riscos(dias_desde_ultima_atividade=LIMIAR_DIAS_STALE_PADRAO)
        self.assertIn("STALE_OPPORTUNITY", no_limiar)

    def test_ordem_do_resultado_segue_deal_risk_tipos(self):
        """Todos os 7 riscos acionados de uma vez — a lista deve sair na
        ordem fixa de DEAL_RISK_TIPOS, nao na ordem de checagem interna."""
        riscos = calcular_riscos(
            estado_meddpicc={},
            tem_proximo_passo=False,
            total_objecoes_preco=LIMIAR_OBJECOES_PRECO_PADRAO,
            competidor_em_vantagem=True,
            dias_desde_ultima_atividade=LIMIAR_DIAS_STALE_PADRAO,
        )
        self.assertEqual(riscos, list(DEAL_RISK_TIPOS))

    def test_total_objecoes_preco_negativo_levanta(self):
        with self.assertRaises(ValueError):
            calcular_riscos(total_objecoes_preco=-1)

    def test_dias_desde_ultima_atividade_negativo_levanta(self):
        with self.assertRaises(ValueError):
            calcular_riscos(dias_desde_ultima_atividade=-1)


if __name__ == "__main__":
    unittest.main()
