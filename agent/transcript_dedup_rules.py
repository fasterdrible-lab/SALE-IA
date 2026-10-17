"""Deduplicação idempotente de fragmentos de transcrição (Tarefa A1,
`docs/tasks-prompt-mestre-v2-restante.md`).

Função pura, sem IA/banco. Achado real em 12 reuniões de produção
(24/09/2026): ~10% das linhas de `MeetingMemory.transcript_full` eram
repetições e ~2,6% eram a mesma fala capturada por 2 fontes com rótulo de
falante diferente. Duas causas independentes:

1. **Reenvio do mesmo delta** — a extensão só avança o índice do último
   envio depois de uma resposta bem-sucedida; um envio disparado enquanto
   outro ainda está em andamento (ou um retry após timeout) manda o mesmo
   `transcricao_nova` de novo, e o backend anexava sem checar nada.
2. **Duas fontes da mesma fala** — legenda do Meet (rótulo = nome do
   Meet, sem pontuação) e Whisper do microfone (rótulo = vendedor,
   pontuado, ~15s depois).

Regra: uma linha nova é descartada se já existe entre as linhas recentes
(exata, janela longa — cobre o reenvio de um delta inteiro) ou se o corpo
da fala é quase igual a uma linha muito recente, de qualquer falante
(janela curta — cobre a segunda fonte). Fica sempre a primeira que
chegou; na prática a legenda, que traz o falante real do Meet. Falas
curtas ("Sim.", "Perfeito.") nunca são descartadas — repetição curta é
legítima numa conversa real.
"""

from __future__ import annotations

import difflib
import re
import unicodedata

JANELA_EXATA_PADRAO = 80
JANELA_SIMILAR_PADRAO = 15
LIMIAR_SIMILARIDADE_PADRAO = 0.85
MIN_CHARS_CORPO_PADRAO = 20
# Auditoria T01 (11/10/2026): cópia exata só é artefato de captura quando
# está colada (varredura da legenda); mais longe é o cliente repetindo uma
# objeção (P7) e tem de ficar.
JANELA_ARTEFATO_PADRAO = 6
# Reenvio do delta (retry): o bloco reenviado aparece no fim da base, com
# no máximo esta folga de linhas que chegaram depois (P9).
FOLGA_REENVIO_PADRAO = 5
# V.1.4.178 (reunião real de 14/10, servidor lento): pedidos presos foram
# gravados minutos depois do reenvio, e o bloco repetido caiu longe do fim
# (22% das linhas). Duas ou mais linhas seguidas idênticas, com pelo menos
# duas longas, em qualquer ponto destas últimas linhas = reenvio.
JANELA_BLOCO_PADRAO = 300
MIN_LINHAS_BLOCO = 2
# V.1.4.178: legenda e áudio cortam a mesma fala em pontos diferentes (o
# áudio junta ~15s numa linha, a legenda quebra em 2-3), então linha contra
# linha nunca passa do limiar de similaridade. Por conteúdo: a fala de uma
# fonte cujas palavras já estão quase todas nas falas recentes da outra.
JANELA_COBERTURA_PADRAO = 60
LIMIAR_COBERTURA_PADRAO = 0.7
MIN_PALAVRAS_COBERTURA = 4

_ROTULO_RE = re.compile(r"^([^:\n]{1,60}):\s*(.*)$")
_NAO_PALAVRA_RE = re.compile(r"[^\w\s]", re.UNICODE)
_ESPACOS_RE = re.compile(r"\s+")


def corpo_normalizado(linha: str) -> str:
    """Texto da fala sem o rótulo de falante, minúsculo, sem pontuação."""
    linha = (linha or "").strip()
    m = _ROTULO_RE.match(linha)
    corpo = m.group(2) if m else linha
    corpo = _NAO_PALAVRA_RE.sub(" ", corpo.lower())
    return _ESPACOS_RE.sub(" ", corpo).strip()


def _linhas(texto: str) -> list:
    return [l.strip() for l in (texto or "").splitlines() if l.strip()]


def palavras_significativas(linha: str) -> list:
    """Palavras do corpo com mais de 3 letras, sem acento."""
    corpo = unicodedata.normalize("NFKD", corpo_normalizado(linha))
    corpo = "".join(ch for ch in corpo if not unicodedata.combining(ch))
    return [p for p in corpo.split() if len(p) > 3]


