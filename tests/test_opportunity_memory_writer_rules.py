"""
Testes — Tarefa A3 (docs/tasks-prompt-mestre-v2-restante.md): escritor
de OpportunityMemory a partir dos fatos do ciclo (SPIN + objeções).

Persistência usa SQLite em memória (mesmo padrão de
tests/test_opportunity_memory.py) — nunca toca no banco real (o .env
local aponta DB_HOST para a VPS).

Run:
    python -m unittest tests.test_opportunity_memory_writer_rules -v
"""

import asyncio
import logging
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlmodel import SQLModel, create_engine

logging.disable(logging.CRITICAL)

import agent.multiagente.orquestrador as orquestrador
from agent.opportunity_memory_writer_rules import (
    gravar_opportunity_memory_do_ciclo,
    montar_insights_do_ciclo,
    opportunity_memory_write_ativo,
)
from api import database


def _spin(main_pain="leads esquecidos", quote_dor="A gente esquece os leads", impacto=None):
    implication = []
    if impacto:
        implication.append({"stage": "implication", "campo": "financial_impact", "valor": impacto[0],
                            "evidence_quote": impacto[1]})
    return {
        "situation": {"known": [
            {"stage": "situation", "campo": "team_size", "valor": "12", "evidence_quote": "Somos 12"},
        ], "missing": []},
        "problem": {"known": [
            {"stage": "problem", "campo": "main_pain", "valor": main_pain, "evidence_quote": quote_dor},
        ], "missing": []},
        "implication": {"known": implication, "missing": []},
        "need_payoff": {"known": [
            {"stage": "need_payoff", "campo": "solution_value", "valor": "fechar mais", "evidence_quote": "Queria fechar mais"},
        ], "missing": []},
    }


_OBJECOES = [{
    "objection_spoken": {"category": "PRICE", "evidence_quote": "Achei caro"},
    "root_cause_hypothesis": {"hypothesis": "ADOPTION_RISK", "confidence": 0.75,
                              "evidence_quote": "Minha equipe não vai usar"},
    "precisa_investigar": False,
}]


class MontarInsightsTest(unittest.TestCase):
    def test_mapeamento_spin_e_objecoes(self):
        insights = montar_insights_do_ciclo(_spin(impacto=("R$20.000/mês", "Perdemos uns 20 mil por mês")), _OBJECOES)
        self.assertEqual(
            [(i["categoria"], i["campo"], i["valor"]) for i in insights],
            [
                ("pain_points", "main_pain", "leads esquecidos"),
                ("business_impact", "financial_impact", "R$20.000/mês"),
                ("goals", "solution_value", "fechar mais"),
                ("objections", None, "PRICE"),
                ("objections", None, "ROOT_CAUSE:ADOPTION_RISK"),
            ],
        )

    def test_situation_nunca_e_gravado(self):
        categorias = {i["campo"] for i in montar_insights_do_ciclo(_spin())}
        self.assertNotIn("team_size", categorias)

    def test_evidencia_sempre_presente(self):
        for insight in montar_insights_do_ciclo(_spin(), _OBJECOES):
            self.assertTrue(insight["evidence"])

    def test_confidence_so_na_causa_raiz(self):
        por_valor = {i["valor"]: i for i in montar_insights_do_ciclo(objections=_OBJECOES)}
        self.assertNotIn("confidence", por_valor["PRICE"])
        self.assertEqual(por_valor["ROOT_CAUSE:ADOPTION_RISK"]["confidence"], 0.75)

    def test_entrada_vazia_ou_malformada_nunca_levanta(self):
        self.assertEqual(montar_insights_do_ciclo(), [])
        self.assertEqual(montar_insights_do_ciclo(
            spin_state={"problem": "lixo", "implication": {"known": ["lixo", {"campo": "financial_impact"}]}},
            objections=["lixo", {"objection_spoken": {"category": "PRICE"},
                                 "root_cause_hypothesis": {"hypothesis": "X", "confidence": "alta", "evidence_quote": "q"}}],
        ), [])


