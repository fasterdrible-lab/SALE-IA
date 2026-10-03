"""
Testes — Tarefa A5 (docs/tasks-prompt-mestre-v2-restante.md): extrator
de MEDDPICC via IA (mockada — nunca chama provedor real) + integração
com A2 (SalesEvidence), A3 (OpportunityMemory) e o orquestrador.

Run:
    python -m unittest tests.test_meddpicc_extractor -v
"""

import asyncio
import logging
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlmodel import SQLModel, create_engine

logging.disable(logging.CRITICAL)

import agent.multiagente.orquestrador as orquestrador
from agent.meddpicc_extractor import estado_meddpicc, extrair_fatos_meddpicc_async, meddpicc_extractor_ativo
from agent.opportunity_memory_writer_rules import gravar_opportunity_memory_do_ciclo, montar_insights_do_ciclo
from agent.sales_evidence_persist_rules import coletar_evidencias
from api import ai_features, database

_HISTORICO = "Vendedor: quem aprova esse tipo de compra aí?"
_TRANSCRICAO = (
    "Cliente: quem assina é o nosso CFO, o Marcos. "
    "Cliente: a gente também tá olhando o Pipedrive. "
    "Cliente: a Juliana, do comercial, é quem mais tá empurrando isso aqui dentro."
)


def _fato(item, valor, quote, status="CONFIRMED", confidence=0.9):
    return {"item": item, "status": status, "valor": valor, "confidence": confidence, "evidence_quote": quote}


def _rodar(resposta):
    ia = AsyncMock(return_value=resposta)
    with patch("agent.meddpicc_extractor.chamar_ia_com_fallback_claude", new=ia):
        fatos = asyncio.run(extrair_fatos_meddpicc_async(_TRANSCRICAO, _HISTORICO, usuario_id="s1", meeting_id="m1"))
    return fatos, ia


class ExtrairFatosTest(unittest.TestCase):
    def test_extrai_fatos_validos(self):
        fatos, _ = _rodar({"fatos": [
            _fato("economic_buyer", "CFO Marcos", "quem assina é o nosso CFO, o Marcos"),
            _fato("competition", "Pipedrive", "a gente também tá olhando o Pipedrive", "PARTIAL", 0.7),
        ]})
        self.assertEqual([f["item"] for f in fatos], ["economic_buyer", "competition"])
        self.assertEqual(fatos[0]["valor"], "CFO Marcos")

    def test_citacao_fabricada_e_descartada(self):
        """Teste literal da Tarefa A5: guarda contra citação fabricada."""
        fatos, _ = _rodar({"fatos": [
            _fato("economic_buyer", "CFO Marcos", "quem assina é o nosso CFO, o Marcos"),
            _fato("champion", "Juliana", "a Juliana é nossa grande defensora"),  # nunca foi dito
            _fato("metrics", "dobrar conversão", "queremos dobrar a conversão"),  # nunca foi dito
        ]})
        self.assertEqual([f["item"] for f in fatos], ["economic_buyer"])

    def test_vocabulario_fechado_status_e_confidence(self):
        fatos, _ = _rodar({"fatos": [
            _fato("budget", "x", "quem assina é o nosso CFO, o Marcos"),               # item fora dos 8
            _fato("champion", "Juliana", "a Juliana, do comercial", "UNKNOWN"),         # UNKNOWN não é fato
            _fato("champion", "Juliana", "a Juliana, do comercial", "CONFIRMED", 1.5),  # confidence fora
            _fato("champion", "", "a Juliana, do comercial"),                           # sem valor
            _fato("champion", "Juliana", "a Juliana, do comercial", "CONFIRMED", 0.8),
        ]})
        self.assertEqual(len(fatos), 1)
        self.assertEqual(fatos[0]["confidence"], 0.8)

    def test_item_repetido_mantem_o_primeiro(self):
        fatos, _ = _rodar({"fatos": [
            _fato("competition", "Pipedrive", "a gente também tá olhando o Pipedrive"),
            _fato("competition", "outro", "quem assina é o nosso CFO, o Marcos"),
        ]})
        self.assertEqual([f["valor"] for f in fatos], ["Pipedrive"])

    def test_resposta_vazia_ou_malformada(self):
        self.assertEqual(_rodar({"fatos": []})[0], [])
        self.assertEqual(_rodar({})[0], [])
        self.assertEqual(_rodar(None)[0], [])
        self.assertEqual(_rodar({"fatos": ["lixo", 3, None]})[0], [])

    def test_custo_atribuido_a_feature_propria(self):
        """O custo de cada chamada fica medido em `ai_usage_events` sob a
        feature `meddpicc.extracao` (medição real só com tráfego)."""
        _, ia = _rodar({"fatos": []})
        self.assertEqual(ia.await_args.kwargs["feature"], ai_features.MEDDPICC_EXTRACAO)
        self.assertEqual(ia.await_args.kwargs["meeting_id"], "m1")
        prompt = ia.await_args.args[1]
        self.assertIn(_TRANSCRICAO, prompt)
        self.assertIn(_HISTORICO, prompt)

    def test_falha_de_ia_propaga(self):
        with patch("agent.meddpicc_extractor.chamar_ia_com_fallback_claude", new=AsyncMock(side_effect=RuntimeError("503"))):
            with self.assertRaises(RuntimeError):
                asyncio.run(extrair_fatos_meddpicc_async(_TRANSCRICAO, _HISTORICO))

    def test_estado_usa_calcular_qualificacao(self):
        estado = estado_meddpicc([_fato("economic_buyer", "CFO Marcos", "quem assina é o nosso CFO, o Marcos")])
        self.assertEqual(estado["economic_buyer"]["status"], "CONFIRMED")
        self.assertEqual(estado["champion"]["status"], "UNKNOWN")
        self.assertEqual(len(estado), 8)
        self.assertEqual(estado_meddpicc([])["metrics"]["status"], "UNKNOWN")


