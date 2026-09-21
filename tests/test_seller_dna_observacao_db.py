"""
Testes de persistência do SellerDnaObservacao — Bloco 5 / Tarefa 5.1
(`docs/tasks-sales-reasoning-engine-completo.md`).

Persistência usa SQLite em memória (mesmo padrão de
tests/test_opportunity_memory.py) — nunca toca no banco real do
projeto.

Run:
    python -m unittest tests.test_seller_dna_observacao_db -v
"""

import unittest

from sqlmodel import SQLModel, Session, create_engine
from unittest.mock import patch

from api import database


class CriarSellerDnaObservacaoTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_criar_observacao_valida(self):
        criada = database.criar_seller_dna_observacao(
            seller_id="vendedor-1",
            meeting_id="m1",
            campo="opening_patterns",
            valor="Abre perguntando sobre a rotina do time.",
            evidence_quote="me conta como está sendo o dia a dia de vocês aí",
        )
        self.assertEqual(criada["seller_id"], "vendedor-1")
        self.assertEqual(criada["meeting_id"], "m1")
        self.assertEqual(criada["campo"], "opening_patterns")
        self.assertIsNotNone(criada["id"])
        self.assertIsNotNone(criada["created_at"])

    def test_campo_fora_do_vocabulario_levanta(self):
        with self.assertRaises(ValueError):
            database.criar_seller_dna_observacao(
                seller_id="vendedor-1", meeting_id="m1",
                campo="personalidade_geral", valor="x", evidence_quote="y",
            )

    def test_seller_id_vazio_levanta(self):
        with self.assertRaises(ValueError):
            database.criar_seller_dna_observacao(
                seller_id="", meeting_id="m1",
                campo="closing_patterns", valor="x", evidence_quote="y",
            )

    def test_evidence_quote_vazia_levanta(self):
        with self.assertRaises(ValueError):
            database.criar_seller_dna_observacao(
                seller_id="vendedor-1", meeting_id="m1",
                campo="closing_patterns", valor="x", evidence_quote="",
            )


class ListarSellerDnaObservacoesTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_lista_so_do_vendedor_pedido(self):
        database.criar_seller_dna_observacao(
            seller_id="vendedor-1", meeting_id="m1",
            campo="pricing_style", valor="Fala o preço só depois de reforçar o valor.",
            evidence_quote="antes de falar de valor, deixa eu recapitular o que a gente resolve",
        )
        database.criar_seller_dna_observacao(
            seller_id="vendedor-2", meeting_id="m2",
            campo="pricing_style", valor="Outro estilo qualquer.",
            evidence_quote="outra citação qualquer",
        )

        observacoes = database.listar_seller_dna_observacoes("vendedor-1")
        self.assertEqual(len(observacoes), 1)
        self.assertEqual(observacoes[0]["seller_id"], "vendedor-1")

    def test_vendedor_sem_observacao_retorna_lista_vazia(self):
        self.assertEqual(database.listar_seller_dna_observacoes("vendedor-fantasma"), [])

    def test_ordenado_da_mais_antiga_pra_mais_recente(self):
        database.criar_seller_dna_observacao(
            seller_id="vendedor-1", meeting_id="m1",
            campo="closing_patterns", valor="primeira", evidence_quote="q1",
        )
        database.criar_seller_dna_observacao(
            seller_id="vendedor-1", meeting_id="m2",
            campo="closing_patterns", valor="segunda", evidence_quote="q2",
        )

        observacoes = database.listar_seller_dna_observacoes("vendedor-1")
        self.assertEqual([o["valor"] for o in observacoes], ["primeira", "segunda"])
