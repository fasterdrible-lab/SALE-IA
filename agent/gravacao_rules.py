"""Gravação contínua do áudio da reunião — regras puras (T02 do roteiro
Audio-First, docs/PROMPT_MESTRE_AUDIO_FIRST.md).

A extensão grava cada trilha (`aba` = participantes, `microfone` =
vendedor) sem parar, entregando blocos de alguns segundos; a cada
`rotacao_s` o gravador recomeça com um `recording_id` novo (cabeçalho
WebM novo), para que um bloco perdido estrague no máximo uma gravação,
nunca a reunião inteira. Só o 1º bloco de cada gravação tem o cabeçalho:
os demais só tocam colados a ele, em ordem.

Decisões do usuário (11/10/2026): confirmação de que os participantes
foram avisados a cada reunião; retenção de 90 dias; gravação só com o
vendedor logado. Desligada por padrão (`GRAVACAO_AUDIO_ENABLED`).

V.1.4.180 (15/10/2026, docs/tasks-legenda-tempo-real.md 1.1/1.2): retenção
de 7 dias (decisão do usuário), áudio a 32 kbps (voz; 128 kbps gastava
~58 MB/h por trilha) e transcrição de áudio em tempo real desligada por
padrão — durante a reunião a IA usa a legenda do Meet; a gravação é a
única fonte de áudio.
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

TRILHAS = ("aba", "microfone")
BLOCO_S_PADRAO = 5
ROTACAO_S_PADRAO = 600
RETENCAO_DIAS_PADRAO = 7
BITRATE_PADRAO = 32_000
# nginx aceita 1 MB por requisição; o bloco vai em base64 (+33%).
MAX_BLOCO_BYTES = 700_000
# Duração do bloco é o relógio da extensão, não do áudio: quando a trilha
# fica sem som (aba fechada, chamada encerrada) o MediaRecorder não entrega
# nada e o bloco seguinte cobre o tempo todo parado — até a rotação inteira
# (máx. 3600s). Em 12/10 o último bloco cobriu 130s e foi recusado com o
# limite antigo de 120s, deixando a gravação com lacuna. O tamanho continua
# limitado por MAX_BLOCO_BYTES.
MAX_DURACAO_BLOCO_MS = (3600 + 60) * 1000
TEXTO_CONSENTIMENTO = "Informei os participantes que a reunião será gravada."

_MEETING_RE = re.compile(r"^[a-z]{3}-[a-z]{4}-[a-z]{3}$")
_RECORDING_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def habilitada(env: dict | None = None) -> bool:
    env = os.environ if env is None else env
    return str(env.get("GRAVACAO_AUDIO_ENABLED", "false")).strip().lower() in ("1", "true", "yes")


def transcricao_tempo_real_ativa(env: dict | None = None) -> bool:
    """`/audio-transcricao` durante a reunião. Desligada por padrão: em
    14/10 travou a VPS (Whisper local) e esgotou a cota da Groq."""
    env = os.environ if env is None else env
    return str(env.get("TRANSCRICAO_TEMPO_REAL_ATIVA", "false")).strip().lower() in ("1", "true", "yes")


def _inteiro_env(nome: str, padrao: int, minimo: int, maximo: int, env: dict | None = None) -> int:
    env = os.environ if env is None else env
    try:
        valor = int(env.get(nome, padrao))
    except (TypeError, ValueError):
        valor = padrao
    return max(minimo, min(maximo, valor))


def configuracao(env: dict | None = None) -> dict:
    """O que a extensão precisa saber antes de gravar."""
    return {
        "habilitada": habilitada(env),
        "bloco_s": _inteiro_env("GRAVACAO_BLOCO_S", BLOCO_S_PADRAO, 2, 30, env),
        "rotacao_s": _inteiro_env("GRAVACAO_ROTACAO_S", ROTACAO_S_PADRAO, 60, 3600, env),
        "retencao_dias": _inteiro_env("GRAVACAO_RETENCAO_DIAS", RETENCAO_DIAS_PADRAO, 1, 3650, env),
        "bitrate": _inteiro_env("GRAVACAO_BITRATE", BITRATE_PADRAO, 16_000, 256_000, env),
        "transcricao_tempo_real": transcricao_tempo_real_ativa(env),
        "texto_consentimento": TEXTO_CONSENTIMENTO,
        "trilhas": list(TRILHAS),
    }


def validar_inicio(meeting_id: str, track_id: str, recording_id: str, consentimento: bool) -> list:
    """Lista de erros (vazia = ok)."""
    erros = []
    if not _MEETING_RE.match(meeting_id or ""):
        erros.append("meeting_id inválido")
    if track_id not in TRILHAS:
        erros.append("track_id deve ser 'aba' ou 'microfone'")
    if not _RECORDING_RE.match(recording_id or ""):
        erros.append("recording_id inválido")
    if consentimento is not True:
        erros.append("é preciso confirmar que os participantes foram avisados da gravação")
    return erros


def hash_do_conteudo(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def validar_bloco(sequence: int, start_ms: int, end_ms: int, content_hash: str, dados: bytes) -> list:
    erros = []
    if not isinstance(sequence, int) or sequence < 0:
        erros.append("sequence deve ser inteiro >= 0")
    if not isinstance(start_ms, int) or not isinstance(end_ms, int) or end_ms <= start_ms:
        erros.append("end_ms deve ser maior que start_ms")
    elif end_ms - start_ms > MAX_DURACAO_BLOCO_MS:
        erros.append("bloco longo demais")
    if not dados:
        erros.append("bloco vazio")
    elif len(dados) > MAX_BLOCO_BYTES:
        erros.append("bloco grande demais")
    if not _HASH_RE.match(content_hash or ""):
        erros.append("content_hash deve ser SHA-256 em hexadecimal")
    elif dados and hash_do_conteudo(dados) != content_hash:
        erros.append("content_hash não confere com o conteúdo")
    return erros


def caminho_do_bloco(raiz: Path, meeting_id: str, track_id: str, recording_id: str, sequence: int) -> Path:
    """Só monta caminho com componentes já validados (sem `..`, sem barra)."""
    if validar_inicio(meeting_id, track_id, recording_id, True):
        raise ValueError("componente de caminho inválido")
    return Path(raiz) / meeting_id / track_id / recording_id / f"{int(sequence):06d}.webm"


def lacunas(sequencias: list, ultima: int | None = None) -> list:
    """Sequências que faltam entre 0 e `ultima` (ou a maior recebida)."""
    recebidas = set(int(s) for s in sequencias)
    if ultima is None:
        ultima = max(recebidas) if recebidas else -1
    return [s for s in range(0, int(ultima) + 1) if s not in recebidas]


def data_para_apagar(agora: datetime, dias: int) -> datetime:
    return agora + timedelta(days=int(dias))
