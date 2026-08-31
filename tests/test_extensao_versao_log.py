"""
Testa a exposicao da versao da extensao Chrome (header X-Extensao-Versao)
nos logs estruturados — mesmo padrao de ContextVar ja usado pelo `cid`
de correlacao (api/main.py::_CorrelationMiddleware).

Run:
    python -m unittest tests.test_extensao_versao_log -v
"""

import asyncio
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
