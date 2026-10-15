"""
Vocabulário do Whisper (A12): agent/transcricao_vocabulario_rules.py e
o uso em POST /audio-transcricao.

Run:
    python -m unittest tests.test_transcricao_vocabulario -v
"""
import base64
import os
import unittest
from unittest.mock import patch

from agent.transcricao_vocabulario_rules import (
    GLOSSARIO_PADRAO,
    MAX_CHARS_PROMPT,
    contexto_final,
    eh_alucinacao,
    glossario_do_ambiente,
    montar_prompt_whisper,
    nomes_dos_falantes,
)

TRECHO = "\n".join([
    "Paulo: Me conta como vocês fazem hoje o controle financeiro",
    "Maria Souza: Hoje a gente faz tudo na planilha, é bem manual.",
    "Cliente: E quanto custa o programa?",
    "Não identificado: Pois é.",
    "[Groq] Isso depende do plano que vocês escolherem.",
])


class RegrasTest(unittest.TestCase):
    def test_glossario(self):
        self.assertEqual(glossario_do_ambiente(None), GLOSSARIO_PADRAO)
        self.assertEqual(glossario_do_ambiente(" Mentoria , Performance ,"), ("Mentoria", "Performance"))

    def test_nomes_ignora_rotulos_genericos(self):
        self.assertEqual(nomes_dos_falantes(TRECHO), ["Paulo", "Maria Souza"])

    def test_contexto_final_sem_rotulos_e_cortado_em_palavra(self):
        ctx = contexto_final(TRECHO)
        self.assertTrue(ctx.endswith("Isso depende do plano que vocês escolherem."))
        self.assertNotIn("Maria Souza:", ctx)
        self.assertNotIn("[Groq]", ctx)
        self.assertLessEqual(len(ctx), 220)
        self.assertFalse(ctx.startswith(" "))

    def test_prompt_tem_tudo_e_respeita_o_limite(self):
        p = montar_prompt_whisper(GLOSSARIO_PADRAO, ["Paulo", "Maria Souza"], contexto_final(TRECHO))
        self.assertIn("Programa de Aceleração", p)
        self.assertIn("Participantes: Paulo, Maria Souza.", p)
        self.assertIn("escolherem", p)
        self.assertLessEqual(len(montar_prompt_whisper(GLOSSARIO_PADRAO, ["X"] * 6, "palavra " * 500)), MAX_CHARS_PROMPT)

    def test_alucinacoes_tipicas(self):
        self.assertTrue(eh_alucinacao("Legendas pela comunidade Amara.org", ""))
        self.assertTrue(eh_alucinacao("Obrigado por assistir!", ""))

    def test_eco_do_prompt(self):
        p = montar_prompt_whisper(GLOSSARIO_PADRAO, ["Paulo"], contexto_final(TRECHO))
        self.assertTrue(eh_alucinacao("Isso depende do plano que vocês escolherem", p))
        self.assertTrue(eh_alucinacao("Reunião de vendas em português do Brasil.", p))

    def test_fala_real_nao_e_descartada(self):
        p = montar_prompt_whisper(GLOSSARIO_PADRAO, ["Paulo"], contexto_final(TRECHO))
        self.assertFalse(eh_alucinacao("Com certeza", p))  # curta repetida fica
        self.assertFalse(eh_alucinacao("Obrigado, Paulo, até semana que vem", p))
        self.assertFalse(eh_alucinacao("O Programa de Aceleração começa quando?", p))
        self.assertFalse(eh_alucinacao("", p))


