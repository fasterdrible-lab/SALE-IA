"""
Testes — Tarefa B3: pipeline analítico assíncrono
(agent/sales_science_pipeline.py) e o uso do retrato em
GET /sales-science/insights.

Run:
    python -m unittest tests.test_sales_science_pipeline -v
"""
import json
import logging
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

logging.disable(logging.CRITICAL)

from agent import sales_science_pipeline as ssp


class _Isolado(unittest.TestCase):
    def setUp(self):
        from api import database
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        p = patch.object(ssp, "SNAPSHOT_PATH", Path(self._tmp.name) / "sales_science_snapshot.json")
        p.start()
        self.addCleanup(p.stop)
        self._database = database
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)
        pe = patch.object(database, "engine", engine)
        pe.start()
        self.addCleanup(pe.stop)


class ExecutarPipelineTest(_Isolado):
    def test_com_reuniao_ativa_nao_executa_nem_grava(self):
        r = ssp.executar_pipeline(contar_ativas=lambda: 2)
        self.assertFalse(r["executado"])
        self.assertIn("2 reunião", r["motivo"])
        self.assertFalse(ssp.SNAPSHOT_PATH.exists())

    def test_sem_reuniao_grava_retrato_com_payload_completo(self):
        self._database.criar_sales_evidence(meeting_id="m1", type="OBJECTION:PRICE", quote="tá caro")
        r = ssp.executar_pipeline(contar_ativas=lambda: 0)
        self.assertTrue(r["executado"])
        self.assertEqual(r["objecoes"], 1)
        dados = json.loads(ssp.SNAPSHOT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(dados["payload"]["objection_trends"]["total_objecoes"], 1)
        self.assertIn("seller_benchmark", dados["payload"])
        self.assertIsNotNone(ssp.ler_snapshot_valido())


class LerSnapshotTest(_Isolado):
    def _gravar(self, gerado_em, payload=None):
        ssp.SNAPSHOT_PATH.write_text(json.dumps({"gerado_em": gerado_em, "payload": payload or {"amostra_total": 7}}), encoding="utf-8")

    def test_ausente_ou_corrompido_e_none(self):
        self.assertIsNone(ssp.ler_snapshot_valido())
        ssp.SNAPSHOT_PATH.write_text("{quebrado", encoding="utf-8")
        self.assertIsNone(ssp.ler_snapshot_valido())

    def test_vencido_e_none(self):
        velho = datetime.now(timezone.utc) - timedelta(hours=ssp.VALIDADE_HORAS + 1)
        self._gravar(velho.isoformat())
        self.assertIsNone(ssp.ler_snapshot_valido())

    def test_data_sem_fuso_e_tratada_como_utc(self):
        recente = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        self._gravar(recente.isoformat())
        self.assertIsNotNone(ssp.ler_snapshot_valido())


class EndpointUsaRetratoTest(_Isolado):
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
        cls.headers = {"Authorization": "Bearer " + _main._gerar_token("admin-1", "admin@saleia.app.br", "admin")}

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)
        for p in cls._patches:
            p.stop()

    def test_com_retrato_recente_nao_consulta_o_banco(self):
        gerado = datetime.now(timezone.utc).isoformat(timespec="seconds")
        ssp.SNAPSHOT_PATH.write_text(json.dumps({"gerado_em": gerado, "payload": {"amostra_total": 7}}), encoding="utf-8")
        with patch("api.database.listar_opportunities", side_effect=AssertionError("não devia consultar")):
            r = self.client.get("/sales-science/insights", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["amostra_total"], 7)
        self.assertEqual(r.json()["pre_calculado"], {"gerado_em": gerado})

    def test_sem_retrato_calcula_ao_vivo(self):
        r = self.client.get("/sales-science/insights", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["pre_calculado"])
        self.assertEqual(r.json()["amostra_total"], 0)


if __name__ == "__main__":
    unittest.main()
