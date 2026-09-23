"""
Testes — scripts/transcription_benchmark_run.py (Fase 25, "o que
falta pra ligar", item 4/5). Só a parte pura (carregar_gabarito, sem
IA) — a execução real (_real_run) chama as 3 funções de transcrição
reais de api/main.py, testada manualmente via `--real` (custo real),
mesma disciplina de scripts/quality_monitoring_golden_run.py.

Run:
    python -m unittest tests.test_transcription_benchmark_run -v
"""

import unittest

from scripts.transcription_benchmark_run import PROVIDERS, carregar_gabarito


class CarregarGabaritoTest(unittest.TestCase):
    def test_carrega_as_8_falas_reais(self):
        itens = carregar_gabarito()
        self.assertEqual(len(itens), 8)

    def test_cada_item_tem_id_texto_audio(self):
        for item in carregar_gabarito():
            self.assertTrue(item.get("id"))
            self.assertTrue(item.get("texto"))
            self.assertTrue(item.get("audio"))
            self.assertTrue(item.get("_audio_path"))

    def test_ids_sao_unicos(self):
        itens = carregar_gabarito()
        ids = [item["id"] for item in itens]
        self.assertEqual(len(ids), len(set(ids)))


class ProvidersTest(unittest.TestCase):
    def test_3_provedores_reais_do_projeto(self):
        self.assertEqual(PROVIDERS, ("whisper", "groq", "whisper_local"))


if __name__ == "__main__":
    unittest.main()
