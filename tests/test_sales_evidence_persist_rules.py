"""
Testes — Tarefa A2 (docs/tasks-prompt-mestre-v2-restante.md): persistir
SalesEvidence a partir dos extratores que já rodam no ciclo de tempo
real (SPIN, sinais comportamentais, motivação, objeção + causa raiz).

Persistência usa SQLite em memória (mesmo padrão de
tests/test_sales_evidence.py) — nunca toca no banco real do projeto (o
.env local aponta DB_HOST para a VPS).

Run:
    python -m unittest tests.test_sales_evidence_persist_rules -v
"""

import asyncio
import logging
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlmodel import SQLModel, create_engine

logging.disable(logging.CRITICAL)

import agent.multiagente.orquestrador as orquestrador
from agent.sales_evidence_persist_rules import (
    coletar_evidencias,
    persistir_evidencias_do_ciclo,
    sales_evidence_persist_ativo,
)
from api import database

_SPIN = {
    "situation": {"known": [
        {"stage": "situation", "campo": "team_size", "valor": "12", "evidence_quote": "Somos 12 vendedores"},
    ], "missing": ["crm_tool"]},
    "problem": {"known": [
        {"stage": "problem", "campo": "main_pain", "valor": "leads esquecidos", "evidence_quote": "A gente esquece os leads"},
    ], "missing": []},
    "implication": {"known": [], "missing": ["financial_impact"]},
    "need_payoff": {"known": [], "missing": ["solution_value"]},
}
_SINAIS = [
    {"signal": "RISK_AVERSION", "evidence_quote": "Tenho medo de trocar e dar errado", "descricao": "..."},
]
_MOTIVACAO = {
    "motivation": "GROWTH", "confidence": 0.8,
    "evidence": ["Queremos dobrar o time esse ano", "Crescer é a meta"],
}
_OBJECOES = [{
    "objection_spoken": {"category": "PRICE", "evidence_quote": "Achei caro"},
    "root_cause_hypothesis": {"hypothesis": "ADOPTION_RISK", "confidence": 0.75,
                              "evidence_quote": "Minha equipe não vai usar"},
    "precisa_investigar": False,
}]


