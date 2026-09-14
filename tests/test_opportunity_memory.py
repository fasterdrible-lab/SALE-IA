"""
Testes da Opportunity / OpportunityMemory — Fase 2 / Tarefa 2.1 do
"PROMPT MESTRE — SALE-IA V2" (evoluir Meeting Memory para Opportunity
Memory).

Persistência usa SQLite em memória (mesmo padrão de
tests/test_sales_event.py) — nunca toca no banco real do projeto.

Escopo desta tarefa: criar Opportunity + OpportunityMemory e a regra de
"nunca sobrescrever, registrar contradição" — não inclui o Opportunity
Graph (Tarefa 2.2, separada) nem qualquer extração automática de
conhecimento a partir de transcrição livre.

Run:
    python -m unittest tests.test_opportunity_memory -v
"""

import unittest
from datetime import datetime

from sqlmodel import SQLModel, Session, create_engine, select
from unittest.mock import patch

from agent.opportunity_memory_rules import (
    OPPORTUNITY_MEMORY_CATEGORIES,
    adicionar_insight,
    validar_status,
)
from api import database
from api.database import MeetingMemory


class ValidarStatusTest(unittest.TestCase):
    def test_status_validos_nao_levantam(self):
        for status in ("open", "won", "lost", "abandoned"):
            validar_status(status)

    def test_status_invalido_levanta(self):
        with self.assertRaises(ValueError):
            validar_status("qualificando")


class AdicionarInsightTest(unittest.TestCase):
    def test_primeiro_insight_nao_gera_contradicao(self):
        lista, contradicao = adicionar_insight(
            [], meeting_id="m1", valor="leads esquecidos", campo=None,
        )
        self.assertEqual(len(lista), 1)
        self.assertIsNone(contradicao)
        self.assertEqual(lista[0]["meeting_id"], "m1")
        self.assertEqual(lista[0]["valor"], "leads esquecidos")
        self.assertIsNone(lista[0]["contradiz"])

    def test_nao_muta_lista_original(self):
        original = []
        adicionar_insight(original, meeting_id="m1", valor="x")
        self.assertEqual(original, [])  # a lista passada nunca é alterada in-place

    def test_mesmo_campo_mesmo_valor_nao_e_contradicao(self):
        lista, _ = adicionar_insight([], meeting_id="m1", valor="R$5000/mes", campo="orcamento_mensal")
        lista, contradicao = adicionar_insight(lista, meeting_id="m2", valor="R$5000/mes", campo="orcamento_mensal")
        self.assertIsNone(contradicao)
        self.assertEqual(len(lista), 2)

    def test_mesmo_campo_valor_diferente_registra_contradicao_sem_apagar_nada(self):
        """Regra central da Tarefa 2.1: informações históricas não
        desaparecem; contradições são registradas e não silenciosamente
        sobrescritas."""
        lista, _ = adicionar_insight(
            [], meeting_id="m1", valor="R$5000/mes", campo="orcamento_mensal",
        )
        lista, contradicao = adicionar_insight(
            lista, meeting_id="m2", valor="R$8000/mes", campo="orcamento_mensal",
        )

        self.assertIsNotNone(contradicao)
        self.assertEqual(contradicao["valor"], "R$5000/mes")
        self.assertEqual(len(lista), 2)  # a entrada antiga continua na lista, nao foi removida
        self.assertEqual(lista[0]["valor"], "R$5000/mes")
        self.assertEqual(lista[1]["valor"], "R$8000/mes")
        self.assertEqual(lista[1]["contradiz"], lista[0]["id"])

    def test_campos_diferentes_nunca_contradizem(self):
        lista, _ = adicionar_insight([], meeting_id="m1", valor="Joao", campo="champion")
        lista, contradicao = adicionar_insight(lista, meeting_id="m1", valor="Maria", campo="economic_buyer")
        self.assertIsNone(contradicao)
        self.assertEqual(len(lista), 2)

    def test_sem_meeting_id_levanta(self):
        with self.assertRaises(ValueError):
            adicionar_insight([], meeting_id="", valor="x")

    def test_confidence_fora_de_0_1_levanta(self):
        with self.assertRaises(ValueError):
            adicionar_insight([], meeting_id="m1", valor="x", confidence=1.5)

    def test_todas_as_13_categorias_existem(self):
        self.assertEqual(len(OPPORTUNITY_MEMORY_CATEGORIES), 13)


class OpportunityPersistenciaTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def _criar_meeting(self, meeting_id: str):
        with Session(self._engine) as session:
            session.add(MeetingMemory(
                meeting_id=meeting_id,
                transcript_full=f"transcricao de {meeting_id}",
            ))
            session.commit()

    def test_criar_e_obter_opportunity(self):
        criada = database.criar_opportunity(client_id="cliente-1", seller_id="vendedor-1", stage="descoberta")
        self.assertEqual(criada["status"], "open")
        self.assertIsNone(criada["won_at"])

        lida = database.obter_opportunity(criada["id"])
        self.assertEqual(lida["client_id"], "cliente-1")
        self.assertEqual(lida["stage"], "descoberta")

    def test_atualizar_status_status_invalido_levanta(self):
        opp = database.criar_opportunity(client_id="c1", seller_id="s1")
        with self.assertRaises(ValueError):
            database.atualizar_status_opportunity(opp["id"], "qualificando")

    def test_atualizar_status_won_grava_won_at_uma_vez(self):
        opp = database.criar_opportunity(client_id="c1", seller_id="s1")
        atualizada = database.atualizar_status_opportunity(
            opp["id"], "won", value=1000.0, product="SALEIA Enterprise", close_date=datetime.now(),
        )
        self.assertEqual(atualizada["status"], "won")
        self.assertIsNotNone(atualizada["won_at"])
        primeiro_won_at = atualizada["won_at"]

        # segunda chamada não precisa repassar value/product/close_date —
        # won_at já gravado, validação (e sobrescrita) não roda de novo
        atualizada2 = database.atualizar_status_opportunity(opp["id"], "won")
        self.assertEqual(atualizada2["won_at"], primeiro_won_at)  # nunca sobrescreve

    def test_atualizar_status_lost_grava_loss_reason(self):
        opp = database.criar_opportunity(client_id="c1", seller_id="s1")
        atualizada = database.atualizar_status_opportunity(opp["id"], "lost", loss_reason="Sem orcamento")
        self.assertEqual(atualizada["status"], "lost")
        self.assertEqual(atualizada["loss_reason"], "Sem orcamento")
        self.assertIsNotNone(atualizada["lost_at"])

    def test_atualizar_status_won_exige_value_product_close_date(self):
        """Fase 8 / Tarefa 8.1 — Outcome Tracking."""
        opp = database.criar_opportunity(client_id="c1", seller_id="s1")
        with self.assertRaises(ValueError):
            database.atualizar_status_opportunity(opp["id"], "won")  # sem value/product

    def test_atualizar_status_won_grava_outcome_value_product_e_cycle_days(self):
        opp = database.criar_opportunity(client_id="c1", seller_id="s1")
        with Session(self._engine) as session:
            row = session.get(database.Opportunity, opp["id"])
            row.created_at = datetime(2026, 1, 1)
            session.add(row)
            session.commit()

        atualizada = database.atualizar_status_opportunity(
            opp["id"], "won",
            value=25000.0, product="SALEIA Enterprise", close_date=datetime(2026, 1, 21),
        )
        self.assertEqual(atualizada["status"], "won")
        self.assertEqual(atualizada["outcome_value"], 25000.0)
        self.assertEqual(atualizada["product"], "SALEIA Enterprise")
        self.assertEqual(atualizada["cycle_days"], 20)

    def test_atualizar_status_lost_exige_reason(self):
        opp = database.criar_opportunity(client_id="c1", seller_id="s1")
        with self.assertRaises(ValueError):
            database.atualizar_status_opportunity(opp["id"], "lost")  # sem loss_reason

    def test_atualizar_status_lost_grava_competitor_opcional(self):
        opp = database.criar_opportunity(client_id="c1", seller_id="s1")
        atualizada = database.atualizar_status_opportunity(
            opp["id"], "lost", loss_reason="Preco alto", competitor="ConcorrenteX",
        )
        self.assertEqual(atualizada["competitor"], "ConcorrenteX")

        opp2 = database.criar_opportunity(client_id="c1", seller_id="s1")
        atualizada2 = database.atualizar_status_opportunity(opp2["id"], "lost", loss_reason="Projeto cancelado")
        self.assertIsNone(atualizada2["competitor"])

    def test_atualizar_status_abandoned_nao_exige_dados_extras(self):
        opp = database.criar_opportunity(client_id="c1", seller_id="s1")
        atualizada = database.atualizar_status_opportunity(opp["id"], "abandoned")
        self.assertEqual(atualizada["status"], "abandoned")

    def test_oportunidade_fechada_nao_aparece_como_aberta_em_estatisticas(self):
        """Regra de teste literal da Tarefa 8.1."""
        database.criar_opportunity(client_id="c1", seller_id="s1")
        opp2 = database.criar_opportunity(client_id="c1", seller_id="s1")
        opp3 = database.criar_opportunity(client_id="c1", seller_id="s1")
        database.atualizar_status_opportunity(opp2["id"], "won", value=1000, product="X", close_date=datetime.now())
        database.atualizar_status_opportunity(opp3["id"], "abandoned")

        from agent.outcome_rules import resumo_por_status

        todas = database.listar_opportunities(client_id="c1")
        resumo = resumo_por_status(todas)
        self.assertEqual(resumo["abertas"], 1)
        self.assertEqual(resumo["fechadas"], 2)

        abertas_filtradas = database.listar_opportunities(client_id="c1", status="open")
        self.assertEqual(len(abertas_filtradas), 1)

    def test_listar_opportunities_filtra_por_client_e_status(self):
        database.criar_opportunity(client_id="c1", seller_id="s1")
        opp2 = database.criar_opportunity(client_id="c1", seller_id="s1")
        database.criar_opportunity(client_id="c2", seller_id="s1")
        database.atualizar_status_opportunity(
            opp2["id"], "won", value=1000.0, product="SALEIA Enterprise", close_date=datetime.now(),
        )

        self.assertEqual(len(database.listar_opportunities(client_id="c1")), 2)
        self.assertEqual(len(database.listar_opportunities(status="won")), 1)
        self.assertEqual(len(database.listar_opportunities(client_id="c2")), 1)

    def test_vincular_meeting_a_opportunity_inexistente_retorna_false(self):
        self.assertFalse(database.vincular_meeting_opportunity("meeting-fantasma", 999))

    def test_criar_oportunidade_com_tres_reunioes(self):
        """Reproduz o teste literal da Tarefa 2.1: criar oportunidade com
        três reuniões e confirmar isolamento + agregação."""
        opp = database.criar_opportunity(client_id="cliente-x", seller_id="vendedor-y")

        for mid in ("reuniao-1", "reuniao-2", "reuniao-3"):
            self._criar_meeting(mid)
            self.assertTrue(database.vincular_meeting_opportunity(mid, opp["id"]))

        meetings = database.listar_meetings_da_opportunity(opp["id"])
        self.assertEqual(len(meetings), 3)
        self.assertEqual({m["meeting_id"] for m in meetings}, {"reuniao-1", "reuniao-2", "reuniao-3"})


class OpportunityMemoryPersistenciaTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.opp = database.criar_opportunity(client_id="cliente-x", seller_id="vendedor-y")

    def test_categoria_invalida_levanta_e_nada_persiste(self):
        with self.assertRaises(ValueError):
            database.registrar_conhecimento_opportunity(
                self.opp["id"], "categoria_inexistente", meeting_id="m1", valor="x",
            )
        memoria = database.obter_opportunity_memory(self.opp["id"])
        self.assertEqual(memoria["pain_points"], [])

    def test_obter_opportunity_memory_cria_vazia_se_ausente(self):
        memoria = database.obter_opportunity_memory(self.opp["id"])
        self.assertEqual(memoria["opportunity_id"], self.opp["id"])
        for categoria in OPPORTUNITY_MEMORY_CATEGORIES:
            self.assertEqual(memoria[categoria], [])

    def test_registrar_conhecimento_agrega_entre_reunioes_sem_perder_historico(self):
        """Meeting Memory permanece isolada; Opportunity Memory agrega
        conhecimento; informações históricas não desaparecem."""
        database.registrar_conhecimento_opportunity(
            self.opp["id"], "pain_points", meeting_id="reuniao-1",
            valor="leads esquecidos", evidence="Perdemos muitos leads",
        )
        database.registrar_conhecimento_opportunity(
            self.opp["id"], "business_impact", meeting_id="reuniao-2",
            valor="R$20.000/mes", campo="impacto_mensal",
        )
        database.registrar_conhecimento_opportunity(
            self.opp["id"], "pain_points", meeting_id="reuniao-3",
            valor="processo manual demorado",
        )

        memoria = database.obter_opportunity_memory(self.opp["id"])
        self.assertEqual(len(memoria["pain_points"]), 2)
        self.assertEqual(memoria["pain_points"][0]["meeting_id"], "reuniao-1")
        self.assertEqual(memoria["pain_points"][1]["meeting_id"], "reuniao-3")
        self.assertEqual(memoria["business_impact"][0]["valor"], "R$20.000/mes")

    def test_contradicao_entre_reunioes_fica_registrada_nao_sobrescrita(self):
        r1 = database.registrar_conhecimento_opportunity(
            self.opp["id"], "champion", meeting_id="reuniao-1",
            valor="Joao (TI)", campo="nome_champion",
        )
        self.assertIsNone(r1["contradicao"])

        r2 = database.registrar_conhecimento_opportunity(
            self.opp["id"], "champion", meeting_id="reuniao-2",
            valor="Maria (Financeiro)", campo="nome_champion",
        )
        self.assertIsNotNone(r2["contradicao"])
        self.assertEqual(r2["contradicao"]["valor"], "Joao (TI)")

        memoria = database.obter_opportunity_memory(self.opp["id"])
        self.assertEqual(len(memoria["champion"]), 2)  # nenhuma entrada foi apagada
        valores = {c["valor"] for c in memoria["champion"]}
        self.assertEqual(valores, {"Joao (TI)", "Maria (Financeiro)"})

    def test_meeting_memory_permanece_isolada_da_agregacao(self):
        with Session(self._engine) as session:
            session.add(MeetingMemory(meeting_id="reuniao-1", transcript_full="fala da reuniao 1"))
            session.add(MeetingMemory(meeting_id="reuniao-2", transcript_full="fala da reuniao 2"))
            session.commit()

        database.vincular_meeting_opportunity("reuniao-1", self.opp["id"])
        database.vincular_meeting_opportunity("reuniao-2", self.opp["id"])
        database.registrar_conhecimento_opportunity(
            self.opp["id"], "goals", meeting_id="reuniao-1", valor="crescer 30% ao ano",
        )

        with Session(self._engine) as session:
            m1 = session.exec(select(MeetingMemory).where(MeetingMemory.meeting_id == "reuniao-1")).first()
            m2 = session.exec(select(MeetingMemory).where(MeetingMemory.meeting_id == "reuniao-2")).first()
        self.assertEqual(m1.transcript_full, "fala da reuniao 1")
        self.assertEqual(m2.transcript_full, "fala da reuniao 2")
        self.assertNotEqual(m1.transcript_full, m2.transcript_full)  # nunca mesclados


if __name__ == "__main__":
    unittest.main()
