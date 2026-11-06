"""D7 (05-06/11/2026): o Ollama usava 73-88% da CPU porque cada ciclo de 20 s
embutia 3 vezes o mesmo texto longo. Agora: consulta curta, 1 embedding por
texto e RAG reaproveitado por reunião."""
import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

from agent.multiagente import orquestrador
from services.embeddings import ollama_provider
from services.embeddings.ollama_provider import OllamaEmbeddingProvider, limpar_cache_embeddings


class ConsultaTest(unittest.TestCase):
    def test_usa_o_fim_da_conversa_com_teto(self):
        consulta = orquestrador.consulta_rag("a" * 5000 + "FALA_ATUAL", "historico")
        self.assertTrue(consulta.endswith("FALA_ATUAL"))
        self.assertEqual(len(consulta), orquestrador.RAG_CONSULTA_MAX_CHARS)

    def test_sem_trecho_usa_o_historico(self):
        self.assertEqual(orquestrador.consulta_rag("", "inicio"), "inicio")


class CachePorReuniaoTest(unittest.TestCase):
    def setUp(self):
        orquestrador._rag_por_reuniao.clear()
        self.addCleanup(orquestrador._rag_por_reuniao.clear)

    def test_vale_pelo_intervalo(self):
        orquestrador.guardar_rag("m1", 100.0, "ctx")
        with patch.dict(os.environ, {"RAG_INTERVALO_S": "120"}):
            self.assertEqual(orquestrador.rag_em_cache("m1", 219.0), "ctx")
            self.assertIsNone(orquestrador.rag_em_cache("m1", 221.0))

    def test_resultado_vazio_tambem_vale(self):
        orquestrador.guardar_rag("m1", 100.0, "")
        self.assertEqual(orquestrador.rag_em_cache("m1", 101.0), "")

    def test_reuniao_anonima_nunca_usa_cache(self):
        orquestrador.guardar_rag("default", 100.0, "ctx")
        self.assertIsNone(orquestrador.rag_em_cache("default", 101.0))
        self.assertIsNone(orquestrador.rag_em_cache(None, 101.0))

    def test_reunioes_nao_se_misturam(self):
        orquestrador.guardar_rag("m1", 100.0, "ctx")
        self.assertIsNone(orquestrador.rag_em_cache("m2", 101.0))


class CicloTest(unittest.TestCase):
    """Dois ciclos seguidos da mesma reunião: a busca roda 1 vez só."""

    def setUp(self):
        orquestrador._rag_por_reuniao.clear()
        self.addCleanup(orquestrador._rag_por_reuniao.clear)

    def test_segundo_ciclo_reaproveita_o_rag(self):
        rag = AsyncMock(return_value="CONTEXTO_RAG")
        coach = AsyncMock(return_value={})
        vazio = AsyncMock(return_value={})
        with patch.object(orquestrador, "buscar_contexto_similar", rag), \
                patch("agent.sales_memory.buscar_contexto_para_reuniao", return_value=None) as mem, \
                patch("api.database.buscar_conhecimento_compilado_similar", return_value=None), \
                patch.object(orquestrador, "analisar_coach", coach), \
                patch.object(orquestrador, "analisar_disc", vazio), \
                patch.object(orquestrador, "analisar_finance", vazio), \
                patch.object(orquestrador, "analisar_closer", vazio), \
                patch.object(orquestrador, "analisar_bigfive", vazio):
            for _ in range(2):
                try:
                    asyncio.run(orquestrador.analisar_fragmento_multi("Cliente: está caro " * 20, meeting_id="m1"))
                except Exception:
                    pass
        self.assertEqual(rag.await_count, 1)
        self.assertEqual(mem.call_count, 1)
        self.assertEqual(coach.await_count, 2)
        for chamada in coach.await_args_list:
            self.assertIn("CONTEXTO_RAG", chamada.args[6])


class CacheDeVetoresTest(unittest.TestCase):
    def setUp(self):
        limpar_cache_embeddings()
        self.addCleanup(limpar_cache_embeddings)

    def test_mesmo_texto_chama_o_ollama_uma_vez(self):
        prov = OllamaEmbeddingProvider(base_url="http://x", model="m")
        with patch.object(OllamaEmbeddingProvider, "_post_embedding",
                          new=AsyncMock(return_value=[0.1, 0.2])) as post:
            a = prov.embed("texto igual")
            b = prov.embed("texto igual")
            c = prov.embed("outro texto")
        self.assertEqual(post.await_count, 2)
        self.assertEqual(a.vector, b.vector)
        self.assertEqual(c.dimension, 2)

    def test_falha_nao_fica_em_cache(self):
        prov = OllamaEmbeddingProvider(base_url="http://x", model="m")
        with patch.object(OllamaEmbeddingProvider, "_post_embedding",
                          new=AsyncMock(side_effect=[RuntimeError("fora"), [0.3]])):
            self.assertIsNone(prov.embed("t"))
            self.assertEqual(prov.embed("t").vector, [0.3])

    def test_cache_tem_teto(self):
        prov = OllamaEmbeddingProvider(base_url="http://x", model="m")
        # Cada embed() sobe um loop novo (~0,3 s no Windows): teto pequeno no teste.
        with patch.object(ollama_provider, "_CACHE_MAX", 3), \
                patch.object(OllamaEmbeddingProvider, "_post_embedding", new=AsyncMock(return_value=[1.0])):
            for i in range(5):
                prov.embed(f"t{i}")
            self.assertEqual(len(ollama_provider._cache_vetores), 3)
            self.assertNotIn(("http://x", "m", "t0"), ollama_provider._cache_vetores)


if __name__ == "__main__":
    unittest.main()
