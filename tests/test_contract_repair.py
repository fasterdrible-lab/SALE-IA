"""
Testes — Tarefa D5 (docs/tasks-prompt-mestre-v2-restante.md, seção 29):
contract tests com reparo controlado. Resposta inválida de LLM →
rejeitar → reparar → registrar → fallback seguro; JSON quebrado nunca
chega à sidebar.

Cobre as 2 camadas (`agent/contract_repair_rules.py`): reparo sintático
no roteador (`api/ai_router.py::_extract_json`) e contrato da sidebar
no `/tempo-real` (`api/main.py::_aplicar_contrato_sidebar`), mais a
regressão do crash de `confidence` em texto em `_nba_para_nbq`.

Persistência em SQLite em memória — nunca toca no banco real.

Run:
    python -m unittest tests.test_contract_repair -v
"""

import copy
import itertools
import json
import logging
import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

logging.disable(logging.CRITICAL)

from agent.contract_repair_rules import (
    reparar_contrato_sidebar,
    reparar_json,
    reparar_next_best_action,
    violacoes_do_contrato_sidebar,
)
from api import ai_router, database
from api.processador_tempo_real import _fallback_next_best_action, _normalizar_resposta_realtime

_FALLBACK = _fallback_next_best_action()
_NBA_OK = {"type": "question", "category": "implicacao", "title": "Impacto", "message": "Quanto isso custa?",
           "objective": "quantificar", "reason": "dor sem número", "confidence": 0.8}


class RepararJsonTest(unittest.TestCase):
    def test_json_valido_nao_e_tocado(self):
        self.assertEqual(reparar_json('{"a": 1}'), ({"a": 1}, []))

    def test_texto_em_volta(self):
        obj, reparos = reparar_json('Claro! Aqui está: {"a": {"b": "x}y"}} Espero ter ajudado.')
        self.assertEqual(obj, {"a": {"b": "x}y"}})
        self.assertEqual(reparos, ["texto_em_volta"])

    def test_cerca_de_codigo_no_meio(self):
        obj, reparos = reparar_json('Segue o JSON:\n```json\n{"a": 1}\n```\nQualquer coisa me avise.')
        self.assertEqual(obj, {"a": 1})
        self.assertIn("cerca_de_codigo", reparos)

    def test_virgula_sobrando(self):
        obj, reparos = reparar_json('{"a": [1, 2,], "b": 3,}')
        self.assertEqual(obj, {"a": [1, 2], "b": 3})
        self.assertEqual(reparos, ["virgula_sobrando"])

    def test_sem_reparo_seguro_rejeita(self):
        for texto in ("isto nao e json", '{"a": 1', "[1, 2, 3]", "", None, '{"a": tru}'):
            self.assertEqual(reparar_json(texto), (None, []), texto)


class ExtractJsonNoRoteadorTest(unittest.TestCase):
    def test_reparo_registra_e_marca(self):
        antes = ai_router._counters["json_reparado"]
        obj = ai_router._extract_json('Resposta: {"message": "oi",}')
        self.assertEqual(obj["message"], "oi")
        self.assertEqual(obj["_json_reparado_ia"], ["texto_em_volta", "virgula_sobrando"])
        self.assertEqual(ai_router._counters["json_reparado"], antes + 1)

    def test_sem_reparo_propaga_o_erro_original(self):
        with self.assertRaises(ValueError):
            ai_router._extract_json("nada de json aqui")

    def test_provedor_com_json_quebrado_vira_falha_e_503(self):
        """Rejeitar → fallback: sem reparo possível, o provedor conta como
        falha e o roteador devolve 503 (o agente cai no fallback dele)."""
        ai_router.resetar_estado_ia_para_testes()
        self.addCleanup(ai_router.resetar_estado_ia_para_testes)

        def _caller(system_prompt, user_content, key, model, timeout):
            return ai_router._extract_json("desculpe, não consigo responder em JSON"), None

        provider = ai_router.Provider(name="deepseek", env_keys=("CR_FAKE_KEY",), model_env="CR_FAKE_MODEL",
                                      default_model="deepseek-chat", caller=_caller)
        with patch.dict(os.environ, {"CR_FAKE_KEY": "x", "OTIMIZACAO_CACHE_ATIVO": "false"}), \
             patch.object(ai_router, "_provider_order", return_value=[provider]), \
             patch.object(ai_router, "_registrar_evento_uso_ia_melhor_esforco"):
            with self.assertRaises(HTTPException) as ctx:
                ai_router.chamar_ia("s", "u", feature="realtime.coach")
        self.assertEqual(ctx.exception.status_code, 503)


