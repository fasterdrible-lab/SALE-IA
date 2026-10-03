"""
Testes — Tarefa D2 (docs/tasks-prompt-mestre-v2-restante.md): definição
de alucinação crítica (`agent/critical_hallucination_rules.py`), medição
no runner do Golden Dataset e guarda no Piloto.

Run:
    python -m unittest tests.test_critical_hallucination -v
"""

import asyncio
import logging
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlmodel import SQLModel, create_engine

logging.disable(logging.CRITICAL)

from agent.critical_hallucination_rules import detectar_alucinacoes_criticas, taxa_alucinacao_critica
from agent.quality_monitoring_golden_runner import montar_relatorio_metricas
from agent.readiness_rules import medicoes_do_golden_dataset
from api import database

_FONTE = (
    'Cliente: "Hoje somos 8 vendedores e perdemos uns 20 mil por mês com lead esquecido. '
    'Quem assina é o Marcos, nosso CFO. O plano de R$ 1.500 ficou caro."'
)


def _saida(**campos):
    base = {"current_state": "x", "recommended_framework": "SPIN_IMPLICATION", "next_best_action": "y",
            "reason": "z", "confidence": 0.5, "hypotheses": [], "evidence": [], "missing_information": [],
            "avoid": [], "next_best_question": None}
    base.update(campos)
    return base


def _categorias(achados):
    return sorted({a["categoria"] for a in achados})


class DetectarTest(unittest.TestCase):
    def test_saida_fiel_a_fonte_nao_e_critica(self):
        saida = _saida(
            next_best_action="Pergunte ao Marcos como os 20 mil por mês afetam a meta do time.",
            reason="O cliente disse que perde 20 mil por mês e citou o plano de R$ 1.500.",
            evidence=["perdemos uns 20 mil por mês com lead esquecido"],
            hypotheses=["Com 8 vendedores, o controle manual falha."],
        )
        self.assertEqual(detectar_alucinacoes_criticas(saida, _FONTE), [])

    def test_numero_preco_ou_percentual_inventado(self):
        saida = _saida(
            next_best_action="Ofereça o plano de R$ 990 com 15% de desconto.",
            reason="Eles perdem 50 mil por mês e têm 120 leads parados.",
        )
        trechos = {a["trecho"] for a in detectar_alucinacoes_criticas(saida, _FONTE)}
        self.assertTrue({"R$ 990", "15%", "50 mil", "120"} <= trechos)

    def test_mil_e_milhar_sao_o_mesmo_numero(self):
        fonte = "Cliente: perdemos uns 20.000 por mês."
        self.assertEqual(detectar_alucinacoes_criticas(_saida(reason="Perdem 20 mil por mês."), fonte), [])

    def test_numeros_pequenos_nao_contam(self):
        self.assertEqual(detectar_alucinacoes_criticas(_saida(next_best_action="Faça 2 perguntas de implicação."), _FONTE), [])

    def test_promessa_de_resultado(self):
        saida = _saida(next_best_question="Posso te garantir que o retorno garantido vem em 3 meses, sem risco?")
        self.assertEqual(_categorias(detectar_alucinacoes_criticas(saida, _FONTE)), ["promessa_de_resultado"])

    def test_promessa_dita_pelo_proprio_cliente_nao_conta(self):
        fonte = 'Cliente: "Vocês dão garantia? Quero algo sem risco."'
        self.assertEqual(detectar_alucinacoes_criticas(_saida(reason="Ele quer algo sem risco."), fonte), [])

    def test_dado_do_cliente_inventado(self):
        saida = _saida(
            next_best_action="Confirme com a diretora Fernanda o envio para fernanda@acme.com ou (11) 98765-4321.",
        )
        trechos = {a["trecho"] for a in detectar_alucinacoes_criticas(saida, _FONTE)}
        self.assertTrue({"Fernanda", "fernanda@acme.com", "(11) 98765-4321"} <= trechos)

    def test_inicio_de_frase_e_rotulos_nao_sao_nomes(self):
        saida = _saida(next_best_action="Investigue o impacto. Depois, Pergunte sobre SPIN e o MEDDPICC do Cliente.")
        self.assertEqual(detectar_alucinacoes_criticas(saida, _FONTE), [])

    def test_fases_e_estagios_em_portugues_nao_sao_nomes(self):
        # V.1.4.162: 13/13 falsos positivos da 1ª rodada real do Golden Dataset.
        saida = _saida(
            reason="Pela regra da Fase 6.1, a objeção precisa de investigação; a Fase 4.2 pede o decisor.",
            current_state="Conversa na etapa de Situação, sem Problema nem Implicação mapeados.",
            next_best_action="Investigue a Necessidade antes do Fechamento e confirme o Comprador Econômico.",
        )
        self.assertEqual(detectar_alucinacoes_criticas(saida, _FONTE), [])

    def test_achado_traz_contexto_do_trecho(self):
        achado = detectar_alucinacoes_criticas(_saida(reason="Ele aceita o plano de R$ 990 agora."), _FONTE)[0]
        self.assertEqual(achado["trecho"], "R$ 990")
        self.assertIn("plano de R$ 990 agora", achado["contexto"])

    def test_avoid_fica_de_fora(self):
        self.assertEqual(detectar_alucinacoes_criticas(_saida(avoid=["Não ofereça 20% de desconto."]), _FONTE), [])

    def test_entrada_invalida(self):
        self.assertEqual(detectar_alucinacoes_criticas(None, _FONTE), [])
        self.assertEqual(detectar_alucinacoes_criticas({"next_best_action": 3}, ""), [])

    def test_taxa(self):
        self.assertEqual(taxa_alucinacao_critica(1, 40), 0.025)
        self.assertIsNone(taxa_alucinacao_critica(0, 0))


