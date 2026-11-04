"""Regras puras da transcrição pós-reunião (Fase 3 de
`docs/tasks-legenda-tempo-real.md`): sem banco, sem rede.
"""
from __future__ import annotations

# Plano grátis do Groq (whisper-large-v3), medido em 14/10/2026.
LIMITE_S_HORA = 7200
LIMITE_S_DIA = 28800

# Abaixo disso a gravação inteira é silêncio: não gasta cota e evita o
# Whisper inventar frase em áudio vazio.
LIMIAR_SILENCIO_DB = -50.0
NO_SPEECH_MAX = 0.6

ESPERA_COTA_HORA_S = 300
ESPERA_COTA_DIA_S = 1800


def eh_silencio(pico_db: float | None) -> bool:
    """Sem medição (None) não é silêncio: na dúvida, transcreve."""
    return pico_db is not None and pico_db <= LIMIAR_SILENCIO_DB


def filtrar_segmentos(segmentos: list) -> list:
    """Segmentos do Whisper com fala de verdade, no formato gravado."""
    limpos = []
    for s in segmentos or []:
        texto = str(s.get("text") or "").strip()
        if not texto or float(s.get("no_speech_prob") or 0) >= NO_SPEECH_MAX:
            continue
        limpos.append({"inicio": float(s.get("start") or 0), "fim": float(s.get("end") or 0), "texto": texto})
    return limpos


def espera_por_cota(usado_hora: float, usado_dia: float, duracao_s: float,
                    limite_hora: int = LIMITE_S_HORA, limite_dia: int = LIMITE_S_DIA) -> int:
    """Segundos a esperar antes de enviar `duracao_s` de áudio (0 = pode enviar)."""
    if usado_dia + duracao_s > limite_dia:
        return ESPERA_COTA_DIA_S
    if usado_hora + duracao_s > limite_hora:
        return ESPERA_COTA_HORA_S
    return 0