class AudioTranscricaoEndpointTest(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from api.main import app
        self.client = TestClient(app)
        self.payload = {
            "audio_base64": "data:audio/webm;base64," + base64.b64encode(b"0" * 1024).decode(),
            "mime_type": "audio/webm", "meeting_id": "abc-defg-hij",
        }
        for p in (
            patch.dict(os.environ, {"TRANSCRICAO_PROVEDOR": "whisper_local", "TRANSCRICAO_GLOSSARIO": "", "TRANSCRICAO_TEMPO_REAL_ATIVA": "true"}),
            patch("api.database.obter_trecho_final_transcricao", return_value=TRECHO),
            patch("agent.sessao_manager.registrar_sessao"),
            patch("agent.sessao_manager.salvar_transcricao_bruta"),
        ):
            p.start()
            self.addCleanup(p.stop)

    def test_prompt_com_vocabulario_chega_ao_whisper(self):
        with patch("agent.whisper_local.transcrever", return_value="ola mundo") as fake:
            r = self.client.post("/audio-transcricao", json=self.payload)
        self.assertEqual(r.json()["texto"], "ola mundo")
        prompt = fake.call_args.kwargs["prompt"]
        self.assertIn("Programa de Aceleração", prompt)
        self.assertIn("Maria Souza", prompt)

    def test_alucinacao_e_descartada_e_nao_e_salva(self):
        with patch("agent.whisper_local.transcrever", return_value="Legendas pela comunidade Amara.org"), \
             patch("agent.sessao_manager.salvar_transcricao_bruta") as salvar:
            r = self.client.post("/audio-transcricao", json=self.payload)
        body = r.json()
        self.assertEqual(body["texto"], "")
        self.assertEqual(body["motivo"], "descartado")
        salvar.assert_not_called()

    def test_v180_tempo_real_desligado_nao_transcreve_nenhuma_trilha(self):
        for corpo in ({**self.payload, "fonte": "aba"}, {**self.payload, "fonte": "microfone"}, self.payload):
            with patch.dict(os.environ, {"TRANSCRICAO_TEMPO_REAL_ATIVA": "false", "TRANSCRICAO_MICROFONE_ATIVA": "true"}), \
                 patch("agent.whisper_local.transcrever", return_value="ola mundo") as fake:
                r = self.client.post("/audio-transcricao", json=corpo)
            self.assertEqual(r.json(), {"texto": "", "ok": True, "motivo": "tempo_real_desligado"})
            fake.assert_not_called()

    def test_v180_config_informa_a_extensao(self):
        with patch.dict(os.environ, {"TRANSCRICAO_TEMPO_REAL_ATIVA": ""}):
            cfg = self.client.get("/gravacao/config").json()
        self.assertIs(cfg["transcricao_tempo_real"], False)
        self.assertEqual(cfg["bitrate"], 32_000)

    def test_microfone_desligado_por_padrao_nao_transcreve(self):
        with patch.dict(os.environ, {"TRANSCRICAO_MICROFONE_ATIVA": ""}), \
             patch("agent.whisper_local.transcrever", return_value="ola mundo") as fake:
            r = self.client.post("/audio-transcricao", json={**self.payload, "fonte": "microfone"})
        self.assertEqual(r.json(), {"texto": "", "ok": True, "motivo": "microfone_desligado"})
        fake.assert_not_called()

    def test_microfone_religado_pelo_env_transcreve(self):
        with patch.dict(os.environ, {"TRANSCRICAO_MICROFONE_ATIVA": "true"}), \
             patch("agent.whisper_local.transcrever", return_value="ola mundo") as fake:
            r = self.client.post("/audio-transcricao", json={**self.payload, "fonte": "microfone"})
        self.assertEqual(r.json()["texto"], "ola mundo")
        fake.assert_called_once()

    def test_aba_e_extensao_antiga_continuam_transcrevendo(self):
        for corpo in ({**self.payload, "fonte": "aba"}, self.payload):
            with patch("agent.whisper_local.transcrever", return_value="ola mundo") as fake:
                r = self.client.post("/audio-transcricao", json=corpo)
            self.assertEqual(r.json()["texto"], "ola mundo")
            fake.assert_called_once()

    def test_sem_banco_vai_so_o_glossario(self):
        with patch("api.database.obter_trecho_final_transcricao", side_effect=RuntimeError("banco fora")), \
             patch("agent.whisper_local.transcrever", return_value="ola mundo") as fake:
            r = self.client.post("/audio-transcricao", json=self.payload)
        self.assertTrue(r.json()["ok"])
        self.assertIn("Programa de Aceleração", fake.call_args.kwargs["prompt"])


if __name__ == "__main__":
    unittest.main()
