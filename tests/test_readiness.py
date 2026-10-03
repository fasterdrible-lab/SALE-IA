"""
Testes — Tarefa D1 (docs/tasks-prompt-mestre-v2-restante.md): painel de
prontidão com os 9 critérios da Fase 25 (`agent/readiness_rules.py`,
`api/database.py::readiness_*`, `GET /admin/readiness`).

Persistência usa SQLite em memória — nunca toca no banco real.

Run:
    python -m unittest tests.test_readiness -v
"""

import logging
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

logging.disable(logging.CRITICAL)

from agent.readiness_rules import (
    CRITERIOS,
    avaliar_status,
    medicao_da_transcricao,
    medicoes_do_golden_dataset,
    montar_painel,
)
from api import ai_features, database

_SEM_DADO = {"janela_dias": 7, "audit": {"chamadas": 0, "auditadas": 0}, "e2e": {"total": 0, "sucesso": 0},
             "policy_violations": 0}


def _por_criterio(painel):
    return {c["criterio"]: c for c in painel["criterios"]}


class AvaliarStatusTest(unittest.TestCase):
    def test_comparacoes(self):
        self.assertEqual(avaliar_status(0.07, 0.10, "max"), "atinge")
        self.assertEqual(avaliar_status(0.11, 0.10, "max"), "nao_atinge")
        self.assertEqual(avaliar_status(0.995, 0.99, "min"), "atinge")
        self.assertEqual(avaliar_status(0.855, 0.99, "min"), "nao_atinge")
        self.assertEqual(avaliar_status(0.45, None, None), "sem_alvo")
        self.assertEqual(avaliar_status(None, 0.9, "min"), "sem_numero")


class MontarPainelTest(unittest.TestCase):
    def test_sempre_os_9_criterios_na_ordem_da_fase_25(self):
        painel = montar_painel(_SEM_DADO, {})
        self.assertEqual([c["criterio"] for c in painel["criterios"]], [c["nome"] for c in CRITERIOS])
        self.assertEqual(painel["resumo"]["total"], 9)

    def test_gaps_e_lote_sem_medicao_nunca_viram_numero(self):
        c = _por_criterio(montar_painel(_SEM_DADO, {}))
        self.assertEqual(c["human_escalation_functional"]["origem"], "gap")
        self.assertEqual(c["human_escalation_functional"]["status"], "sem_numero")
        self.assertTrue(c["human_escalation_functional"]["detalhe"])
        # Tarefa A7: event_precision virou critério de lote (golden dataset).
        self.assertEqual(c["event_precision"]["status"], "sem_numero")
        self.assertIn("quality_monitoring_golden_run.py", c["event_precision"]["detalhe"])
        self.assertEqual(c["objection_classification"]["status"], "sem_numero")
        self.assertIn("quality_monitoring_golden_run.py", c["objection_classification"]["detalhe"])
        # sem chamadas: audit/e2e sem número, nunca 0% nem 100% inventado
        self.assertIsNone(c["audit_coverage"]["valor"])
        self.assertIsNone(c["e2e_success"]["valor"])
        self.assertEqual(c["policy_violation"]["status"], "atinge")

    def test_ao_vivo_e_lote_com_dado_real(self):
        contagens = {"janela_dias": 7, "audit": {"chamadas": 322, "auditadas": 322},
                     "e2e": {"total": 1000, "sucesso": 855}, "policy_violations": 0}
        lote = {
            "transcription_reliability": {"valor": 0.073, "origem": "real", "amostra": 30,
                                          "medido_em": "2026-09-24T10:00:00", "fonte": "x"},
            "objection_classification": {"valor": 0.75, "origem": "real", "amostra": 8,
                                         "medido_em": "2026-09-23T10:00:00", "fonte": "x"},
            "critical_hallucination": {"valor": 0.1444, "origem": "proxy", "amostra": 90,
                                       "medido_em": "2026-09-23T10:00:00", "fonte": "x"},
            "recommendation_quality": {"valor": 0.456, "origem": "real", "amostra": 180,
                                       "medido_em": "2026-09-29T10:00:00", "fonte": "x"},
        }
        painel = montar_painel(contagens, lote)
        c = _por_criterio(painel)
        self.assertEqual((c["audit_coverage"]["valor"], c["audit_coverage"]["status"]), (1.0, "atinge"))
        self.assertEqual((c["e2e_success"]["valor"], c["e2e_success"]["origem"]), (0.855, "proxy"))
        self.assertEqual(c["e2e_success"]["status"], "nao_atinge")
        self.assertEqual(c["transcription_reliability"]["status"], "atinge")
        self.assertEqual(c["objection_classification"]["status"], "nao_atinge")
        self.assertEqual(c["critical_hallucination"]["origem"], "proxy")
        self.assertEqual(c["recommendation_quality"]["status"], "sem_alvo")
        self.assertEqual(c["transcription_reliability"]["medido_em"], "2026-09-24T10:00:00")
        self.assertFalse(painel["resumo"]["pronto_para_digital_twin"])
        self.assertEqual(painel["resumo"]["atinge"], 3)

    def test_proxy_no_alvo_nao_libera_o_digital_twin(self):
        contagens = {"janela_dias": 7, "audit": {"chamadas": 1, "auditadas": 1},
                     "e2e": {"total": 100, "sucesso": 100}, "policy_violations": 0}
        self.assertFalse(montar_painel(contagens, {})["resumo"]["pronto_para_digital_twin"])


