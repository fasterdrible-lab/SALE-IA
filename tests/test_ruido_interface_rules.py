"""
Testes de agent/ruido_interface_rules.py (A12) — exemplos reais das
transcrições de 20/09 a 08/10/2026.

Run:
    python -m unittest tests.test_ruido_interface_rules -v
"""
import unittest

from agent.ruido_interface_rules import eh_so_nome_proprio, eh_texto_de_interface
from agent.transcript_dedup_rules import compactar_transcricao

RUIDO_REAL = [
    "Você tem extensões instaladas que talvez afetem a qualidade da chamada",
    "Comece a falar durante a reunião para ver a transcrição aqui.",
    "Saiba mais",
    "Pergunte à Tactiq AI",
    "Transcribing: Portuguese (Brazil)",
    "O Gemini vai analisar sua conversa usando o acesso temporário ao conteúdo da reunião. O organizador pode desativar esse recurso. Saiba mais",
    "Desativar o recurso Peça ao Gemini",
    "60 segundos restantes",
    "Voltando à tela inicial em 60 segundos.",
    "Você saiu da reunião",
    "Como estava o áudio e o vídeo?",
    "AirPods (Bluetooth)",
    "BlackHole 2ch (Virtual)",
    "LC24RG50 (DisplayPort)",
    "Dispositivo com Saída Múltipla (Aggregate)",
    "Câmera do MacBook\xa0Air",
    "Paulo Henrique Pagoti de Oliveira Silva",
    "Paulo Henrique Pagoti de Oliveira Silva (Você, apresentando e fazendo anotações)",
    "Giovane Ribeiro Romano (chat)",
    "Fixar Igor Martins na tela principal",
    "Liberar a apresentação de Guilherme Borges Batista da tela principal",
    "A apresentação de Daniel Souza foi adicionada à tela principal. A apresentação de Daniel Souza está na tela principal.",
    "Mais 13 pessoas",
    "Ver tudo (1)",
    "3 participantes entraram",
    "1 usuário não confirmado",
    "Iniciando a apresentação…",
    "Tamanho das anotações:",
    "Após a reunião, a gravação será salva no Drive de Paulo Henrique Pagoti de Oliveira Silva. Quando necessário",
    ".SnackbarItem-variantInfo { background-color: #feff02; color: black; }",
    "/* Suppress default focus style on the canvas element. */",
    "disable it if the ink-engine is not participating in the tab order, or if",
    'canvas.ink-engine[tabindex="-1"] + div.post-canvas-tab-target,',
    "hidden;",
    "var(--ink-canvas-outline, 0);",
    "focus {",
    # fim da chamada (12/10/2026)
    "Como não tem mais ninguém nesta chamada, ela terminará em menos de 2 minutos. Quer continuar nela?",
    'Para não ver mais isto, acesse "Configurações" > "Gerais".',
    "Sair agora",
    "Continuar na chamada",
    "A chamada foi encerrada porque todas as pessoas saíram",
    "Sua reunião está segura",
    "As pessoas só podem participar de uma reunião se o organizador convidar ou permitir",
    "Fazer upgrade",
    "Faça upgrade para ter acesso aos recursos premium",
    "Participar novamente",
]

FALA_REAL = [
    "Com certeza",
    "Claro, com certeza.",
    "Entendi, entendi.",
    "Graças a Deus.",
    "Tudo bem, graças a Deus. E você?",
    "Que que vocês acharam aí pessoal?",
    "Sim, sim, sim.",
    "E aí Paulo? Tudo bem?",
    "Hoje a gente faz tudo na planilha, é bem manual.",
    "Eu saí da reunião anterior agora, desculpa o atraso",
    "Quanto custa o Programa de Aceleração?",
    "Meu fone é um AirPods, tá me ouvindo bem?",
    "Saiba mais sobre o seu negócio antes de investir",
    "Mais ou menos, depende do mês",
    "A gente tem 60 segundos pra fechar isso? Brincadeira.",
    "A chamada foi encerrada e ninguém me avisou",
    "Posso sair agora e voltar depois?",
]


class EhTextoDeInterfaceTest(unittest.TestCase):
    def test_ruido_real_sai(self):
        for texto in RUIDO_REAL:
            with self.subTest(texto=texto):
                self.assertTrue(eh_texto_de_interface(texto))

    def test_fala_real_fica(self):
        for texto in FALA_REAL:
            with self.subTest(texto=texto):
                self.assertFalse(eh_texto_de_interface(texto))

    def test_vazio(self):
        self.assertFalse(eh_texto_de_interface(""))
        self.assertFalse(eh_texto_de_interface(None))


class EhSoNomeProprioTest(unittest.TestCase):
    def test_nomes(self):
        self.assertTrue(eh_so_nome_proprio("Daniel Camargo de Andrade"))
        self.assertTrue(eh_so_nome_proprio("Igor Martins"))

    def test_nao_nomes(self):
        self.assertFalse(eh_so_nome_proprio("Paulo"))  # 1 palavra: pode ser vocativo
        self.assertFalse(eh_so_nome_proprio("Graças a Deus"))
        self.assertFalse(eh_so_nome_proprio("Muito bom"))
        self.assertFalse(eh_so_nome_proprio("de Oliveira"))


class CompactarTranscricaoComRuidoTest(unittest.TestCase):
    def test_remove_ruido_com_rotulo_e_mantem_fala(self):
        texto = "\n".join([
            "Felipe: AirPods (Bluetooth)",
            "Cliente: Saiba mais",
            "Paulo: Me conta como vocês fazem hoje o controle",
            "João: O Gemini está fazendo anotações",
            "Cliente: Hoje a gente faz tudo na planilha, é bem manual.",
            "Paulo: 60 segundos restantes",
            "Cliente: Com certeza",
        ])
        self.assertEqual(compactar_transcricao(texto).splitlines(), [
            "Paulo: Me conta como vocês fazem hoje o controle",
            "Cliente: Hoje a gente faz tudo na planilha, é bem manual.",
            "Cliente: Com certeza",
        ])


if __name__ == "__main__":
    unittest.main()
