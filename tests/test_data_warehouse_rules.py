"""
Testes de agent/data_warehouse_rules.py — Fase 9 / Tarefa 9.1 do
"PROMPT MESTRE — SALE-IA V2" (Data Warehouse comercial mínimo).

Módulo puro (sem IA, sem banco) — mesmo padrão de
tests/test_win_loss_rules.py / tests/test_outcome_rules.py.

Run:
    python -m unittest tests.test_data_warehouse_rules -v
"""

import unittest
from datetime import datetime

from agent.data_warehouse_rules import (
    DIMENSOES_DATASET,
    construir_dataset_analitico,
    construir_linha_analitica,
    derivar_dimensoes_calendario,
    pode_executar_analise_pesada,
)


class DerivarDimensoesCalendarioTest(unittest.TestCase):
    def test_dimensoes_de_uma_data_conhecida(self):
        # 14/09/2026 é uma segunda-feira, Q3.
        data = datetime(2026, 9, 14, 15, 30)
        dims = derivar_dimensoes_calendario(data)
        self.assertEqual(dims["date"], "2026-09-14")
        self.assertEqual(dims["month"], 9)
        self.assertEqual(dims["quarter"], 3)
        self.assertEqual(dims["weekday"], 0)  # segunda
        self.assertEqual(dims["hour"], 15)

    def test_quarter_calculado_corretamente_nos_4_trimestres(self):
        self.assertEqual(derivar_dimensoes_calendario(datetime(2026, 1, 1))["quarter"], 1)
        self.assertEqual(derivar_dimensoes_calendario(datetime(2026, 4, 1))["quarter"], 2)
        self.assertEqual(derivar_dimensoes_calendario(datetime(2026, 7, 1))["quarter"], 3)
        self.assertEqual(derivar_dimensoes_calendario(datetime(2026, 12, 31))["quarter"], 4)

    def test_data_invalida_levanta(self):
        with self.assertRaises(ValueError):
            derivar_dimensoes_calendario("2026-09-14")  # string, nao datetime


class ConstruirLinhaAnaliticaTest(unittest.TestCase):
    def _opportunity_won(self):
        return {
            "seller_id": "vendedor-1",
            "stage": "fechamento",
            "status": "won",
            "estimated_value": 10000.0,
            "outcome_value": 25000.0,
            "product": "SALEIA Enterprise",
            "close_date": "2026-09-14T15:30:00",
            "created_at": "2026-08-01T10:00:00",
            "cycle_days": 44,
        }

    def test_usa_close_date_por_padrao(self):
        linha = construir_linha_analitica(self._opportunity_won())
        self.assertEqual(linha["date"], "2026-09-14")
        self.assertEqual(linha["month"], 9)

    def test_cai_para_created_at_quando_sem_close_date(self):
        opp = self._opportunity_won()
        opp["close_date"] = None
        linha = construir_linha_analitica(opp)
        self.assertEqual(linha["date"], "2026-08-01")

    def test_ticket_prioriza_outcome_value_sobre_estimated_value(self):
        linha = construir_linha_analitica(self._opportunity_won())
        self.assertEqual(linha["ticket"], 25000.0)

    def test_ticket_cai_para_estimated_value_sem_outcome_value(self):
        opp = self._opportunity_won()
        opp["outcome_value"] = None
        linha = construir_linha_analitica(opp)
        self.assertEqual(linha["ticket"], 10000.0)

    def test_won_lost_mapeados_como_flags_booleanos(self):
        won = construir_linha_analitica(self._opportunity_won())
        self.assertTrue(won["won"])
        self.assertFalse(won["lost"])

        opp_lost = self._opportunity_won()
        opp_lost["status"] = "lost"
        lost = construir_linha_analitica(opp_lost)
        self.assertFalse(lost["won"])
        self.assertTrue(lost["lost"])

    def test_status_open_nao_e_won_nem_lost(self):
        opp = self._opportunity_won()
        opp["status"] = "open"
        linha = construir_linha_analitica(opp)
        self.assertFalse(linha["won"])
        self.assertFalse(linha["lost"])

    def test_dimensoes_extra_nao_rastreadas_na_opportunity_ainda_aparecem(self):
        linha = construir_linha_analitica(
            self._opportunity_won(),
            team="Time A", segment="Enterprise", lead_source="Outbound",
            objection_type="preco", sales_strategy="consultiva",
        )
        self.assertEqual(linha["team"], "Time A")
        self.assertEqual(linha["segment"], "Enterprise")
        self.assertEqual(linha["lead_source"], "Outbound")
        self.assertEqual(linha["objection_type"], "preco")
        self.assertEqual(linha["sales_strategy"], "consultiva")

    def test_dimensoes_extra_ausentes_ficam_none_sem_levantar(self):
        linha = construir_linha_analitica(self._opportunity_won())
        self.assertIsNone(linha["team"])
        self.assertIsNone(linha["segment"])

    def test_todas_as_16_dimensoes_do_prompt_mestre_presentes(self):
        linha = construir_linha_analitica(self._opportunity_won())
        self.assertEqual(set(linha.keys()), DIMENSOES_DATASET)

    def test_sem_nenhuma_data_levanta(self):
        with self.assertRaises(ValueError):
            construir_linha_analitica({"status": "won"})


class ConstruirDatasetAnaliticoTest(unittest.TestCase):
    def test_pula_oportunidade_sem_data_sem_derrubar_o_dataset(self):
        boa = {"status": "won", "close_date": "2026-09-14T10:00:00", "created_at": "2026-08-01T10:00:00"}
        ruim = {"status": "lost"}  # sem nenhuma data
        dataset = construir_dataset_analitico([boa, ruim, boa])
        self.assertEqual(len(dataset), 2)  # so as 2 boas

    def test_dataset_vazio(self):
        self.assertEqual(construir_dataset_analitico([]), [])

    def test_dimensoes_extra_propagadas_pra_todas_as_linhas(self):
        opps = [
            {"status": "won", "close_date": "2026-09-14T10:00:00", "created_at": "2026-08-01T10:00:00"},
            {"status": "lost", "close_date": "2026-09-15T10:00:00", "created_at": "2026-08-02T10:00:00"},
        ]
        dataset = construir_dataset_analitico(opps, segment="SMB")
        self.assertTrue(all(linha["segment"] == "SMB" for linha in dataset))


class PodeExecutarAnalisePesadaTest(unittest.TestCase):
    def test_sem_reuniao_ativa_pode_executar(self):
        self.assertTrue(pode_executar_analise_pesada(0))

    def test_com_reuniao_ativa_nao_pode_executar(self):
        self.assertFalse(pode_executar_analise_pesada(1))
        self.assertFalse(pode_executar_analise_pesada(5))

    def test_valor_negativo_levanta(self):
        with self.assertRaises(ValueError):
            pode_executar_analise_pesada(-1)


if __name__ == "__main__":
    unittest.main()
