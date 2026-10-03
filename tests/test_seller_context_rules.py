"""
Testes — Tarefa C2 (docs/tasks-prompt-mestre-v2-restante.md): SellerDNA
agregado ligado em `seller_context` do SalesReasoningEngine.

Persistência usa SQLite em memória — nunca toca no banco real (o .env
local aponta DB_HOST para a VPS).

Run:
    python -m unittest tests.test_seller_context_rules -v
"""

import asyncio
import logging
import os
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from sqlmodel import SQLModel, create_engine

logging.disable(logging.CRITICAL)

import agent.multiagente.orquestrador as orquestrador
from agent.seller_context_rules import obter_seller_context, seller_context_ativo
from api import database


def _observar(seller_id, n_reunioes, campo="question_patterns", valor="faz perguntas abertas sobre o processo"):
    for i in range(n_reunioes):
        database.criar_seller_dna_observacao(
            seller_id=seller_id, meeting_id=f"{seller_id}-m{i}", campo=campo,
            valor=valor, evidence_quote=f"citação {i}",
        )


class _ComBancoEmMemoria(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        p = patch.object(database, "engine", self._engine)
        p.start()
        self.addCleanup(p.stop)
        env = patch.dict(os.environ, {"SELLER_CONTEXT_ENABLED": "true"})
        env.start()
        self.addCleanup(env.stop)


class ObterSellerContextTest(_ComBancoEmMemoria):
    def test_sem_vendedor_ou_sem_observacoes(self):
        self.assertIsNone(obter_seller_context(None))
        self.assertIsNone(obter_seller_context("  "))
        self.assertIsNone(obter_seller_context("s1"))

    def test_abaixo_da_amostra_minima_fica_none(self):
        """Fase 15.1: nunca clonar personalidade de poucas conversas —
        9 reuniões distintas não bastam."""
        _observar("s1", 9)
        self.assertIsNone(obter_seller_context("s1"))

    def test_linhas_da_mesma_reuniao_nao_contam_como_reunioes(self):
        for campo in ("question_patterns", "opening_patterns", "closing_patterns"):
            for i in range(4):
                database.criar_seller_dna_observacao(
                    seller_id="s1", meeting_id=f"m{i}", campo=campo, valor=f"{campo} {i}", evidence_quote="q",
                )
        self.assertIsNone(obter_seller_context("s1"))  # 12 linhas, só 4 reuniões

    def test_com_amostra_suficiente_monta_o_perfil(self):
        _observar("s1", 10)
        database.criar_seller_dna_observacao(
            seller_id="s1", meeting_id="s1-m0", campo="opening_patterns",
            valor="abre falando do cenário do cliente", evidence_quote="q",
        )
        contexto = obter_seller_context("s1")
        self.assertEqual(contexto["seller_id"], "s1")
        self.assertEqual(contexto["n_reunioes_analisadas"], 10)
        self.assertEqual(contexto["campos"]["question_patterns"], ["faz perguntas abertas sobre o processo"])
        self.assertEqual(contexto["campos"]["opening_patterns"], ["abre falando do cenário do cliente"])
        self.assertIsNone(contexto["campos"]["pricing_style"])
        self.assertEqual(len(contexto["campos"]), 12)

    def test_observacoes_de_outro_vendedor_nao_contam(self):
        _observar("s2", 10)
        self.assertIsNone(obter_seller_context("s1"))

    def test_alegacao_de_eficacia_derruba_o_perfil_inteiro(self):
        """Fase 15.2: SellerDNA registra comportamento, nunca eficácia."""
        _observar("s1", 10)
        database.criar_seller_dna_observacao(
            seller_id="s1", meeting_id="s1-m1", campo="closing_patterns",
            valor="fecha com urgência, o que funciona sempre", evidence_quote="q",
        )
        self.assertIsNone(obter_seller_context("s1"))

    def test_kill_switch(self):
        _observar("s1", 10)
        with patch.dict(os.environ, {"SELLER_CONTEXT_ENABLED": "false"}):
            self.assertFalse(seller_context_ativo())
            self.assertIsNone(obter_seller_context("s1"))
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SELLER_CONTEXT_ENABLED", None)
            self.assertTrue(seller_context_ativo())


class PromptTest(unittest.TestCase):
    def test_prompt_do_motor_restringe_o_uso_do_seller_context(self):
        template = (Path(__file__).parent.parent / "agent" / "prompt_templates" / "sales_reasoning_engine.txt").read_text(encoding="utf-8")
        self.assertIn("{seller_context}", template)
        self.assertIn("nunca eficácia", template)


class WiringOrquestradorTest(_ComBancoEmMemoria):
    def _rodar_shadow(self, usuario_id="s1", listar=None):
        raciocinar_mock = AsyncMock(return_value=None)
        patches = [
            patch.dict(os.environ, {
                "SALES_EVIDENCE_PERSIST_ENABLED": "false", "OPPORTUNITY_MEMORY_WRITE_ENABLED": "false",
                "OPPORTUNITY_GRAPH_WRITE_ENABLED": "false", "MEDDPICC_EXTRACTOR_ENABLED": "false", "SALES_EVENT_EXTRACTOR_ENABLED": "false",
            }),
            patch("agent.sales_reasoning_engine.raciocinar_async", new=raciocinar_mock),
            patch("api.database.criar_shadow_mode_comparison", new=MagicMock(return_value=None)),
            patch("api.database.obter_ultimo_ai_usage_event", return_value=None),
            patch("agent.opportunity_link_rules.vincular_automaticamente_se_possivel", return_value=None),
            patch("agent.spin_extractor.extrair_spin_state_async", new=AsyncMock(return_value=None)),
            patch("agent.behavioral_signal_extractor.extrair_sinais_comportamentais_async", new=AsyncMock(return_value=[])),
            patch("agent.buyer_motivation_extractor.extrair_buyer_motivation_async", new=AsyncMock(return_value=None)),
        ]
        if listar is not None:
            patches.append(patch.object(database, "listar_seller_dna_observacoes", new=listar))
        for p in patches:
            p.start()
        try:
            asyncio.run(orquestrador._rodar_shadow_mode(
                recomendacao_atual={}, objecao_detectada=None,
                transcricao_parcial="t", historico="", resumo_vivo="",
                diagnostico_atual={}, mapa_financeiro={}, historico_scores=[], eventos=[],
                client_context="", usuario_id=usuario_id, meeting_id="m1",
            ))
        finally:
            for p in reversed(patches):
                p.stop()
        return raciocinar_mock

    def test_seller_context_real_na_entrada_do_motor(self):
        _observar("s1", 10)
        entrada = self._rodar_shadow().await_args.args[0]
        self.assertEqual(entrada["seller_context"]["n_reunioes_analisadas"], 10)

    def test_amostra_insuficiente_ou_anonimo_vira_none(self):
        _observar("s1", 3)
        self.assertIsNone(self._rodar_shadow().await_args.args[0]["seller_context"])
        self.assertIsNone(self._rodar_shadow(usuario_id=None).await_args.args[0]["seller_context"])

    def test_falha_de_banco_nunca_derruba_o_ciclo(self):
        raciocinar_mock = self._rodar_shadow(listar=MagicMock(side_effect=RuntimeError("banco fora")))
        raciocinar_mock.assert_awaited_once()
        self.assertIsNone(raciocinar_mock.await_args.args[0]["seller_context"])


if __name__ == "__main__":
    unittest.main()
