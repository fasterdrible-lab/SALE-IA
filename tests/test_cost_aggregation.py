"""
Testes das agregacoes de custo de IA (Cost Intelligence Fase 2):
custos_resumo, custos_por_usuario, custos_reunioes_mais_caras,
eventos_de_reuniao, exportar_eventos_uso_ia.

Usa engine SQLite em memoria isolado por teste — nunca toca no banco real
do projeto. Mesmo harness de tests/test_ai_usage_events.py.

Run:
    python -m unittest tests.test_cost_aggregation -v
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlmodel import SQLModel, create_engine

from api import database


class CostAggregationTest(unittest.TestCase):
    def setUp(self):
        self._engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self._engine)
        self._patch = patch.object(database, "engine", self._engine)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def _evento(self, **overrides):
        base = dict(
            feature="realtime.coach", provider="deepseek", model="deepseek-chat",
            input_tokens=100, output_tokens=50, usage_source="provider",
            cost_usd=0.01, success=True, fallback_used=False,
            meeting_id="m1", usuario_id="user-1",
        )
        base.update(overrides)
        database.registrar_evento_uso_ia(**base)

    # ── custos_resumo ──────────────────────────

    def test_resumo_totais_gerais(self):
        self._evento(cost_usd=0.01, success=True, fallback_used=False)
        self._evento(cost_usd=0.02, success=False, fallback_used=True, provider="openai")

        r = database.custos_resumo()
        self.assertEqual(r["total_eventos"], 2)
        self.assertAlmostEqual(r["total_usd"], 0.03, places=6)
        self.assertEqual(r["eventos_sucesso"], 1)
        self.assertEqual(r["eventos_falha"], 1)
        self.assertEqual(r["fallback_eventos"], 1)
        self.assertAlmostEqual(r["fallback_usd"], 0.02, places=6)

    def test_resumo_agrupa_por_provider_model_feature(self):
        self._evento(provider="deepseek", model="deepseek-chat", feature="realtime.coach", cost_usd=0.01)
        self._evento(provider="deepseek", model="deepseek-chat", feature="realtime.coach", cost_usd=0.01)
        self._evento(provider="openai", model="gpt-4o", feature="realtime.disc", cost_usd=0.05)

        r = database.custos_resumo()
        por_provider = {p["provider"]: p for p in r["por_provider"]}
        self.assertEqual(por_provider["deepseek"]["eventos"], 2)
        self.assertAlmostEqual(por_provider["deepseek"]["total_usd"], 0.02, places=6)
        self.assertEqual(por_provider["openai"]["eventos"], 1)
        # ordenado por total_usd desc
        self.assertEqual(r["por_provider"][0]["provider"], "openai")

        por_feature = {f["feature"]: f for f in r["por_feature"]}
        self.assertEqual(por_feature["realtime.coach"]["eventos"], 2)
        self.assertEqual(por_feature["realtime.disc"]["eventos"], 1)

        por_model = {(m["provider"], m["model"]): m for m in r["por_model"]}
        self.assertEqual(por_model[("deepseek", "deepseek-chat")]["eventos"], 2)

    def test_resumo_sem_eventos_nao_quebra(self):
        r = database.custos_resumo()
        self.assertEqual(r["total_eventos"], 0)
        self.assertEqual(r["total_usd"], 0.0)
        self.assertEqual(r["por_provider"], [])

    def test_resumo_filtro_de_data_inclusivo_de_exclusivo_ate(self):
        self._evento(cost_usd=0.10)  # criado_em = agora (default_factory=datetime.now)

        ontem = datetime.now() - timedelta(days=1)
        amanha = datetime.now() + timedelta(days=1)
        r_dentro = database.custos_resumo(date_from=ontem, date_to=amanha)
        self.assertEqual(r_dentro["total_eventos"], 1)

        # janela totalmente antes do evento
        dez_dias_atras = datetime.now() - timedelta(days=10)
        nove_dias_atras = datetime.now() - timedelta(days=9)
        r_fora = database.custos_resumo(date_from=dez_dias_atras, date_to=nove_dias_atras)
        self.assertEqual(r_fora["total_eventos"], 0)

    # ── custos_por_usuario ──────────────────────

    def test_por_usuario_agrupa_e_ordena(self):
        self._evento(usuario_id="user-1", cost_usd=0.01)
        self._evento(usuario_id="user-1", cost_usd=0.01)
        self._evento(usuario_id="user-2", cost_usd=0.50)
        self._evento(usuario_id=None, cost_usd=0.05)  # uso anonimo da extensao

        r = database.custos_por_usuario()
        self.assertEqual(len(r), 3)
        self.assertEqual(r[0]["usuario_id"], "user-2")  # maior custo primeiro
        anonimo = next(x for x in r if x["usuario_id"] is None)
        self.assertAlmostEqual(anonimo["total_usd"], 0.05, places=6)

    def test_por_usuario_respeita_limit(self):
        for i in range(5):
            self._evento(usuario_id=f"user-{i}", cost_usd=0.01 * (i + 1))
        r = database.custos_por_usuario(limit=2)
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0]["usuario_id"], "user-4")  # maior custo

    # ── custos_reunioes_mais_caras ──────────────

    def test_reunioes_mais_caras_ordena_por_custo_e_ignora_meeting_id_nulo(self):
        self._evento(meeting_id="m1", cost_usd=0.10)
        self._evento(meeting_id="m2", cost_usd=1.00)
        self._evento(meeting_id="m2", cost_usd=0.50)
        self._evento(meeting_id=None, cost_usd=99.0)  # sem meeting_id — fora da lista

        r = database.custos_reunioes_mais_caras()
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0]["meeting_id"], "m2")
        self.assertAlmostEqual(r[0]["total_usd"], 1.50, places=6)
        self.assertEqual(r[0]["eventos"], 2)
        self.assertIsNotNone(r[0]["inicio"])
        self.assertIsNotNone(r[0]["fim"])

    def test_reunioes_mais_caras_respeita_limit(self):
        for i in range(5):
            self._evento(meeting_id=f"meeting-{i}", cost_usd=0.01 * (i + 1))
        r = database.custos_reunioes_mais_caras(limit=2)
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0]["meeting_id"], "meeting-4")

    # ── eventos_de_reuniao ──────────────────────

    def test_eventos_de_reuniao_ordem_cronologica(self):
        self._evento(meeting_id="m1", feature="realtime.coach", cost_usd=0.01)
        self._evento(meeting_id="m1", feature="realtime.disc", cost_usd=0.02)
        self._evento(meeting_id="m2", feature="realtime.coach", cost_usd=99.0)

        eventos = database.eventos_de_reuniao("m1")
        self.assertEqual(len(eventos), 2)
        self.assertEqual(eventos[0]["feature"], "realtime.coach")
        self.assertEqual(eventos[1]["feature"], "realtime.disc")
        self.assertIn("criado_em", eventos[0])

    def test_eventos_de_reuniao_inexistente_retorna_lista_vazia(self):
        self.assertEqual(database.eventos_de_reuniao("nao-existe"), [])

    # ── exportar_eventos_uso_ia ─────────────────

    def test_exportar_respeita_limit(self):
        for i in range(5):
            self._evento(meeting_id=f"m{i}", cost_usd=0.01)
        linhas = database.exportar_eventos_uso_ia(limit=3)
        self.assertEqual(len(linhas), 3)

    def test_exportar_campos_completos(self):
        self._evento(meeting_id="m1", usuario_id="user-1", cost_usd=0.01)
        linhas = database.exportar_eventos_uso_ia()
        self.assertEqual(len(linhas), 1)
        linha = linhas[0]
        for campo in (
            "criado_em", "meeting_id", "usuario_id", "feature", "provider", "model",
            "input_tokens", "output_tokens", "cached_input_tokens", "usage_source",
            "cost_usd", "latency_ms", "success", "fallback_used",
        ):
            self.assertIn(campo, linha)


if __name__ == "__main__":
    unittest.main(verbosity=2)
