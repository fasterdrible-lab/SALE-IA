"""
Testes do Opportunity Graph — Fase 2 / Tarefa 2.2 do "PROMPT MESTRE —
SALE-IA V2" (relacionar os insights da OpportunityMemory, Tarefa 2.1,
num grafo lógico CLIENT -> PAIN/IMPACT/GOAL/OBJECTION/STAKEHOLDER/
COMPETITOR/DECISION/NEXT_STEP).

Persistência usa SQLite em memória (mesmo padrão de
tests/test_opportunity_memory.py) — nunca toca no banco real do
projeto. Diferente de agent/knowledge_graph.py (Sales Brain Fase 7.2,
grafo de navegação entre cliente/reunião/memória/playbook/skill,
raw-pymysql) — este é um grafo novo e separado, escopado por
opportunity_id, com evidence/confidence/source por aresta.

Run:
    python -m unittest tests.test_opportunity_graph -v
"""

import unittest

from sqlmodel import SQLModel, create_engine
from unittest.mock import patch

from agent.opportunity_graph_rules import NODE_TYPES, validar_aresta
from api import database


class ValidarArestaTest(unittest.TestCase):
    def _aresta_valida(self, **overrides):
        base = {
            "from_type": "PAIN", "from_id": "1", "to_type": "IMPACT", "to_id": "1",
            "relation": "causa", "evidence": "Achamos que os leads esquecidos custam caro",
            "confidence": 0.8,
        }
        base.update(overrides)
        return base

    def test_aresta_valida_nao_levanta(self):
        validar_aresta(self._aresta_valida())

    def test_from_type_invalido_levanta(self):
        with self.assertRaises(ValueError):
            validar_aresta(self._aresta_valida(from_type="NAO_EXISTE"))

    def test_to_type_invalido_levanta(self):
        with self.assertRaises(ValueError):
            validar_aresta(self._aresta_valida(to_type="NAO_EXISTE"))

    def test_from_id_vazio_levanta(self):
        with self.assertRaises(ValueError):
            validar_aresta(self._aresta_valida(from_id=""))

    def test_to_id_vazio_levanta(self):
        with self.assertRaises(ValueError):
            validar_aresta(self._aresta_valida(to_id=""))

    def test_relation_vazia_levanta(self):
        with self.assertRaises(ValueError):
            validar_aresta(self._aresta_valida(relation=""))

    def test_evidence_vazia_levanta(self):
        """Regra central da Tarefa 2.2: cada relação deve conter
        evidence — sem perder a origem."""
        with self.assertRaises(ValueError):
            validar_aresta(self._aresta_valida(evidence=""))

    def test_evidence_ausente_levanta(self):
        dados = self._aresta_valida()
        del dados["evidence"]
        with self.assertRaises(ValueError):
            validar_aresta(dados)

    def test_confidence_fora_de_0_1_levanta(self):
        with self.assertRaises(ValueError):
            validar_aresta(self._aresta_valida(confidence=1.5))
        with self.assertRaises(ValueError):
            validar_aresta(self._aresta_valida(confidence=-0.1))

    def test_todos_os_9_tipos_de_no_existem(self):
        self.assertEqual(len(NODE_TYPES), 9)
        for tipo in ("CLIENT", "PAIN", "IMPACT", "GOAL", "OBJECTION",
                     "STAKEHOLDER", "COMPETITOR", "DECISION", "NEXT_STEP"):
            self.assertIn(tipo, NODE_TYPES)


class OpportunityGraphPersistenciaTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.opp = database.criar_opportunity(client_id="cliente-x", seller_id="vendedor-y")

    def test_criar_aresta_invalida_nao_persiste_nada(self):
        with self.assertRaises(ValueError):
            database.criar_aresta_opportunity_graph(
                self.opp["id"], from_type="PAIN", from_id="1", to_type="IMPACT", to_id="1",
                relation="causa", evidence="",
            )
        self.assertEqual(database.listar_arestas_opportunity(self.opp["id"]), [])

    def test_criar_e_listar_aresta(self):
        criada = database.criar_aresta_opportunity_graph(
            self.opp["id"], from_type="PAIN", from_id="1", to_type="IMPACT", to_id="1",
            relation="causa", evidence="Leads esquecidos geram retrabalho", confidence=0.9,
        )
        self.assertIsNotNone(criada["id"])

        arestas = database.listar_arestas_opportunity(self.opp["id"])
        self.assertEqual(len(arestas), 1)
        self.assertEqual(arestas[0]["from_type"], "PAIN")
        self.assertEqual(arestas[0]["to_type"], "IMPACT")
        self.assertEqual(arestas[0]["relation"], "causa")
        self.assertEqual(arestas[0]["evidence"], "Leads esquecidos geram retrabalho")

    def test_listar_filtra_por_no_especifico(self):
        database.criar_aresta_opportunity_graph(
            self.opp["id"], from_type="PAIN", from_id="1", to_type="IMPACT", to_id="1",
            relation="causa", evidence="ev1",
        )
        database.criar_aresta_opportunity_graph(
            self.opp["id"], from_type="PAIN", from_id="1", to_type="OBJECTION", to_id="1",
            relation="gera", evidence="ev2",
        )
        database.criar_aresta_opportunity_graph(
            self.opp["id"], from_type="CLIENT", from_id="cliente-x", to_type="GOAL", to_id="1",
            relation="busca", evidence="ev3",
        )

        arestas_do_pain = database.listar_arestas_opportunity(self.opp["id"], node_type="PAIN", node_id="1")
        self.assertEqual(len(arestas_do_pain), 2)

        arestas_do_goal = database.listar_arestas_opportunity(self.opp["id"], node_type="GOAL", node_id="1")
        self.assertEqual(len(arestas_do_goal), 1)

    def test_arestas_isoladas_por_opportunity(self):
        outra_opp = database.criar_opportunity(client_id="cliente-z", seller_id="vendedor-y")
        database.criar_aresta_opportunity_graph(
            self.opp["id"], from_type="PAIN", from_id="1", to_type="IMPACT", to_id="1",
            relation="causa", evidence="ev1",
        )
        self.assertEqual(len(database.listar_arestas_opportunity(self.opp["id"])), 1)
        self.assertEqual(len(database.listar_arestas_opportunity(outra_opp["id"])), 0)

    def test_integracao_exemplo_do_prompt_mestre_dor_causa_impacto(self):
        """Reproduz literalmente o exemplo da Tarefa 2.2: reunião 1
        identifica dor=leads esquecidos, reunião 2 identifica
        impacto=R$20.000/mes, o grafo relaciona dor -> causa -> impacto
        sem perder a origem (evidence/meeting_id de cada insight
        continuam intactos em OpportunityMemory, e a aresta carrega sua
        própria evidence/source/confidence/timestamp)."""
        resultado_pain = database.registrar_conhecimento_opportunity(
            self.opp["id"], "pain_points", meeting_id="reuniao-1",
            valor="leads esquecidos", evidence="Perdemos muitos leads no funil",
        )
        insight_pain = resultado_pain["insights"][-1]

        resultado_impact = database.registrar_conhecimento_opportunity(
            self.opp["id"], "business_impact", meeting_id="reuniao-2",
            valor="R$20.000/mes", evidence="Estimamos uns 20 mil reais por mes de prejuizo",
        )
        insight_impact = resultado_impact["insights"][-1]

        aresta = database.criar_aresta_opportunity_graph(
            self.opp["id"],
            from_type="PAIN", from_id=insight_pain["id"],
            to_type="IMPACT", to_id=insight_impact["id"],
            relation="causa",
            evidence="Leads esquecidos (reuniao-1) geram o prejuizo mensal (reuniao-2)",
            confidence=0.85,
        )

        self.assertEqual(aresta["from_type"], "PAIN")
        self.assertEqual(aresta["to_type"], "IMPACT")
        self.assertEqual(aresta["relation"], "causa")
        self.assertTrue(aresta["evidence"])

        # a origem de cada insight (meeting_id/evidence) nao se perde
        memoria = database.obter_opportunity_memory(self.opp["id"])
        self.assertEqual(memoria["pain_points"][0]["meeting_id"], "reuniao-1")
        self.assertEqual(memoria["business_impact"][0]["meeting_id"], "reuniao-2")

        arestas = database.listar_arestas_opportunity(
            self.opp["id"], node_type="PAIN", node_id=insight_pain["id"],
        )
        self.assertEqual(len(arestas), 1)
        self.assertEqual(arestas[0]["to_id"], str(insight_impact["id"]))


if __name__ == "__main__":
    unittest.main()
