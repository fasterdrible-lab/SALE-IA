"""Texto de tela do Google Meet que entra na transcrição como fala (A12).

A extensão observa a página inteira e filtra por lista de exclusão; cada
mudança do Meet deixa passar textos novos. Medido em 08/10/2026 nas 50
reuniões desde 20/09: 22,6% das linhas eram texto que se repete em 5+
reuniões (avisos do Meet e do Gemini, botões, contagem regressiva,
dispositivos de áudio, nomes de participantes, CSS, painel do Tactiq).

Este filtro roda no backend, então vale também para extensões antigas.
Só frases e padrões de interface — fala curta real ("Com certeza",
"Entendi, entendi") nunca entra aqui, mesmo sendo repetida. Função pura.
"""
import re
import unicodedata

# Frases exatas (comparadas sem acento, sem caixa e sem pontuação final).
_FRASES = """
transcricao ao vivo
voce tem extensoes instaladas que talvez afetem a qualidade da chamada
configurar o modo de exibicao da sala
comece a falar durante a reuniao para ver a transcricao aqui
start talking during the meeting to see the transcript here
pergunte a tactiq ai
obtenha ajuda com o tactiq
gerenciar configuracoes do tactiq
saiba mais
mudar idioma da reuniao
mais acoes
nao mostrar novamente
voltar a tela inicial
voltar para a sala
voltando a tela inicial
voce saiu da reuniao
como estava o audio e o video
muito ruim
esta chamada esta sendo transcrita
participantes externos entraram
participantes externos sairam
a transcricao comecou
a transcricao comecara em breve
a transcricao esta vazia
aguardando para participar
aguardando permissao
aguardando agrupamento
mais emojis
esta reuniao esta sendo gravada
sua videochamada esta sendo gravada
visivel para organizadores
somente voce
iniciando a apresentacao
parar apresentacao
parar compartilhamento
apresentar outra coisa
nao ha mais ninguem nesta reuniao
parar gravacao
gerenciar gravacao
gravar sua videochamada
comecar a gravar
a gravacao comecara em breve
o meet vai gravar
o painel gravacao esta aberto
incluir legendas na gravacao
desativar som do microfone deste participante
desativar som da apresentacao deste participante
desativar o som da sua apresentacao
ativar o som da sua apresentacao
desativar som
remover da chamada
atividade da reuniao
parar de transcrever
transcrever a reuniao
ajuste a visualizacao
voce esta apresentando
sua apresentacao
abrir na tela cheia
tela cheia
usar o modo companion
transmitir esta reuniao
outras formas de participar
participar agora
participar usando o audio do telefone
ouvir a reuniao por telefone
ajuda e solucao de problemas
informar um problema
enviar feedback
abrir picture-in-picture
picture-in-picture automatico
mudar a configuracao automatica do picture-in-picture
nao e possivel ativar o som de outra pessoa
nao e possivel ativar o audio da apresentacao
nao e possivel ativar o som da apresentacao de outra pessoa
nao e possivel ativar o microfone aqui
adic. pessoas
ver todos nesta chamada
audio da apresentacao
mostrar minha tela mesmo assim
parar anotacao
parar de fazer anotacoes
limpar tudo
tinta temporaria
permita que outras pessoas facam anotacoes
elas vao aparecer para todos
caixa de texto
nota autoadesiva
linhas e formas
tamanho das anotacoes
mude o idioma nas configuracoes
carregando os convidados
abrir o painel pessoas
o painel pessoas esta aberto
desfocar plano de fundo
fixar sua apresentacao na tela principal
fazer anotacoes na guia "meet"
ver lista de transcricoes
salvamento automatico com sucesso
na reuniao
seu video foi reenquadrado
ajustando o video
mostrar mais informacoes
organizador da reuniao
abrir em uma nova janela
quais as novidades
ligue e teste seu microfone
aumentar zoom
apagar esta conversa
o microfone nao foi encontrado
o alto-falante nao foi encontrado
a camera nao foi encontrada
informacoes de privacidade
fixado para voce
disponivel apenas para o organizador da reuniao
confirme se todos estao prontos
faca um resumo da discussao ate o momento
resumo, detalhes, proximas etapas, decisoes
voce ainda esta aqui
legendas traduzidas
camera desligada
legenda instantanea
idioma da reuniao
idioma falado padrao
sua preferencia de idioma
personalizar as legendas
legendas e transcricoes esta no idioma da reuniao portugues
as legendas e transcricoes vao estar no idioma da reuniao
mostra legendas para falas no idioma da reuniao
escolha as configuracoes que voce quer para as legendas durante as chamadas
pressione para falar
mantenha a barra de espaco pressionada para ativar o microfone
registros da reuniao
os registros da reuniao incluem
compartilhar notas e transcricao
controle de chamadas
fechar caixa de dialogo
fechar banner
minimizar widget
mais configuracoes
somente audio
audio adaptativo
aprimorando seu audio
conectar dispositivo
sair de chamadas vazias
notificacoes na area de trabalho
ha visitantes nesta reuniao
ha colaboradores moderados nesta chamada
algumas pessoas estao usando o modo companion nesta chamada
uma ou mais pessoas querem participar desta chamada
as pessoas estao esperando. entre para permitir que elas participem
para acessar mais pessoas, use o layout em mosaico
seu audio foi mesclado com dispositivos por perto
camera do macbook air
iniciar um novo
coletando informacoes
editar texto
limpar historico
nova conversa
boa resposta
resposta ruim
mais sugestoes
sugestoes atualizadas
conversa nao encontrada
o conteudo esta desatualizado
"""

