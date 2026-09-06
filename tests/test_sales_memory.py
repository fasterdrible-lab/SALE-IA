"""
Testes unitários — agent/sales_memory.py, foco no ajuste de ranking por
outcome da reunião de origem (Fase 6 do PROMPT MESTRE, TAREFA 6.4).

Não exigem banco real nem rede: o cache de embeddings é injetado
diretamente (mesmo padrão de tests/test_embeddings.py) e
`gerar_embedding`/`listar_status_reunioes` são mockados.

Run:
    python -m unittest tests.test_sales_memory -v
"""
import logging
import unittest
from unittest.mock import patch

import numpy as np

logging.disable(logging.CRITICAL)

import agent.sales_memory as sales_memory
from agent.sales_memory import (
    OUTCOME_BOOST_WON,
    OUTCOME_PENALTY_LOST,
    _ajustar_similaridade_por_outcome,
    _status_reunioes_origem,
    buscar_memorias_semantico,
)


def _cache_fake(vetores, origens, tipos=None, confs=None):
    n = len(vetores)
    dim = len(vetores[0])
    return {
        "vazio": False,
        "ids": [f"mem-{i}" for i in range(n)],
        "tipos": tipos or ["objection"] * n,
        "titulos": [f"titulo-{i}" for i in range(n)],
        "conteudos": [f"conteudo-{i}" for i in range(n)],
        "confs": confs or [0.8] * n,
        "tags": [[] for _ in range(n)],
        "origens": origens,
        "matrix": np.array(vetores, dtype=np.float32),
        "embedding_meta": {"provider": "fake", "model": "fake", "dim": dim},
    }


class AjustarSimilaridadePorOutcomeTest(unittest.TestCase):
    def test_won_aplica_boost(self):
        self.assertAlmostEqual(
            _ajustar_similaridade_por_outcome(0.5, "won"), 0.5 + OUTCOME_BOOST_WON
        )

    def test_lost_aplica_penalidade(self):
        self.assertAlmostEqual(
            _ajustar_similaridade_por_outcome(0.5, "lost"), 0.5 - OUTCOME_PENALTY_LOST
        )

    def test_sem_status_e_neutro(self):
        self.assertEqual(_ajustar_similaridade_por_outcome(0.5, None), 0.5)

    def test_status_open_e_neutro(self):
        self.assertEqual(_ajustar_similaridade_por_outcome(0.5, "open"), 0.5)

    def test_boost_nao_ultrapassa_1(self):
        self.assertEqual(_ajustar_similaridade_por_outcome(0.99, "won"), 1.0)

    def test_penalidade_nao_fica_negativa(self):
        self.assertEqual(_ajustar_similaridade_por_outcome(0.05, "lost"), 0.0)


class StatusReunioesOrigemTest(unittest.TestCase):
    def test_ignora_ids_vazios_sem_chamar_playbook(self):
        with patch("agent.playbook_generator.listar_status_reunioes") as mock_listar:
            resultado = _status_reunioes_origem({"", None})
        mock_listar.assert_not_called()
        self.assertEqual(resultado, {})

    def test_repassa_ids_validos_para_listar_status_reunioes(self):
        with patch(
            "agent.playbook_generator.listar_status_reunioes",
            return_value={"m1": "won"},
        ) as mock_listar:
            resultado = _status_reunioes_origem({"m1", ""})
        mock_listar.assert_called_once()
        (chamados,), _ = mock_listar.call_args
        self.assertEqual(list(chamados), ["m1"])
        self.assertEqual(resultado, {"m1": "won"})

    def test_falha_no_lookup_retorna_vazio_sem_lancar(self):
        with patch(
            "agent.playbook_generator.listar_status_reunioes",
            side_effect=RuntimeError("db down"),
        ):
            resultado = _status_reunioes_origem({"m1"})
        self.assertEqual(resultado, {})


class BuscarMemoriasSemanticoOutcomeTest(unittest.TestCase):
    def setUp(self):
        self.addCleanup(sales_memory.invalidar_cache_memorias)

    def test_memoria_sem_status_fica_neutra_ordem_por_similaridade_bruta(self):
        cache = _cache_fake(
            vetores=[[1.0, 0.0], [0.9, 0.1]],
            origens=["", ""],
        )
        sales_memory._cache_memorias = cache
        with patch.object(sales_memory, "gerar_embedding", return_value=[1.0, 0.0]), \
             patch("agent.playbook_generator.listar_status_reunioes", return_value={}) as mock_listar:
            resultados = buscar_memorias_semantico("query", top_k=2, similarity_min=0.0)

        mock_listar.assert_not_called()
        self.assertEqual(resultados[0]["id"], "mem-0")
        self.assertIsNone(resultados[0]["outcome"])
        self.assertEqual(resultados[0]["similarity"], 1.0)

    def test_memoria_de_reuniao_ganha_sobe_no_ranking(self):
        # mem-0 tem similaridade bruta maior (cos=0.90) mas mem-1 veio de
        # reunião "won" (cos=0.87) e a diferença bruta (0.03) é menor que o
        # boost (0.05) — mem-1 deve ultrapassar mem-0 no ranking final.
        cache = _cache_fake(
            vetores=[[1.0, 0.4843], [1.0, 0.5667]],
            origens=["m-aberta", "m-ganha"],
        )
        sales_memory._cache_memorias = cache
        with patch.object(sales_memory, "gerar_embedding", return_value=[1.0, 0.0]), \
             patch(
                 "agent.playbook_generator.listar_status_reunioes",
                 return_value={"m-ganha": "won"},
             ):
            resultados = buscar_memorias_semantico("query", top_k=2, similarity_min=0.0)

        self.assertEqual(resultados[0]["id"], "mem-1")
        self.assertEqual(resultados[0]["outcome"], "won")

    def test_memoria_de_reuniao_perdida_desce_no_ranking(self):
        # mem-0 (cos=0.95) veio de reunião "lost" e leva penalidade (0.10),
        # ficando abaixo de mem-1 (cos=0.90, neutra) no ranking final.
        cache = _cache_fake(
            vetores=[[1.0, 0.3286], [1.0, 0.4843]],
            origens=["m-perdida", "m-aberta"],
        )
        sales_memory._cache_memorias = cache
        with patch.object(sales_memory, "gerar_embedding", return_value=[1.0, 0.0]), \
             patch(
                 "agent.playbook_generator.listar_status_reunioes",
                 return_value={"m-perdida": "lost"},
             ):
            resultados = buscar_memorias_semantico("query", top_k=2, similarity_min=0.0)

        self.assertEqual(resultados[0]["id"], "mem-1")
        self.assertEqual(resultados[1]["id"], "mem-0")
        self.assertEqual(resultados[1]["outcome"], "lost")

    def test_top_k_e_respeitado_apos_reordenacao(self):
        cache = _cache_fake(
            vetores=[[1.0, 0.0], [0.9, 0.1], [0.8, 0.2]],
            origens=["", "", ""],
        )
        sales_memory._cache_memorias = cache
        with patch.object(sales_memory, "gerar_embedding", return_value=[1.0, 0.0]), \
             patch("agent.playbook_generator.listar_status_reunioes", return_value={}):
            resultados = buscar_memorias_semantico("query", top_k=2, similarity_min=0.0)

        self.assertEqual(len(resultados), 2)


if __name__ == "__main__":
    unittest.main()
