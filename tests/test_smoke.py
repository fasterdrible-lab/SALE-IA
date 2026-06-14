"""
Smoke tests — verify that the three critical endpoints start and respond correctly.

These tests do NOT require external services (MySQL, DeepSeek, OpenAI etc.).
Database startup calls are patched; AI calls return a fixed fake response.

Run:
    python -m unittest tests.test_smoke -v
"""

import logging
import unittest
from unittest.mock import patch

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
    """Smoke tests for /health, /dashboard and /recapitulacao-manual."""

    @classmethod
    def setUpClass(cls):
        # 1. Import main so module-level setup runs (SQLite fallback engine is OK)
        import api.main as _main  # noqa: triggers SQLite engine init

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

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)
        cls._ai_patch.stop()
        for p in cls._patches:
            p.stop()

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
        )
        self.assertEqual(r.status_code, 200)

    def test_recapitulacao_manual_payload_keys(self):
        data = self.client.post(
            "/recapitulacao-manual",
            json={
                "transcricao": "Vendedor: Olá, tudo bem? Cliente: Sim, tenho interesse.",
                "titulo_reuniao": "Smoke Test",
            },
        ).json()
        for key in ("recapitulacao", "perfil_disc", "diagnostico_financeiro", "gerado_em"):
            self.assertIn(key, data, msg=f"Chave ausente na resposta: {key}")

    def test_recapitulacao_manual_rejects_empty_transcricao(self):
        r = self.client.post(
            "/recapitulacao-manual",
            json={"transcricao": "", "titulo_reuniao": "Smoke"},
        )
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
