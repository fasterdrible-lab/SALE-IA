"""
Testes do Negotiation Engine — Fase 6 / Tarefa 6.2 do "PROMPT MESTRE —
SALE-IA V2".

Função pura (agent/negotiation_rules.py), sem IA/banco — constrói sobre
`agent/objection_rules.precisa_investigar()` (Tarefa 6.1). Reproduz o
teste específico do prompt mestre: cliente diz "Está caro." → resultado
proibido "Posso dar 20% agora." → resultado esperado: estratégia de
investigação.

Run:
    python -m unittest tests.test_negotiation_rules -v
"""

import unittest

from agent.negotiation_rules import (
    DESCRICOES_ESTRATEGIAS,
    ESTRATEGIAS_INVESTIGATIVAS,
    ESTRATEGIAS_POS_INVESTIGACAO,
    NEGOTIATION_TIPOS,
    recomendar_estrategia,
)


def _spoken(category, evidence_quote="evidencia generica"):
    return {"category": category, "evidence_quote": evidence_quote}


def _root(hypothesis, confidence=0.8, evidence_quote="evidencia da investigacao"):
    return {"hypothesis": hypothesis, "confidence": confidence, "evidence_quote": evidence_quote}


class TaxonomiaTest(unittest.TestCase):
    def test_taxonomia_tem_as_7_estrategias_do_prompt_mestre(self):
        self.assertEqual(
            NEGOTIATION_TIPOS,
            frozenset({
                "LABEL", "MIRROR", "CALIBRATED_QUESTION", "SUMMARIZE",
                "CLARIFY", "VALUE_REFRAME", "RISK_REDUCTION",
            }),
        )

    def test_estrategias_investigativas_e_pos_investigacao_cobrem_toda_taxonomia_sem_sobrepor(self):
        self.assertEqual(ESTRATEGIAS_INVESTIGATIVAS | ESTRATEGIAS_POS_INVESTIGACAO, NEGOTIATION_TIPOS)
        self.assertEqual(ESTRATEGIAS_INVESTIGATIVAS & ESTRATEGIAS_POS_INVESTIGACAO, frozenset())

    def test_todos_os_7_tipos_tem_descricao_canonica(self):
        self.assertEqual(set(DESCRICOES_ESTRATEGIAS.keys()), NEGOTIATION_TIPOS)

    def test_desconto_nao_e_uma_estrategia_valida(self):
        self.assertNotIn("DISCOUNT", NEGOTIATION_TIPOS)
        self.assertNotIn("GIVE_DISCOUNT", NEGOTIATION_TIPOS)


class RecomendarEstrategiaTest(unittest.TestCase):
    def test_exemplo_literal_do_prompt_mestre_esta_caro_recomenda_investigacao(self):
        """Cliente diz 'Está caro.' sem nenhuma causa raiz investigada
        ainda — resultado esperado e uma estrategia de INVESTIGACAO,
        nunca uma concessao/desconto (que nem existe na taxonomia)."""
        spoken = _spoken("PRICE", "Está caro.")
        recomendacao = recomendar_estrategia(spoken)

        self.assertTrue(recomendacao["precisa_investigar"])
        self.assertIn(recomendacao["estrategia"], ESTRATEGIAS_INVESTIGATIVAS)
        self.assertEqual(recomendacao["estrategia"], "CALIBRATED_QUESTION")

    def test_forcar_estrategia_pos_investigacao_durante_investigacao_levanta(self):
        """Regra central: mesmo se um chamador (ou uma IA futura)
        tentar pular direto pra VALUE_REFRAME sem investigar, o motor
        recusa — nunca deixa 'Está caro.' virar uma resposta de
        concessao disfarcada."""
        spoken = _spoken("PRICE", "Está caro.")
        with self.assertRaises(ValueError):
            recomendar_estrategia(spoken, estrategia_desejada="VALUE_REFRAME")

    def test_estrategia_investigativa_explicita_e_aceita_durante_investigacao(self):
        spoken = _spoken("PRICE", "Está caro.")
        recomendacao = recomendar_estrategia(spoken, estrategia_desejada="MIRROR")
        self.assertEqual(recomendacao["estrategia"], "MIRROR")

    def test_apos_investigacao_real_permite_estrategia_pos_investigacao(self):
        spoken = _spoken("PRICE", "Está caro.")
        root = _root(
            "ADOPTION_RISK", confidence=0.8,
            evidence_quote="Perguntei o porque e ele disse que teme a equipe nao adotar",
        )
        recomendacao = recomendar_estrategia(spoken, root, estrategia_desejada="RISK_REDUCTION")

        self.assertFalse(recomendacao["precisa_investigar"])
        self.assertEqual(recomendacao["estrategia"], "RISK_REDUCTION")

    def test_default_apos_investigacao_e_value_reframe(self):
        spoken = _spoken("PRICE", "Está caro.")
        root = _root(
            "ADOPTION_RISK", confidence=0.8,
            evidence_quote="Perguntei o porque e ele disse que teme a equipe nao adotar",
        )
        recomendacao = recomendar_estrategia(spoken, root)
        self.assertEqual(recomendacao["estrategia"], "VALUE_REFRAME")

    def test_estrategia_fora_da_taxonomia_levanta(self):
        spoken = _spoken("PRICE", "Está caro.")
        with self.assertRaises(ValueError):
            recomendar_estrategia(spoken, estrategia_desejada="GIVE_DISCOUNT")

    def test_descricao_da_recomendacao_bate_com_a_canonica(self):
        spoken = _spoken("BUDGET", "nao temos verba esse trimestre")
        recomendacao = recomendar_estrategia(spoken)
        self.assertEqual(recomendacao["descricao"], DESCRICOES_ESTRATEGIAS[recomendacao["estrategia"]])

    def test_spoken_invalido_propaga_erro_de_objection_rules(self):
        with self.assertRaises(ValueError):
            recomendar_estrategia(_spoken("CARO_DEMAIS"))


class GuardaContraTaticasManipulativasTest(unittest.TestCase):
    """Regra explícita do prompt mestre: nunca permitir ameaça, mentira,
    escassez falsa, manipulação, informações inventadas — garantida
    verificando que nenhuma descrição canônica menciona essas táticas."""

    def test_nenhuma_descricao_menciona_taticas_proibidas(self):
        termos_proibidos = [
            "desconto", "ameaç", "mentir", "escassez falsa", "urgencia falsa",
            "urgência falsa", "manipul", "inventad", "ultimato",
        ]
        for tipo, descricao in DESCRICOES_ESTRATEGIAS.items():
            descricao_normalizada = descricao.lower()
            for termo in termos_proibidos:
                self.assertNotIn(
                    termo, descricao_normalizada,
                    f"descricao de {tipo!r} nao deveria conter tatica proibida ({termo!r})",
                )


if __name__ == "__main__":
    unittest.main()
