"""
Testes — agent/quality_monitoring_golden_runner.py (Fase 25, "o que
falta pra ligar", item 3/5: Golden Dataset → Quality Monitoring).

Cobre as funções puras (extrair_categoria_esperada/
evidencia_fundamentada/montar_texto_fundamentacao/
carregar_cenarios_golden_dataset — sem IA) e o motor real
(executar_golden_dataset_async, mockando raciocinar_async/
classificar_categoria_objecao_async, mesmo padrão de
tests/test_sales_reasoning_engine.py) + o reshape final
(montar_relatorio_metricas).

Run:
    python -m unittest tests.test_quality_monitoring_golden_runner -v
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from agent.quality_monitoring_golden_runner import (
    ARQUIVO_OBJECOES,
    carregar_cenarios_golden_dataset,
    evidencia_fundamentada,
    executar_golden_dataset_async,
    extrair_categoria_esperada,
    montar_relatorio_metricas,
    montar_texto_fundamentacao,
)


class CarregarCenariosTest(unittest.TestCase):
    def test_carrega_os_40_cenarios_reais_dos_10_arquivos(self):
        cenarios = carregar_cenarios_golden_dataset()
        self.assertEqual(len(cenarios), 40)
        arquivos = {c["_arquivo"] for c in cenarios}
        self.assertEqual(len(arquivos), 10)

    def test_cada_cenario_tem_input_e_id(self):
        for cenario in carregar_cenarios_golden_dataset():
            self.assertTrue(cenario.get("id"))
            self.assertTrue(cenario.get("input"))

    def test_objections_yaml_tem_4_cenarios(self):
        cenarios = carregar_cenarios_golden_dataset()
        objecoes = [c for c in cenarios if c["_arquivo"] == ARQUIVO_OBJECOES]
        self.assertEqual(len(objecoes), 4)


class ExtrairCategoriaEsperadaTest(unittest.TestCase):
    def test_categoria_simples(self):
        self.assertEqual(extrair_categoria_esperada("categoria TRUST"), "TRUST")

    def test_categoria_com_texto_extra_pega_a_primeira(self):
        self.assertEqual(
            extrair_categoria_esperada("categoria PRICE (fala literal), mas root cause é ADOPTION"),
            "PRICE",
        )

    def test_sem_padrao_retorna_none(self):
        self.assertIsNone(extrair_categoria_esperada("nenhuma categoria mencionada aqui"))

    def test_valor_none_retorna_none(self):
        self.assertIsNone(extrair_categoria_esperada(None))


class EvidenciaFundamentadaTest(unittest.TestCase):
    def test_substring_literal_bate(self):
        self.assertTrue(evidencia_fundamentada("tenho medo da equipe", "Cliente: tenho medo da equipe não usar."))

    def test_case_insensitive(self):
        self.assertTrue(evidencia_fundamentada("Tenho MEDO da equipe", "cliente diz: tenho medo da equipe hoje"))

    def test_afirmacao_totalmente_fabricada_nao_fundamentada(self):
        self.assertFalse(evidencia_fundamentada("frase inventada que não existe em lugar nenhum", "texto fonte totalmente diferente"))

    def test_afirmacao_vazia_retorna_false(self):
        self.assertFalse(evidencia_fundamentada("", "qualquer texto fonte"))
        self.assertFalse(evidencia_fundamentada(None, "qualquer texto fonte"))

    def test_paraphrase_de_campo_estruturado_e_fundamentada(self):
        # Achado real desta rodada: "meddpicc_state é null" é um fato
        # verdadeiro sobre a entrada (não uma citação literal de
        # nada), mas precisa contar como fundamentada — diferente do
        # antigo texto_contido_em (substring estrita), que marcava
        # isso como alucinação.
        fonte = 'meddpicc_state:\nnull\n\nspin_state:\n{"problem": {"missing": ["main_pain"]}}'
        self.assertTrue(evidencia_fundamentada("meddpicc_state é null", fonte))
        self.assertTrue(evidencia_fundamentada("spin_state.problem.missing inclui 'main_pain'", fonte))

    def test_rotulos_genericos_nao_inflam_cobertura(self):
        # "cliente"/"vendedor" aparecem em quase toda fonte real —
        # sozinhos, não podem "fundamentar" uma afirmação fabricada.
        fonte = "Cliente: preciso pensar. Vendedor: sem problema."
        self.assertFalse(evidencia_fundamentada(
            "cliente vendedor aprovou orcamento internamente hoje mesmo", fonte,
        ))

    def test_cobertura_minima_sobrescrevivel(self):
        fonte = "apenas uma palavra rara: xilofone"
        afirmacao = "xilofone mencionado"  # 1 de 2 tokens significativos bate (50%)
        self.assertFalse(evidencia_fundamentada(afirmacao, fonte, cobertura_minima=0.6))
        self.assertTrue(evidencia_fundamentada(afirmacao, fonte, cobertura_minima=0.4))


class MontarTextoFundamentacaoTest(unittest.TestCase):
    def test_inclui_texto_bruto_e_campos_estruturados_como_null(self):
        cenario = {"input": "Cliente: já validei com meu sócio."}
        texto = montar_texto_fundamentacao(cenario)
        self.assertIn("já validei com meu sócio", texto)
        self.assertIn("meddpicc_state", texto)
        self.assertIn("null", texto)

    def test_contexto_estruturado_aparece_serializado(self):
        cenario = {"input": "x"}
        contexto = {"spin_state": {"problem": {"missing": ["main_pain"]}}}
        texto = montar_texto_fundamentacao(cenario, contexto=contexto)
        self.assertIn("main_pain", texto)


def _cenario_framework(id_, input_, expected_framework):
    return {"id": id_, "input": input_, "expected_framework": expected_framework, "_arquivo": "discovery.yaml"}


def _cenario_objecao(id_, input_, evidence_quote, valor_categoria):
    return {
        "id": id_, "input": input_, "expected_framework": "OBJECTION_INVESTIGATION",
        "_arquivo": ARQUIVO_OBJECOES,
        "expected_facts": [{"campo": "objection_spoken", "valor": valor_categoria, "evidence_quote": evidence_quote}],
    }


class ExecutarGoldenDatasetAsyncTest(unittest.TestCase):
    def _run(self, cenarios, raciocinar_mock, classificar_mock=None, spin_mock=None, behavioral_mock=None, motivation_mock=None):
        with patch("agent.sales_reasoning_engine.raciocinar_async", new=raciocinar_mock), \
             patch("agent.objection_category_classifier.classificar_categoria_objecao_async", new=classificar_mock or AsyncMock(return_value=None)), \
             patch("agent.spin_extractor.extrair_spin_state_async", new=spin_mock or AsyncMock(return_value=None)), \
             patch("agent.behavioral_signal_extractor.extrair_sinais_comportamentais_async", new=behavioral_mock or AsyncMock(return_value=[])), \
             patch("agent.buyer_motivation_extractor.extrair_buyer_motivation_async", new=motivation_mock or AsyncMock(return_value=None)):
            return asyncio.run(executar_golden_dataset_async(cenarios))

    def test_framework_correto_e_incorreto(self):
        cenarios = [
            _cenario_framework("d-01", "cliente fala sobre time e ferramenta atual", "SPIN_SITUATION"),
            _cenario_framework("d-02", "cliente descreve a dor principal", "SPIN_PROBLEM"),
        ]
        respostas = iter([
            {"recommended_framework": "SPIN_SITUATION", "evidence": []},
            {"recommended_framework": "SPIN_IMPLICATION", "evidence": []},  # errado
        ])
        raciocinar_mock = AsyncMock(side_effect=lambda *a, **k: next(respostas))
        resultado = self._run(cenarios, raciocinar_mock)
        self.assertEqual(resultado["framework_corretos"], 1)
        self.assertEqual(resultado["framework_total"], 2)

    def test_cenario_sem_expected_framework_nao_conta_no_total(self):
        cenarios = [_cenario_framework("w-01", "reuniao de fechamento perdida", None)]
        raciocinar_mock = AsyncMock(return_value={"recommended_framework": "CLOSING", "evidence": []})
        resultado = self._run(cenarios, raciocinar_mock)
        self.assertEqual(resultado["framework_total"], 0)

    def test_evidencia_contida_e_nao_contida(self):
        cenarios = [_cenario_framework("d-01", "Cliente: nosso time tem 12 pessoas hoje.", "SPIN_SITUATION")]
        raciocinar_mock = AsyncMock(return_value={
            "recommended_framework": "SPIN_SITUATION",
            "evidence": ["nosso time tem 12 pessoas hoje", "afirmação totalmente inventada e fora do texto"],
        })
        resultado = self._run(cenarios, raciocinar_mock)
        self.assertEqual(resultado["afirmacoes_com_evidencia"], 1)
        self.assertEqual(resultado["afirmacoes_sem_evidencia"], 1)

    def test_objecao_classificada_corretamente_conta_vp(self):
        cenarios = [_cenario_objecao("o-01", "Cliente: nunca ouvi falar de vocês.", "nunca ouvi falar de vocês", "categoria TRUST")]
        raciocinar_mock = AsyncMock(return_value={"recommended_framework": "OBJECTION_INVESTIGATION", "evidence": []})
        classificar_mock = AsyncMock(return_value="TRUST")
        resultado = self._run(cenarios, raciocinar_mock, classificar_mock)
        classificar_mock.assert_awaited_once_with("nunca ouvi falar de vocês")
        self.assertEqual(resultado["objecao_vp"], 1)
        self.assertEqual(resultado["objecao_fp"], 0)

    def test_objecao_classificada_errado_conta_fp(self):
        cenarios = [_cenario_objecao("o-01", "x", "nunca ouvi falar de vocês", "categoria TRUST")]
        raciocinar_mock = AsyncMock(return_value={"recommended_framework": "OBJECTION_INVESTIGATION", "evidence": []})
        classificar_mock = AsyncMock(return_value="PRICE")
        resultado = self._run(cenarios, raciocinar_mock, classificar_mock)
        self.assertEqual(resultado["objecao_vp"], 0)
        self.assertEqual(resultado["objecao_fp"], 1)

    def test_classificador_retorna_none_conta_fp_nunca_vp(self):
        cenarios = [_cenario_objecao("o-01", "x", "nunca ouvi falar de vocês", "categoria TRUST")]
        raciocinar_mock = AsyncMock(return_value={"recommended_framework": "OBJECTION_INVESTIGATION", "evidence": []})
        classificar_mock = AsyncMock(return_value=None)
        resultado = self._run(cenarios, raciocinar_mock, classificar_mock)
        self.assertEqual(resultado["objecao_vp"], 0)
        self.assertEqual(resultado["objecao_fp"], 1)

    def test_falha_no_reasoning_de_um_cenario_nao_derruba_os_outros(self):
        cenarios = [
            _cenario_framework("d-01", "x", "SPIN_SITUATION"),
            _cenario_framework("d-02", "y", "SPIN_PROBLEM"),
        ]
        respostas = iter([
            Exception("provedor indisponível"),
            {"recommended_framework": "SPIN_PROBLEM", "evidence": []},
        ])

        async def _side_effect(*a, **k):
            r = next(respostas)
            if isinstance(r, Exception):
                raise r
            return r

        raciocinar_mock = AsyncMock(side_effect=_side_effect)
        resultado = self._run(cenarios, raciocinar_mock)
        self.assertEqual(resultado["framework_total"], 1)
        self.assertEqual(resultado["framework_corretos"], 1)
        self.assertEqual(len(resultado["erros"]), 1)
        self.assertIn("d-01", resultado["erros"][0])

    def test_falha_no_classificador_de_objecao_conta_como_erro_e_fp(self):
        cenarios = [_cenario_objecao("o-01", "x", "y", "categoria TRUST")]
        raciocinar_mock = AsyncMock(return_value={"recommended_framework": "OBJECTION_INVESTIGATION", "evidence": []})
        classificar_mock = AsyncMock(side_effect=Exception("embedding falhou"))
        resultado = self._run(cenarios, raciocinar_mock, classificar_mock)
        self.assertEqual(resultado["objecao_fp"], 1)
        self.assertEqual(len(resultado["erros"]), 1)

    def test_total_cenarios_reflete_a_lista_recebida(self):
        cenarios = [_cenario_framework("d-01", "x", "SPIN_SITUATION")]
        raciocinar_mock = AsyncMock(return_value={"recommended_framework": "SPIN_SITUATION", "evidence": []})
        resultado = self._run(cenarios, raciocinar_mock)
        self.assertEqual(resultado["total_cenarios"], 1)

    def test_entrada_do_reasoning_recebe_contexto_estruturado_real(self):
        cenarios = [_cenario_framework("d-01", "cliente descreve o time atual", "SPIN_SITUATION")]
        spin_mock = AsyncMock(return_value={"situation": {"known": [{"campo": "team_size"}], "missing": []}})
        behavioral_mock = AsyncMock(return_value=[{"signal": "PRICE_ANCHOR", "evidence_quote": "x"}])
        motivation_mock = AsyncMock(return_value={"motivation": "GROWTH", "confidence": 0.8, "evidence": ["x"]})
        raciocinar_mock = AsyncMock(return_value={"recommended_framework": "SPIN_SITUATION", "evidence": []})

        self._run(cenarios, raciocinar_mock, spin_mock=spin_mock, behavioral_mock=behavioral_mock, motivation_mock=motivation_mock)

        entrada_recebida = raciocinar_mock.call_args.args[0]
        self.assertEqual(entrada_recebida["spin_state"], spin_mock.return_value)
        self.assertEqual(entrada_recebida["behavioral_signals"], behavioral_mock.return_value)
        self.assertEqual(entrada_recebida["buyer_motivation"], motivation_mock.return_value)

    def test_meddpicc_state_nunca_e_preenchido(self):
        cenarios = [_cenario_framework("d-01", "x", "SPIN_SITUATION")]
        raciocinar_mock = AsyncMock(return_value={"recommended_framework": "SPIN_SITUATION", "evidence": []})
        self._run(cenarios, raciocinar_mock)
        entrada_recebida = raciocinar_mock.call_args.args[0]
        self.assertIsNone(entrada_recebida.get("meddpicc_state"))

    def test_objecao_classificada_vira_objection_spoken_real_na_entrada(self):
        cenarios = [_cenario_objecao("o-01", "x", "nunca ouvi falar de vocês", "categoria TRUST")]
        raciocinar_mock = AsyncMock(return_value={"recommended_framework": "OBJECTION_INVESTIGATION", "evidence": []})
        classificar_mock = AsyncMock(return_value="TRUST")
        self._run(cenarios, raciocinar_mock, classificar_mock)
        entrada_recebida = raciocinar_mock.call_args.args[0]
        self.assertEqual(len(entrada_recebida["objections"]), 1)
        objecao = entrada_recebida["objections"][0]
        self.assertEqual(objecao["objection_spoken"]["category"], "TRUST")
        self.assertEqual(objecao["objection_spoken"]["evidence_quote"], "nunca ouvi falar de vocês")

    def test_falha_na_extracao_de_contexto_nao_impede_o_reasoning(self):
        cenarios = [_cenario_framework("d-01", "x", "SPIN_SITUATION")]
        raciocinar_mock = AsyncMock(return_value={"recommended_framework": "SPIN_SITUATION", "evidence": []})
        spin_mock = AsyncMock(side_effect=Exception("provedor indisponível"))
        resultado = self._run(cenarios, raciocinar_mock, spin_mock=spin_mock)
        raciocinar_mock.assert_awaited_once()
        self.assertEqual(resultado["framework_corretos"], 1)


class MontarRelatorioMetricasTest(unittest.TestCase):
    def test_reshape_com_numeros_reais(self):
        contagens = {
            "framework_corretos": 20, "framework_total": 27,
            "objecao_vp": 3, "objecao_fp": 1,
            "afirmacoes_com_evidencia": 30, "afirmacoes_sem_evidencia": 5,
            "erros": [], "total_cenarios": 40,
        }
        relatorio = montar_relatorio_metricas(contagens)
        self.assertEqual(relatorio["framework_accuracy"], round(20 / 27, 4))
        self.assertEqual(relatorio["objection_precision"], round(3 / 4, 4))
        self.assertEqual(relatorio["hallucination_rate"], round(5 / 35, 4))
        self.assertEqual(relatorio["evidence_coverage"], round(30 / 35, 4))

    def test_event_precision_e_recommendation_relevance_sao_gaps_explicitos(self):
        contagens = {
            "framework_corretos": 0, "framework_total": 0,
            "objecao_vp": 0, "objecao_fp": 0,
            "afirmacoes_com_evidencia": 0, "afirmacoes_sem_evidencia": 0,
            "erros": [], "total_cenarios": 0,
        }
        relatorio = montar_relatorio_metricas(contagens)
        self.assertFalse(relatorio["event_precision"]["disponivel"])
        self.assertFalse(relatorio["recommendation_relevance"]["disponivel"])

    def test_denominador_zero_nunca_inventa_numero(self):
        contagens = {
            "framework_corretos": 0, "framework_total": 0,
            "objecao_vp": 0, "objecao_fp": 0,
            "afirmacoes_com_evidencia": 0, "afirmacoes_sem_evidencia": 0,
            "erros": [], "total_cenarios": 0,
        }
        relatorio = montar_relatorio_metricas(contagens)
        self.assertIsNone(relatorio["framework_accuracy"])
        self.assertIsNone(relatorio["objection_precision"])
        self.assertIsNone(relatorio["hallucination_rate"])
        self.assertIsNone(relatorio["evidence_coverage"])


if __name__ == "__main__":
    unittest.main()
