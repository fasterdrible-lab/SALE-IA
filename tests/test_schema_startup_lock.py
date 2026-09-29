"""
Testes — Tarefa D8: DDL do startup serializado entre workers.

Cobre api/database.py::_erro_tabela_ja_existe (1050/1684),
_criar_metadata_tolerante (nova tentativa após corrida) e lock_de_schema
(GET_LOCK nomeado do MySQL; SQLite sem lock; nunca impede o boot).

Run:
    python -m unittest tests.test_schema_startup_lock -v
"""
import logging
import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import OperationalError

import api.database as db

logging.disable(logging.CRITICAL)


def _op_error(codigo, msg):
    return OperationalError("CREATE TABLE x", {}, Exception(codigo, msg))


class ErroTabelaJaExisteTest(unittest.TestCase):
    def test_1050_e_1684_sao_corrida_benigna(self):
        self.assertTrue(db._erro_tabela_ja_existe(_op_error(1050, "Table 'x' already exists")))
        self.assertTrue(db._erro_tabela_ja_existe(_op_error(
            1684, "Table 'x' was skipped since its definition is being modified by concurrent DDL statement")))

    def test_outros_erros_nao(self):
        self.assertFalse(db._erro_tabela_ja_existe(_op_error(2003, "Can't connect to MySQL server")))
        self.assertFalse(db._erro_tabela_ja_existe(_op_error(1045, "Access denied")))


class CriarMetadataTolerranteTest(unittest.TestCase):
    def test_corrida_na_1a_passada_tenta_de_novo(self):
        with patch.object(db.SQLModel.metadata, "create_all",
                          side_effect=[_op_error(1684, "concurrent DDL"), None]) as ca, \
             patch.object(db.time, "sleep"):
            db._criar_metadata_tolerante()
        self.assertEqual(ca.call_count, 2)

    def test_corrida_nas_2_passadas_nao_derruba_o_boot(self):
        with patch.object(db.SQLModel.metadata, "create_all",
                          side_effect=[_op_error(1050, "already exists")] * 2) as ca, \
             patch.object(db.time, "sleep"):
            db._criar_metadata_tolerante()
        self.assertEqual(ca.call_count, 2)

    def test_erro_real_propaga(self):
        with patch.object(db.SQLModel.metadata, "create_all", side_effect=_op_error(1045, "Access denied")):
            with self.assertRaises(OperationalError):
                db._criar_metadata_tolerante()


class LockDeSchemaTest(unittest.TestCase):
    def _engine_mysql(self, resultado_get_lock=1, falha_connect=False):
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = resultado_get_lock
        engine = MagicMock()
        engine.dialect.name = "mysql"
        if falha_connect:
            engine.connect.side_effect = RuntimeError("mysql fora")
        else:
            engine.connect.return_value = conn
        return engine, conn

    def _sqls(self, conn):
        return [str(c.args[0]) for c in conn.execute.call_args_list]

    def test_sqlite_nao_usa_lock(self):
        engine = MagicMock()
        engine.dialect.name = "sqlite"
        with patch.object(db, "engine", engine):
            with db.lock_de_schema():
                pass
        engine.connect.assert_not_called()

    def test_mysql_obtem_e_libera_o_lock(self):
        engine, conn = self._engine_mysql(1)
        executou = []
        with patch.object(db, "engine", engine):
            with db.lock_de_schema(timeout_s=5):
                executou.append(True)
        sqls = self._sqls(conn)
        self.assertIn("GET_LOCK", sqls[0])
        self.assertIn("RELEASE_LOCK", sqls[1])
        self.assertEqual(conn.execute.call_args_list[0].args[1], {"n": "saleia_schema_startup", "t": 5})
        self.assertEqual(executou, [True])
        conn.close.assert_called_once()

    def test_lock_nao_obtido_segue_sem_liberar(self):
        engine, conn = self._engine_mysql(0)
        executou = []
        with patch.object(db, "engine", engine):
            with db.lock_de_schema():
                executou.append(True)
        self.assertEqual(executou, [True])
        self.assertFalse(any("RELEASE_LOCK" in s for s in self._sqls(conn)))
        conn.close.assert_called_once()

    def test_falha_de_conexao_nunca_impede_o_boot(self):
        engine, _ = self._engine_mysql(falha_connect=True)
        executou = []
        with patch.object(db, "engine", engine):
            with db.lock_de_schema():
                executou.append(True)
        self.assertEqual(executou, [True])

    def test_libera_o_lock_mesmo_se_o_ddl_falhar(self):
        engine, conn = self._engine_mysql(1)
        with patch.object(db, "engine", engine):
            with self.assertRaises(ValueError):
                with db.lock_de_schema():
                    raise ValueError("ddl quebrou")
        self.assertIn("RELEASE_LOCK", self._sqls(conn)[-1])


class StartupUsaLockTest(unittest.TestCase):
    def test_on_startup_roda_o_ddl_dentro_do_lock(self):
        import asyncio

        import api.main as main

        ordem = []

        class _Lock:
            def __enter__(self):
                ordem.append("lock")

            def __exit__(self, *a):
                ordem.append("unlock")

        with patch("api.database.lock_de_schema", return_value=_Lock()), \
             patch.object(main, "_inicializar_schema", side_effect=lambda: ordem.append("ddl")), \
             patch.object(main, "_configurar_logging"), \
             patch.object(main, "_loop_metricas", new=MagicMock(return_value=None)), \
             patch.object(main.asyncio, "create_task"):
            asyncio.run(main.on_startup())
        self.assertEqual(ordem, ["lock", "ddl", "unlock"])


if __name__ == "__main__":
    unittest.main()
