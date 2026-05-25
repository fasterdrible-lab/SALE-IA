import json
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from agent import diagnostico_final
from api import webhook_tactiq as webhook


class FinalDiagnosisTest(unittest.IsolatedAsyncioTestCase):
    async def test_generate_final_diagnosis_normalizes_ai_response(self):
        ai_response = {
            "resumo_executivo": "Resumo final da reuniao",
            "diagnostico_cliente": "Cliente com alta intencao de compra",
            "dores": "prazo apertado",
            "objecoes": ["preco"],
            "intencao_compra": {
                "nivel": "alta",
                "evidencias": "cliente pediu proposta",
                "justificativa": "sinal de fechamento",
            },
            "perfil_disc": {
                "tipo": "D",
                "confianca": "alta",
                "evidencia": "respostas objetivas",
                "como_abordar": "direto ao ponto",
            },
            "capacidade_financeira": {
                "nivel": "media",
                "evidencias": "faturamento citado",
                "produto_indicado": {"nome": "Plano X", "valor": "R$ 10.000", "justificativa": "encaixe"},
            },
            "risco_perda": {"nivel": "baixo", "motivos": "nenhum alerta relevante"},
            "proximos_passos": "enviar proposta final",
            "score_final": {"valor": "83", "justificativa": "sinal forte"},
            "sinais_compra": "pedido de proposta",
            "sinais_alerta": "nenhum",
            "oportunidades_nao_exploradas": "validar decisor",
            "transcript_usado": "transcricao parcial",
        }

        with patch.object(diagnostico_final, "chamar_ia_async", AsyncMock(return_value=ai_response)):
            resultado = await diagnostico_final.generateFinalDiagnosis(
                accumulated_summary="Resumo acumulado",
                current_diagnosis={"mapa_financeiro": {"produto_indicado": {"nome": "Plano X"}}},
                key_moments=[{"type": "buying_signal", "quote": "quero seguir"}],
                score_history=[{"valor": 79, "timestamp": "2026-05-24T10:00:00Z"}],
                transcript_full="Cliente falou sobre dor e prazo.",
                events=[{"type": "closing_signal", "quote": "vamos seguir"}],
                diagnostico_financeiro={"produto_recomendado": {"nome": "Plano X"}},
                perfil_disc={"tipo": "D", "confianca": "alta"},
                recapitulacao={"resumo_executivo": "Resumo da recapitulacao"},
            )

        self.assertEqual(resultado["status"], "generated")
        self.assertEqual(resultado["resumo_executivo"], "Resumo final da reuniao")
        self.assertEqual(resultado["dores"], ["prazo apertado"])
        self.assertEqual(resultado["objecoes"], ["preco"])
        self.assertEqual(resultado["intencao_compra"]["evidencias"], ["cliente pediu proposta"])
        self.assertEqual(resultado["perfil_disc"]["tipo"], "D")
        self.assertEqual(resultado["capacidade_financeira"]["produto_indicado"]["nome"], "Plano X")
        self.assertEqual(resultado["risco_perda"]["nivel"], "baixo")
        self.assertEqual(resultado["proximos_passos"], ["enviar proposta final"])
        self.assertEqual(resultado["score_final"]["valor"], 83)
        self.assertEqual(resultado["sinais_compra"], ["pedido de proposta"])
        self.assertEqual(resultado["sinais_alerta"], ["nenhum"])
        self.assertEqual(resultado["oportunidades_nao_exploradas"], ["validar decisor"])

    async def test_webhook_includes_final_diagnosis_and_persists_memory(self):
        transcript = (
            "Cliente explicou a dor principal, o impacto no time, as objecoes sobre preco "
            "e pediu alinhamento do proximo passo com envio de proposta."
        )
        memoria_existente = {
            "meeting_id": "meeting-final",
            "transcript_buffer": "trecho anterior",
            "accumulated_summary": "Resumo acumulado da memoria",
            "current_diagnosis": json.dumps(
                {
                    "mapa_financeiro": {"produto_indicado": {"nome": "Plano Base"}},
                    "score_compra": {"valor": 74},
                },
                ensure_ascii=False,
            ),
            "key_moments": [
                {
                    "type": "buying_signal",
                    "quote": "quero seguir",
                    "speaker": "cliente",
                    "timestamp": "2026-05-24T10:00:00Z",
                    "importance": "high",
                    "confidence": "high",
                    "fact_or_inference": "fact",
                }
            ],
            "events": [
                {
                    "type": "pricing_resistance",
                    "quote": "esta acima do esperado",
                    "speaker": "cliente",
                    "importance": "high",
                    "confidence": "medium",
                    "fact_or_inference": "fact",
                }
            ],
            "score_history": [{"timestamp": "2026-05-24T10:00:00Z", "valor": 74}],
        }
        final_diagnosis = {
            "status": "generated",
            "resumo_executivo": "Resumo executivo final",
            "diagnostico_cliente": "Cliente com alta probabilidade de avancar",
            "dores": ["prazo"],
            "objecoes": ["preco"],
            "intencao_compra": {"nivel": "alta", "evidencias": ["pediu proposta"], "justificativa": "sinal forte"},
            "perfil_disc": {"tipo": "D", "confianca": "alta", "evidencia": "objetivo", "como_abordar": "direto"},
            "capacidade_financeira": {
                "nivel": "media",
                "evidencias": ["faturamento citado"],
                "produto_indicado": {
                    "nome": "Plano Base",
                    "valor": "R$ 10.000",
                    "justificativa": "encaixe no contexto",
                },
            },
            "risco_perda": {"nivel": "medio", "motivos": ["objeção de preço"]},
            "proximos_passos": ["enviar proposta", "confirmar decisor"],
            "mensagem_follow_up": "Vou te enviar a proposta e validar o melhor proximo passo.",
            "score_final": {"valor": 81, "justificativa": "sinal de avanco"},
            "sinais_compra": ["pediu proposta"],
            "sinais_alerta": ["objeção de preço"],
            "oportunidades_nao_exploradas": ["validar decisor"],
            "transcript_usado": "trecho final",
        }

        fake_diagnostico_financeiro = AsyncMock(return_value={
            "produto_recomendado": {"nome": "Plano Base"},
            "_custo_estimado_ia": 0.002,
        })
        fake_perfil_disc = AsyncMock(return_value={
            "tipo": "D",
            "confianca": "alta",
            "_custo_estimado_ia": 0.003,
        })
        fake_recapitulacao = AsyncMock(return_value={
            "resumo_executivo": "Resumo da recapitulacao",
            "_custo_estimado_ia": 0.004,
        })
        fake_final = AsyncMock(return_value={**final_diagnosis, "_custo_estimado_ia": 0.007})
        fake_notificar = AsyncMock(return_value={"canal": "whatsapp", "status": "ok"})
        fake_salvar_relatorio = Mock(return_value=Path("data/relatorios/relatorio-final.json"))
        fake_registrar_transcricao = Mock()
        fake_salvar_memoria = Mock()
        fake_limpar_cache = Mock()

        with ExitStack() as stack:
            stack.enter_context(patch.object(webhook, "diagnostico_financeiro", fake_diagnostico_financeiro))
            stack.enter_context(patch.object(webhook, "perfil_disc", fake_perfil_disc))
            stack.enter_context(patch.object(webhook, "recapitulacao_completa", fake_recapitulacao))
            stack.enter_context(patch.object(webhook, "generateFinalDiagnosis", fake_final))
            stack.enter_context(patch.object(webhook, "notificar_vendedor", fake_notificar))
            stack.enter_context(patch.object(webhook, "salvar_relatorio", fake_salvar_relatorio))
            stack.enter_context(patch.object(webhook, "registrar_transcricao_meeting", fake_registrar_transcricao))
            stack.enter_context(patch.object(webhook, "salvar_meeting_memory", fake_salvar_memoria))
            stack.enter_context(patch.object(webhook, "obter_meeting_memory", Mock(return_value=memoria_existente)))
            stack.enter_context(patch.object(webhook, "limpar_cache_reuniao", fake_limpar_cache))
            resultado = await webhook.processar_webhook_tactiq(
                {
                    "transcript": transcript,
                    "meeting_title": "Reuniao com Cliente Alfa",
                    "participants": ["cliente@empresa.com"],
                    "date": "2026-05-24T12:00:00Z",
                    "meeting_id": "meeting-final",
                }
            )

        self.assertEqual(resultado["status"], "processado")
        self.assertEqual(resultado["arquivo"], str(Path("data/relatorios/relatorio-final.json")))
        self.assertEqual(resultado["notificacao"]["status"], "ok")

        self.assertEqual(fake_final.await_count, 1)
        relatorio_passado = fake_salvar_relatorio.call_args.args[0]
        self.assertIn("diagnostico_final", relatorio_passado)
        self.assertEqual(relatorio_passado["diagnostico_final"]["resumo_executivo"], "Resumo executivo final")
        self.assertAlmostEqual(relatorio_passado["custo_estimado_ia_total"], 0.016, places=6)

        memoria_passada = fake_salvar_memoria.call_args.kwargs
        current_diagnosis = json.loads(memoria_passada["current_diagnosis"])
        self.assertIn("diagnostico_final", current_diagnosis)
        self.assertEqual(current_diagnosis["diagnostico_final"]["score_final"]["valor"], 81)
        self.assertEqual(memoria_passada["accumulated_summary"], "Resumo executivo final")
        self.assertEqual(memoria_passada["score_history"], memoria_existente["score_history"])
        self.assertEqual(memoria_passada["key_moments"], memoria_existente["key_moments"])
        self.assertEqual(memoria_passada["events"], memoria_existente["events"])
        self.assertAlmostEqual(memoria_passada["provider_cost_estimate_delta"], 0.016, places=6)


if __name__ == "__main__":
    unittest.main()
