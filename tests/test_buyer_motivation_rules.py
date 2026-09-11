"""
Testes do Buyer Motivation Engine — Fase 5 / Tarefa 5.1 do "PROMPT
MESTRE — SALE-IA V2".

Função pura (agent/buyer_motivation_rules.py), sem IA/banco. Regra
central do prompt mestre — "DISC nunca deverá ser tratado como
motivação" — testada em dois níveis: (1) comportamento, simulando um
diálogo onde o DISC (externo, opaco a este módulo) permanece igual
enquanto a motivação muda entre turnos; (2) construção, garantindo que
o módulo não importa/lê nada relacionado a DISC (mesmo padrão de
tests/test_signo_solar_rules.py::GuardaArquiteturalTest).

Run:
    python -m unittest tests.test_buyer_motivation_rules -v
"""

import unittest

from agent.buyer_motivation_rules import (
    MOTIVATION_TIPOS,
    motivacao_dominante,
    validar_hipoteses_motivacao,
)


def _hipotese(motivation, confidence=0.8, evidence=None):
    if evidence is None:
        evidence = ["evidencia generica"]
    return {"motivation": motivation, "confidence": confidence, "evidence": evidence}


class ValidarHipotesesMotivacaoTest(unittest.TestCase):
    def test_hipotese_valida_nao_levanta(self):
        validar_hipoteses_motivacao([_hipotese("GROWTH", 0.7, ["quer dobrar o time em 2026"])])

    def test_lista_vazia_nao_levanta(self):
        validar_hipoteses_motivacao([])

    def test_motivation_invalida_levanta(self):
        with self.assertRaises(ValueError):
            validar_hipoteses_motivacao([_hipotese("MEDO")])

    def test_confidence_fora_do_intervalo_levanta(self):
        with self.assertRaises(ValueError):
            validar_hipoteses_motivacao([_hipotese("SECURITY", confidence=1.2)])

    def test_evidence_ausente_levanta(self):
        hipotese = {"motivation": "SPEED", "confidence": 0.6}
        with self.assertRaises(ValueError):
            validar_hipoteses_motivacao([hipotese])

    def test_evidence_lista_vazia_levanta(self):
        with self.assertRaises(ValueError):
            validar_hipoteses_motivacao([_hipotese("SPEED", evidence=[])])

    def test_evidence_com_apenas_string_vazia_levanta(self):
        with self.assertRaises(ValueError):
            validar_hipoteses_motivacao([_hipotese("SPEED", evidence=["   "])])


class MotivacaoDominanteTest(unittest.TestCase):
    def test_none_quando_lista_vazia(self):
        self.assertIsNone(motivacao_dominante([]))

    def test_retorna_a_de_maior_confidence(self):
        hipoteses = [
            _hipotese("COST_REDUCTION", 0.4, ["mencionou reduzir custo, sem enfase"]),
            _hipotese("STATUS", 0.85, ["quer ser a primeira empresa do setor a usar isso"]),
            _hipotese("SPEED", 0.6, ["quer implementar rapido"]),
        ]
        dominante = motivacao_dominante(hipoteses)
        self.assertEqual(dominante["motivation"], "STATUS")

    def test_empate_mantem_ordem_de_chegada(self):
        hipoteses = [
            _hipotese("GROWTH", 0.7, ["quer crescer"]),
            _hipotese("SECURITY", 0.7, ["quer seguranca"]),
        ]
        dominante = motivacao_dominante(hipoteses)
        self.assertEqual(dominante["motivation"], "GROWTH")

    def test_taxonomia_tem_os_12_motivadores_do_prompt_mestre(self):
        self.assertEqual(
            MOTIVATION_TIPOS,
            frozenset({
                "GROWTH", "SECURITY", "CONTROL", "STATUS", "CONVENIENCE", "SPEED",
                "COST_REDUCTION", "REVENUE_GAIN", "RISK_REDUCTION", "PRODUCTIVITY",
                "RECOGNITION", "SIMPLICITY",
            }),
        )


class DialogoDiscPermaneceMotivacaoMudaTest(unittest.TestCase):
    """Regra do prompt mestre: DISC nunca é motivação. Simula 3 turnos de
    um dialogo onde o DISC (dado externo, opaco a este modulo) permanece
    'D' o tempo todo, enquanto a motivacao dominante muda turno a turno —
    o motor precisa refletir a mudanca real, nunca herdar o valor do
    turno anterior."""

    def test_disc_constante_motivacao_muda_entre_turnos(self):
        turnos = [
            {"disc": "D", "hipoteses": [_hipotese("SPEED", 0.8, ["quer decidir rapido, sem enrolacao"])]},
            {"disc": "D", "hipoteses": [_hipotese("CONTROL", 0.85, ["quer aprovar cada etapa pessoalmente"])]},
            {"disc": "D", "hipoteses": [_hipotese("STATUS", 0.9, ["quer ser referencia no mercado com isso"])]},
        ]

        discs = {turno["disc"] for turno in turnos}
        motivacoes = [motivacao_dominante(turno["hipoteses"])["motivation"] for turno in turnos]

        self.assertEqual(discs, {"D"}, "DISC deveria permanecer igual nos 3 turnos")
        self.assertEqual(motivacoes, ["SPEED", "CONTROL", "STATUS"])
        self.assertEqual(len(set(motivacoes)), 3, "motivacao deveria mudar em cada turno, nao ficar presa ao DISC")


class GuardaArquiteturalTest(unittest.TestCase):
    """Garante por construção que DISC nunca é tratado como motivação:
    o módulo de motivação não importa nem lê nada relacionado a DISC —
    mesmo padrão de tests/test_signo_solar_rules.py."""

    def test_modulo_nao_referencia_disc(self):
        import agent.buyer_motivation_rules as mod
        with open(mod.__file__, encoding="utf-8") as f:
            fonte = f.read().lower()
        proibidos = ["disc_agent", "perfil_disc", '"disc"', "'disc'", "import disc"]
        for termo in proibidos:
            self.assertNotIn(termo, fonte, f"buyer_motivation_rules.py não deveria referenciar '{termo}'")

    def test_modulo_nao_importa_ia(self):
        import agent.buyer_motivation_rules as mod
        with open(mod.__file__, encoding="utf-8") as f:
            fonte = f.read()
        proibidos = ["chamar_ia", "ai_router", "import requests", "import httpx", "openai", "anthropic"]
        for termo in proibidos:
            self.assertNotIn(termo, fonte, f"buyer_motivation_rules.py não deveria referenciar '{termo}'")


if __name__ == "__main__":
    unittest.main()
