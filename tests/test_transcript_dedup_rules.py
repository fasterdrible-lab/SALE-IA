"""Tarefa A1 — deduplicação idempotente de fragmentos de transcrição.

Exemplos reais (anonimizados na forma, mesma estrutura) das 12 reuniões
de produção analisadas em 24/09/2026.
"""

import unittest
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

from agent.transcript_dedup_rules import (
    coberta_pela_outra_fonte, compactar_transcricao, corpo_normalizado, deduplicar_fragmento, eh_duplicata,
)

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

    def test_identica_longe_e_repeticao_real_e_fica(self):
        # Auditoria T01 (P7): antes, cópia exata em 80 linhas era descartada
        # — e o cliente insistindo numa objeção sumia. Só a colada (≤6) sai.
        recentes = [LEGENDA] + [f"Cliente: fala intermediária número {i} bem diferente" for i in range(40)]
        self.assertFalse(eh_duplicata(LEGENDA, recentes))

    def test_identica_colada_e_artefato(self):
        recentes = [LEGENDA, "Cliente: fala intermediária bem diferente aqui"]
        self.assertTrue(eh_duplicata(LEGENDA, recentes))

    def test_com_corpos_de_audio_so_junta_a_versao_do_audio(self):
        # P8: duas pessoas dizendo quase a mesma coisa ficam.
        outra_pessoa = "Bruno: Caraca vocês estão botando um bichinho para trabalhar então hein"
        self.assertFalse(eh_duplicata(outra_pessoa, [LEGENDA], corpos_audio=set()))
        self.assertTrue(eh_duplicata(WHISPER, [LEGENDA], corpos_audio={corpo_normalizado(WHISPER)}))


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


class LegendaEAudioCortadosDiferenteTest(unittest.TestCase):
    """V.1.4.178 — reunião real de 14/10: o áudio junta ~15s numa linha e a
    legenda quebra a mesma fala em pedaços; as duas versões entravam."""

    LEGENDA_1 = "Não identificado: Faz um tempinho faz um tempinho porque eu não tinha nem filho. Então faz pelo"
    LEGENDA_2 = "Não identificado: menos quatro anos que eu não fui faz uns cinco anos que eu fui."
    AUDIO = ("Cliente: Faz um tempinho, faz um tempinho porque eu não tinha nem filho. "
             "Então faz pelo menos quatro anos que eu não fui. É, faz uns cinco anos.")
    AUDIO_NOVO = "Cliente: O custo disso para mim foi oito mil reais, pagos no pix, na mesma semana."

    def _audio(self, *linhas):
        return {corpo_normalizado(l) for l in linhas}

    def test_audio_que_a_legenda_ja_trouxe_e_descartado(self):
        filtrado, descartadas = deduplicar_fragmento(
            f"{self.LEGENDA_1}\n{self.LEGENDA_2}", self.AUDIO, corpos_audio=self._audio(self.AUDIO)
        )
        self.assertEqual((filtrado, descartadas), ("", 1))

    def test_legenda_que_o_audio_ja_trouxe_e_descartada(self):
        filtrado, _ = deduplicar_fragmento(
            self.AUDIO, f"{self.LEGENDA_1}\n{self.LEGENDA_2}", corpos_audio=self._audio(self.AUDIO)
        )
        self.assertEqual(filtrado, "")

    def test_audio_com_conteudo_novo_fica(self):
        filtrado, descartadas = deduplicar_fragmento(
            f"{self.LEGENDA_1}\n{self.LEGENDA_2}", self.AUDIO_NOVO, corpos_audio=self._audio(self.AUDIO_NOVO)
        )
        self.assertEqual((filtrado, descartadas), (self.AUDIO_NOVO, 0))

    def test_sem_audio_na_reuniao_nada_muda(self):
        # Duas falas da legenda nunca são juntadas por cobertura (P8).
        base = "Ana: Nosso maior problema hoje é o follow-up dos leads que se perde."
        outra = "Bruno: O maior problema hoje é o follow-up dos leads que se perde mesmo."
        filtrado, _ = deduplicar_fragmento(base, outra, corpos_audio=set())
        self.assertEqual(filtrado, outra)

    def test_duas_falas_do_audio_nunca_sao_juntadas_por_cobertura(self):
        # Mesmas palavras, ordem e frase diferentes: só a cobertura pegaria.
        a1 = "Cliente: Nosso problema maior hoje é perder leads quando falta follow-up rápido."
        a2 = "Vendedor: Quando falta follow-up rápido, vocês perdem leads? Esse é o problema maior hoje?"
        self.assertFalse(coberta_pela_outra_fonte(a2, [a1], self._audio(a1, a2)))
        filtrado, _ = deduplicar_fragmento(a1, a2, corpos_audio=self._audio(a1, a2))
        self.assertEqual(filtrado, a2)

    def test_fala_curta_nunca_e_descartada_por_cobertura(self):
        filtrado, _ = deduplicar_fragmento(
            "Não identificado: Tudo bem e você", "Cliente: Tudo bem, e você?",
            corpos_audio=self._audio("Cliente: Tudo bem, e você?"),
        )
        self.assertEqual(filtrado, "Cliente: Tudo bem, e você?")


