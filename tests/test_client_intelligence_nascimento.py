"""
Testes — dia/mês de nascimento em agent/client_intelligence.py (camada de
astrologia opcional). Cobre: salvar_nascimento_cliente nunca sobrescreve
(WHERE ... IS NULL), migração idempotente, e _deserializar_cliente anexa
perfil_astrologico quando há dia/mês salvos.

Não requer MySQL: `_get_conn()` é substituído por uma conexão fake que só
registra as chamadas (mesmo padrão de tests/test_sales_brain_approval.py).

Run:
    python -m unittest tests.test_client_intelligence_nascimento -v
"""

import logging
import unittest
from unittest.mock import patch

logging.disable(logging.CRITICAL)

import agent.client_intelligence as client_intelligence
from agent.client_intelligence import _deserializar_cliente, salvar_nascimento_cliente


class _RecordingCursor:
    def __init__(self, rowcount=1):
        self.calls = []
        self.rowcount = rowcount

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _RecordingConn:
    def __init__(self, rowcount=1):
        self.cursor_obj = _RecordingCursor(rowcount)

    def cursor(self):
        return self.cursor_obj

    def close(self):
        pass


class SalvarNascimentoClienteTest(unittest.TestCase):
    def test_update_tem_clausula_is_null_para_nunca_sobrescrever(self):
        conn = _RecordingConn(rowcount=1)
        with patch.object(client_intelligence, "_get_conn", return_value=conn):
            ok = salvar_nascimento_cliente("c1", 15, 3)
        self.assertTrue(ok)
        sql, params = conn.cursor_obj.calls[0]
        self.assertIn("data_nascimento_dia IS NULL", sql)
        self.assertIn(15, params)
        self.assertIn(3, params)
        self.assertIn("c1", params)

    def test_rowcount_zero_retorna_false_quando_ja_definido(self):
        conn = _RecordingConn(rowcount=0)  # simula UPDATE que não bateu no WHERE (já tinha valor)
        with patch.object(client_intelligence, "_get_conn", return_value=conn):
            ok = salvar_nascimento_cliente("c1", 15, 3)
        self.assertFalse(ok)

    def test_falha_de_conexao_nao_lanca(self):
        with patch.object(client_intelligence, "_get_conn", side_effect=RuntimeError("sem banco")):
            ok = salvar_nascimento_cliente("c1", 15, 3)
        self.assertFalse(ok)


class DeserializarClientePerfilAstrologicoTest(unittest.TestCase):
    def test_com_dia_e_mes_anexa_perfil_astrologico(self):
        row = {"nome": "Cliente X", "data_nascimento_dia": 21, "data_nascimento_mes": 3}
        resultado = _deserializar_cliente(dict(row))
        self.assertIsNotNone(resultado["perfil_astrologico"])
        self.assertEqual(resultado["perfil_astrologico"]["nome"], "Áries")

    def test_sem_dia_ou_mes_perfil_astrologico_e_none(self):
        resultado = _deserializar_cliente({"nome": "Cliente Y"})
        self.assertIsNone(resultado["perfil_astrologico"])

    def test_sem_dia_e_mes_parcial_perfil_astrologico_e_none(self):
        resultado = _deserializar_cliente({"nome": "Cliente Z", "data_nascimento_dia": 21, "data_nascimento_mes": None})
        self.assertIsNone(resultado["perfil_astrologico"])


if __name__ == "__main__":
    unittest.main()
