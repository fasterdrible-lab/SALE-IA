"""
Módulo de Processamento em Tempo Real do SALEIA.

Implementa polling automático durante a reunião para fornecer
dicas ao painel do vendedor a cada 60 segundos.
"""

import logging
import os
from typing import Optional

import httpx

# Configuração de logging
logger = logging.getLogger(__name__)

# Armazenamento em memória das transcrições parciais por reunião
# Em produção, substituir por Redis ou banco de dados
_cache_transcricoes: dict[str, dict] = {}


def _get_cache_reuniao(meeting_id: str) -> dict:
    """Retorna ou inicializa o cache de uma reunião."""
    if meeting_id not in _cache_transcricoes:
        _cache_transcricoes[meeting_id] = {
            "transcript": "",
            "ultima_atualizacao": None,
            "dicas": None,
        }
    return _cache_transcricoes[meeting_id]


def atualizar_transcript_parcial(meeting_id: str, transcript: str) -> None:
    """
    Atualiza a transcrição parcial de uma reunião em andamento.
    Chamado pelo webhook quando Tactiq envia atualizações parciais.
    """
    from datetime import datetime, timezone

    cache = _get_cache_reuniao(meeting_id)
    cache["transcript"] = transcript
    cache["ultima_atualizacao"] = datetime.now(timezone.utc).isoformat()
    logger.info(f"📝 Transcrição parcial atualizada para reunião {meeting_id}")


def limpar_cache_reuniao(meeting_id: str) -> None:
    """Remove a reunião do cache após o processamento final."""
    if meeting_id in _cache_transcricoes:
        del _cache_transcricoes[meeting_id]
        logger.info(f"🗑️ Cache da reunião {meeting_id} removido")


async def buscar_transcript_tactiq(meeting_id: str) -> Optional[str]:
    """
    Busca a transcrição parcial mais recente via API do Tactiq.

    Nota: Disponível apenas em planos pagos do Tactiq.
    Se não disponível, retorna None e o sistema usa a transcrição do cache.

    Args:
        meeting_id: ID da reunião no Tactiq.

    Returns:
        Texto da transcrição parcial ou None se não disponível.
    """
    tactiq_api_key = os.getenv("TACTIQ_API_KEY")

    if not tactiq_api_key:
        logger.debug("TACTIQ_API_KEY não configurada. API em tempo real indisponível.")
        return None

    # Endpoint da API do Tactiq (verificar documentação do plano)
    url = f"https://api.tactiq.io/v1/meetings/{meeting_id}/transcript"
    headers = {"Authorization": f"Bearer {tactiq_api_key}"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resposta = await client.get(url, headers=headers)
            if resposta.status_code == 200:
                dados = resposta.json()
                return dados.get("transcript", "")
            elif resposta.status_code == 404:
                logger.debug(f"Reunião {meeting_id} não encontrada na API do Tactiq")
                return None
            else:
                logger.warning(
                    f"Erro ao buscar transcrição Tactiq: {resposta.status_code}"
                )
                return None
    except httpx.TimeoutException:
        logger.warning("Timeout ao buscar transcrição do Tactiq")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado ao acessar API do Tactiq: {e}")
        return None


async def processar_status_reuniao(meeting_id: str) -> dict:
    """
    Processa o status atual de uma reunião em andamento.
    Retorna dicas para o painel do vendedor.

    Fluxo:
    1. Tenta buscar transcrição parcial via API do Tactiq
    2. Se não disponível, usa transcrição do cache (colada manualmente)
    3. Processa com IA e retorna dicas
    4. Se nenhuma transcrição disponível, retorna instrução para colar manualmente

    Args:
        meeting_id: Identificador único da reunião.

    Returns:
        Dicionário com status e dicas para o vendedor.
    """
    from agent.recapitulacao import dicas_tempo_real

    # Tenta buscar via API do Tactiq
    transcript_tactiq = await buscar_transcript_tactiq(meeting_id)

    # Fallback: usa cache local
    cache = _get_cache_reuniao(meeting_id)
    transcript = transcript_tactiq or cache.get("transcript", "")

    # Sem transcrição disponível
    if not transcript or len(transcript.strip()) < 100:
        return {
            "meeting_id": meeting_id,
            "status": "aguardando_transcricao",
            "api_tactiq_disponivel": transcript_tactiq is not None,
            "instrucao": (
                "Cole a transcrição parcial do Tactiq neste campo para receber dicas em tempo real."
            ),
            "dicas": None,
            "ultima_atualizacao": cache.get("ultima_atualizacao"),
        }

    # Processa com IA para gerar dicas
    try:
        dicas = await dicas_tempo_real(transcript)
        cache["dicas"] = dicas

        return {
            "meeting_id": meeting_id,
            "status": "em_andamento",
            "api_tactiq_disponivel": transcript_tactiq is not None,
            "dicas": dicas,
            "tamanho_transcript": len(transcript),
            "ultima_atualizacao": cache.get("ultima_atualizacao"),
        }
    except Exception as e:
        logger.error(f"Erro ao processar dicas em tempo real: {e}")
        return {
            "meeting_id": meeting_id,
            "status": "erro_processamento",
            "api_tactiq_disponivel": transcript_tactiq is not None,
            "erro": "Erro ao processar transcrição. Tente novamente.",
            "dicas": cache.get("dicas"),  # Retorna última dica válida se houver
        }
