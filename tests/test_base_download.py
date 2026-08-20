"""
Testes — GET /base/{doc_id}/download

Cobre a Tarefa 49 do prompt de desenvolvimento (V.1.4.40): download de
documentos da Base preserva nome/extensao/conteudo original, exige JWT
valido e trata corretamente os casos de documento sem arquivo, documento
inexistente e arquivo removido do disco.

Nao requer MySQL: `agent.sessao_manager._get_conn` e mockado para devolver
uma conexao/cursor falsos que simulam a linha de `base_conhecimento`.

Run:
    python -m unittest tests.test_base_download -v
"""

import logging
import os
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote

logging.disable(logging.CRITICAL)


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    def execute(self, sql, params=None):
        pass

    def fetchone(self):
        return self._row

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, row):
        self._row = row

    def cursor(self):
        return _FakeCursor(self._row)

    def commit(self):
        pass

    def close(self):
        pass


class BaseDownloadSuite(unittest.TestCase):
    """Testes para GET /base/{doc_id}/download."""

    @classmethod
    def setUpClass(cls):
        import api.main as _main  # noqa: dispara setup a nivel de modulo

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
        cls._main = _main

        cls.token = _main._gerar_token("u1", "vendedor@saleia.app.br", "vendedor")
        cls.auth_header = {"Authorization": f"Bearer {cls.token}"}

        cls._tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        cls._tmp.write(b"%PDF-1.4 conteudo de teste")
        cls._tmp.close()
        cls.arquivo_path = cls._tmp.name

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)
        for p in cls._patches:
            p.stop()
        os.unlink(cls.arquivo_path)

    def _get(self, doc_id, row, headers=None):
        with patch("agent.sessao_manager._get_conn", return_value=_FakeConn(row)):
            return self.client.get(
                f"/base/{doc_id}/download",
                headers=headers if headers is not None else self.auth_header,
            )

    # ── autenticação ─────────────────────────────────────────

    def test_download_requires_auth(self):
        r = self._get(1, (self.arquivo_path, "Manual.pdf", "application/pdf"), headers={})
        self.assertEqual(r.status_code, 401)

    def test_download_invalid_token(self):
        r = self._get(
            1,
            (self.arquivo_path, "Manual.pdf", "application/pdf"),
            headers={"Authorization": "Bearer token-invalido"},
        )
        self.assertEqual(r.status_code, 401)

    # ── sucesso: nome/extensão/conteúdo preservados ─────────────

    def test_download_success_returns_original_content_and_filename(self):
        r = self._get(1, (self.arquivo_path, "Manual de Vendas.pdf", "application/pdf"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b"%PDF-1.4 conteudo de teste")
        self.assertIn("application/pdf", r.headers.get("content-type", ""))
        # Starlette codifica o filename (RFC 5987) quando ha espaco/acento
        self.assertIn("Manual de Vendas.pdf", unquote(r.headers.get("content-disposition", "")))

    def test_download_success_docx_mime_preserved(self):
        r = self._get(
            2,
            (self.arquivo_path, "Playbook.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("wordprocessingml", r.headers.get("content-type", ""))

    # ── casos de erro ────────────────────────────────────────

    def test_download_documento_sem_arquivo_original(self):
        r = self._get(3, (None, None, None))
        self.assertEqual(r.status_code, 404)
        self.assertIn("arquivo original", r.json()["detail"])

    def test_download_documento_inexistente(self):
        r = self._get(999, None)
        self.assertEqual(r.status_code, 404)

    def test_download_arquivo_removido_do_disco(self):
        r = self._get(4, ("/caminho/que/nao/existe.pdf", "Sumiu.pdf", "application/pdf"))
        self.assertEqual(r.status_code, 404)
        self.assertIn("não encontrado no servidor", r.json()["detail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
