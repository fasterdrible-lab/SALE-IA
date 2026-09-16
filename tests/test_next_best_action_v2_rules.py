# -*- coding: utf-8 -*-
"""
Testes do Next Best Action V2 — Fase 16 do "PROMPT MESTRE — SALE-IA
V2".

Função pura (agent/next_best_action_v2_rules.py), sem IA/banco.
Reproduz o exemplo literal do prompt mestre (quantificar impacto
financeiro, gap SPIN Implication, gap MEDDPICC Metrics, histórico com
evidência, confiança alta) e as 4 consistências exigidas ("fatos",
"estágio", "políticas", "conhecimento disponível").

Run:
    python -m unittest tests.test_next_best_action_v2_rules -v
"""

import unittest

from agent.meddpicc_rules import calcular_qualificacao_meddpicc
from agent.next_best_action_v2_rules import (
    NBA_V2_FONTES_COMBINADAS,
    NBA_V2_NIVEIS_CONFIANCA,
    NBA_V2_OUTPUT_CAMPOS,
    montar_next_best_action_v2,
)
from agent.spin_coverage_rules import calcular_cobertura_spin


def _spin_cobertura_exemplo():
    """Situation e Problem cobertos, Implication com os 2 campos
    ainda pendentes (financial_impact/conversion_impact) — mesmo
    cenário do exemplo literal do prompt mestre."""
    fatos = [
        {"stage": "situation", "campo": "team_size", "valor": "12", "evidence_quote": "somos 12 no time"},
        {"stage": "situation", "campo": "crm_tool", "valor": "planilha", "evidence_quote": "hoje usamos planilha"},
        {"stage": "problem", "campo": "main_pain", "valor": "leads esquecidos", "evidence_quote": "a gente esquece de retornar leads"},
    ]
    return calcular_cobertura_spin(fatos)


def _meddpicc_estado_exemplo():
    """metrics segue UNKNOWN (nenhum fato) — os outros 7 itens
    parcialmente preenchidos, mesmo cenário do exemplo literal."""
    fatos = [
        {"item": "economic_buyer", "status": "PARTIAL", "confidence": 0.6, "evidence_quote": "o diretor participou da call"},
    ]
    return calcular_qualificacao_meddpicc(fatos)


def _historico_insight_exemplo():
    return {
        "submodulo": "win_loss_analyzer",
        "insight": "oportunidades semelhantes avançaram mais quando o impacto foi quantificado antes do preço",
        "evidence": {"won": 40, "lost": 12},
        "sample": 52,
        "confidence": 0.95,
        "possible_confounders": ["segmento não controlado"],
        "recommended_test": "Rodar experimento controlado (Fase 14) antes de generalizar",
    }


class VocabularioTest(unittest.TestCase):
    def test_8_fontes_combinadas_literais_do_prompt_mestre(self):
        self.assertEqual(
            NBA_V2_FONTES_COMBINADAS,
            (
                "metodologia", "contexto", "historico", "sazonalidade",
                "cliente", "oportunidade", "seller_dna", "resultado_observado",
            ),
        )

    def test_8_campos_de_saida_literais_do_exemplo(self):
        self.assertEqual(
            NBA_V2_OUTPUT_CAMPOS,
            ("titulo", "por_que", "spin_gap", "meddpicc_gap", "historico", "confianca", "pergunta", "evite"),
        )

    def test_niveis_de_confianca(self):
        self.assertEqual(NBA_V2_NIVEIS_CONFIANCA, ("baixa", "media", "alta"))


class ExemploLiteralDoPromptMestreTest(unittest.TestCase):
    def test_recomendacao_completa_igual_ao_exemplo(self):
        nba = montar_next_best_action_v2(
            titulo="Quantifique o impacto financeiro.",
            por_que="O cliente reconheceu a dor, mas o impacto ainda não foi quantificado.",
            pergunta="Quanto esse problema representa hoje para vocês por mês?",
            evite="Apresentar preço agora.",
            spin_cobertura=_spin_cobertura_exemplo(),
            spin_gap_campo="financial_impact",
            meddpicc_estado=_meddpicc_estado_exemplo(),
            meddpicc_gap_item="metrics",
            historico_insight=_historico_insight_exemplo(),
            confianca="alta",
        )
        self.assertEqual(nba["titulo"], "Quantifique o impacto financeiro.")
        self.assertEqual(nba["spin_gap"], "financial_impact")
        self.assertEqual(nba["meddpicc_gap"], "metrics")
        self.assertEqual(
            nba["historico"],
            "oportunidades semelhantes avançaram mais quando o impacto foi quantificado antes do preço",
        )
        self.assertEqual(nba["confianca"], "alta")
        self.assertEqual(nba["pergunta"], "Quanto esse problema representa hoje para vocês por mês?")
        self.assertEqual(nba["evite"], "Apresentar preço agora.")


class CamposObrigatoriosTest(unittest.TestCase):
    def test_cada_campo_de_texto_obrigatorio(self):
        base = dict(
            titulo="t", por_que="p", pergunta="q", evite="e",
            spin_cobertura=_spin_cobertura_exemplo(), spin_gap_campo="financial_impact",
        )
        for campo in ("titulo", "por_que", "pergunta", "evite"):
            kwargs = dict(base)
            kwargs[campo] = ""
            with self.assertRaises(ValueError):
                montar_next_best_action_v2(**kwargs)

    def test_confianca_invalida_levanta(self):
        with self.assertRaises(ValueError):
            montar_next_best_action_v2(
                titulo="t", por_que="p", pergunta="q", evite="e",
                spin_cobertura=_spin_cobertura_exemplo(), spin_gap_campo="financial_impact",
                confianca="altissima",
            )