class KillSwitchTest(unittest.TestCase):
    def test_ligado_por_padrao(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MEDDPICC_EXTRACTOR_ENABLED", None)
            self.assertTrue(meddpicc_extractor_ativo())

    def test_desligado_com_false(self):
        with patch.dict(os.environ, {"MEDDPICC_EXTRACTOR_ENABLED": "false", "SALES_EVENT_EXTRACTOR_ENABLED": "false", "SELLER_CONTEXT_ENABLED": "false"}):
            self.assertFalse(meddpicc_extractor_ativo())


class IntegracaoA2A3Test(unittest.TestCase):
    def test_a2_grava_evidencia_meddpicc(self):
        evidencias = coletar_evidencias(meddpicc_fatos=[
            _fato("economic_buyer", "CFO Marcos", "quem assina é o nosso CFO, o Marcos", confidence=0.85),
        ])
        self.assertEqual(evidencias, [{
            "type": "MEDDPICC:economic_buyer", "quote": "quem assina é o nosso CFO, o Marcos", "confidence": 0.85,
        }])

    def test_a3_mapeia_itens_para_categorias(self):
        fatos = [
            _fato("metrics", "dobrar conversão", "q1"),
            _fato("economic_buyer", "CFO Marcos", "q2"),
            _fato("champion", "Juliana", "q3"),
            _fato("decision_process", "diretoria semana que vem", "q4"),
            _fato("paper_process", "jurídico revisa contrato", "q5"),
            _fato("decision_criteria", "integração com ERP", "q6"),
            _fato("competition", "Pipedrive", "q7"),
            _fato("identify_pain", "leads esquecidos", "q8"),
        ]
        insights = montar_insights_do_ciclo(meddpicc_fatos=fatos)
        self.assertEqual(
            [(i["categoria"], i["campo"]) for i in insights],
            [
                ("metrics", None),
                ("economic_buyer", "economic_buyer"),
                ("champion", "champion"),
                ("decision_process", "decision_process"),
                ("decision_process", "paper_process"),
                ("decision_process", None),
                ("competitors", None),
            ],
        )
        self.assertTrue(all(i["confidence"] == 0.9 for i in insights))


class IntegracaoA3BancoTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        p = patch.object(database, "engine", self._engine)
        p.start()
        self.addCleanup(p.stop)
        env = patch.dict(os.environ, {"OPPORTUNITY_MEMORY_WRITE_ENABLED": "true"})
        env.start()
        self.addCleanup(env.stop)

    def test_outro_decisor_em_reuniao_seguinte_vira_contradicao(self):
        gravar_opportunity_memory_do_ciclo(1, "m1", meddpicc_fatos=[_fato("economic_buyer", "CFO Marcos", "q1")])
        r = gravar_opportunity_memory_do_ciclo(1, "m2", meddpicc_fatos=[_fato("economic_buyer", "CEO Ana", "q2")])
        self.assertEqual(r, {"criados": 1, "contradicoes": 1})
        decisores = database.obter_opportunity_memory(1, criar_se_ausente=False)["economic_buyer"]
        self.assertEqual([d["valor"] for d in decisores], ["CFO Marcos", "CEO Ana"])
        self.assertEqual(decisores[1]["contradiz"], decisores[0]["id"])


class WiringOrquestradorTest(unittest.TestCase):
    def _rodar_shadow(self, meddpicc_ia, env=None):
        raciocinar_mock = AsyncMock(return_value=None)
        patches = [
            patch.dict(os.environ, {
                "SALES_EVIDENCE_PERSIST_ENABLED": "false", "OPPORTUNITY_MEMORY_WRITE_ENABLED": "false",
                "OPPORTUNITY_GRAPH_WRITE_ENABLED": "false", "MEDDPICC_EXTRACTOR_ENABLED": "true", "SALES_EVENT_EXTRACTOR_ENABLED": "false", "SELLER_CONTEXT_ENABLED": "false", **(env or {}),
            }),
            patch("agent.sales_reasoning_engine.raciocinar_async", new=raciocinar_mock),
            patch("api.database.criar_shadow_mode_comparison", new=MagicMock(return_value=None)),
            patch("api.database.obter_ultimo_ai_usage_event", return_value=None),
            patch("agent.opportunity_link_rules.vincular_automaticamente_se_possivel", return_value=None),
            patch("agent.spin_extractor.extrair_spin_state_async", new=AsyncMock(return_value=None)),
            patch("agent.behavioral_signal_extractor.extrair_sinais_comportamentais_async", new=AsyncMock(return_value=[])),
            patch("agent.buyer_motivation_extractor.extrair_buyer_motivation_async", new=AsyncMock(return_value=None)),
            patch("agent.meddpicc_extractor.chamar_ia_com_fallback_claude", new=meddpicc_ia),
        ]
        for p in patches:
            p.start()
        try:
            asyncio.run(orquestrador._rodar_shadow_mode(
                recomendacao_atual={}, objecao_detectada=None,
                transcricao_parcial=_TRANSCRICAO, historico=_HISTORICO, resumo_vivo="",
                diagnostico_atual={}, mapa_financeiro={}, historico_scores=[], eventos=[],
                client_context="", usuario_id="s1", meeting_id="m1",
            ))
        finally:
            for p in reversed(patches):
                p.stop()
        return raciocinar_mock

    def test_meddpicc_state_real_na_entrada_do_motor(self):
        ia = AsyncMock(return_value={"fatos": [
            _fato("economic_buyer", "CFO Marcos", "quem assina é o nosso CFO, o Marcos"),
        ]})
        entrada = self._rodar_shadow(ia).await_args.args[0]
        self.assertEqual(entrada["meddpicc_state"]["economic_buyer"]["status"], "CONFIRMED")
        self.assertEqual(entrada["meddpicc_state"]["economic_buyer"]["evidence"],
                         ["quem assina é o nosso CFO, o Marcos"])

    def test_nada_qualificado_ainda_vira_estado_todo_unknown(self):
        entrada = self._rodar_shadow(AsyncMock(return_value={"fatos": []})).await_args.args[0]
        self.assertEqual({v["status"] for v in entrada["meddpicc_state"].values()}, {"UNKNOWN"})

    def test_falha_de_ia_nunca_derruba_o_ciclo(self):
        raciocinar_mock = self._rodar_shadow(AsyncMock(side_effect=RuntimeError("503")))
        raciocinar_mock.assert_awaited_once()
        self.assertIsNone(raciocinar_mock.await_args.args[0]["meddpicc_state"])

    def test_kill_switch_desligado_nao_chama_ia(self):
        ia = AsyncMock(return_value={"fatos": []})
        raciocinar_mock = self._rodar_shadow(ia, env={"MEDDPICC_EXTRACTOR_ENABLED": "false", "SALES_EVENT_EXTRACTOR_ENABLED": "false", "SELLER_CONTEXT_ENABLED": "false"})
        ia.assert_not_awaited()
        self.assertIsNone(raciocinar_mock.await_args.args[0]["meddpicc_state"])


if __name__ == "__main__":
    unittest.main()
