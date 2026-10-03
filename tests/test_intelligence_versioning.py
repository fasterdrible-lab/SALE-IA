"""
Testes — Tarefa D6 (docs/tasks-prompt-mestre-v2-restante.md, seção 34):
versionamento completo da inteligência em RecommendationEvent e
AuditTrailEntry (`agent/intelligence_version_rules.py`, colunas novas,
migração no startup, wiring no motor e no rastreamento de recomendação).

Persistência usa SQLite em memória — nunca toca no banco real.

Run:
    python -m unittest tests.test_intelligence_versioning -v
"""

import asyncio
import logging
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, inspect
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

logging.disable(logging.CRITICAL)

from agent import intelligence_version_rules as versionamento
from agent.intelligence_version_rules import (
    ORIGEM_MOTOR,
    ORIGEM_MULTIAGENTE,
    model_version,
    policy_version,
    reasoning_engine_version,
    versao_de_conteudo,
    versoes_da_inteligencia,
)
from api import database


class _ComBancoEmMemoria(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                                     poolclass=StaticPool)
        SQLModel.metadata.create_all(self._engine)
        p = patch.object(database, "engine", self._engine)
        p.start()
        self.addCleanup(p.stop)
        versionamento.resetar_cache_para_testes()
        self.addCleanup(versionamento.resetar_cache_para_testes)


class VersaoDeConteudoTest(unittest.TestCase):
    def setUp(self):
        versionamento.resetar_cache_para_testes()

    def test_formato_e_estabilidade(self):
        v = versao_de_conteudo("x", "a", "b")
        self.assertRegex(v, r"^x@[0-9a-f]{10}$")
        self.assertEqual(v, versao_de_conteudo("x", "a", "b"))
        self.assertNotEqual(v, versao_de_conteudo("x", "a", "c"))
        self.assertNotEqual(versao_de_conteudo("x", "ab", ""), versao_de_conteudo("x", "a", "b"))

    def test_motor_e_multiagente_tem_versoes_distintas(self):
        motor, multi = reasoning_engine_version(ORIGEM_MOTOR), reasoning_engine_version(ORIGEM_MULTIAGENTE)
        self.assertTrue(motor.startswith("sales_reasoning_engine@"))
        self.assertTrue(multi.startswith("multiagente@"))

    def test_versao_do_motor_muda_quando_o_prompt_muda(self):
        """A versão sai do conteúdo — mudar o prompt muda a versão sem
        ninguém lembrar de mexer num número."""
        antes = reasoning_engine_version(ORIGEM_MOTOR)
        versionamento.resetar_cache_para_testes()
        with patch.object(versionamento, "_ler", return_value="prompt alterado"):
            depois = reasoning_engine_version(ORIGEM_MOTOR)
        self.assertNotEqual(antes, depois)

    def test_versao_de_politica_muda_com_a_guarda(self):
        antes = policy_version()
        versionamento.resetar_cache_para_testes()
        with patch("agent.prompt_injection_rules.PROMPT_INJECTION_GUARD_TEXT", "guarda nova"):
            depois = policy_version()
        self.assertTrue(antes.startswith("policy@"))
        self.assertNotEqual(antes, depois)

    def test_model_version(self):
        self.assertEqual(model_version("deepseek", "deepseek-chat"), "deepseek/deepseek-chat")
        self.assertIsNone(model_version(None, None))


class KnowledgeVersionTest(_ComBancoEmMemoria):
    def _item(self, status):
        from sqlmodel import Session
        with Session(self._engine) as s:
            s.add(database.KnowledgeItem(source_id=1, item_type="FRAMEWORK", title="t", content="c", status=status))
            s.commit()

    def test_so_itens_aprovados_mudam_a_versao(self):
        vazia = versionamento.knowledge_version(agora=0)
        versionamento.resetar_cache_para_testes()
        self._item("DRAFT")
        self.assertEqual(versionamento.knowledge_version(agora=0), vazia)
        versionamento.resetar_cache_para_testes()
        self._item("APPROVED")
        self.assertNotEqual(versionamento.knowledge_version(agora=0), vazia)

    def test_cache_de_5_minutos(self):
        v1 = versionamento.knowledge_version(agora=1000)
        self._item("APPROVED")
        self.assertEqual(versionamento.knowledge_version(agora=1100), v1)   # ainda no cache
        self.assertNotEqual(versionamento.knowledge_version(agora=1400), v1)  # expirou

    def test_falha_de_banco_vira_none(self):
        with patch("sqlmodel.Session", side_effect=RuntimeError("banco fora")):
            self.assertIsNone(versionamento.knowledge_version(agora=0))


class VersoesDaInteligenciaTest(_ComBancoEmMemoria):
    def test_model_version_da_ultima_chamada_da_feature(self):
        database.registrar_evento_uso_ia(feature="realtime.coach", provider="deepseek", model="deepseek-chat",
                                          input_tokens=1, output_tokens=1, usage_source="provider",
                                          cost_usd=0.0, success=True, meeting_id="m1")
        v = versoes_da_inteligencia(ORIGEM_MULTIAGENTE, feature="realtime.coach", meeting_id="m1")
        self.assertEqual(set(v), set(database.VERSOES_INTELIGENCIA))
        self.assertEqual(v["model_version"], "deepseek/deepseek-chat")
        self.assertIsNone(versoes_da_inteligencia(feature="realtime.coach", meeting_id="outra")["model_version"])

    def test_uma_versao_que_falha_nao_derruba_as_outras(self):
        with patch.object(versionamento, "policy_version", side_effect=RuntimeError("x")):
            v = versoes_da_inteligencia(ORIGEM_MOTOR, provider="openai", model="gpt-4o")
        self.assertIsNone(v["policy_version"])
        self.assertTrue(v["reasoning_engine_version"].startswith("sales_reasoning_engine@"))
        self.assertEqual(v["model_version"], "openai/gpt-4o")