class MedicaoTest(unittest.TestCase):
    def _contagens(self, **extra):
        base = {"framework_corretos": 0, "framework_total": 0, "objecao_vp": 0, "objecao_fp": 0,
                "afirmacoes_com_evidencia": 9, "afirmacoes_sem_evidencia": 1, "erros": [], "total_cenarios": 40}
        base.update(extra)
        return base

    def test_relatorio_e_painel_usam_a_taxa_critica_real(self):
        casos = [{"cenario": "pricing-03", "achados": [{"categoria": "numero_inventado", "campo": "x", "trecho": "15%"}]}]
        relatorio = montar_relatorio_metricas(self._contagens(
            cenarios_avaliados=40, cenarios_com_alucinacao_critica=1, alucinacoes_criticas=casos,
        ))
        self.assertEqual(relatorio["critical_hallucination_rate"], 0.025)
        self.assertEqual(relatorio["alucinacoes_criticas"], casos)
        medicao = {m["criterio"]: m for m in medicoes_do_golden_dataset(relatorio)}["critical_hallucination"]
        self.assertEqual((medicao["valor"], medicao["origem"], medicao["amostra"]), (0.025, "real", 40))

    def test_relatorio_antigo_cai_no_proxy(self):
        relatorio = montar_relatorio_metricas(self._contagens())
        self.assertIsNone(relatorio["critical_hallucination_rate"])
        medicao = {m["criterio"]: m for m in medicoes_do_golden_dataset(relatorio)}["critical_hallucination"]
        self.assertEqual(medicao["origem"], "proxy")


class GuardaNoPilotoTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(engine)
        p = patch.object(database, "engine", engine)
        p.start()
        self.addCleanup(p.stop)

    def _rodar_piloto(self, saida_motor):
        import agent.multiagente.orquestrador as orq
        resultado = {"next_best_action": {"type": "question", "message": "Me conta mais?", "category": "x"}}
        patches = [
            patch.dict(os.environ, {
                "SALES_EVIDENCE_PERSIST_ENABLED": "false", "OPPORTUNITY_MEMORY_WRITE_ENABLED": "false",
                "OPPORTUNITY_GRAPH_WRITE_ENABLED": "false", "MEDDPICC_EXTRACTOR_ENABLED": "false",
                "SELLER_CONTEXT_ENABLED": "false", "SALES_EVENT_EXTRACTOR_ENABLED": "false",
            }),
            patch("agent.sales_reasoning_engine.raciocinar_async", new=AsyncMock(return_value=saida_motor)),
            patch("api.database.criar_shadow_mode_comparison", new=MagicMock(return_value=None)),
            patch("api.database.obter_ultimo_ai_usage_event", return_value=None),
            patch("agent.opportunity_link_rules.vincular_automaticamente_se_possivel", return_value=None),
            patch("agent.spin_extractor.extrair_spin_state_async", new=AsyncMock(return_value=None)),
            patch("agent.behavioral_signal_extractor.extrair_sinais_comportamentais_async", new=AsyncMock(return_value=[])),
            patch("agent.buyer_motivation_extractor.extrair_buyer_motivation_async", new=AsyncMock(return_value=None)),
        ]
        for p in patches:
            p.start()
        try:
            aplicado = asyncio.run(orq._aplicar_piloto_sales_reasoning(
                resultado, _FONTE, "", "", {}, {}, [], [], "", "s1", "m1",
            ))
        finally:
            for p in reversed(patches):
                p.stop()
        return resultado, aplicado

    def test_recomendacao_com_preco_inventado_nunca_chega_ao_vendedor(self):
        resultado, aplicado = self._rodar_piloto(_saida(next_best_action="Ofereça 30% de desconto hoje.",
                                                        next_best_question=None))
        self.assertFalse(aplicado)
        self.assertEqual(resultado["next_best_action"]["message"], "Me conta mais?")  # modelo atual mantido
        entrada = database.listar_audit_trail_entries(actor="critical_hallucination_guard")[0]
        self.assertEqual(entrada["result"], "recomendacao_do_modelo_atual_mantida")
        self.assertIn("30%", entrada["reason"])

    def test_recomendacao_fiel_e_aplicada(self):
        resultado, aplicado = self._rodar_piloto(_saida(
            next_best_action="Pergunte como os 20 mil por mês afetam a meta.", next_best_question=None,
        ))
        self.assertTrue(aplicado)
        self.assertEqual(database.listar_audit_trail_entries(actor="critical_hallucination_guard"), [])


if __name__ == "__main__":
    unittest.main()
