"""
Testes de Budget Guard / projecao / precos de plano / auditoria financeira
(Cost Intelligence Fase 3) em api/database.py.

Usa engine SQLite em memoria isolado por teste — mesmo harness de
tests/test_cost_aggregation.py.

Run:
    python -m unittest tests.test_budget_and_margin -v
"""

import calendar
import unittest
from datetime import datetime
from unittest.mock import patch

from sqlmodel import Session, SQLModel, create_engine

from api import database


class BudgetAndMarginTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def _evento(self, **overrides):
        base = dict(
            feature="realtime.coach", provider="deepseek", model="deepseek-chat",
            input_tokens=100, output_tokens=50, usage_source="provider",
            cost_usd=0.01, success=True,
        )
        base.update(overrides)
        database.registrar_evento_uso_ia(**base)

    def _evento_em(self, ano, mes, dia, cost_usd):
        """Insere um evento com criado_em explicito — registrar_evento_uso_ia
        sempre usa datetime.now(), entao para simular "mes anterior" o teste
        grava direto via Session."""
        with Session(self._engine) as session:
            session.add(database.AiUsageEvent(
                feature="x", provider="deepseek", cost_usd=cost_usd,
                criado_em=datetime(ano, mes, dia),
            ))
            session.commit()

    # ── gasto_mes_usd ───────────────────────────

    def test_gasto_mes_usd_soma_so_o_mes_pedido(self):
        agora = datetime.now()
        self._evento(cost_usd=10.0)  # mes corrente

        if agora.month == 1:
            ano_ant, mes_ant = agora.year - 1, 12
        else:
            ano_ant, mes_ant = agora.year, agora.month - 1
        self._evento_em(ano_ant, mes_ant, 15, cost_usd=999.0)  # mes anterior — nao deve entrar

        total = database.gasto_mes_usd(agora.year, agora.month)
        self.assertAlmostEqual(total, 10.0, places=6)

    def test_gasto_mes_usd_sem_eventos_retorna_zero(self):
        self.assertEqual(database.gasto_mes_usd(2020, 1), 0.0)

    # ── projecao_mensal_custo ───────────────────

    def test_projecao_estrutura_e_calculo(self):
        agora = datetime.now()
        self._evento(cost_usd=10.0)

        r = database.projecao_mensal_custo()
        self.assertEqual(r["mes"], f"{agora.year:04d}-{agora.month:02d}")
        self.assertEqual(r["dias_decorridos"], agora.day)
        dias_no_mes = calendar.monthrange(agora.year, agora.month)[1]
        self.assertEqual(r["dias_no_mes"], dias_no_mes)
        self.assertAlmostEqual(r["gasto_atual_usd"], 10.0, places=6)
        esperado = round((10.0 / agora.day) * dias_no_mes, 6)
        self.assertAlmostEqual(r["projecao_fim_mes_usd"], esperado, places=6)

    def test_projecao_sem_gasto_nao_quebra(self):
        r = database.projecao_mensal_custo()
        self.assertEqual(r["gasto_atual_usd"], 0.0)
        self.assertEqual(r["projecao_fim_mes_usd"], 0.0)
        self.assertIsNone(r["crescimento_pct"])  # sem mes anterior pra comparar

    def test_projecao_crescimento_pct_vs_mes_anterior(self):
        agora = datetime.now()
        if agora.month == 1:
            ano_ant, mes_ant = agora.year - 1, 12
        else:
            ano_ant, mes_ant = agora.year, agora.month - 1
        self._evento_em(ano_ant, mes_ant, 15, cost_usd=20.0)
        self._evento(cost_usd=10.0)

        r = database.projecao_mensal_custo()
        self.assertAlmostEqual(r["gasto_mes_anterior_usd"], 20.0, places=6)
        self.assertIsNotNone(r["crescimento_pct"])

    # ── orcamento_ia ─────────────────────────────

    def test_obter_orcamento_sem_configuracao_retorna_none(self):
        self.assertIsNone(database.obter_orcamento_ia())

    def test_definir_e_obter_orcamento(self):
        r = database.definir_orcamento_ia(100.0, "admin-1", "admin@saleia.app.br")
        self.assertEqual(r["limite_mensal_usd"], 100.0)

        lido = database.obter_orcamento_ia()
        self.assertEqual(lido["limite_mensal_usd"], 100.0)
        self.assertEqual(lido["atualizado_por_email"], "admin@saleia.app.br")

    def test_definir_orcamento_grava_auditoria_com_valor_anterior_correto(self):
        database.definir_orcamento_ia(100.0, "admin-1", "admin@saleia.app.br")
        database.definir_orcamento_ia(150.0, "admin-1", "admin@saleia.app.br")

        auditoria = database.listar_auditoria_financeira()
        self.assertEqual(len(auditoria), 2)
        # mais recente primeiro
        self.assertEqual(auditoria[0]["tipo"], "orcamento")
        self.assertEqual(auditoria[0]["valor_anterior"], "100.0")
        self.assertEqual(auditoria[0]["valor_novo"], "150.0")
        self.assertIsNone(auditoria[1]["valor_anterior"])  # primeira config — nao havia valor antes

    # ── precos de plano ──────────────────────────

    def test_obter_precos_planos_vazio_por_padrao(self):
        self.assertEqual(database.obter_precos_planos(), {})

    def test_definir_preco_plano_upsert_e_auditoria(self):
        database.definir_preco_plano("pro", 199.0, "admin-1", "admin@saleia.app.br")
        self.assertEqual(database.obter_precos_planos(), {"pro": 199.0})

        database.definir_preco_plano("pro", 249.0, "admin-1", "admin@saleia.app.br")
        self.assertEqual(database.obter_precos_planos(), {"pro": 249.0})

        auditoria = database.listar_auditoria_financeira()
        self.assertEqual(auditoria[0]["tipo"], "preco_plano")
        self.assertEqual(auditoria[0]["campo"], "preco_mensal_brl:pro")
        self.assertEqual(auditoria[0]["valor_anterior"], "199.0")

    # ── listar_auditoria_financeira ──────────────

    def test_listar_auditoria_respeita_limit_e_ordem(self):
        for i in range(5):
            database.definir_orcamento_ia(float(i), "admin-1", "admin@saleia.app.br")
        r = database.listar_auditoria_financeira(limit=2)
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0]["valor_novo"], "4.0")  # mais recente primeiro


if __name__ == "__main__":
    unittest.main(verbosity=2)