class PersistenciaTest(_ComBancoEmMemoria):
    _V = {"reasoning_engine_version": "multiagente@abc", "policy_version": "policy@def",
          "knowledge_version": "knowledge@123", "model_version": "deepseek/deepseek-chat"}

    def test_recommendation_event_e_audit_gravam_as_4_versoes(self):
        ev = database.criar_recommendation_event(meeting_id="m1", strategy="s", recommendation="r", reason="x",
                                                 versoes={**self._V, "chave_invalida": "ignorada"})
        audit = database.criar_audit_trail_entry(actor="a", action="b", reason="c", result="d", versoes=self._V)
        for registro in (ev, audit):
            for chave, valor in self._V.items():
                self.assertEqual(registro[chave], valor)
        self.assertNotIn("chave_invalida", ev)

    def test_sem_versoes_continua_funcionando(self):
        ev = database.criar_recommendation_event(meeting_id="m1", strategy="s", recommendation="r", reason="x")
        self.assertIsNone(ev["policy_version"])

    def test_versao_longa_e_cortada_no_tamanho_da_coluna(self):
        ev = database.criar_recommendation_event(meeting_id="m1", strategy="s", recommendation="r", reason="x",
                                                 versoes={"model_version": "x" * 200})
        self.assertEqual(len(ev["model_version"]), 80)


class MigracaoTest(unittest.TestCase):
    def test_adiciona_colunas_que_faltam_e_e_idempotente(self):
        """Banco de produção já tem as tabelas sem as colunas novas —
        `create_all()` não migra; `migrar_colunas_versionamento()` sim."""
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        meta = MetaData()
        Table("recommendation_events", meta, Column("id", Integer, primary_key=True), Column("meeting_id", String(200)),
              Column("strategy", String(120)), Column("recommendation", Text), Column("reason", Text),
              Column("shown_at", DateTime), Column("created_at", DateTime))
        Table("audit_trail_entries", meta, Column("id", Integer, primary_key=True), Column("actor", String(120)))
        meta.create_all(engine)

        with patch.object(database, "engine", engine):
            adicionadas = database.migrar_colunas_versionamento()
            self.assertEqual(len(adicionadas), 8)
            self.assertEqual(database.migrar_colunas_versionamento(), [])

        for tabela in ("recommendation_events", "audit_trail_entries"):
            colunas = {c["name"] for c in inspect(engine).get_columns(tabela)}
            self.assertTrue(set(database.VERSOES_INTELIGENCIA) <= colunas)


class WiringTest(_ComBancoEmMemoria):
    def test_rastreamento_grava_versoes_do_multiagente(self):
        from agent.multiagente.orquestrador import _rastrear_recomendacao
        database.registrar_evento_uso_ia(feature="realtime.coach", provider="deepseek", model="deepseek-chat",
                                          input_tokens=1, output_tokens=1, usage_source="provider",
                                          cost_usd=0.0, success=True, meeting_id="m1")
        asyncio.run(_rastrear_recomendacao(
            {"next_best_action": {"message": "Pergunte o impacto.", "category": "c", "reason": "r"}}, "", "m1",
        ))
        ev = database.listar_recommendation_events(meeting_id="m1")[0]
        self.assertTrue(ev["reasoning_engine_version"].startswith("multiagente@"))
        self.assertTrue(ev["policy_version"].startswith("policy@"))
        self.assertTrue(ev["knowledge_version"].startswith("knowledge@"))
        self.assertEqual(ev["model_version"], "deepseek/deepseek-chat")

    def test_rastreamento_com_piloto_aplicado_usa_versao_do_motor(self):
        from agent.multiagente.orquestrador import _rastrear_recomendacao
        asyncio.run(_rastrear_recomendacao(
            {"next_best_action": {"message": "Pergunte o impacto.", "category": "c", "reason": "r"}}, "", "m1",
            origem=ORIGEM_MOTOR,
        ))
        ev = database.listar_recommendation_events(meeting_id="m1")[0]
        self.assertTrue(ev["reasoning_engine_version"].startswith("sales_reasoning_engine@"))

    def test_audit_do_motor_grava_versoes(self):
        from agent.sales_reasoning_engine import raciocinar_async
        resposta = {
            "current_state": "x", "recommended_framework": "SPIN_PROBLEM", "next_best_action": "y",
            "reason": "z", "confidence": 0.5, "hypotheses": [], "evidence": [], "missing_information": [],
            "avoid": [], "next_best_question": None, "_provedor_ia": "anthropic", "_modelo_ia": "claude-sonnet-4-6",
        }
        with patch("agent.sales_reasoning_engine.chamar_ia_com_fallback_claude", new=AsyncMock(return_value=resposta)):
            asyncio.run(raciocinar_async({}, meeting_id="m1"))
        audit = database.listar_audit_trail_entries()[0]
        self.assertTrue(audit["reasoning_engine_version"].startswith("sales_reasoning_engine@"))
        self.assertEqual(audit["model_version"], "anthropic/claude-sonnet-4-6")
        self.assertTrue(audit["policy_version"].startswith("policy@"))


if __name__ == "__main__":
    unittest.main()
