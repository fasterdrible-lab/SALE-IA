"""
Testes unitários — agent/knowledge_graph.py (Sales Brain Fase 7.2).

Não exigem banco real: `_get_conn()` é substituído por uma conexão fake
(mesmo padrão de tests/test_sales_brain_approval.py).

Run:
    python -m unittest tests.test_knowledge_graph -v
"""
import logging
import unittest
from unittest.mock import patch

logging.disable(logging.CRITICAL)

import agent.knowledge_graph as knowledge_graph
from agent.knowledge_graph import TIPOS_VALIDOS, buscar_conexoes, registrar_aresta


class _RecordingCursor:
    def __init__(self, rows=None):
        self.calls = []
        self._rows = rows or []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _RecordingConn:
    def __init__(self, rows=None):
        self.cursor_obj = _RecordingCursor(rows)

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        pass

    def close(self):
        pass


class RegistrarArestaTest(unittest.TestCase):
    def test_tipo_invalido_retorna_false_sem_gravar(self):
        conn = _RecordingConn()
        with patch.object(knowledge_graph, "_get_conn", return_value=conn):
            ok = registrar_aresta("invalido", "1", "reuniao", "m1", "x")
        self.assertFalse(ok)
        self.assertEqual(conn.cursor_obj.calls, [])

    def test_id_vazio_retorna_false_sem_gravar(self):
        conn = _RecordingConn()
        with patch.object(knowledge_graph, "_get_conn", return_value=conn):
            ok = registrar_aresta("cliente", "", "reuniao", "m1", "x")
        self.assertFalse(ok)

    def test_aresta_valida_grava_com_insert_ignore(self):
        conn = _RecordingConn()
        with patch.object(knowledge_graph, "_get_conn", return_value=conn):
            ok = registrar_aresta("cliente", "c1", "reuniao", "m1", "teve_reuniao")
        self.assertTrue(ok)
        sql, params = conn.cursor_obj.calls[0]
        self.assertIn("INSERT IGNORE", sql)
        self.assertIn("cliente", params)
        self.assertIn("c1", params)
        self.assertIn("m1", params)

    def test_falha_de_conexao_nao_lanca(self):
        with patch.object(knowledge_graph, "_get_conn", side_effect=RuntimeError("sem banco")):
            ok = registrar_aresta("cliente", "c1", "reuniao", "m1", "teve_reuniao")
        self.assertFalse(ok)


class BuscarConexoesTest(unittest.TestCase):
    def test_tipo_invalido_retorna_vazio(self):
        self.assertEqual(buscar_conexoes("invalido", "x"), [])

    def test_id_vazio_retorna_vazio(self):
        self.assertEqual(buscar_conexoes("cliente", ""), [])

    def test_resolve_direcao_saida_e_entrada(self):
        rows = [
            {"from_type": "cliente", "from_id": "c1", "to_type": "reuniao", "to_id": "m1",
             "relacao": "teve_reuniao", "created_at": None},
            {"from_type": "reuniao", "from_id": "m1", "to_type": "playbook", "to_id": "p1",
             "relacao": "gerou_playbook", "created_at": None},
        ]
        conn = _RecordingConn(rows)
        with patch.object(knowledge_graph, "_get_conn", return_value=conn), \
             patch.object(knowledge_graph, "_resolver_rotulo", return_value="Rótulo"):
            conexoes = buscar_conexoes("reuniao", "m1")
        self.assertEqual(len(conexoes), 2)
        direcoes = {c["direcao"] for c in conexoes}
        self.assertEqual(direcoes, {"saida", "entrada"})
        # aresta 1: reuniao é o destino (to_type) -> entrada, outro lado é cliente c1
        entrada = next(c for c in conexoes if c["direcao"] == "entrada")
        self.assertEqual(entrada["tipo"], "cliente")
        self.assertEqual(entrada["id"], "c1")
        # aresta 2: reuniao é a origem (from_type) -> saida, outro lado é playbook p1
        saida = next(c for c in conexoes if c["direcao"] == "saida")
        self.assertEqual(saida["tipo"], "playbook")
        self.assertEqual(saida["id"], "p1")

    def test_erro_de_conexao_retorna_vazio_sem_lancar(self):
        with patch.object(knowledge_graph, "_get_conn", side_effect=RuntimeError("sem banco")):
            self.assertEqual(buscar_conexoes("cliente", "c1"), [])

    def test_todos_os_tipos_esperados_estao_presentes(self):
        self.assertEqual(TIPOS_VALIDOS, {"cliente", "reuniao", "memoria", "playbook", "skill"})


if __name__ == "__main__":
    unittest.main()
