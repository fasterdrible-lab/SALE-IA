"""
Testes — V.1.4.196: envio da reunião analisada ao SalesOS (V2-7.2 do SalesOS).

Run:
    python -m unittest tests.test_salesos_envio -v
"""
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from agent import salesos_event_rules as r
from api import salesos_envio as svc

AGORA = datetime(2026, 11, 6, 18, 0, 0)
INICIO = datetime(2026, 11, 6, 14, 0, 0)
FIM = datetime(2026, 11, 6, 14, 52, 30)

RECAP = {
    "resumo_executivo": "Cliente quer organizar o comercial e pediu proposta.",
    "cliente_identificado": {"nome": "Ana Souza", "empresa": "Acme Ltda"},
    "recapitulacao_estrategica": {
        "dores_identificadas": ["Processo comercial manual", "Processo comercial manual"],
        "objecoes_levantadas": ["Preço acima do orçamento"],
    },
    "proximos_passos": [
        {"acao": "Enviar proposta revisada", "prazo": "sexta", "responsavel": "vendedor"},
        {"acao": "ação a ser tomada", "prazo": "quando", "responsavel": "vendedor|cliente"},
    ],
    "probabilidade_fechamento": "média",
    "justificativa_probabilidade": "Tem orçamento, falta o decisor.",
    "propensao": {
        "nivel": "media",
        "resumo": "Interesse claro, decisor ausente.",
        "fatores_positivos": [{"fator": "Pediu prazo de implantação", "evidencia": "Quanto tempo leva?"}],
        "fatores_negativos": [{"fator": "Decisor não participou", "evidencia": None}],
        "como_avancar": ["Agendar reunião com o diretor"],
    },
}
RELATORIO = {"titulo": "Reunião abc-defg-hij — 06/11/2026 14:00 UTC", "recapitulacao": RECAP}
PARTICIPANTES = [{"nome_meet": "Você", "nome": "Carlos", "papel": "vendedor"}, {"nome": "Ana Souza", "papel": "cliente"}]


def evento(**kw):
    base = dict(meeting_id="abc-defg-hij", titulo=RELATORIO["titulo"], inicio=INICIO, fim=FIM,
                participantes=PARTICIPANTES, relatorio=RELATORIO, agora=AGORA, event_id="ev-1")
    base.update(kw)
    return r.montar_evento(**base)


class AssinaturaTest(unittest.TestCase):
    def test_mesmo_hmac_do_salesos(self):
        # Vetor gerado por apps/web/lib/saleia/signature.ts (SalesOS).
        self.assertEqual(
            r.assinar("slia_vetor-de-teste", "1762430400", '{"reuniao":"ação"}'),
            "sha256=4735d6ddadc7eea96850567726cd8f200ce5c9cc601faaf4ce067e5afe5f0216",
        )

    def test_cabecalhos_usam_segundos_utc(self):
        # AGORA (sem fuso) é lido como UTC: 2026-11-06T18:00:00Z.
        h = r.cabecalhos("s", "{}", AGORA)
        self.assertEqual(h["X-Saleia-Timestamp"], "1793988000")
        self.assertEqual(h["X-Saleia-Signature"], r.assinar("s", "1793988000", "{}"))

    def test_configuracao_exige_url_https_e_segredo(self):
        self.assertIsNone(r.configuracao({}))
        self.assertIsNone(r.configuracao({"SALESOS_EVENTS_URL": "https://saleos.tech/x"}))
        self.assertIsNone(r.configuracao({"SALESOS_EVENTS_URL": "http://saleos.tech/x", "SALESOS_EVENTS_SECRET": "s"}))
        self.assertEqual(
            r.configuracao({"SALESOS_EVENTS_URL": " https://saleos.tech/x ", "SALESOS_EVENTS_SECRET": " s "}),
            ("https://saleos.tech/x", "s"),
        )
        self.assertIsNotNone(r.configuracao({"SALESOS_EVENTS_URL": "http://localhost:3100/x", "SALESOS_EVENTS_SECRET": "s"}))


