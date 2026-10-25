"""
Testes — D7 (teste de carga): IA falsa e gerador (scripts/loadtest/).

Run:
    python -m unittest tests.test_loadtest -v
"""
import json
import random
import statistics
import unittest

from scripts.loadtest import fake_ai, gerar_carga


class FakeAiTest(unittest.TestCase):
    def test_atraso_segue_a_distribuicao_de_producao(self):
        random.seed(7)
        amostra = sorted(fake_ai.sortear_atraso_s() for _ in range(20000))
        self.assertAlmostEqual(statistics.median(amostra), 2.109, delta=0.15)
        self.assertAlmostEqual(amostra[int(len(amostra) * 0.9)], 5.649, delta=0.3)
        self.assertTrue(all(0.4 <= a <= 12 for a in amostra))

    def test_resposta_e_json_valido_para_o_roteador(self):
        from api.ai_router import _extract_json
        dados = _extract_json(json.dumps(fake_ai.RESPOSTA, ensure_ascii=False))
        for chave in ("current_state", "recommended_framework", "next_best_action", "reason", "confidence"):
            self.assertIn(chave, dados)


class GeradorTest(unittest.TestCase):
    def test_payload_como_a_extensao_e_falas_distintas(self):
        r = gerar_carga.Reuniao(1, 10)
        p1, p2 = r.payload(), r.payload()
        self.assertTrue(r.id.startswith("lt010-001-"))
        novas2 = p2["transcricao_nova"].splitlines()
        self.assertTrue(novas2 and not set(novas2) & set(p1["transcricao_nova"].splitlines()))
        self.assertEqual(len(p2["turnos_novos"]), len(novas2))
        todas = p2["transcricao_parcial"].splitlines()
        self.assertEqual(len(todas), len(set(todas)))  # a deduplicação não pode descartar nada

    def test_resumo_conta_status_e_timeouts(self):
        res = [{"s": 1.0, "status": 200}, {"s": 3.0, "status": 200}, {"s": 60.0, "status": "timeout"},
               {"s": 0.5, "status": 503}]
        amostras = [{"cpu": 50.0, "mem_mb": 2000, "rss_mb": 600, "mysql": {"Questions": 100}, "ia": {"max_em_andamento": 4}},
                    {"cpu": 70.0, "mem_mb": 2100, "rss_mb": 650, "mysql": {"Questions": 700}, "ia": {"max_em_andamento": 9}}]
        r = gerar_carga.resumir(10, res, amostras, {"total": 0}, {"total": 30, "tokens_entrada": 6000}, 60)
        self.assertEqual(r["timeouts"], 1)
        self.assertEqual(r["por_status"], {"200": 2, "timeout": 1, "503": 1})
        self.assertEqual(r["taxa_sucesso"], 0.5)
        self.assertEqual(r["ia"]["fila_max"], 9)
        self.assertEqual(r["ia"]["chamadas_por_min"], 30.0)
        self.assertEqual(r["mysql"]["consultas_por_s"], 10.0)


if __name__ == "__main__":
    unittest.main()
