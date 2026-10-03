"""
Testes — Tarefa A4 (docs/tasks-prompt-mestre-v2-restante.md): escritor
de OpportunityGraph a partir da OpportunityMemory gravada pela A3.

Persistência usa SQLite em memória (mesmo padrão de
tests/test_opportunity_graph.py) — nunca toca no banco real (o .env
local aponta DB_HOST para a VPS).

Run:
    python -m unittest tests.test_opportunity_graph_writer_rules -v
"""

import asyncio
import logging
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlmodel import SQLModel, create_engine

logging.disable(logging.CRITICAL)

import agent.multiagente.orquestrador as orquestrador
from agent.opportunity_graph_writer_rules import (
    calcular_arestas,
    gravar_opportunity_graph,
    opportunity_graph_write_ativo,
)
from agent.opportunity_memory_writer_rules import gravar_opportunity_memory_do_ciclo
from api import database


def _insight(id_, valor, evidence, confidence=1.0, contradiz=None, campo=None):
    return {"id": id_, "meeting_id": "m1", "campo": campo, "valor": valor, "evidence": evidence,
            "confidence": confidence, "timestamp": "2026-09-30T10:00:00", "contradiz": contradiz}


def _memoria(**categorias):
    base = {c: [] for c in ("pain_points", "business_impact", "goals", "objections")}
    base.update(categorias)
    return base


def _spin_dor():
    return {"problem": {"known": [
        {"stage": "problem", "campo": "main_pain", "valor": "leads esquecidos",
         "evidence_quote": "A gente esquece os leads"},
    ], "missing": []}}


def _spin_impacto():
    return {"implication": {"known": [
        {"stage": "implication", "campo": "financial_impact", "valor": "R$20.000/mês",
         "evidence_quote": "Perdemos uns 20 mil por mês"},
    ], "missing": []}}


class CalcularArestasTest(unittest.TestCase):
    def test_regras_por_categoria(self):
        memoria = _memoria(
            pain_points=[_insight(1, "leads esquecidos", "A gente esquece os leads", 0.9)],
            business_impact=[_insight(1, "R$20.000/mês", "Perdemos uns 20 mil", 0.7)],
            goals=[_insight(1, "fechar mais", "Queria fechar mais")],
            objections=[_insight(1, "PRICE", "Achei caro")],
        )
        arestas = calcular_arestas(memoria, client_id="c1")
        self.assertEqual(
            [(a["from_type"], a["from_id"], a["relation"], a["to_type"], a["to_id"]) for a in arestas],
            [
                ("CLIENT", "c1", "sente", "PAIN", "1"),
                ("PAIN", "1", "causa", "IMPACT", "1"),
                ("PAIN", "1", "motiva", "GOAL", "1"),
                ("CLIENT", "c1", "levanta", "OBJECTION", "1"),
            ],
        )
        causa = arestas[1]
        self.assertEqual(causa["confidence"], 0.7)
        self.assertIn("A gente esquece os leads", causa["evidence"])
        self.assertIn("Perdemos uns 20 mil", causa["evidence"])
        self.assertEqual(causa["source"], "regra_memoria")

    def test_sem_client_id_nao_cria_no_client(self):
        memoria = _memoria(
            pain_points=[_insight(1, "dor", "q1")],
            objections=[_insight(1, "PRICE", "Achei caro")],
        )
        self.assertEqual(calcular_arestas(memoria, client_id=None), [])

    def test_dor_contradita_nao_ganha_aresta_nova(self):
        memoria = _memoria(
            pain_points=[_insight(1, "dor antiga", "q1", campo="main_pain"),
                         _insight(2, "dor nova", "q2", campo="main_pain", contradiz=1)],
            business_impact=[_insight(1, "impacto", "q3")],
        )
        causas = [a for a in calcular_arestas(memoria) if a["relation"] == "causa"]
        self.assertEqual([a["from_id"] for a in causas], ["2"])

    def test_causa_raiz_fica_fora(self):
        memoria = _memoria(objections=[_insight(1, "PRICE", "Achei caro"),
                                       _insight(2, "ROOT_CAUSE:ADOPTION_RISK", "Equipe não vai usar")])
        arestas = calcular_arestas(memoria, client_id="c1")
        self.assertEqual([a["to_id"] for a in arestas], ["1"])

    def test_insight_sem_evidencia_nao_vira_no(self):
        memoria = _memoria(pain_points=[_insight(1, "dor", "")], business_impact=[_insight(1, "x", "q")])
        self.assertEqual(calcular_arestas(memoria, client_id="c1"), [])

    def test_memoria_ausente_ou_malformada(self):
        self.assertEqual(calcular_arestas(None), [])
        self.assertEqual(calcular_arestas({"pain_points": ["lixo", {"valor": "sem id"}]}), [])


