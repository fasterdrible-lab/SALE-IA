"""
Testes de agent/pilot_rollout_rules.py — Fase 24 do "PROMPT MESTRE —
SALE-IA V2" (Piloto).

Módulo puro (sem IA, sem banco) — mesmo padrão de
tests/test_shadow_mode_rules.py.

Run:
    python -m unittest tests.test_pilot_rollout_rules -v
"""

import unittest

from agent.pilot_rollout_rules import (
    PILOT_MODES,
    deve_usar_modelo_novo,
    mapear_para_next_best_action,
    usuario_no_percentual,
)


class UsuarioNoPercentualTest(unittest.TestCase):
    def test_sem_usuario_id_nunca_entra(self):
        self.assertFalse(usuario_no_percentual(None, 100))
        self.assertFalse(usuario_no_percentual("", 100))

    def test_zero_por_cento_nunca_entra(self):
        for uid in ("seller-1", "seller-2", "seller-3"):
            self.assertFalse(usuario_no_percentual(uid, 0))

    def test_cem_por_cento_sempre_entra(self):
        for uid in ("seller-1", "seller-2", "seller-3", "outro-id-qualquer"):
            self.assertTrue(usuario_no_percentual(uid, 100))

    def test_deterministico_e_estavel_entre_chamadas(self):
        resultados = {usuario_no_percentual("seller-x", 50) for _ in range(20)}
        self.assertEqual(len(resultados), 1)

    def test_subir_percentual_e_sempre_superconjunto(self):
        usuarios = [f"seller-{i}" for i in range(500)]
        em_5 = {u for u in usuarios if usuario_no_percentual(u, 5)}
        em_20 = {u for u in usuarios if usuario_no_percentual(u, 20)}
        em_50 = {u for u in usuarios if usuario_no_percentual(u, 50)}
        em_100 = {u for u in usuarios if usuario_no_percentual(u, 100)}
        self.assertTrue(em_5.issubset(em_20))
        self.assertTrue(em_20.issubset(em_50))
        self.assertTrue(em_50.issubset(em_100))
        self.assertEqual(em_100, set(usuarios))

    def test_distribuicao_aproximada_5_por_cento(self):
        usuarios = [f"seller-{i}" for i in range(2000)]
        em_5 = sum(1 for u in usuarios if usuario_no_percentual(u, 5))
        # tolerancia generosa (hash nao e uniforme perfeito em amostra finita)
        self.assertTrue(50 <= em_5 <= 200, f"esperado ~100 (5% de 2000), obtido {em_5}")


class DeveUsarModeloNovoTest(unittest.TestCase):
    def test_sem_usuario_id_nunca_entra_em_nenhum_modo(self):
        for modo in PILOT_MODES:
            self.assertFalse(deve_usar_modelo_novo(None, modo))

    def test_modo_off_nunca_entra(self):
        self.assertFalse(deve_usar_modelo_novo("seller-1", "off"))

    def test_modo_invalido_nunca_entra(self):
        self.assertFalse(deve_usar_modelo_novo("seller-1", "modo-inventado"))

    def test_modo_pilot_user_so_allowlist(self):
        self.assertTrue(deve_usar_modelo_novo("seller-1", "pilot_user", usuarios_piloto=["seller-1"]))
        self.assertFalse(deve_usar_modelo_novo("seller-2", "pilot_user", usuarios_piloto=["seller-1"]))

    def test_modo_pilot_user_sem_allowlist_nunca_entra(self):
        self.assertFalse(deve_usar_modelo_novo("seller-1", "pilot_user"))

    def test_modo_100pct_qualquer_usuario_entra(self):
        self.assertTrue(deve_usar_modelo_novo("qualquer-id", "100pct"))

    def test_modo_percentual_consistente_com_usuario_no_percentual(self):
        for uid in (f"seller-{i}" for i in range(50)):
            self.assertEqual(
                deve_usar_modelo_novo(uid, "20pct"),
                usuario_no_percentual(uid, 20),
            )


class MapearParaNextBestActionTest(unittest.TestCase):
    def _saida(self, **overrides):
        base = {
            "current_state": "Cliente demonstrou interesse mas não validou orçamento.",
            "hypotheses": [], "evidence": [], "missing_information": [],
            "recommended_framework": "MEDDPICC_QUALIFICATION",
            "next_best_action": "Pergunte sobre o orçamento disponível.",
            "next_best_question": "Qual o orçamento disponível para este projeto?",
            "avoid": [], "reason": "MEDDPICC Metrics ausente.", "confidence": 0.75,
        }
        base.update(overrides)
        return base

    def test_com_next_best_question_vira_type_question(self):
        r = mapear_para_next_best_action(self._saida())
        self.assertEqual(r["type"], "question")
        self.assertEqual(r["message"], "Qual o orçamento disponível para este projeto?")

    def test_sem_next_best_question_vira_type_insight(self):
        r = mapear_para_next_best_action(self._saida(next_best_question=None))
        self.assertEqual(r["type"], "insight")
        self.assertEqual(r["message"], "Pergunte sobre o orçamento disponível.")

    def test_next_best_question_string_vazia_vira_insight(self):
        r = mapear_para_next_best_action(self._saida(next_best_question="   "))
        self.assertEqual(r["type"], "insight")

    def test_category_e_o_recommended_framework_cru_nunca_traduzido(self):
        r = mapear_para_next_best_action(self._saida(recommended_framework="OBJECTION_INVESTIGATION"))
        self.assertEqual(r["category"], "OBJECTION_INVESTIGATION")

    def test_objective_e_current_state(self):
        r = mapear_para_next_best_action(self._saida())
        self.assertEqual(r["objective"], "Cliente demonstrou interesse mas não validou orçamento.")

    def test_reason_e_confidence_repassados(self):
        r = mapear_para_next_best_action(self._saida())
        self.assertEqual(r["reason"], "MEDDPICC Metrics ausente.")
        self.assertEqual(r["confidence"], 0.75)

    def test_avoid_vira_evite_concatenado(self):
        r = mapear_para_next_best_action(self._saida(avoid=["prometer desconto", "garantir prazo"]))
        self.assertEqual(r["evite"], "prometer desconto; garantir prazo")

    def test_avoid_vazio_vira_evite_none(self):
        r = mapear_para_next_best_action(self._saida(avoid=[]))
        self.assertIsNone(r["evite"])

    def test_todas_as_chaves_do_schema_antigo_presentes(self):
        r = mapear_para_next_best_action(self._saida())
        chaves_esperadas = {
            "type", "category", "title", "message", "objective", "reason",
            "expected_effect", "risk_if_ignored", "follow_up", "evite", "confidence",
        }
        self.assertEqual(set(r.keys()), chaves_esperadas)


if __name__ == "__main__":
    unittest.main()