_FRASES_SET = {f.strip() for f in _FRASES.strip().splitlines() if f.strip()}

# Começo de frase de aviso do Meet/Gemini/Tactiq (frases longas ou com variação).
_PREFIXOS = (
    "o gemini ", "pedir para gemini", "peca ao gemini", "desativar o recurso peca ao gemini",
    "notificacoes do recurso peca ao gemini", "use o gemini", "saiba como o gemini",
    "fazer anotacoes com o gemini", "iniciar tambem o recurso fazer anotacoes",
    "tambem parar de usar o recurso fazer anotacoes", "o recurso gemini", "resposta do gemini",
    "o que o gemini", "os comandos e as respostas so ficam visiveis",
    "transcribing:", "transcricao:", "alguem quer participar desta chamada",
    "outras pessoas podem ver mais do seu plano de fundo", "a gravacao foi iniciada",
    "pessoas de fora da organizacao", "para evitar o efeito de espelho infinito",
    "com o picture-in-picture", "o modo picture-in-picture", "selecione quando voce quer",
    "selecione como voce quer ouvir", "os dados coletados, incluindo audio",
    "as anotacoes serao", "as anotacoes vao estar", "anotacoes automaticas em reunioes",
    "voltando a tela inicial em", "liberar sua apresentacao", "liberar a apresentacao de",
    "sua apresentacao foi", "o meet pode mostrar notificacoes", "ocorreu um erro e nao e possivel",
    "nao foi possivel carregar suas conversas", "nao e possivel editar imagens",
    "voce atingiu o limite de mensagens", "junta automaticamente o microfone",
    "usar o processamento de sinal de audio", "filtra os sons do seu microfone",
    "remove voce depois de alguns minutos", "mostre a palma da sua mao",
    "definicao padrao (", "controle o meet com seu dispositivo", "capturar o que acontece automaticamente",
    "apos a reuniao, a gravacao sera salva",
)

_PADROES = [re.compile(p) for p in (
    r"^\d+ segundos? restantes?$",
    r"^ha \d+ (segundos?|minutos?|horas?)$",
    r"^mais \d+ pessoas?$",
    r"^\d+ (participantes?|usuarios?) (entraram|entrou|sairam|saiu|nao confirmados?)$",
    r"^\d+ pessoas? tambem foram convidadas$",
    r"^permitir \d+ convidados?$",
    r"^ver tudo \(\d+\)$",
    r"^fixar .+ na tela principal$",
    r"^a apresentacao de .+ (foi adicionada|foi removida|esta) ",
    # "Fulano (Você, apresentando)", "Fulano (chat)", "Fulano (Apresentando)"
    r"^[^()]{2,80} \((voce|apresentando|chat|sua apresentacao)[^)]*\)$",
    # dispositivos: "AirPods (Bluetooth)", "BlackHole 2ch (Virtual)", "LC24RG50 (DisplayPort)"
    r"\((bluetooth|virtual|displayport|aggregate|hdmi|usb|built-in|integrado|padrao|default)\)$",
    r"^dispositivo com saida multipla",
)]

# CSS que vaza do Meet: comentário, seletor com "{", valor solto com ";".
_CSS_PADROES = [re.compile(p) for p in (
    r"^/\*", r"\*/$", r"\{\s*$", r"^\s*\}", r"^\.[\w-]+\s*\{.*\}$",
    # valor solto ("hidden;", "100%;", "border-box;"); fala com ";" ("vamos lá;") fica
    r"^[a-z0-9%#().,-]+;$", r"var\(--", r"^(left|right|center|top|bottom)( (left|right|center|top|bottom))?;$",
    # comentário/seletor de várias linhas do editor de anotações do Meet
    r"ink-engine|ink-canvas|ink-layer|tab-target",
)]


_PARTICULAS_NOME = {"da", "de", "di", "do", "das", "dos", "e"}
_PALAVRA_NOME_RE = re.compile(r"^[A-ZÁÉÍÓÚÂÊÔÃÕÀÇ][a-záéíóúâêôãõàçü'-]+$")


def eh_so_nome_proprio(texto: str) -> bool:
    """Linha que é só um nome ("Paulo Henrique Pagoti de Oliveira Silva"):
    tile/lista de participantes do Meet, não fala. A legenda só põe
    maiúscula na 1ª palavra, então fala real quase nunca passa nisto."""
    palavras = (texto or "").strip().split()
    if not 2 <= len(palavras) <= 7:
        return False
    if palavras[0] in _PARTICULAS_NOME or palavras[-1] in _PARTICULAS_NOME:
        return False
    return all(p in _PARTICULAS_NOME or _PALAVRA_NOME_RE.match(p) for p in palavras)


def _normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"\s+", " ", t.replace("…", "")).strip().lower()  # \s pega o espaço fixo (\xa0) do Meet
    return re.sub(r"[\s.!?:]+$", "", t)


def eh_texto_de_interface(corpo: str) -> bool:
    """`corpo` = a fala sem o rótulo do falante."""
    bruto = (corpo or "").strip()
    if not bruto:
        return False
    if any(p.search(bruto) for p in _CSS_PADROES):
        return True
    if eh_so_nome_proprio(bruto):
        return True
    t = _normalizar(bruto)
    if t in _FRASES_SET:
        return True
    if any(t.startswith(p) for p in _PREFIXOS):
        return True
    return any(p.search(t) for p in _PADROES)
