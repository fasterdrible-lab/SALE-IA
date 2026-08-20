"""
Testes — agent/propensao_rules.py

Cobre a Tarefa 51 do prompt de desenvolvimento (V.1.4.40): classificacao
deterministica de propensao nas 4 faixas (alta/media/baixa/nao_determinada)
e a Tarefa 38/V.1.4.41: limiares configuraveis via variavel de ambiente.

Run:
    python -m unittest tests.test_propensao_rules -v
"""

import importlib
import os
import unittest
from unittest.mock import patch


class PropensaoRulesSuite(unittest.TestCase):

    def setUp(self):
        import agent.propensao_rules as _mod
        self.mod = _mod

    def test_score_alto_classifica_como_alta(self):
        self.assertEqual(self.mod.classificar_propensao(85), "alta")
        self.assertEqual(self.mod.classificar_propensao(70), "alta")  # limite inclusivo

    def test_score_medio_classifica_como_media(self):
        self.assertEqual(self.mod.classificar_propensao(60), "media")
        self.assertEqual(self.mod.classificar_propensao(45), "media")  # limite inclusivo

    def test_score_baixo_classifica_como_baixa(self):
        self.assertEqual(self.mod.classificar_propensao(20), "baixa")
        self.assertEqual(self.mod.classificar_propensao(0), "baixa")

    def test_score_ausente_ou_invalido_classifica_como_nao_determinada(self):
        self.assertEqual(self.mod.classificar_propensao(None), "nao_determinada")
        self.assertEqual(self.mod.classificar_propensao("abc"), "nao_determinada")
        self.assertEqual(self.mod.classificar_propensao(""), "nao_determinada")

    def test_limiares_padrao(self):
        self.assertEqual(self.mod.LIMIAR_ALTA, 70)
        self.assertEqual(self.mod.LIMIAR_MEDIA, 45)

    def test_limiares_configuraveis_via_env(self):
        # reload() muta o módulo em memória (é o mesmo objeto para todos os
        # testes) — o reload de restauração precisa rodar FORA do
        # patch.dict, senão ele "restaura" lendo os próprios valores
        # sobrescritos em vez dos originais.
        import agent.propensao_rules as _mod2
        try:
            with patch.dict(
                os.environ,
                {"PROPENSAO_LIMIAR_ALTA": "60", "PROPENSAO_LIMIAR_MEDIA": "30"},
            ):
                importlib.reload(_mod2)
                self.assertEqual(_mod2.LIMIAR_ALTA, 60.0)
                self.assertEqual(_mod2.LIMIAR_MEDIA, 30.0)
                self.assertEqual(_mod2.classificar_propensao(65), "alta")
        finally:
            importlib.reload(_mod2)  # env já restaurado aqui — volta aos padrões

    def test_limiar_env_invalido_cai_no_padrao(self):
        import agent.propensao_rules as _mod3
        try:
            with patch.dict(os.environ, {"PROPENSAO_LIMIAR_ALTA": "nao-e-numero"}):
                importlib.reload(_mod3)
                self.assertEqual(_mod3.LIMIAR_ALTA, 70)
        finally:
            importlib.reload(_mod3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
