import json
import unittest
from datetime import datetime, timedelta

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from agent.transcricao_definitiva_rules import (
    ESPERA_COTA_DIA_S,
    ESPERA_COTA_HORA_S,
    eh_silencio,
    espera_por_cota,
    filtrar_segmentos,
)
from api.database import GravacaoAudio, TranscricaoDefinitiva
from scripts import transcrever_gravacoes as tg

AGORA = datetime(2026, 11, 4, 12, 0, 0)


class RegrasTest(unittest.TestCase):
    def test_silencio_so_com_medicao_abaixo_do_limiar(self):
        self.assertTrue(eh_silencio(-91.0))
        self.assertFalse(eh_silencio(-20.0))
        self.assertFalse(eh_silencio(None))

    def test_filtra_vazio_e_trecho_sem_fala(self):
        limpos = filtrar_segmentos([
            {"start": 0, "end": 2, "text": " Bom dia ", "no_speech_prob": 0.1},
            {"start": 2, "end": 4, "text": "Obrigado.", "no_speech_prob": 0.9},
            {"start": 4, "end": 5, "text": "   ", "no_speech_prob": 0},
        ])
        self.assertEqual(limpos, [{"inicio": 0.0, "fim": 2.0, "texto": "Bom dia"}])

    def test_espera_por_cota(self):
        self.assertEqual(espera_por_cota(0, 0, 600), 0)
        self.assertEqual(espera_por_cota(6800, 6800, 600), ESPERA_COTA_HORA_S)
        self.assertEqual(espera_por_cota(0, 28500, 600), ESPERA_COTA_DIA_S)


class Erro429(Exception):
    def __init__(self, headers):
        super().__init__("rate limit")
        self.response = type("R", (), {"status_code": 429, "headers": headers})()


class ProcessarTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(self.engine)
        self.esperas = []

    def _gravacao(self, rid, apagar_dias=10, meeting="abc", **extra):
        dados = dict(recording_id=rid, meeting_id=meeting, track_id="aba", usuario_id="u1", consentimento_texto="ok",
                     consentimento_em=AGORA, iniciada_em=AGORA - timedelta(days=5), status="encerrada",
                     integridade="ok", duracao_s=600.0, apagar_em=AGORA + timedelta(days=apagar_dias))
        dados.update(extra)
        with Session(self.engine) as s:
            s.add(GravacaoAudio(**dados))
            s.commit()

    def _linhas(self):
        with Session(self.engine) as s:
            return {x.recording_id: x for x in s.exec(select(TranscricaoDefinitiva)).all()}

    def _rodar(self, transcrever, medir=lambda c: -10.0, reunioes=("abc",)):
        return tg.processar(self.engine, list(reunioes), transcrever=transcrever, medir=medir,
                            montar=lambda e, r: None, dormir=self.esperas.append, agora=lambda: AGORA)

    def test_grava_texto_e_nao_repete_na_segunda_passada(self):
        self._gravacao("r1")
        chamadas = []

        def transcrever(_):
            chamadas.append(1)
            return [{"start": 1, "end": 2, "text": "quanto custa", "no_speech_prob": 0}]

        self.assertEqual(self._rodar(transcrever)["ok"], 1)
        self.assertEqual(self._rodar(transcrever)["ok"], 0)
        self.assertEqual(len(chamadas), 1)
        linha = self._linhas()["r1"]
        self.assertEqual((linha.status, linha.texto, linha.trilha), ("ok", "quanto custa", "aba"))
        self.assertEqual(json.loads(linha.segmentos_json)[0]["inicio"], 1.0)

    def test_silencio_nao_gasta_cota(self):
        self._gravacao("r1")
        resultado = self._rodar(lambda _: self.fail("não deveria enviar"), medir=lambda c: -91.0)
        self.assertEqual(resultado["silencio"], 1)
        self.assertEqual(self._linhas()["r1"].status, "silencio")

    def test_ignora_outra_reuniao_vencida_e_sem_integridade(self):
        self._gravacao("outra", meeting="xyz")
        self._gravacao("vencida", apagar_dias=-1)
        self._gravacao("ruim", integridade="erro")
        self.assertEqual(self._rodar(lambda _: [])["ok"], 0)
        self.assertEqual(self._linhas(), {})

    def test_vencimento_mais_proximo_primeiro(self):
        self._gravacao("depois", apagar_dias=18)
        self._gravacao("antes", apagar_dias=14)
        self.assertEqual([g.recording_id for g in tg.pendentes(self.engine, ["abc"], AGORA)], ["antes", "depois"])

    def test_erro_nao_para_as_outras_e_volta_a_ser_tentado(self):
        self._gravacao("r1", apagar_dias=1)
        self._gravacao("r2", apagar_dias=2)
        respostas = [RuntimeError("falhou"), []]

        def transcrever(_):
            r = respostas.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        self.assertEqual(self._rodar(transcrever), {"ok": 1, "silencio": 0, "erro": 1})
        self.assertIn("RuntimeError", self._linhas()["r1"].detalhe)
        self.assertEqual(self._rodar(lambda _: [])["ok"], 1)
        self.assertEqual(self._linhas()["r1"].status, "ok")

    def test_429_espera_o_tempo_pedido_e_repete(self):
        self._gravacao("r1")
        respostas = [Erro429({"retry-after": "120"}), [{"start": 0, "end": 1, "text": "oi", "no_speech_prob": 0}]]

        def transcrever(_):
            r = respostas.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        self.assertEqual(self._rodar(transcrever)["ok"], 1)
        self.assertEqual(self.esperas, [120])

    def test_429_sem_header_usa_espera_padrao(self):
        self.assertEqual(tg._espera_do_429(Erro429({})), tg.ESPERA_429_PADRAO_S)
        self.assertIsNone(tg._espera_do_429(RuntimeError("x")))


if __name__ == "__main__":
    unittest.main()
