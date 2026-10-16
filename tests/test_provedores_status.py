"""
Testes — V.1.4.183: painel de provedores de IA + avisos de saldo e reserva.

Run:
    python -m unittest tests.test_provedores_status -v
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent import alertas
from agent.provedores_status_rules import (
    ler_limites_groq,
    ler_saldo_deepseek,
    montar_alerta_reserva,
    montar_alerta_saldo_baixo,
    provedor_em_uso,
    saldo_baixo,
)
from api import ai_router, provedores_status

# Respostas reais (VPS, 16/10/2026).
SALDO_REAL = {"is_available": True, "balance_infos": [
    {"currency": "USD", "total_balance": "5.65", "granted_balance": "5.65", "topped_up_balance": "-0.00"}]}
CABECALHOS_GROQ_REAIS = {
    "x-ratelimit-limit-requests": "1000", "x-ratelimit-limit-tokens": "8000",
    "x-ratelimit-remaining-requests": "999", "x-ratelimit-remaining-tokens": "7923",
    "x-ratelimit-reset-requests": "1m26.4s", "x-ratelimit-reset-tokens": "577ms",
}


class RegrasTest(unittest.TestCase):
    def test_saldo_deepseek_real(self):
        s = ler_saldo_deepseek(SALDO_REAL)
        self.assertEqual(s, {"disponivel": True, "moeda": "USD", "total": 5.65, "credito_concedido": 5.65, "pago": -0.0})
        self.assertFalse(saldo_baixo(s, 2.0))
        self.assertTrue(saldo_baixo({**s, "total": 1.99}, 2.0))
        self.assertTrue(saldo_baixo({**s, "disponivel": False}, 2.0))

    def test_saldo_prefere_usd_e_aceita_resposta_ruim(self):
        r = {"is_available": True, "balance_infos": [
            {"currency": "CNY", "total_balance": "100"}, {"currency": "USD", "total_balance": "3.10"}]}
        self.assertEqual(ler_saldo_deepseek(r)["total"], 3.1)
        self.assertIsNone(ler_saldo_deepseek({}))
        self.assertIsNone(ler_saldo_deepseek(None))
        self.assertFalse(saldo_baixo(None, 2.0))

    def test_limites_groq_reais(self):
        l = ler_limites_groq(CABECALHOS_GROQ_REAIS)
        self.assertEqual((l["pedidos_restantes_dia"], l["pedidos_limite_dia"]), (999, 1000))
        self.assertEqual((l["tokens_restantes_min"], l["tokens_limite_min"]), (7923, 8000))
        self.assertIsNone(ler_limites_groq({"content-type": "application/json"}))

    def test_provedor_em_uso(self):
        ordem = ["deepseek", "openai", "groq"]
        self.assertEqual(provedor_em_uso([("deepseek", "t")], ordem)["reserva"], False)
        self.assertEqual(provedor_em_uso([("groq", "t")], ordem), {"provedor": "groq", "reserva": True, "desde": "t"})
        self.assertIsNone(provedor_em_uso([], ordem)["provedor"])

    def test_mensagens(self):
        m = montar_alerta_saldo_baixo({"total": 1.5, "credito_concedido": 1.5, "pago": 0.0}, 2.0)
        self.assertIn("US$ 1.50", m)
        self.assertIn("Top up", m)
        r = montar_alerta_reserva("groq", {"deepseek": "sem_saldo", "openai": "cooldown"})
        self.assertIn("groq", r)
        self.assertIn("deepseek: sem saldo", r)


class _ComDiretorio(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        p = patch.object(provedores_status, "DIR_DADOS", Path(self._tmp.name))
        p.start()
        self.addCleanup(p.stop)
        self.alertar = patch("agent.alertas.alertar").start()
        self.addCleanup(patch.stopall)
        provedores_status._saldo_cache.update(em=0.0, valor=None, erro=None)


class AvisosTest(_ComDiretorio):
    def test_saldo_baixo_avisa_uma_vez_so(self):
        baixo = {"saldo": {"disponivel": True, "moeda": "USD", "total": 1.2, "credito_concedido": 1.2, "pago": 0.0}}
        with patch.object(provedores_status, "saldo_deepseek", return_value=baixo):
            provedores_status.verificar_saldo_e_avisar()
            provedores_status.verificar_saldo_e_avisar()  # 2º worker / próxima volta
        self.assertEqual(self.alertar.call_count, 1)
        self.assertIn("saldo baixo", self.alertar.call_args.args[0])

    def test_saldo_ok_nao_avisa(self):
        ok = {"saldo": ler_saldo_deepseek(SALDO_REAL)}
        with patch.object(provedores_status, "saldo_deepseek", return_value=ok):
            provedores_status.verificar_saldo_e_avisar()
        self.alertar.assert_not_called()

    def test_limites_groq_gravados_e_lidos(self):
        provedores_status.registrar_limites_groq(CABECALHOS_GROQ_REAIS)
        self.assertEqual(provedores_status.limites_groq()["pedidos_restantes_dia"], 999)

    def test_painel_junta_estado_uso_saldo_e_limites(self):
        provedores_status.registrar_limites_groq(CABECALHOS_GROQ_REAIS)
        uso = {"deepseek": {"ok_1h": 550, "falhas_1h": 0, "custo_1h_usd": 0.31, "ultimo_sucesso": "2026-10-16T13:00:00"}}
        with patch.object(provedores_status, "_uso_recente", return_value=(uso, [("deepseek", "2026-10-16T13:00:00")])), \
             patch.object(provedores_status, "saldo_deepseek", return_value={"saldo": ler_saldo_deepseek(SALDO_REAL), "erro": None}):
            painel = provedores_status.painel_provedores()
        self.assertEqual(painel["em_uso"]["provedor"], "deepseek")
        self.assertFalse(painel["em_uso"]["reserva"])
        por_nome = {p["nome"]: p for p in painel["provedores"]}
        self.assertEqual(por_nome["deepseek"]["ok_1h"], 550)
        self.assertEqual(por_nome["deepseek"]["saldo"]["saldo"]["total"], 5.65)
        if "groq" in por_nome:
            self.assertEqual(por_nome["groq"]["limites"]["pedidos_limite_dia"], 1000)


class RouterReservaTest(_ComDiretorio):
    def setUp(self):
        super().setUp()
        ai_router.STATE_FILE = Path(self._tmp.name) / "ai_provider_order.json"
        ai_router.resetar_estado_ia_para_testes()
        alertas._last_alerta.clear()
        self.addCleanup(alertas._last_alerta.clear)
        self.addCleanup(ai_router.resetar_estado_ia_para_testes)

        def falha(*a):
            raise RuntimeError("Error code: 402 - {'error': {'message': 'Insufficient Balance'}}")

        def ok(*a):
            return {"ok": True}, None

        self.providers = {
            "deepseek": ai_router.Provider(name="deepseek", env_keys=("DEEPSEEK_API_KEY",), model_env="DEEPSEEK_MODEL",
                                           default_model="deepseek-chat", caller=falha),
            "groq": ai_router.Provider(name="groq", env_keys=("GROQ_API_KEY",), model_env="GROQ_LLM_MODEL",
                                       default_model="openai/gpt-oss-120b", caller=ok),
        }
        for p in (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "t", "GROQ_API_KEY": "t", "AI_PROVIDER_ORDER": "deepseek,groq",
                                    "GROQ_LLM_ATIVO": "true"}, clear=False),
            patch.object(ai_router, "PROVIDERS", self.providers),
            patch.object(ai_router, "_registrar_evento_uso_ia_melhor_esforco"),
        ):
            p.start()

    def _mensagens(self):
        return [c.args[0] for c in self.alertar.call_args_list]

    def test_reserva_atendendo_avisa_uma_vez_por_hora(self):
        r1 = ai_router.chamar_ia("system", "user 1")
        r2 = ai_router.chamar_ia("system", "user 2")
        self.assertEqual((r1["_provedor_ia"], r2["_provedor_ia"]), ("groq", "groq"))
        reserva = [m for m in self._mensagens() if "reserva" in m]
        self.assertEqual(len(reserva), 1)
        self.assertIn("deepseek: sem saldo", reserva[0])

    def test_principal_atendendo_nao_avisa(self):
        self.providers["deepseek"] = ai_router.Provider(
            name="deepseek", env_keys=("DEEPSEEK_API_KEY",), model_env="DEEPSEEK_MODEL",
            default_model="deepseek-chat", caller=lambda *a: ({"ok": True}, None))
        self.assertEqual(ai_router.chamar_ia("system", "user 3")["_provedor_ia"], "deepseek")
        self.assertFalse(any("reserva" in m for m in self._mensagens()))


if __name__ == "__main__":
    unittest.main()