class KillSwitchTest(unittest.TestCase):
    def test_ligado_por_padrao(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPPORTUNITY_MEMORY_WRITE_ENABLED", None)
            self.assertTrue(opportunity_memory_write_ativo())

    def test_desligado_com_false(self):
        with patch.dict(os.environ, {"OPPORTUNITY_MEMORY_WRITE_ENABLED": "false"}):
            self.assertFalse(opportunity_memory_write_ativo())


class _ComBancoEmMemoria(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)
        env = patch.dict(os.environ, {"OPPORTUNITY_MEMORY_WRITE_ENABLED": "true"})
        env.start()
        self.addCleanup(env.stop)


class GravarOpportunityMemoryTest(_ComBancoEmMemoria):
    def test_duas_reunioes_acumulam_e_contradicao_nao_apaga(self):
        """Teste literal da Tarefa A3: 2 reuniões na mesma oportunidade →
        memória acumulada; valor divergente → `contradiz` preenchido,
        nada apagado."""
        r1 = gravar_opportunity_memory_do_ciclo(1, "m1", _spin(), _OBJECOES)
        r2 = gravar_opportunity_memory_do_ciclo(
            1, "m2", _spin(main_pain="follow-up lento", quote_dor="Nosso follow-up é lento",
                           impacto=("R$20.000/mês", "Perdemos uns 20 mil por mês")),
        )

        self.assertEqual(r1, {"criados": 4, "contradicoes": 0})
        self.assertEqual(r2, {"criados": 2, "contradicoes": 1})

        memoria = database.obter_opportunity_memory(1, criar_se_ausente=False)
        dores = memoria["pain_points"]
        self.assertEqual([d["valor"] for d in dores], ["leads esquecidos", "follow-up lento"])
        self.assertEqual([d["meeting_id"] for d in dores], ["m1", "m2"])
        self.assertIsNone(dores[0]["contradiz"])
        self.assertEqual(dores[1]["contradiz"], dores[0]["id"])
        self.assertEqual(len(memoria["business_impact"]), 1)
        self.assertEqual(len(memoria["objections"]), 2)
        self.assertEqual(len(memoria["goals"]), 1)

    def test_mesmo_fato_em_ciclos_seguidos_nao_duplica(self):
        gravar_opportunity_memory_do_ciclo(1, "m1", _spin(), _OBJECOES)
        r = gravar_opportunity_memory_do_ciclo(1, "m1", _spin(), _OBJECOES)
        self.assertEqual(r["criados"], 0)
        memoria = database.obter_opportunity_memory(1, criar_se_ausente=False)
        self.assertEqual(len(memoria["pain_points"]), 1)
        self.assertEqual(len(memoria["objections"]), 2)

    def test_mesma_fala_repetida_em_outra_reuniao_nao_duplica(self):
        gravar_opportunity_memory_do_ciclo(1, "m1", _spin())
        self.assertEqual(gravar_opportunity_memory_do_ciclo(1, "m2", _spin())["criados"], 0)

    def test_duas_objecoes_de_preco_diferentes_nao_sao_contradicao(self):
        outra = [{"objection_spoken": {"category": "PRICE", "evidence_quote": "Tá fora do orçamento"},
                  "root_cause_hypothesis": None}]
        gravar_opportunity_memory_do_ciclo(1, "m1", objections=_OBJECOES)
        r = gravar_opportunity_memory_do_ciclo(1, "m1", objections=outra)
        self.assertEqual(r, {"criados": 1, "contradicoes": 0})

    def test_sem_oportunidade_ou_reuniao_anonima_nao_grava(self):
        self.assertEqual(gravar_opportunity_memory_do_ciclo(None, "m1", _spin())["criados"], 0)
        self.assertEqual(gravar_opportunity_memory_do_ciclo(1, "default", _spin())["criados"], 0)
        self.assertEqual(gravar_opportunity_memory_do_ciclo(1, None, _spin())["criados"], 0)
        self.assertIsNone(database.obter_opportunity_memory(1, criar_se_ausente=False))

    def test_kill_switch_desligado_nao_grava(self):
        with patch.dict(os.environ, {"OPPORTUNITY_MEMORY_WRITE_ENABLED": "false"}):
            self.assertEqual(gravar_opportunity_memory_do_ciclo(1, "m1", _spin())["criados"], 0)
        self.assertIsNone(database.obter_opportunity_memory(1, criar_se_ausente=False))


class WiringOrquestradorTest(_ComBancoEmMemoria):
    def _rodar_shadow(self, opportunity_id, registrar=None):
        raciocinar_mock = AsyncMock(return_value=None)
        patches = [
            patch.dict(os.environ, {"SALES_EVIDENCE_PERSIST_ENABLED": "false"}),
            patch("agent.sales_reasoning_engine.raciocinar_async", new=raciocinar_mock),
            patch("api.database.criar_shadow_mode_comparison", new=MagicMock(return_value=None)),
            patch("api.database.obter_ultimo_ai_usage_event", return_value=None),
            patch("agent.opportunity_link_rules.vincular_automaticamente_se_possivel", return_value=opportunity_id),
            patch("agent.historical_pattern_rules.obter_historical_pattern_da_opportunity", return_value=None),
            patch("agent.spin_extractor.extrair_spin_state_async", new=AsyncMock(return_value=_spin())),
            patch("agent.behavioral_signal_extractor.extrair_sinais_comportamentais_async", new=AsyncMock(return_value=[])),
            patch("agent.buyer_motivation_extractor.extrair_buyer_motivation_async", new=AsyncMock(return_value=None)),
        ]
        if registrar is not None:
            patches.append(patch.object(database, "registrar_conhecimento_opportunity", new=registrar))
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

    def test_ciclo_grava_e_proximo_ciclo_le_a_memoria(self):
        primeiro = self._rodar_shadow(7)
        self.assertIsNone(primeiro.await_args.args[0]["opportunity_memory"])

        segundo = self._rodar_shadow(7)
        memoria_lida = segundo.await_args.args[0]["opportunity_memory"]
        self.assertEqual([d["valor"] for d in memoria_lida["pain_points"]], ["leads esquecidos"])
        self.assertEqual(len(memoria_lida["goals"]), 1)

    def test_sem_oportunidade_vinculada_nada_e_gravado(self):
        self._rodar_shadow(None)
        self.assertIsNone(database.obter_opportunity_memory(7, criar_se_ausente=False))

    def test_falha_de_gravacao_nunca_derruba_o_ciclo(self):
        raciocinar_mock = self._rodar_shadow(7, registrar=MagicMock(side_effect=RuntimeError("banco fora")))
        raciocinar_mock.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