class ColetarEvidenciasTest(unittest.TestCase):
    def test_converte_as_4_fontes(self):
        evidencias = coletar_evidencias(_SPIN, _SINAIS, _MOTIVACAO, _OBJECOES)
        tipos = [e["type"] for e in evidencias]
        self.assertEqual(tipos, [
            "SPIN_SITUATION:team_size",
            "SPIN_PROBLEM:main_pain",
            "BEHAVIOR:RISK_AVERSION",
            "MOTIVATION:GROWTH",
            "MOTIVATION:GROWTH",
            "OBJECTION:PRICE",
            "ROOT_CAUSE:ADOPTION_RISK",
        ])

    def test_confidence_so_quando_o_extrator_produz(self):
        por_tipo = {e["type"]: e for e in coletar_evidencias(_SPIN, _SINAIS, _MOTIVACAO, _OBJECOES)}
        self.assertNotIn("confidence", por_tipo["SPIN_PROBLEM:main_pain"])
        self.assertNotIn("confidence", por_tipo["OBJECTION:PRICE"])
        self.assertEqual(por_tipo["ROOT_CAUSE:ADOPTION_RISK"]["confidence"], 0.75)

    def test_objecao_falada_e_causa_raiz_nunca_fundidas(self):
        evidencias = coletar_evidencias(objections=_OBJECOES)
        self.assertEqual(len(evidencias), 2)
        self.assertEqual(evidencias[0]["quote"], "Achei caro")
        self.assertEqual(evidencias[1]["quote"], "Minha equipe não vai usar")

    def test_objecao_sem_causa_raiz_gera_so_a_falada(self):
        objecoes = [{"objection_spoken": {"category": "PRICE", "evidence_quote": "Achei caro"},
                     "root_cause_hypothesis": None, "precisa_investigar": True}]
        self.assertEqual([e["type"] for e in coletar_evidencias(objections=objecoes)], ["OBJECTION:PRICE"])

    def test_entrada_toda_vazia_ou_none(self):
        self.assertEqual(coletar_evidencias(), [])
        self.assertEqual(coletar_evidencias({}, [], None, []), [])

    def test_entrada_malformada_nunca_levanta(self):
        evidencias = coletar_evidencias(
            spin_state={"situation": "lixo", "problem": {"known": ["lixo", {"campo": "x"}]}},
            behavioral_signals=["lixo", {"signal": "", "evidence_quote": "a"}],
            buyer_motivation={"motivation": "GROWTH", "confidence": "alta", "evidence": ["a"]},
            objections=["lixo", {"objection_spoken": "lixo"}],
        )
        self.assertEqual(evidencias, [])

    def test_dedup_dentro_do_lote_ignora_caixa_e_espacos(self):
        sinais = [
            {"signal": "RISK_AVERSION", "evidence_quote": "Tenho medo"},
            {"signal": "RISK_AVERSION", "evidence_quote": "  tenho   MEDO "},
        ]
        self.assertEqual(len(coletar_evidencias(behavioral_signals=sinais)), 1)

    def test_mesma_fala_com_tipos_diferentes_nao_e_duplicata(self):
        sinais = [
            {"signal": "RISK_AVERSION", "evidence_quote": "Tenho medo"},
            {"signal": "LOSS_AVERSION", "evidence_quote": "Tenho medo"},
        ]
        self.assertEqual(len(coletar_evidencias(behavioral_signals=sinais)), 2)

    def test_type_truncado_no_limite_da_coluna(self):
        objecoes = [{"objection_spoken": {"category": "PRICE", "evidence_quote": "caro"},
                     "root_cause_hypothesis": {"hypothesis": "X" * 100, "confidence": 0.9, "evidence_quote": "q"}}]
        tipos = [e["type"] for e in coletar_evidencias(objections=objecoes)]
        self.assertTrue(all(len(t) <= 60 for t in tipos))


