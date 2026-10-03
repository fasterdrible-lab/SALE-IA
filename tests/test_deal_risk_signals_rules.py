"""
Testes — Tarefa A6 (docs/tasks-prompt-mestre-v2-restante.md): sinais
reais para o Deal Risk Engine (Fase 4.2) a partir da OpportunityMemory
(A3/A5), dos próximos passos da recapitulação e das reuniões vinculadas.

Persistência usa SQLite em memória — nunca toca no banco real.

Run:
    python -m unittest tests.test_deal_risk_signals_rules -v
"""

import os
import unittest
from datetime import datetime
from unittest.mock import patch

from sqlmodel import SQLModel, create_engine

from agent.deal_risk_signals_rules import calcular_sinais, estado_meddpicc_da_memoria, montar_riscos_calculados
from agent.opportunity_memory_writer_rules import (
    gravar_opportunity_memory_do_ciclo,
    gravar_proximos_passos_da_recapitulacao,
    montar_proximos_passos,
)
from api import database

AGORA = datetime(2026, 9, 30, 12, 0, 0)


def _insight(id_, valor, evidence="q", campo=None, status=None, meeting_id="m1", contradiz=None):
    i = {"id": id_, "meeting_id": meeting_id, "campo": campo, "valor": valor, "evidence": evidence,
         "confidence": 0.9, "timestamp": "2026-09-01T10:00:00", "contradiz": contradiz}
    if status:
        i["status"] = status
    return i


def _opp(status="open", created_at="2026-09-01T10:00:00"):
    return {"id": 1, "status": status, "created_at": created_at, "updated_at": created_at}


def _reuniao(meeting_id, quando):
    return {"meeting_id": meeting_id, "created_at": quando, "updated_at": quando}


def _memoria_qualificada():
    return {
        "economic_buyer": [_insight(1, "CFO Marcos", campo="economic_buyer", status="CONFIRMED")],
        "champion": [_insight(1, "Juliana", campo="champion", status="CONFIRMED")],
        "metrics": [_insight(1, "dobrar conversão", status="CONFIRMED")],
        "next_steps": [_insight(1, "enviar proposta", evidence=None, meeting_id="m2")],
        "objections": [],
    }


class EstadoMeddpiccDaMemoriaTest(unittest.TestCase):
    def test_sem_status_nenhum_e_none(self):
        memoria = {"champion": [_insight(1, "Marcos", campo="champion")]}  # sem status (não veio da A5)
        self.assertIsNone(estado_meddpicc_da_memoria(memoria))
        self.assertIsNone(estado_meddpicc_da_memoria(None))

    def test_reconstroi_status_por_item(self):
        memoria = {
            "economic_buyer": [_insight(1, "alguém lá em cima", campo="economic_buyer", status="PARTIAL"),
                               _insight(2, "CFO Marcos", campo="economic_buyer", status="CONFIRMED", contradiz=1)],
            "decision_process": [_insight(1, "jurídico revisa", campo="paper_process", status="PARTIAL"),
                                 _insight(2, "integração com ERP", status="CONFIRMED")],
            "competitors": [_insight(1, "Pipedrive", status="PARTIAL")],
        }
        estado = estado_meddpicc_da_memoria(memoria)
        self.assertEqual(estado["economic_buyer"]["status"], "CONFIRMED")
        self.assertEqual(estado["paper_process"]["status"], "PARTIAL")
        self.assertEqual(estado["decision_criteria"]["status"], "CONFIRMED")
        self.assertEqual(estado["competition"]["status"], "PARTIAL")
        self.assertEqual(estado["champion"]["status"], "UNKNOWN")


