"""Tarefa A1 — deduplicação idempotente de fragmentos de transcrição.

Exemplos reais (anonimizados na forma, mesma estrutura) das 12 reuniões
de produção analisadas em 24/09/2026.
"""

import unittest
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

from agent.transcript_dedup_rules import corpo_normalizado, deduplicar_fragmento, eh_duplicata

LEGENDA = "Felipe: Caraca vocês estão botando um bichinho para trabalhar então, hein?"
WHISPER = "Paulo: Caraca, vocês estão botando bichinho pra trabalhar, então hein? Caraca!"


class CorpoNormalizadoTest(unittest.TestCase):
    def test_remove_rotulo_pontuacao_e_caixa(self):
        self.assertEqual(corpo_normalizado("Felipe: Olá, TUDO bem?"), "olá tudo bem")

    def test_linha_sem_rotulo(self):
        self.assertEqual(corpo_normalizado("apenas texto."), "apenas texto")


class EhDuplicataTest(unittest.TestCase):
    def test_mesma_fala_duas_fontes_rotulo_diferente(self):
        self.assertTrue(eh_duplicata(WHISPER, [LEGENDA]))

    def test_linha_identica(self):
        self.assertTrue(eh_duplicata(LEGENDA, [LEGENDA]))

    def test_fala_diferente_nao_e_duplicata(self):
        self.assertFalse(eh_duplicata("Paulo: Qual é o orçamento mensal de vocês hoje?", [LEGENDA]))

    def test_fala_curta_repetida_nunca_descartada(self):
        self.assertFalse(eh_duplicata("Felipe: Sim, perfeito.", ["Felipe: Sim, perfeito."]))

    def test_similar_fora_da_janela_curta_nao_descartada(self):
        recentes = [LEGENDA] + [f"Cliente: fala intermediária número {i} bem diferente" for i in range(20)]
        self.assertFalse(eh_duplicata(WHISPER, recentes))

    def test_identica_na_janela_longa_descartada(self):
        recentes = [LEGENDA] + [f"Cliente: fala intermediária número {i} bem diferente" for i in range(40)]
        self.assertTrue(eh_duplicata(LEGENDA, recentes))


class DeduplicarFragmentoTest(unittest.TestCase):
    def test_reenvio_do_mesmo_delta_inteiro_descartado(self):
        delta = "\n".join([
            "Felipe: Foi lá a viagem de vocês, a visita na feira, me conta mais.",
            "Cliente: Foi ótima, fechamos com dois fornecedores novos na feira.",
        ])
        base, _ = deduplicar_fragmento("", delta)
        filtrado, descartadas = deduplicar_fragmento(base, delta)
        self.assertEqual(filtrado, "")
        self.assertEqual(descartadas, 2)

    def test_mantem_linhas_novas_e_ordem(self):
        base = LEGENDA
        frag = "\n".join([WHISPER, "Cliente: A gente tem três pessoas no time comercial hoje.", "Felipe: Sim."])
        filtrado, descartadas = deduplicar_fragmento(base, frag)
        self.assertEqual(descartadas, 1)
        self.assertEqual(filtrado.splitlines(), [
            "Cliente: A gente tem três pessoas no time comercial hoje.",
            "Felipe: Sim.",
        ])

    def test_duplicata_dentro_do_proprio_fragmento(self):
        frag = "\n".join([LEGENDA, WHISPER])
        filtrado, descartadas = deduplicar_fragmento("", frag)
        self.assertEqual((filtrado, descartadas), (LEGENDA, 1))

    def test_base_com_separador_de_paragrafo(self):
        base = f"{LEGENDA}\n\nCliente: outra fala qualquer do cliente aqui"
        filtrado, descartadas = deduplicar_fragmento(base, WHISPER)
        self.assertEqual((filtrado, descartadas), ("", 1))

    def test_fragmento_vazio(self):
        self.assertEqual(deduplicar_fragmento(LEGENDA, ""), ("", 0))


class RegistrarTranscricaoIdempotenteTest(unittest.TestCase):
    def setUp(self):
        import api.database as database

        self._database = database
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)
        p = patch.object(database, "engine", engine)
        p.start()
        self.addCleanup(p.stop)

    def test_reenvio_nao_duplica_transcript_full(self):
        delta = f"{LEGENDA}\nCliente: A gente tem três pessoas no time comercial hoje."
        self._database.registrar_transcricao_meeting("abc-defg-hij", delta)
        r = self._database.registrar_transcricao_meeting("abc-defg-hij", delta)
        self.assertEqual(r["fragmento_aceito"], "")
        self.assertEqual(r["transcript_full"].count("três pessoas"), 1)

    def test_segunda_fonte_descartada_e_nova_fala_mantida(self):
        self._database.registrar_transcricao_meeting("abc-defg-hij", LEGENDA)
        r = self._database.registrar_transcricao_meeting(
            "abc-defg-hij", f"{WHISPER}\nCliente: Nosso maior problema é o follow-up que se perde."
        )
        self.assertNotIn("Paulo:", r["transcript_full"])
        self.assertIn("follow-up que se perde", r["transcript_full"])
        self.assertEqual(r["fragmento_aceito"], "Cliente: Nosso maior problema é o follow-up que se perde.")

    def test_substituir_nao_passa_pela_dedup(self):
        self._database.registrar_transcricao_meeting("abc-defg-hij", LEGENDA)
        r = self._database.registrar_transcricao_meeting("abc-defg-hij", LEGENDA, substituir=True)
        self.assertEqual(r["transcript_full"], LEGENDA)


if __name__ == "__main__":
    unittest.main()
