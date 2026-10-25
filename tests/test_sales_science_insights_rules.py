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
    STRATEGY_EFFECTIVENESS_NAO_DISPONIVEL,
    classificar_vendedores,
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
    def test_seller_benchmark_sem_vendedor_e_gap(self):
        resultado = montar_sales_science_insights([])
        self.assertFalse(resultado["seller_benchmark"]["disponivel"])
        self.assertEqual(resultado["seller_benchmark"]["vendedores"], [])

    def test_strategy_effectiveness_e_sempre_gap(self):
        resultado = montar_sales_science_insights([])
        self.assertEqual(resultado["strategy_effectiveness"], STRATEGY_EFFECTIVENESS_NAO_DISPONIVEL)

    def test_objection_trends_sem_evidencia_e_gap(self):
        resultado = montar_sales_science_insights([])
        self.assertEqual(resultado["objection_trends"], OBJECTION_TRENDS_NAO_DISPONIVEL)
        resultado = montar_sales_science_insights([], [])
        self.assertEqual(resultado["objection_trends"], OBJECTION_TRENDS_NAO_DISPONIVEL)

    def test_gaps_sao_copias_nunca_a_mesma_referencia_mutavel(self):
        r1 = montar_sales_science_insights([])
        r1["strategy_effectiveness"]["motivo"] = "mutado"
        r2 = montar_sales_science_insights([])
        self.assertNotEqual(r2["strategy_effectiveness"]["motivo"], "mutado")


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


def _ev(meeting_id, categoria, dia, tipo_prefixo="OBJECTION"):
    return {"meeting_id": meeting_id, "type": f"{tipo_prefixo}:{categoria}", "quote": "x",
            "timestamp": dia.isoformat(), "created_at": dia.isoformat()}


class ObjectionTrendsTest(unittest.TestCase):
    """B4: Objection Trends com SalesEvidence OBJECTION:* reais."""

    SEMANA_1 = datetime(2026, 10, 12, 15, 0)  # 2026-W42
    SEMANA_2 = datetime(2026, 10, 19, 15, 0)  # 2026-W43

    def test_conta_uma_vez_por_reuniao_e_categoria(self):
        from agent.sales_science_insights_rules import eventos_de_objecao
        evs = [
            _ev("m1", "PRICE", self.SEMANA_1),
            _ev("m1", "PRICE", self.SEMANA_2),  # mesma objeção, outra citação/ciclo
            _ev("m1", "TRUST", self.SEMANA_1),
            _ev("m2", "PRICE", self.SEMANA_2),
            _ev("m3", "x", self.SEMANA_1, tipo_prefixo="ROOT_CAUSE"),  # não é objeção falada
        ]
        eventos = sorted(eventos_de_objecao(evs), key=lambda e: (e["category"], e["period"]))
        self.assertEqual(eventos, [
            {"category": "PRICE", "period": "2026-W42"},
            {"category": "PRICE", "period": "2026-W43"},
            {"category": "TRUST", "period": "2026-W42"},
        ])

    def test_uma_semana_so_mostra_distribuicao(self):
        evs = [_ev(f"m{i}", "PRICE" if i < 3 else "TRUST", self.SEMANA_1) for i in range(4)]
        ot = montar_sales_science_insights([], evs)["objection_trends"]
        self.assertFalse(ot["disponivel"])
        self.assertEqual(ot["total_objecoes"], 4)
        self.assertEqual(ot["distribuicao"], {"PRICE": 3, "TRUST": 1})
        self.assertIn("2026-W42", ot["motivo"])

    def test_duas_semanas_amostra_pequena_sem_insight(self):
        evs = [_ev("m1", "PRICE", self.SEMANA_1), _ev("m2", "TRUST", self.SEMANA_2)]
        ot = montar_sales_science_insights([], evs)["objection_trends"]
        self.assertTrue(ot["disponivel"])
        self.assertEqual(ot["insights"], [])

    def test_mudanca_grande_vira_insight_significativo(self):
        evs = []
        for i in range(40):
            evs.append(_ev(f"a{i}", "PRICE" if i < 30 else "TRUST", self.SEMANA_1))
            evs.append(_ev(f"b{i}", "PRICE" if i < 8 else "TRUST", self.SEMANA_2))
        ot = montar_sales_science_insights([], evs)["objection_trends"]
        self.assertTrue(ot["disponivel"])
        self.assertEqual((ot["total_inicio"], ot["total_fim"]), (40, 40))
        por_cat = {i["evidence"]["categoria"]: i for i in ot["insights"]}
        self.assertEqual(set(por_cat), {"PRICE", "TRUST"})
        self.assertIn("decrescente", por_cat["PRICE"]["insight"])
        self.assertIn("crescente", por_cat["TRUST"]["insight"])
        self.assertEqual(por_cat["PRICE"]["sample"], 38)


