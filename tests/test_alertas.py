"""
Testes de agent/alertas.py::verificar_orcamento (Budget Guard, Cost
Intelligence Fase 3).

Run:
    python -m unittest tests.test_alertas -v
"""

import logging
import os
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from agent import alertas


class VerificarOrcamentoTest(unittest.TestCase):
    def setUp(self):
        # cooldown e por-processo (dict em modulo) — isola entre testes
        alertas._last_alerta.clear()

    def test_sem_limite_configurado_nao_alerta(self):
        with patch.object(alertas, "alertar") as m:
            alertas.verificar_orcamento(gasto_mes_usd=999.0, limite_usd=None)
            alertas.verificar_orcamento(gasto_mes_usd=999.0, limite_usd=0)
            alertas.verificar_orcamento(gasto_mes_usd=999.0, limite_usd=-5)
        m.assert_not_called()

    def test_abaixo_de_80pct_nao_alerta(self):
        with patch.object(alertas, "alertar") as m:
            alertas.verificar_orcamento(gasto_mes_usd=50.0, limite_usd=100.0)
        m.assert_not_called()

    def test_80pct_dispara_aviso(self):
        with patch.object(alertas, "alertar") as m:
            alertas.verificar_orcamento(gasto_mes_usd=80.0, limite_usd=100.0)
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertIn("80%", args[0])
        self.assertEqual(kwargs.get("nivel"), "⚠️")

    def test_100pct_dispara_critico_nao_aviso(self):
        with patch.object(alertas, "alertar") as m:
            alertas.verificar_orcamento(gasto_mes_usd=120.0, limite_usd=100.0)
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertEqual(kwargs.get("nivel"), "🔴")

    def test_cooldown_evita_alerta_repetido(self):
        with patch.object(alertas, "alertar") as m:
            alertas.verificar_orcamento(gasto_mes_usd=80.0, limite_usd=100.0)
            alertas.verificar_orcamento(gasto_mes_usd=85.0, limite_usd=100.0)
        m.assert_called_once()

    def test_100pct_e_80pct_sao_chaves_de_cooldown_independentes(self):
        with patch.object(alertas, "alertar") as m:
            alertas.verificar_orcamento(gasto_mes_usd=80.0, limite_usd=100.0)  # dispara 80%
            alertas.verificar_orcamento(gasto_mes_usd=101.0, limite_usd=100.0)  # dispara 100% (chave diferente)
        self.assertEqual(m.call_count, 2)


class VerificarAnomaliaTest(unittest.TestCase):
    def setUp(self):
        alertas._last_alerta.clear()

    def test_dispara_alerta(self):
        with patch.object(alertas, "alertar") as m:
            alertas.verificar_anomalia("realtime.coach", media_atual=0.30, media_anterior=0.01, multiplicador=30.0)
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertIn("realtime.coach", args[0])
        self.assertEqual(kwargs.get("nivel"), "🟠")

    def test_cooldown_e_por_feature(self):
        with patch.object(alertas, "alertar") as m:
            alertas.verificar_anomalia("realtime.coach", 0.30, 0.01, 30.0)
            alertas.verificar_anomalia("realtime.coach", 0.31, 0.01, 31.0)  # mesma feature — cooldown
            alertas.verificar_anomalia("realtime.disc", 0.30, 0.01, 30.0)  # feature diferente — dispara
        self.assertEqual(m.call_count, 2)


class EscalarParaHumanoTest(unittest.TestCase):
    def setUp(self):
        alertas._last_alerta.clear()

    def test_dispara_alerta_com_urgencia_do_escalonamento(self):
        escalonamento = {
            "acao": "enviar_followup",
            "fronteira": "HUMAN_APPROVAL",
            "motivo": "desconto de 15% acima do limite de 5%",
            "urgencia": "⚠️",
            "contexto": {},
        }
        with patch.object(alertas, "alertar") as m:
            alertas.escalar_para_humano(escalonamento)
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertIn("enviar_followup", args[0])
        self.assertIn("HUMAN_APPROVAL", args[0])
        self.assertIn("desconto de 15%", args[0])
        self.assertEqual(kwargs.get("nivel"), "⚠️")

    def test_contexto_aparece_na_mensagem(self):
        escalonamento = {
            "acao": "alteracao_juridica",
            "fronteira": "HUMAN_REQUIRED",
            "motivo": "cláusula contratual não padrão",
            "urgencia": "🔴",
            "contexto": {"opportunity_id": 42},
        }
        with patch.object(alertas, "alertar") as m:
            alertas.escalar_para_humano(escalonamento)
        args, _ = m.call_args
        self.assertIn("opportunity_id=42", args[0])

    def test_nunca_tem_cooldown_dispara_toda_vez(self):
        escalonamento = {
            "acao": "promessa_nao_documentada",
            "fronteira": "FORBIDDEN",
            "motivo": "IA tentou prometer resultado sem base",
            "urgencia": "🔴",
            "contexto": {},
        }
        with patch.object(alertas, "alertar") as m:
            alertas.escalar_para_humano(escalonamento)
            alertas.escalar_para_humano(escalonamento)
            alertas.escalar_para_humano(escalonamento)
        self.assertEqual(m.call_count, 3)


