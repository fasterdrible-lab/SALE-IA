"""
Testes — Dev Manual só para admin (13/10/2026). A página pública é só a
casca; o conteúdo exige JWT de admin.

Run:
    python -m unittest tests.test_manual_tecnico -v
"""
import unittest

from fastapi.testclient import TestClient

import api.main as main


class TestManualTecnico(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def _h(self, perfil):
        return {"Authorization": "Bearer " + main._gerar_token("u1", "x@saleia.app.br", perfil)}

    def test_pagina_publica_e_so_a_casca_sem_conteudo(self):
        r = self.client.get("/manual-tecnico")
        self.assertEqual(r.status_code, 200)
        self.assertIn("/manual-tecnico/conteudo", r.text)
        self.assertNotIn("Roteador de IA", r.text)
        self.assertIn("noindex", r.headers.get("x-robots-tag", ""))

    def test_conteudo_exige_admin(self):
        self.assertEqual(self.client.get("/manual-tecnico/conteudo").status_code, 401)
        self.assertEqual(self.client.get("/manual-tecnico/conteudo", headers=self._h("operador")).status_code, 403)
        r = self.client.get("/manual-tecnico/conteudo", headers=self._h("admin"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("Dev Manual", r.text)
        self.assertEqual(r.headers.get("cache-control"), "no-store")

    def test_manual_nao_expoe_acesso_a_vps(self):
        texto = self.client.get("/manual-tecnico/conteudo", headers=self._h("admin")).text
        for proibido in ("37.27.214.33", "root@", "@gmail.com"):
            self.assertNotIn(proibido, texto)


if __name__ == "__main__":
    unittest.main()
