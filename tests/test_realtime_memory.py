import sys
import sys
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlmodel import create_engine

from api import database
from api import processador_tempo_real as realtime


class RealtimeMemoryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.db_path = Path(self._tmpdir.name) / "saleia_realtime.db"
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        self.engine_patch = patch.object(database, "engine", self.engine)
        self.engine_patch.start()
        self.addCleanup(self.engine_patch.stop)
        self.addCleanup(self.engine.dispose)
        database.criar_tabelas()
        realtime._cache_transcricoes.clear()

    async def test_skips_ai_when_new_text_is_insufficient(self):
        database.registrar_analise_meeting(
            "meeting-skip",
            {
                "recapitulacao": "resumo salvo",
                "score_compra": {"valor": 71, "justificativa": "bom sinal"},
                "perfil_disc": {"tipo": "D"},
            },
        )

        fake_ai = types.ModuleType("agent.agente_tempo_real")
        fake_ai.analisar_fragmento = AsyncMock()
        fake_sessao = types.ModuleType("agent.sessao_manager")
        fake_sessao.salvar_analise = lambda *args, **kwargs: None

        with patch.dict(
            sys.modules,
            {
                "agent.agente_tempo_real": fake_ai,
                "agent.sessao_manager": fake_sessao,
            },
        ):
            resultado = await realtime.analyzeRealtimeMeeting(
                transcricao_parcial="oi",
                transcricao_nova="oi",
                historico="hist",
                perfil_disc_atual="D",
                meeting_id="meeting-skip",
            )

        self.assertEqual(resultado["analysis_status"], "skipped")
        self.assertEqual(resultado["analysis_reason"], "texto_novo_insuficiente")
        self.assertEqual(resultado["resumo_vivo"], "resumo salvo")
        self.assertEqual(resultado["score_compra"]["valor"], 71)
        fake_ai.analisar_fragmento.assert_not_awaited()

    async def test_calls_ai_and_persists_realtime_analysis(self):
        mock_result = {
            "recapitulacao": "resumo vivo atualizado",
            "alerta_urgente": "risco moderado",
            "score_compra": {"valor": 82, "justificativa": "cliente engajado"},
            "proxima_fala": "Pode me confirmar se isso faz sentido?",
            "objecao_detectada": {"objecao": "esta caro", "resposta_pronta": "podemos ajustar"},
            "mapa_financeiro": {"faturamento_mensal": "R$ 40 mil"},
        }

        fake_ai = types.ModuleType("agent.agente_tempo_real")
        fake_ai.analisar_fragmento = AsyncMock(return_value=mock_result)
        fake_sessao = types.ModuleType("agent.sessao_manager")
        fake_sessao.salvar_analise = lambda *args, **kwargs: None

        with patch.dict(
            sys.modules,
            {
                "agent.agente_tempo_real": fake_ai,
                "agent.sessao_manager": fake_sessao,
            },
        ):
            resultado = await realtime.analyzeRealtimeMeeting(
                transcricao_parcial=(
                    "Cliente explicou a dor principal, o impacto no time, o processo atual, "
                    "as preocupacoes com prazo e custo, e pediu uma proposta com proximo passo claro."
                ),
                transcricao_nova=(
                    "Cliente explicou a dor principal, o impacto no time, o processo atual, "
                    "as preocupacoes com prazo e custo, e pediu uma proposta com proximo passo claro."
                ),
                historico="inicio",
                perfil_disc_atual="I",
                meeting_id="meeting-update",
        )

        self.assertEqual(resultado["analysis_status"], "updated")
        self.assertEqual(resultado["analysis_reason"], "sem_tempo_anterior")
        self.assertEqual(resultado["resumo_vivo"], "resumo vivo atualizado")
        self.assertEqual(resultado["proxima_fala"], "Pode me confirmar se isso faz sentido?")
        self.assertEqual(resultado["mapa_financeiro"]["faturamento_mensal"], "R$ 40 mil")
        self.assertEqual(fake_ai.analisar_fragmento.await_count, 1)

        chamada = fake_ai.analisar_fragmento.await_args.kwargs
        self.assertEqual(chamada["resumo_vivo"], "Resumo ainda nao disponivel")
        self.assertEqual(chamada["diagnostico_atual"], {})

        memoria = database.obter_meeting_memory("meeting-update")
        self.assertIsNotNone(memoria)
        self.assertEqual(memoria["accumulated_summary"], "resumo vivo atualizado")
        self.assertEqual(memoria["score_history"][0]["valor"], 82)
        diagnostico = json.loads(memoria["current_diagnosis"])
        self.assertEqual(diagnostico["score_compra"]["valor"], 82)

    async def test_generates_live_recap_when_trigger_phrase_is_detected(self):
        mock_result = {
            "recapitulacao": "resumo vivo atualizado",
            "score_compra": {"valor": 76, "justificativa": "cliente segue engajado"},
            "proxima_fala": "Vamos alinhar o proximo passo.",
            "mapa_financeiro": {},
        }
        mock_recap = {
            "status": "generated",
            "texto_falavel": "Pelo que eu entendi, a principal dor agora e reduzir o risco e confirmar o investimento.",
            "pergunta_confirmacao": "Faz sentido recapitular dessa forma?",
            "perguntas_faltantes": ["Validar decisor final"],
            "dica_vendedor": "Use a deixa para confirmar entendimento e alinhar o proximo passo.",
            "mapa_mental": {
                "dor_principal": "reduzir risco",
                "impacto": "seguranca da decisao",
                "objetivo": "avancar com clareza",
                "objecoes": ["esta caro"],
                "oportunidades": ["validar investimento"],
                "proximo_passo": "confirmar entendimento",
            },
        }

        fake_ai = types.ModuleType("agent.agente_tempo_real")
        fake_ai.analisar_fragmento = AsyncMock(return_value=mock_result)
        fake_recap = types.ModuleType("agent.recapitulacao")
        fake_recap.detectRecapTrigger = lambda texto, memoria=None, cooldown_seconds=None: {
            "triggered": True,
            "reason": "matched_phrase",
            "cooldown_seconds": 180,
            "remaining_cooldown_seconds": 0,
            "trigger_phrase": "deixa eu ver se entendi",
            "confidence": "high",
            "fact_or_inference": "fact",
            "timestamp": "2026-05-24T12:00:00+00:00",
        }
        fake_recap.generateLiveRecapMindMap = AsyncMock(return_value=mock_recap)
        fake_sessao = types.ModuleType("agent.sessao_manager")
        fake_sessao.salvar_analise = lambda *args, **kwargs: None

        with patch.dict(
            sys.modules,
            {
                "agent.agente_tempo_real": fake_ai,
                "agent.recapitulacao": fake_recap,
                "agent.sessao_manager": fake_sessao,
            },
        ):
            resultado = await realtime.analyzeRealtimeMeeting(
                transcricao_parcial=(
                    "Deixa eu ver se entendi: voce esta dizendo que o principal ponto agora "
                    "e reduzir risco antes de seguir com a proposta."
                ),
                transcricao_nova=(
                    "Deixa eu ver se entendi: voce esta dizendo que o principal ponto agora "
                    "e reduzir risco antes de seguir com a proposta."
                ),
                historico="inicio",
                perfil_disc_atual="S",
                meeting_id="meeting-recap",
            )

        self.assertEqual(resultado["recap_trigger"]["trigger_phrase"], "deixa eu ver se entendi")
        self.assertEqual(resultado["recapitulacao_viva"]["mapa_mental"]["dor_principal"], "reduzir risco")
        self.assertEqual(resultado["recapitulacao_viva"]["texto_falavel"], mock_recap["texto_falavel"])
        self.assertTrue(any(item["type"] == "recap_trigger" for item in resultado["eventos"]))

        memoria = database.obter_meeting_memory("meeting-recap")
        self.assertIsNotNone(memoria)
        self.assertIsNotNone(memoria["last_recap_trigger_at"])
        diagnostico = json.loads(memoria["current_diagnosis"])
        self.assertIn("recapitulacao_viva", diagnostico)

    def test_recapitulacao_viva_endpoint_regenerates_from_memory(self):
        database.salvar_meeting_memory(
            "meeting-endpoint",
            transcript_full="Cliente falou sobre prazo e investimento.",
            transcript_buffer="Cliente falou sobre prazo e investimento.",
            accumulated_summary="Resumo persistido da reunião.",
            current_diagnosis=json.dumps(
                {
                    "objecao_detectada": {"objecao": "esta caro"},
                    "proxima_fala": "Posso recapitular o que ficou combinado?",
                },
                ensure_ascii=False,
            ),
            score_history=[{"timestamp": "2026-05-24T12:00:00+00:00", "valor": 77}],
            key_moments=[{"type": "buying_signal", "quote": "quero seguir"}],
            events=[{"type": "pricing_resistance", "quote": "esta caro"}],
        )

        fake_recap = types.ModuleType("agent.recapitulacao")
        fake_recap.generateLiveRecapMindMap = AsyncMock(
            return_value={
                "status": "generated",
                "texto_falavel": "Vamos recapitular o combinado.",
                "pergunta_confirmacao": "Faz sentido seguir assim?",
                "perguntas_faltantes": ["Validar decisor"],
                "dica_vendedor": "Aproveite para confirmar o proximo passo.",
                "mapa_mental": {
                    "dor_principal": "prazo",
                    "impacto": "risco de atraso",
                    "objetivo": "avancar",
                    "objecoes": ["esta caro"],
                    "oportunidades": ["validar decisor"],
                    "proximo_passo": "confirmar alinhamento",
                },
            }
        )

        with patch.dict(sys.modules, {"agent.recapitulacao": fake_recap}):
            from api.main import app as saleia_app

            client = TestClient(saleia_app)
            response = client.post("/recapitulacao-viva", json={"meeting_id": "meeting-endpoint"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meeting_id"], "meeting-endpoint")
        self.assertEqual(payload["recapitulacao_viva"]["mapa_mental"]["dor_principal"], "prazo")
        self.assertEqual(payload["live_recap"]["texto_falavel"], "Vamos recapitular o combinado.")


if __name__ == "__main__":
    unittest.main()
