"""
Testes de agent/historical_pattern_rules.py — Bloco 2 / Tarefa 2.1 de
docs/tasks-sales-reasoning-engine-completo.md.

SQLite em memória (mesmo padrão de tests/test_opportunity_link_rules.py).

Run:
    python -m unittest tests.test_historical_pattern_rules -v
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlmodel import SQLModel, create_engine

from api import database
from agent import historical_pattern_rules as hpr
from agent.historical_pattern_rules import obter_historical_pattern_da_opportunity


class _SnapshotIsolado(unittest.TestCase):
    """Aponta o retrato da C5 para uma pasta temporária (o
    `data/efetividade_estrategias.json` real nunca entra no teste)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.snapshot = Path(self._tmp.name) / "efetividade_estrategias.json"
        p = patch.object(hpr, "SNAPSHOT_EFETIVIDADE_PATH", self.snapshot)
        p.start()
        self.addCleanup(p.stop)
        hpr._cache_snapshot.update({"mtime": None, "dados": None})


class ObterHistoricalPatternDaOpportunityTest(_SnapshotIsolado):
    def setUp(self):
        super().setUp()
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def _fechar(self, opportunity_id, status, **kwargs):
        if status == "won":
            database.atualizar_status_opportunity(
                opportunity_id, "won", None, value=1000.0, product="Plano Pro", **kwargs,
            )
        else:
            database.atualizar_status_opportunity(
                opportunity_id, "lost", "Sem orçamento", **kwargs,
            )

    def test_opportunity_inexistente_retorna_none(self):
        r = obter_historical_pattern_da_opportunity(999999)
        self.assertIsNone(r)

    def test_opportunity_sem_stage_retorna_none(self):
        opp = database.criar_opportunity(client_id="c1", seller_id="s1")
        r = obter_historical_pattern_da_opportunity(opp["id"])
        self.assertIsNone(r)

    def test_amostra_insuficiente_retorna_none(self):
        opp = database.criar_opportunity(client_id="c1", seller_id="s1", stage="negociacao")
        # so 1 oportunidade no estagio - bem abaixo do minimo de amostra
        r = obter_historical_pattern_da_opportunity(opp["id"])
        self.assertIsNone(r)

    def test_com_amostra_suficiente_retorna_insight_real(self):
        # 40 oportunidades no estagio "negociacao": 32 won, 8 lost (80%)
        for i in range(40):
            opp = database.criar_opportunity(client_id=f"c{i}", seller_id="s1", stage="negociacao")
            if i < 32:
                self._fechar(opp["id"], "won")
            else:
                self._fechar(opp["id"], "lost")

        opp_atual = database.criar_opportunity(client_id="c-atual", seller_id="s1", stage="negociacao")
        r = obter_historical_pattern_da_opportunity(opp_atual["id"])

        self.assertIsNotNone(r)
        self.assertIn("insight", r)
        self.assertEqual(r["evidence"]["valor"], "negociacao")
        # so as 40 fechadas contam — comparar_por_variavel_categorica()
        # (Fase 8) ignora oportunidades ainda abertas no agrupamento
        # won/lost, a atual (opp_atual, status="open") nunca entra.
        self.assertEqual(r["sample"], 40)

    def test_estagio_diferente_do_com_amostra_retorna_none(self):
        for i in range(40):
            opp = database.criar_opportunity(client_id=f"c{i}", seller_id="s1", stage="negociacao")
            self._fechar(opp["id"], "won")

        opp_atual = database.criar_opportunity(client_id="c-atual", seller_id="s1", stage="descoberta")
        r = obter_historical_pattern_da_opportunity(opp_atual["id"])
        self.assertIsNone(r)


def _resumo(usos, taxa_avanco, suficiente, desfecho=None):
    return {"usos": usos, "taxa_avanco": taxa_avanco, "amostra_avanco_suficiente": suficiente,
            "taxa_desfecho_positivo": desfecho, "amostra_desfecho_suficiente": False,
            "afirmacao": f"'x' foi usada {usos} vezes" if taxa_avanco is not None else None}


class EstrategiasComEfetividadeTest(_SnapshotIsolado):
    """C5: estratégias com efetividade medida entram no historical_patterns."""

    def test_sem_retrato_lista_vazia(self):
        self.assertEqual(hpr.estrategias_com_efetividade(), [])

    def test_so_entram_estrategias_com_amostra_suficiente(self):
        hpr.salvar_snapshot_efetividade({
            "SPIN": _resumo(40, 0.5, True, desfecho=0.3),
            "Challenger": _resumo(5, 1.0, False),
            "Ancoragem": _resumo(60, 0.4, True),
        }, total_eventos=105)
        estrategias = hpr.estrategias_com_efetividade()
        self.assertEqual([e["evidence"]["strategy"] for e in estrategias], ["Ancoragem", "SPIN"])
        self.assertEqual(estrategias[1]["evidence"]["taxa_avanco"], 0.5)
        self.assertEqual(estrategias[1]["evidence"]["taxa_desfecho_positivo"], 0.3)

    def test_kill_switch_desliga(self):
        hpr.salvar_snapshot_efetividade({"SPIN": _resumo(40, 0.5, True)}, total_eventos=40)
        with patch.dict(os.environ, {"ESTRATEGIAS_EFETIVAS_NO_MOTOR_ENABLED": "false"}):
            self.assertEqual(hpr.estrategias_com_efetividade(), [])

    def test_retrato_corrompido_nunca_quebra(self):
        self.snapshot.write_text("{nao é json", encoding="utf-8")
        self.assertEqual(hpr.estrategias_com_efetividade(), [])

    def test_historical_patterns_combina_win_loss_e_estrategias(self):
        hpr.salvar_snapshot_efetividade({"SPIN": _resumo(40, 0.5, True)}, total_eventos=40)
        with patch.object(hpr, "_win_loss_do_estagio", return_value=None):
            r = obter_historical_pattern_da_opportunity(1)
        self.assertIsNone(r["win_loss_do_estagio"])
        self.assertEqual(len(r["estrategias_com_efetividade"]), 1)
        self.assertIn("nunca causa", r["aviso"])

    def test_sem_estrategia_elegivel_formato_antigo(self):
        hpr.salvar_snapshot_efetividade({"SPIN": _resumo(5, 0.5, False)}, total_eventos=5)
        insight = {"insight": "x"}
        with patch.object(hpr, "_win_loss_do_estagio", return_value=insight):
            self.assertIs(obter_historical_pattern_da_opportunity(1), insight)


if __name__ == "__main__":
    unittest.main()