class CalcularSinaisTest(unittest.TestCase):
    def test_proximo_passo_olha_a_ultima_reuniao(self):
        memoria = {"next_steps": [_insight(1, "enviar proposta", meeting_id="m1")]}
        reunioes = [_reuniao("m1", "2026-09-10T10:00:00"), _reuniao("m2", "2026-09-20T10:00:00")]
        sinais = calcular_sinais(_opp(), memoria, reunioes, AGORA)
        self.assertEqual(sinais["ultima_reuniao"], "m2")
        self.assertFalse(sinais["tem_proximo_passo"])
        self.assertEqual(sinais["dias_desde_ultima_atividade"], 10)

    def test_sem_reuniao_proximo_passo_nao_avaliavel_e_stale_pela_oportunidade(self):
        sinais = calcular_sinais(_opp(created_at="2026-09-05T12:00:00"), {}, [], AGORA)
        self.assertIsNone(sinais["tem_proximo_passo"])
        self.assertEqual(sinais["dias_desde_ultima_atividade"], 25)

    def test_conta_objecoes_de_preco(self):
        memoria = {"objections": [
            _insight(1, "PRICE", "Achei caro"), _insight(2, "PRICE", "Tá fora do orçamento"),
            _insight(3, "ROOT_CAUSE:ADOPTION_RISK", "Equipe não vai usar"), _insight(4, "TIMING", "Agora não"),
        ]}
        self.assertEqual(calcular_sinais(_opp(), memoria, [], AGORA)["total_objecoes_preco"], 2)


class MontarRiscosCalculadosTest(unittest.TestCase):
    def test_oportunidade_bem_qualificada_e_ativa_sem_risco(self):
        r = montar_riscos_calculados(_opp(), _memoria_qualificada(),
                                     [_reuniao("m2", "2026-09-28T10:00:00")], AGORA)
        self.assertTrue(r["disponivel"])
        self.assertEqual(r["riscos"], [])
        self.assertEqual([n["risco"] for n in r["nao_avaliados"]], ["COMPETITOR_ADVANTAGE"])

    def test_sinais_reais_disparam_os_riscos(self):
        memoria = {
            "economic_buyer": [_insight(1, "alguém lá em cima", campo="economic_buyer", status="PARTIAL")],
            "objections": [_insight(i, "PRICE", f"caro {i}") for i in range(1, 4)],
            "next_steps": [],
        }
        r = montar_riscos_calculados(_opp(), memoria, [_reuniao("m1", "2026-09-01T10:00:00")], AGORA)
        self.assertEqual(r["riscos"], [
            "NO_ECONOMIC_BUYER", "NO_CHAMPION", "NO_NEXT_STEP", "NO_METRICS",
            "HIGH_PRICE_RESISTANCE", "STALE_OPPORTUNITY",
        ])
        self.assertEqual(r["sinais"]["total_objecoes_preco"], 3)
        self.assertEqual(r["sinais"]["dias_desde_ultima_atividade"], 29)

    def test_concorrente_em_vantagem_nunca_e_inventado(self):
        memoria = {**_memoria_qualificada(), "competitors": [_insight(1, "Pipedrive", status="CONFIRMED")]}
        r = montar_riscos_calculados(_opp(), memoria, [_reuniao("m2", "2026-09-28T10:00:00")], AGORA)
        self.assertNotIn("COMPETITOR_ADVANTAGE", r["riscos"])
        self.assertIn("COMPETITOR_ADVANTAGE", [n["risco"] for n in r["nao_avaliados"]])

    def test_sem_reuniao_no_next_step_vai_para_nao_avaliados(self):
        r = montar_riscos_calculados(_opp(created_at="2026-09-29T10:00:00"), _memoria_qualificada(), [], AGORA)
        self.assertNotIn("NO_NEXT_STEP", r["riscos"])
        self.assertIn("NO_NEXT_STEP", [n["risco"] for n in r["nao_avaliados"]])

    def test_oportunidade_encerrada_nao_tem_risco_em_aberto(self):
        r = montar_riscos_calculados(_opp(status="won"), {}, [], AGORA)
        self.assertTrue(r["encerrada"])
        self.assertEqual(r["riscos"], [])


