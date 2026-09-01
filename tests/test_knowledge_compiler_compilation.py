"""
Testes do Knowledge Compiler — Fase 2 (compilação com IA em KnowledgeItems).

`chamar_ia_async` e `get_embedding_provider` são sempre mockados — nenhum
teste bate no SDK/API real (mesmo padrão de
tests/test_multiagente_claude_fallback.py). Persistência usa SQLite em
memória (mesmo padrão de tests/test_ai_usage_events.py).

Run:
    python -m unittest tests.test_knowledge_compiler_compilation -v
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from sqlmodel import SQLModel, create_engine

from api import database
from services.embeddings import EmbeddingResult
from services.knowledge_compiler import compiler as kc_compiler
from services.knowledge_compiler.compiler import (
    KNOWLEDGE_ITEM_TYPES,
    _secoes_compilaveis,
    _validar_item,
    estimar_custo_compilacao,
)


class ValidarItemTest(unittest.TestCase):
    def test_item_valido(self):
        item = _validar_item({
            "type": "framework", "title": "SPIN", "content": "Metodologia de perguntas em 4 etapas.",
            "confidence": 0.9, "tags": ["spin", "descoberta"], "metadata": {"steps": ["S", "P", "I", "N"]},
        })
        self.assertIsNotNone(item)
        self.assertEqual(item["item_type"], "FRAMEWORK")
        self.assertEqual(item["metadata"]["steps"], ["S", "P", "I", "N"])

    def test_tipo_desconhecido_e_rejeitado(self):
        self.assertIsNone(_validar_item({"type": "FOO", "title": "x", "content": "y" * 30}))

    def test_titulo_ou_conteudo_vazio_e_rejeitado(self):
        self.assertIsNone(_validar_item({"type": "SCRIPT", "title": "", "content": "y" * 30}))
        self.assertIsNone(_validar_item({"type": "SCRIPT", "title": "x", "content": ""}))

    def test_conteudo_curto_demais_e_rejeitado(self):
        self.assertIsNone(_validar_item({"type": "CASE", "title": "x", "content": "curto"}))

    def test_nao_dict_e_rejeitado(self):
        self.assertIsNone(_validar_item("nao e um dict"))

    def test_confidence_invalida_cai_no_default(self):
        item = _validar_item({"type": "CASE", "title": "x", "content": "y" * 30, "confidence": "not-a-number"})
        self.assertEqual(item["confidence"], 0.75)

    def test_todos_os_7_tipos_sao_aceitos(self):
        for tipo in KNOWLEDGE_ITEM_TYPES:
            item = _validar_item({"type": tipo, "title": "t", "content": "c" * 25})
            self.assertIsNotNone(item, f"tipo {tipo} deveria ser aceito")


class SecoesCompilaveisTest(unittest.TestCase):
    def test_separa_secoes_flagadas(self):
        fonte = {"sections": [
            {"title": "A", "content": "ok", "flags": []},
            {"title": "B", "content": "suspeito", "flags": ["potential_instruction_injection"]},
        ]}
        compilaveis, puladas = _secoes_compilaveis(fonte)
        self.assertEqual(len(compilaveis), 1)
        self.assertEqual(compilaveis[0]["title"], "A")
        self.assertEqual(len(puladas), 1)
        self.assertEqual(puladas[0]["title"], "B")

    def test_sem_sections_retorna_vazio(self):
        self.assertEqual(_secoes_compilaveis({}), ([], []))


class EstimarCustoTest(unittest.TestCase):
    def test_estimativa_e_deterministica_sem_chamar_ia(self):
        fonte = {"sections": [
            {"title": "A", "content": "x" * 1000, "flags": []},
            {"title": "B", "content": "y" * 500, "flags": []},
            {"title": "C", "content": "z" * 200, "flags": ["potential_instruction_injection"]},
        ]}
        with patch.object(kc_compiler, "status_provedores", return_value={
            "deepseek": {"modelo": "deepseek-chat"}, "openai": {"modelo": "gpt-4o"},
        }):
            estimativa = estimar_custo_compilacao(fonte)

        self.assertEqual(estimativa["secoes_a_compilar"], 2)
        self.assertEqual(estimativa["secoes_puladas"], 1)
        self.assertEqual(estimativa["provedor_estimado"], "deepseek")
        self.assertEqual(estimativa["modelo_estimado"], "deepseek-chat")
        self.assertGreater(estimativa["custo_estimado_usd"], 0)
        self.assertGreater(estimativa["tokens_entrada_estimados"], 0)


def _stub_embedding_provider(vector):
    class _Stub:
        provider_name = "stub"

        async def embed_async(self, text):
            return EmbeddingResult(vector=vector, provider="stub", model="stub-model", dimension=len(vector))

    return _Stub()


class CompilarFonteTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch_engine = patch.object(database, "engine", self._engine)
        self._patch_engine.start()
        self.addCleanup(self._patch_engine.stop)

    def _run(self, source_id, fonte):
        return asyncio.run(kc_compiler.compilar_fonte(source_id, fonte))

    def test_compila_secao_valida_pula_secao_flagada_e_descarta_item_invalido(self):
        fonte = {"sections": [
            {"title": "S1", "content": "conteudo relevante", "flags": []},
            {"title": "S2", "content": "conteudo suspeito", "flags": ["potential_instruction_injection"]},
        ]}
        resposta_ia = {"itens": [
            {"type": "FRAMEWORK", "title": "SPIN", "content": "c" * 30, "confidence": 0.9, "tags": [], "metadata": {}},
            {"type": "TIPO_INVALIDO", "title": "lixo", "content": "c" * 30},
        ]}

        with patch.object(kc_compiler, "chamar_ia_async", new=AsyncMock(return_value=resposta_ia)) as mock_ia:
            with patch("services.embeddings.get_embedding_provider", return_value=_stub_embedding_provider([1.0, 0.0])):
                resumo = self._run(1, fonte)

        mock_ia.assert_awaited_once()  # S2 (flagada) nunca chega a chamar IA
        self.assertEqual(resumo["itens_criados"], 1)
        self.assertEqual(resumo["por_tipo"], {"FRAMEWORK": 1})
        self.assertEqual(resumo["secoes_compiladas"], 1)
        self.assertEqual(resumo["secoes_puladas"], 1)

    def test_dedup_marca_possivel_duplicado_sem_bloquear(self):
        fonte = {"sections": [
            {"title": "S1", "content": "conteudo A", "flags": []},
            {"title": "S2", "content": "conteudo B", "flags": []},
        ]}
        resp1 = {"itens": [{"type": "FRAMEWORK", "title": "SPIN v1", "content": "c" * 30, "confidence": 0.8, "tags": [], "metadata": {}}]}
        resp2 = {"itens": [{"type": "FRAMEWORK", "title": "SPIN v2", "content": "d" * 30, "confidence": 0.8, "tags": [], "metadata": {}}]}

        with patch.object(kc_compiler, "chamar_ia_async", new=AsyncMock(side_effect=[resp1, resp2])):
            with patch("services.embeddings.get_embedding_provider", return_value=_stub_embedding_provider([1.0, 0.0, 0.0])):
                resumo = self._run(1, fonte)

        self.assertEqual(resumo["itens_criados"], 2)
        itens = database.listar_knowledge_items(source_id=1)
        itens_por_titulo = {i["title"]: i for i in itens}
        self.assertIsNone(itens_por_titulo["SPIN v1"]["possivel_duplicado_de"])
        self.assertEqual(itens_por_titulo["SPIN v2"]["possivel_duplicado_de"], itens_por_titulo["SPIN v1"]["id"])

    def test_sem_itens_validos_nao_gera_erro(self):
        fonte = {"sections": [{"title": "S1", "content": "x", "flags": []}]}
        with patch.object(kc_compiler, "chamar_ia_async", new=AsyncMock(return_value={"itens": []})):
            resumo = self._run(1, fonte)
        self.assertEqual(resumo["itens_criados"], 0)
        self.assertEqual(resumo["por_tipo"], {})

    def test_erro_na_ia_de_uma_secao_nao_derruba_as_outras(self):
        fonte = {"sections": [
            {"title": "S1", "content": "x", "flags": []},
            {"title": "S2", "content": "y", "flags": []},
        ]}
        resp_ok = {"itens": [{"type": "CASE", "title": "Caso 1", "content": "c" * 30, "confidence": 0.8, "tags": [], "metadata": {}}]}
        with patch.object(kc_compiler, "chamar_ia_async", new=AsyncMock(side_effect=[RuntimeError("provedor fora do ar"), resp_ok])):
            with patch("services.embeddings.get_embedding_provider", return_value=_stub_embedding_provider([0.0, 1.0])):
                resumo = self._run(1, fonte)
        self.assertEqual(resumo["itens_criados"], 1)


class KnowledgeItemDbTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_criar_listar_contar_e_atualizar_status(self):
        criado = database.criar_knowledge_item(1, {
            "item_type": "OBJECTION", "title": "Preço alto", "content": "c" * 30,
            "metadata": {"category": "PRICE_VALUE"}, "tags": ["preco"], "confidence": 0.7,
        })
        self.assertIsNotNone(criado)
        self.assertEqual(criado["status"], "DRAFT")
        self.assertEqual(criado["metadata"]["category"], "PRICE_VALUE")

        itens = database.listar_knowledge_items(source_id=1)
        self.assertEqual(len(itens), 1)

        contagem = database.contar_knowledge_items_por_tipo(1)
        self.assertEqual(contagem, {"OBJECTION": 1})

        atualizado = database.atualizar_status_knowledge_item(criado["id"], "APPROVED")
        self.assertEqual(atualizado["status"], "APPROVED")

    def test_item_malformado_nao_lanca_excecao(self):
        resultado = database.criar_knowledge_item(1, {"item_type": "OBJECTION"})  # falta title/content
        self.assertIsNone(resultado)

    def test_buscar_similar_respeita_threshold_e_tipo(self):
        item1 = database.criar_knowledge_item(1, {"item_type": "FRAMEWORK", "title": "A", "content": "c" * 30})
        database.salvar_embedding_knowledge_item(item1["id"], [1.0, 0.0], "stub", "stub-model", 2)

        # mesmo vetor, tipo diferente -> nao deve casar
        sem_match_tipo = database.buscar_knowledge_item_similar("OBJECTION", [1.0, 0.0])
        self.assertIsNone(sem_match_tipo)

        # vetor identico, mesmo tipo -> similaridade 1.0, acima do threshold padrao
        match = database.buscar_knowledge_item_similar("FRAMEWORK", [1.0, 0.0])
        self.assertIsNotNone(match)
        self.assertEqual(match["id"], item1["id"])

        # vetor ortogonal, mesmo tipo -> similaridade 0.0, abaixo do threshold
        sem_match_similaridade = database.buscar_knowledge_item_similar("FRAMEWORK", [0.0, 1.0])
        self.assertIsNone(sem_match_similaridade)

    def test_buscar_similar_sem_candidatos_retorna_none(self):
        self.assertIsNone(database.buscar_knowledge_item_similar("FRAMEWORK", [1.0, 0.0]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
