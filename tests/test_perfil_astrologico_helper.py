"""
Testes — api/main.py::_processar_perfil_astrologico()

Cobre: sem menção de nascimento -> perfil_astrologico None, sem tocar
client_intelligence; com menção -> calcula o signo e persiste só se a
reunião tiver cliente vinculado.

Run:
    python -m unittest tests.test_perfil_astrologico_helper -v
"""

import logging
import unittest
from unittest.mock import patch

logging.disable(logging.CRITICAL)

from api.main import _processar_perfil_astrologico


class ProcessarPerfilAstrologicoTest(unittest.TestCase):
    def test_sem_data_nascimento_mencionada_fica_none(self):
        resultado = {"recapitulacao": {}}
        _processar_perfil_astrologico(resultado, "m1")
        self.assertIsNone(resultado["perfil_astrologico"])

    def test_data_invalida_fica_none(self):
        resultado = {"data_nascimento_mencionada": {"dia": 40, "mes": 13}}
        _processar_perfil_astrologico(resultado, "m1")
        self.assertIsNone(resultado["perfil_astrologico"])

    def test_data_valida_calcula_signo(self):
        resultado = {"data_nascimento_mencionada": {"dia": 21, "mes": 3}}
        with patch("agent.client_intelligence.buscar_cliente_por_reuniao", return_value=None):
            _processar_perfil_astrologico(resultado, "m1")
        self.assertIsNotNone(resultado["perfil_astrologico"])
        self.assertEqual(resultado["perfil_astrologico"]["nome"], "Áries")

    def test_com_cliente_vinculado_persiste_nascimento(self):
        resultado = {"data_nascimento_mencionada": {"dia": 21, "mes": 3}}
        with patch("agent.client_intelligence.buscar_cliente_por_reuniao", return_value="c1"), \
             patch("agent.client_intelligence.salvar_nascimento_cliente") as mock_salvar:
            _processar_perfil_astrologico(resultado, "m1")
        mock_salvar.assert_called_once_with("c1", 21, 3)

    def test_formato_real_do_endpoint_campo_dentro_de_recapitulacao(self):
        # Regressão V.1.4.145: /recapitulacao-manual|completa entregam o
        # campo aninhado; antes só o nível de cima era lido.
        resultado = {"recapitulacao": {"data_nascimento_mencionada": {"dia": 21, "mes": 3}}}
        with patch("agent.client_intelligence.buscar_cliente_por_reuniao", return_value=None):
            _processar_perfil_astrologico(resultado, "m1")
        self.assertEqual(resultado["perfil_astrologico"]["nome"], "Áries")

    def test_placeholder_do_schema_dia_zero_fica_none(self):
        resultado = {"recapitulacao": {"data_nascimento_mencionada": {"dia": 0, "mes": 0}}}
        _processar_perfil_astrologico(resultado, "m1")
        self.assertIsNone(resultado["perfil_astrologico"])

    def test_sem_cliente_vinculado_nao_persiste(self):
        resultado = {"data_nascimento_mencionada": {"dia": 21, "mes": 3}}
        with patch("agent.client_intelligence.buscar_cliente_por_reuniao", return_value=None), \
             patch("agent.client_intelligence.salvar_nascimento_cliente") as mock_salvar:
            _processar_perfil_astrologico(resultado, "m1")
        mock_salvar.assert_not_called()
        self.assertIsNotNone(resultado["perfil_astrologico"])


if __name__ == "__main__":
    unittest.main()