class ConversoresDeScriptTest(unittest.TestCase):
    def test_golden_dataset(self):
        relatorio = {"objection_precision": 0.75, "hallucination_rate": 0.1444,
                     "amostra": {"objecao_total": 8, "afirmacoes_total": 90}}
        medicoes = {m["criterio"]: m for m in medicoes_do_golden_dataset(relatorio)}
        self.assertEqual(medicoes["objection_classification"]["origem"], "real")
        self.assertEqual(medicoes["critical_hallucination"]["origem"], "proxy")
        self.assertEqual(medicoes["critical_hallucination"]["amostra"], 90)
        self.assertEqual(medicoes_do_golden_dataset({"objection_precision": None, "hallucination_rate": None}), [])
        # Tarefa A7: event_precision entra quando é número; gap (dict) não.
        com_eventos = {**relatorio, "event_precision": 0.6, "event_recall": 0.5, "amostra": {"eventos_previstos": 20}}
        evento = {m["criterio"]: m for m in medicoes_do_golden_dataset(com_eventos)}["event_precision"]
        self.assertEqual((evento["valor"], evento["origem"], evento["amostra"]), (0.6, "real", 20))
        gap = {**relatorio, "event_precision": {"disponivel": False}}
        self.assertNotIn("event_precision", {m["criterio"] for m in medicoes_do_golden_dataset(gap)})

    def test_transcricao_usa_o_provider_ativo(self):
        resumo = {"groq": {"n": 30, "wer_medio": 0.073}, "whisper_local": {"n": 30, "wer_medio": 0.11},
                  "whisper": {"n": 30, "wer_medio": None}}
        medicao = medicao_da_transcricao(resumo, "whisper_local")
        self.assertEqual((medicao["valor"], medicao["amostra"]), (0.11, 30))
        self.assertIsNone(medicao_da_transcricao(resumo, "whisper"))  # nunca troca pelo melhor


class _ComBancoEmMemoria(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                                     poolclass=StaticPool)
        SQLModel.metadata.create_all(self._engine)
        p = patch.object(database, "engine", self._engine)
        p.start()
        self.addCleanup(p.stop)

    def _chamada(self, feature, quando, success=True):
        with Session(self._engine) as s:
            s.add(database.AiUsageEvent(feature=feature, provider="deepseek", criado_em=quando, success=success))
            s.commit()

    def _audit(self, quando):
        with Session(self._engine) as s:
            s.add(database.AuditTrailEntry(actor="sales_reasoning_engine", action="gerar_recomendacao",
                                           reason="r", result="ok", created_at=quando))
            s.commit()


