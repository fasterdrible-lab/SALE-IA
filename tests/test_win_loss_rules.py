"""
Testes de agent/win_loss_rules.py — Fase 8 / Tarefa 8.2 do "PROMPT
MESTRE — SALE-IA V2" (Win/Loss Intelligence).

Módulo puro (sem IA, sem banco, sem numpy/scipy) — mesmo padrão de
tests/test_outcome_rules.py / tests/test_deal_risk_rules.py.

Run:
    python -m unittest tests.test_win_loss_rules -v
"""

import unittest

from agent.win_loss_rules import (
    TEMPLATE_AFIRMACAO_ASSOCIACAO,
    TEMPLATE_AMOSTRA_INSUFICIENTE,
    TEMPLATE_SIMPSONS_PARADOX,
    amostra_suficiente,
    calcular_limites_iqr,
    calcular_taxa_conversao,
    comparar_por_variavel_categorica,
    detectar_outliers_iqr,
    detectar_simpsons_paradox,
    intervalo_confianca_wilson,
    resumir_variavel_numerica,
)


def _opp(status, **campos):
    return {"status": status, **campos}


class CalcularTaxaConversaoTest(unittest.TestCase):
    def test_taxa_basica(self):
        opps = [_opp("won"), _opp("won"), _opp("lost"), _opp("open"), _opp("abandoned")]
        resultado = calcular_taxa_conversao(opps)
        self.assertEqual(resultado["won"], 2)
        self.assertEqual(resultado["lost"], 1)
        self.assertEqual(resultado["total"], 3)  # open/abandoned nao contam
        self.assertAlmostEqual(resultado["taxa_conversao"], 2 / 3)

    def test_sem_dados_retorna_taxa_none(self):
        resultado = calcular_taxa_conversao([])
        self.assertEqual(resultado["total"], 0)
        self.assertIsNone(resultado["taxa_conversao"])


class AmostraSuficienteTest(unittest.TestCase):
    def test_padrao_30(self):
        self.assertFalse(amostra_suficiente(29))
        self.assertTrue(amostra_suficiente(30))

    def test_minimo_customizado(self):
        self.assertTrue(amostra_suficiente(10, minimo=10))
        self.assertFalse(amostra_suficiente(9, minimo=10))


class IntervaloConfiancaWilsonTest(unittest.TestCase):
    def test_total_zero_retorna_none(self):
        self.assertIsNone(intervalo_confianca_wilson(0, 0))

    def test_intervalo_contem_a_proporcao_observada(self):
        inferior, superior = intervalo_confianca_wilson(60, 100, confianca=0.95)
        self.assertLess(inferior, 0.60)
        self.assertGreater(superior, 0.60)

    def test_amostra_maior_produz_intervalo_mais_estreito(self):
        pequena = intervalo_confianca_wilson(6, 10)
        grande = intervalo_confianca_wilson(600, 1000)
        largura_pequena = pequena[1] - pequena[0]
        largura_grande = grande[1] - grande[0]
        self.assertLess(largura_grande, largura_pequena)

    def test_confianca_nao_suportada_levanta(self):
        with self.assertRaises(ValueError):
            intervalo_confianca_wilson(5, 10, confianca=0.5)


class OutliersIQRTest(unittest.TestCase):
    def test_amostra_pequena_demais_nao_detecta_nada(self):
        self.assertIsNone(calcular_limites_iqr([1, 2, 3]))
        self.assertEqual(detectar_outliers_iqr([1, 2, 3]), [])

    def test_detecta_outlier_obvio(self):
        valores = [10, 12, 11, 13, 12, 11, 10, 12, 500]
        outliers = detectar_outliers_iqr(valores)
        self.assertIn(500, outliers)
        self.assertNotIn(12, outliers)

    def test_sem_outliers_retorna_lista_vazia(self):
        valores = [10, 11, 12, 13, 14, 15]
        self.assertEqual(detectar_outliers_iqr(valores), [])


