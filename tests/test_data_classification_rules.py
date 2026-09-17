"""
Testes — agent/data_classification_rules.py

Tarefa 18.3 do "PROMPT MESTRE — SALE-IA V2": classificação de dados +
nunca logar senha/token/Authorization header/API key.

Run:
    python -m unittest tests.test_data_classification_rules -v
"""
import unittest

from agent.data_classification_rules import (
    CLASSIFICACAO_CAMPOS_PADRAO,
    DATA_CLASSIFICATION_LEVELS,
    RETENTION_SUGERIDA_DIAS_PADRAO,
    classificar_campo,
    redigir_dict,
    redigir_segredos,
)


class DataClassificationLevelsTest(unittest.TestCase):
    def test_os_5_niveis_literais_do_prompt_mestre(self):
        self.assertEqual(
            DATA_CLASSIFICATION_LEVELS,
            ("PUBLIC", "INTERNAL", "CONFIDENTIAL", "PII", "SENSITIVE"),
        )

    def test_todo_campo_catalogado_usa_um_nivel_valido(self):
        for campo, nivel in CLASSIFICACAO_CAMPOS_PADRAO.items():
            self.assertIn(nivel, DATA_CLASSIFICATION_LEVELS, f"{campo} -> {nivel}")

    def test_retention_cobre_exatamente_os_5_niveis(self):
        self.assertEqual(set(RETENTION_SUGERIDA_DIAS_PADRAO), set(DATA_CLASSIFICATION_LEVELS))


class ClassificarCampoTest(unittest.TestCase):
    def test_campo_conhecido_pii(self):
        self.assertEqual(classificar_campo("email"), "PII")
        self.assertEqual(classificar_campo("EMAIL"), "PII")  # case-insensitive

    def test_campo_conhecido_sensitive(self):
        self.assertEqual(classificar_campo("senha"), "SENSITIVE")
        self.assertEqual(classificar_campo("api_key"), "SENSITIVE")

    def test_campo_desconhecido_retorna_none_nunca_adivinha(self):
        self.assertIsNone(classificar_campo("campo_que_nao_existe"))

    def test_campo_vazio_retorna_none(self):
        self.assertIsNone(classificar_campo(""))
        self.assertIsNone(classificar_campo(None))


class RedigirSegredosTest(unittest.TestCase):
    def test_senha_com_igual_e_redigida(self):
        resultado = redigir_segredos("senha=minhaSenhaSecreta123")
        self.assertNotIn("minhaSenhaSecreta123", resultado)
        self.assertIn("***REDACTED***", resultado)
        self.assertIn("senha=", resultado)  # mantem o rotulo

    def test_token_com_dois_pontos_e_redigido(self):
        resultado = redigir_segredos("token: eyJhbGciOiJIUzI1NiJ9.abc.def")
        self.assertNotIn("eyJhbGciOiJIUzI1NiJ9.abc.def", resultado)
        self.assertIn("***REDACTED***", resultado)

    def test_authorization_header_e_redigido(self):
        resultado = redigir_segredos("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def")
        self.assertNotIn("eyJhbGciOiJIUzI1NiJ9.abc.def", resultado)
        self.assertIn("***REDACTED***", resultado)

    def test_bearer_isolado_sem_rotulo_authorization_e_redigido(self):
        resultado = redigir_segredos("cabecalho recebido: Bearer sk-abcdef1234567890xyz")
        self.assertNotIn("sk-abcdef1234567890xyz", resultado)
        self.assertIn("***REDACTED***", resultado)

    def test_api_key_com_igual_e_redigida(self):
        resultado = redigir_segredos("api_key=sk-proj-abc123def456ghi789")
        self.assertNotIn("sk-proj-abc123def456ghi789", resultado)

    def test_chave_openai_style_solta_e_redigida(self):
        resultado = redigir_segredos("erro ao chamar provedor com chave sk-abcdefghij1234567890")
        self.assertNotIn("sk-abcdefghij1234567890", resultado)
        self.assertIn("***REDACTED***", resultado)

    def test_chave_google_style_solta_e_redigida(self):
        resultado = redigir_segredos("GEMINI_API_KEY invalida: AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz1234")
        self.assertNotIn("AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz1234", resultado)

    def test_texto_comercial_normal_nao_e_alterado(self):
        texto = "O cliente disse que o token de compra ainda nao foi liberado pelo financeiro."
        self.assertEqual(redigir_segredos(texto), texto)

    def test_frase_com_a_palavra_senha_sem_valor_nao_e_alterada(self):
        texto = "O vendedor esqueceu a senha do dashboard e pediu recuperacao."
        self.assertEqual(redigir_segredos(texto), texto)

    def test_texto_vazio_ou_none_nunca_levanta(self):
        self.assertEqual(redigir_segredos(""), "")
        self.assertEqual(redigir_segredos(None), "")


class RedigirDictTest(unittest.TestCase):
    def test_chave_secreta_e_mascarada_independente_do_valor(self):
        entrada = {"usuario": "vendedor@empresa.com", "senha": "abc123"}
        resultado = redigir_dict(entrada)
        self.assertEqual(resultado["senha"], "***REDACTED***")
        self.assertEqual(resultado["usuario"], "vendedor@empresa.com")

    def test_chave_com_token_no_nome_e_mascarada(self):
        entrada = {"oauth_token_encrypted": "cripto-xyz", "status": "ativo"}
        resultado = redigir_dict(entrada)
        self.assertEqual(resultado["oauth_token_encrypted"], "***REDACTED***")
        self.assertEqual(resultado["status"], "ativo")

    def test_recursivo_em_listas_e_dicts_aninhados(self):
        entrada = {"conexoes": [{"api_key": "sk-123456789012"}, {"nome": "ok"}]}
        resultado = redigir_dict(entrada)
        self.assertEqual(resultado["conexoes"][0]["api_key"], "***REDACTED***")
        self.assertEqual(resultado["conexoes"][1]["nome"], "ok")

    def test_string_solta_tambem_passa_por_redigir_segredos(self):
        resultado = redigir_dict("Authorization: Bearer abc.def.ghi")
        self.assertIn("***REDACTED***", resultado)

    def test_tipos_nao_string_passam_intactos(self):
        self.assertEqual(redigir_dict(42), 42)
        self.assertEqual(redigir_dict(None), None)
        self.assertEqual(redigir_dict(True), True)


if __name__ == "__main__":
    unittest.main()
