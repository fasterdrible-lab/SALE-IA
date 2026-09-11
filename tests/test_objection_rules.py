"""
Testes da Taxonomia de Objeções — Fase 6 / Tarefa 6.1 do "PROMPT MESTRE
— SALE-IA V2".

Função pura (agent/objection_rules.py), sem IA/banco. Regra central do
prompt mestre reproduzida literalmente: o caso "Está caro." não pode
resultar automaticamente em root_cause = PRICE, confidence 100% — o
sistema deve primeiro recomendar investigação.

Run:
    python -m unittest tests.test_objection_rules -v
"""

import unittest

from agent.objection_rules import (
    LIMIAR_CONFIANCA_MINIMA_ROOT_CAUSE,
    OBJECTION_TIPOS,
    precisa_investigar,
    registrar_objecao,
)


def _spoken(category, evidence_quote="evidencia generica"):
    return {"category": category, "evidence_quote": evidence_quote}


def _root(hypothesis, confidence=0.8, evidence_quote="evidencia da investigacao"):
    return {"hypothesis": hypothesis, "confidence": confidence, "evidence_quote": evidence_quote}


class TaxonomiaTest(unittest.TestCase):
    def test_taxonomia_tem_as_13_categorias_do_prompt_mestre(self):
        self.assertEqual(
            OBJECTION_TIPOS,
            frozenset({
                "PRICE", "VALUE", "BUDGET", "TIMING", "TRUST", "ADOPTION",
                "COMPETITOR", "AUTHORITY", "PRIORITY", "IMPLEMENTATION",
                "LEGAL", "PROCUREMENT", "SECURITY",
            }),
        )