class CompararPorVariavelCategoricaTest(unittest.TestCase):
    def test_divisao_por_segmento_categorico(self):
        """'divisão por segmento' — a Tarefa 8.2 pede explicitamente
        que o motor compare grupos categóricos corretamente."""
        opps = (
            [_opp("won", segment="SMB") for _ in range(40)]
            + [_opp("lost", segment="SMB") for _ in range(10)]
            + [_opp("won", segment="Enterprise") for _ in range(10)]
            + [_opp("lost", segment="Enterprise") for _ in range(40)]
        )
        resultado = comparar_por_variavel_categorica(opps, "segment")
        self.assertAlmostEqual(resultado["grupos"]["SMB"]["taxa_conversao"], 0.8)
        self.assertAlmostEqual(resultado["grupos"]["Enterprise"]["taxa_conversao"], 0.2)
        self.assertTrue(resultado["grupos"]["SMB"]["amostra_suficiente"])
        self.assertIsNotNone(resultado["grupos"]["SMB"]["intervalo_confianca"])

    def test_ausencia_de_dados_nao_quebra_e_e_contada_separadamente(self):
        """'ausência de dados' — oportunidade sem valor no campo nunca
        vira um grupo "None" nem é descartada silenciosamente."""
        opps = [
            _opp("won", origin="ads"),
            _opp("lost", origin=None),
            _opp("won"),  # campo nem presente
        ]
        resultado = comparar_por_variavel_categorica(opps, "origin")
        self.assertEqual(resultado["sem_dado"], 2)
        self.assertNotIn(None, resultado["grupos"])
        self.assertEqual(set(resultado["grupos"].keys()), {"ads"})

    def test_amostra_insuficiente_nao_gera_intervalo_nem_afirmacao_de_associacao(self):
        opps = [_opp("won", strategy="X"), _opp("lost", strategy="X")]  # n=2
        resultado = comparar_por_variavel_categorica(opps, "strategy", minimo_amostra=30)
        grupo = resultado["grupos"]["X"]
        self.assertFalse(grupo["amostra_suficiente"])
        self.assertIsNone(grupo["intervalo_confianca"])
        self.assertIn("amostra insuficiente", grupo["afirmacao"])

    def test_campo_vazio_levanta(self):
        with self.assertRaises(ValueError):
            comparar_por_variavel_categorica([_opp("won")], "")


class ResumirVariavelNumericaTest(unittest.TestCase):
    def test_media_e_mediana_sem_outliers(self):
        opps = [_opp("won", ticket=v) for v in (100, 110, 105, 95, 108, 102, 5000)]
        resultado = resumir_variavel_numerica(opps, "ticket")
        self.assertEqual(resultado["n"], 7)
        self.assertEqual(resultado["n_outliers"], 1)
        self.assertIn(5000, resultado["outliers"])
        self.assertLess(resultado["media_sem_outliers"], 200)  # 5000 nao distorce a media

    def test_filtra_por_status(self):
        opps = [_opp("won", cycle=10), _opp("won", cycle=20), _opp("lost", cycle=999)]
        resultado = resumir_variavel_numerica(opps, "cycle", status_filtro="won")
        self.assertEqual(resultado["n"], 2)

    def test_sem_dados_retorna_estrutura_vazia(self):
        resultado = resumir_variavel_numerica([], "ticket")
        self.assertEqual(resultado["n"], 0)
        self.assertIsNone(resultado["media_sem_outliers"])