def coberta_pela_outra_fonte(
    linha: str,
    recentes: list,
    corpos_audio: set,
    *,
    janela: int = JANELA_COBERTURA_PADRAO,
    limiar: float = LIMIAR_COBERTURA_PADRAO,
) -> bool:
    """A fala já entrou pela outra fonte (legenda × áudio do servidor)?
    Só compara fontes diferentes: duas falas da legenda, ou duas do áudio,
    nunca são juntadas por aqui (P8)."""
    if not corpos_audio:
        return False
    palavras = palavras_significativas(linha)
    if len(palavras) < MIN_PALAVRAS_COBERTURA:
        return False
    do_audio = corpo_normalizado(linha) in corpos_audio
    da_outra_fonte = set()
    for anterior in recentes[-janela:]:
        if (corpo_normalizado(anterior) in corpos_audio) != do_audio:
            da_outra_fonte.update(palavras_significativas(anterior))
    cobertas = sum(1 for p in palavras if p in da_outra_fonte)
    return cobertas / len(palavras) >= limiar


def tamanho_bloco_reenviado(linhas: list, inicio: int, historico: list) -> int:
    """Quantas linhas a partir de `linhas[inicio]` repetem, em sequência,
    linhas já gravadas em `historico`. Vale só com `MIN_LINHAS_BLOCO` ou
    mais linhas seguidas e pelo menos duas longas: a objeção repetida (P7)
    é uma linha só e fica."""
    alvo = linhas[inicio].strip()
    melhor = 0
    for j, anterior in enumerate(historico):
        if anterior.strip() != alvo:
            continue
        n = longas = 0
        while (inicio + n < len(linhas) and j + n < len(historico)
               and linhas[inicio + n].strip() == historico[j + n].strip()):
            if len(corpo_normalizado(linhas[inicio + n])) >= MIN_CHARS_CORPO_PADRAO:
                longas += 1
            n += 1
        if n >= MIN_LINHAS_BLOCO and longas >= 2:
            melhor = max(melhor, n)
    return melhor


def eh_duplicata(
    linha: str,
    recentes: list,
    *,
    janela_similar: int = JANELA_SIMILAR_PADRAO,
    limiar: float = LIMIAR_SIMILARIDADE_PADRAO,
    min_chars: int = MIN_CHARS_CORPO_PADRAO,
    janela_artefato: int = JANELA_ARTEFATO_PADRAO,
    corpos_audio: set | None = None,
) -> bool:
    """`recentes` em ordem cronológica (a mais nova por último).

    `corpos_audio`: corpos (`corpo_normalizado`) que o servidor transcreveu
    do áudio desta reunião. Com ele, a regra de similaridade só junta uma
    fala com a sua versão do áudio — duas pessoas dizendo quase a mesma
    coisa ficam (P8). `None` mantém a regra antiga (qualquer par)."""
    if corpos_audio and coberta_pela_outra_fonte(linha, recentes, corpos_audio):
        return True
    corpo = corpo_normalizado(linha)
    if len(corpo) < min_chars:
        return False
    for anterior in recentes[-janela_artefato:]:
        if anterior.strip() == linha.strip():
            return True
    for anterior in recentes[-janela_similar:]:
        outro = corpo_normalizado(anterior)
        if len(outro) < min_chars:
            continue
        if corpos_audio is not None and corpo not in corpos_audio and outro not in corpos_audio:
            continue
        if difflib.SequenceMatcher(None, corpo, outro).ratio() >= limiar:
            return True
    return False


def linhas_reenviadas(recentes: list, fragmento: list, folga: int = FOLGA_REENVIO_PADRAO) -> int:
    """Quantas linhas do começo de `fragmento` são um reenvio: o maior `k`
    tal que `fragmento[:k]` aparece, em sequência, nas últimas `k + folga`
    linhas de `recentes`. Cobre o retry depois de timeout (mesmo delta) e
    o delta que cresceu enquanto o anterior não foi confirmado. Vale para
    fala curta também (P9). Uma linha sozinha só conta se for a última."""
    rec = [l.strip() for l in recentes]
    frag = [l.strip() for l in fragmento]
    for k in range(len(frag), 0, -1):
        alvo = frag[:k]
        if k == 1:
            if rec and rec[-1] == alvo[0]:
                return 1
            continue
        cauda = rec[-(k + folga):]
        for i in range(len(cauda) - k + 1):
            if cauda[i:i + k] == alvo:
                return k
    return 0