class EventoTest(unittest.TestCase):
    def test_cabecalho_do_evento(self):
        e = evento()
        self.assertEqual((e["version"], e["event"], e["eventId"]), (1, "meeting.analyzed", "ev-1"))
        self.assertEqual(e["occurredAt"], "2026-11-06T18:00:00Z")
        self.assertEqual(e["meeting"]["externalId"], "abc-defg-hij")
        self.assertEqual(e["meeting"]["title"], "Reunião com Acme Ltda")
        self.assertEqual(e["meeting"]["startedAt"], "2026-11-06T14:00:00Z")
        self.assertEqual(e["meeting"]["durationMinutes"], 52)
        self.assertEqual(e["meeting"]["participants"], [{"name": "Carlos"}, {"name": "Ana Souza"}])
        self.assertEqual(e["links"], {"opportunityId": None, "companyName": "Acme Ltda"})

    def test_resumo_junta_propensao_e_probabilidade(self):
        resumo = evento()["meeting"]["summary"]
        self.assertTrue(resumo.startswith("Cliente quer organizar"))
        self.assertIn("Propensão de compra: media. Interesse claro", resumo)
        self.assertIn("Probabilidade de fechamento: média. Tem orçamento", resumo)

    def test_insights_mapeados_sem_placeholder_nem_repeticao(self):
        pares = [(i["kind"], i["text"]) for i in evento()["insights"]]
        self.assertEqual(pares, [
            ("RECOMMENDATION", "Enviar proposta revisada (prazo: sexta)"),
            ("RECOMMENDATION", "Agendar reunião com o diretor"),
            ("STAGE_SUGGESTION", "Próximo passo combinado: Enviar proposta revisada (prazo: sexta)"),
            ("OBJECTION", "Preço acima do orçamento"),
            ("PAIN", "Processo comercial manual"),
            ("BUYING_SIGNAL", "Pediu prazo de implantação"),
            ("EVIDENCE", "Atenção: Decisor não participou"),
        ])
        insights = evento()["insights"]
        self.assertEqual(insights[2]["stageName"], "Proposta")
        self.assertEqual(insights[5]["quote"], "Quanto tempo leva?")
        self.assertNotIn("quote", insights[6])

    def test_etapa_mais_avancada_vence(self):
        self.assertEqual(r.sugerir_etapa(["Enviar proposta", "Enviar contrato para assinatura"])["stageName"], "Negociação")
        self.assertIsNone(r.sugerir_etapa(["Agendar nova conversa"]))

    def test_sem_empresa_usa_nome_e_depois_o_titulo(self):
        so_nome = dict(RECAP, cliente_identificado={"nome": "Ana Souza", "empresa": None})
        e = evento(relatorio={"recapitulacao": so_nome})
        self.assertEqual(e["meeting"]["title"], "Reunião com Ana Souza")
        self.assertIsNone(e["links"]["companyName"])
        sem = dict(RECAP, cliente_identificado={"nome": "Cliente", "empresa": "a empresa"})
        self.assertEqual(evento(relatorio={"recapitulacao": sem})["meeting"]["title"], RELATORIO["titulo"])

    def test_sem_resumo_nao_envia(self):
        self.assertIsNone(evento(relatorio={"recapitulacao": {"proximos_passos": []}}))
        self.assertIsNone(evento(relatorio={"recapitulacao": "texto que nao e json"}))

    def test_recapitulacao_em_texto_json(self):
        self.assertIsNotNone(evento(relatorio={"recapitulacao": json.dumps(RECAP)}))

    def test_respeita_limites_do_contrato(self):
        grande = dict(RECAP, resumo_executivo="x" * 50_000,
                      recapitulacao_estrategica={"dores_identificadas": [f"dor {i} " + "y" * 3000 for i in range(80)]})
        e = evento(relatorio={"recapitulacao": grande}, participantes=[{"nome": f"P{i}"} for i in range(70)],
                   inicio=INICIO, fim=INICIO + timedelta(days=3))
        self.assertLessEqual(len(e["meeting"]["summary"]), r.MAX_RESUMO)
        self.assertEqual(len(e["insights"]), r.MAX_INSIGHTS)
        self.assertTrue(all(len(i["text"]) <= r.MAX_TEXTO for i in e["insights"]))
        self.assertEqual(len(e["meeting"]["participants"]), r.MAX_PARTICIPANTES)
        self.assertEqual(e["meeting"]["durationMinutes"], 24 * 60)
        self.assertIsNotNone(r.serializar(e))

    def test_serializar_recusa_acima_de_256kb(self):
        self.assertIsNone(r.serializar({"x": "y" * (r.MAX_BYTES + 1)}))