class KillSwitchTest(unittest.TestCase):
    def test_ligado_por_padrao(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPPORTUNITY_GRAPH_WRITE_ENABLED", None)
            self.assertTrue(opportunity_graph_write_ativo())

    def test_desligado_com_false(self):
        with patch.dict(os.environ, {"OPPORTUNITY_GRAPH_WRITE_ENABLED": "false"}):
            self.assertFalse(opportunity_graph_write_ativo())


class _ComBancoEmMemoria(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)
        env = patch.dict(os.environ, {
            "OPPORTUNITY_MEMORY_WRITE_ENABLED": "true", "OPPORTUNITY_GRAPH_WRITE_ENABLED": "true",
        })
        env.start()
        self.addCleanup(env.stop)
        self.opp = database.criar_opportunity(client_id="c1", seller_id="s1")


class GravarOpportunityGraphTest(_ComBancoEmMemoria):
    def test_exemplo_literal_da_fase_2_2_com_dado_do_ciclo(self):
        """Teste literal da Tarefa A4: reunião 1 identifica a dor,
        reunião 2 identifica o impacto; o grafo relaciona PAIN → causa →
        IMPACT sem perder a origem de nenhum dos dois."""
        opp_id = self.opp["id"]
        gravar_opportunity_memory_do_ciclo(opp_id, "m1", _spin_dor())
        gravar_opportunity_graph(opp_id)
        gravar_opportunity_memory_do_ciclo(opp_id, "m2", _spin_impacto())
        gravar_opportunity_graph(opp_id)

        memoria = database.obter_opportunity_memory(opp_id, criar_se_ausente=False)
        dor, impacto = memoria["pain_points"][0], memoria["business_impact"][0]
        self.assertEqual((dor["meeting_id"], impacto["meeting_id"]), ("m1", "m2"))

        causas = [a for a in database.listar_arestas_opportunity(opp_id) if a["relation"] == "causa"]
        self.assertEqual(len(causas), 1)
        self.assertEqual((causas[0]["from_type"], causas[0]["from_id"]), ("PAIN", str(dor["id"])))
        self.assertEqual((causas[0]["to_type"], causas[0]["to_id"]), ("IMPACT", str(impacto["id"])))
        self.assertIn("A gente esquece os leads", causas[0]["evidence"])
        self.assertIn("Perdemos uns 20 mil por mês", causas[0]["evidence"])

    def test_client_id_vem_da_oportunidade(self):
        gravar_opportunity_memory_do_ciclo(self.opp["id"], "m1", _spin_dor())
        gravar_opportunity_graph(self.opp["id"])
        arestas = database.listar_arestas_opportunity(self.opp["id"], node_type="CLIENT", node_id="c1")
        self.assertEqual([a["relation"] for a in arestas], ["sente"])

    def test_ciclos_repetidos_nao_duplicam(self):
        opp_id = self.opp["id"]
        gravar_opportunity_memory_do_ciclo(opp_id, "m1", {**_spin_dor(), **_spin_impacto()})
        primeiro = gravar_opportunity_graph(opp_id)
        segundo = gravar_opportunity_graph(opp_id)
        self.assertEqual((primeiro, segundo), (2, 0))
        self.assertEqual(len(database.listar_arestas_opportunity(opp_id)), 2)

    def test_dor_nova_contradizendo_mantem_arestas_antigas(self):
        opp_id = self.opp["id"]
        gravar_opportunity_memory_do_ciclo(opp_id, "m1", {**_spin_dor(), **_spin_impacto()})
        gravar_opportunity_graph(opp_id)
        outra_dor = {"problem": {"known": [
            {"stage": "problem", "campo": "main_pain", "valor": "follow-up lento",
             "evidence_quote": "Nosso follow-up é lento"},
        ], "missing": []}}
        gravar_opportunity_memory_do_ciclo(opp_id, "m2", outra_dor)
        gravar_opportunity_graph(opp_id)

        causas = [a for a in database.listar_arestas_opportunity(opp_id) if a["relation"] == "causa"]
        self.assertEqual([a["from_id"] for a in causas], ["1", "2"])

    def test_sem_oportunidade_sem_memoria_ou_kill_switch(self):
        self.assertEqual(gravar_opportunity_graph(None), 0)
        self.assertEqual(gravar_opportunity_graph(self.opp["id"]), 0)
        gravar_opportunity_memory_do_ciclo(self.opp["id"], "m1", _spin_dor())
        with patch.dict(os.environ, {"OPPORTUNITY_GRAPH_WRITE_ENABLED": "false"}):
            self.assertEqual(gravar_opportunity_graph(self.opp["id"]), 0)
        self.assertEqual(database.listar_arestas_opportunity(self.opp["id"]), [])


class WiringOrquestradorTest(_ComBancoEmMemoria):
    def _rodar_shadow(self, criar_aresta=None):
        raciocinar_mock = AsyncMock(return_value=None)
        spin = {**_spin_dor(), **_spin_impacto()}
        patches = [
            patch.dict(os.environ, {"SALES_EVIDENCE_PERSIST_ENABLED": "false", "MEDDPICC_EXTRACTOR_ENABLED": "false", "SALES_EVENT_EXTRACTOR_ENABLED": "false", "SELLER_CONTEXT_ENABLED": "false"}),
            patch("agent.sales_reasoning_engine.raciocinar_async", new=raciocinar_mock),
            patch("api.database.criar_shadow_mode_comparison", new=MagicMock(return_value=None)),
            patch("api.database.obter_ultimo_ai_usage_event", return_value=None),
            patch("agent.opportunity_link_rules.vincular_automaticamente_se_possivel", return_value=self.opp["id"]),
            patch("agent.historical_pattern_rules.obter_historical_pattern_da_opportunity", return_value=None),
            patch("agent.spin_extractor.extrair_spin_state_async", new=AsyncMock(return_value=spin)),
            patch("agent.behavioral_signal_extractor.extrair_sinais_comportamentais_async", new=AsyncMock(return_value=[])),
            patch("agent.buyer_motivation_extractor.extrair_buyer_motivation_async", new=AsyncMock(return_value=None)),
        ]
        if criar_aresta is not None:
            patches.append(patch.object(database, "criar_aresta_opportunity_graph", new=criar_aresta))
        for p in patches:
            p.start()
        try:
            asyncio.run(orquestrador._rodar_shadow_mode(
                recomendacao_atual={}, objecao_detectada=None,
                transcricao_parcial="t", historico="", resumo_vivo="",
                diagnostico_atual={}, mapa_financeiro={}, historico_scores=[], eventos=[],
                client_context="", usuario_id="seller-1", meeting_id="m1",
            ))
        finally:
            for p in reversed(patches):
                p.stop()
        return raciocinar_mock

    def test_ciclo_grava_e_proximo_ciclo_le_o_grafo(self):
        primeiro = self._rodar_shadow()
        self.assertEqual(primeiro.await_args.args[0]["opportunity_graph"], [])

        segundo = self._rodar_shadow()
        grafo_lido = segundo.await_args.args[0]["opportunity_graph"]
        self.assertEqual(sorted(a["relation"] for a in grafo_lido), ["causa", "sente"])

    def test_falha_do_grafo_nunca_derruba_o_ciclo(self):
        raciocinar_mock = self._rodar_shadow(criar_aresta=MagicMock(side_effect=RuntimeError("banco fora")))
        raciocinar_mock.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
