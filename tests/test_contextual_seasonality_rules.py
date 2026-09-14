"""
Testes de agent/contextual_seasonality_rules.py — Fase 9 / Tarefa 9.3
do "PROMPT MESTRE — SALE-IA V2" (Sazonalidade Contextual).

Módulo puro (sem IA, sem banco) — mesmo padrão de
tests/test_seasonality_rules.py.

Run:
    python -m unittest tests.test_contextual_seasonality_rules -v
"""

import random
import unittest

from agent.contextual_seasonality_rules import (
    DIMENSOES_CONTEXTO,
    TEMPLATE_SAZONALIDADE_CONTEXTUAL,
    detectar_sazonalidade_contextual,
)


def _linha(won, quarter, segment, **extra):
    return {"won": won, "lost": not won, "quarter": quarter, "segment": segment, **extra}


class DetectarSazonalidadeContextualConhecidaTest(unittest.TestCase):
    """Exemplo literal do prompt mestre: Q4 × segmento SaaS é uma
    descoberta. Adaptado pra conversão (a "descoberta" da Tarefa 9.3 é
    uma divergência de taxa, não um "campo dominante" — decisão
    deliberada de escopo, ver CLAUDE.md)."""

    def _dataset(self):
        linhas = []
        for quarter in (1, 2, 3, 4):
            for segment in ("SaaS", "Varejo"):
                # Q4 x SaaS tem conversao bem acima do resto (+30pp)
                taxa = 0.80 if (quarter == 4 and segment == "SaaS") else 0.50
                n_won = int(60 * taxa)
                linhas += [_linha(True, quarter, segment) for _ in range(n_won)]
                linhas += [_linha(False, quarter, segment) for _ in range(60 - n_won)]
        return linhas

    def test_detecta_q4_saas_como_descoberta_significativa(self):
        linhas = self._dataset()
        descobertas = detectar_sazonalidade_contextual(linhas, "quarter", "segment")

        alvo = next((d for d in descobertas if d["period"] == 4 and d["context_value"] == "SaaS"), None)
        self.assertIsNotNone(alvo, "Q4 x SaaS deveria estar entre as descobertas")
        self.assertGreater(alvo["difference"], 0.20)
        self.assertIsNotNone(alvo["afirmacao"])

    def test_descobertas_tem_todos_os_6_campos_literais_do_prompt_mestre(self):
        linhas = self._dataset()
        descobertas = detectar_sazonalidade_contextual(linhas, "quarter", "segment")
        self.assertTrue(descobertas)
        campos_esperados = {"sample_size", "baseline", "observed", "difference", "confidence", "period"}
        for descoberta in descobertas:
            self.assertTrue(campos_esperados.issubset(descoberta.keys()))

    def test_descobertas_ordenadas_por_magnitude_da_diferenca(self):
        linhas = self._dataset()
        descobertas = detectar_sazonalidade_contextual(linhas, "quarter", "segment")
        diferencas_abs = [abs(d["difference"]) for d in descobertas]
        self.assertEqual(diferencas_abs, sorted(diferencas_abs, reverse=True))

    def test_outras_combinacoes_nao_viram_descoberta(self):
        linhas = self._dataset()
        descobertas = detectar_sazonalidade_contextual(linhas, "quarter", "segment")
        chaves = {(d["period"], d["context_value"]) for d in descobertas}
        self.assertNotIn((1, "SaaS"), chaves)
        self.assertNotIn((4, "Varejo"), chaves)


class DetectarSazonalidadeContextualSemSinalTest(unittest.TestCase):
    def test_dataset_com_taxa_identica_nao_gera_descobertas(self):
        linhas = []
        for quarter in (1, 2, 3, 4):
            for segment in ("SaaS", "Varejo"):
                linhas += [_linha(True, quarter, segment) for _ in range(30)]
                linhas += [_linha(False, quarter, segment) for _ in range(30)]
        descobertas = detectar_sazonalidade_contextual(linhas, "quarter", "segment")
        self.assertEqual(descobertas, [])

    def test_dataset_aleatorio_com_seed_fixa_gera_poucas_descobertas(self):
        rng = random.Random(7)
        linhas = []
        for quarter in (1, 2, 3, 4):
            for segment in ("SaaS", "Varejo", "Enterprise"):
                for _ in range(100):
                    linhas.append(_linha(rng.random() < 0.5, quarter, segment))
        descobertas = detectar_sazonalidade_contextual(linhas, "quarter", "segment")
        # 12 combinacoes testadas, IC 95% -> ~5% de falso-positivo esperado por combinacao
        self.assertLessEqual(len(descobertas), 2)


class ValidacaoTest(unittest.TestCase):
    def test_dimensao_temporal_invalida_levanta(self):
        with self.assertRaises(ValueError):
            detectar_sazonalidade_contextual([], "date", "segment")

    def test_dimensao_contexto_vazia_levanta(self):
        with self.assertRaises(ValueError):
            detectar_sazonalidade_contextual([], "quarter", "")

    def test_dataset_vazio_nao_levanta(self):
        self.assertEqual(detectar_sazonalidade_contextual([], "quarter", "segment"), [])

    def test_linha_sem_valor_de_contexto_e_ignorada(self):
        linhas = [_linha(True, 4, None) for _ in range(40)] + [_linha(False, 4, None) for _ in range(40)]
        self.assertEqual(detectar_sazonalidade_contextual(linhas, "quarter", "segment"), [])

    def test_dimensoes_contexto_documenta_os_7_campos_literais(self):
        self.assertEqual(
            DIMENSOES_CONTEXTO,
            {"segment", "product", "origin", "ticket", "client_type", "objection_type", "opportunity_stage"},
        )


class GuardaContraCausalidadeTest(unittest.TestCase):
    def test_template_nunca_declara_causalidade(self):
        self.assertNotIn("causa", TEMPLATE_SAZONALIDADE_CONTEXTUAL.lower())
        self.assertIn("associad", TEMPLATE_SAZONALIDADE_CONTEXTUAL.lower())


if __name__ == "__main__":
    unittest.main()
