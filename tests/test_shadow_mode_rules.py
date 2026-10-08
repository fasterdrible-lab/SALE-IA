"""
Testes de agent/shadow_mode_rules.py — Fase 23 do "PROMPT MESTRE —
SALE-IA V2" (Teste em Shadow Mode).

Módulo puro (sem IA, sem banco) — mesmo padrão de
tests/test_opportunity_intelligence_rules.py.

Run:
    python -m unittest tests.test_shadow_mode_rules -v
"""

import unittest

from agent.shadow_mode_rules import (
    MENSAGEM_FALLBACK_ATUAL,
    PILOTO_MIN_COMPARAVEIS,
    QUALITY_NAO_DISPONIVEL,
    avaliar_concordancia_estrutural,
    avaliar_shadow_mode,
    montar_registro_shadow,
    resumir_comparacoes,
)


class AvaliarConcordanciaEstruturalTest(unittest.TestCase):
    def test_ambos_recomendam_pergunta_concorda(self):
        atual = {"type": "question"}
        nova = {"next_best_question": "Quanto isso custa hoje?"}
        r = avaliar_concordancia_estrutural(atual, nova)
        self.assertTrue(r["concordancia"])
        self.assertTrue(r["atual_e_pergunta"])
        self.assertTrue(r["novo_e_pergunta"])

    def test_ambos_nao_recomendam_pergunta_concorda(self):
        atual = {"type": "warning"}
        nova = {"next_best_question": None}
        r = avaliar_concordancia_estrutural(atual, nova)
        self.assertTrue(r["concordancia"])
        self.assertFalse(r["atual_e_pergunta"])
        self.assertFalse(r["novo_e_pergunta"])

    def test_um_recomenda_pergunta_outro_nao_discorda(self):
        atual = {"type": "insight"}
        nova = {"next_best_question": "Qual o orçamento disponível?"}
        r = avaliar_concordancia_estrutural(atual, nova)
        self.assertFalse(r["concordancia"])

    def test_next_best_question_string_vazia_conta_como_sem_pergunta(self):
        atual = {"type": "question"}
        nova = {"next_best_question": "   "}
        r = avaliar_concordancia_estrutural(atual, nova)
        self.assertFalse(r["novo_e_pergunta"])
        self.assertFalse(r["concordancia"])

    def test_recomendacao_nova_none_nunca_vira_discordancia(self):
        r = avaliar_concordancia_estrutural({"type": "question"}, None)
        self.assertIsNone(r["concordancia"])
        self.assertIsNone(r["atual_e_pergunta"])
        self.assertIsNone(r["novo_e_pergunta"])

    def test_recomendacao_atual_none_nunca_quebra(self):
        r = avaliar_concordancia_estrutural(None, {"next_best_question": None})
        self.assertFalse(r["atual_e_pergunta"])


class MontarRegistroShadowTest(unittest.TestCase):
    def test_estrutura_completa(self):
        r = montar_registro_shadow(
            {"type": "question"}, {"next_best_question": "X?"}, 850, 0.0021, None,
        )
        chaves_esperadas = {
            "recomendacao_atual", "recomendacao_nova", "concordancia",
            "atual_e_pergunta", "novo_e_pergunta", "latency_ms", "cost_usd",
            "erro", "quality",
        }
        self.assertEqual(set(r.keys()), chaves_esperadas)

    def test_quality_e_sempre_gap_explicito(self):
        r = montar_registro_shadow({}, {"next_best_question": None}, 100, 0.001, None)
        self.assertEqual(r["quality"], QUALITY_NAO_DISPONIVEL)
        self.assertFalse(r["quality"]["disponivel"])

    def test_erro_preenchido_recomendacao_nova_none(self):
        r = montar_registro_shadow({"type": "question"}, None, None, None, "ValueError: JSON inválido")
        self.assertIsNone(r["recomendacao_nova"])
        self.assertIsNone(r["concordancia"])
        self.assertEqual(r["erro"], "ValueError: JSON inválido")

    def test_gaps_sao_copias_nunca_a_mesma_referencia_mutavel(self):
        r1 = montar_registro_shadow({}, {"next_best_question": None}, 1, 1, None)
        r1["quality"]["motivo"] = "mutado"
        r2 = montar_registro_shadow({}, {"next_best_question": None}, 1, 1, None)
        self.assertNotEqual(r2["quality"]["motivo"], "mutado")


