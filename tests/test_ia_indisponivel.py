"""
Alerta de IA fora do ar (V.1.4.168): regras puras em
agent/ia_indisponivel_rules.py + ligação em api/ai_router.py.

Motivo: de 06/10 a 08/10/2026 os 4 provedores ficaram sem saldo/chave e
o /health seguiu "online"; nenhum alerta dizia que TODA a IA tinha caído.

Run:
    python -m unittest tests.test_ia_indisponivel -v
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from agent import alertas
from agent.ia_indisponivel_rules import (
    CAUSA_CHAVE_INVALIDA,
    CAUSA_LIMITE_DE_USO,
    CAUSA_OUTRA,
    CAUSA_SEM_CHAVE,
    CAUSA_SEM_SALDO,
    classificar_causa,
    montar_alerta_ia_fora,
    resumir_estado,
)
from api import ai_router

# Mensagens reais do journal de 06-08/10/2026 (cortadas).
ERRO_DEEPSEEK = "APIStatusError: Error code: 402 - {'error': {'message': 'Insufficient Balance'"
ERRO_OPENAI = ("RateLimitError: Error code: 429 - {'error': {'message': 'You have no credits remaining.', "
               "'type': 'insufficient_quota'")
ERRO_ANTHROPIC = ("BadRequestError: Error code: 400 - {'type': 'error', 'error': {'message': "
                  "'Your credit balance is too low to access the Anthropic API.'")
ERRO_GEMINI = "ClientError: 400 INVALID_ARGUMENT. {'error': {'message': 'API key not valid. Please pass a valid API key.'"


class ClassificarCausaTest(unittest.TestCase):
    def test_erros_reais_de_outubro(self):
        self.assertEqual(classificar_causa(ERRO_DEEPSEEK), CAUSA_SEM_SALDO)
        self.assertEqual(classificar_causa(ERRO_OPENAI), CAUSA_SEM_SALDO)  # 429 de quota é saldo, não limite
        self.assertEqual(classificar_causa(ERRO_ANTHROPIC), CAUSA_SEM_SALDO)
        self.assertEqual(classificar_causa(ERRO_GEMINI), CAUSA_CHAVE_INVALIDA)

    def test_limite_de_uso_e_outros(self):
        self.assertEqual(classificar_causa("RateLimitError: Error code: 429 - rate limit reached"), CAUSA_LIMITE_DE_USO)
        self.assertEqual(classificar_causa("TimeoutError: read timed out"), CAUSA_OUTRA)
        self.assertEqual(classificar_causa(None), CAUSA_OUTRA)


class ResumirEstadoTest(unittest.TestCase):
    def test_disponivel_se_um_provedor_esta_abaixo_do_limite(self):
        r = resumir_estado({
            "deepseek": {"configurado": True, "falhas": 335, "ultimo_erro": ERRO_DEEPSEEK},
            "openai": {"configurado": True, "falhas": 1, "ultimo_erro": ERRO_OPENAI},
        }, 3)
        self.assertTrue(r["ia_disponivel"])
        self.assertEqual(r["causas"], {})

    def test_indisponivel_com_causa_por_provedor(self):
        r = resumir_estado({
            "deepseek": {"configurado": True, "falhas": 335, "ultimo_erro": ERRO_DEEPSEEK},
            "gemini": {"configurado": True, "falhas": 208, "ultimo_erro": ERRO_GEMINI},
            "anthropic": {"configurado": False, "falhas": 0, "ultimo_erro": ""},
        }, 3)
        self.assertFalse(r["ia_disponivel"])
        self.assertEqual(r["causas"], {
            "deepseek": CAUSA_SEM_SALDO, "gemini": CAUSA_CHAVE_INVALIDA, "anthropic": CAUSA_SEM_CHAVE,
        })

    def test_nada_configurado_e_indisponivel(self):
        self.assertFalse(resumir_estado({}, 3)["ia_disponivel"])

    def test_mensagem_diz_o_que_fazer(self):
        msg = montar_alerta_ia_fora({"deepseek": CAUSA_SEM_SALDO, "gemini": CAUSA_CHAVE_INVALIDA}, 12)
        self.assertIn("IA FORA DO AR", msg)
        self.assertIn("há 12 min", msg)
        self.assertIn("recarregar saldo", msg)
        self.assertIn("chave nova", msg)


class RouterAlertaIaForaTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        ai_router.STATE_FILE = Path(self._tmpdir.name) / "ai_provider_order.json"
        ai_router.resetar_estado_ia_para_testes()
        alertas._last_alerta.clear()
        self.addCleanup(alertas._last_alerta.clear)
        self.addCleanup(ai_router.resetar_estado_ia_para_testes)
        self.falhar = True

        def caller(*args):
            if self.falhar:
                raise RuntimeError(ERRO_DEEPSEEK)
            return {"ok": True}, None

        self.providers = {"deepseek": ai_router.Provider(
            name="deepseek", env_keys=("DEEPSEEK_API_KEY",), model_env="DEEPSEEK_MODEL",
            default_model="deepseek-chat", caller=caller,
        )}
        for p in (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test", "AI_PROVIDER_ORDER": "deepseek"}, clear=False),
            patch.object(ai_router, "PROVIDERS", self.providers),
            patch.object(ai_router, "_registrar_evento_uso_ia_melhor_esforco"),
        ):
            p.start()
            self.addCleanup(p.stop)
        self.alertar = patch("agent.alertas.alertar").start()
        self.addCleanup(patch.stopall)

    def _chamar(self):
        # conteúdo diferente a cada chamada: o cache de respostas (Fase 5)
        # devolveria o sucesso anterior sem chegar ao provedor
        self._n = getattr(self, "_n", 0) + 1
        try:
            return ai_router.chamar_ia("system", f"user {self._n}")
        except HTTPException as e:
            return e

    def _mensagens(self):
        return [c.args[0] for c in self.alertar.call_args_list]

    def _liberar_breaker(self):
        ai_router._breakers["deepseek"].opened_at = 0.0  # simula o fim do cooldown de 60s

    def test_falha_isolada_nao_alerta_ia_fora(self):
        self.assertIsInstance(self._chamar(), HTTPException)
        self.assertFalse(any("IA FORA DO AR" in m for m in self._mensagens()))
        self.assertTrue(ai_router.estado_geral_ia()["ia_disponivel"])

    def test_breaker_aberto_em_todos_alerta_com_a_causa(self):
        for _ in range(ai_router.FAILURES_TO_OPEN):
            self._liberar_breaker()
            self._chamar()
        fora = [m for m in self._mensagens() if "IA FORA DO AR" in m]
        self.assertEqual(len(fora), 1)
        self.assertIn("sem saldo", fora[0])
        estado = ai_router.estado_geral_ia()
        self.assertFalse(estado["ia_disponivel"])
        self.assertEqual(estado["causas"], {"deepseek": CAUSA_SEM_SALDO})
        self.assertIsNotNone(estado["ia_fora_desde"])

    def test_alerta_de_ia_fora_no_maximo_1_por_hora(self):
        for _ in range(ai_router.FAILURES_TO_OPEN + 5):
            self._liberar_breaker()
            self._chamar()
        self.assertEqual(sum("IA FORA DO AR" in m for m in self._mensagens()), 1)

    def test_volta_avisa_e_rearma_o_alerta(self):
        for _ in range(ai_router.FAILURES_TO_OPEN):
            self._liberar_breaker()
            self._chamar()
        self.falhar = False
        self._liberar_breaker()
        self.assertTrue(self._chamar()["ok"])
        self.assertTrue(any("IA voltou via *deepseek*" in m for m in self._mensagens()))
        estado = ai_router.estado_geral_ia()
        self.assertTrue(estado["ia_disponivel"])
        self.assertIsNone(estado["ia_fora_desde"])

        # nova queda avisa de novo na hora, sem esperar 1h
        self.falhar = True
        for _ in range(ai_router.FAILURES_TO_OPEN):
            self._liberar_breaker()
            self._chamar()
        self.assertEqual(sum("IA FORA DO AR" in m for m in self._mensagens()), 2)

    def test_sucesso_sem_queda_antes_nao_avisa(self):
        self.falhar = False
        self._chamar()
        self.assertFalse(any("IA voltou" in m for m in self._mensagens()))

    def test_erro_no_alerta_nunca_muda_o_503(self):
        self.alertar.side_effect = RuntimeError("telegram fora")
        for _ in range(ai_router.FAILURES_TO_OPEN):
            self._liberar_breaker()
            r = self._chamar()
        self.assertIsInstance(r, HTTPException)
        self.assertEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main()