class ProximosPassosTest(unittest.TestCase):
    def test_montar_proximos_passos(self):
        recap = {"proximos_passos": [
            {"acao": "Enviar proposta", "prazo": "sexta", "responsavel": "vendedor"},
            {"acao": "ação a ser tomada", "prazo": "quando"},  # placeholder copiado do schema
            {"acao": "Agendar demo", "prazo": "quando"},
            "Ligar para o CFO",
            {"acao": "  enviar   proposta ", "prazo": "sexta"},
            42,
        ]}
        self.assertEqual(montar_proximos_passos(recap),
                         ["Enviar proposta (prazo: sexta)", "Agendar demo", "Ligar para o CFO"])
        self.assertEqual(montar_proximos_passos("texto"), [])
        self.assertEqual(montar_proximos_passos({}), [])


class _ComBancoEmMemoria(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        p = patch.object(database, "engine", self._engine)
        p.start()
        self.addCleanup(p.stop)
        env = patch.dict(os.environ, {"OPPORTUNITY_MEMORY_WRITE_ENABLED": "true"})
        env.start()
        self.addCleanup(env.stop)


class GravarProximosPassosTest(_ComBancoEmMemoria):
    def test_dedup_por_reuniao(self):
        recap = {"proximos_passos": [{"acao": "Enviar proposta", "prazo": "sexta"}]}
        self.assertEqual(gravar_proximos_passos_da_recapitulacao(1, "m1", recap), 1)
        self.assertEqual(gravar_proximos_passos_da_recapitulacao(1, "m1", recap), 0)  # recap regerada
        self.assertEqual(gravar_proximos_passos_da_recapitulacao(1, "m2", recap), 1)  # mesmo passo, outra reunião
        passos = database.obter_opportunity_memory(1, criar_se_ausente=False)["next_steps"]
        self.assertEqual([(p["meeting_id"], p["valor"]) for p in passos],
                         [("m1", "Enviar proposta (prazo: sexta)"), ("m2", "Enviar proposta (prazo: sexta)")])
        self.assertIsNone(passos[0]["evidence"])  # resumo da IA, nunca fingido como citação

    def test_sem_oportunidade_anonima_ou_kill_switch(self):
        recap = {"proximos_passos": ["Enviar proposta"]}
        self.assertEqual(gravar_proximos_passos_da_recapitulacao(None, "m1", recap), 0)
        self.assertEqual(gravar_proximos_passos_da_recapitulacao(1, "default", recap), 0)
        with patch.dict(os.environ, {"OPPORTUNITY_MEMORY_WRITE_ENABLED": "false"}):
            self.assertEqual(gravar_proximos_passos_da_recapitulacao(1, "m1", recap), 0)


class StatusMeddpiccNaMemoriaTest(_ComBancoEmMemoria):
    def _fato(self, status, quote):
        return {"item": "economic_buyer", "status": status, "valor": "CFO Marcos",
                "confidence": 0.9, "evidence_quote": quote}

    def test_a3_grava_status_e_registra_promocao_para_confirmed(self):
        gravar_opportunity_memory_do_ciclo(1, "m1", meddpicc_fatos=[self._fato("PARTIAL", "o Marcos talvez")])
        gravar_opportunity_memory_do_ciclo(1, "m1", meddpicc_fatos=[self._fato("PARTIAL", "o Marcos talvez")])
        gravar_opportunity_memory_do_ciclo(1, "m2", meddpicc_fatos=[self._fato("CONFIRMED", "o Marcos talvez")])
        decisores = database.obter_opportunity_memory(1, criar_se_ausente=False)["economic_buyer"]
        self.assertEqual([d["status"] for d in decisores], ["PARTIAL", "CONFIRMED"])
        self.assertIsNone(decisores[1]["contradiz"])  # mesmo decisor, só mais confirmado
        estado = estado_meddpicc_da_memoria(database.obter_opportunity_memory(1, criar_se_ausente=False))
        self.assertEqual(estado["economic_buyer"]["status"], "CONFIRMED")

    def test_insight_sem_status_continua_sem_a_chave(self):
        database.registrar_conhecimento_opportunity(1, "pain_points", meeting_id="m1", valor="dor", evidence="q")
        self.assertNotIn("status", database.obter_opportunity_memory(1)["pain_points"][0])


if __name__ == "__main__":
    unittest.main()
