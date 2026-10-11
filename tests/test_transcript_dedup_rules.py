"""Tarefa A1 — deduplicação idempotente de fragmentos de transcrição.

Exemplos reais (anonimizados na forma, mesma estrutura) das 12 reuniões
de produção analisadas em 24/09/2026.
"""

import unittest
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

from agent.transcript_dedup_rules import compactar_transcricao, corpo_normalizado, deduplicar_fragmento, eh_duplicata

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
