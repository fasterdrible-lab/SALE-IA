"""
Testes — V.1.4.181: sessão encerrada quando o vendedor sai da chamada.

Antes, o Dashboard só deixava de mostrar "Ao vivo" 5 min depois do último
envio, e uma aba esquecida aberta seguia "ao vivo" (teste real, 15/10/2026).

Run:
    python -m unittest tests.test_sessao_encerrada -v
"""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from agent import sessao_manager as sm


class _Cursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.conn.sqls.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.conn.linha


class _Conn:
    def __init__(self, linha):
        self.linha = linha
        self.sqls = []
        self.commits = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


class TestSessaoEncerrada(unittest.TestCase):
    def _com(self, linha):
        conn = _Conn(linha)
        return conn, patch.object(sm, "_get_conn", return_value=conn)

    def test_encerra_a_sessao_ativa_sem_mexer_no_updated_at(self):
        conn, p = self._com((42, "Vendedor: oi", 3))
        with p:
            self.assertTrue(sm.encerrar_sessao("abc-defg-hij"))
        ultimo = conn.sqls[-1]
        self.assertIn("SET encerrada_em = NOW(), updated_at = updated_at WHERE id = %s", ultimo[0])
        self.assertEqual(ultimo[1], (42,))
        self.assertEqual(conn.commits, 1)

    def test_sem_sessao_ativa_nao_encerra_nada(self):
        conn, p = self._com(None)
        with p:
            self.assertFalse(sm.encerrar_sessao("abc-defg-hij"))
        self.assertFalse(any("UPDATE" in s for s, _ in conn.sqls))

    def test_voltar_para_a_reuniao_reabre(self):
        conn, p = self._com((42, "", 0))
        with p:
            self.assertEqual(sm.registrar_sessao("abc-defg-hij"), 42)
        self.assertTrue(any("encerrada_em = NULL" in s for s, _ in conn.sqls))

    def test_fala_nova_reabre(self):
        conn, p = self._com((42, "", 0))
        with p, patch.object(sm, "_limpar_e_deduplicar", return_value="Vendedor: voltei"):
            sm.salvar_transcricao_bruta("abc-defg-hij", "Vendedor: voltei")
        upd = [s for s, _ in conn.sqls if s.startswith("UPDATE")]
        self.assertTrue(upd and "encerrada_em = NULL" in upd[-1])

    def test_lista_traz_encerrada_em(self):
        src = Path(sm.__file__).read_text(encoding="utf-8")
        ini = src.index("def listar_sessoes")
        trecho = src[ini:src.index("\ndef ", ini + 1)]
        self.assertIn("s.encerrada_em", trecho)


class TestEndpointEncerrarSessao(unittest.TestCase):
    def test_endpoint_chama_encerrar(self):
        from fastapi.testclient import TestClient
        import api.main as main
        with patch("agent.sessao_manager.encerrar_sessao", return_value=True) as fake:
            r = TestClient(main.app).post("/encerrar-sessao", json={"meeting_id": "abc-defg-hij"})
        self.assertEqual(r.json(), {"ok": True})
        fake.assert_called_once_with("abc-defg-hij")

    def test_dashboard_mostra_finalizada_com_encerrada_em(self):
        html = (Path(__file__).resolve().parent.parent / "frontend" / "dashboard.html").read_text(encoding="utf-8")
        trecho = html[html.index("function _statusSessao"):html.index("function _duracaoSessao")]
        self.assertLess(trecho.index("s.encerrada_em"), trecho.index("diffMin"))



class TestListaSessoesAtualizaSozinha(unittest.TestCase):
    def test_v182_lista_se_atualiza_enquanto_a_pagina_esta_aberta(self):
        html = (Path(__file__).resolve().parent.parent / "frontend" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("if (nome === 'sessoes')       { carregarSessoes(); _iniciarAutoSessoes(); }", html)
        self.assertIn("if (nome !== 'sessoes') _pararAutoSessoes();", html)
        trecho = html[html.index("function _iniciarAutoSessoes"):html.index("async function carregarSessoes")]
        self.assertIn("carregarSessoes(true)", trecho)
        self.assertIn("15000", trecho)
        detalhe = html[html.index("async function verSessaoDetalhe"):]
        self.assertLess(detalhe.index("_pararAutoSessoes()"), detalhe.index("page-sessao-detalhe"))


if __name__ == "__main__":
    unittest.main()
