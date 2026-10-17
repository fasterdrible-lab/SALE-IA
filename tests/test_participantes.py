"""
Testes — V.1.4.186 (ext 1.4.35): "quem é quem" da reunião
(agent/participantes_rules.py, /tempo-real, relatório automático).

Run:
    python -m unittest tests.test_participantes -v
"""
import asyncio
import json
import logging
import unittest
from unittest.mock import AsyncMock, patch

logging.disable(logging.CRITICAL)

from agent import participantes_rules as R  # noqa: E402

PEDRO_ANDRE = [
    {"nome_meet": "Você", "nome": "Pedro", "papel": "vendedor"},
    {"nome_meet": "fasterdrible", "nome": "André", "papel": "cliente"},
]


class NormalizarTest(unittest.TestCase):
    def test_limpa_papel_invalido_nome_vazio_e_repetidos(self):
        saida = R.normalizar_participantes([
            {"nome_meet": "Você", "nome": "  Pedro   Henrique ", "papel": "VENDEDOR"},
            {"nome_meet": "x", "nome": "", "papel": "chefe"},
            {"nome_meet": "", "nome": "", "papel": "cliente"},
            {"nome_meet": "y", "nome": "pedro henrique", "papel": "cliente"},
            "lixo",
        ])
        self.assertEqual(saida, [
            {"nome_meet": "Você", "nome": "Pedro Henrique", "papel": "vendedor"},
            {"nome_meet": "x", "nome": "x", "papel": ""},
        ])

    def test_entrada_invalida_vira_lista_vazia(self):
        for entrada in (None, "abc", {"a": 1}, 3):
            self.assertEqual(R.normalizar_participantes(entrada), [])

    def test_limites(self):
        muitos = [{"nome_meet": f"p{i}", "nome": str(i) + "N" * 200, "papel": "outro"} for i in range(50)]
        saida = R.normalizar_participantes(muitos)
        self.assertEqual(len(saida), R.MAX_PARTICIPANTES)
        self.assertTrue(all(len(p["nome"]) <= R.MAX_NOME for p in saida))


class CabecalhoTest(unittest.TestCase):
    def test_diz_quem_vende_e_quem_compra(self):
        cab = R.cabecalho_participantes(R.normalizar_participantes(PEDRO_ANDRE))
        self.assertIn("QUEM É QUEM NESTA REUNIÃO", cab)
        self.assertIn("- Pedro: VENDEDOR", cab)
        self.assertIn('- André (no Meet: "fasterdrible"): CLIENTE', cab)
        # Teste real 16/10: a pergunta sugerida chamava o VENDEDOR pelo nome.
        self.assertIn("PARA o cliente — chame o cliente de André, nunca pelo nome do vendedor", cab)
        self.assertTrue(cab.endswith("\n\n"))

    def test_prompts_dos_agentes_sem_vendedor_fixo(self):
        # Antes: "Paulo Henrique e sempre o vendedor" em todos os agentes.
        from pathlib import Path
        pasta = Path(__file__).resolve().parent.parent / "agent" / "prompt_templates"
        for nome in ("multiagente_coach.txt", "multiagente_closer.txt", "multiagente_disc.txt",
                     "multiagente_finance.txt", "multiagente_bigfive.txt", "agente_tempo_real.txt"):
            texto = (pasta / nome).read_text(encoding="utf-8")
            self.assertNotIn("Paulo", texto, nome)
            self.assertIn("QUEM É QUEM NESTA REUNIÃO", texto, nome)

    def test_sem_papel_de_ninguem_alem_do_vendedor_nao_manda_nada(self):
        # "Você = vendedor" é o padrão da extensão: a IA deduz pela conversa.
        so_vendedor = [{"nome_meet": "Você", "nome": "Pedro", "papel": "vendedor"},
                       {"nome_meet": "Ana", "nome": "Ana", "papel": ""}]
        self.assertEqual(R.cabecalho_participantes(R.normalizar_participantes(so_vendedor)), "")
        self.assertEqual(R.cabecalho_participantes([]), "")

    def test_papel_nao_informado_aparece_como_tal(self):
        lista = PEDRO_ANDRE + [{"nome_meet": "Ana", "nome": "Ana", "papel": ""}]
        self.assertIn("- Ana: papel não informado", R.cabecalho_participantes(R.normalizar_participantes(lista)))

    def test_json_ida_e_volta(self):
        lista = R.normalizar_participantes(PEDRO_ANDRE)
        self.assertEqual(R.de_json(R.para_json(lista)), lista)
        self.assertEqual(R.de_json(""), [])
        self.assertEqual(R.de_json("{quebrado"), [])


