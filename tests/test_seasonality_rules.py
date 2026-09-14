"""
Testes de agent/seasonality_rules.py — Fase 9 / Tarefa 9.2 do "PROMPT
MESTRE — SALE-IA V2" (Sazonalidade temporal).

Módulo puro (sem IA, sem banco) — mesmo padrão de
tests/test_win_loss_rules.py.

Run:
    python -m unittest tests.test_seasonality_rules -v
"""

import random
import unittest

from agent.seasonality_rules import (
    DIMENSOES_TEMPORAIS,
    TEMPLATE_SAZONALIDADE,
    detectar_sazonalidade,
    taxa_conversao_por_periodo,
)


def _linha(won, month, **extra):
    return {"won": won, "lost": not won, "month": month, **extra}


class TaxaConversaoPorPeriodoTest(unittest.TestCase):
    def test_agrupa_e_calcula_taxa_por_mes(self):
        linhas = [_linha(True, 3)] * 8 + [_linha(False, 3)] * 2 + [_linha(True, 6)] * 5 + [_linha(False, 6)] * 5
        resultado = taxa_conversao_por_periodo(linhas, "month")
        self.assertAlmostEqual(resultado[3]["taxa_conversao"], 0.8)
        self.assertAlmostEqual(resultado[6]["taxa_conversao"], 0.5)

    def test_linha_sem_desfecho_nao_entra(self):
        linhas = [_linha(True, 3), {"won": False, "lost": False, "month": 3}]  # ainda aberta
        resultado = taxa_conversao_por_periodo(linhas, "month")
        self.assertEqual(resultado[3]["total"], 1)

    def test_linha_sem_periodo_e_ignorada(self):
        linhas = [_linha(True, None)]
        resultado = taxa_conversao_por_periodo(linhas, "month")
        self.assertEqual(resultado, {})

    def test_dimensao_invalida_levanta(self):
        with self.assertRaises(ValueError):
            taxa_conversao_por_periodo([], "date")  # "date" fora de proposito, nao e temporal recorrente


class DetectarSazonalidadeConhecidaTest(unittest.TestCase):
    """'Gerar dataset sintético contendo sazonalidade conhecida. O
    motor deverá detectá-la.' — exemplo literal do prompt mestre:
    segmento X, março-maio, conversion +18%."""

    def _dataset_com_sazonalidade_marco_maio(self):
        linhas = []
        for mes in range(1, 13):
            taxa = 0.68 if mes in (3, 4, 5) else 0.50  # +18pp em marco-maio
            n_won = int(100 * taxa)
            n_lost = 100 - n_won
            linhas += [_linha(True, mes) for _ in range(n_won)]
            linhas += [_linha(False, mes) for _ in range(n_lost)]
        return linhas

    def test_marco_maio_detectados_como_significativos(self):
        linhas = self._dataset_com_sazonalidade_marco_maio()
        resultado = detectar_sazonalidade(linhas, "month")

        for mes in (3, 4, 5):
            periodo = resultado["periodos"][mes]
            self.assertTrue(periodo["significativo"], f"mes {mes} deveria ser significativo")
            self.assertGreater(periodo["diferenca_vs_baseline"], 0.10)
            self.assertIsNotNone(periodo["afirmacao"])

    def test_outros_meses_nao_sao_marcados_como_significativos(self):
        linhas = self._dataset_com_sazonalidade_marco_maio()
        resultado = detectar_sazonalidade(linhas, "month")

        for mes in (1, 2, 6, 7, 8, 9, 10, 11, 12):
            self.assertFalse(resultado["periodos"][mes]["significativo"], f"mes {mes} nao deveria ser significativo")

    def test_baseline_reflete_a_media_geral(self):
        linhas = self._dataset_com_sazonalidade_marco_maio()
        resultado = detectar_sazonalidade(linhas, "month")
        # 9 meses a 50% + 3 meses a 68% = baseline levemente acima de 50%
        self.assertGreater(resultado["baseline_taxa_conversao"], 0.50)
        self.assertLess(resultado["baseline_taxa_conversao"], 0.55)


class DetectarSazonalidadeSemSinalTest(unittest.TestCase):
    """'Criar também dataset aleatório. O motor NÃO deverá inventar
    sazonalidade significativa.'"""

    def test_dataset_com_taxa_identica_em_todo_periodo_nao_gera_falso_positivo(self):
        """Caso determinístico: todo período tem exatamente a mesma
        taxa de conversão — nenhuma divergência real existe, então
        nenhum período pode ser significativo, sempre, sem depender de
        sorte de seed aleatória."""
        linhas = []
        for mes in range(1, 13):
            linhas += [_linha(True, mes) for _ in range(50)]
            linhas += [_linha(False, mes) for _ in range(50)]
        resultado = detectar_sazonalidade(linhas, "month")
        self.assertTrue(all(not p["significativo"] for p in resultado["periodos"].values()))

    def test_dataset_aleatorio_com_seed_fixa_nao_gera_excesso_de_falsos_positivos(self):
        """Dataset genuinamente aleatório (taxa constante de 50%,
        independente do mês) com seed fixa — reprodutível a cada run.
        Um IC de 95% tem ~5% de falso-positivo por período testado; com
        12 meses, é estatisticamente esperado (não um bug) que raros
        periodos cruzem a linha por acaso. O motor não pode inventar
        sazonalidade em excesso — toleramos no máximo 1 dos 12."""
        rng = random.Random(42)
        linhas = []
        for mes in range(1, 13):
            for _ in range(200):
                linhas.append(_linha(rng.random() < 0.5, mes))
        resultado = detectar_sazonalidade(linhas, "month")
        falsos_positivos = sum(1 for p in resultado["periodos"].values() if p["significativo"])
        self.assertLessEqual(falsos_positivos, 1)

    def test_amostra_insuficiente_nunca_e_marcada_significativa(self):
        linhas = (
            [_linha(True, 1)] * 2 + [_linha(False, 1)] * 3  # mes 1: n=5, taxa=40% (bem abaixo do minimo de amostra)
            + [_linha(True, 2)] * 50 + [_linha(False, 2)] * 50  # mes 2: n=100, define o baseline
        )
        resultado = detectar_sazonalidade(linhas, "month", minimo_amostra=30)
        self.assertFalse(resultado["periodos"][1]["amostra_suficiente"])
        self.assertFalse(resultado["periodos"][1]["significativo"])
        self.assertIsNone(resultado["periodos"][1]["afirmacao"])


class GuardaContraCausalidadeTest(unittest.TestCase):
    def test_template_nunca_declara_causalidade(self):
        self.assertNotIn("causa", TEMPLATE_SAZONALIDADE.lower())
        self.assertIn("associad", TEMPLATE_SAZONALIDADE.lower())

    def test_afirmacao_gerada_em_tempo_real_nunca_contem_causa(self):
        linhas = []
        for mes in range(1, 4):
            taxa = 0.80 if mes == 1 else 0.40
            n_won = int(50 * taxa)
            linhas += [_linha(True, mes) for _ in range(n_won)]
            linhas += [_linha(False, mes) for _ in range(50 - n_won)]
        resultado = detectar_sazonalidade(linhas, "month")
        afirmacoes = [p["afirmacao"] for p in resultado["periodos"].values() if p["afirmacao"]]
        self.assertTrue(afirmacoes)  # pelo menos uma foi gerada
        for afirmacao in afirmacoes:
            self.assertNotIn("causa", afirmacao.lower())


if __name__ == "__main__":
    unittest.main()
