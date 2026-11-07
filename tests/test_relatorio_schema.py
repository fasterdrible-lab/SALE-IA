"""
Testes — V.1.4.199: `relatorio.dados_json` cabe um relatório inteiro.

Na VPS nova (21/10/2026) a tabela `relatorio` nasceu com `dados_json`
VARCHAR(255) (campo `str` sem `sa_column`), e nenhum relatório coube:
DataError de 19 a 21/10 e, depois do erro de fuso (V.1.4.198), de novo.

Run:
    python -m unittest tests.test_relatorio_schema -v
"""
import json
import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy import String, Text
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

import api.database as db


class ModeloTest(unittest.TestCase):
    def test_dados_json_e_texto_longo(self):
        coluna = db.Relatorio.__table__.columns["dados_json"]
        self.assertIsInstance(coluna.type, Text)
        self.assertFalse(coluna.nullable)
        ddl = str(CreateTable(db.Relatorio.__table__).compile(dialect=mysql.dialect()))
        self.assertIn("dados_json MEDIUMTEXT NOT NULL", ddl)

    def test_nenhuma_coluna_json_e_varchar(self):
        from sqlmodel import SQLModel
        problemas = [
            f"{t.name}.{c.name}"
            for t in SQLModel.metadata.sorted_tables
            for c in t.columns
            if (c.name.endswith("_json") or c.name in ("dados", "conteudo"))
            and isinstance(c.type, String) and not isinstance(c.type, Text)
        ]
        self.assertEqual(problemas, [])

    def test_relatorio_grande_grava_e_le(self):
        dados = {"recapitulacao": {"resumo_executivo": "x" * 30_000}}
        salvo = db.salvar_relatorio("schema-teste-1", "teste", dados)
        try:
            self.assertEqual(db.buscar_relatorio("schema-teste-1"), dados)
        finally:
            from sqlmodel import Session
            with Session(db.engine) as s:
                s.delete(s.get(db.Relatorio, salvo.id))
                s.commit()


def _inspetor(tipo):
    inspetor = MagicMock()
    inspetor.get_table_names.return_value = ["relatorio"]
    inspetor.get_columns.return_value = [{"name": "dados_json", "type": tipo}]
    return inspetor


class MigracaoTest(unittest.TestCase):
    def _rodar(self, dialeto, tipo):
        motor = MagicMock()
        motor.dialect.name = dialeto
        conexao = motor.begin.return_value.__enter__.return_value
        with patch.object(db, "engine", motor), patch("sqlalchemy.inspect", return_value=_inspetor(tipo)):
            alterou = db.migrar_coluna_relatorio_dados()
        return alterou, [str(c.args[0]) for c in conexao.execute.call_args_list]

    def test_varchar_no_mysql_vira_mediumtext(self):
        alterou, sqls = self._rodar("mysql", mysql.VARCHAR(255))
        self.assertTrue(alterou)
        self.assertEqual(sqls, ["ALTER TABLE relatorio MODIFY dados_json MEDIUMTEXT NOT NULL"])

    def test_ja_texto_nao_altera(self):
        for tipo in (mysql.MEDIUMTEXT(), mysql.TEXT(), mysql.LONGTEXT()):
            self.assertEqual(self._rodar("mysql", tipo), (False, []))

    def test_fora_do_mysql_nao_altera(self):
        self.assertEqual(self._rodar("sqlite", String(255)), (False, []))


if __name__ == "__main__":
    unittest.main()