class RepararNextBestActionTest(unittest.TestCase):
    def test_nba_valido_passa_sem_reparo(self):
        self.assertEqual(reparar_next_best_action(dict(_NBA_OK), _FALLBACK), (_NBA_OK, []))

    def test_campos_de_texto_com_tipo_errado(self):
        nba = {**_NBA_OK, "title": 3, "reason": ["ponto 1", "ponto 2"], "objective": {"x": 1}, "evite": True}
        reparado, reparos = reparar_next_best_action(nba, _FALLBACK)
        self.assertEqual(reparado["title"], "3")
        self.assertEqual(reparado["reason"], "ponto 1; ponto 2")
        self.assertIsNone(reparado["objective"])  # objeto descartado, nunca [object Object]
        self.assertIsNone(reparado["evite"])
        self.assertEqual(len(reparos), 4)

    def test_confidence(self):
        for bruto, esperado in (("alta", None), ("85%", 0.85), ("0,7", 0.7), (80, 0.8), (150, None),
                                (-1, None), (True, None), ({"v": 1}, None), (float("nan"), None), (0.3, 0.3)):
            reparado, _ = reparar_next_best_action({**_NBA_OK, "confidence": bruto}, _FALLBACK)
            self.assertEqual(reparado["confidence"], esperado, repr(bruto))

    def test_type_fora_do_vocabulario(self):
        reparado, reparos = reparar_next_best_action({**_NBA_OK, "type": "pergunta"}, _FALLBACK)
        self.assertEqual(reparado["type"], "insight")
        self.assertIn("next_best_action.type:fora_do_vocabulario", reparos)

    def test_sem_mensagem_utilizavel_cai_no_fallback(self):
        for nba in ({**_NBA_OK, "message": {"texto": "x"}}, {**_NBA_OK, "message": "   "}, "texto solto", None, []):
            reparado, reparos = reparar_next_best_action(nba, _FALLBACK)
            self.assertEqual(reparado, _FALLBACK)
            self.assertTrue(any("fallback_aplicado" in r for r in reparos))


class ContratoSidebarTest(unittest.TestCase):
    def test_campos_de_topo(self):
        resultado = {"next_best_action": dict(_NBA_OK), "alerta_urgente": {"nivel": "alto"},
                     "resumo_vivo": ["a", "b"], "perfil_disc": "D", "mapa_financeiro": ["x"],
                     "texto_falavel": 42}
        reparado, reparos = reparar_contrato_sidebar(resultado, _FALLBACK)
        self.assertIsNone(reparado["alerta_urgente"])
        self.assertEqual(reparado["resumo_vivo"], "a; b")
        self.assertEqual((reparado["perfil_disc"], reparado["mapa_financeiro"]), ({}, {}))
        self.assertEqual(reparado["texto_falavel"], "42")
        self.assertEqual(violacoes_do_contrato_sidebar(reparado), [])
        self.assertEqual(len(reparos), 5)

    def test_resultado_que_nao_e_objeto(self):
        reparado, reparos = reparar_contrato_sidebar("texto cru da IA", _FALLBACK)
        self.assertEqual(reparado["next_best_action"], _FALLBACK)
        self.assertEqual(violacoes_do_contrato_sidebar(reparado), [])

    def test_combinacoes_de_valores_ruins_nunca_violam_o_contrato(self):
        """Contract test: todo valor ruim em todo campo sai sem violação."""
        ruins = [None, 0, 1.5, True, "", "texto", [], ["a", 1], {"x": 1}, float("nan")]
        campos = ["message", "title", "category", "reason", "confidence", "type"]
        for campo, valor in itertools.product(campos, ruins):
            resultado = {"next_best_action": {**_NBA_OK, campo: copy.deepcopy(valor)},
                         "alerta_urgente": copy.deepcopy(valor), "resumo_vivo": copy.deepcopy(valor)}
            reparado, _ = reparar_contrato_sidebar(resultado, _FALLBACK)
            self.assertEqual(violacoes_do_contrato_sidebar(reparado), [], f"{campo}={valor!r}")
            json.dumps(reparado)  # sempre serializável


