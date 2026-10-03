"""
Testes — Tarefa D3 (docs/tasks-prompt-mestre-v2-restante.md, objection
classification 75% → 90%): conjunto de classificação de objeções,
correção do `objections-04` do Golden Dataset, medição no runner e
regras de desempate no prompt do classificador. Nunca chama IA.

Run:
    python -m unittest tests.test_objection_classification_set -v
"""

import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import yaml

from agent.objection_rules import OBJECTION_TIPOS
from agent.quality_monitoring_golden_runner import (
    ARQUIVO_OBJECOES,
    carregar_cenarios_golden_dataset,
    carregar_conjunto_classificacao_objecoes,
    executar_golden_dataset_async,
    extrair_categoria_esperada,
    montar_relatorio_metricas,
)

_RAIZ = Path(__file__).parent.parent


class ConjuntoTest(unittest.TestCase):
    def setUp(self):
        self.casos = carregar_conjunto_classificacao_objecoes()

    def test_estrutura(self):
        self.assertEqual(len(self.casos), 30)
        self.assertEqual(len({c["id"] for c in self.casos}), 30)
        for caso in self.casos:
            self.assertIn(caso["categoria"], OBJECTION_TIPOS, caso["id"])
            self.assertIn(caso["fonte"], ("real_anonimizado", "sintetico"), caso["id"])
            self.assertTrue(caso["texto"].strip(), caso["id"])

    def test_cobre_as_13_categorias(self):
        self.assertEqual({c["categoria"] for c in self.casos}, set(OBJECTION_TIPOS))

    def test_reais_vem_do_dataset_anonimizado(self):
        """Rastreabilidade: toda fala marcada como real existe no dataset
        de objeções reais já anonimizado (nenhuma fala nova de cliente)."""
        reais = yaml.safe_load((_RAIZ / "evals/datasets/coach/objections_real.yaml").read_text(encoding="utf-8"))
        falas = {x["vars"]["transcricao"].removeprefix("Cliente: ").strip() for x in reais}
        marcados = [c for c in self.casos if c["fonte"] == "real_anonimizado"]
        self.assertEqual(len(marcados), 17)
        for caso in marcados:
            self.assertIn(caso["texto"].strip(), falas, caso["id"])


class GoldenObjecoesTest(unittest.TestCase):
    def test_citacao_esta_no_input_e_a_categoria_e_extraivel(self):
        """Fecha a classe do bug dos 75%: a citação mandada ao
        classificador precisa ser a da objeção falada, dentro do input."""
        objecoes = [c for c in carregar_cenarios_golden_dataset() if c["_arquivo"] == ARQUIVO_OBJECOES]
        self.assertEqual(len(objecoes), 4)
        for cenario in objecoes:
            fato = cenario["expected_facts"][0]
            self.assertEqual(fato["campo"], "objection_spoken", cenario["id"])
            self.assertIn(fato["evidence_quote"], cenario["input"], cenario["id"])
            self.assertIn(extrair_categoria_esperada(fato["valor"]), OBJECTION_TIPOS, cenario["id"])

    def test_objections_04_fala_e_causa_raiz_separadas(self):
        cenario = next(c for c in carregar_cenarios_golden_dataset() if c["id"] == "objections-04")
        falada, causa = cenario["expected_facts"]
        self.assertEqual(extrair_categoria_esperada(falada["valor"]), "PRICE")
        self.assertEqual(falada["evidence_quote"], "Está caro pra gente agora.")
        self.assertEqual((causa["campo"], causa["valor"]), ("root_cause_hypothesis", "ADOPTION"))


class MedicaoNoRunnerTest(unittest.TestCase):
    def test_conjunto_entra_na_precisao_e_erros_sao_listados(self):
        conjunto = [
            {"id": "oc-a", "texto": "achei caro", "categoria": "PRICE"},
            {"id": "oc-b", "texto": "sem caixa agora", "categoria": "BUDGET"},
            {"id": "oc-c", "texto": "fala ambígua", "categoria": "VALUE"},
        ]
        respostas = {"achei caro": "PRICE", "sem caixa agora": "PRICE", "fala ambígua": None}
        classificador = AsyncMock(side_effect=lambda texto, *a, **k: respostas[texto])
        with patch("agent.objection_category_classifier.classificar_categoria_objecao_async", new=classificador):
            contagens = asyncio.run(executar_golden_dataset_async(cenarios=[], conjunto_objecoes=conjunto))
        self.assertEqual((contagens["objecao_vp"], contagens["objecao_fp"]), (1, 2))
        relatorio = montar_relatorio_metricas({**contagens, "afirmacoes_com_evidencia": 0, "afirmacoes_sem_evidencia": 0})
        self.assertAlmostEqual(relatorio["objection_precision"], 1 / 3, places=3)
        self.assertEqual(
            [(e["caso"], e["esperado"], e["previsto"]) for e in relatorio["objecoes_erradas"]],
            [("oc-b", "BUDGET", "PRICE"), ("oc-c", "VALUE", None)],
        )

    def test_rodada_de_teste_com_cenarios_proprios_nao_carrega_o_conjunto(self):
        classificador = AsyncMock(return_value="PRICE")
        with patch("agent.objection_category_classifier.classificar_categoria_objecao_async", new=classificador):
            contagens = asyncio.run(executar_golden_dataset_async(cenarios=[]))
        classificador.assert_not_awaited()
        self.assertEqual(contagens["objecoes_erradas"], [])


class PromptTest(unittest.TestCase):
    def test_regras_de_desempate_no_prompt(self):
        texto = (_RAIZ / "agent/prompt_templates/objecao_categoria_classificacao.txt").read_text(encoding="utf-8")
        self.assertIn("Classifique o que o cliente DISSE", texto)
        for par in ("BUDGET = ", "PRIORITY = ", "IMPLEMENTATION = ", "PROCUREMENT = ", "SECURITY = "):
            self.assertIn(par, texto)
        self.assertIn("{objecao_texto}", texto)


if __name__ == "__main__":
    unittest.main()
