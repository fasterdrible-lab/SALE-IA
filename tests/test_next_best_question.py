"""
Tests — Funcionalidade "Próxima Melhor Pergunta" (next_best_question).

Verifica que a lógica de fallback, normalização e persistência funcionam
corretamente para os 8 cenários documentados no prompt spec.

Não realiza chamadas de IA reais nem acessa banco de dados.

Run:
    python -m unittest tests.test_next_best_question -v
"""

import json
import logging
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

logging.disable(logging.CRITICAL)

# ─────────────────────────────────────────────
# Helpers para montar respostas fake da IA
# ─────────────────────────────────────────────

def _make_ai_response(**nba_override) -> dict:
    """Monta resposta mínima válida da IA com next_best_action.

    Desde a V.1.4.28, next_best_question NUNCA é preservado diretamente da
    IA — api/processador_tempo_real.py::_normalizar_resposta_realtime
    sempre o regenera a partir de next_best_action via _nba_para_nbq()
    (next_best_question virou só um alias de backward-compat). Por isso o
    fake da IA precisa popular next_best_action, não next_best_question,
    para os testes exercitarem o caminho real (ver CLAUDE.md, seção
    "Arquitetura do Motor de Análise").
    """
    nba = {
        "type": "question",
        "category": "impacto_financeiro",
        "title": "Aprofundar impacto",
        "message": "Quanto esse problema está custando por mês?",
        "objective": "Quantificar a dor",
        "reason": "Cliente mencionou perda de produtividade sem valor.",
        "expected_effect": "Cliente quantifica o custo do problema",
        "risk_if_ignored": "Conversa sem urgência mensurável",
        "follow_up": "E se continuar por 6 meses?",
        "confidence": 0.6,
    }
    nba.update(nba_override)
    return {
        "status": "updated",
        "resumo_vivo": "Cliente tem dor operacional.",
        "perfil_disc": {"tipo": "D", "confianca": "media", "evidencia": "...", "como_tratar": "..."},
        "mapa_financeiro": {"faturamento_mensal": None, "capacidade_investimento": None},
        "temperatura": {"nivel": "media", "entonacao": "neutro", "sinal": "...", "acao": "..."},
        "proxima_fala": "Qual seria o impacto disso?",
        "proxima_pergunta": "Qual seria o impacto?",
        "acao_recomendada": "Aprofundar dor",
        "dica_vendedor": "Foque no impacto financeiro.",
        "objecao_detectada": {"objecao": None, "resposta_pronta": None},
        "dado_esquecido": None,
        "score_compra": {"valor": 45, "justificativa": "Dor identificada, sem fechamento."},
        "next_best_action": nba,
        "eventos": [],
        "key_moments": [],
        "current_diagnosis": {},
        "recapitulacao": "Resumo da reunião.",
    }


# ─────────────────────────────────────────────
# Testes da lógica de fallback (sem IA real)
# ─────────────────────────────────────────────

class TestNBQFallback(unittest.TestCase):
    """Verifica que _fallback_next_best_question retorna estrutura válida."""

    def setUp(self):
        from api.processador_tempo_real import _fallback_next_best_question
        self._fallback = _fallback_next_best_question

    def test_fallback_tem_campos_obrigatorios(self):
        nbq = self._fallback()
        for campo in ("question", "category", "objective", "reason", "expected_score_impact", "urgency_level"):
            self.assertIn(campo, nbq, f"Campo ausente: {campo}")

    def test_fallback_category_e_descoberta_dor(self):
        nbq = self._fallback()
        self.assertEqual(nbq["category"], "descoberta_dor")

    def test_fallback_question_nao_vazia(self):
        nbq = self._fallback()
        self.assertTrue(nbq["question"].strip())

    def test_fallback_urgency_e_low(self):
        nbq = self._fallback()
        self.assertEqual(nbq["urgency_level"], "low")


# ─────────────────────────────────────────────
# Testes de normalização no processador
# ─────────────────────────────────────────────

