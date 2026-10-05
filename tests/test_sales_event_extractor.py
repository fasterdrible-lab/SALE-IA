"""
Testes — Tarefa A7 (docs/tasks-prompt-mestre-v2-restante.md): extrator
de SalesEvent via IA (mockada — nunca chama provedor real), gravação com
dedup entre ciclos e wiring no orquestrador.

Persistência em SQLite em memória — nunca toca no banco real.

Run:
    python -m unittest tests.test_sales_event_extractor -v
"""

import asyncio
import logging
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlmodel import SQLModel, create_engine

logging.disable(logging.CRITICAL)

import agent.multiagente.orquestrador as orquestrador
from agent.sales_event_extractor import (
    CONFIANCA_MINIMA,
    contar_precisao_eventos,
    extrair_sales_events_async,
    persistir_sales_events_do_ciclo,
    sales_event_extractor_ativo,
)
from api import ai_features, database

_CONVERSA = (
    "Cliente: quanto fica o plano anual? "
    "Cliente: achei caro pra gente agora. "
    "Vendedor: fechado então, te mando a proposta na sexta. Cliente: combinado, pode mandar."
)


def _ev(tipo, citacao, confianca=0.9):
    return {"event_type": tipo, "confidence": confianca, "evidence_quote": citacao}


def _extrair(resposta):
    ia = AsyncMock(return_value=resposta)
    with patch("agent.sales_event_extractor.chamar_ia_com_fallback_claude", new=ia):
        eventos = asyncio.run(extrair_sales_events_async(_CONVERSA, "", usuario_id="s1", meeting_id="m1"))
    return eventos, ia


class ExtrairTest(unittest.TestCase):
    def test_eventos_validos(self):
        eventos, ia = _extrair({"eventos": [
            _ev("PRICE_DISCUSSION", "quanto fica o plano anual?"),
            _ev("OBJECTION_RAISED", "achei caro pra gente agora"),
            _ev("NEXT_STEP_AGREED", "te mando a proposta na sexta"),
        ]})
        self.assertEqual([e["event_type"] for e in eventos], ["PRICE_DISCUSSION", "OBJECTION_RAISED", "NEXT_STEP_AGREED"])
        self.assertEqual(ia.await_args.kwargs["feature"], ai_features.SALES_EVENT_EXTRACAO)

    def test_citacao_fabricada_tipo_fora_do_vocabulario_e_confidence_invalida(self):
        eventos, _ = _extrair({"eventos": [
            _ev("DEAL_WON", "assinamos o contrato hoje"),          # nunca foi dito
            _ev("HAPPY_CUSTOMER", "quanto fica o plano anual?"),   # tipo inventado
            _ev("PRICE_DISCUSSION", "quanto fica o plano anual?", 1.4),
            _ev("PRICE_DISCUSSION", ""),
            _ev("OBJECTION_RAISED", "achei caro pra gente agora"),
        ]})
        self.assertEqual([e["event_type"] for e in eventos], ["OBJECTION_RAISED"])

    def test_confianca_abaixo_do_minimo_e_descartada(self):
        # A7b: a própria IA marcando com confiança baixa = frase mal comprova o tipo.
        eventos, _ = _extrair({"eventos": [
            _ev("CHAMPION_IDENTIFIED", "achei caro pra gente agora", 0.3),
            _ev("PRICE_DISCUSSION", "quanto fica o plano anual?", CONFIANCA_MINIMA),
        ]})
        self.assertEqual([e["event_type"] for e in eventos], ["PRICE_DISCUSSION"])

    def test_mesmo_evento_com_a_mesma_fala_nao_duplica(self):
        eventos, _ = _extrair({"eventos": [
            _ev("PRICE_DISCUSSION", "quanto fica o plano anual?"),
            _ev("PRICE_DISCUSSION", "quanto fica o plano anual? "),
        ]})
        self.assertEqual(len(eventos), 1)

    def test_resposta_vazia_ou_malformada(self):
        for resposta in ({"eventos": []}, {}, None, {"eventos": ["lixo", 3]}, "texto"):
            self.assertEqual(_extrair(resposta)[0], [], repr(resposta))

    def test_kill_switch(self):
        with patch.dict(os.environ, {"SALES_EVENT_EXTRACTOR_ENABLED": "false"}):
            self.assertFalse(sales_event_extractor_ativo())
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SALES_EVENT_EXTRACTOR_ENABLED", None)
            self.assertTrue(sales_event_extractor_ativo())


class PromptSemVazamentoDoGabaritoTest(unittest.TestCase):
    """A7b: exemplos do prompt nunca podem ser frases do Golden Dataset —
    senão o `event_precision` mede a IA nos exemplos que ela acabou de ver."""

    def test_prompt_nao_contem_5_palavras_seguidas_de_nenhum_cenario(self):
        import re
        from pathlib import Path

        from agent.quality_monitoring_golden_runner import carregar_cenarios_golden_dataset

        def palavras(texto):
            return re.findall(r"\w+", texto.lower())

        prompt = " ".join(palavras(
            (Path(__file__).parent.parent / "agent" / "prompt_templates" / "sales_event_extractor.txt").read_text(encoding="utf-8")
        ))
        for cenario in carregar_cenarios_golden_dataset():
            p = palavras(cenario["input"])
            for i in range(len(p) - 4):
                trecho = " ".join(p[i:i + 5])
                self.assertNotIn(trecho, prompt, f"{cenario['id']}: '{trecho}'")