# ── Compactação (06/10/2026) ──────────────────────────────────────────
# Achado nas reuniões reais de 05/10: a legenda do Meet é capturada várias
# vezes enquanto a pessoa ainda fala ("Cara a minha esposa." → "Cara. A
# minha esposa ela é fis." → "Cara A minha esposa ela é fisioterapeuta…"),
# e CSS do Meet vazava como fala. As versões parciais passam pela regra de
# similaridade acima (tamanhos muito diferentes) e chegavam à IA, que só
# recebe 6.000 caracteres por ciclo.

JANELA_PARCIAL_PADRAO = 6

# Case-sensitive de propósito: propriedade CSS é minúscula; "Paulo: tá;" não casa.
_CSS_RE = re.compile(r"^\s*([a-z][a-z-]*\s*:\s*[^;{}]+;|[{}]|[.#]?[a-z][\w.#:-]*\s*\{)\s*$")
# Depois do rótulo ("João: position: absolute;") a regra acima pegaria fala
# ("olha: isso é caro;"); aqui só propriedade CSS conhecida ou com hífen (P14).
_CSS_CORPO_RE = re.compile(
    r"^\s*(position|display|width|height|top|left|right|bottom|outline|overflow|opacity|"
    r"visibility|transform|transition|animation|margin|padding|border|background|color|"
    r"cursor|content|inset|flex|gap|z-index|[a-z]+(-[a-z]+)+)\s*:\s*[^;{}]+;\s*$"
)
_TEM_LETRA_RE = re.compile(r"[^\W\d_]", re.UNICODE)
# P10: o Meet reescreve o começo da legenda ao reconhecer melhor ("pentear
# o cliente B…" → "perfil do cliente B…"). Parecido assim com o começo da
# versão seguinte do mesmo falante = versão antiga da mesma frase.
LIMIAR_REVISAO_PADRAO = 0.8
MIN_CHARS_REVISAO = 15


def _rotulo(linha: str) -> str:
    m = _ROTULO_RE.match(linha)
    return m.group(1).strip().lower() if m else ""


def eh_ruido_de_tela(linha: str) -> bool:
    """CSS vazado do Meet (`position: absolute;`, `}`), linha sem letra ou
    texto de interface do Meet/Gemini/Tactiq com rótulo de falante (A12,
    `agent/ruido_interface_rules.py`)."""
    from agent.ruido_interface_rules import eh_texto_de_interface

    linha = (linha or "").strip()
    if _CSS_RE.match(linha) or not _TEM_LETRA_RE.search(linha):
        return True
    m = _ROTULO_RE.match(linha)
    corpo = m.group(2) if m else linha
    if _CSS_CORPO_RE.match(corpo):
        return True
    return eh_texto_de_interface(corpo)


def _versao_antiga_da_mesma_frase(corpo: str, posterior: str) -> bool:
    """`corpo` é começo de `posterior` (legenda crescendo) ou o começo de
    `posterior` reescrito pelo Meet (P10)."""
    if len(posterior) <= len(corpo):
        return False
    if posterior.startswith(corpo):
        return True
    if len(corpo) < MIN_CHARS_REVISAO:
        return False
    # O Meet reescreve o começo; o fim da versão antiga continua lá. Sem
    # isto, "ver com o financeiro" sumiria diante de "ver com o jurídico…".
    fim = " ".join(corpo.split()[-2:])
    if fim not in posterior[: len(corpo) + 15]:
        return False
    inicio = posterior[: len(corpo)]
    return difflib.SequenceMatcher(None, corpo, inicio).ratio() >= LIMIAR_REVISAO_PADRAO