class BlocoReenviadoLongeDoFimTest(unittest.TestCase):
    """V.1.4.178 — servidor lento em 14/10: o pedido preso foi gravado
    minutos depois do reenvio e o bloco repetido caiu longe do fim."""

    BLOCO = [
        "Cliente: Aí é um saco, né? Aí eu fui tirar visto para a viagem.",
        "Não identificado: Aí eu fui tirar visto só nada muito sério nada para visitar.",
        "Não identificado: Entendi, você veio para qual região aqui de São Paulo?",
    ]

    def _meio(self, n):
        return [f"Não identificado: fala intermediária número {i} sobre outro assunto." for i in range(n)]

    def test_bloco_repetido_longe_do_fim_e_descartado(self):
        base = "\n".join(self.BLOCO + self._meio(30))
        nova = "Cliente: Para a capital mesmo, ficamos uma semana inteira lá."
        filtrado, descartadas = deduplicar_fragmento(base, "\n".join(self.BLOCO + [nova]))
        self.assertEqual((filtrado, descartadas), (nova, 3))

    def test_objecao_repetida_sozinha_fica(self):
        # P7: o cliente insistindo é uma linha só, não um bloco.
        objecao = "Cliente: Mas olha, sinceramente, eu acho que está caro para o momento."
        base = "\n".join([objecao] + self._meio(30))
        filtrado, _ = deduplicar_fragmento(base, objecao)
        self.assertEqual(filtrado, objecao)

    def test_respostas_curtas_seguidas_nao_formam_bloco(self):
        base = "\n".join(["Cliente: Sim.", "Vendedor: Perfeito."] + self._meio(10))
        filtrado, _ = deduplicar_fragmento(base, "Cliente: Sim.\nVendedor: Perfeito.")
        self.assertEqual(filtrado.splitlines(), ["Cliente: Sim.", "Vendedor: Perfeito."])

    def test_bloco_alem_da_janela_fica(self):
        base = "\n".join(self.BLOCO + self._meio(400))
        filtrado, _ = deduplicar_fragmento(base, "\n".join(self.BLOCO))
        self.assertEqual(len(filtrado.splitlines()), 3)


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
        # Fluxo real: /audio-transcricao registra o texto do áudio antes de
        # ele voltar pela extensão com rótulo de falante (P8).
        self._database.registrar_transcricao_audio("abc-defg-hij", WHISPER.split(": ", 1)[1])
        self._database.registrar_transcricao_meeting("abc-defg-hij", LEGENDA)
        r = self._database.registrar_transcricao_meeting(
            "abc-defg-hij", f"{WHISPER}\nCliente: Nosso maior problema é o follow-up que se perde."
        )
        self.assertNotIn("Paulo:", r["transcript_full"])
        self.assertIn("follow-up que se perde", r["transcript_full"])
        self.assertEqual(r["fragmento_aceito"], "Cliente: Nosso maior problema é o follow-up que se perde.")

    def test_audio_cortado_diferente_da_legenda_nao_duplica(self):
        audio = LegendaEAudioCortadosDiferenteTest.AUDIO
        self._database.registrar_transcricao_audio("abc-defg-hij", audio.split(": ", 1)[1])
        self._database.registrar_transcricao_meeting(
            "abc-defg-hij",
            f"{LegendaEAudioCortadosDiferenteTest.LEGENDA_1}\n{LegendaEAudioCortadosDiferenteTest.LEGENDA_2}",
        )
        r = self._database.registrar_transcricao_meeting("abc-defg-hij", audio)
        self.assertEqual(r["fragmento_aceito"], "")
        self.assertNotIn("Cliente:", r["transcript_full"])

    def test_substituir_nao_passa_pela_dedup(self):
        self._database.registrar_transcricao_meeting("abc-defg-hij", LEGENDA)
        r = self._database.registrar_transcricao_meeting("abc-defg-hij", LEGENDA, substituir=True)
        self.assertEqual(r["transcript_full"], LEGENDA)