def _opp_vendedor(i, seller_id, status, product="Plano Pro", valor=1000.0):
    return {"id": i, "client_id": f"c{i}", "seller_id": seller_id, "status": status,
            "stage": "negociacao", "product": product, "estimated_value": valor,
            "created_at": "2026-10-01T10:00:00", "close_date": "2026-10-10T10:00:00"}


class SellerBenchmarkTest(unittest.TestCase):
    """B5: seller_tier real pela taxa de conversão de cada vendedor."""

    def _dataset(self, ganhos_por_vendedor, total=40):
        opps, i = [], 0
        for seller_id, ganhos in ganhos_por_vendedor.items():
            for k in range(total):
                opps.append(_opp_vendedor(i, seller_id, "won" if k < ganhos else "lost", valor=500.0 + 50 * (k % 10)))
                i += 1
        return opps

    def test_vendedor_abaixo_do_minimo_fica_sem_tier(self):
        opps = [_opp_vendedor(i, "s1", "won") for i in range(9)] + [_opp_vendedor(100, "s1", "open")]
        linhas = classificar_vendedores(opps)
        self.assertEqual(linhas, [{"seller_id": "s1", "won": 9, "lost": 0, "total": 9, "taxa_conversao": 1.0, "tier": None}])

    def test_menos_de_3_vendedores_elegiveis_e_gap_com_tabela(self):
        sb = montar_sales_science_insights(self._dataset({"s1": 30, "s2": 10}))["seller_benchmark"]
        self.assertFalse(sb["disponivel"])
        self.assertIn("2 vendedor(es)", sb["motivo"])
        self.assertEqual(len(sb["vendedores"]), 2)

    def test_tres_vendedores_viram_top_median_low(self):
        sb = montar_sales_science_insights(self._dataset({"s1": 30, "s2": 20, "s3": 8}))["seller_benchmark"]
        self.assertTrue(sb["disponivel"])
        tiers = {l["seller_id"]: l["tier"] for l in sb["vendedores"]}
        self.assertEqual(tiers, {"s1": "top", "s2": "median", "s3": "low"})
        por_tier = {i["evidence"]["valor"]: i for i in sb["insights"]}
        self.assertEqual(set(por_tier), {"top", "median", "low"})
        self.assertEqual(por_tier["top"]["sample"], 40)
        self.assertIsInstance(sb["confundimentos"], list)

    def test_vantagem_que_some_dentro_do_produto_vira_confundimento(self):
        # s1 só vende o produto fácil, s3 só o difícil: dentro de cada
        # produto não há comparação top x low -> nunca afirmar vantagem limpa.
        opps, i = [], 0
        for seller_id, ganhos, produto in (("s1", 30, "Fácil"), ("s2", 20, "Fácil"), ("s3", 8, "Difícil")):
            for k in range(40):
                opps.append(_opp_vendedor(i, seller_id, "won" if k < ganhos else "lost", product=produto))
                i += 1
        sb = montar_sales_science_insights(opps)["seller_benchmark"]
        self.assertTrue(sb["disponivel"])
        for c in sb["confundimentos"]:
            self.assertIn(c["possible_confounders"][0], ("product", "ticket"))


if __name__ == "__main__":
    unittest.main()