class SimpsonsParadoxTest(unittest.TestCase):
    def _dataset_sintetico(self):
        """Reproduz a estrutura clássica de paradoxo de Simpson (mesmos
        números do exemplo clássico de tratamento A/B por tamanho de
        cálculo renal, adaptado ao domínio comercial: 2 estratégias de
        venda, segmentadas por porte do negócio).

        Small: A 81/87 (93%) > B 234/270 (87%)
        Large: A 192/263 (73%) > B 55/80 (69%)
        Agregado: A 273/350 (78%) < B 289/350 (83%) — inverte!
        """
        def grupo(estrategia, porte, ganhas, total):
            perdidas = total - ganhas
            return (
                [_opp("won", strategy=estrategia, deal_size=porte) for _ in range(ganhas)]
                + [_opp("lost", strategy=estrategia, deal_size=porte) for _ in range(perdidas)]
            )

        return (
            grupo("A", "small", 81, 87)
            + grupo("B", "small", 234, 270)
            + grupo("A", "large", 192, 263)
            + grupo("B", "large", 55, 80)
        )

    def test_detecta_paradoxo_no_dataset_sintetico_classico(self):
        opps = self._dataset_sintetico()
        resultado = detectar_simpsons_paradox(opps, campo="strategy", campo_segmento="deal_size")

        self.assertEqual(resultado["direcao_agregada"], "B")  # B vence agregado
        self.assertEqual(resultado["direcoes_por_segmento"]["small"], "A")  # A vence em cada segmento
        self.assertEqual(resultado["direcoes_por_segmento"]["large"], "A")
        self.assertTrue(resultado["possivel_simpsons_paradox"])
        self.assertIsNotNone(resultado["afirmacao"])
        self.assertNotIn("causa", resultado["afirmacao"].lower())

    def test_sem_reversao_nao_marca_paradoxo(self):
        opps = (
            [_opp("won", strategy="A", deal_size="small") for _ in range(40)]
            + [_opp("lost", strategy="A", deal_size="small") for _ in range(10)]
            + [_opp("won", strategy="B", deal_size="small") for _ in range(10)]
            + [_opp("lost", strategy="B", deal_size="small") for _ in range(40)]
            + [_opp("won", strategy="A", deal_size="large") for _ in range(40)]
            + [_opp("lost", strategy="A", deal_size="large") for _ in range(10)]
            + [_opp("won", strategy="B", deal_size="large") for _ in range(10)]
            + [_opp("lost", strategy="B", deal_size="large") for _ in range(40)]
        )
        resultado = detectar_simpsons_paradox(opps, campo="strategy", campo_segmento="deal_size")
        self.assertFalse(resultado["possivel_simpsons_paradox"])
        self.assertIsNone(resultado["afirmacao"])

    def test_mais_de_2_grupos_levanta(self):
        opps = [
            _opp("won", strategy="A"), _opp("lost", strategy="A"),
            _opp("won", strategy="B"), _opp("lost", strategy="B"),
            _opp("won", strategy="C"), _opp("lost", strategy="C"),
        ]
        with self.assertRaises(ValueError):
            detectar_simpsons_paradox(opps, campo="strategy", campo_segmento="deal_size")


class GuardaContraCausalidadeTest(unittest.TestCase):
    """Regra científica central da Tarefa 8.2: nunca declarar
    causalidade ("X causa vendas"), sempre associação ("X está
    associado a maior conversão nesta amostra")."""

    def test_templates_nunca_declaram_causalidade(self):
        for template in (TEMPLATE_AFIRMACAO_ASSOCIACAO, TEMPLATE_AMOSTRA_INSUFICIENTE, TEMPLATE_SIMPSONS_PARADOX):
            self.assertNotIn("causa", template.lower())
            self.assertNotIn("causou", template.lower())

    def test_template_de_associacao_usa_linguagem_de_associacao(self):
        self.assertIn("associad", TEMPLATE_AFIRMACAO_ASSOCIACAO.lower())

    def test_afirmacao_gerada_em_tempo_real_nunca_contem_causa(self):
        opps = [_opp("won", segment="SMB") for _ in range(35)] + [_opp("lost", segment="SMB") for _ in range(5)]
        resultado = comparar_por_variavel_categorica(opps, "segment")
        self.assertNotIn("causa", resultado["grupos"]["SMB"]["afirmacao"].lower())


if __name__ == "__main__":
    unittest.main()
