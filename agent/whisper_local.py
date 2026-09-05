"""Transcricao de audio local (self-hosted) via faster-whisper.

Terceira opcao para TRANSCRICAO_PROVEDOR, ao lado de "whisper" (OpenAI) e
"groq" — roda inteiramente no proprio servidor onde a SALEIA esta rodando,
sem enviar nenhum audio a uma API externa. Mesmo espirito de
services/embeddings/ollama_provider.py (provedor local, sem custo por
chamada), mas aqui como um modulo simples em vez de uma interface nova —
so existe hoje um caminho de transcricao real (/audio-transcricao em
api/main.py), nao ha varios modulos de negocio chamando isso.

O modelo e carregado uma unica vez por processo (singleton, recarregado
so se WHISPER_LOCAL_MODEL/DEVICE/COMPUTE_TYPE mudar) — carregar a cada
chamada seria proibitivamente lento.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

logger = logging.getLogger("saleia.whisper_local")

_model = None
_model_lock = threading.Lock()
_model_key: Optional[tuple] = None


def _current_config_key() -> tuple:
    return (
        os.environ.get("WHISPER_LOCAL_MODEL", "small"),
        os.environ.get("WHISPER_LOCAL_DEVICE", "cpu"),
        os.environ.get("WHISPER_LOCAL_COMPUTE_TYPE", "int8"),
    )


def _get_model(refresh: bool = False):
    """Retorna a instancia carregada do WhisperModel (faster-whisper),
    recarregando so se a configuracao mudou desde a ultima chamada
    (mesmo padrao de singleton configuravel de
    services/embeddings/factory.py::get_embedding_provider)."""
    global _model, _model_key

    config_key = _current_config_key()
    with _model_lock:
        if not refresh and _model is not None and _model_key == config_key:
            return _model

        from faster_whisper import WhisperModel

        model_size, device, compute_type = config_key
        logger.info(
            "[WhisperLocal] Carregando modelo '%s' (device=%s, compute_type=%s)...",
            model_size, device, compute_type,
        )
        _model = WhisperModel(model_size, device=device, compute_type=compute_type)
        _model_key = config_key
        return _model


def transcrever(caminho_arquivo: str, idioma: str = "pt") -> str:
    """Transcreve um arquivo de audio local com o modelo Whisper carregado
    no proprio processo. Nunca envia o arquivo pra nenhuma API externa.

    Levanta a excecao original em caso de falha (mesmo contrato dos
    callers de OpenAI/Groq em api/main.py::_transcrever_via_*) — quem
    chama decide como degradar; nunca cai silenciosamente para um
    provedor pago (TAREFA 3.11 do PROMPT MESTRE).
    """
    modelo = _get_model()
    segments, _info = modelo.transcribe(caminho_arquivo, language=idioma, vad_filter=True)
    return " ".join(segment.text.strip() for segment in segments).strip()


def reset_model_cache() -> None:
    """Forca a proxima chamada a recarregar o modelo. Usado por testes."""
    global _model, _model_key
    with _model_lock:
        _model = None
        _model_key = None


async def health_check() -> dict:
    """Confirma que o modelo local carrega e consegue ser instanciado —
    nao transcreve audio nenhum, so garante que a dependencia/modelo
    estao disponiveis (mesmo contrato de retorno de
    services/embeddings/provider.py::EmbeddingProvider.health_check).
    """
    try:
        _get_model()
        model_size, device, compute_type = _current_config_key()
        return {
            "ok": True,
            "detalhe": f"Modelo '{model_size}' carregado ({device}/{compute_type}).",
            "modelo": model_size,
        }
    except Exception as e:
        return {"ok": False, "detalhe": str(e)[:200], "modelo": _current_config_key()[0]}
