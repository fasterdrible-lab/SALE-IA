"""
Testes — T02 (gravação contínua do áudio): regras, armazenamento e rotas.

Áudio real: WebM/Opus gerado com PyAV e cortado em blocos, como o
MediaRecorder entrega (só o 1º bloco tem o cabeçalho). Banco SQLite e
pasta de gravações temporários — nada toca produção.

Run:
    python -m unittest tests.test_gravacao_t02 -v
"""

import base64
import io
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import av
import numpy as np
from sqlmodel import Session, create_engine, select

from agent import gravacao_rules as regras
from api import database, gravacao_store
from api.database import GravacaoAudio, GravacaoBloco

MEETING = "abc-defg-hij"
REC = "rec-0001-aba"


def gerar_webm(segundos: float = 3.0) -> bytes:
    """WebM/Opus mono 48 kHz com um tom — o mesmo formato do MediaRecorder."""
    buf = io.BytesIO()
    saida = av.open(buf, "w", format="webm")
    stream = saida.add_stream("libopus", rate=48000)
    t = np.arange(960)
    for i in range(int(segundos * 50)):  # quadros de 20 ms
        amostras = (np.sin((t + i * 960) * 2 * np.pi * 440 / 48000) * 8000).astype("int16")
        frame = av.AudioFrame.from_ndarray(amostras.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = 48000
        frame.pts = i * 960
        for pacote in stream.encode(frame):
            saida.mux(pacote)
    for pacote in stream.encode(None):
        saida.mux(pacote)
    saida.close()
    return buf.getvalue()


def cortar(dados: bytes, partes: int) -> list:
    tamanho = -(-len(dados) // partes)
    return [dados[i:i + tamanho] for i in range(0, len(dados), tamanho)]


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.engine = create_engine(f"sqlite:///{Path(self._tmp.name) / 'g.db'}")
        self.pasta = Path(self._tmp.name) / "gravacoes"
        for p in (patch.object(database, "engine", self.engine),
                  patch.dict(os.environ, {"GRAVACAO_DIR": str(self.pasta)})):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.engine.dispose)
        database.criar_tabelas()

    def iniciar(self, usuario="u1", rec=REC, trilha="aba"):
        return gravacao_store.iniciar_gravacao(usuario, MEETING, trilha, rec, "audio/webm;codecs=opus", 48000, True)

    def bloco(self, seq, dados, usuario="u1", rec=REC):
        return gravacao_store.receber_bloco(usuario, rec, seq, 1_000_000 + seq * 5000,
                                            1_000_000 + (seq + 1) * 5000, regras.hash_do_conteudo(dados), dados)


class TestRegras(unittest.TestCase):
    def test_sem_consentimento_nao_comeca(self):
        self.assertIn("é preciso confirmar que os participantes foram avisados da gravação",
                      regras.validar_inicio(MEETING, "aba", REC, False))

    def test_componentes_invalidos_nao_viram_caminho(self):
        for meeting, trilha, rec in (("../etc", "aba", REC), (MEETING, "tela", REC), (MEETING, "aba", "a/../b")):
            with self.assertRaises(ValueError):
                regras.caminho_do_bloco(Path("/x"), meeting, trilha, rec, 0)

    def test_hash_que_nao_confere_e_recusado(self):
        self.assertIn("content_hash não confere com o conteúdo",
                      regras.validar_bloco(0, 1, 2, "0" * 64, b"abc"))

    def test_bloco_grande_demais(self):
        dados = b"x" * (regras.MAX_BLOCO_BYTES + 1)
        self.assertIn("bloco grande demais", regras.validar_bloco(0, 1, 2, regras.hash_do_conteudo(dados), dados))

    def test_ultimo_bloco_depois_de_trilha_sem_som_e_aceito(self):
        # 12/10: a aba ficou 130s sem entregar áudio; o bloco do fechamento
        # cobriu esse tempo todo e era recusado (limite antigo de 120s).
        dados = b"x" * 100
        h = regras.hash_do_conteudo(dados)
        self.assertEqual(regras.validar_bloco(93, 0, 130_000, h, dados), [])
        self.assertEqual(regras.validar_bloco(0, 0, 3600 * 1000, h, dados), [])  # rotação máxima
        self.assertIn("bloco longo demais", regras.validar_bloco(0, 0, 2 * 3600 * 1000, h, dados))

    def test_lacunas(self):
        self.assertEqual(regras.lacunas([0, 1, 3, 5]), [2, 4])
        self.assertEqual(regras.lacunas([0, 1], ultima=3), [2, 3])

    def test_desligada_por_padrao(self):
        self.assertFalse(regras.habilitada({}))
        self.assertEqual(regras.configuracao({})["retencao_dias"], 7)

    def test_v180_voz_a_32kbps_e_limites(self):
        self.assertEqual(regras.configuracao({})["bitrate"], 32_000)
        self.assertEqual(regras.configuracao({"GRAVACAO_BITRATE": "64000"})["bitrate"], 64_000)
        self.assertEqual(regras.configuracao({"GRAVACAO_BITRATE": "1000"})["bitrate"], 16_000)
        self.assertEqual(regras.configuracao({"GRAVACAO_BITRATE": "x"})["bitrate"], 32_000)

    def test_v180_transcricao_tempo_real_desligada_por_padrao(self):
        self.assertFalse(regras.configuracao({})["transcricao_tempo_real"])
        self.assertTrue(regras.configuracao({"TRANSCRICAO_TEMPO_REAL_ATIVA": "true"})["transcricao_tempo_real"])
        self.assertFalse(regras.transcricao_tempo_real_ativa({"TRANSCRICAO_TEMPO_REAL_ATIVA": "nao"}))


class TestArmazenamento(_Base):
    def test_gravacao_completa_toca_e_tem_a_duracao_certa(self):
        audio = gerar_webm(3.0)
        self.iniciar()
        for seq, parte in enumerate(cortar(audio, 6)):
            self.bloco(seq, parte)
        r = gravacao_store.encerrar_gravacao("u1", REC, ultima_sequence=5)
        self.assertEqual((r["integridade"], r["lacunas"]), ("ok", []))
        self.assertAlmostEqual(r["duracao_s"], 3.0, delta=0.1)
        self.assertEqual(gravacao_store.audio_da_gravacao("u1", REC), audio)

    def test_mesmo_bloco_100_vezes_fica_uma_vez(self):
        self.iniciar()
        parte = cortar(gerar_webm(1.0), 2)[0]
        respostas = [self.bloco(0, parte) for _ in range(100)]
        self.assertEqual(sum(1 for r in respostas if not r["duplicado"]), 1)
        with Session(self.engine) as s:
            self.assertEqual(len(s.exec(select(GravacaoBloco)).all()), 1)
        self.assertEqual(len(list(self.pasta.rglob("*.webm"))), 1)

    def test_mesma_sequencia_com_outro_conteudo_e_conflito(self):
        self.iniciar()
        self.bloco(0, b"conteudo-a" * 10)
        with self.assertRaises(gravacao_store.GravacaoErro) as e:
            self.bloco(0, b"conteudo-b" * 10)
        self.assertEqual(e.exception.status, 409)

    def test_blocos_fora_de_ordem_montam_o_audio_na_ordem(self):
        audio = gerar_webm(2.0)
        partes = cortar(audio, 4)
        self.iniciar()
        for seq in (2, 0, 3, 1):
            self.bloco(seq, partes[seq])
        r = gravacao_store.encerrar_gravacao("u1", REC, ultima_sequence=3)
        self.assertEqual(r["integridade"], "ok")
        self.assertEqual(gravacao_store.audio_da_gravacao("u1", REC), audio)

    def test_bloco_do_meio_perdido_vira_lacuna(self):
        partes = cortar(gerar_webm(2.0), 4)
        self.iniciar()
        for seq in (0, 1, 3):
            self.bloco(seq, partes[seq])
        r = gravacao_store.encerrar_gravacao("u1", REC, ultima_sequence=3)
        self.assertEqual((r["lacunas"], r["integridade"]), ([2], "erro"))

    def test_sem_o_bloco_0_nao_ha_cabecalho(self):
        partes = cortar(gerar_webm(2.0), 4)
        self.iniciar()
        self.bloco(1, partes[1])
        r = gravacao_store.encerrar_gravacao("u1", REC, ultima_sequence=1)
        self.assertIn("bloco 0", r["integridade_detalhe"])

    def test_fim_da_gravacao_perdido_aparece_pela_ultima_sequencia_declarada(self):
        partes = cortar(gerar_webm(2.0), 4)
        self.iniciar()
        for seq in (0, 1):
            self.bloco(seq, partes[seq])
        r = gravacao_store.encerrar_gravacao("u1", REC, ultima_sequence=3)
        self.assertEqual(r["lacunas"], [2, 3])

    def _outro_worker_grava_antes(self, conteudo_do_outro: bytes):
        """O outro worker grava a sequência 0 entre a checagem e o INSERT."""
        original = regras.caminho_do_bloco

        def no_meio(*a, **kw):
            caminho = original(*a, **kw)
            h = regras.hash_do_conteudo(conteudo_do_outro)
            arquivo = caminho.with_name(f"{caminho.stem}-{h[:12]}.webm")
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            arquivo.write_bytes(conteudo_do_outro)
            with Session(self.engine) as s:
                s.add(GravacaoBloco(recording_id=REC, sequence=0, start_ms=1, end_ms=2, content_hash=h,
                                    tamanho=len(conteudo_do_outro), caminho=str(arquivo)))
                s.commit()
            return caminho

        return patch.object(regras, "caminho_do_bloco", no_meio)

    def test_dois_workers_mesmo_bloco_ao_mesmo_tempo(self):
        self.iniciar()
        parte = cortar(gerar_webm(1.0), 2)[0]
        with self._outro_worker_grava_antes(parte):
            r = self.bloco(0, parte)
        self.assertTrue(r["duplicado"])
        with Session(self.engine) as s:
            self.assertEqual(len(s.exec(select(GravacaoBloco)).all()), 1)
        arquivos = list(self.pasta.rglob("*.webm"))
        self.assertEqual([a.read_bytes() for a in arquivos], [parte])  # mesmo nome, mesmo conteúdo

    def test_dois_workers_versoes_diferentes_da_mesma_sequencia(self):
        self.iniciar()
        with self._outro_worker_grava_antes(b"versao-do-outro" * 10):
            with self.assertRaises(gravacao_store.GravacaoErro) as e:
                self.bloco(0, b"minha-versao" * 10)
        self.assertEqual(e.exception.status, 409)
        arquivos = list(self.pasta.rglob("*.webm"))
        self.assertEqual([a.read_bytes() for a in arquivos], [b"versao-do-outro" * 10])  # o meu foi apagado

    def test_gravacao_de_outra_pessoa_nao_aparece(self):
        self.iniciar("u1")
        with self.assertRaises(gravacao_store.GravacaoErro) as e:
            self.bloco(0, b"x" * 50, usuario="u2")
        self.assertEqual(e.exception.status, 404)
        with self.assertRaises(gravacao_store.GravacaoErro):
            gravacao_store.audio_da_gravacao("u2", REC)
        self.assertEqual(gravacao_store.audio_da_gravacao("u2", REC, admin=True), b"")

    def test_iniciar_de_novo_e_idempotente(self):
        self.assertFalse(self.iniciar()["ja_existia"])
        self.assertTrue(self.iniciar()["ja_existia"])

    def test_bloco_depois_de_encerrar_e_recusado(self):
        self.iniciar()
        gravacao_store.encerrar_gravacao("u1", REC)
        with self.assertRaises(gravacao_store.GravacaoErro) as e:
            self.bloco(0, b"x" * 50)
        self.assertEqual(e.exception.status, 409)

    def test_cada_bloco_fica_na_pasta_da_sua_reuniao_e_trilha(self):
        self.iniciar(rec="rec-mic-0001", trilha="microfone")
        self.bloco(0, b"y" * 50, rec="rec-mic-0001")
        arquivos = list(self.pasta.rglob("*.webm"))
        self.assertEqual(arquivos[0].relative_to(self.pasta).parts[:3], (MEETING, "microfone", "rec-mic-0001"))

    def test_retencao_apaga_audio_vencido(self):
        self.iniciar()
        self.bloco(0, cortar(gerar_webm(1.0), 2)[0])
        gravacao_store.encerrar_gravacao("u1", REC)
        r = gravacao_store.manutencao(agora=datetime.now() + timedelta(days=91))
        self.assertEqual(r["apagadas"], 1)
        self.assertEqual(list(self.pasta.rglob("*.webm")), [])
        with self.assertRaises(gravacao_store.GravacaoErro) as e:
            gravacao_store.audio_da_gravacao("u1", REC)
        self.assertEqual(e.exception.status, 410)

    def test_gravacao_abandonada_e_encerrada(self):
        partes = cortar(gerar_webm(1.0), 2)
        self.iniciar()
        for seq, parte in enumerate(partes):
            self.bloco(seq, parte)
        r = gravacao_store.manutencao(agora=datetime.now() + timedelta(minutes=31))
        self.assertEqual(r["encerradas_por_abandono"], 1)
        with Session(self.engine) as s:
            g = s.exec(select(GravacaoAudio)).first()
        self.assertEqual((g.status, g.integridade), ("encerrada", "ok"))


class TestRotas(_Base):
    def setUp(self):
        super().setUp()
        from fastapi.testclient import TestClient
        import api.main as main

        self.main = main
        main._RATE_LIMIT_CHAMADAS.clear()
        self.client = TestClient(main.app)
        self.token = main._gerar_token("u1", "vendedor@saleia.app.br", "vendedor")

    def _h(self, token=None):
        return {"Authorization": f"Bearer {token or self.token}"}

    def _iniciar(self, **extra):
        corpo = {"meeting_id": MEETING, "track_id": "aba", "recording_id": REC,
                 "codec": "audio/webm;codecs=opus", "sample_rate": 48000, "consentimento": True}
        corpo.update(extra)
        return self.client.post("/gravacao/iniciar", json=corpo, headers=self._h())

    def test_desligada_por_padrao(self):
        with patch.dict(os.environ, {"GRAVACAO_AUDIO_ENABLED": "false"}):
            self.assertFalse(self.client.get("/gravacao/config").json()["habilitada"])
            self.assertEqual(self._iniciar().status_code, 403)

    def test_fluxo_completo_e_audio_reproduzivel(self):
        audio = gerar_webm(2.0)
        with patch.dict(os.environ, {"GRAVACAO_AUDIO_ENABLED": "true"}):
            self.assertEqual(self.client.post("/gravacao/iniciar", json={
                "meeting_id": MEETING, "track_id": "aba", "recording_id": REC, "consentimento": True,
            }).status_code, 401)  # sem login
            self.assertEqual(self._iniciar(consentimento=False).status_code, 400)
            self.assertEqual(self._iniciar().status_code, 200)
            for seq, parte in enumerate(cortar(audio, 3)):
                r = self.client.post("/gravacao/bloco", headers=self._h(), json={
                    "recording_id": REC, "sequence": seq, "start_ms": 1000 + seq * 5000,
                    "end_ms": 6000 + seq * 5000, "content_hash": regras.hash_do_conteudo(parte),
                    "recorded_at": "2026-10-11T15:00:00Z",
                    "audio_base64": "data:audio/webm;base64," + base64.b64encode(parte).decode()})
                self.assertEqual(r.status_code, 200, r.text)
            r = self.client.post("/gravacao/encerrar", headers=self._h(),
                                 json={"recording_id": REC, "ultima_sequence": 2})
            self.assertEqual(r.json()["integridade"], "ok")
            baixado = self.client.get(f"/gravacao/{REC}/audio", headers=self._h())
            self.assertEqual((baixado.status_code, baixado.content), (200, audio))
            outro = self.main._gerar_token("u2", "outro@saleia.app.br", "vendedor")
            self.assertEqual(self.client.get(f"/gravacao/{REC}/audio", headers=self._h(outro)).status_code, 404)

    def test_hash_errado_e_base64_invalido(self):
        with patch.dict(os.environ, {"GRAVACAO_AUDIO_ENABLED": "true"}):
            self._iniciar()
            base = {"recording_id": REC, "sequence": 0, "start_ms": 1, "end_ms": 2}
            r = self.client.post("/gravacao/bloco", headers=self._h(), json={
                **base, "content_hash": "0" * 64, "audio_base64": base64.b64encode(b"abc").decode()})
            self.assertEqual(r.status_code, 400)
            r = self.client.post("/gravacao/bloco", headers=self._h(), json={
                **base, "content_hash": "0" * 64, "audio_base64": "@@@"})
            self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
