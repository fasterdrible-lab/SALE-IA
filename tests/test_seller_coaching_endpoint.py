"""
Testes — GET /seller-coaching/{seller_id}, Fase 22 (Frontend) / bloco
"Seller Coaching" do "PROMPT MESTRE — SALE-IA V2" (fecha a Fase 22).

Mesmo padrão de tests/test_opportunity_intelligence_endpoint.py
(TestClient real + ownership via _verificar_dono_ou_admin). Diferente
daquele endpoint, este não lê nenhuma tabela — o payload é sempre os 8
gaps de agent/seller_coaching_rules.py, então não precisa de SQLite em
memória nem de fixtures de dado.

Run:
    python -m unittest tests.test_seller_coaching_endpoint -v
"""
import logging
import unittest

logging.disable(logging.CRITICAL)


class SellerCoachingEndpointTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import api.main as _main

        from fastapi.testclient import TestClient
        cls._ctx = TestClient(_main.app)
        cls.client = cls._ctx.__enter__()
        cls._main = _main

        cls.admin_token = _main._gerar_token("admin-1", "admin@saleia.app.br", "admin")
        cls.admin_headers = {"Authorization": f"Bearer {cls.admin_token}"}
        cls.dono_token = _main._gerar_token("seller-dono", "dono@saleia.app.br", "vendedor")
        cls.dono_headers = {"Authorization": f"Bearer {cls.dono_token}"}
        cls.outro_token = _main._gerar_token("seller-outro", "outro@saleia.app.br", "vendedor")
        cls.outro_headers = {"Authorization": f"Bearer {cls.outro_token}"}

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def test_sem_token_401(self):
        r = self.client.get("/seller-coaching/seller-dono")
        self.assertEqual(r.status_code, 401)

    def test_outro_vendedor_recebe_404_nunca_403(self):
        r = self.client.get("/seller-coaching/seller-dono", headers=self.outro_headers)
        self.assertEqual(r.status_code, 404)

    def test_dono_acessa_200(self):
        r = self.client.get("/seller-coaching/seller-dono", headers=self.dono_headers)
        self.assertEqual(r.status_code, 200)

    def test_admin_acessa_qualquer_seller_id_200(self):
        r = self.client.get("/seller-coaching/seller-dono", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)

    def test_payload_traz_os_8_campos_como_gap_explicito(self):
        r = self.client.get("/seller-coaching/seller-dono", headers=self.dono_headers)
        body = r.json()
        self.assertEqual(body["seller_id"], "seller-dono")
        campos = (
            "talk_ratio", "question_quality", "spin_coverage", "qualification",
            "objection_handling", "negotiation", "next_step_discipline", "trend",
        )
        for campo in campos:
            self.assertIn(campo, body)
            self.assertFalse(body[campo]["disponivel"], campo)
            self.assertTrue(body[campo]["motivo"], campo)


if __name__ == "__main__":
    unittest.main()
