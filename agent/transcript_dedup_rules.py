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

JANELA_EXATA_PADRAO = 80
JANELA_SIMILAR_PADRAO = 15
LIMIAR_SIMILARIDADE_PADRAO = 0.85
MIN_CHARS_CORPO_PADRAO = 20

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


def eh_duplicata(
    linha: str,
    recentes: list,
    *,
    janela_similar: int = JANELA_SIMILAR_PADRAO,
    limiar: float = LIMIAR_SIMILARIDADE_PADRAO,
    min_chars: int = MIN_CHARS_CORPO_PADRAO,
) -> bool:
    """`recentes` em ordem cronológica (a mais nova por último)."""
    corpo = corpo_normalizado(linha)
    if len(corpo) < min_chars:
        return False
    for anterior in recentes:
        if anterior.strip() == linha.strip():
            return True
    for anterior in recentes[-janela_similar:]:
        outro = corpo_normalizado(anterior)
        if len(outro) < min_chars:
            continue
        if difflib.SequenceMatcher(None, corpo, outro).ratio() >= limiar:
            return True
    return False


def deduplicar_fragmento(
    base: str,
    fragmento: str,
    *,
    janela_exata: int = JANELA_EXATA_PADRAO,
    janela_similar: int = JANELA_SIMILAR_PADRAO,
    limiar: float = LIMIAR_SIMILARIDADE_PADRAO,
    min_chars: int = MIN_CHARS_CORPO_PADRAO,
) -> tuple:
    """Retorna `(fragmento_filtrado, n_descartadas)`. Compara cada linha
    do fragmento contra o final de `base` e contra as linhas já aceitas
    do próprio fragmento. Nunca altera o texto de uma linha mantida."""
    recentes = _linhas(base)[-janela_exata:]
    mantidas = []
    descartadas = 0
    for linha in _linhas(fragmento):
        if eh_duplicata(linha, recentes, janela_similar=janela_similar, limiar=limiar, min_chars=min_chars):
            descartadas += 1
            continue
        mantidas.append(linha)
        recentes.append(linha)
        if len(recentes) > janela_exata:
            recentes.pop(0)
    return "\n".join(mantidas), descartadas