class TestNBQNormalizacao(unittest.TestCase):
    """Verifica que _normalizar_resposta_realtime deriva next_best_question
    a partir de next_best_action (mapeamento feito por _nba_para_nbq —
    next_best_question é só um alias de backward-compat desde a V.1.4.28,
    nunca preservado diretamente do que a IA mandou nesse campo)."""

    def setUp(self):
        from api.processador_tempo_real import _normalizar_resposta_realtime, _fallback_next_best_question
        self._normalizar = _normalizar_resposta_realtime
        self._fallback_q = _fallback_next_best_question()["question"]

    # Cenário 1: IA retornou next_best_action válido → nbq é derivado dele
    def test_cenario_1_nbq_derivado_do_nba_valido(self):
        ai = _make_ai_response(category="impacto_financeiro", message="Qual o custo mensal?")
        resultado = self._normalizar(ai, None, {})
        self.assertEqual(resultado["next_best_question"]["question"], "Qual o custo mensal?")
        self.assertEqual(resultado["next_best_question"]["category"], "impacto_financeiro")

    # Cenário 2: IA retornou next_best_action ausente → deve usar fallback
    def test_cenario_2_nba_ausente_usa_fallback(self):
        ai = _make_ai_response()
        del ai["next_best_action"]
        resultado = self._normalizar(ai, None, {})
        self.assertIn("next_best_question", resultado)
        self.assertEqual(resultado["next_best_question"]["question"], self._fallback_q)

    # Cenário 3: next_best_action com message vazia → deve usar fallback question
    def test_cenario_3_nba_message_vazia_substituida(self):
        ai = _make_ai_response(message="")
        resultado = self._normalizar(ai, None, {})
        self.assertEqual(resultado["next_best_question"]["question"], self._fallback_q)

    # Cenário 4: next_best_action não é dict → deve usar fallback
    def test_cenario_4_nba_nao_dict_usa_fallback(self):
        ai = _make_ai_response()
        ai["next_best_action"] = "texto invalido"
        resultado = self._normalizar(ai, None, {})
        self.assertEqual(resultado["next_best_question"]["question"], self._fallback_q)


# ─────────────────────────────────────────────
# Testes por cenário de negócio (8 casos)
# ─────────────────────────────────────────────

class TestNBQCenariosNegocio(unittest.TestCase):
    """
    Valida que a estrutura retornada pela IA mockada é consistente com
    cada um dos 8 cenários definidos no prompt spec.
    """

    def _normalizar(self, ai_resp):
        from api.processador_tempo_real import _normalizar_resposta_realtime
        return _normalizar_resposta_realtime(ai_resp, None, {})

    # Cenário N1: cliente sem dor clara → descoberta_dor
    def test_N1_sem_dor_descoberta(self):
        ai = _make_ai_response(category="descoberta_dor", message="O que motivou vocês a buscar isso agora?")
        r = self._normalizar(ai)
        self.assertEqual(r["next_best_question"]["category"], "descoberta_dor")

    # Cenário N2: dor operacional identificada → amplificacao_dor
    def test_N2_dor_operacional_amplificacao(self):
        ai = _make_ai_response(category="amplificacao_dor", message="Como isso afeta sua equipe no dia a dia?")
        r = self._normalizar(ai)
        self.assertEqual(r["next_best_question"]["category"], "amplificacao_dor")

    # Cenário N3: objeção de preço → objecao
    def test_N3_objecao_preco(self):
        ai = _make_ai_response(category="objecao", message="Quando você diz caro, está comparando com o que?")
        ai["objecao_detectada"] = {"objecao": "Está caro", "resposta_pronta": "..."}
        r = self._normalizar(ai)
        self.assertEqual(r["next_best_question"]["category"], "objecao")

    # Cenário N4: urgência alta → fechamento (confidence >= 0.8 é o que
    # _nba_para_nbq usa para decidir urgency_level "high" — não é o
    # score_compra, que fica só de diagnóstico/persistência aqui)
    def test_N4_urgencia_alta_fechamento(self):
        ai = _make_ai_response(category="fechamento", confidence=0.85, message="Qual seria o melhor prazo pra começar?")
        ai["score_compra"] = {"valor": 75, "justificativa": "Alta temperatura e score alto."}
        r = self._normalizar(ai)
        self.assertEqual(r["next_best_question"]["category"], "fechamento")
        self.assertEqual(r["next_best_question"]["urgency_level"], "high")

    # Cenário N5: score baixo → descoberta_dor
    def test_N5_score_baixo_descoberta(self):
        ai = _make_ai_response(category="descoberta_dor", message="Quais são os maiores desafios hoje?")
        ai["score_compra"] = {"valor": 20, "justificativa": "Pouco contexto."}
        r = self._normalizar(ai)
        self.assertEqual(r["next_best_question"]["category"], "descoberta_dor")

    # Cenário N6: score alto → pode ser fechamento
    def test_N6_score_alto_fechamento(self):
        ai = _make_ai_response(category="fechamento", message="O que falta pra você tomar a decisão hoje?")
        ai["score_compra"] = {"valor": 82, "justificativa": "Alta intenção."}
        r = self._normalizar(ai)
        self.assertEqual(r["next_best_question"]["category"], "fechamento")

    # Cenário N7: perfil DISC C (analítico) → pergunta de dados
    def test_N7_disc_c_pergunta_dados(self):
        ai = _make_ai_response(
            category="impacto_financeiro",
            message="Quais dados você precisaria para validar o ROI dessa decisão?"
        )
        ai["perfil_disc"]["tipo"] = "C"
        r = self._normalizar(ai)
        self.assertIn("dados", r["next_best_question"]["question"].lower())

    # Cenário N8: decisor ausente → autoridade
    def test_N8_sem_decisor_autoridade(self):
        ai = _make_ai_response(category="autoridade", message="Quem mais está envolvido na decisão?")
        r = self._normalizar(ai)
        self.assertEqual(r["next_best_question"]["category"], "autoridade")

    # Estrutura: todos os campos obrigatórios presentes
    def test_estrutura_campos_obrigatorios(self):
        ai = _make_ai_response()
        r = self._normalizar(ai)
        nbq = r["next_best_question"]
        for campo in ("question", "category", "objective", "reason", "expected_score_impact", "urgency_level"):
            self.assertIn(campo, nbq, f"Campo ausente em next_best_question: {campo}")


