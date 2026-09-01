"""
Testes do Knowledge Compiler — Fase 3 (integração RAG / Skill / Playbook).

`get_embedding_provider`, `salvar_skill` e `salvar_playbook` são sempre
mockados — nunca tocam MySQL/rede real. Persistência de KnowledgeItem usa
SQLite em memória (mesmo padrão das Fases 1-2).

Run:
    python -m unittest tests.test_knowledge_compiler_integracao -v
"""
import unittest
from unittest.mock import patch

from sqlmodel import SQLModel, create_engine

from agent.playbook_generator import gerar_playbook_de_fonte, mapear_knowledge_items_para_playbook
from agent.skill_resolver import gerar_skill_de_knowledge_item, mapear_knowledge_item_para_skill
from api import database
from services.embeddings import EmbeddingResult


def _stub_provider(vector):
    class _Stub:
        def embed(self, text):
            return EmbeddingResult(vector=vector, provider="stub", model="stub-model", dimension=len(vector))

    return _Stub()


class BuscarConhecimentoCompiladoTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def _criar_item(self, status, vector, item_type="FRAMEWORK", title="Item"):
        criado = database.criar_knowledge_item(1, {
            "item_type": item_type, "title": title, "content": "c" * 30,
        })
        database.salvar_embedding_knowledge_item(criado["id"], vector, "stub", "stub-model", len(vector))
        database.atualizar_status_knowledge_item(criado["id"], status)
        return criado

    def test_so_retorna_itens_aprovados(self):
        self._criar_item("DRAFT", [1.0, 0.0], title="Rascunho")
        self._criar_item("APPROVED", [1.0, 0.0], title="Aprovado")
        self._criar_item("REJECTED", [1.0, 0.0], title="Rejeitado")

        with patch("services.embeddings.get_embedding_provider", return_value=_stub_provider([1.0, 0.0])):
            resultado = database.buscar_conhecimento_compilado_similar("query qualquer")

        self.assertIsNotNone(resultado)
        self.assertIn("Aprovado", resultado)
        self.assertNotIn("Rascunho", resultado)
        self.assertNotIn("Rejeitado", resultado)

    def test_sem_itens_aprovados_retorna_none(self):
        self._criar_item("DRAFT", [1.0, 0.0])
        with patch("services.embeddings.get_embedding_provider", return_value=_stub_provider([1.0, 0.0])):
            self.assertIsNone(database.buscar_conhecimento_compilado_similar("query"))

    def test_respeita_top_k(self):
        for i in range(5):
            self._criar_item("APPROVED", [1.0, 0.0], title=f"Item {i}")
        with patch("services.embeddings.get_embedding_provider", return_value=_stub_provider([1.0, 0.0])):
            resultado = database.buscar_conhecimento_compilado_similar("query", top_k=2)
        self.assertEqual(resultado.count("[FRAMEWORK]"), 2)

    def test_abaixo_do_similarity_min_nao_aparece(self):
        self._criar_item("APPROVED", [0.0, 1.0], title="Ortogonal")
        with patch("services.embeddings.get_embedding_provider", return_value=_stub_provider([1.0, 0.0])):
            resultado = database.buscar_conhecimento_compilado_similar("query", similarity_min=0.5)
        self.assertIsNone(resultado)

    def test_formato_do_bloco_de_texto(self):
        self._criar_item("APPROVED", [1.0, 0.0], item_type="OBJECTION", title="Preço alto")
        with patch("services.embeddings.get_embedding_provider", return_value=_stub_provider([1.0, 0.0])):
            resultado = database.buscar_conhecimento_compilado_similar("query")
        self.assertTrue(resultado.startswith("CONHECIMENTO COMERCIAL RELEVANTE"))
        self.assertIn("[OBJECTION] Preço alto:", resultado)


