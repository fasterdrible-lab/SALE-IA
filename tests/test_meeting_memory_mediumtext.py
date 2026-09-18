"""
Testes — colunas JSON de MeetingMemory precisam ser MEDIUMTEXT no MySQL
(TEXT trunca em 64KB, achado real em produção em 18/09/2026 com
key_moments_json; mesmo fix já aplicado 2x antes neste projeto,
V.1.4.54 e V.1.4.100, para outras colunas).

Nunca reproduz o bug de verdade (SQLite não tem o limite de 64KB do
MySQL TEXT) — só confirma que o tipo de coluna compila para MEDIUMTEXT
sob o dialeto MySQL, pra nenhuma edição futura reintroduzir Text puro
por acidente.

Run:
    python -m unittest tests.test_meeting_memory_mediumtext -v
"""
import unittest

from sqlalchemy.dialects import mysql

from api.database import MeetingMemory

_COLUNAS_MEDIUMTEXT = (
    "transcript_full",
    "transcript_buffer",
    "accumulated_summary",
    "current_diagnosis",
    "score_history_json",
    "key_moments_json",
    "events_json",
)


class MeetingMemoryColunasMediumtextTest(unittest.TestCase):
    def test_todas_as_colunas_json_longas_compilam_para_mediumtext_no_mysql(self):
        for nome_coluna in _COLUNAS_MEDIUMTEXT:
            coluna = MeetingMemory.__table__.c[nome_coluna]
            compilado = str(coluna.type.compile(dialect=mysql.dialect()))
            self.assertEqual(compilado, "MEDIUMTEXT", f"{nome_coluna} deveria compilar para MEDIUMTEXT, veio {compilado}")


if __name__ == "__main__":
    unittest.main()
