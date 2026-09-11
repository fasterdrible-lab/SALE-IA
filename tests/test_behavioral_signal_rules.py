"""
Testes do Behavioral Signal Engine — Fase 5 / Tarefa 5.2 do "PROMPT
MESTRE — SALE-IA V2".

Função pura (agent/behavioral_signal_rules.py), sem IA/banco. Regra
central do prompt mestre — "cada sinal precisa apresentar trecho da
conversa que o sustenta" — e a proibição de alegações pseudocientíficas
("o cérebro reptiliano foi ativado") testadas explicitamente.

Run:
    python -m unittest tests.test_behavioral_signal_rules -v
"""

import unittest

from agent.behavioral_signal_rules import (
    BEHAVIORAL_SIGNAL_TIPOS,
    DESCRICOES_SINAIS,
    contagem_por_sinal,
    detectar_sinais,
    validar_sinais_comportamentais,
)


def _sinal(signal, evidence_quote="evidencia generica"):
    return {"signal": signal, "evidence_quote": evidence_quote}


class ValidarSinaisComportamentaisTest(unittest.TestCase):
    def test_sinal_valido_nao_levanta(self):
        validar_sinais_comportamentais([_sinal("LOSS_AVERSION", "tenho medo de perder o que ja construi")])

    def test_lista_vazia_nao_levanta(self):
        validar_sinais_comportamentais([])

    def test_signal_invalido_levanta(self):
        with self.assertRaises(ValueError):
            validar_sinais_comportamentais([_sinal("MEDO_DE_MUDANCA")])

    def test_evidence_quote_ausente_levanta(self):
        """Regra central do prompt mestre: 'cada sinal precisa apresentar
        trecho da conversa que o sustenta' — sem evidencia, nao existe."""
        sinal = {"signal": "STATUS_QUO_BIAS"}
        with self.assertRaises(ValueError):
            validar_sinais_comportamentais([sinal])

    def test_evidence_quote_vazia_levanta(self):
        with self.assertRaises(ValueError):
            validar_sinais_comportamentais([_sinal("STATUS_QUO_BIAS", evidence_quote="")])

    def test_evidence_quote_so_espacos_levanta(self):
        with self.assertRaises(ValueError):
            validar_sinais_comportamentais([_sinal("STATUS_QUO_BIAS", evidence_quote="   ")])

    def test_taxonomia_tem_os_6_sinais_do_prompt_mestre(self):
        self.assertEqual(
            BEHAVIORAL_SIGNAL_TIPOS,
            frozenset({
                "LOSS_AVERSION", "STATUS_QUO_BIAS", "SOCIAL_PROOF_REQUEST",
                "AUTHORITY_REQUEST", "PRICE_ANCHOR", "RISK_AVERSION",
            }),
        )


class DetectarSinaisTest(unittest.TestCase):
    def test_cada_sinal_apresenta_o_trecho_que_o_sustenta(self):
        sinais = [
            _sinal("PRICE_ANCHOR", "o concorrente X cobra metade disso"),
            _sinal("SOCIAL_PROOF_REQUEST", "voces tem algum cliente do meu segmento usando?"),
        ]
        detectados = detectar_sinais(sinais)

        self.assertEqual(len(detectados), 2)
        for original, detectado in zip(sinais, detectados):
            self.assertEqual(detectado["signal"], original["signal"])
            self.assertEqual(detectado["evidence_quote"], original["evidence_quote"])
            self.assertTrue(detectado["evidence_quote"].strip())

    def test_descricao_e_sempre_a_canonica_do_tipo(self):
        detectados = detectar_sinais([_sinal("RISK_AVERSION", "prefiro nao arriscar mudar de fornecedor agora")])
        self.assertEqual(detectados[0]["descricao"], DESCRICOES_SINAIS["RISK_AVERSION"])

    def test_lista_vazia_retorna_lista_vazia(self):
        self.assertEqual(detectar_sinais([]), [])

    def test_sinal_invalido_propaga_erro(self):
        with self.assertRaises(ValueError):
            detectar_sinais([_sinal("CEREBRO_REPTILIANO_ATIVADO", "evidencia qualquer")])


class ContagemPorSinalTest(unittest.TestCase):
    def test_contagem_correta_por_tipo(self):
        sinais = [
            _sinal("LOSS_AVERSION", "nao quero perder o investimento ja feito"),
            _sinal("LOSS_AVERSION", "tenho medo de sair perdendo com a troca"),
            _sinal("AUTHORITY_REQUEST", "preciso que o time juridico valide isso"),
        ]
        contagem = contagem_por_sinal(sinais)
        self.assertEqual(contagem, {"LOSS_AVERSION": 2, "AUTHORITY_REQUEST": 1})

    def test_lista_vazia_retorna_dict_vazio(self):
        self.assertEqual(contagem_por_sinal([]), {})


class GuardaContraAlegacoesPseudocientificasTest(unittest.TestCase):
    """Regra explícita do prompt mestre: 'evitar alegações como o cérebro
    reptiliano foi ativado' — garantida verificando que nenhuma descrição
    canônica menciona mecanismo neurológico/evolutivo especulativo."""

    def test_nenhuma_descricao_usa_linguagem_pseudocientifica(self):
        termos_proibidos = [
            "cerebro reptiliano", "cérebro reptiliano", "cerebro primitivo",
            "instinto animal", "neurociencia", "neurocientífic", "amigdala", "amígdala",
        ]
        for tipo, descricao in DESCRICOES_SINAIS.items():
            descricao_normalizada = descricao.lower()
            for termo in termos_proibidos:
                self.assertNotIn(
                    termo, descricao_normalizada,
                    f"descricao de {tipo!r} nao deveria conter linguagem pseudocientifica ({termo!r})",
                )

    def test_todos_os_6_tipos_tem_descricao_canonica(self):
        self.assertEqual(set(DESCRICOES_SINAIS.keys()), BEHAVIORAL_SIGNAL_TIPOS)


if __name__ == "__main__":
    unittest.main()
