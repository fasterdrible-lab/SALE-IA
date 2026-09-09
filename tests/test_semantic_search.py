"""
Testes unitários — agent/semantic_search.py (Sales Brain, gap da Tarefa 1.3:
busca semântica sobre relatórios/transcrições, além de memórias).

Não exigem banco real nem rede: o cache de embeddings é injetado
diretamente (mesmo padrão de tests/test_sales_memory.py) e
`get_embedding_provider`/`buscar_memorias_semantico` são mockados.

Run:
    python -m unittest tests.test_semantic_search -v
"""
import logging
import unittest
from unittest.mock import patch

import numpy as np

logging.disable(logging.CRITICAL)

import agent.semantic_search as semantic_search
from agent.semantic_search import (
    _montar_texto_relatorio,
    buscar_semantico_unificado,
)
from services.embeddings import EmbeddingResult


def _cache_fake(vetores, fontes, meeting_ids=None, titulos=None):
    n = len(vetores)
    dim = len(vetores[0])
    return {
        "vazio": False,
        "ids": [f"idx-{i}" for i in range(n)],
        "fontes": fontes,
        "meeting_ids": meeting_ids or [f"m{i}" for i in range(n)],
        "titulos": titulos or [f"titulo-{i}" for i in range(n)],
        "trechos": [f"trecho-{i}" for i in range(n)],
        "matrix": np.array(vetores, dtype=np.float32),
        "embedding_meta": {"provider": "fake", "model": "fake", "dim": dim},
    }


class MontarTextoRelatorioTest(unittest.TestCase):
    def test_extrai_resumo_executivo_e_dores_e_objecoes(self):
        resultado = {
            "recapitulacao": {
                "resumo_executivo": "Cliente interessado no plano anual.",
                "recapitulacao_estrategica": {
                    "dores_identificadas": ["Sem visibilidade de custo"],
                    "objecoes_levantadas": ["Preço alto"],
                },
            },
            "diagnostico_financeiro": {"produto_recomendado": "Produto Completo"},
            "perfil_disc": {"tipo": "Dominante"},
        }
        texto = _montar_texto_relatorio(resultado)
        self.assertIn("Cliente interessado no plano anual.", texto)
        self.assertIn("Sem visibilidade de custo", texto)
        self.assertIn("Preço alto", texto)
        self.assertIn("Produto Completo", texto)
        self.assertIn("Dominante", texto)

    def test_resultado_vazio_retorna_string_vazia(self):
        self.assertEqual(_montar_texto_relatorio({}), "")


class BuscarSemanticoUnificadoTest(unittest.TestCase):
    def setUp(self):
        semantic_search._cache_indice = None
        self.addCleanup(setattr, semantic_search, "_cache_indice", None)

    def test_filtra_por_fonte_e_ordena_por_similaridade(self):
        vetores = [[1.0, 0.0], [0.0, 1.0]]
        semantic_search._cache_indice = _cache_fake(
            vetores, fontes=["relatorio", "transcricao"],
            meeting_ids=["mA", "mB"], titulos=["Relatório A", "Transcrição B"],
        )
        stub = EmbeddingResult(vector=[1.0, 0.0], provider="fake", model="fake", dimension=2)
        with patch("agent.semantic_search.get_embedding_provider") as mock_provider:
            mock_provider.return_value.embed.return_value = stub
            with patch("agent.sales_memory.buscar_memorias_semantico", return_value=[]):
                resultados = buscar_semantico_unificado("busca", fontes=["relatorios"], top_k=5)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0]["fonte"], "relatorio")
        self.assertEqual(resultados[0]["meeting_id"], "mA")

    def test_mescla_com_memorias_e_respeita_top_k(self):
        # vetor do índice deliberadamente distante do vetor da query (cosseno
        # ~0.6), para que a memória mockada com similarity=0.99 vença de forma
        # inequívoca — evita empate/instabilidade se algum dia baterem.
        vetores = [[0.6, 0.8]]
        semantic_search._cache_indice = _cache_fake(vetores, fontes=["relatorio"])
        stub = EmbeddingResult(vector=[1.0, 0.0], provider="fake", model="fake", dimension=2)
        memorias_fake = [
            {"id": "mem-1", "title": "Objeção preço", "content": "conteudo", "similarity": 0.99, "source_meeting_id": "m9"},
            {"id": "mem-2", "title": "Objeção prazo", "content": "conteudo2", "similarity": 0.10, "source_meeting_id": "m8"},
        ]
        with patch("agent.semantic_search.get_embedding_provider") as mock_provider:
            mock_provider.return_value.embed.return_value = stub
            with patch("agent.sales_memory.buscar_memorias_semantico", return_value=memorias_fake):
                resultados = buscar_semantico_unificado("busca", top_k=2)
        self.assertEqual(len(resultados), 2)
        # o de maior similaridade (memória com 0.99) deve vir primeiro
        self.assertEqual(resultados[0]["fonte"], "memoria")
        self.assertEqual(resultados[0]["meeting_id"], "m9")

    def test_cache_vazio_nao_lanca(self):
        semantic_search._cache_indice = {"vazio": True}
        with patch("agent.sales_memory.buscar_memorias_semantico", return_value=[]):
            resultados = buscar_semantico_unificado("busca", top_k=3)
        self.assertEqual(resultados, [])


if __name__ == "__main__":
    unittest.main()