class NormalizacaoRegressaoTest(unittest.TestCase):
    def test_confidence_em_texto_nao_quebra_mais_o_ciclo(self):
        """Antes: `_nba_para_nbq` comparava 'alta' >= 0.8 e levantava
        TypeError no meio do ciclo."""
        resultado = _normalizar_resposta_realtime({"next_best_action": {**_NBA_OK, "confidence": "alta"}}, None, {})
        self.assertIsNone(resultado["next_best_action"]["confidence"])
        self.assertEqual(resultado["next_best_question"]["question"], _NBA_OK["message"])
        self.assertIn("next_best_action.confidence:texto_nao_numerico", resultado["_reparos_contrato"])


class _FakeSessaoConn:
    def cursor(self):
        return self

    def execute(self, *a, **k):
        pass

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def commit(self):
        pass

    def close(self):
        pass


class TempoRealContratoEndpointTest(unittest.TestCase):
    """Contract test no ponto único de saída para a extensão: qualquer que
    seja o resultado do processador, a resposta cumpre o contrato e o
    reparo fica registrado."""

    @classmethod
    def setUpClass(cls):
        import api.main as _main
        cls._patches = []
        for target in ("api.database.criar_tabelas", "agent.sessao_manager.criar_tabela_sessoes",
                       "agent.sessao_manager.criar_tabela_usuarios", "agent.visual_scenario.criar_tabela_visual_scenarios",
                       "agent.sales_memory.criar_tabela_sales_memories"):
            try:
                p = patch(target)
                p.start()
                cls._patches.append(p)
            except Exception:
                pass
        from fastapi.testclient import TestClient
        cls._ctx = TestClient(_main.app)
        cls.client = cls._ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)
        for p in cls._patches:
            p.stop()

    def setUp(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)
        for p in (patch.object(database, "engine", engine),
                  patch("agent.sessao_manager._get_conn", return_value=_FakeSessaoConn()),
                  patch.dict(os.environ, {"DB_HOST": "127.0.0.1", "DB_PORT": "1"})):
            p.start()
            self.addCleanup(p.stop)

    def _tempo_real(self, resultado_processador):
        with patch("api.processador_tempo_real.processar_fragmento_tempo_real",
                   new=AsyncMock(return_value=resultado_processador)):
            r = self.client.post("/tempo-real", json={"transcricao_parcial": "Cliente: oi", "meeting_id": "cr-m1"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_respostas_malformadas_nunca_chegam_quebradas(self):
        casos = [
            {"next_best_action": {**_NBA_OK, "message": {"texto": "x"}}},
            {"next_best_action": {**_NBA_OK, "confidence": "alta", "title": ["a", "b"]}},
            {"next_best_action": "texto solto", "alerta_urgente": {"x": 1}},
            {"alerta_urgente": ["cuidado", "agora"], "perfil_disc": "D", "mapa_financeiro": None},
            None,
            "string crua da IA",
        ]
        for caso in casos:
            dados = self._tempo_real(copy.deepcopy(caso))
            self.assertEqual(violacoes_do_contrato_sidebar(dados), [], repr(caso))
            self.assertEqual(dados["next_best_question"]["question"], dados["next_best_action"]["message"])
            self.assertIn("auth_status", dados)

    def test_reparo_e_registrado_na_auditoria(self):
        self._tempo_real({"next_best_action": {**_NBA_OK, "message": None}})
        entradas = database.listar_audit_trail_entries(actor="contract_guard")
        self.assertEqual(len(entradas), 1)
        self.assertEqual(entradas[0]["result"], "fallback_aplicado")
        self.assertEqual(entradas[0]["meeting_id"], "cr-m1")
        self.assertIn("next_best_action.message:vazio:fallback_aplicado", entradas[0]["data_used"]["reparos"])

    def test_resposta_valida_nao_e_tocada_nem_registrada(self):
        dados = self._tempo_real({"next_best_action": dict(_NBA_OK), "alerta_urgente": "Cliente esfriou"})
        self.assertEqual(dados["next_best_action"], _NBA_OK)
        self.assertEqual(dados["alerta_urgente"], "Cliente esfriou")
        self.assertEqual(database.listar_audit_trail_entries(actor="contract_guard"), [])

    def test_reparos_da_normalizacao_chegam_ao_registro_e_saem_da_resposta(self):
        dados = self._tempo_real({"next_best_action": dict(_NBA_OK),
                                  "_reparos_contrato": ["next_best_action.confidence:texto_nao_numerico"]})
        self.assertNotIn("_reparos_contrato", dados)
        entradas = database.listar_audit_trail_entries(actor="contract_guard")
        self.assertEqual(entradas[0]["result"], "reparado")


if __name__ == "__main__":
    unittest.main()
