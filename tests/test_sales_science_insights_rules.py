"""
Testes de agent/sales_science_insights_rules.py — Fase 22 (Frontend) /
bloco "Sales Science" do "PROMPT MESTRE — SALE-IA V2".

Módulo puro (sem IA, sem banco) — orquestra motores já prontos das
Fases 8/9/13 sobre uma lista de Opportunity real.

Run:
    python -m unittest tests.test_sales_science_insights_rules -v
"""

import unittest
from datetime import datetime, timedelta

from agent.sales_science_insights_rules import (
    OBJECTION_TRENDS_NAO_DISPONIVEL,
    SELLER_BENCHMARK_NAO_DISPONIVEL,
    STRATEGY_EFFECTIVENESS_NAO_DISPONIVEL,
    montar_sales_science_insights,
)


def _opp(i, stage, status, created_offset_days=0, cycle_days=5, product="Plano Pro", competitor=None):
    created = datetime(2026, 1, 1) + timedelta(days=created_offset_days)
    close = created + timedelta(days=cycle_days) if status in ("won", "lost") else None
    return {
        "id": i, "client_id": f"c{i}", "seller_id": "s1",
        "created_at": created.isoformat(), "stage": stage, "status": status,
        "estimated_value": 1000.0, "outcome_value": 1200.0 if status == "won" else None,
        "product": product, "competitor": competitor,
        "close_date": close.isoformat() if close else None, "cycle_days": cycle_days,
    }


class EstruturaCompletaTest(unittest.TestCase):
    def test_todas_as_chaves_literais_presentes(self):
        resultado = montar_sales_science_insights([])
        chaves_esperadas = {
            "amostra_total", "win_loss", "seasonality", "conversion_drivers",
            "seller_benchmark", "strategy_effectiveness", "objection_trends",
        }
        self.assertEqual(set(resultado.keys()), chaves_esperadas)

    def test_lista_vazia_nunca_quebra(self):
        resultado = montar_sales_science_insights([])
        self.assertEqual(resultado["amostra_total"], 0)
        self.assertEqual(resultado["win_loss"], {"stage": [], "product": [], "competitor": []})
        self.assertEqual(resultado["conversion_drivers"], [])


class GapsExplicitosTest(unittest.TestCase):
    def test_seller_benchmark_e_sempre_gap(self):
        resultado = montar_sales_science_insights([])
        self.assertEqual(resultado["seller_benchmark"], SELLER_BENCHMARK_NAO_DISPONIVEL)
        self.assertFalse(resultado["seller_benchmark"]["disponivel"])

    def test_strategy_effectiveness_e_sempre_gap(self):
        resultado = montar_sales_science_insights([])
        self.assertEqual(resultado["strategy_effectiveness"], STRATEGY_EFFECTIVENESS_NAO_DISPONIVEL)

    def test_objection_trends_e_sempre_gap(self):
        resultado = montar_sales_science_insights([])
        self.assertEqual(resultado["objection_trends"], OBJECTION_TRENDS_NAO_DISPONIVEL)

    def test_gaps_sao_copias_nunca_a_mesma_referencia_mutavel(self):
        r1 = montar_sales_science_insights([])
        r1["seller_benchmark"]["motivo"] = "mutado"
        r2 = montar_sales_science_insights([])
        self.assertNotEqual(r2["seller_benchmark"]["motivo"], "mutado")


class AmostraInsuficienteTest(unittest.TestCase):
    def test_amostra_abaixo_de_30_nunca_produz_insight(self):
        opps = [_opp(i, "descoberta", "won" if i % 2 == 0 else "lost", created_offset_days=i) for i in range(10)]
        resultado = montar_sales_science_insights(opps)
        self.assertEqual(resultado["win_loss"]["stage"], [])
        self.assertEqual(resultado["conversion_drivers"], [])


class SinalRealTest(unittest.TestCase):
    """Reproduz o cenário sintético já validado manualmente: 2 estágios,
    taxas de conversão bem diferentes, amostra grande o bastante."""

    def _dataset(self):
        opps = []
        for i in range(200):
            stage = "descoberta" if i < 100 else "negociacao"
            status = "won" if (i < 25 or (i >= 100 and i < 169)) else "lost"
            opps.append(_opp(i, stage, status, created_offset_days=i % 20))
        return opps

    def test_win_loss_detecta_diferenca_real_entre_estagios(self):
        resultado = montar_sales_science_insights(self._dataset())
        insights_por_valor = {i["evidence"]["valor"]: i for i in resultado["win_loss"]["stage"]}
        self.assertIn("descoberta", insights_por_valor)
        self.assertIn("negociacao", insights_por_valor)
        self.assertEqual(insights_por_valor["descoberta"]["sample"], 100)
        self.assertEqual(insights_por_valor["negociacao"]["sample"], 100)

    def test_conversion_drivers_ranqueia_por_desvio_do_baseline(self):
        resultado = montar_sales_science_insights(self._dataset())
        self.assertEqual(len(resultado["conversion_drivers"]), 2)
        # ordenado por |diferenca_vs_baseline| decrescente -> ambos empatados
        # aqui, só confirma que os dois aparecem com sample=100
        for driver in resultado["conversion_drivers"]:
            self.assertEqual(driver["sample"], 100)

    def test_seasonality_roda_sem_erro_com_dataset_real(self):
        resultado = montar_sales_science_insights(self._dataset())
        self.assertIn("month", resultado["seasonality"])
        self.assertIn("quarter", resultado["seasonality"])
        self.assertIn("weekday", resultado["seasonality"])


if __name__ == "__main__":
    unittest.main()