class ResumirComparacoesTest(unittest.TestCase):
    def _comparacao(self, **overrides):
        base = {"concordancia": True, "latency_ms": 800, "cost_usd": 0.002, "erro": None}
        base.update(overrides)
        return base

    def test_lista_vazia_nunca_quebra(self):
        r = resumir_comparacoes([])
        self.assertEqual(r["total_comparacoes"], 0)
        self.assertIsNone(r["agreement_rate"])
        self.assertIsNone(r["error_rate"])
        self.assertEqual(r["cost_usd_total"], 0.0)

    def test_agreement_rate_so_conta_comparaveis(self):
        comparacoes = [
            self._comparacao(concordancia=True),
            self._comparacao(concordancia=True),
            self._comparacao(concordancia=False),
            self._comparacao(concordancia=None, erro="TimeoutError"),  # erro, nunca entra no denominador
        ]
        r = resumir_comparacoes(comparacoes)
        self.assertEqual(r["total_comparacoes"], 4)
        self.assertEqual(r["comparaveis"], 3)
        self.assertAlmostEqual(r["agreement_rate"], 2 / 3)
        self.assertAlmostEqual(r["disagreement_rate"], 1 / 3)

    def test_error_rate_conta_sobre_o_total(self):
        comparacoes = [
            self._comparacao(),
            self._comparacao(concordancia=None, erro="ValueError"),
        ]
        r = resumir_comparacoes(comparacoes)
        self.assertAlmostEqual(r["error_rate"], 0.5)

    def test_latencia_e_custo_ignoram_none(self):
        comparacoes = [
            self._comparacao(latency_ms=1000, cost_usd=0.01),
            self._comparacao(latency_ms=None, cost_usd=None, concordancia=None, erro="X"),
        ]
        r = resumir_comparacoes(comparacoes)
        self.assertEqual(r["latency_ms_media"], 1000)
        self.assertEqual(r["cost_usd_total"], 0.01)

    def test_quality_sempre_gap_no_resumo(self):
        r = resumir_comparacoes([self._comparacao()])
        self.assertFalse(r["quality"]["disponivel"])