class MapearSkillTest(unittest.TestCase):
    def test_mapeamento_basico(self):
        item = {"item_type": "FRAMEWORK", "title": "SPIN", "content": "Metodologia X", "source_id": 3, "metadata": {}}
        skill = mapear_knowledge_item_para_skill(item)
        self.assertEqual(skill["name"], "SPIN")
        self.assertEqual(skill["priority"], 60)
        self.assertEqual(skill["source"], "knowledge_compiler")
        self.assertEqual(skill["trigger_disc"], [])
        self.assertIn("[FRAMEWORK] SPIN", skill["system_injection"])
        self.assertIn("Metodologia X", skill["system_injection"])

    def test_metadata_de_framework_entra_na_injecao(self):
        item = {
            "item_type": "FRAMEWORK", "title": "SPIN", "content": "c",
            "metadata": {"when_to_use": "No início da descoberta", "steps": ["S", "P", "I", "N"]},
        }
        skill = mapear_knowledge_item_para_skill(item)
        self.assertIn("No início da descoberta", skill["system_injection"])
        self.assertIn("S; P; I; N", skill["system_injection"])

    def test_metadata_de_objection_entra_na_injecao(self):
        item = {
            "item_type": "OBJECTION", "title": "Preço", "content": "c",
            "metadata": {"recommended_actions": ["Investigar valor"], "questions": ["O que te faz achar caro?"]},
        }
        skill = mapear_knowledge_item_para_skill(item)
        self.assertIn("Investigar valor", skill["system_injection"])
        self.assertIn("O que te faz achar caro?", skill["system_injection"])

    def test_gerar_skill_chama_salvar_skill_com_mapeamento(self):
        item = {"item_type": "CASE", "title": "Caso X", "content": "c", "source_id": 1, "metadata": {}}
        with patch("agent.skill_resolver.salvar_skill", return_value="skill-uuid-123") as mock_salvar:
            resultado = gerar_skill_de_knowledge_item(item)
        self.assertEqual(resultado, "skill-uuid-123")
        mock_salvar.assert_called_once()
        dict_passado = mock_salvar.call_args[0][0]
        self.assertEqual(dict_passado["source"], "knowledge_compiler")


class MapearPlaybookTest(unittest.TestCase):
    def _item(self, item_type, title, content, metadata=None):
        return {"item_type": item_type, "title": title, "content": content, "metadata": metadata or {}}

    def test_agrupamento_por_tipo(self):
        itens = [
            self._item("DISCOVERY_QUESTION", "Q1", "Qual seu maior desafio?"),
            self._item("SCRIPT", "Abertura", "Bom dia, tudo bem?"),
            self._item("OBJECTION", "Preço alto", "Investigar percepção de valor."),
            self._item("FRAMEWORK", "SPIN", "Metodologia de perguntas."),
            self._item("CASE", "Caso vencedor", "Cliente fechou em 2 semanas."),
        ]
        fonte = {"id": 7, "title": "Livro de Vendas", "author": "Fulano"}
        playbook = mapear_knowledge_items_para_playbook(fonte, itens)

        self.assertEqual(playbook["name"], "Playbook — Livro de Vendas")
        self.assertEqual(playbook["targetPersona"], "Fulano")
        self.assertIn("Qual seu maior desafio?", playbook["steps"])
        self.assertIn("Bom dia, tudo bem?", playbook["steps"])
        self.assertEqual(playbook["objections"], [{"objecao": "Preço alto", "resposta": "Investigar percepção de valor."}])
        self.assertIn("Metodologia de perguntas.", playbook["winningArguments"])
        self.assertIn("Cliente fechou em 2 semanas.", playbook["winningArguments"])
        self.assertEqual(playbook["source_meeting_id"], "knowledge_source:7")

    def test_closing_sequence_usa_scripts_de_fechamento(self):
        itens = [
            self._item("SCRIPT", "Fechamento 1", "Vamos fechar hoje?", {"momento": "fechamento"}),
            self._item("SCRIPT", "Abertura", "Oi", {"momento": "abertura"}),
        ]
        playbook = mapear_knowledge_items_para_playbook({"id": 1}, itens)
        self.assertEqual(playbook["closingSequence"], ["Vamos fechar hoje?"])

    def test_closing_sequence_cai_no_fallback_decision_rule(self):
        itens = [
            self._item("SCRIPT", "Abertura", "Oi", {"momento": "abertura"}),
            self._item("DECISION_RULE", "Regra 1", "Se objeção só for preço, negociar."),
        ]
        playbook = mapear_knowledge_items_para_playbook({"id": 1}, itens)
        self.assertEqual(playbook["closingSequence"], ["Se objeção só for preço, negociar."])

    def test_sem_itens_gera_playbook_vazio_mas_valido(self):
        playbook = mapear_knowledge_items_para_playbook({"id": 1, "title": "X"}, [])
        self.assertEqual(playbook["steps"], [])
        self.assertEqual(playbook["objections"], [])

    def test_gerar_playbook_chama_salvar_playbook_com_mapeamento(self):
        itens = [self._item("CASE", "Caso", "conteudo")]
        with patch("agent.playbook_generator.salvar_playbook", return_value="pb-uuid-456") as mock_salvar:
            resultado = gerar_playbook_de_fonte({"id": 9, "title": "Fonte"}, itens)
        self.assertEqual(resultado, "pb-uuid-456")
        dict_passado = mock_salvar.call_args[0][0]
        self.assertEqual(dict_passado["source_meeting_id"], "knowledge_source:9")


if __name__ == "__main__":
    unittest.main(verbosity=2)