class ReadinessBancoTest(_ComBancoEmMemoria):
    def test_registrar_valida_criterio_e_origem(self):
        with self.assertRaises(ValueError):
            database.registrar_readiness_medicao("inventado", 0.5)
        with self.assertRaises(ValueError):
            database.registrar_readiness_medicao("objection_classification", 0.5, origem="gap")

    def test_ultimas_medicoes_pega_a_mais_recente(self):
        database.registrar_readiness_medicao("objection_classification", 0.70, fonte="a")
        database.registrar_readiness_medicao("objection_classification", 0.75, fonte="b", detalhe={"x": 1})
        ultima = database.ultimas_readiness_medicoes()["objection_classification"]
        self.assertEqual((ultima["valor"], ultima["fonte"], ultima["detalhe"]), (0.75, "b", {"x": 1}))

    def test_audit_coverage_so_conta_chamadas_depois_da_1a_auditoria(self):
        """Regressão do erro de medição da V.1.4.141: chamadas anteriores
        ao audit trail existir nunca entram no denominador."""
        agora = datetime(2026, 10, 1, 12, 0)
        motor = ai_features.SALES_REASONING_RACIOCINIO
        self._chamada(motor, agora - timedelta(days=3))          # antes da 1ª auditoria
        self._audit(agora - timedelta(days=2))
        self._chamada(motor, agora - timedelta(days=2))
        self._audit(agora - timedelta(days=1))
        self._chamada(motor, agora - timedelta(days=1))
        self._chamada("realtime.coach", agora - timedelta(days=1), success=False)
        self._chamada("realtime.coach", agora - timedelta(days=30))  # fora da janela

        contagens = database.readiness_contagens_ao_vivo(dias=7, agora=agora)
        self.assertEqual(contagens["audit"], {"chamadas": 2, "auditadas": 2})
        self.assertEqual(contagens["e2e"], {"total": 4, "sucesso": 3})

    def test_audit_gravado_depois_da_chamada_conta_a_chamada_que_o_gerou(self):
        """Achado da D4: a auditoria é gravada depois que a chamada de IA
        termina. A chamada que gerou a 1ª auditoria precisa entrar no
        denominador (antes: 2 auditorias / 1 chamada = 200%)."""
        agora = datetime(2026, 10, 1, 12, 0)
        motor = ai_features.SALES_REASONING_RACIOCINIO
        self._chamada(motor, agora - timedelta(days=5))  # anterior ao audit trail existir
        for horas in (48, 24):
            self._chamada(motor, agora - timedelta(hours=horas))
            self._audit(agora - timedelta(hours=horas) + timedelta(seconds=1))
        contagens = database.readiness_contagens_ao_vivo(dias=7, agora=agora)
        self.assertEqual(contagens["audit"], {"chamadas": 2, "auditadas": 2})

    def test_sem_auditoria_nenhuma(self):
        self._chamada(ai_features.SALES_REASONING_RACIOCINIO, datetime.now())
        self.assertEqual(database.readiness_contagens_ao_vivo()["audit"], {"chamadas": 0, "auditadas": 0})

    def test_policy_violations(self):
        database.criar_policy_violation_event(tipo="PROMPT_INJECTION", trechos_detectados=["ignore as regras"])
        self.assertEqual(database.readiness_contagens_ao_vivo()["policy_violations"], 1)


class AdminReadinessEndpointTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import api.main as _main

        cls._patches = []
        for target in (
            "api.database.criar_tabelas",
            "agent.sessao_manager.criar_tabela_sessoes",
            "agent.sessao_manager.criar_tabela_usuarios",
            "agent.visual_scenario.criar_tabela_visual_scenarios",
            "agent.sales_memory.criar_tabela_sales_memories",
        ):
            try:
                p = patch(target)
                p.start()
                cls._patches.append(p)
            except Exception:
                pass

        from fastapi.testclient import TestClient
        cls._ctx = TestClient(_main.app)
        cls.client = cls._ctx.__enter__()
        cls.admin_headers = {"Authorization": f"Bearer {_main._gerar_token('admin-1', 'admin@saleia.app.br', 'admin')}"}
        cls.vendedor_headers = {"Authorization": f"Bearer {_main._gerar_token('u1', 'v@saleia.app.br', 'vendedor')}"}

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)
        for p in cls._patches:
            p.stop()

    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                                     poolclass=StaticPool)
        SQLModel.metadata.create_all(self._engine)
        p = patch.object(database, "engine", self._engine)
        p.start()
        self.addCleanup(p.stop)

    def test_sem_token_401_e_nao_admin_403(self):
        self.assertEqual(self.client.get("/admin/readiness").status_code, 401)
        self.assertEqual(self.client.get("/admin/readiness", headers=self.vendedor_headers).status_code, 403)

    def test_admin_200_com_os_9_criterios(self):
        database.registrar_readiness_medicao("recommendation_quality", 0.456, amostra=180)
        r = self.client.get("/admin/readiness", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body["criterios"]), 9)
        self.assertEqual(body["janela_dias"], 7)
        c = {x["criterio"]: x for x in body["criterios"]}
        self.assertEqual(c["recommendation_quality"]["valor"], 0.456)
        self.assertIn("pronto_para_digital_twin", body["resumo"])

    def test_dias_invalido_422(self):
        self.assertEqual(self.client.get("/admin/readiness?dias=0", headers=self.admin_headers).status_code, 422)


if __name__ == "__main__":
    unittest.main()
