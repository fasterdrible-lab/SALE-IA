"""
Testes — Tarefa B1 (Data Quality, seção 33 do PROMPT MESTRE V2).

Cobre agent/data_quality_rules.py (função pura), api/database.py::
coletar_dados_qualidade (SQLite em memória) e GET /admin/data-quality
(mesmo padrão de tests/test_observability_endpoint.py).

Run:
    python -m unittest tests.test_data_quality -v
"""
import logging
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

from agent.data_quality_rules import (
    DATA_QUALITY_CHECKS,
    gerar_relatorio_qualidade,
    verificar_meetings,
    verificar_opportunities,
    verificar_recommendation_events,
    verificar_sales_events,
)

logging.disable(logging.CRITICAL)

AGORA = datetime(2026, 9, 24, 12, 0, 0)


def _item(itens, codigo, tabela):
    return next(i for i in itens if i["codigo"] == codigo and i["tabela"] == tabela)


def _opp(id_, **kw):
    base = {"id": id_, "seller_id": "u1", "status": "open", "estimated_value": 1000.0, "outcome_value": None,
            "product": None, "loss_reason": None, "created_at": AGORA - timedelta(days=5),
            "close_date": None, "won_at": None, "lost_at": None}
    base.update(kw)
    return base


class VocabularioTest(unittest.TestCase):
    def test_sete_codigos_literais_da_secao_33(self):
        self.assertEqual(set(DATA_QUALITY_CHECKS), {
            "missing_seller_id", "missing_opportunity_id", "negative_deal_value", "invalid_timestamps",
            "duplicate_events", "orphan_meetings", "unknown_outcomes",
        })


class VerificarMeetingsTest(unittest.TestCase):
    def setUp(self):
        t = AGORA - timedelta(hours=1)
        self.meetings = [
            {"meeting_id": "ok", "usuario_id": "u1", "opportunity_id": 1, "created_at": t, "updated_at": t},
            {"meeting_id": "anonima", "usuario_id": None, "opportunity_id": None, "created_at": t, "updated_at": t},
            {"meeting_id": "orfa", "usuario_id": "u1", "opportunity_id": 99, "created_at": t, "updated_at": t},
            {"meeting_id": "futura", "usuario_id": "u1", "opportunity_id": 1,
             "created_at": AGORA + timedelta(days=1), "updated_at": AGORA + timedelta(days=1)},
            {"meeting_id": "invertida", "usuario_id": "u1", "opportunity_id": 1,
             "created_at": t, "updated_at": t - timedelta(hours=2)},
        ]
        self.itens = verificar_meetings(self.meetings, {1}, AGORA)

    def test_missing_seller_e_opportunity(self):
        self.assertEqual(_item(self.itens, "missing_seller_id", "meeting_memory")["exemplos"], ["anonima"])
        self.assertEqual(_item(self.itens, "missing_opportunity_id", "meeting_memory")["exemplos"], ["anonima"])

    def test_orfa_aponta_para_opportunity_inexistente(self):
        self.assertEqual(_item(self.itens, "orphan_meetings", "meeting_memory")["exemplos"], ["orfa"])

    def test_timestamps_futuro_e_invertido(self):
        self.assertEqual(sorted(_item(self.itens, "invalid_timestamps", "meeting_memory")["exemplos"]),
                         ["futura", "invertida"])

    def test_taxa_e_avaliados(self):
        i = _item(self.itens, "orphan_meetings", "meeting_memory")
        self.assertEqual((i["avaliados"], i["problemas"], i["taxa"]), (5, 1, 0.2))

    def test_tolerancia_de_relogio_nao_acusa_futuro_proximo(self):
        m = [{"meeting_id": "x", "usuario_id": "u", "opportunity_id": None,
              "created_at": AGORA + timedelta(minutes=2), "updated_at": AGORA + timedelta(minutes=2)}]
        self.assertEqual(_item(verificar_meetings(m, set(), AGORA), "invalid_timestamps", "meeting_memory")["problemas"], 0)