class KillSwitchTest(unittest.TestCase):
    def test_ligado_por_padrao(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SALES_EVIDENCE_PERSIST_ENABLED", None)
            self.assertTrue(sales_evidence_persist_ativo())

    def test_desligado_com_false(self):
        with patch.dict(os.environ, {"SALES_EVIDENCE_PERSIST_ENABLED": "false"}):
            self.assertFalse(sales_evidence_persist_ativo())


class _ComBancoEmMemoria(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)
        env = patch.dict(os.environ, {"SALES_EVIDENCE_PERSIST_ENABLED": "true"})
        env.start()
        self.addCleanup(env.stop)


class PersistirEvidenciasTest(_ComBancoEmMemoria):
    def test_reuniao_de_3_ciclos_sem_duplicata(self):
        """Teste literal da Tarefa A2: a mesma fala reaparece a cada ciclo
        (transcrição acumulada) — só evidência nova é gravada."""
        ciclo1 = persistir_evidencias_do_ciclo("m1", spin_state=_SPIN)
        ciclo2 = persistir_evidencias_do_ciclo("m1", spin_state=_SPIN, behavioral_signals=_SINAIS)
        ciclo3 = persistir_evidencias_do_ciclo(
            "m1", spin_state=_SPIN, behavioral_signals=_SINAIS,
            buyer_motivation=_MOTIVACAO, objections=_OBJECOES,
        )

        self.assertEqual((ciclo1, ciclo2, ciclo3), (2, 1, 4))
        gravadas = database.listar_sales_evidences(meeting_id="m1")
        self.assertEqual(len(gravadas), 7)
        chaves = {(e["type"], e["quote"]) for e in gravadas}
        self.assertEqual(len(chaves), 7)

    def test_campos_gravados(self):
        persistir_evidencias_do_ciclo("m1", objections=_OBJECOES)
        por_tipo = {e["type"]: e for e in database.listar_sales_evidences(meeting_id="m1")}
        root = por_tipo["ROOT_CAUSE:ADOPTION_RISK"]
        self.assertEqual(root["quote"], "Minha equipe não vai usar")
        self.assertEqual(root["confidence"], 0.75)
        self.assertEqual(root["source"], "conversation")
        self.assertIsNone(root["speaker"])
        self.assertEqual(por_tipo["OBJECTION:PRICE"]["confidence"], 1.0)

    def test_dedup_e_por_reuniao(self):
        persistir_evidencias_do_ciclo("m1", behavioral_signals=_SINAIS)
        self.assertEqual(persistir_evidencias_do_ciclo("m2", behavioral_signals=_SINAIS), 1)

    def test_reuniao_anonima_nunca_grava(self):
        self.assertEqual(persistir_evidencias_do_ciclo(None, behavioral_signals=_SINAIS), 0)
        self.assertEqual(persistir_evidencias_do_ciclo("default", behavioral_signals=_SINAIS), 0)
        self.assertEqual(database.listar_sales_evidences(), [])

    def test_kill_switch_desligado_nunca_grava(self):
        with patch.dict(os.environ, {"SALES_EVIDENCE_PERSIST_ENABLED": "false"}):
            self.assertEqual(persistir_evidencias_do_ciclo("m1", behavioral_signals=_SINAIS), 0)
        self.assertEqual(database.listar_sales_evidences(), [])

    def test_item_invalido_no_banco_nao_derruba_os_outros(self):
        original = database.criar_sales_evidence
        chamadas = []

        def _criar(**kwargs):
            chamadas.append(kwargs["type"])
            if kwargs["type"] == "OBJECTION:PRICE":
                raise ValueError("simulado")
            return original(**kwargs)

        with patch.object(database, "criar_sales_evidence", side_effect=_criar):
            criadas = persistir_evidencias_do_ciclo("m1", objections=_OBJECOES)

        self.assertEqual(criadas, 1)
        self.assertEqual(len(chamadas), 2)
        self.assertEqual([e["type"] for e in database.listar_sales_evidences(meeting_id="m1")],
                         ["ROOT_CAUSE:ADOPTION_RISK"])


class WiringOrquestradorTest(_ComBancoEmMemoria):
    """Shadow Mode (ligado em produção) roda os extratores e passa a
    gravar as evidências — sem mudar a entrada do SalesReasoningEngine."""

    def _rodar_shadow(self, criar_evidence=None):
        raciocinar_mock = AsyncMock(return_value=None)
        patches = [
            patch("agent.sales_reasoning_engine.raciocinar_async", new=raciocinar_mock),
            patch("api.database.criar_shadow_mode_comparison", new=MagicMock(return_value=None)),
            patch("api.database.obter_ultimo_ai_usage_event", return_value=None),
            patch("agent.opportunity_link_rules.vincular_automaticamente_se_possivel", return_value=None),
            patch("agent.spin_extractor.extrair_spin_state_async", new=AsyncMock(return_value=_SPIN)),
            patch("agent.behavioral_signal_extractor.extrair_sinais_comportamentais_async",
                  new=AsyncMock(return_value=_SINAIS)),
            patch("agent.buyer_motivation_extractor.extrair_buyer_motivation_async",
                  new=AsyncMock(return_value=_MOTIVACAO)),
        ]
        if criar_evidence is not None:
            patches.append(patch.object(database, "criar_sales_evidence", new=criar_evidence))
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
            for p in patches:
                p.stop()
        return raciocinar_mock

    def test_shadow_mode_grava_evidencias_e_dedup_no_segundo_ciclo(self):
        raciocinar_mock = self._rodar_shadow()
        self._rodar_shadow()

        gravadas = database.listar_sales_evidences(meeting_id="m1")
        self.assertEqual(len(gravadas), 5)  # 2 SPIN + 1 sinal + 2 citações de motivação
        entrada = raciocinar_mock.await_args.args[0]
        self.assertEqual(entrada["spin_state"], _SPIN)
        self.assertNotIn("sales_evidence", entrada)

    def test_falha_de_persistencia_nunca_derruba_o_ciclo(self):
        raciocinar_mock = self._rodar_shadow(criar_evidence=MagicMock(side_effect=RuntimeError("banco fora")))
        raciocinar_mock.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