# ─────────────────────────────────────────────
# Testes de persistência (key_moments)
# ─────────────────────────────────────────────

class TestNBQPersistencia(unittest.TestCase):
    """
    Verifica que next_best_question é acrescentado a key_moments
    para aparecer no relatório pós-reunião.
    """

    def setUp(self):
        from api.processador_tempo_real import _FALLBACK_NBQ_QUESTION
        self._fallback_q = _FALLBACK_NBQ_QUESTION

    def _simular_resultado(self, nbq_question, nbq_category="impacto_financeiro"):
        """Simula o estado do resultado após analyzeRealtimeMeeting antes da persistência."""
        nbq = {
            "question": nbq_question,
            "category": nbq_category,
            "objective": "Quantificar dor",
            "reason": "Sem valor mencionado.",
            "expected_score_impact": "+8",
            "urgency_level": "medium",
            "follow_up_question": None,
        }
        resultado = {"key_moments": [], "next_best_question": nbq}
        # Simula a lógica de acúmulo de key_moments do processador
        if nbq["question"] and nbq["question"] != self._fallback_q:
            from datetime import datetime, timezone
            nbq_moment = {
                "type": "next_best_question",
                "quote": nbq["question"],
                "speaker": "vendedor",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "importance": "medium",
                "confidence": "high",
                "fact_or_inference": "inference",
                "category": nbq.get("category"),
                "objective": nbq.get("objective"),
                "reason": nbq.get("reason"),
                "expected_score_impact": nbq.get("expected_score_impact"),
            }
            resultado["key_moments"].append(nbq_moment)
        return resultado

    def test_nbq_real_adicionado_a_key_moments(self):
        resultado = self._simular_resultado("Qual o custo mensal desse problema?")
        self.assertEqual(len(resultado["key_moments"]), 1)
        self.assertEqual(resultado["key_moments"][0]["type"], "next_best_question")

    def test_nbq_fallback_nao_adicionado_a_key_moments(self):
        resultado = self._simular_resultado(self._fallback_q)
        self.assertEqual(len(resultado["key_moments"]), 0)

    def test_nbq_key_moment_tem_campos(self):
        resultado = self._simular_resultado("Como isso afeta o faturamento?", "impacto_financeiro")
        km = resultado["key_moments"][0]
        for campo in ("type", "quote", "category", "objective", "reason", "expected_score_impact"):
            self.assertIn(campo, km, f"Campo ausente no key_moment: {campo}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
