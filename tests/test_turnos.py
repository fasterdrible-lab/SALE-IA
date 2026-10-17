"""
Testes — A8 (V.1.4.187 + ext 1.4.37): turnos temporizados por falante
(agent/turnos_rules.py, api/database.registrar_turnos/listar_turnos,
/tempo-real, Seller Coaching).

Run:
    python -m unittest tests.test_turnos -v
"""
import asyncio
import logging
import unittest
from unittest.mock import AsyncMock, patch

logging.disable(logging.CRITICAL)

from agent import turnos_rules as T  # noqa: E402

T0 = 1_760_000_000_000  # ms (out/2025)
QUEM = [
    {"nome_meet": "Você", "nome": "Pedro", "papel": "vendedor"},
    {"nome_meet": "fasterdrible", "nome": "Ana", "papel": "cliente"},
]


def turno(falante, ini_s, fim_s, texto=""):
    return {"falante": falante, "inicio_ms": T0 + int(ini_s * 1000), "fim_ms": T0 + int(fim_s * 1000), "texto": texto}


# Conversa conhecida. Conta à mão:
#   Pedro: 0-20 (20) + 25-40 (15) + 60-160 (100, pergunta aberta no fim
#          do bloco de 100 s = monólogo) = 135 s; perguntas: "Como...?"
#          (aberta), "Fechamos amanhã?" (fechada), "O que você acha?"
#          (aberta) = 3 (2 abertas, 1 fechada)
#   Ana:   20-25 (5) + 38-60 (22, começa antes de Pedro acabar em 40 →
#          1 interrupção) = 27 s
#   Não identificado: 160-170 — fora da conta
#   Total 162 s → vendedor 135/162 = 83,3%, cliente 16,7%
CONVERSA = [
    turno("Pedro", 0, 20, "Bom dia, Ana. Como vocês fazem o controle hoje?"),
    turno("Ana", 20, 25, "Na planilha."),
    turno("Pedro", 25, 40, "Entendi. Fechamos amanhã?"),
    turno("Ana", 38, 60, "Calma, ainda preciso ver com o financeiro."),
    turno("Pedro", 60, 160, "Deixa eu te mostrar tudo... O que você acha?"),
    turno("Não identificado", 160, 170, "barulho"),
]


class NormalizarTurnosTest(unittest.TestCase):
    def test_descarta_invalidos(self):
        entrada = [
            {"falante": "  Ana  ", "inicio_ms": T0, "fim_ms": T0 + 1000, "texto": "oi"},
            {"falante": "", "inicio_ms": T0, "fim_ms": T0 + 1000},              # sem falante
            {"falante": "Ana", "inicio_ms": T0 + 5000, "fim_ms": T0},            # fim < início
            {"falante": "Ana", "inicio_ms": 1000, "fim_ms": 2000},               # relógio absurdo
            {"falante": "Ana", "inicio_ms": T0, "fim_ms": T0 + 11 * 60 * 1000},  # > 10 min
            {"falante": "Ana", "inicio_ms": "x", "fim_ms": T0},
            "lixo",
        ]
        self.assertEqual(T.normalizar_turnos(entrada),
                         [{"falante": "Ana", "inicio_ms": T0, "fim_ms": T0 + 1000, "texto": "oi"}])
        self.assertEqual(T.normalizar_turnos(None), [])


class PapelTest(unittest.TestCase):
    def test_papel_informado_vale(self):
        self.assertEqual(T.papel_do_falante(QUEM, "pedro"), ("vendedor", False))
        self.assertEqual(T.papel_do_falante(QUEM, "Ana"), ("cliente", False))

    def test_com_cliente_marcado_desconhecido_fica_fora(self):
        self.assertEqual(T.papel_do_falante(QUEM, "Zé"), ("", False))

    def test_sem_cliente_marcado_quem_nao_e_vendedor_e_cliente_inferido(self):
        so_vendedor = [{"nome_meet": "Você", "nome": "Pedro", "papel": "vendedor"}]
        self.assertEqual(T.papel_do_falante(so_vendedor, "motomec 17 GB"), ("cliente", True))

    def test_outro_e_nao_identificado_ficam_fora(self):
        lista = QUEM + [{"nome_meet": "x", "nome": "Gerente", "papel": "outro"}]
        self.assertEqual(T.papel_do_falante(lista, "Gerente"), ("", False))
        self.assertEqual(T.papel_do_falante(QUEM, "Não identificado"), ("", False))


class PerguntasTest(unittest.TestCase):
    def test_cada_frase_com_interrogacao_conta(self):
        self.assertEqual(T.perguntas_do_texto("Bom dia, Ana. Como vocês fazem hoje? E o prazo? Ok."),
                         ["Como vocês fazem hoje?", "E o prazo?"])
        self.assertEqual(T.perguntas_do_texto("sem pergunta."), [])
        self.assertEqual(T.perguntas_do_texto(""), [])