class PrecisaoTest(unittest.TestCase):
    def test_contagem_por_tipo(self):
        previstos = [_ev("PRICE_DISCUSSION", "a"), _ev("PRICE_DISCUSSION", "b"), _ev("BUYING_SIGNAL", "c")]
        self.assertEqual(contar_precisao_eventos(previstos, ["PRICE_DISCUSSION", "OBJECTION_RAISED"]), (1, 1, 1))

    def test_cenario_sem_evento_esperado(self):
        self.assertEqual(contar_precisao_eventos([_ev("PAIN_DETECTED", "x")], []), (0, 1, 0))
        self.assertEqual(contar_precisao_eventos([], []), (0, 0, 0))


class _ComBancoEmMemoria(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(engine)
        p = patch.object(database, "engine", engine)
        p.start()
        self.addCleanup(p.stop)


class PersistirTest(_ComBancoEmMemoria):
    def test_grava_com_dedup_entre_ciclos(self):
        ciclo1 = [_ev("PRICE_DISCUSSION", "quanto fica o plano anual?")]
        ciclo2 = ciclo1 + [_ev("OBJECTION_RAISED", "achei caro pra gente agora")]
        self.assertEqual(persistir_sales_events_do_ciclo("m1", ciclo1, opportunity_id=7, seller_id="s1"), 1)
        self.assertEqual(persistir_sales_events_do_ciclo("m1", ciclo2, opportunity_id=7, seller_id="s1"), 1)
        gravados = database.listar_sales_events(meeting_id="m1")
        self.assertEqual([e["event_type"] for e in gravados], ["PRICE_DISCUSSION", "OBJECTION_RAISED"])
        self.assertEqual(gravados[0]["source"], "conversation")
        self.assertEqual(gravados[0]["opportunity_id"], 7)
        self.assertEqual(gravados[0]["seller_id"], "s1")

    def test_reuniao_anonima_ou_sem_eventos(self):
        self.assertEqual(persistir_sales_events_do_ciclo("default", [_ev("PRICE_DISCUSSION", "x")]), 0)
        self.assertEqual(persistir_sales_events_do_ciclo(None, [_ev("PRICE_DISCUSSION", "x")]), 0)
        self.assertEqual(persistir_sales_events_do_ciclo("m1", []), 0)
        self.assertEqual(database.listar_sales_events(), [])

    def test_evento_invalido_e_pulado(self):
        criados = persistir_sales_events_do_ciclo("m1", [{"event_type": "INVENTADO", "confidence": 0.9,
                                                          "evidence_quote": "x"},
                                                         _ev("BUYING_SIGNAL", "quero seguir")])
        self.assertEqual(criados, 1)


class WiringOrquestradorTest(_ComBancoEmMemoria):
    def _rodar_shadow(self, eventos_ia, env=None, meeting_id="m1"):
        raciocinar_mock = AsyncMock(return_value=None)
        patches = [
            patch.dict(os.environ, {
                "SALES_EVIDENCE_PERSIST_ENABLED": "false", "OPPORTUNITY_MEMORY_WRITE_ENABLED": "false",
                "OPPORTUNITY_GRAPH_WRITE_ENABLED": "false", "MEDDPICC_EXTRACTOR_ENABLED": "false",
                "SELLER_CONTEXT_ENABLED": "false", "SALES_EVENT_EXTRACTOR_ENABLED": "true", **(env or {}),
            }),
            patch("agent.sales_reasoning_engine.raciocinar_async", new=raciocinar_mock),
            patch("api.database.criar_shadow_mode_comparison", new=MagicMock(return_value=None)),
            patch("api.database.obter_ultimo_ai_usage_event", return_value=None),
            patch("agent.opportunity_link_rules.vincular_automaticamente_se_possivel", return_value=None),
            patch("agent.spin_extractor.extrair_spin_state_async", new=AsyncMock(return_value=None)),
            patch("agent.behavioral_signal_extractor.extrair_sinais_comportamentais_async", new=AsyncMock(return_value=[])),
            patch("agent.buyer_motivation_extractor.extrair_buyer_motivation_async", new=AsyncMock(return_value=None)),
            patch("agent.sales_event_extractor.chamar_ia_com_fallback_claude", new=eventos_ia),
        ]
        for p in patches:
            p.start()
        try:
            asyncio.run(orquestrador._rodar_shadow_mode(
                recomendacao_atual={}, objecao_detectada=None,
                transcricao_parcial=_CONVERSA, historico="", resumo_vivo="",
                diagnostico_atual={}, mapa_financeiro={}, historico_scores=[], eventos=[],
                client_context="", usuario_id="s1", meeting_id=meeting_id,
            ))
        finally:
            for p in reversed(patches):
                p.stop()
        return raciocinar_mock

    def test_ciclo_grava_sales_events(self):
        ia = AsyncMock(return_value={"eventos": [_ev("PRICE_DISCUSSION", "quanto fica o plano anual?")]})
        self._rodar_shadow(ia)
        self._rodar_shadow(ia)  # 2º ciclo, mesma fala: sem duplicata
        eventos = database.listar_sales_events(meeting_id="m1")
        self.assertEqual([e["event_type"] for e in eventos], ["PRICE_DISCUSSION"])
        self.assertEqual(eventos[0]["seller_id"], "s1")

    def test_falha_de_ia_nunca_derruba_o_ciclo(self):
        raciocinar_mock = self._rodar_shadow(AsyncMock(side_effect=RuntimeError("503")))
        raciocinar_mock.assert_awaited_once()
        self.assertEqual(database.listar_sales_events(), [])

    def test_kill_switch_e_reuniao_anonima_nao_chamam_ia(self):
        ia = AsyncMock(return_value={"eventos": []})
        self._rodar_shadow(ia, env={"SALES_EVENT_EXTRACTOR_ENABLED": "false"})
        self._rodar_shadow(ia, meeting_id="default")
        ia.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
