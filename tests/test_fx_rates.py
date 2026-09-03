"""
Testes de api/fx_rates.py (Cost Intelligence Fase 3).

Run:
    python -m unittest tests.test_fx_rates -v
"""

import os
import unittest
from unittest.mock import patch

from api import fx_rates


class FxRatesTest(unittest.TestCase):
    def test_taxa_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FX_USD_BRL_RATE", None)
            self.assertEqual(fx_rates.taxa_usd_brl(), 5.40)

    def test_taxa_override_via_env(self):
        with patch.dict(os.environ, {"FX_USD_BRL_RATE": "6.10"}):
            self.assertEqual(fx_rates.taxa_usd_brl(), 6.10)

    def test_usd_para_brl_usa_taxa_atual(self):
        with patch.dict(os.environ, {"FX_USD_BRL_RATE": "5.00"}):
            self.assertEqual(fx_rates.usd_para_brl(10.0), 50.0)

    def test_usd_para_brl_arredonda_2_casas(self):
        with patch.dict(os.environ, {"FX_USD_BRL_RATE": "5.333333"}):
            self.assertEqual(fx_rates.usd_para_brl(1.0), 5.33)

    def test_usd_para_brl_none_vira_zero(self):
        self.assertEqual(fx_rates.usd_para_brl(None), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