class VerificarOpportunitiesTest(unittest.TestCase):
    def test_valor_negativo(self):
        itens = verificar_opportunities([_opp(1), _opp(2, estimated_value=-5.0), _opp(3, outcome_value=-1.0)], AGORA)
        self.assertEqual(_item(itens, "negative_deal_value", "opportunities")["exemplos"], [2, 3])

    def test_close_date_antes_da_criacao(self):
        o = _opp(1, status="won", outcome_value=10.0, product="X",
                 close_date=AGORA - timedelta(days=10), won_at=AGORA)
        itens = verificar_opportunities([o], AGORA)
        self.assertEqual(_item(itens, "invalid_timestamps", "opportunities")["exemplos"], [1])

    def test_close_date_no_mesmo_dia_da_criacao_e_valido(self):
        criado = datetime(2026, 9, 20, 15, 0)
        o = _opp(1, status="won", outcome_value=10.0, product="X", created_at=criado,
                 close_date=datetime(2026, 9, 20, 0, 0), won_at=criado)
        self.assertEqual(_item(verificar_opportunities([o], AGORA), "invalid_timestamps", "opportunities")["problemas"], 0)

    def test_desfechos_desconhecidos(self):
        opps = [
            _opp(1),                                                  # aberta recente: ok
            _opp(2, created_at=AGORA - timedelta(days=200)),           # aberta há muito tempo
            _opp(3, status="won", outcome_value=None, product="X", close_date=AGORA),   # won sem valor
            _opp(4, status="lost", loss_reason=""),                    # lost sem motivo
            _opp(5, status="talvez"),                                  # status fora do vocabulário
            _opp(6, status="lost", loss_reason="preço"),               # ok
            _opp(7, status="abandoned"),                               # ok
        ]
        itens = verificar_opportunities(opps, AGORA)
        self.assertEqual(_item(itens, "unknown_outcomes", "opportunities")["exemplos"], [2, 3, 4, 5])

    def test_dias_sem_desfecho_configuravel(self):
        opps = [_opp(1, created_at=AGORA - timedelta(days=40))]
        self.assertEqual(_item(verificar_opportunities(opps, AGORA), "unknown_outcomes", "opportunities")["problemas"], 0)
        self.assertEqual(_item(verificar_opportunities(opps, AGORA, dias_sem_desfecho=30),
                               "unknown_outcomes", "opportunities")["problemas"], 1)


class VerificarEventosTest(unittest.TestCase):
    def test_recommendation_duplicada_na_janela_curta(self):
        t = AGORA - timedelta(hours=1)
        eventos = [
            {"id": 1, "meeting_id": "m1", "opportunity_id": 1, "recommendation": "Pergunte o orçamento.", "shown_at": t, "used_at": None},
            {"id": 2, "meeting_id": "m1", "opportunity_id": 1, "recommendation": "pergunte o  orçamento.", "shown_at": t + timedelta(minutes=1), "used_at": None},
            {"id": 3, "meeting_id": "m1", "opportunity_id": 1, "recommendation": "Pergunte o orçamento.", "shown_at": t + timedelta(minutes=30), "used_at": None},
            {"id": 4, "meeting_id": "m2", "opportunity_id": None, "recommendation": "Pergunte o orçamento.", "shown_at": t, "used_at": t - timedelta(minutes=1)},
        ]
        itens = verificar_recommendation_events(eventos, {"m1"}, AGORA)
        self.assertEqual(_item(itens, "duplicate_events", "recommendation_events")["exemplos"], [2])
        self.assertEqual(_item(itens, "orphan_meetings", "recommendation_events")["exemplos"], [4])
        self.assertEqual(_item(itens, "missing_opportunity_id", "recommendation_events")["exemplos"], [4])
        self.assertEqual(_item(itens, "invalid_timestamps", "recommendation_events")["exemplos"], [4])

    def test_sales_event_duplicado(self):
        t = AGORA - timedelta(hours=1)
        eventos = [
            {"id": 1, "meeting_id": "m1", "seller_id": "u1", "event_type": "OBJECTION_RAISED", "evidence_quote": "Achei caro", "timestamp": t},
            {"id": 2, "meeting_id": "m1", "seller_id": "u1", "event_type": "OBJECTION_RAISED", "evidence_quote": "achei caro", "timestamp": t + timedelta(seconds=30)},
            {"id": 3, "meeting_id": "m1", "seller_id": None, "event_type": "PAIN_DETECTED", "evidence_quote": "Achei caro", "timestamp": t},
        ]
        itens = verificar_sales_events(eventos, {"m1"}, AGORA)
        self.assertEqual(_item(itens, "duplicate_events", "sales_events")["exemplos"], [2])
        self.assertEqual(_item(itens, "missing_seller_id", "sales_events")["exemplos"], [3])


