"""
Testes — api/metricas_historico.py (vazamento de conexão SQLite).

Regressão do incidente de 10-11/10/2026: `with sqlite3.connect()` só faz
commit/rollback e nunca fechava a conexão; o loop de métricas (1x/min por
worker) vazou 1 descritor por chamada até bater o limite de 1024 e a API
inteira passou a devolver 502.

Run:
    python -m unittest tests.test_metricas_historico -v
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from api import metricas_historico as mh


class TestConexoesSempreFechadas(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._path = mock.patch.object(mh, "_DB_PATH", Path(self._tmp.name) / "m.db")
        self._path.start()
        self.abertas = []
        connect_real = sqlite3.connect

        def connect_rastreado(*a, **kw):
            conn = connect_real(*a, **kw)
            self.abertas.append(conn)
            return conn

        self._connect = mock.patch.object(mh.sqlite3, "connect", connect_rastreado)
        self._connect.start()

    def tearDown(self):
        self._connect.stop()
        self._path.stop()
        self._tmp.cleanup()

    def _assert_todas_fechadas(self):
        self.assertTrue(self.abertas)
        for conn in self.abertas:
            with self.assertRaises(sqlite3.ProgrammingError):
                conn.execute("SELECT 1")

    def test_todas_as_funcoes_fecham_a_conexao(self):
        mh.criar_tabela_metricas()
        mh.criar_tabela_teste_provedores()
        self.assertTrue(mh.registrar({"latencia_ms": 2.0, "banco": "mysql"}, 1, 3))
        self.assertFalse(mh.registrar({}, 0, 0))  # dedup: retorno antecipado
        mh.obter(6)
        mh.salvar_teste_provedor("deepseek", True, 1.0, "ok")
        mh.ler_testes_provedores()
        self.assertEqual(len(self.abertas), 7)
        self._assert_todas_fechadas()

    def test_dados_persistem_apos_fechar(self):
        mh.criar_tabela_metricas()
        mh.criar_tabela_teste_provedores()
        mh.registrar({"latencia_ms": 2.0, "banco": "mysql"}, 1, 3)
        mh.salvar_teste_provedor("openai", False, 5.0, "429")
        self.assertEqual(mh.obter(1)[0]["reunioes_hoje"], 3)
        self.assertEqual(mh.ler_testes_provedores()["openai"]["detalhe"], "429")

    def test_erro_faz_rollback_e_fecha(self):
        mh.criar_tabela_metricas()
        with self.assertRaises(sqlite3.OperationalError):
            with mh._conn() as db:
                db.execute("INSERT INTO metricas_historico (ts) VALUES (1)")
                db.execute("SELECT * FROM tabela_inexistente")
        with mh._conn() as db:
            total = db.execute("SELECT COUNT(*) FROM metricas_historico").fetchone()[0]
        self.assertEqual(total, 0)
        self._assert_todas_fechadas()


if __name__ == "__main__":
    unittest.main()