class PrecisaInvestigarTest(unittest.TestCase):
    def test_exemplo_literal_do_prompt_mestre_esta_caro_nao_confirma_automaticamente(self):
        """'Está caro.' com hipotese de causa raiz identica (mesma
        categoria, mesma evidencia, confidence 100%) NAO pode ser aceita
        sem investigacao — regra central da Tarefa 6.1."""
        spoken = _spoken("PRICE", "Está caro.")
        root = _root("PRICE", confidence=1.0, evidence_quote="Está caro.")

        self.assertTrue(precisa_investigar(spoken, root))

    def test_sem_hipotese_de_causa_raiz_sempre_precisa_investigar(self):
        spoken = _spoken("PRICE", "Está caro.")
        self.assertTrue(precisa_investigar(spoken, None))

    def test_hipotese_com_confidence_abaixo_do_limiar_precisa_investigar(self):
        spoken = _spoken("PRICE", "Está caro.")
        root = _root("ADOPTION_RISK", confidence=LIMIAR_CONFIANCA_MINIMA_ROOT_CAUSE - 0.1)
        self.assertTrue(precisa_investigar(spoken, root))

    def test_exemplo_bom_do_prompt_mestre_spoken_price_root_adoption_risk(self):
        """Exemplo literal 'bom' do prompt mestre: spoken=PRICE,
        root=ADOPTION_RISK, com evidencia distinta de uma investigacao
        real — nao precisa de investigacao adicional."""
        spoken = _spoken("PRICE", "Está caro.")
        root = _root(
            "ADOPTION_RISK", confidence=0.75,
            evidence_quote="Perguntei o porque do preco incomodar e ele disse que teme a equipe nao adotar a ferramenta",
        )
        self.assertFalse(precisa_investigar(spoken, root))

    def test_categoria_diferente_da_falada_com_boa_confidence_nao_bloqueia(self):
        """A regra so forca investigacao quando a hipotese repete a
        MESMA categoria falada com a MESMA evidencia (espelhamento) —
        categoria diferente, mesmo reaproveitando a mesma citacao, ja
        e uma leitura distinta do spoken."""
        spoken = _spoken("PRICE", "Está caro.")
        root = _root("ADOPTION_RISK", confidence=0.9, evidence_quote="Está caro.")
        self.assertFalse(precisa_investigar(spoken, root))

    def test_mesma_categoria_com_evidencia_propria_nao_bloqueia(self):
        """Repetir a mesma categoria falada e valido quando ha evidencia
        PROPRIA de investigacao (nao a simples repeticao da fala)."""
        spoken = _spoken("PRICE", "Está caro.")
        root = _root(
            "PRICE", confidence=0.85,
            evidence_quote="Perguntei o quanto seria razoavel e ele confirmou que o valor em si e o problema, nao o ROI",
        )
        self.assertFalse(precisa_investigar(spoken, root))

    def test_spoken_invalido_levanta(self):
        with self.assertRaises(ValueError):
            precisa_investigar(_spoken("CARO_DEMAIS"), None)

    def test_spoken_sem_evidencia_levanta(self):
        spoken = {"category": "PRICE"}
        with self.assertRaises(ValueError):
            precisa_investigar(spoken, None)

    def test_root_cause_sem_hypothesis_levanta(self):
        spoken = _spoken("PRICE", "Está caro.")
        root = {"confidence": 0.8, "evidence_quote": "algo"}
        with self.assertRaises(ValueError):
            precisa_investigar(spoken, root)

    def test_root_cause_confidence_fora_do_intervalo_levanta(self):
        spoken = _spoken("PRICE", "Está caro.")
        root = _root("ADOPTION_RISK", confidence=1.5)
        with self.assertRaises(ValueError):
            precisa_investigar(spoken, root)

    def test_root_cause_sem_evidencia_levanta(self):
        spoken = _spoken("PRICE", "Está caro.")
        root = {"hypothesis": "ADOPTION_RISK", "confidence": 0.8}
        with self.assertRaises(ValueError):
            precisa_investigar(spoken, root)

    def test_root_cause_pode_usar_vocabulario_fora_da_taxonomia_de_spoken(self):
        """root_cause_hypothesis.hypothesis e vocabulario livre — nao
        precisa estar em OBJECTION_TIPOS (ex.: 'ADOPTION_RISK' nao esta
        nas 13 categorias de objection_spoken)."""
        spoken = _spoken("PRICE", "Está caro.")
        root = _root("ADOPTION_RISK", confidence=0.8, evidence_quote="investigacao real")
        self.assertNotIn("ADOPTION_RISK", OBJECTION_TIPOS)
        precisa_investigar(spoken, root)  # nao deve levantar


class RegistrarObjecaoTest(unittest.TestCase):
    def test_estrutura_completa_sem_hipotese(self):
        registro = registrar_objecao(_spoken("BUDGET", "nao temos verba esse trimestre"))
        self.assertEqual(registro["objection_spoken"]["category"], "BUDGET")
        self.assertIsNone(registro["root_cause_hypothesis"])
        self.assertTrue(registro["precisa_investigar"])

    def test_estrutura_completa_com_hipotese_investigada(self):
        spoken = _spoken("PRICE", "Está caro.")
        root = _root("ADOPTION_RISK", confidence=0.8, evidence_quote="investigacao real, distinta do spoken")
        registro = registrar_objecao(spoken, root)

        self.assertEqual(registro["objection_spoken"], spoken)
        self.assertEqual(registro["root_cause_hypothesis"], root)
        self.assertFalse(registro["precisa_investigar"])

    def test_spoken_e_root_sao_campos_sempre_separados(self):
        """Regra central: objection_spoken e root_cause_hypothesis nunca
        sao fundidos num campo so."""
        spoken = _spoken("TRUST", "nao confio em fornecedores novos")
        registro = registrar_objecao(spoken)
        self.assertIn("objection_spoken", registro)
        self.assertIn("root_cause_hypothesis", registro)
        self.assertNotEqual(set(registro.keys()), {"category"})


if __name__ == "__main__":
    unittest.main()