class OfertaTest(unittest.TestCase):
    """V.1.4.200 — `offer` para o "Só diagnóstico" (V2-8.2/8.3 do SalesOS)."""

    def com_oferta(self, oferta):
        return evento(relatorio={"recapitulacao": dict(RECAP, oferta=oferta)})["offer"]

    def test_nao_apresentada_leva_o_motivo(self):
        self.assertEqual(
            self.com_oferta({"apresentada": False, "motivo_nao_apresentada": "  O decisor   não estava. "}),
            {"presented": False, "reason": "O decisor não estava."},
        )

    def test_apresentada_nao_leva_motivo(self):
        self.assertEqual(
            self.com_oferta({"apresentada": True, "motivo_nao_apresentada": "qualquer"}),
            {"presented": True, "reason": None},
        )

    def test_sem_avaliacao_fica_nulo(self):
        self.assertIsNone(evento()["offer"])  # relatório antigo, sem o campo
        for valor in (None, "true", "false", "sim", 1, "null"):
            self.assertIsNone(self.com_oferta({"apresentada": valor}), valor)
        self.assertIsNone(self.com_oferta("texto"))

    def test_motivo_placeholder_ou_vazio_vira_nulo(self):
        for motivo in ("motivo ou null", "null", "", None, "x"):
            self.assertEqual(
                self.com_oferta({"apresentada": False, "motivo_nao_apresentada": motivo}),
                {"presented": False, "reason": None},
                motivo,
            )

    def test_motivo_respeita_o_limite(self):
        oferta = self.com_oferta({"apresentada": False, "motivo_nao_apresentada": "m" * 5000})
        self.assertEqual(len(oferta["reason"]), r.MAX_TEXTO)

    def test_offer_vai_no_corpo_serializado(self):
        e = evento(relatorio={"recapitulacao": dict(RECAP, oferta={"apresentada": False, "motivo_nao_apresentada": "Faltou tempo"})})
        self.assertEqual(json.loads(r.serializar(e))["offer"], {"presented": False, "reason": "Faltou tempo"})

    def test_prompt_pede_a_oferta(self):
        from api import main as m
        self.assertIn('REGRAS PARA "oferta"', m.PROMPT_RECAPITULACAO)
        self.assertIn('"oferta": {"apresentada"', m.PROMPT_RECAPITULACAO)


class ReenvioTest(unittest.TestCase):
    def test_classifica_respostas(self):
        self.assertEqual(r.classificar_resposta(201), r.STATUS_OK)
        self.assertEqual(r.classificar_resposta(200), r.STATUS_OK)
        for codigo in (None, 500, 502, 429):
            self.assertEqual(r.classificar_resposta(codigo), r.STATUS_ERRO, codigo)
        for codigo in (400, 401, 404):
            self.assertEqual(r.classificar_resposta(codigo), r.STATUS_RECUSADO, codigo)

    def test_espera_crescente_e_limite(self):
        self.assertTrue(r.pode_reenviar(0, None, AGORA))
        self.assertFalse(r.pode_reenviar(1, AGORA - timedelta(minutes=4), AGORA))
        self.assertTrue(r.pode_reenviar(1, AGORA - timedelta(minutes=5), AGORA))
        self.assertFalse(r.pode_reenviar(2, AGORA - timedelta(minutes=20), AGORA))
        self.assertTrue(r.pode_reenviar(4, AGORA - timedelta(hours=6), AGORA))
        self.assertFalse(r.pode_reenviar(r.MAX_TENTATIVAS, AGORA - timedelta(days=9), AGORA))


ENV = {"SALESOS_EVENTS_URL": "https://saleos.tech/api/integrations/saleia/org1/events", "SALESOS_EVENTS_SECRET": "slia_x"}


def sessao(sid, status=None, tentativas=0, em=None):
    return (sid, f"meet-{sid}", status, tentativas, em, FIM, FIM)


