"""Painel de gravações do Dashboard — regras puras (validação da T02 e
gabarito da T03, roteiro Audio-First em docs/PROMPT_MESTRE_AUDIO_FIRST.md).

Fase 1: agrupar as gravações de uma reunião (uma por trilha a cada
rotação/pausa) numa linha do tempo única, para ouvir aba e microfone
juntos ao lado da transcrição.

Fase 2: trechos de referência — a pessoa ouve um pedaço, cola o que o
sistema transcreveu e escreve o que foi dito de verdade; o WER sai daqui.
Mede a transcrição gravada (hoje, a legenda do Meet), não a gravação.

Pedido do usuário em 12/10/2026: vendedor vê só as próprias gravações,
admin vê todas (mesma regra de GET /gravacao/{id}/audio).
"""
from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Optional

from agent.transcription_benchmark_rules import calcular_wer

# Duas gravações da mesma sala do Meet com mais que isso entre elas são
# reuniões diferentes (sala recorrente; MeetingMemory usa 6h, aqui menos
# porque a gravação é por reunião de verdade, não por sala).
INTERVALO_NOVA_SESSAO = timedelta(hours=2)
TRILHAS_REFERENCIA = ("aba", "microfone", "ambas")
MAX_TEXTO_REFERENCIA = 20_000  # ~10 min de fala com folga
MAX_PALAVRAS_WER = 5_000       # Levenshtein por palavra é O(n*m)
JANELA_NIVEL_S = 2


def painel_habilitado(env: dict | None = None) -> bool:
    """Kill-switch. Ligado por padrão: só leitura, com a mesma permissão de
    quem já pode baixar o áudio."""
    env = os.environ if env is None else env
    return str(env.get("GRAVACOES_PAINEL_ENABLED", "true")).strip().lower() not in ("0", "false", "no")


def _fim(g: dict) -> datetime:
    return g.get("fim") or g["inicio"]


def agrupar_sessoes(gravacoes: list) -> list:
    """`gravacoes`: dicts com recording_id, meeting_id, track_id, inicio,
    fim (datetime ou None). Devolve sessões em ordem de início, cada uma
    {sessao_id (= recording_id da 1ª gravação), meeting_id, inicio, fim,
    gravacoes: [...]}. Mesma sala com intervalo > INTERVALO_NOVA_SESSAO =
    sessão nova."""
    sessoes = []
    por_reuniao: dict = {}
    for g in sorted(gravacoes, key=lambda x: (x["meeting_id"], x["inicio"])):
        atual = por_reuniao.get(g["meeting_id"])
        if atual is None or g["inicio"] - atual["fim"] > INTERVALO_NOVA_SESSAO:
            atual = {"sessao_id": g["recording_id"], "meeting_id": g["meeting_id"],
                     "inicio": g["inicio"], "fim": _fim(g), "gravacoes": []}
            por_reuniao[g["meeting_id"]] = atual
            sessoes.append(atual)
        atual["gravacoes"].append(g)
        atual["fim"] = max(atual["fim"], _fim(g))
    return sorted(sessoes, key=lambda s: s["inicio"])


def escolher_memoria(candidatas: list, inicio: datetime, fim: datetime) -> Optional[dict]:
    """A MeetingMemory da sessão: sala recorrente tem várias (as antigas
    arquivadas como `código#AAAAMMDDhhmm-id`). Fica a que mais se sobrepõe
    ao período gravado; sem sobreposição, nenhuma (não mostra a transcrição
    de outra reunião)."""
    melhor, melhor_sobra = None, timedelta(0)
    for m in candidatas:
        ini, fi = m.get("created_at"), m.get("updated_at")
        if not ini or not fi:
            continue
        sobra = min(fi, fim) - max(ini, inicio)
        if sobra > melhor_sobra:
            melhor, melhor_sobra = m, sobra
    return melhor


# Rótulo = até 4 palavras no começo da linha, começando com maiúscula
# ("Paulo:", "Não identificado:", "Cliente 2:").
_ROTULO_RE = re.compile(r"^[ \t]*[A-ZÀ-Ý][^\s:]*(?:[ \t][^\s:]+){0,3}:[ \t]+", re.MULTILINE)


def tirar_rotulos_de_falante(texto: str) -> str:
    """'Paulo: bom dia' → 'bom dia' (o WER mede palavras, não o falante)."""
    return _ROTULO_RE.sub("", texto or "")


def normalizar_para_wer(texto: str) -> str:
    """Caixa baixa, sem pontuação e sem espaços repetidos. Acento fica:
    'esta' × 'está' é erro de transcrição de verdade."""
    t = unicodedata.normalize("NFC", texto or "").lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def validar_referencia(inicio_s, fim_s, trilha: str, texto_referencia: str, texto_sistema: str) -> list:
    erros = []
    try:
        inicio_s, fim_s = float(inicio_s), float(fim_s)
        if inicio_s < 0 or fim_s <= inicio_s:
            erros.append("o fim do trecho deve ser depois do início")
    except (TypeError, ValueError):
        erros.append("início e fim do trecho devem ser números (segundos)")
    if trilha not in TRILHAS_REFERENCIA:
        erros.append("trilha deve ser 'aba', 'microfone' ou 'ambas'")
    if not normalizar_para_wer(texto_referencia):
        erros.append("escreva o que foi dito no trecho (texto correto)")
    for nome, t in (("texto correto", texto_referencia), ("texto do sistema", texto_sistema)):
        if len(t or "") > MAX_TEXTO_REFERENCIA:
            erros.append(f"{nome} longo demais (máx. {MAX_TEXTO_REFERENCIA} caracteres)")
    return erros


def medir_trecho(texto_referencia: str, texto_sistema: str) -> dict:
    """WER do trecho: referência = o que foi dito; hipótese = o que o
    sistema transcreveu (sem rótulos de falante)."""
    ref = normalizar_para_wer(tirar_rotulos_de_falante(texto_referencia)).split()[:MAX_PALAVRAS_WER]
    hip = normalizar_para_wer(tirar_rotulos_de_falante(texto_sistema)).split()[:MAX_PALAVRAS_WER]
    r = calcular_wer(" ".join(ref), " ".join(hip))
    r["erros"] = r["substitutions"] + r["deletions"] + r["insertions"]
    r["hipotese_palavras"] = len(hip)
    return r


def resumir_referencias(referencias: list) -> dict:
    """WER total ponderado pelas palavras de cada trecho (trecho curto não
    pesa igual a um longo)."""
    palavras = sum(int(r.get("referencia_palavras") or 0) for r in referencias)
    erros = sum(int(r.get("erros") or 0) for r in referencias)
    segundos = sum(max(0.0, float(r.get("fim_s", 0)) - float(r.get("inicio_s", 0))) for r in referencias)
    return {
        "trechos": len(referencias),
        "segundos_revisados": round(segundos, 1),
        "palavras_referencia": palavras,
        "erros": erros,
        "wer": round(erros / palavras, 4) if palavras else None,
    }


def resumir_niveis(niveis: list, limiar_db: float = -45.0) -> dict:
    """Quanto da trilha tem som (janelas acima de `limiar_db`)."""
    if not niveis:
        return {"janelas": 0, "com_som": 0, "fracao_com_som": None}
    com_som = sum(1 for n in niveis if n is not None and n > limiar_db)
    return {"janelas": len(niveis), "com_som": com_som, "fracao_com_som": round(com_som / len(niveis), 3)}
