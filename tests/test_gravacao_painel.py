"""
Testes — painel de gravações do Dashboard (fase 1: ouvir e comparar;
fase 2: trechos de referência com WER). Pedido de 12/10/2026.

Banco SQLite e pasta temporários; o nome dos vendedores (MySQL) é
substituído — nada toca produção.

Run:
    python -m unittest tests.test_gravacao_painel -v
"""

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

from agent import gravacao_revisao_rules as rr
from agent import gravacao_rules as regras
from api import database, gravacao_painel, gravacao_store
from api.database import GravacaoNivel, MeetingMemory

MEETING = "abc-defg-hij"
T0 = datetime(2026, 10, 12, 14, 0, 0)


def gerar_webm(segundos: float, amplitude: int = 8000) -> bytes:
    buf = io.BytesIO()
    saida = av.open(buf, "w", format="webm")
    stream = saida.add_stream("libopus", rate=48000)
    t = np.arange(960)
    for i in range(int(segundos * 50)):
        amostras = (np.sin((t + i * 960) * 2 * np.pi * 440 / 48000) * amplitude).astype("int16")
        frame = av.AudioFrame.from_ndarray(amostras.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = 48000
        frame.pts = i * 960
        for pacote in stream.encode(frame):
            saida.mux(pacote)
    for pacote in stream.encode(None):
        saida.mux(pacote)
    saida.close()
    return buf.getvalue()


class TestRegras(unittest.TestCase):
    def g(self, rid, minutos, dur_min=10, meeting=MEETING, trilha="aba"):
        ini = T0 + timedelta(minutes=minutos)
        return {"recording_id": rid, "meeting_id": meeting, "track_id": trilha,
                "inicio": ini, "fim": ini + timedelta(minutes=dur_min)}

    def test_rotacoes_e_trilhas_viram_uma_sessao_e_sala_reusada_horas_depois_outra(self):
        sessoes = rr.agrupar_sessoes([
            self.g("a1", 0), self.g("m1", 0, trilha="microfone"), self.g("a2", 10),
            self.g("a3", 300),  # mesma sala 4h50 depois
            self.g("x1", 5, meeting="xyz-wxyz-xyz"),
        ])
        self.assertEqual([(s["sessao_id"], len(s["gravacoes"])) for s in sessoes], [("a1", 3), ("x1", 1), ("a3", 1)])
        self.assertEqual(sessoes[0]["fim"], T0 + timedelta(minutes=20))

    def test_transcricao_da_reuniao_certa_na_sala_recorrente(self):
        antiga = {"meeting_id": MEETING + "#202610051400-1", "created_at": T0 - timedelta(days=7),
                  "updated_at": T0 - timedelta(days=7, hours=-1)}
        atual = {"meeting_id": MEETING, "created_at": T0 - timedelta(minutes=2), "updated_at": T0 + timedelta(minutes=50)}
        self.assertIs(rr.escolher_memoria([antiga, atual], T0, T0 + timedelta(hours=1)), atual)
        self.assertIsNone(rr.escolher_memoria([antiga], T0, T0 + timedelta(hours=1)))  # nunca a de outra reunião

    def test_wer_ignora_rotulo_caixa_e_pontuacao_mas_conta_acento(self):
        sistema = "Paulo: Bom dia, tudo bem?\nNão identificado: Esta caro."
        self.assertEqual(rr.medir_trecho("bom dia tudo bem está caro", sistema)["erros"], 1)  # esta × está
        self.assertEqual(rr.medir_trecho("Bom dia. Tudo bem?", "Paulo: bom dia tudo bem")["wer"], 0.0)
        r = rr.medir_trecho("um dois três quatro", "um três quatro cinco")
        self.assertEqual((r["deletions"], r["insertions"], r["wer"]), (1, 1, 0.5))

    def test_fala_com_dois_pontos_no_meio_nao_perde_palavras(self):
        self.assertEqual(rr.tirar_rotulos_de_falante("o valor fica assim: 20 mil"), "o valor fica assim: 20 mil")

    def test_wer_total_ponderado_pelas_palavras(self):
        r = rr.resumir_referencias([
            {"referencia_palavras": 100, "erros": 10, "inicio_s": 0, "fim_s": 60},
            {"referencia_palavras": 10, "erros": 5, "inicio_s": 60, "fim_s": 70},
        ])
        self.assertEqual((r["wer"], r["trechos"], r["segundos_revisados"]), (round(15 / 110, 4), 2, 70.0))
        self.assertIsNone(rr.resumir_referencias([])["wer"])

    def test_validacao_do_trecho(self):
        self.assertTrue(rr.validar_referencia(10, 5, "aba", "oi", ""))
        self.assertTrue(rr.validar_referencia(0, 5, "tela", "oi", ""))
        self.assertTrue(rr.validar_referencia(0, 5, "aba", "  ...  ", ""))
        self.assertEqual(rr.validar_referencia(0, 5, "ambas", "oi", "oi"), [])

    def test_painel_ligado_por_padrao_com_kill_switch(self):
        self.assertTrue(rr.painel_habilitado({}))
        self.assertFalse(rr.painel_habilitado({"GRAVACOES_PAINEL_ENABLED": "false"}))


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.engine = create_engine(f"sqlite:///{Path(self._tmp.name) / 'g.db'}")
        self.pasta = Path(self._tmp.name) / "gravacoes"
        for p in (patch.object(database, "engine", self.engine),
                  patch.dict(os.environ, {"GRAVACAO_DIR": str(self.pasta)}),
                  patch.object(gravacao_painel, "_nomes", lambda ids: {"u1": {"nome": "Vendedor Um"}})):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.engine.dispose)
        database.criar_tabelas()

    def gravar(self, rec, trilha, inicio_ms, audio, usuario="u1", partes=3, encerrar=True):
        gravacao_store.iniciar_gravacao(usuario, MEETING, trilha, rec, "audio/webm;codecs=opus", 48000, True)
        tam = -(-len(audio) // partes)
        pedacos = [audio[i:i + tam] for i in range(0, len(audio), tam)]
        passo = 5000
        for seq, p in enumerate(pedacos):
            gravacao_store.receber_bloco(usuario, rec, seq, inicio_ms + seq * passo, inicio_ms + (seq + 1) * passo,
                                         regras.hash_do_conteudo(p), p)
        if encerrar:
            gravacao_store.encerrar_gravacao(usuario, rec, ultima_sequence=len(pedacos) - 1)

    def memoria(self, texto, meeting=MEETING):
        agora = datetime.now()
        with Session(self.engine) as s:
            s.add(MeetingMemory(meeting_id=meeting, transcript_full=texto, provider_cost_estimate=0.0,
                                created_at=agora - timedelta(minutes=5), updated_at=agora + timedelta(minutes=5)))
            s.commit()


class TestPainel(_Base):
    def test_vendedor_ve_so_as_proprias_e_admin_ve_todas(self):
        self.gravar("rec-u1-aba", "aba", 1_000_000, gerar_webm(1.0))
        self.gravar("rec-u2-aba", "aba", 2_000_000, gerar_webm(1.0), usuario="u2")
        self.assertEqual([s["sessao_id"] for s in gravacao_painel.listar_sessoes("u1")], ["rec-u1-aba"])
        self.assertEqual(len(gravacao_painel.listar_sessoes("admin", admin=True)), 1)  # mesma sala → 1 sessão
        self.assertEqual(len(gravacao_painel.detalhe_sessao("admin", True, "rec-u1-aba")["trilhas"]["aba"]), 2)
        with self.assertRaises(gravacao_store.GravacaoErro) as e:
            gravacao_painel.detalhe_sessao("u2", False, "rec-u1-aba")
        self.assertEqual(e.exception.status, 404)

    def test_trilhas_na_mesma_linha_do_tempo_pelo_relogio_da_extensao(self):
        self.gravar("rec-aba-1", "aba", 1_000_000, gerar_webm(3.0))
        self.gravar("rec-mic-1", "microfone", 1_002_000, gerar_webm(3.0))  # começou 2s depois
        d = gravacao_painel.detalhe_sessao("u1", False, "rec-aba-1")
        self.assertEqual(d["trilhas"]["aba"][0]["offset_s"], 0.0)
        self.assertEqual(d["trilhas"]["microfone"][0]["offset_s"], 2.0)
        self.assertAlmostEqual(d["trilhas"]["aba"][0]["duracao_s"], 3.0, delta=0.1)
        self.assertEqual(d["inicio_relogio_ms"], 1_000_000)

    def test_volume_mostra_fala_e_silencio_e_fica_em_cache(self):
        self.gravar("rec-aba-1", "aba", 1_000_000, gerar_webm(4.0, amplitude=0))  # aba sem ninguém falando
        self.gravar("rec-mic-1", "microfone", 1_000_000, gerar_webm(4.0))
        d = gravacao_painel.detalhe_sessao("u1", False, "rec-aba-1")
        aba, mic = d["trilhas"]["aba"][0], d["trilhas"]["microfone"][0]
        self.assertIn(len(mic["niveis"]), (2, 3))  # janelas de 2s (o Opus estica um pouco o fim)
        self.assertGreater(min(mic["niveis"][:2]), -45)
        self.assertEqual(aba["som"]["com_som"], 0)
        self.assertGreaterEqual(mic["som"]["com_som"], 2)
        with Session(self.engine) as s:
            self.assertEqual(len(s.exec(select(GravacaoNivel)).all()), 2)
        with patch.object(gravacao_painel, "calcular_niveis", side_effect=AssertionError("recalculou")):
            gravacao_painel.detalhe_sessao("u1", False, "rec-aba-1")

    def test_gravacao_aberta_nao_entra_no_cache(self):
        self.gravar("rec-aba-1", "aba", 1_000_000, gerar_webm(2.0), encerrar=False)
        d = gravacao_painel.detalhe_sessao("u1", False, "rec-aba-1")
        self.assertEqual(d["trilhas"]["aba"][0]["status"], "gravando")
        with Session(self.engine) as s:
            self.assertEqual(s.exec(select(GravacaoNivel)).all(), [])

    def test_transcricao_da_mesma_reuniao(self):
        self.gravar("rec-aba-1", "aba", 1_000_000, gerar_webm(1.0))
        self.memoria("Paulo: bom dia\nCliente: bom dia")
        self.memoria("de outra reunião", meeting="xyz-wxyz-xyz")
        t = gravacao_painel.detalhe_sessao("u1", False, "rec-aba-1")["transcricao"]
        self.assertEqual((t["disponivel"], t["texto"]), (True, "Paulo: bom dia\nCliente: bom dia"))

    def test_gravacao_fechada_pela_manutencao_nao_estica_a_reuniao(self):
        self.gravar("rec-aba-1", "aba", 1_000_000, gerar_webm(2.0), encerrar=False)
        gravacao_store.iniciar_gravacao("u1", MEETING, "aba", "rec-aba-2", "audio/webm", 48000, True)  # nunca recebeu bloco
        depois = datetime.now() + timedelta(hours=2)
        gravacao_store.manutencao(agora=depois)  # fecha as 2 por abandono, 2h depois
        s = gravacao_painel.listar_sessoes("u1")[0]
        self.assertLess(s["duracao_s"], 60)

    def test_lista_resume_trilhas(self):
        self.gravar("rec-aba-1", "aba", 1_000_000, gerar_webm(2.0))
        s = gravacao_painel.listar_sessoes("u1")[0]
        self.assertEqual(s["vendedores"], ["Vendedor Um"])
        self.assertEqual((s["trilhas"]["aba"]["gravacoes"], s["trilhas"]["aba"]["lacunas"]), (1, 0))
        self.assertNotIn("microfone", s["trilhas"])


class TestReferencias(_Base):
    def setUp(self):
        super().setUp()
        self.gravar("rec-aba-1", "aba", 1_000_000, gerar_webm(1.0))

    DADOS = {"trilha": "ambas", "inicio_s": 0, "fim_s": 60,
             "texto_referencia": "bom dia tudo bem com você", "texto_sistema": "Paulo: bom dia tudo bem com voce"}

    def test_criar_mede_o_wer_e_entra_no_resumo(self):
        r = gravacao_painel.criar_referencia("u1", False, "rec-aba-1", dict(self.DADOS))
        self.assertEqual((r["erros"], r["referencia_palavras"], r["wer"]), (1, 6, round(1 / 6, 4)))
        d = gravacao_painel.detalhe_sessao("u1", False, "rec-aba-1")
        self.assertEqual(d["revisao"]["wer"], round(1 / 6, 4))
        self.assertEqual(d["referencias"][0]["autor"], "Vendedor Um")
        self.assertEqual(gravacao_painel.listar_sessoes("u1")[0]["revisao"]["trechos"], 1)

    def test_editar_remede_e_apagar_remove(self):
        r = gravacao_painel.criar_referencia("u1", False, "rec-aba-1", dict(self.DADOS))
        r2 = gravacao_painel.atualizar_referencia("u1", False, r["id"], {**self.DADOS, "texto_sistema": "bom dia tudo bem com você"})
        self.assertEqual(r2["wer"], 0.0)
        gravacao_painel.apagar_referencia("u1", False, r["id"])
        self.assertEqual(gravacao_painel.detalhe_sessao("u1", False, "rec-aba-1")["referencias"], [])

    def test_outro_vendedor_nao_ve_nem_altera_admin_pode(self):
        r = gravacao_painel.criar_referencia("u1", False, "rec-aba-1", dict(self.DADOS))
        for fn, args in ((gravacao_painel.criar_referencia, ("rec-aba-1", dict(self.DADOS))),
                         (gravacao_painel.apagar_referencia, (r["id"],))):
            with self.assertRaises(gravacao_store.GravacaoErro) as e:
                fn("u2", False, *args)
            self.assertEqual(e.exception.status, 404)
        gravacao_painel.apagar_referencia("admin", True, r["id"])

    def test_trecho_invalido_e_recusado(self):
        with self.assertRaises(gravacao_store.GravacaoErro) as e:
            gravacao_painel.criar_referencia("u1", False, "rec-aba-1", {**self.DADOS, "fim_s": 0})
        self.assertEqual(e.exception.status, 400)


class TestRotas(_Base):
    def setUp(self):
        super().setUp()
        from fastapi.testclient import TestClient
        import api.main as main

        self.client = TestClient(main.app)
        self.h = {"Authorization": "Bearer " + main._gerar_token("u1", "vendedor@saleia.app.br", "vendedor")}
        self.gravar("rec-aba-1", "aba", 1_000_000, gerar_webm(1.0))

    def test_fluxo_pelas_rotas(self):
        self.assertEqual(self.client.get("/gravacoes").status_code, 401)
        lista = self.client.get("/gravacoes", headers=self.h).json()
        self.assertEqual((lista["admin"], lista["sessoes"][0]["sessao_id"]), (False, "rec-aba-1"))
        self.assertEqual(self.client.get("/gravacoes/rec-aba-1", headers=self.h).status_code, 200)
        r = self.client.post("/gravacoes/rec-aba-1/referencias", headers=self.h, json=TestReferencias.DADOS)
        self.assertEqual(r.status_code, 200, r.text)
        rid = r.json()["id"]
        self.assertEqual(self.client.put(f"/gravacoes/referencias/{rid}", headers=self.h,
                                         json={**TestReferencias.DADOS, "fim_s": -1}).status_code, 400)
        self.assertEqual(self.client.delete(f"/gravacoes/referencias/{rid}", headers=self.h).status_code, 200)

    def test_kill_switch(self):
        with patch.dict(os.environ, {"GRAVACOES_PAINEL_ENABLED": "false"}):
            self.assertEqual(self.client.get("/gravacoes", headers=self.h).status_code, 403)


if __name__ == "__main__":
    unittest.main()