class FilaTest(unittest.TestCase):
    def setUp(self):
        self.marcas = []
        patches = [
            patch.dict("os.environ", ENV, clear=False),
            patch.object(svc, "_reservar", return_value=True),
            patch.object(svc, "_marcar", side_effect=lambda sid, st, det, tentou: self.marcas.append((sid, st, det, tentou))),
            patch.object(svc, "_dados_da_reuniao", return_value=(RELATORIO, INICIO, PARTICIPANTES)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_desligado_sem_configuracao(self):
        with patch.dict("os.environ", {"SALESOS_EVENTS_URL": "", "SALESOS_EVENTS_SECRET": ""}), \
             patch.object(svc, "_candidatas") as candidatas:
            self.assertEqual(svc.processar_envios(agora=AGORA), [])
            candidatas.assert_not_called()

    def test_envia_assinado_e_marca_ok(self):
        enviados = []

        def post(url, corpo, headers):
            enviados.append((url, corpo, headers))
            return 201, "HTTP 201 via=company"

        with patch.object(svc, "_candidatas", return_value=[sessao(1)]), patch.object(svc, "_post", side_effect=post):
            feitos = svc.processar_envios(agora=AGORA)

        self.assertEqual(feitos, [{"sessao_id": 1, "status": "ok", "detalhe": "HTTP 201 via=company"}])
        self.assertEqual(self.marcas, [(1, "ok", "HTTP 201 via=company", True)])
        url, corpo, headers = enviados[0]
        self.assertEqual(url, ENV["SALESOS_EVENTS_URL"])
        self.assertEqual(headers["X-Saleia-Signature"], r.assinar("slia_x", headers["X-Saleia-Timestamp"], corpo))
        self.assertEqual(json.loads(corpo)["meeting"]["externalId"], "meet-1")

    def test_falha_de_rede_volta_para_a_fila_e_401_nao(self):
        respostas = iter([(None, "ConnectError"), (401, "HTTP 401 UNAUTHENTICATED")])
        with patch.object(svc, "_candidatas", return_value=[sessao(1), sessao(2)]), \
             patch.object(svc, "_post", side_effect=lambda *a: next(respostas)):
            svc.processar_envios(agora=AGORA)
        self.assertEqual([(m[0], m[1]) for m in self.marcas], [(1, "erro"), (2, "recusado")])

    def test_respeita_a_espera_antes_de_reenviar(self):
        cedo = sessao(1, status="erro", tentativas=1, em=AGORA - timedelta(minutes=2))
        tarde = sessao(2, status="erro", tentativas=1, em=AGORA - timedelta(minutes=6))
        with patch.object(svc, "_candidatas", return_value=[cedo, tarde]), \
             patch.object(svc, "_post", return_value=(200, "HTTP 200 via=None")) as post:
            feitos = svc.processar_envios(agora=AGORA)
        self.assertEqual([f["sessao_id"] for f in feitos], [2])
        self.assertEqual(post.call_count, 1)

    def test_sem_resumo_fica_pulado_sem_contar_tentativa(self):
        with patch.object(svc, "_candidatas", return_value=[sessao(1)]), \
             patch.object(svc, "_dados_da_reuniao", return_value=({"recapitulacao": {}}, INICIO, [])), \
             patch.object(svc, "_post") as post:
            svc.processar_envios(agora=AGORA)
        post.assert_not_called()
        self.assertEqual(self.marcas, [(1, "pulado", "sem resumo", False)])

    def test_outro_worker_levou_a_sessao(self):
        with patch.object(svc, "_candidatas", return_value=[sessao(1)]), \
             patch.object(svc, "_reservar", return_value=False), patch.object(svc, "_post") as post:
            self.assertEqual(svc.processar_envios(agora=AGORA), [])
        post.assert_not_called()

    def test_erro_inesperado_nao_derruba_o_laco(self):
        with patch.object(svc, "_candidatas", return_value=[sessao(1), sessao(2)]), \
             patch.object(svc, "_post", side_effect=[RuntimeError("x"), (201, "HTTP 201 via=None")]):
            feitos = svc.processar_envios(agora=AGORA)
        self.assertEqual([f["status"] for f in feitos], ["erro", "ok"])


if __name__ == "__main__":
    unittest.main()