class CompactarTranscricaoTest(unittest.TestCase):
    """06/10/2026 — casos reais das reuniões de 05/10."""

    def test_legenda_crescendo_fica_so_a_versao_completa(self):
        texto = (
            "João: Cara a minha esposa.\n"
            "João: Cara. A minha esposa ela é fis.\n"
            "João: Cara A minha esposa ela é fisioterapeuta. Então a gente tem cada uma sua vida.\n"
            "João: Entendi então se você tomar uma decisão aqui comigo hoje o casamento está de pé."
        )
        self.assertEqual(compactar_transcricao(texto).splitlines(), [
            "João: Cara A minha esposa ela é fisioterapeuta. Então a gente tem cada uma sua vida.",
            "João: Entendi então se você tomar uma decisão aqui comigo hoje o casamento está de pé.",
        ])

    def test_css_do_meet_e_removido_mas_fala_com_ponto_e_virgula_fica(self):
        texto = (
            "box-shadow: var(--ink-form-field-focus-box-shadow, 0 0 0 2px black);\n"
            "position: absolute;\n"
            "}\n"
            ".caption-x {\n"
            "Paulo: vamos lá;\n"
            "João: Hoje o primeiro passo que a gente vai executar com você."
        )
        self.assertEqual(compactar_transcricao(texto).splitlines(), [
            "Paulo: vamos lá;",
            "João: Hoje o primeiro passo que a gente vai executar com você.",
        ])

    def test_parcial_de_outro_falante_nao_e_removida(self):
        texto = "Cliente: Está caro.\nVendedor: Está caro em relação a quê exatamente?"
        self.assertEqual(len(compactar_transcricao(texto).splitlines()), 2)

    def test_fala_curta_repetida_e_legitima(self):
        texto = "Cliente: Perfeito.\nVendedor: Então seguimos com a proposta?\nCliente: Perfeito."
        self.assertEqual(len(compactar_transcricao(texto).splitlines()), 3)

    def test_repeticao_exata_longa_e_removida(self):
        linha = "João: Então tá bom, tá marcado para quinta-feira às 8 horas da manhã."
        self.assertEqual(compactar_transcricao(f"{linha}\nPaulo: Combinado.\n{linha}").splitlines(),
                         [linha, "Paulo: Combinado."])

    def test_parcial_longe_demais_nao_e_tocada(self):
        linhas = ["João: Ó Ricardo."] + [f"Paulo: fala número {i} sobre outro assunto qualquer." for i in range(7)]
        linhas.append("João: Ó Ricardo, tá vendo o seu painel aqui?")
        self.assertIn("João: Ó Ricardo.", compactar_transcricao("\n".join(linhas)).splitlines())

    def test_texto_vazio(self):
        self.assertEqual(compactar_transcricao(""), "")
        self.assertEqual(compactar_transcricao(None), "")


class LimparTranscricaoProcessadorTest(unittest.TestCase):
    def test_aviso_do_meet_e_compactacao_no_texto_que_vai_para_a_ia(self):
        from api.processador_tempo_real import _limitar_contexto_ia

        texto = (
            "João: Sua apresentação foi adicionada à tela principal. Sua apresentação está na tela principal.\n"
            "João: Ó Ricardo.\n"
            "João: Ó, Ricardo, tá vendo o seu painel aqui do lado?"
        )
        self.assertEqual(_limitar_contexto_ia(texto), "João: Ó, Ricardo, tá vendo o seu painel aqui do lado?")


if __name__ == "__main__":
    unittest.main()
