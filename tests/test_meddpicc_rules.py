"""
Testes do Opportunity Qualification Engine — Fase 4 / Tarefa 4.1 do
"PROMPT MESTRE — SALE-IA V2".

Função pura (agent/meddpicc_rules.py), sem IA/banco. O prompt mestre
pede pelo menos 3 cenários com resultado esperado definido antes da
execução: oportunidade mal qualificada, intermediária e enterprise
avançada — os 3 abaixo, com os níveis exatos que `resumo_qualificacao()`
deve produzir.

Run:
    python -m unittest tests.test_meddpicc_rules -v
"""

import unittest

from agent.meddpicc_rules import (
    MEDDPICC_ITENS,
    STATUS_VALIDOS,
    calcular_qualificacao_meddpicc,
    itens_pendentes,
    resumo_qualificacao,
)


def _fato(item, status, confidence=0.8, evidence="evidencia generica"):
    return {"item": item, "status": status, "confidence": confidence, "evidence_quote": evidence}


class CalcularQualificacaoMeddpiccTest(unittest.TestCase):
    def test_sem_nenhum_fato_todos_unknown(self):
        estado = calcular_qualificacao_meddpicc([])
        self.assertEqual(set(estado.keys()), set(MEDDPICC_ITENS))
        for item in MEDDPICC_ITENS:
            self.assertEqual(estado[item], {"status": "UNKNOWN", "confidence": 0.0, "evidence": []})

    def test_fato_unico_preenche_item_correto(self):
        fatos = [_fato("champion", "CONFIRMED", 0.9, "o diretor de vendas topou puxar internamente")]
        estado = calcular_qualificacao_meddpicc(fatos)
        self.assertEqual(estado["champion"]["status"], "CONFIRMED")
        self.assertEqual(estado["champion"]["confidence"], 0.9)
        self.assertEqual(estado["champion"]["evidence"], ["o diretor de vendas topou puxar internamente"])
        # outros itens continuam intocados
        self.assertEqual(estado["metrics"]["status"], "UNKNOWN")

    def test_status_nunca_regride_com_multiplos_fatos(self):
        fatos = [
            _fato("economic_buyer", "CONFIRMED", 0.9, "o CFO aprovou o orcamento"),
            _fato("economic_buyer", "PARTIAL", 0.5, "falou que precisa checar com o CFO de novo"),
        ]
        estado = calcular_qualificacao_meddpicc(fatos)
        self.assertEqual(estado["economic_buyer"]["status"], "CONFIRMED")

    def test_evidence_acumula_todas_as_quotes_na_ordem(self):
        fatos = [
            _fato("metrics", "PARTIAL", 0.4, "mencionou que quer reduzir custo"),
            _fato("metrics", "CONFIRMED", 0.85, "confirmou meta de reduzir 20% do CAC"),
        ]
        estado = calcular_qualificacao_meddpicc(fatos)
        self.assertEqual(
            estado["metrics"]["evidence"],
            ["mencionou que quer reduzir custo", "confirmou meta de reduzir 20% do CAC"],
        )

    def test_confidence_usa_o_maior_valor_ja_visto(self):
        fatos = [
            _fato("champion", "PARTIAL", 0.3, "sinal fraco de patrocinio interno"),
            _fato("champion", "PARTIAL", 0.6, "sinal mais forte de patrocinio interno"),
        ]
        estado = calcular_qualificacao_meddpicc(fatos)
        self.assertEqual(estado["champion"]["confidence"], 0.6)

    def test_item_invalido_levanta(self):
        fatos = [_fato("orcamento", "CONFIRMED")]
        with self.assertRaises(ValueError):
            calcular_qualificacao_meddpicc(fatos)

    def test_status_invalido_levanta(self):
        fatos = [_fato("metrics", "TALVEZ")]
        with self.assertRaises(ValueError):
            calcular_qualificacao_meddpicc(fatos)

    def test_confidence_fora_do_intervalo_levanta(self):
        fatos = [_fato("metrics", "CONFIRMED", confidence=1.5)]
        with self.assertRaises(ValueError):
            calcular_qualificacao_meddpicc(fatos)

    def test_status_diferente_de_unknown_sem_evidencia_levanta(self):
        """Regra central: nenhum item pode avançar de UNKNOWN sem
        evidence_quote real — mesma disciplina de SalesEvent/SPIN."""
        fatos = [_fato("champion", "PARTIAL", evidence="")]
        with self.assertRaises(ValueError):
            calcular_qualificacao_meddpicc(fatos)


