"""
Testes — GET /workspace/resumo, GET /workspace/pendencias,
GET /grafo/conexoes/{tipo}/{id}, GET /busca-semantica (Sales Brain Fase
7.1 + 7.2 + gap da Tarefa 1.3).

Não requer MySQL: as funções de agregação de cada módulo são mockadas
(mesmo padrão de tests/test_resumo_cliente_endpoint.py).

Run:
    python -m unittest tests.test_workspace_endpoints -v
"""

import logging
import unittest
from unittest.mock import patch

logging.disable(logging.CRITICAL)


class WorkspaceEndpointsSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import api.main as _main

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
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)
        for p in cls._patches:
            p.stop()

    def test_resumo_sem_token_401(self):
        r = self.client.get("/workspace/resumo")
        self.assertEqual(r.status_code, 401)

    def test_resumo_agrega_contadores(self):
        with patch("agent.client_intelligence.listar_clientes", return_value=[{}, {}]), \
             patch("agent.playbook_generator.listar_playbooks", return_value=[{"status": "approved"}]), \
             patch("agent.skill_resolver.listar_skills", return_value=[{}, {}, {}]), \
             patch("agent.sales_memory.listar_memorias", return_value=[{}]), \
             patch("agent.followup_generator.listar_followups_pendentes", return_value=[{}]):
            r = self.client.get("/workspace/resumo", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["clientes_ativos"], 2)
        self.assertEqual(body["followups_pendentes"], 1)

    def test_resumo_falha_isolada_nao_derruba_endpoint(self):
        with patch("agent.client_intelligence.listar_clientes", side_effect=RuntimeError("sem banco")), \
             patch("agent.playbook_generator.listar_playbooks", return_value=[]), \
             patch("agent.skill_resolver.listar_skills", return_value=[]), \
             patch("agent.sales_memory.listar_memorias", return_value=[]), \
             patch("agent.followup_generator.listar_followups_pendentes", return_value=[]):
            r = self.client.get("/workspace/resumo", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["clientes_ativos"], 0)

    def test_pendencias_agrega_memorias_playbooks_skills_pendentes(self):
        memorias_fake = [{"id": "m1", "title": "Objeção X", "memory_type": "objection", "created_at": None}]
        playbooks_fake = [{"id": "p1", "name": "PB", "status": "pending", "source_meeting_id": "mid1", "created_at": None},
                           {"id": "p2", "name": "PB ativo", "status": "approved", "created_at": None}]
        skills_fake = [{"id": "s1", "name": "Skill X", "status": "pending", "source_playbook_id": "p1", "created_at": None},
                       {"id": "s2", "name": "Skill builtin", "created_at": None}]
        with patch("agent.sales_memory.listar_memorias", return_value=memorias_fake), \
             patch("agent.playbook_generator.listar_playbooks", return_value=playbooks_fake), \
             patch("agent.skill_resolver.listar_skills", return_value=skills_fake):
            r = self.client.get("/workspace/pendencias", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["total"], 3)
        tipos = {p["tipo"] for p in body["pendencias"]}
        self.assertEqual(tipos, {"memoria", "playbook", "skill"})


class GrafoConexoesEndpointSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import api.main as _main
        from fastapi.testclient import TestClient
        cls._ctx = TestClient(_main.app)
        cls.client = cls._ctx.__enter__()
        cls._main = _main
        cls.token = _main._gerar_token("u1", "vendedor@saleia.app.br", "vendedor")
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def test_tipo_invalido_retorna_400(self):
        r = self.client.get("/grafo/conexoes/invalido/x1", headers=self.headers)
        self.assertEqual(r.status_code, 400)

    def test_tipo_valido_delega_para_buscar_conexoes(self):
        conexoes_fake = [{"tipo": "playbook", "id": "p1", "rotulo": "PB", "relacao": "gerou_playbook", "direcao": "saida"}]
        with patch("agent.knowledge_graph.buscar_conexoes", return_value=conexoes_fake):
            r = self.client.get("/grafo/conexoes/reuniao/m1", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["conexoes"][0]["tipo"], "playbook")


class BuscaSemanticaEndpointSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import api.main as _main
        from fastapi.testclient import TestClient
        cls._ctx = TestClient(_main.app)
        cls.client = cls._ctx.__enter__()
        cls._main = _main
        cls.token = _main._gerar_token("u1", "vendedor@saleia.app.br", "vendedor")
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def test_query_curta_retorna_400(self):
        r = self.client.get("/busca-semantica?q=ab", headers=self.headers)
        self.assertEqual(r.status_code, 400)

    def test_query_valida_delega_e_repassa_fontes(self):
        with patch("agent.semantic_search.buscar_semantico_unificado", return_value=[{"fonte": "memoria"}]) as mock_busca:
            r = self.client.get("/busca-semantica?q=preco+alto&fontes=memorias,relatorios", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 1)
        _, kwargs = mock_busca.call_args
        self.assertEqual(kwargs.get("fontes"), ["memorias", "relatorios"])


if __name__ == "__main__":
    unittest.main()