class MetricasReuniaoTest(unittest.TestCase):
    def test_conversa_conhecida_bate_com_a_conta_manual(self):
        m = T.metricas_da_reuniao(CONVERSA, QUEM)
        self.assertTrue(m["disponivel"])
        self.assertEqual((m["tempo_vendedor_s"], m["tempo_cliente_s"]), (135.0, 27.0))
        self.assertAlmostEqual(m["seller_talk_ratio"], 135 / 162)
        self.assertAlmostEqual(m["customer_talk_ratio"], 27 / 162)
        self.assertEqual((m["questions_total"], m["open_questions"], m["closed_questions"]), (3, 2, 1))
        self.assertEqual(m["interruptions"], 1)
        self.assertEqual(m["monologues"], 1)
        self.assertEqual(m["turnos"], 6)
        self.assertFalse(m["papeis_inferidos"])

    def test_sem_vendedor_nem_cliente_nao_disponivel(self):
        m = T.metricas_da_reuniao([turno("Não identificado", 0, 10)], QUEM)
        self.assertFalse(m["disponivel"])
        self.assertTrue(m["motivo"])
        self.assertFalse(T.metricas_da_reuniao([], QUEM)["disponivel"])

    def test_agregado_do_vendedor_pondera_pelo_tempo(self):
        a = T.metricas_da_reuniao(CONVERSA, QUEM)                        # 135 × 27
        b = T.metricas_da_reuniao([turno("Pedro", 0, 10, "Tudo bem?"),  # 10 × 90
                                   turno("Ana", 10, 100)], QUEM)
        g = T.agregar_vendedor([a, b, {"disponivel": False}])
        self.assertEqual(g["reunioes"], 2)
        self.assertAlmostEqual(g["seller_talk_ratio"], 145 / 262)
        self.assertEqual((g["questions_total"], g["open_questions"], g["closed_questions"]), (4, 2, 2))
        self.assertAlmostEqual(g["open_question_rate"], 0.5)
        self.assertEqual(T.agregar_vendedor([]), {})


class BancoTurnosTest(unittest.TestCase):
    def setUp(self):
        # SQLite em memória isolado — nunca toca no banco real.
        from sqlmodel import SQLModel, create_engine
        from api import database
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        p = patch.object(database, "engine", self._engine)
        p.start()
        self.addCleanup(p.stop)

    def test_grava_le_e_nao_duplica_no_reenvio(self):
        from api.database import listar_turnos, registrar_turnos
        mid = "teste-a8-turnos"
        turnos = T.normalizar_turnos(CONVERSA[:2])
        self.assertEqual(registrar_turnos(mid, turnos), 2)
        self.assertEqual(registrar_turnos(mid, turnos), 0)  # mesmo delta reenviado
        lidos = listar_turnos(mid)
        self.assertEqual([t["falante"] for t in lidos], ["Pedro", "Ana"])
        self.assertEqual(registrar_turnos("default", turnos), 0)


class TempoRealTurnosTest(unittest.TestCase):
    def test_turnos_validos_vao_para_o_banco(self):
        import api.main as m
        req = m.TempoRealRequest(transcricao_parcial="Ana: oi", meeting_id="m1",
                                 turnos_novos=[*CONVERSA[:2], {"falante": "", "inicio_ms": 1}])
        with patch("api.processador_tempo_real.processar_fragmento_tempo_real",
                   new=AsyncMock(return_value={"next_best_action": {}})), \
             patch("agent.sessao_manager.salvar_transcricao_bruta"), \
             patch("agent.sessao_manager.salvar_analise"), \
             patch("api.database.registrar_turnos") as reg:
            asyncio.run(m.analisar_tempo_real(req, authorization=None))
        mid, turnos = reg.call_args.args
        self.assertEqual((mid, [t["falante"] for t in turnos]), ("m1", ["Pedro", "Ana"]))

    def test_extensao_antiga_sem_turnos(self):
        import api.main as m
        req = m.TempoRealRequest(transcricao_parcial="Ana: oi", meeting_id="m1")
        with patch("api.processador_tempo_real.processar_fragmento_tempo_real",
                   new=AsyncMock(return_value={"next_best_action": {}})), \
             patch("agent.sessao_manager.salvar_transcricao_bruta"), \
             patch("agent.sessao_manager.salvar_analise"), \
             patch("api.database.registrar_turnos") as reg:
            asyncio.run(m.analisar_tempo_real(req, authorization=None))
        reg.assert_not_called()


class SellerCoachingTest(unittest.TestCase):
    def test_com_dado_talk_ratio_e_question_quality_saem_do_gap(self):
        from agent.seller_coaching_rules import montar_seller_coaching
        g = T.agregar_vendedor([T.metricas_da_reuniao(CONVERSA, QUEM)])
        g["dias"] = 30
        r = montar_seller_coaching("s1", g)
        self.assertTrue(r["talk_ratio"]["disponivel"])
        self.assertAlmostEqual(r["talk_ratio"]["seller_talk_ratio"], 135 / 162)
        self.assertTrue(r["question_quality"]["disponivel"])
        self.assertEqual(r["question_quality"]["open_questions"], 2)
        self.assertFalse(r["next_step_discipline"]["disponivel"])  # continua gap

    def test_sem_dado_continua_gap(self):
        from agent.seller_coaching_rules import montar_seller_coaching
        r = montar_seller_coaching("s1", {})
        self.assertFalse(r["talk_ratio"]["disponivel"])
        self.assertFalse(r["question_quality"]["disponivel"])


if __name__ == "__main__":
    unittest.main()
