"""
Teste de integração — ranking semântico com Ollama real (opcional).

Prova que embeddings gerados localmente (embeddinggemma via Ollama) de
fato ordenam textos semanticamente relacionados acima de textos não
relacionados — não apenas que a interface funciona (isso já é coberto
por tests/test_embeddings.py com mocks).

Este teste só roda se houver um Ollama acessível em OLLAMA_BASE_URL (ou
localhost:11434) com o modelo configurado já baixado — do contrário é
pulado (skip), nunca falha por falta de infraestrutura local. A suíte
padrão (`python -m unittest discover`) portanto nunca exige rede.

Run manualmente com Ollama rodando:
    python -m unittest tests.test_embeddings_semantic_ranking -v
"""
import os
import unittest

import numpy as np


def _ollama_disponivel() -> bool:
    try:
        import httpx
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        modelo = os.environ.get("OLLAMA_EMBEDDING_MODEL", "embeddinggemma")
        resp = httpx.post(
            f"{base_url}/api/embeddings",
            json={"model": modelo, "prompt": "ping"},
            timeout=3,
        )
        return resp.status_code == 200 and "embedding" in resp.json()
    except Exception:
        return False


_OLLAMA_OK = _ollama_disponivel()


@unittest.skipUnless(_OLLAMA_OK, "Nenhum Ollama local acessível com o modelo configurado — pulando teste de integração.")
class TestSemanticRankingOllama(unittest.IsolatedAsyncioTestCase):
    async def test_price_objection_query_ranks_price_texts_higher(self):
        from services.embeddings import cosine_top_k, get_embedding_provider

        os.environ["EMBEDDING_PROVIDER"] = "ollama"
        provider = get_embedding_provider(refresh=True)

        texto_a = "Cliente considera o preço muito alto"
        texto_b = "Lead apresentou objeção relacionada ao valor"
        texto_c = "Cliente perguntou sobre prazo de implementação"
        query = "O cliente achou caro"

        vetores = []
        for texto in (texto_a, texto_b, texto_c):
            resultado = await provider.embed_async(texto)
            self.assertIsNotNone(resultado, f"Falha ao gerar embedding para: {texto}")
            vetores.append(resultado.vector)

        matrix = np.array(vetores, dtype=np.float32)
        resultado_query = await provider.embed_async(query)
        self.assertIsNotNone(resultado_query)

        vec_query = np.array(resultado_query.vector, dtype=np.float32)
        ranking = cosine_top_k(vec_query, matrix, k=3)

        indice_c = 2  # texto sobre prazo — não relacionado a preço
        posicao_c = next(pos for pos, (idx, _sim) in enumerate(ranking) if idx == indice_c)

        # C (prazo) não deve ficar em primeiro — A e/ou B (preço) devem vir antes.
        self.assertGreater(posicao_c, 0, "Texto sobre prazo ficou à frente dos textos sobre preço.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