class ResumoQualificacaoTest(unittest.TestCase):
    def test_cenario_oportunidade_mal_qualificada(self):
        """Só 1 item com sinal (PARTIAL), os outros 7 intocados —
        resultado esperado definido antes da execução: nivel 'fraca'."""
        fatos = [_fato("identify_pain", "PARTIAL", 0.4, "cliente mencionou uma dor vaga")]
        estado = calcular_qualificacao_meddpicc(fatos)
        resumo = resumo_qualificacao(estado)

        self.assertEqual(resumo["nivel"], "fraca")
        self.assertEqual(resumo["contagem_por_status"]["CONFIRMED"], 0)
        self.assertEqual(resumo["contagem_por_status"]["UNKNOWN"], 7)

    def test_cenario_oportunidade_intermediaria(self):
        """3 itens CONFIRMED, 2 PARTIAL, 3 UNKNOWN — resultado esperado
        definido antes da execução: nivel 'intermediaria'."""
        fatos = [
            _fato("identify_pain", "CONFIRMED", 0.8, "dor confirmada: leads esquecidos"),
            _fato("metrics", "CONFIRMED", 0.75, "meta de reduzir CAC em 20%"),
            _fato("champion", "CONFIRMED", 0.7, "gerente comercial puxando internamente"),
            _fato("economic_buyer", "PARTIAL", 0.5, "citou que precisa aprovar com a diretoria"),
            _fato("decision_criteria", "PARTIAL", 0.4, "mencionou preco como criterio, sem detalhar"),
        ]
        estado = calcular_qualificacao_meddpicc(fatos)
        resumo = resumo_qualificacao(estado)

        self.assertEqual(resumo["nivel"], "intermediaria")
        self.assertEqual(resumo["contagem_por_status"]["CONFIRMED"], 3)
        self.assertEqual(resumo["contagem_por_status"]["PARTIAL"], 2)
        self.assertEqual(resumo["contagem_por_status"]["UNKNOWN"], 3)

    def test_cenario_oportunidade_enterprise_avancada(self):
        """Todos os 8 itens CONFIRMED — resultado esperado definido
        antes da execução: nivel 'avancada'."""
        fatos = [
            _fato("metrics", "CONFIRMED", 0.9, "meta de reduzir CAC em 20% confirmada em reuniao com o CFO"),
            _fato("economic_buyer", "CONFIRMED", 0.9, "CFO participou da ultima call e aprovou o orcamento"),
            _fato("decision_criteria", "CONFIRMED", 0.85, "criterios formais definidos em RFP interno"),
            _fato("decision_process", "CONFIRMED", 0.85, "processo de aprovacao em 3 etapas mapeado"),
            _fato("paper_process", "CONFIRMED", 0.8, "juridico ja revisou o contrato padrao"),
            _fato("identify_pain", "CONFIRMED", 0.9, "dor confirmada: leads esquecidos custando R$20k/mes"),
            _fato("champion", "CONFIRMED", 0.9, "VP de vendas e patrocinador ativo do projeto"),
            _fato("competition", "CONFIRMED", 0.8, "concorrente X descartado por falta de integracao"),
        ]
        estado = calcular_qualificacao_meddpicc(fatos)
        resumo = resumo_qualificacao(estado)

        self.assertEqual(resumo["nivel"], "avancada")
        self.assertEqual(resumo["contagem_por_status"]["CONFIRMED"], 8)
        self.assertEqual(itens_pendentes(estado), [])


class ItensPendentesTest(unittest.TestCase):
    def test_itens_pendentes_inclui_partial_e_unknown_na_ordem_do_prompt_mestre(self):
        fatos = [
            _fato("metrics", "CONFIRMED", 0.9, "meta confirmada"),
            _fato("champion", "PARTIAL", 0.4, "sinal fraco de patrocinio"),
        ]
        estado = calcular_qualificacao_meddpicc(fatos)
        pendentes = itens_pendentes(estado)

        self.assertNotIn("metrics", pendentes)
        self.assertEqual(pendentes, [item for item in MEDDPICC_ITENS if item != "metrics"])

    def test_status_validos_tem_as_3_categorias_do_prompt_mestre(self):
        self.assertEqual(STATUS_VALIDOS, frozenset({"UNKNOWN", "PARTIAL", "CONFIRMED"}))


if __name__ == "__main__":
    unittest.main()