class ConsistenciaComFatosTest(unittest.TestCase):
    """Regra literal: consistência com 'fatos' — gaps precisam ser
    reais, nunca inventados."""

    def test_spin_gap_campo_inexistente_no_missing_levanta(self):
        with self.assertRaises(ValueError):
            montar_next_best_action_v2(
                titulo="t", por_que="p", pergunta="q", evite="e",
                spin_cobertura=_spin_cobertura_exemplo(),
                spin_gap_campo="campo_que_nao_existe",
            )

    def test_meddpicc_gap_item_ja_confirmed_levanta(self):
        estado = calcular_qualificacao_meddpicc([
            {"item": "metrics", "status": "CONFIRMED", "confidence": 0.9, "evidence_quote": "confirmado em call"},
        ])
        with self.assertRaises(ValueError):
            montar_next_best_action_v2(
                titulo="t", por_que="p", pergunta="q", evite="e",
                spin_cobertura=_spin_cobertura_exemplo(), spin_gap_campo="financial_impact",
                meddpicc_estado=estado, meddpicc_gap_item="metrics",
            )

    def test_meddpicc_gap_item_sem_meddpicc_estado_levanta(self):
        with self.assertRaises(ValueError):
            montar_next_best_action_v2(
                titulo="t", por_que="p", pergunta="q", evite="e",
                spin_cobertura=_spin_cobertura_exemplo(), spin_gap_campo="financial_impact",
                meddpicc_gap_item="metrics",
            )


class ConsistenciaComEstagioTest(unittest.TestCase):
    """Regra literal: consistência com 'estágio' — não pode pular um
    estágio SPIN ainda pendente."""

    def test_gap_de_estagio_futuro_enquanto_situation_pendente_levanta(self):
        # Nenhum fato de "situation" -> ainda pendente -> estagio_atual == "situation"
        cobertura = calcular_cobertura_spin([])
        with self.assertRaises(ValueError):
            montar_next_best_action_v2(
                titulo="t", por_que="p", pergunta="q", evite="e",
                spin_cobertura=cobertura, spin_gap_campo="financial_impact",  # e' de implication, nao de situation
            )

    def test_gap_do_estagio_atual_e_aceito(self):
        cobertura = calcular_cobertura_spin([])
        nba = montar_next_best_action_v2(
            titulo="t", por_que="p", pergunta="q", evite="e",
            spin_cobertura=cobertura, spin_gap_campo="team_size",
        )
        self.assertEqual(nba["spin_gap"], "team_size")


class ConsistenciaComPoliticasTest(unittest.TestCase):
    """Regra literal: consistência com 'políticas' — qualquer bloqueio
    ativo recusa a recomendação, fail-closed."""

    def test_bloqueio_ativo_recusa_recomendacao(self):
        with self.assertRaises(ValueError):
            montar_next_best_action_v2(
                titulo="t", por_que="p", pergunta="q", evite="e",
                spin_cobertura=_spin_cobertura_exemplo(), spin_gap_campo="financial_impact",
                bloqueios_politica=["objecao_de_preco_nao_investigada"],
            )

    def test_sem_bloqueio_passa(self):
        nba = montar_next_best_action_v2(
            titulo="t", por_que="p", pergunta="q", evite="e",
            spin_cobertura=_spin_cobertura_exemplo(), spin_gap_campo="financial_impact",
            bloqueios_politica=[],
        )
        self.assertEqual(nba["titulo"], "t")


class ConsistenciaComConhecimentoDisponivelTest(unittest.TestCase):
    """Regra literal: consistência com 'conhecimento disponível' —
    confiança alta exige histórico com evidência real."""

    def test_confianca_alta_sem_historico_insight_levanta(self):
        with self.assertRaises(ValueError):
            montar_next_best_action_v2(
                titulo="t", por_que="p", pergunta="q", evite="e",
                spin_cobertura=_spin_cobertura_exemplo(), spin_gap_campo="financial_impact",
                confianca="alta",
            )

    def test_confianca_media_sem_historico_insight_e_aceita(self):
        nba = montar_next_best_action_v2(
            titulo="t", por_que="p", pergunta="q", evite="e",
            spin_cobertura=_spin_cobertura_exemplo(), spin_gap_campo="financial_impact",
            confianca="media",
        )
        self.assertIsNone(nba["historico"])

    def test_historico_insight_sem_evidence_levanta(self):
        insight_incompleto = dict(_historico_insight_exemplo())
        insight_incompleto["evidence"] = {}
        with self.assertRaises(ValueError):
            montar_next_best_action_v2(
                titulo="t", por_que="p", pergunta="q", evite="e",
                spin_cobertura=_spin_cobertura_exemplo(), spin_gap_campo="financial_impact",
                confianca="alta", historico_insight=insight_incompleto,
            )

    def test_historico_insight_nao_dict_levanta(self):
        with self.assertRaises(ValueError):
            montar_next_best_action_v2(
                titulo="t", por_que="p", pergunta="q", evite="e",
                spin_cobertura=_spin_cobertura_exemplo(), spin_gap_campo="financial_impact",
                confianca="alta", historico_insight="nao e um dict",
            )


if __name__ == "__main__":
    unittest.main()
