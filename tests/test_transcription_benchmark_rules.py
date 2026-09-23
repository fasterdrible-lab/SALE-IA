"""
Testes de agent/transcription_benchmark_rules.py — Fase 25 do "PROMPT
MESTRE — SALE-IA V2" (Critério para iniciar o Digital Sales Twin),
item 4/5 ("benchmark de transcrição").

Módulo puro (sem IA, sem banco) — mesmo padrão de
tests/test_win_loss_rules.py / tests/test_observability_metrics_rules.py.

Run:
    python -m unittest tests.test_transcription_benchmark_rules -v
"""

import unittest

from agent.transcription_benchmark_rules import (
    TRANSCRIPTION_BENCHMARK_SEM_DATASET_REAL,
    TRANSCRIPTION_PROVIDERS,
    WER_ALVO_PADRAO,
    avaliar_meta_confiabilidade,
    calcular_wer,
    comparar_provedores,
    montar_resultado_transcricao,
)


class CalcularWerTest(unittest.TestCase):
    def test_transcricao_identica_wer_zero(self):
        resultado = calcular_wer("the quick brown fox", "the quick brown fox")
        self.assertEqual(resultado["wer"], 0.0)
        self.assertEqual(resultado["substitutions"], 0)
        self.assertEqual(resultado["deletions"], 0)
        self.assertEqual(resultado["insertions"], 0)
        self.assertEqual(resultado["referencia_palavras"], 4)

    def test_case_insensitive(self):
        resultado = calcular_wer("The Quick Brown Fox", "the quick brown fox")
        self.assertEqual(resultado["wer"], 0.0)

    def test_uma_delecao(self):
        resultado = calcular_wer("the quick brown fox", "the quick fox")
        self.assertEqual(resultado["deletions"], 1)
        self.assertEqual(resultado["substitutions"], 0)
        self.assertEqual(resultado["insertions"], 0)
        self.assertAlmostEqual(resultado["wer"], 0.25)  # 1/4

    def test_uma_insercao(self):
        resultado = calcular_wer("the quick brown fox", "the quick brown fox jumps")
        self.assertEqual(resultado["insertions"], 1)
        self.assertEqual(resultado["deletions"], 0)
        self.assertEqual(resultado["substitutions"], 0)
        self.assertAlmostEqual(resultado["wer"], 0.25)  # 1/4

    def test_uma_substituicao(self):
        resultado = calcular_wer("the quick brown fox", "the fast brown fox")
        self.assertEqual(resultado["substitutions"], 1)
        self.assertEqual(resultado["deletions"], 0)
        self.assertEqual(resultado["insertions"], 0)
        self.assertAlmostEqual(resultado["wer"], 0.25)  # 1/4

    def test_referencia_vazia_wer_none(self):
        resultado = calcular_wer("", "algo transcrito")
        self.assertIsNone(resultado["wer"])
        self.assertEqual(resultado["referencia_palavras"], 0)
        self.assertEqual(resultado["insertions"], 2)

    def test_hipotese_vazia_todas_delecoes(self):
        resultado = calcular_wer("preciso saber o preco", "")
        self.assertEqual(resultado["deletions"], 4)
        self.assertEqual(resultado["wer"], 1.0)


class AvaliarMetaConfiabilidadeTest(unittest.TestCase):
    def test_wer_none_retorna_none(self):
        self.assertIsNone(avaliar_meta_confiabilidade(None))

    def test_wer_dentro_do_alvo(self):
        self.assertTrue(avaliar_meta_confiabilidade(0.05))

    def test_wer_igual_ao_alvo_atinge(self):
        self.assertTrue(avaliar_meta_confiabilidade(WER_ALVO_PADRAO))

    def test_wer_acima_do_alvo_nao_atinge(self):
        self.assertFalse(avaliar_meta_confiabilidade(0.35))

    def test_alvo_sobrescrevivel(self):
        self.assertFalse(avaliar_meta_confiabilidade(0.15, alvo=0.05))


