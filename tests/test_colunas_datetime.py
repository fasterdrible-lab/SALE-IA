"""
Testes — V.1.4.198: nenhuma coluna de data exige fuso horário.

O SALE-IA grava datas sem fuso (UTC da VPS) em todo o código. O sqlmodel
>= 0.0.4x passou a mapear `campo: datetime` sem `sa_column` para
`UTCDateTime`, que recusa datetime sem fuso no INSERT. Com o 0.0.48 na VPS
(desde 21/10/2026), todo relatório automático falhou de 27/10 a 06/11.
Este teste falha nessa versão se algum modelo voltar a declarar data sem
coluna explícita.

Run:
    python -m unittest tests.test_colunas_datetime -v
"""
import unittest
from datetime import datetime

from sqlalchemy import DateTime
from sqlmodel import SQLModel

import api.database  # noqa: F401 — registra os modelos


class ColunasDatetimeTest(unittest.TestCase):
    def test_nenhuma_coluna_de_data_exige_fuso(self):
        problemas = []
        for tabela in SQLModel.metadata.sorted_tables:
            for coluna in tabela.columns:
                tipo = coluna.type
                if type(tipo).__name__ == "UTCDateTime" or (isinstance(tipo, DateTime) and tipo.timezone):
                    problemas.append(f"{tabela.name}.{coluna.name} ({type(tipo).__name__})")
        self.assertEqual(problemas, [], "colunas que recusam datetime sem fuso")

    def test_relatorio_aceita_datetime_sem_fuso(self):
        coluna = api.database.Relatorio.__table__.columns["criado_em"]
        self.assertIs(type(coluna.type), DateTime)
        self.assertFalse(coluna.nullable)
        bind = coluna.type.bind_processor(api.database.engine.dialect)
        valor = datetime(2026, 11, 6, 12, 0, 0)
        self.assertIsNotNone(bind(valor) if bind else valor)


if __name__ == "__main__":
    unittest.main()