def compactar_transcricao(texto: str, janela: int = JANELA_PARCIAL_PADRAO) -> str:
    """Remove de `texto` (linhas "Falante: fala"):

    - ruído de tela (CSS, linha sem letra);
    - versão parcial de uma legenda: a linha cujo corpo é o começo (ou o
      começo reescrito pelo Meet) do corpo de uma das `janela` linhas
      seguintes do mesmo falante — fica só a versão completa;
    - repetição exata (mesmo falante e corpo, ≥ 20 caracteres) colada a
      ela (até `JANELA_ARTEFATO_PADRAO` linhas) — artefato da captura; mais
      longe é repetição real e fica (P7).

    Mantém a ordem e o texto original das linhas que ficam. Função pura."""
    linhas = [l for l in _linhas(texto) if not eh_ruido_de_tela(l)]
    corpos = [corpo_normalizado(l) for l in linhas]
    rotulos = [_rotulo(l) for l in linhas]
    mantidas = []
    vistos_recentes: list = []
    for i, linha in enumerate(linhas):
        corpo = corpos[i]
        if not corpo:
            continue
        eh_parcial = any(
            rotulos[j] == rotulos[i] and _versao_antiga_da_mesma_frase(corpo, corpos[j])
            for j in range(i + 1, min(len(linhas), i + 1 + janela))
        )
        if eh_parcial:
            continue
        chave = (rotulos[i], corpo)
        # fala curta repetida ("Sim.", "Perfeito.") é legítima numa conversa
        if len(corpo) >= MIN_CHARS_CORPO_PADRAO and chave in vistos_recentes:
            continue
        mantidas.append(linha)
        vistos_recentes.append(chave)
        if len(vistos_recentes) > JANELA_ARTEFATO_PADRAO:
            vistos_recentes.pop(0)
    return "\n".join(mantidas)


ROTULOS_SEM_JUNCAO = {"não identificado", "nao identificado", "participante"}


def juntar_falas_seguidas(texto: str) -> str:
    """V.1.4.186: falas seguidas da mesma pessoa viram uma linha só, como o
    Meet mostra num bloco. A extensão grava a fala em pedaços (pausa de
    3,5 s, ou a cada 15 s) e manda a continuação de um bloco já enviado
    como linha nova (1.4.29) — a conversa ficava partida ("Fulano: olha" /
    "Fulano: nos meus olhos…"). Só para leitura (painel, IA, relatório): o
    texto guardado não muda, a deduplicação continua linha a linha.
    "Não identificado" nunca é juntado (podem ser pessoas diferentes).
    Linha sem rótulo fica como está. Função pura."""
    saida: list[list[str]] = []  # [rotulo_original, rotulo_normalizado, corpo]
    for linha in _linhas(texto):
        m = _ROTULO_RE.match(linha)
        if not m:
            saida.append(["", "", linha])
            continue
        rotulo, corpo = m.group(1).strip(), m.group(2).strip()
        chave = rotulo.lower()
        if (saida and saida[-1][1] == chave and chave and chave not in ROTULOS_SEM_JUNCAO
                and corpo):
            saida[-1][2] = (saida[-1][2] + " " + corpo).strip()
        else:
            saida.append([rotulo, chave, corpo])
    return "\n".join(f"{r}: {c}" if r else c for r, _, c in saida)


def deduplicar_fragmento(
    base: str,
    fragmento: str,
    *,
    janela_exata: int = JANELA_EXATA_PADRAO,
    janela_similar: int = JANELA_SIMILAR_PADRAO,
    limiar: float = LIMIAR_SIMILARIDADE_PADRAO,
    min_chars: int = MIN_CHARS_CORPO_PADRAO,
    corpos_audio: set | None = None,
) -> tuple:
    """Retorna `(fragmento_filtrado, n_descartadas)`. Primeiro tira o
    trecho reenviado (`linhas_reenviadas`); depois compara cada linha
    contra o final de `base` e contra as linhas já aceitas do próprio
    fragmento. Nunca altera o texto de uma linha mantida."""
    historico = _linhas(base)[-JANELA_BLOCO_PADRAO:]
    recentes = historico[-janela_exata:]
    linhas = _linhas(fragmento)
    descartadas = linhas_reenviadas(recentes, linhas)
    mantidas = []
    i = descartadas
    while i < len(linhas):
        bloco = tamanho_bloco_reenviado(linhas, i, historico)
        if bloco:
            descartadas += bloco
            i += bloco
            continue
        linha = linhas[i]
        i += 1
        if eh_duplicata(linha, recentes, janela_similar=janela_similar, limiar=limiar,
                        min_chars=min_chars, corpos_audio=corpos_audio):
            descartadas += 1
            continue
        mantidas.append(linha)
        historico.append(linha)
        recentes.append(linha)
        if len(recentes) > janela_exata:
            recentes.pop(0)
    return "\n".join(mantidas), descartadas