class MontarResultadoTranscricaoTest(unittest.TestCase):
    def test_combina_wer_latencia_custo(self):
        resultado = montar_resultado_transcricao(
            "groq", "eu quero saber o preco", "eu quero saber o preco",
            latencia_ms=850.0, custo_usd=0.0004,
        )
        self.assertEqual(resultado["provider"], "groq")
        self.assertEqual(resultado["wer"], 0.0)
        self.assertEqual(resultado["latencia_ms"], 850.0)
        self.assertEqual(resultado["custo_usd"], 0.0004)

    def test_provider_livre_nao_travado_ao_vocabulario(self):
        resultado = montar_resultado_transcricao("qualquer_provider_novo", "a", "a")
        self.assertEqual(resultado["provider"], "qualquer_provider_novo")


class CompararProvedoresTest(unittest.TestCase):
    def test_agrupa_por_provider_e_calcula_wer_medio(self):
        resultados = [
            montar_resultado_transcricao("whisper", "a b c d", "a b c d", latencia_ms=100),
            montar_resultado_transcricao("whisper", "a b c d", "a b x d", latencia_ms=120),
            montar_resultado_transcricao("groq", "a b c d", "a x c d", latencia_ms=50),
        ]
        resumo = comparar_provedores(resultados)
        self.assertEqual(set(resumo.keys()), {"whisper", "groq"})
        self.assertEqual(resumo["whisper"]["n"], 2)
        self.assertAlmostEqual(resumo["whisper"]["wer_medio"], (0.0 + 0.25) / 2)
        self.assertEqual(resumo["groq"]["n"], 1)
        self.assertAlmostEqual(resumo["groq"]["wer_medio"], 0.25)

    def test_reaproveita_estatisticas_latencia_existentes(self):
        resultados = [
            montar_resultado_transcricao("whisper", "a", "a", latencia_ms=100),
            montar_resultado_transcricao("whisper", "a", "a", latencia_ms=200),
        ]
        resumo = comparar_provedores(resultados)
        self.assertEqual(resumo["whisper"]["latencia"]["amostra"], 2)
        self.assertEqual(resumo["whisper"]["latencia"]["media_ms"], 150.0)

    def test_custo_medio_ignora_none(self):
        resultados = [
            montar_resultado_transcricao("whisper", "a", "a", custo_usd=0.001),
            montar_resultado_transcricao("whisper", "a", "a", custo_usd=None),
        ]
        resumo = comparar_provedores(resultados)
        self.assertEqual(resumo["whisper"]["custo_medio_usd"], 0.001)

    def test_provider_sem_referencia_valida_wer_medio_none(self):
        resultados = [montar_resultado_transcricao("whisper", "", "algo")]
        resumo = comparar_provedores(resultados)
        self.assertIsNone(resumo["whisper"]["wer_medio"])
        self.assertIsNone(resumo["whisper"]["atinge_meta"])

    def test_lista_vazia_retorna_dict_vazio(self):
        self.assertEqual(comparar_provedores([]), {})

    def test_outliers_nunca_distorcem_wer_medio_silenciosamente(self):
        # 5 resultados quase perfeitos + 1 catastrófico (outlier real).
        resultados = [
            montar_resultado_transcricao("whisper", "a b c d e f g h", "a b c d e f g h")
            for _ in range(5)
        ] + [montar_resultado_transcricao("whisper", "a b c d e f g h", "")]
        resumo = comparar_provedores(resultados)
        self.assertEqual(resumo["whisper"]["n"], 6)
        self.assertGreaterEqual(resumo["whisper"]["wer_n_outliers"], 1)


class VocabularioEGapTest(unittest.TestCase):
    def test_providers_documentados(self):
        self.assertEqual(TRANSCRIPTION_PROVIDERS, frozenset({"whisper", "groq", "whisper_local"}))

    def test_gap_sem_dataset_real_documentado(self):
        self.assertFalse(TRANSCRIPTION_BENCHMARK_SEM_DATASET_REAL["disponivel"])
        self.assertIn("motivo", TRANSCRIPTION_BENCHMARK_SEM_DATASET_REAL)


if __name__ == "__main__":
    unittest.main()
