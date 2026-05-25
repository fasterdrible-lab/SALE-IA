import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from sqlmodel import create_engine

from api import database


class MeetingMemoryTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.db_path = Path(self._tmpdir.name) / "saleia_memory.db"
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        self.engine_patch = patch.object(database, "engine", self.engine)
        self.engine_patch.start()
        self.addCleanup(self.engine_patch.stop)
        self.addCleanup(self.engine.dispose)
        database.criar_tabelas()

    def test_creates_and_reads_meeting_memory(self):
        database.salvar_meeting_memory(
            "meeting-1",
            transcript_full="transcricao completa",
            transcript_buffer="trecho recente",
            accumulated_summary="resumo vivo",
            current_diagnosis="diagnostico atual",
            score_history=[{"timestamp": "2026-05-23T10:00:00", "valor": 72, "fonte": "tempo_real"}],
            key_moments=[{"type": "objection_detected", "quote": "está caro"}],
            events=[{"type": "pricing_resistance"}],
            provider_cost_estimate=1.5,
        )

        memoria = database.obter_meeting_memory("meeting-1")

        self.assertIsNotNone(memoria)
        self.assertEqual(memoria["meeting_id"], "meeting-1")
        self.assertEqual(memoria["transcript_full"], "transcricao completa")
        self.assertEqual(memoria["transcript_buffer"], "trecho recente")
        self.assertEqual(memoria["accumulated_summary"], "resumo vivo")
        self.assertEqual(memoria["current_diagnosis"], "diagnostico atual")
        self.assertEqual(memoria["score_history"][0]["valor"], 72)
        self.assertEqual(memoria["key_moments"][0]["type"], "objection_detected")
        self.assertEqual(memoria["events"][0]["type"], "pricing_resistance")
        self.assertEqual(memoria["provider_cost_estimate"], 1.5)

    def test_appends_transcript_and_keeps_recent_buffer(self):
        database.registrar_transcricao_meeting("meeting-2", "primeiro fragmento")
        database.registrar_transcricao_meeting("meeting-2", "segundo fragmento")

        memoria = database.obter_meeting_memory("meeting-2")

        self.assertIsNotNone(memoria)
        self.assertIn("primeiro fragmento", memoria["transcript_full"])
        self.assertIn("segundo fragmento", memoria["transcript_full"])
        self.assertIn("segundo fragmento", memoria["transcript_buffer"])

    def test_registers_analysis_and_score_history(self):
        database.registrar_analise_meeting(
            "meeting-3",
            {
                "recapitulacao": "resumo ao vivo",
                "alerta_urgente": "risco de perda",
                "score_compra": {
                    "valor": 64,
                    "justificativa": "sinal misto, mas com interesse claro",
                },
                "objecao_detectada": {
                    "objecao": "está caro",
                    "resposta_pronta": "podemos avaliar o encaixe",
                },
            },
        )

        memoria = database.obter_meeting_memory("meeting-3")

        self.assertIsNotNone(memoria)
        self.assertEqual(memoria["accumulated_summary"], "resumo ao vivo")
        self.assertTrue(memoria["current_diagnosis"])
        self.assertEqual(memoria["score_history"][0]["valor"], 64)
        self.assertEqual(memoria["key_moments"][0]["type"], "pricing_resistance")
        self.assertEqual(memoria["events"][0]["type"], "pricing_resistance")
        self.assertEqual(memoria["events"][1]["type"], "alerta_urgente")

    def test_persists_structured_events_and_key_moments(self):
        database.registrar_analise_meeting(
            "meeting-4",
            {
                "recapitulacao": "cliente revisou o contexto e pediu confirmacao",
                "eventos": [
                    {
                        "type": "buying_signal",
                        "quote": "quero seguir com a proposta",
                        "speaker": "cliente",
                        "importance": "high",
                        "confidence": "high",
                        "fact_or_inference": "fact",
                    },
                    {
                        "type": "pricing_resistance",
                        "quote": "esta acima do que eu imaginava",
                        "speaker": "cliente",
                        "importance": "high",
                        "confidence": "medium",
                        "fact_or_inference": "fact",
                    },
                    {
                        "type": "recap_trigger",
                        "quote": "so para confirmar",
                        "speaker": "cliente",
                        "importance": "medium",
                        "confidence": "high",
                        "fact_or_inference": "fact",
                    },
                ],
                "key_moments": [
                    {
                        "type": "buying_signal",
                        "quote": "quero seguir com a proposta",
                        "speaker": "cliente",
                        "timestamp": "2026-05-23T10:01:00",
                        "importance": "high",
                        "confidence": "high",
                        "fact_or_inference": "fact",
                    },
                    {
                        "type": "competitor_mention",
                        "quote": "estou olhando uma outra solucao",
                        "speaker": "cliente",
                        "importance": "medium",
                        "confidence": "medium",
                        "fact_or_inference": "fact",
                    },
                ],
            },
        )

        memoria = database.obter_meeting_memory("meeting-4")

        self.assertIsNotNone(memoria)
        self.assertEqual(memoria["events"][0]["type"], "buying_signal")
        self.assertEqual(memoria["events"][0]["fact_or_inference"], "fact")
        self.assertEqual(memoria["events"][1]["type"], "pricing_resistance")
        self.assertEqual(memoria["events"][2]["type"], "recap_trigger")
        self.assertEqual(memoria["key_moments"][0]["type"], "buying_signal")
        self.assertEqual(memoria["key_moments"][1]["type"], "competitor_mention")
        self.assertIsNotNone(memoria["last_recap_trigger_at"])


if __name__ == "__main__":
    unittest.main()
