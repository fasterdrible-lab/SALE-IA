"""
Testa a exposicao da versao da extensao Chrome (header X-Extensao-Versao)
nos logs estruturados — mesmo padrao de ContextVar ja usado pelo `cid`
de correlacao (api/main.py::_CorrelationMiddleware).

Run:
    python -m unittest tests.test_extensao_versao_log -v
"""

import asyncio
import io
import json
import logging
import unittest

from starlette.requests import Request
from starlette.responses import PlainTextResponse

import api.main as main


def _run_middleware(headers):
    captured = {}

    async def call_next(request):
        captured["ext_ver"] = main._ext_ver_var.get()
        return PlainTextResponse("ok")

    scope = {"type": "http", "headers": headers, "method": "GET", "path": "/x"}
    request = Request(scope)
    middleware = main._CorrelationMiddleware(app=None)
    asyncio.run(middleware.dispatch(request, call_next))
    return captured["ext_ver"]


class ExtensaoVersaoLogTest(unittest.TestCase):
    def test_middleware_expoe_versao_do_header(self):
        ext_ver = _run_middleware([(b"x-extensao-versao", b"1.4.5")])
        self.assertEqual(ext_ver, "1.4.5")

    def test_middleware_usa_traco_sem_header(self):
        ext_ver = _run_middleware([])
        self.assertEqual(ext_ver, "-")

    def test_contextvar_e_resetado_apos_a_requisicao(self):
        _run_middleware([(b"x-extensao-versao", b"1.4.5")])
        self.assertEqual(main._ext_ver_var.get(), "-")

    def test_json_formatter_inclui_ext_ver(self):
        record = logging.LogRecord("saleia.test", logging.INFO, __file__, 1, "msg", None, None)
        token = main._ext_ver_var.set("1.4.5")
        try:
            formatted = main._JsonFormatter().format(record)
        finally:
            main._ext_ver_var.reset(token)
        doc = json.loads(formatted)
        self.assertEqual(doc["ext_ver"], "1.4.5")

    def test_json_formatter_usa_traco_por_padrao(self):
        record = logging.LogRecord("saleia.test", logging.INFO, __file__, 1, "msg", None, None)
        doc = json.loads(main._JsonFormatter().format(record))
        self.assertEqual(doc["ext_ver"], "-")

    def test_json_formatter_redige_segredo_na_mensagem(self):
        """Tarefa 18.3 ("PROMPT MESTRE — SALE-IA V2"): nunca logar
        senha/token/Authorization header/API key."""
        record = logging.LogRecord(
            "saleia.test", logging.WARNING, __file__, 1,
            "Falha ao autenticar: Authorization: Bearer eyJabc.def.ghi123456",
            None, None,
        )
        doc = json.loads(main._JsonFormatter().format(record))
        self.assertNotIn("eyJabc.def.ghi123456", doc["msg"])
        self.assertIn("***REDACTED***", doc["msg"])

    def test_json_formatter_redige_segredo_na_excecao(self):
        try:
            raise RuntimeError("token=segredo-real-nao-pode-vazar-123")
        except RuntimeError:
            import sys
            record = logging.LogRecord(
                "saleia.test", logging.ERROR, __file__, 1, "erro", None, sys.exc_info(),
            )
        doc = json.loads(main._JsonFormatter().format(record))
        self.assertNotIn("segredo-real-nao-pode-vazar-123", doc["exc"])
        self.assertIn("***REDACTED***", doc["exc"])


class ConfigurarLoggingRedigeSegredosTest(unittest.TestCase):
    """Tarefa 18.3: loggers fora da árvore "saleia.*" (ex.: módulos que
    usam logging.getLogger(__name__), como agent/multiagente/
    claude_fallback.py) também precisam passar pelo mesmo _JsonFormatter
    com redação — sem isso, caem no handler de último recurso do Python
    (stderr cru, sem redação nenhuma)."""

    def setUp(self):
        # Varios arquivos de teste do projeto chamam logging.disable(
        # logging.CRITICAL) no nivel de modulo (import time) sem nunca
        # resetar — em `unittest discover`, isso suprime globalmente
        # qualquer log abaixo de CRITICAL pro resto do processo,
        # independente de handler configurado. Salva/restaura pra este
        # teste nao depender da ordem de import dos outros arquivos.
        self._logging_disable_antes = logging.root.manager.disable
        logging.disable(logging.NOTSET)

        self._root = logging.getLogger()
        self._root_handlers_antes = list(self._root.handlers)
        self._saleia = logging.getLogger("saleia")
        self._saleia_handlers_antes = list(self._saleia.handlers)
        self._saleia_propagate_antes = self._saleia.propagate
        self._root.handlers = []
        self._saleia.handlers = []

    def tearDown(self):
        self._root.handlers = self._root_handlers_antes
        self._saleia.handlers = self._saleia_handlers_antes
        self._saleia.propagate = self._saleia_propagate_antes
        logging.disable(self._logging_disable_antes)

    def test_logger_fora_da_arvore_saleia_e_redigido_via_root(self):
        main._configurar_logging()
        buf = io.StringIO()
        self._root.handlers[0].stream = buf

        outro_logger = logging.getLogger("agent.modulo_qualquer_fora_de_saleia")
        outro_logger.warning("Falha ao autenticar: token=abc123segredoreal")

        saida = buf.getvalue()
        self.assertIn("***REDACTED***", saida)
        self.assertNotIn("abc123segredoreal", saida)

    def test_saleia_log_nao_duplica_via_propagacao_pro_root(self):
        main._configurar_logging()
        buf_saleia = io.StringIO()
        buf_root = io.StringIO()
        self._saleia.handlers[0].stream = buf_saleia
        self._root.handlers[0].stream = buf_root

        logging.getLogger("saleia.teste_18_3").warning("mensagem saleia sem segredo")

        self.assertIn("mensagem saleia sem segredo", buf_saleia.getvalue())
        self.assertEqual(buf_root.getvalue(), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