class _RespostaFalsa:
    def __init__(self, status_code, corpo):
        self.status_code = status_code
        self._corpo = corpo
        self.text = str(corpo)

    def json(self):
        return self._corpo


class EnvioTelegramTest(unittest.TestCase):
    """D13 (V.1.4.164): IPv4 forçado, resposta conferida, fallback sem
    Markdown e envio sem bloquear quem chama."""

    def setUp(self):
        # Outros arquivos de teste chamam logging.disable(CRITICAL) no import;
        # na suíte completa isso esconderia os warnings que assertLogs espera.
        self._disable_anterior = logging.root.manager.disable
        logging.disable(logging.NOTSET)

    def tearDown(self):
        logging.disable(self._disable_anterior)

    def _client_falso(self, respostas):
        client = MagicMock()
        client.__enter__.return_value = client
        client.post.side_effect = respostas
        return client

    def test_forca_ipv4_e_envia(self):
        client = self._client_falso([_RespostaFalsa(200, {"ok": True})])
        with patch("httpx.HTTPTransport") as transporte, patch("httpx.Client", return_value=client):
            self.assertTrue(alertas._enviar_telegram("tok", "123", "oi"))
        self.assertEqual(transporte.call_args.kwargs.get("local_address"), "0.0.0.0")
        self.assertEqual(client.post.call_args.kwargs["json"]["parse_mode"], "Markdown")

    def test_recusa_do_telegram_vira_warning_sem_vazar_token(self):
        client = self._client_falso([_RespostaFalsa(401, {"ok": False, "description": "Unauthorized"})])
        with patch("httpx.Client", return_value=client), \
                self.assertLogs("saleia.alertas", level="WARNING") as logs:
            self.assertFalse(alertas._enviar_telegram("tok-secreto", "123", "oi"))
        self.assertIn("Unauthorized", logs.output[0])
        self.assertNotIn("tok-secreto", logs.output[0])

    def test_markdown_invalido_reenvia_sem_parse_mode(self):
        client = self._client_falso([
            _RespostaFalsa(400, {"ok": False, "description": "Bad Request: can't parse entities"}),
            _RespostaFalsa(200, {"ok": True}),
        ])
        with patch("httpx.Client", return_value=client):
            self.assertTrue(alertas._enviar_telegram("tok", "123", "sales_event.extracao"))
        self.assertEqual(client.post.call_count, 2)
        self.assertNotIn("parse_mode", client.post.call_args.kwargs["json"])

    def test_timeout_vira_warning(self):
        client = self._client_falso(TimeoutError("The read operation timed out"))
        with patch("httpx.Client", return_value=client), \
                self.assertLogs("saleia.alertas", level="WARNING"):
            self.assertFalse(alertas._enviar_telegram("tok", "123", "oi"))

    def test_alertar_nao_bloqueia_quem_chama(self):
        liberar = threading.Event()
        with patch.dict(os.environ, {"TELEGRAM_TOKEN": "tok", "TELEGRAM_CHAT_ID": "123"}), \
                patch.object(alertas, "_enviar_telegram", side_effect=lambda *a: liberar.wait(5)) as envio:
            inicio = time.monotonic()
            alertas.alertar("teste")
            self.assertLess(time.monotonic() - inicio, 1.0)
            liberar.set()
        self.assertEqual(envio.call_args.args[2], "⚠️ *SALEIA*\nteste")

    def test_sem_credenciais_nao_envia(self):
        with patch.dict(os.environ, {"TELEGRAM_TOKEN": "", "TELEGRAM_CHAT_ID": ""}), \
                patch.object(alertas, "_enviar_telegram") as envio:
            alertas.alertar("teste")
        envio.assert_not_called()


class CircuitBreakerAlertaTest(unittest.TestCase):
    def setUp(self):
        alertas._last_alerta.clear()

    def test_um_alerta_por_provedor_por_hora(self):
        from api.ai_router import FAILURES_TO_OPEN, CircuitBreaker

        deepseek, openai = CircuitBreaker("deepseek"), CircuitBreaker("openai")
        with patch.object(alertas, "alertar") as m:
            for _ in range(FAILURES_TO_OPEN + 20):
                deepseek.register_failure()
            for _ in range(FAILURES_TO_OPEN + 5):
                openai.register_failure()
        self.assertEqual(m.call_count, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
