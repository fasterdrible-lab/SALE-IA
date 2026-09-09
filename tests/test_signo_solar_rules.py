"""
Testes unitários — agent/signo_solar_rules.py (astrologia opcional,
signo solar). Função pura, sem IA, sem rede — cobre casos de fronteira
entre signos e entradas inválidas.

Run:
    python -m unittest tests.test_signo_solar_rules -v
"""
import unittest

from agent.signo_solar_rules import DISCLAIMER_ASTROLOGIA, SIGNOS, calcular_signo, obter_perfil_signo


class CalcularSignoTest(unittest.TestCase):
    def test_dentro_do_intervalo_normal(self):
        self.assertEqual(calcular_signo(15, 3), "Peixes")
        self.assertEqual(calcular_signo(25, 12), "Capricórnio")
        self.assertEqual(calcular_signo(1, 7), "Câncer")

    def test_fronteiras_exatas(self):
        self.assertEqual(calcular_signo(21, 3), "Áries")  # início de Áries
        self.assertEqual(calcular_signo(19, 4), "Áries")  # fim de Áries
        self.assertEqual(calcular_signo(20, 4), "Touro")  # início de Touro

    def test_capricornio_atravessa_o_ano(self):
        self.assertEqual(calcular_signo(31, 12), "Capricórnio")
        self.assertEqual(calcular_signo(1, 1), "Capricórnio")
        self.assertEqual(calcular_signo(19, 1), "Capricórnio")
        self.assertEqual(calcular_signo(20, 1), "Aquário")
        self.assertEqual(calcular_signo(22, 12), "Capricórnio")
        self.assertEqual(calcular_signo(21, 12), "Sagitário")

    def test_dia_ou_mes_ausente_retorna_none(self):
        self.assertIsNone(calcular_signo(None, 3))
        self.assertIsNone(calcular_signo(15, None))
        self.assertIsNone(calcular_signo(None, None))

    def test_mes_invalido_retorna_none(self):
        self.assertIsNone(calcular_signo(15, 13))
        self.assertIsNone(calcular_signo(15, 0))

    def test_dia_invalido_retorna_none(self):
        self.assertIsNone(calcular_signo(32, 3))
        self.assertIsNone(calcular_signo(0, 3))

    def test_tipo_nao_numerico_retorna_none(self):
        self.assertIsNone(calcular_signo("quinze", 3))

    def test_todos_os_12_signos_sao_alcancaveis(self):
        # Um dia "meio" de cada intervalo confirmado deve resolver para
        # cada um dos 12 signos — garante que a tabela cobre o ano inteiro
        # sem lacunas.
        casos = {
            "Áries": (1, 4), "Touro": (1, 5), "Gêmeos": (1, 6), "Câncer": (1, 7),
            "Leão": (1, 8), "Virgem": (1, 9), "Libra": (1, 10), "Escorpião": (1, 11),
            "Sagitário": (1, 12), "Capricórnio": (10, 1), "Aquário": (1, 2), "Peixes": (25, 2),
        }
        for esperado, (dia, mes) in casos.items():
            self.assertEqual(calcular_signo(dia, mes), esperado, f"dia={dia} mes={mes}")


class ObterPerfilSignoTest(unittest.TestCase):
    def test_signo_valido_retorna_perfil_completo(self):
        perfil = obter_perfil_signo("Áries")
        self.assertEqual(perfil["nome"], "Áries")
        self.assertEqual(perfil["elemento"], "Fogo")
        self.assertIn("disclaimer", perfil)
        self.assertEqual(perfil["disclaimer"], DISCLAIMER_ASTROLOGIA)

    def test_signo_invalido_retorna_none(self):
        self.assertIsNone(obter_perfil_signo("Signo Inexistente"))
        self.assertIsNone(obter_perfil_signo(None))

    def test_todos_os_12_signos_tem_campos_minimos(self):
        campos_obrigatorios = {
            "simbolo", "periodo", "elemento", "modalidade", "regente", "arquetipo",
            "comunicacao", "motivadores", "pontos_fortes", "pontos_atencao", "sob_pressao",
        }
        for nome in SIGNOS:
            perfil = obter_perfil_signo(nome)
            faltando = campos_obrigatorios - set(perfil.keys())
            self.assertEqual(faltando, set(), f"{nome} sem campos: {faltando}")


class GuardaArquiteturalTest(unittest.TestCase):
    """Garante por construção que astrologia nunca pode ajustar DISC/Big
    Five: o módulo de signo não importa nada de IA/rede."""

    def test_modulo_signo_nao_importa_ia(self):
        import agent.signo_solar_rules as mod
        with open(mod.__file__, encoding="utf-8") as f:
            fonte = f.read()
        proibidos = ["chamar_ia", "ai_router", "import requests", "import httpx", "openai", "anthropic"]
        for termo in proibidos:
            self.assertNotIn(termo, fonte, f"signo_solar_rules.py não deveria referenciar '{termo}'")

    def test_prompts_disc_e_bigfive_nunca_recebem_astrologia_como_input(self):
        # O prompt pode mencionar "astrologia" só para INSTRUIR a IA a
        # ignorá-la (defesa em profundidade) — o que nunca pode existir é
        # um placeholder de substituição trazendo dado de signo/astrologia
        # como entrada real do prompt (isso sim contaminaria o cálculo).
        from pathlib import Path
        base = Path(__file__).parent.parent / "agent" / "prompt_templates"
        for nome in ("multiagente_disc.txt", "multiagente_bigfive.txt"):
            texto = (base / nome).read_text(encoding="utf-8").lower()
            for placeholder in ("{signo", "{astrolog", "{zodiac", "{perfil_astrologico"):
                self.assertNotIn(placeholder, texto, f"{nome} não deveria ter um placeholder '{placeholder}...}}'")


if __name__ == "__main__":
    unittest.main()