class TempoRealParticipantesTest(unittest.TestCase):
    def _chamar(self, participantes):
        import api.main as m
        req = m.TempoRealRequest(transcricao_parcial="André: quanto custa?", meeting_id="m1",
                                 participantes=participantes)
        with patch("api.processador_tempo_real.processar_fragmento_tempo_real",
                   new=AsyncMock(return_value={"next_best_action": {}})) as proc, \
             patch("agent.sessao_manager.salvar_transcricao_bruta"), \
             patch("agent.sessao_manager.salvar_analise"), \
             patch("agent.sessao_manager.salvar_participantes") as salvar:
            asyncio.run(m.analisar_tempo_real(req, authorization=None))
        return proc.call_args.kwargs["participantes"], salvar

    def test_lista_vai_normalizada_para_a_ia_e_e_guardada_na_sessao(self):
        enviados, salvar = self._chamar(PEDRO_ANDRE)
        self.assertEqual(enviados, R.normalizar_participantes(PEDRO_ANDRE))
        salvar.assert_called_once()
        mid, texto = salvar.call_args.args
        self.assertEqual((mid, json.loads(texto)), ("m1", enviados))

    def test_extensao_antiga_sem_participantes(self):
        enviados, salvar = self._chamar(None)
        self.assertEqual(enviados, [])
        salvar.assert_not_called()


class ProcessadorCabecalhoTest(unittest.TestCase):
    def test_cabecalho_vai_antes_da_conversa_enviada_aos_agentes(self):
        from api import processador_tempo_real as p
        multi = AsyncMock(return_value={})
        with patch("api.database.registrar_transcricao_meeting", return_value={"fragmento_aceito": "x"}), \
             patch("api.database.obter_meeting_memory", return_value=None), \
             patch("api.database.registrar_analise_meeting"), \
             patch.object(p, "_pode_chamar_ia", return_value=(True, "ok")), \
             patch("agent.multiagente.orquestrador.analisar_fragmento_multi", new=multi), \
             patch.object(p, "_normalizar_resposta_realtime", side_effect=lambda r, *a: {}):
            try:
                asyncio.run(p.analyzeRealtimeMeeting(
                    transcricao_parcial="André: quanto custa?", meeting_id="m-cab",
                    transcricao_nova="André: quanto custa?",
                    participantes=R.normalizar_participantes(PEDRO_ANDRE)))
            except Exception:
                pass  # etapas depois da IA não importam aqui
        enviado = multi.call_args.kwargs["transcricao_parcial"]
        self.assertTrue(enviado.startswith("QUEM É QUEM NESTA REUNIÃO"))
        self.assertTrue(enviado.endswith("André: quanto custa?"))


class JuntarFalasSeguidasTest(unittest.TestCase):
    def test_caso_real_fala_partida_vira_uma(self):
        # Teste real 16/10: "olha" / "nos meus olhos…" = 1 bloco no Meet.
        from agent.transcript_dedup_rules import juntar_falas_seguidas
        texto = ("ANDRE LUIZ DA SILVA: dois três quatro\nMoly: chupa essa manga.\n\n"
                 "ANDRE LUIZ DA SILVA: olha\n\nANDRE LUIZ DA SILVA: nos meus olhos esqueçam\n\n"
                 "Moly: Eu caguei")
        self.assertEqual(juntar_falas_seguidas(texto),
                         "ANDRE LUIZ DA SILVA: dois três quatro\nMoly: chupa essa manga.\n"
                         "ANDRE LUIZ DA SILVA: olha nos meus olhos esqueçam\nMoly: Eu caguei")

    def test_nao_identificado_e_linha_sem_rotulo_nao_juntam(self):
        from agent.transcript_dedup_rules import juntar_falas_seguidas
        texto = "Não identificado: a\nNão identificado: b\nsem rótulo\nsem rótulo 2\nAna: x\nana: y"
        self.assertEqual(juntar_falas_seguidas(texto),
                         "Não identificado: a\nNão identificado: b\nsem rótulo\nsem rótulo 2\nAna: x y")

    def test_vazio(self):
        from agent.transcript_dedup_rules import juntar_falas_seguidas
        self.assertEqual(juntar_falas_seguidas(""), "")
        self.assertEqual(juntar_falas_seguidas(None), "")


class RelatorioAutomaticoTest(unittest.TestCase):
    def test_cabecalho_vem_da_sessao(self):
        from api import relatorio_automatico as ra
        with patch("agent.sessao_manager.obter_participantes", return_value=R.para_json(PEDRO_ANDRE)):
            self.assertIn("- Pedro: VENDEDOR", ra._cabecalho_quem_e_quem("m1"))
        with patch("agent.sessao_manager.obter_participantes", return_value=""):
            self.assertEqual(ra._cabecalho_quem_e_quem("m1"), "")
        with patch("agent.sessao_manager.obter_participantes", side_effect=RuntimeError("mysql fora")):
            self.assertEqual(ra._cabecalho_quem_e_quem("m1"), "")


if __name__ == "__main__":
    unittest.main()
