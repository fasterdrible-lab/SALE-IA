"""
Smoke tests — verify that the three critical endpoints start and respond correctly.

These tests do NOT require external services (MySQL, DeepSeek, OpenAI etc.).
Database startup calls are patched; AI calls return a fixed fake response.

Run:
    python -m unittest tests.test_smoke -v
"""

import io
import logging
import os
import unittest
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

logging.disable(logging.CRITICAL)

# Minimal AI response — smoke tests only check structure, not content
_FAKE_AI = {
    "ok": "smoke",
    "probabilidade_fechamento": "alta",
    "perfil_primario": "D",
    "produto_recomendado": "intermediario",
    "faturamento_mensal": "nao mencionado",
}


class SmokeSuite(unittest.TestCase):
    """Smoke tests — Fase 0 (SALE-IA V2): /health, /dashboard,
    /recapitulacao-manual, /auth/login, /iniciar-sessao, Biblioteca
    (Knowledge Compiler) e /busca-semantica, via TestClient real (não só
    as funções internas, que já têm cobertura própria em outros arquivos)."""

    @classmethod
    def setUpClass(cls):
        # 1. Import main so module-level setup runs (SQLite fallback engine is OK)
        import api.main as _main  # noqa: triggers SQLite engine init
        from api import database as _database
        cls._database = _database

        # 2. Patch startup DB calls before the ASGI lifespan fires
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
                pass  # target may not exist in all envs

        # 3. Patch chamar_ia in main's namespace (imported via `from ... import`)
        cls._ai_patch = patch("api.main.chamar_ia", return_value=_FAKE_AI)
        cls._ai_patch.start()

        # 4. Enter TestClient — fires startup events with patches active
        from fastapi.testclient import TestClient
        cls._ctx = TestClient(_main.app)
        cls.client = cls._ctx.__enter__()

        # 5. Token válido — /recapitulacao-manual passou a exigir autenticação
        token = _main._gerar_token("1", "smoke@teste.com", "operador")
        cls._auth_headers = {"Authorization": f"Bearer {token}"}

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)
        cls._ai_patch.stop()
        for p in cls._patches:
            p.stop()

    def setUp(self):
        # Engine SQLite em memória isolado por teste (mesmo padrão de
        # tests/test_admin_costs_endpoints.py) — necessário só pro teste de
        # Biblioteca (KnowledgeSource é SQLModel), inofensivo pros demais.
        # StaticPool + check_same_thread=False porque o TestClient roda o
        # endpoint numa worker thread diferente desta.
        self._engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(self._engine)
        self._engine_patch = patch.object(self._database, "engine", self._engine)
        self._engine_patch.start()
        self.addCleanup(self._engine_patch.stop)

        # agent.sessao_manager._get_conn tenta MySQL real (default
        # 127.0.0.1) sem DB_HOST configurado — sem mockar, /iniciar-sessao
        # ficaria lento esperando o connect_timeout de verdade em vez de
        # falhar rápido.
        self._sessao_conn_patch = patch(
            "agent.sessao_manager._get_conn", side_effect=RuntimeError("sem banco nos testes")
        )
        self._sessao_conn_patch.start()
        self.addCleanup(self._sessao_conn_patch.stop)

    # ── /health ──────────────────────────────────────────────

    def test_health_status_200(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)

    def test_health_payload_shape(self):
        data = self.client.get("/health").json()
        self.assertIn("status", data)
        self.assertIn(data["status"], ("online", "degradado"),
                      msg="status deve ser 'online' ou 'degradado'")
        self.assertIn("servico", data)
        self.assertIn("versao", data)
        self.assertIn("timestamp", data)

    # ── /dashboard ───────────────────────────────────────────

    def test_dashboard_status_200(self):
        r = self.client.get("/dashboard")
        self.assertEqual(r.status_code, 200)

    def test_dashboard_content_type_html(self):
        r = self.client.get("/dashboard")
        self.assertIn("text/html", r.headers.get("content-type", ""))

    def test_dashboard_html_contains_saleia(self):
        r = self.client.get("/dashboard")
        self.assertIn(b"SALEIA", r.content)

    # ── /recapitulacao-manual ─────────────────────────────────

    def test_recapitulacao_manual_status_200(self):
        r = self.client.post(
            "/recapitulacao-manual",
            json={
                "transcricao": "Vendedor: Olá, tudo bem? Cliente: Sim, tenho interesse.",
                "titulo_reuniao": "Smoke Test",
            },
            headers=self._auth_headers,
        )
        self.assertEqual(r.status_code, 200)

    def test_recapitulacao_manual_payload_keys(self):
        data = self.client.post(
            "/recapitulacao-manual",
            json={
                "transcricao": "Vendedor: Olá, tudo bem? Cliente: Sim, tenho interesse.",
                "titulo_reuniao": "Smoke Test",
            },
            headers=self._auth_headers,
        ).json()
        for key in ("recapitulacao", "perfil_disc", "diagnostico_financeiro", "gerado_em"):
            self.assertIn(key, data, msg=f"Chave ausente na resposta: {key}")

    def test_recapitulacao_manual_rejects_empty_transcricao(self):
        r = self.client.post(
            "/recapitulacao-manual",
            json={"transcricao": "", "titulo_reuniao": "Smoke"},
            headers=self._auth_headers,
        )
        self.assertEqual(r.status_code, 400)

    def test_recapitulacao_manual_requires_auth(self):
        r = self.client.post(
            "/recapitulacao-manual",
            json={"transcricao": "Vendedor: Olá. Cliente: Oi.", "titulo_reuniao": "Smoke"},
        )
        self.assertEqual(r.status_code, 401)

    # ── /auth/login (Fase 0) ───────────────────────────────────

    def test_auth_login_endpoint_responde(self):
        # Sem fixture de usuário seedado no ambiente de teste — cobre o
        # caminho de erro (e-mail inexistente) só pra confirmar que o
        # endpoint sobe, parseia o body e responde certo, sem 500. Login
        # com sucesso já é exercitado indiretamente por todo teste que usa
        # _gerar_token diretamente (bypassando o endpoint). auth_login()
        # chama `_get_conn()` fora do try/finally — o mock genérico de
        # `setUp` (RuntimeError) viraria 500 aqui, então este teste precisa
        # de um fake connection funcional (fetchone -> None = "sem linha").
        class _FakeCursor:
            def execute(self, *a, **k):
                pass

            def fetchone(self):
                return None

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class _FakeConn:
            def cursor(self):
                return _FakeCursor()

            def close(self):
                pass

        with patch("agent.sessao_manager._get_conn", return_value=_FakeConn()):
            r = self.client.post(
                "/auth/login",
                json={"email": "ninguem-existe-smoke@saleia.invalido", "senha": "qualquer"},
            )
        self.assertEqual(r.status_code, 401)

    # ── /iniciar-sessao (Fase 0) ─────────────────────────────────

    def test_iniciar_sessao_status_200(self):
        r = self.client.post("/iniciar-sessao", json={"meeting_id": "smoke-teste-sessao-1"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("ok", data)
        self.assertIn("sessao_id", data)

    # ── Biblioteca / Knowledge Compiler (Fase 0) ──────────────────

    def test_biblioteca_upload_e_extracao_e2e(self):
        with patch.dict(os.environ, {"KNOWLEDGE_COMPILER_ENABLED": "true"}):
            arquivo = io.BytesIO("Conteudo de teste para a Biblioteca de Inteligencia — smoke test.".encode("utf-8"))
            r_upload = self.client.post(
                "/biblioteca/fontes",
                files={"arquivo": ("smoke.txt", arquivo, "text/plain")},
                data={"title": "Fonte Smoke Test", "source_type": "OTHER"},
                headers=self._auth_headers,
            )
            self.assertEqual(r_upload.status_code, 200, r_upload.text)
            source_id = r_upload.json()["id"]

            r_extrair = self.client.post(
                f"/biblioteca/fontes/{source_id}/extrair",
                headers=self._auth_headers,
            )
            self.assertEqual(r_extrair.status_code, 200, r_extrair.text)

    def test_biblioteca_desligada_retorna_404(self):
        with patch.dict(os.environ, {"KNOWLEDGE_COMPILER_ENABLED": "false"}):
            r = self.client.post(
                "/biblioteca/fontes",
                files={"arquivo": ("x.txt", io.BytesIO(b"x"), "text/plain")},
                data={"title": "X"},
                headers=self._auth_headers,
            )
        self.assertEqual(r.status_code, 404)

    # ── /busca-semantica (RAG, Fase 0) ────────────────────────────

    def test_busca_semantica_endpoint_responde(self):
        r = self.client.get("/busca-semantica?q=objecao+de+preco", headers=self._auth_headers)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("resultados", data)
        self.assertIn("total", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
