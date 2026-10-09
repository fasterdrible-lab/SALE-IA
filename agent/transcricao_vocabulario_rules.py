"""Vocabulário para o Whisper (A12, 08/10/2026).

Até aqui a transcrição de áudio mandava só `language="pt"`. Nomes de
pessoas, de produtos e termos do negócio saíam errados com frequência.
O Whisper aceita um `prompt` (até ~224 tokens) que orienta grafia e
contexto: aqui ele leva os termos do negócio, os nomes que já apareceram
como falantes na reunião e o fim da conversa (continuidade entre os
trechos de 15s).

Risco conhecido: em trecho de silêncio o Whisper pode devolver o próprio
prompt, ou frases típicas de legenda do YouTube com que foi treinado.
`eh_alucinacao()` descarta esses casos.

Funções puras.
"""
import re
import unicodedata

GLOSSARIO_PADRAO = ("SALEIA", "Programa de Aceleração", "Performance")
MAX_CHARS_PROMPT = 600
MAX_CHARS_CONTEXTO = 220
MAX_NOMES = 6

_ROTULO_RE = re.compile(r"^([^:\n]{1,60}):\s*(.*)$")
_ROTULOS_GENERICOS = {
    "cliente", "vendedor", "participante", "nao identificado", "voce", "you",
}

# Frases que o Whisper "inventa" em silêncio (treino com legendas de vídeo).
_ALUCINACOES = (
    "amara.org", "legendas pela comunidade", "legenda pela comunidade", "inscreva-se no canal",
    "inscreva se no canal", "obrigado por assistir", "obrigada por assistir", "ative o sininho",
    "transcricao e legendas", "legendado por",
)


def _sem_acento(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _normalizar(texto: str) -> str:
    t = re.sub(r"[^\w\s]", " ", _sem_acento(texto).lower())
    return re.sub(r"\s+", " ", t).strip()


def glossario_do_ambiente(valor: str | None) -> tuple:
    """`TRANSCRICAO_GLOSSARIO` = termos separados por vírgula; vazio usa o padrão."""
    termos = tuple(t.strip() for t in (valor or "").split(",") if t.strip())
    return termos or GLOSSARIO_PADRAO


def nomes_dos_falantes(trecho: str) -> list:
    """Rótulos de falante que são nomes de verdade, na ordem em que aparecem."""
    nomes: list = []
    for linha in (trecho or "").splitlines():
        m = _ROTULO_RE.match(linha.strip())
        if not m:
            continue
        nome = m.group(1).strip()
        if nome.startswith("[") or _normalizar(nome) in _ROTULOS_GENERICOS or not re.search(r"[^\W\d_]", nome):
            continue
        if nome not in nomes:
            nomes.append(nome)
    return nomes[-MAX_NOMES:]


def contexto_final(trecho: str) -> str:
    """Fim da conversa, só o texto falado (sem rótulos), cortado em palavra."""
    corpos = []
    for linha in (trecho or "").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        m = _ROTULO_RE.match(linha)
        corpo = m.group(2) if m else re.sub(r"^\[[^\]]+\]\s*", "", linha)
        if corpo.strip():
            corpos.append(corpo.strip())
    texto = " ".join(corpos)
    if len(texto) <= MAX_CHARS_CONTEXTO:
        return texto
    corte = texto[-MAX_CHARS_CONTEXTO:]
    return corte.split(" ", 1)[1] if " " in corte else corte


def montar_prompt_whisper(glossario, nomes, contexto: str) -> str:
    partes = ["Reunião de vendas em português do Brasil."]
    if glossario:
        partes.append("Termos: " + ", ".join(glossario) + ".")
    if nomes:
        partes.append("Participantes: " + ", ".join(nomes) + ".")
    prompt = " ".join(partes)
    if contexto:
        sobra = MAX_CHARS_PROMPT - len(prompt) - 1
        if sobra > 40:
            prompt += " " + contexto[-sobra:]
    return prompt[:MAX_CHARS_PROMPT]


def eh_alucinacao(texto: str, prompt: str | None) -> bool:
    """True para frase típica de alucinação em silêncio ou para texto que é
    só um pedaço do próprio prompt (eco)."""
    t = _normalizar(texto)
    if not t:
        return False
    bruto = _sem_acento(texto).lower()
    if any(a in bruto for a in _ALUCINACOES):
        return True
    p = _normalizar(prompt or "")
    # 4+ palavras: fala curta repetida de verdade ("com certeza") não é eco
    return len(t.split()) >= 4 and t in p
