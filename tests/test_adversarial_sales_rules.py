"""
Testes — agent/adversarial_sales_rules.py

Fase 21 do "PROMPT MESTRE — SALE-IA V2" (Testes de Adversarial Sales).

Run:
    python -m unittest tests.test_adversarial_sales_rules -v
"""
import unittest

from agent.adversarial_sales_rules import ADVERSARIAL_SALES_GUARD_TEXT


class AdversarialSalesGuardTextTest(unittest.TestCase):
    def test_nao_vazio(self):
        self.assertTrue(ADVERSARIAL_SALES_GUARD_TEXT.strip())

    def test_cobre_os_3_casos_sem_guarda_previa(self):
        texto = ADVERSARIAL_SALES_GUARD_TEXT.lower()
        # Caso 1: nunca inventar ataque a concorrente.
        self.assertIn("concorrente", texto)
        # Caso 2: nunca burlar politica de desconto "as escondidas".
        self.assertIn("desconto", texto)
        self.assertIn("lideranca", texto)
        # Caso 3: nunca garantir resultado/ROI sem base.
        self.assertIn("retorno", texto)
        self.assertIn("garanta", texto)


if __name__ == "__main__":
    unittest.main()