class RelatorioTest(unittest.TestCase):
    def test_vazio_e_ok_com_taxas_none(self):
        r = gerar_relatorio_qualidade({}, AGORA)
        self.assertTrue(r["ok"])
        self.assertEqual((r["total_erros"], r["total_avisos"]), (0, 0))
        self.assertTrue(all(i["taxa"] is None for i in r["verificacoes"]))

    def test_aviso_nao_derruba_ok_mas_erro_derruba(self):
        t = AGORA - timedelta(hours=1)
        dados = {"meetings": [{"meeting_id": "a", "usuario_id": None, "opportunity_id": None, "created_at": t, "updated_at": t}]}
        self.assertTrue(gerar_relatorio_qualidade(dados, AGORA)["ok"])
        dados["opportunities"] = [_opp(1, estimated_value=-1.0)]
        r = gerar_relatorio_qualidade(dados, AGORA)
        self.assertFalse(r["ok"])
        self.assertEqual(r["total_erros"], 1)

    def test_ordem_segue_a_secao_33(self):
        codigos = [i["codigo"] for i in gerar_relatorio_qualidade({}, AGORA)["verificacoes"]]
        ordem = list(DATA_QUALITY_CHECKS)
        self.assertEqual(codigos, sorted(codigos, key=ordem.index))


class ColetarEEndpointTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import api.main as _main
        from api import database

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
        cls._database = database
        cls.admin_headers = {"Authorization": f"Bearer {_main._gerar_token('admin-1', 'admin@saleia.app.br', 'admin')}"}
        cls.vendedor_headers = {"Authorization": f"Bearer {_main._gerar_token('u1', 'vendedor@saleia.app.br', 'vendedor')}"}

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)
        for p in cls._patches:
            p.stop()

    def setUp(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)
        p = patch.object(self._database, "engine", engine)
        p.start()
        self.addCleanup(p.stop)
        self._database.registrar_transcricao_meeting("m-anonima", "Cliente: uma fala qualquer suficiente")
        self._database.criar_opportunity(client_id="c1", seller_id="u1", estimated_value=-10.0)

    def test_coletar_nao_traz_transcricao(self):
        dados = self._database.coletar_dados_qualidade()
        self.assertEqual(len(dados["meetings"]), 1)
        self.assertNotIn("transcript_full", dados["meetings"][0])
        self.assertIsInstance(dados["opportunities"][0]["created_at"], datetime)

    def test_sem_token_401_e_nao_admin_403(self):
        self.assertEqual(self.client.get("/admin/data-quality").status_code, 401)
        self.assertEqual(self.client.get("/admin/data-quality", headers=self.vendedor_headers).status_code, 403)

    def test_admin_200_detecta_problemas_reais(self):
        r = self.client.get("/admin/data-quality", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertFalse(d["ok"])
        neg = _item(d["verificacoes"], "negative_deal_value", "opportunities")
        self.assertEqual(neg["problemas"], 1)
        self.assertEqual(_item(d["verificacoes"], "missing_seller_id", "meeting_memory")["exemplos"], ["m-anonima"])

    def test_dias_sem_desfecho_invalido_422(self):
        r = self.client.get("/admin/data-quality?dias_sem_desfecho=0", headers=self.admin_headers)
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()