class AvaliarShadowModeTest(unittest.TestCase):
    """Tarefa C3 — relatório completo para decidir o Piloto (C6)."""

    _id = 0

    def _c(self, **overrides):
        AvaliarShadowModeTest._id += 1
        base = {
            "id": AvaliarShadowModeTest._id,
            "criado_em": "2026-10-05T14:00:00",
            "meeting_id": "m1",
            "usuario_id": None,
            "origem": "shadow",
            "recomendacao_atual": {"type": "question", "category": "spin", "message": "Quanto custa hoje?"},
            "recomendacao_nova": {"next_best_question": "Qual o impacto?", "recommended_framework": "SPIN"},
            "concordancia": True,
            "atual_e_pergunta": True,
            "novo_e_pergunta": True,
            "latency_ms": 5000,
            "cost_usd": 0.001,
            "erro": None,
        }
        base.update(overrides)
        return base

    def test_lista_vazia_nunca_quebra_e_piloto_nao_libera(self):
        r = avaliar_shadow_mode([])
        self.assertEqual(r["por_origem"], {})
        self.assertFalse(r["prontidao_piloto"]["pode_iniciar"])
        self.assertEqual(r["custo"]["caminho_shadow_usd"], 0.0)

    def test_shadow_e_piloto_nunca_se_misturam(self):
        r = avaliar_shadow_mode([self._c(), self._c(origem="piloto", concordancia=False)])
        self.assertEqual(r["por_origem"]["shadow"]["agreement_rate"], 1.0)
        self.assertEqual(r["por_origem"]["piloto"]["agreement_rate"], 0.0)

    def test_fallback_do_modelo_atual_sai_do_agreement_sem_fallback(self):
        fallback = {"type": "question", "message": MENSAGEM_FALLBACK_ATUAL}
        r = avaliar_shadow_mode([
            self._c(recomendacao_atual=fallback),
            self._c(concordancia=False, novo_e_pergunta=False),
        ])
        shadow = r["por_origem"]["shadow"]
        self.assertEqual(shadow["atual_em_fallback"], 1)
        self.assertAlmostEqual(shadow["agreement_rate"], 0.5)
        self.assertEqual(shadow["agreement_rate_sem_fallback"], 0.0)

    def test_matriz_pergunta(self):
        r = avaliar_shadow_mode([
            self._c(),
            self._c(concordancia=False, novo_e_pergunta=False),
            self._c(concordancia=False, atual_e_pergunta=False),
            self._c(atual_e_pergunta=False, novo_e_pergunta=False),
        ])
        self.assertEqual(r["por_origem"]["shadow"]["matriz_pergunta"], {
            "ambos_pergunta": 1, "so_atual_pergunta": 1, "so_novo_pergunta": 1, "nenhum_pergunta": 1,
        })

    def test_erros_agrupados_por_tipo(self):
        r = avaliar_shadow_mode([
            self._c(concordancia=None, recomendacao_nova=None, erro="TimeoutError: 30s"),
            self._c(concordancia=None, recomendacao_nova=None, erro="TimeoutError: 31s"),
            self._c(concordancia=None, recomendacao_nova=None, erro="ValueError: JSON"),
        ])
        self.assertEqual(r["por_origem"]["shadow"]["erros_por_tipo"], {"TimeoutError": 2, "ValueError": 1})

    def test_percentis_de_latencia(self):
        r = avaliar_shadow_mode([self._c(latency_ms=v) for v in (1000, 2000, 3000, 4000, 100000)])
        shadow = r["por_origem"]["shadow"]
        self.assertEqual(shadow["latency_ms_p50"], 3000)
        self.assertEqual(shadow["latency_ms_p95"], 100000)

    def test_recortes_por_reuniao_e_por_dia(self):
        r = avaliar_shadow_mode([
            self._c(meeting_id="a", criado_em="2026-10-05T10:00:00"),
            self._c(meeting_id="a", criado_em="2026-10-05T10:01:00", usuario_id="u1"),
            self._c(meeting_id="b", criado_em="2026-10-06T09:00:00"),
        ])
        shadow = r["por_origem"]["shadow"]
        self.assertEqual(shadow["reunioes"], 2)
        self.assertEqual([(l["chave"], l["total"]) for l in shadow["por_reuniao"]], [("a", 2), ("b", 1)])
        self.assertEqual(shadow["por_reuniao"][0]["com_vendedor"], 1)
        self.assertEqual([l["chave"] for l in shadow["por_dia"]], ["2026-10-05", "2026-10-06"])

    def test_custo_soma_todas_as_chamadas_do_caminho_shadow(self):
        custos = [
            {"feature": "sales_reasoning.raciocinio", "eventos": 10, "total_usd": 0.02},
            {"feature": "spin.extracao_fatos", "eventos": 10, "total_usd": 0.01},
            {"feature": "realtime.coach", "eventos": 30, "total_usd": 0.06},
            {"feature": "report.recapitulacao", "eventos": 1, "total_usd": 0.5},
        ]
        custo = avaliar_shadow_mode([self._c()], custos)["custo"]
        self.assertAlmostEqual(custo["caminho_shadow_usd"], 0.03)
        self.assertEqual(custo["caminho_shadow_chamadas"], 20)
        self.assertAlmostEqual(custo["tempo_real_usd"], 0.06)
        self.assertAlmostEqual(custo["shadow_sobre_tempo_real"], 0.5)

    def test_quality_sem_medicao_sempre_bloqueia_o_piloto(self):
        comparacoes = [
            self._c(meeting_id=f"m{i % 10}", latency_ms=1000) for i in range(PILOTO_MIN_COMPARAVEIS + 10)
        ]
        prontidao = avaliar_shadow_mode(comparacoes)["prontidao_piloto"]
        outras = [c for c in prontidao["checagens"] if "quality" not in c["criterio"]]
        self.assertTrue(all(c["ok"] for c in outras))
        self.assertFalse(prontidao["pode_iniciar"])

    def test_mensagem_de_fallback_igual_a_do_orquestrador(self):
        from agent.multiagente.orquestrador import _FALLBACK_NBA
        self.assertEqual(MENSAGEM_FALLBACK_ATUAL, _FALLBACK_NBA["message"])

    def test_amostras_limitadas_e_sem_fallback(self):
        comparacoes = [self._c(concordancia=False) for _ in range(15)]
        comparacoes.append(self._c(concordancia=False, recomendacao_atual={"message": MENSAGEM_FALLBACK_ATUAL}))
        amostras = avaliar_shadow_mode(comparacoes)["por_origem"]["shadow"]["amostras_discordancia"]
        self.assertEqual(len(amostras), 10)
        self.assertTrue(all(a["atual"]["message"] != MENSAGEM_FALLBACK_ATUAL for a in amostras))


if __name__ == "__main__":
    unittest.main()
