"""
Testes do SPIN Coverage Engine — Fase 3 / Tarefa 3.1 do "PROMPT MESTRE
— SALE-IA V2".

Função pura (agent/spin_coverage_rules.py), sem IA/banco — os testes
usam fixtures de "diálogo já estruturado" (fatos com evidence_quote,
como o prompt mestre pede) com expected output manual, reproduzindo o
exemplo literal da Tarefa 3.1 (equipe/CRM conhecidos, custo financeiro/
impacto em conversão/valor da solução faltantes).

Run:
    python -m unittest tests.test_spin_coverage_rules -v
"""

import unittest

from agent.spin_coverage_rules import (
    SPIN_STAGES,
    calcular_cobertura_spin,
    estagio_atual,
    sugerir_proxima_pergunta,
)


def _fato(stage, campo, valor, evidence="evidencia generica"):
    return {"stage": stage, "campo": campo, "valor": valor, "evidence_quote": evidence}


class CalcularCoberturaSpinTest(unittest.TestCase):
    def test_exemplo_literal_do_prompt_mestre(self):
        """Reproduz o exemplo exato da Tarefa 3.1: Situation com 2
        fatos conhecidos, Problem com 1, Implication e Need Payoff
        totalmente faltantes."""
        fatos = [
            _fato("situation", "team_size", "12 vendedores", "temos 12 vendedores no time"),
            _fato("situation", "crm_tool", "HubSpot", "usamos o HubSpot pra tudo"),
            _fato("problem", "main_pain", "follow-up lento", "nosso follow-up e muito lento"),
        ]

        cobertura = calcular_cobertura_spin(fatos)

        self.assertEqual({f["campo"] for f in cobertura["situation"]["known"]}, {"team_size", "crm_tool"})
        self.assertEqual(cobertura["situation"]["missing"], [])

        self.assertEqual({f["campo"] for f in cobertura["problem"]["known"]}, {"main_pain"})
        self.assertEqual(cobertura["problem"]["missing"], [])

        self.assertEqual(cobertura["implication"]["known"], [])
        self.assertEqual(set(cobertura["implication"]["missing"]), {"financial_impact", "conversion_impact"})

        self.assertEqual(cobertura["need_payoff"]["known"], [])
        self.assertEqual(cobertura["need_payoff"]["missing"], ["solution_value"])

    def test_sem_nenhum_fato_tudo_faltante(self):
        cobertura = calcular_cobertura_spin([])
        for stage in SPIN_STAGES:
            self.assertEqual(cobertura[stage]["known"], [])
            self.assertTrue(len(cobertura[stage]["missing"]) > 0)

    def test_fato_sem_evidencia_levanta_regra_nao_inventar(self):
        """Regra central da Tarefa 3.1: não permitir que a IA (ou
        qualquer chamador) invente informação faltante — todo 'known'
        precisa de evidence_quote."""
        fatos = [_fato("situation", "team_size", "12 vendedores", evidence="")]
        with self.assertRaises(ValueError):
            calcular_cobertura_spin(fatos)

    def test_stage_invalido_levanta(self):
        fatos = [_fato("descoberta", "x", "y")]
        with self.assertRaises(ValueError):
            calcular_cobertura_spin(fatos)

    def test_fato_fora_do_checklist_ainda_conta_como_known(self):
        fatos = [_fato("situation", "orcamento_disponivel", "R$10.000")]
        cobertura = calcular_cobertura_spin(fatos)
        self.assertEqual({f["campo"] for f in cobertura["situation"]["known"]}, {"orcamento_disponivel"})
        # nao esperado no checklist padrao, entao continua faltando os 2 de sempre
        self.assertEqual(set(cobertura["situation"]["missing"]), {"team_size", "crm_tool"})

    def test_checklist_customizado_e_respeitado(self):
        checklist = {"situation": ["idioma_preferido"], "problem": [], "implication": [], "need_payoff": []}
        cobertura = calcular_cobertura_spin([], checklist=checklist)
        self.assertEqual(cobertura["situation"]["missing"], ["idioma_preferido"])
        self.assertEqual(cobertura["problem"]["missing"], [])


class EstagioAtualTest(unittest.TestCase):
    def test_estagio_correto_e_o_primeiro_com_pendencia(self):
        fatos = [
            _fato("situation", "team_size", "12"),
            _fato("situation", "crm_tool", "HubSpot"),
            _fato("problem", "main_pain", "follow-up lento"),
        ]
        cobertura = calcular_cobertura_spin(fatos)
        self.assertEqual(estagio_atual(cobertura), "implication")

    def test_estagio_situation_quando_nada_foi_coberto(self):
        cobertura = calcular_cobertura_spin([])
        self.assertEqual(estagio_atual(cobertura), "situation")

    def test_estagio_need_payoff_quando_tudo_coberto(self):
        fatos = [
            _fato("situation", "team_size", "12"),
            _fato("situation", "crm_tool", "HubSpot"),
            _fato("problem", "main_pain", "follow-up lento"),
            _fato("implication", "financial_impact", "R$20.000/mes"),
            _fato("implication", "conversion_impact", "queda de 15%"),
            _fato("need_payoff", "solution_value", "dobrar as vendas"),
        ]
        cobertura = calcular_cobertura_spin(fatos)
        self.assertEqual(estagio_atual(cobertura), "need_payoff")


class SugerirProximaPerguntaTest(unittest.TestCase):
    def test_pergunta_sugerida_bate_com_o_exemplo_do_prompt_mestre(self):
        fatos = [
            _fato("situation", "team_size", "12"),
            _fato("situation", "crm_tool", "HubSpot"),
            _fato("problem", "main_pain", "follow-up lento"),
        ]
        cobertura = calcular_cobertura_spin(fatos)
        sugestao = sugerir_proxima_pergunta(cobertura)

        self.assertEqual(sugestao["stage"], "implication")
        self.assertEqual(sugestao["campo"], "financial_impact")
        self.assertEqual(sugestao["pergunta"], "Quanto esse problema custa atualmente?")

    def test_pergunta_relacionada_ao_gap_detectado(self):
        """Regra da Tarefa 3.2 (usada aqui como checagem de consistencia
        da Tarefa 3.1): a pergunta recomendada precisa estar relacionada
        ao campo do gap, nunca a outro."""
        cobertura = calcular_cobertura_spin([], checklist={
            "situation": [], "problem": [], "implication": [], "need_payoff": ["solution_value"],
        })
        sugestao = sugerir_proxima_pergunta(cobertura)
        self.assertEqual(sugestao["campo"], "solution_value")
        self.assertIn("valeria", sugestao["pergunta"].lower())

    def test_campo_fora_do_dict_de_perguntas_usa_fallback(self):
        cobertura = calcular_cobertura_spin([], checklist={
            "situation": ["campo_nunca_visto"], "problem": [], "implication": [], "need_payoff": [],
        })
        sugestao = sugerir_proxima_pergunta(cobertura)
        self.assertIn("campo_nunca_visto", sugestao["pergunta"])

    def test_none_quando_cobertura_completa(self):
        checklist = {"situation": [], "problem": [], "implication": [], "need_payoff": []}
        cobertura = calcular_cobertura_spin([], checklist=checklist)
        self.assertIsNone(sugerir_proxima_pergunta(cobertura))


if __name__ == "__main__":
    unittest.main()
