"""
Módulo do Webhook Tactiq do SALEIA.

Recebe e processa automaticamente os dados enviados pelo Tactiq
ao final de cada reunião no Google Meet.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request

from agent.diagnostico import diagnostico_financeiro
from agent.perfil_disc import perfil_disc
from agent.recapitulacao import recapitulacao_completa
from api.notificador import notificar_vendedor
from api.processador_tempo_real import limpar_cache_reuniao

# Configuração de logging
logger = logging.getLogger(__name__)

# Pasta onde os relatórios são salvos
PASTA_RELATORIOS = Path("data/relatorios")


def _validar_assinatura_webhook(payload_bytes: bytes, assinatura_header: Optional[str]) -> bool:
    """
    Valida a assinatura do webhook do Tactiq para garantir autenticidade.
    Se TACTIQ_WEBHOOK_SECRET não estiver configurado, aceita qualquer requisição.

    Args:
        payload_bytes: Corpo da requisição em bytes.
        assinatura_header: Valor do header X-Tactiq-Signature.

    Returns:
        True se assinatura válida ou se validação não estiver configurada.
    """
    secret = os.getenv("TACTIQ_WEBHOOK_SECRET")

    # Se não configurado, não valida (modo desenvolvimento)
    if not secret:
        return True

    if not assinatura_header:
        logger.warning("⚠️ Webhook recebido sem header de assinatura")
        return False

    # Calcula HMAC-SHA256 esperado
    assinatura_esperada = hmac.new(
        secret.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()

    # Comparação segura contra timing attacks
    return hmac.compare_digest(assinatura_esperada, assinatura_header)


def _extrair_nome_cliente(meeting_title: str, participants: list[str]) -> str:
    """
    Extrai o nome do cliente a partir do título da reunião ou participantes.

    Args:
        meeting_title: Título da reunião (ex: "Consultoria - Cliente João").
        participants: Lista de e-mails dos participantes.

    Returns:
        Nome do cliente identificado.
    """
    # Tenta extrair do título (formato: "Consultoria - Cliente NomeCliente")
    separadores = [" - ", " – ", ": ", " | "]
    for sep in separadores:
        if sep in meeting_title:
            partes = meeting_title.split(sep, 1)
            if len(partes) > 1:
                nome = partes[-1].strip()
                if nome:
                    return nome

    # Fallback: usa o e-mail do segundo participante (assume que o primeiro é o vendedor)
    email_vendedor = os.getenv("EMAIL_VENDEDOR", "").lower()
    for participante in participants:
        if participante.lower() != email_vendedor:
            # Usa a parte antes do @ como nome
            return participante.split("@")[0].replace(".", " ").title()

    return meeting_title or "Cliente"


def _gerar_relatorio_id(data: str, nome_cliente: str) -> str:
    """
    Gera um ID único para o relatório baseado em data e nome do cliente.

    Args:
        data: Data da reunião (ISO 8601).
        nome_cliente: Nome do cliente.

    Returns:
        ID do relatório no formato AAAA-MM-DD_NomeCliente.
    """
    try:
        dt = datetime.fromisoformat(data.replace("Z", "+00:00"))
        data_formatada = dt.strftime("%Y-%m-%d_%H-%M")
    except (ValueError, AttributeError):
        data_formatada = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M")

    # Sanitiza o nome do cliente para uso em nome de arquivo.
    # Normaliza caracteres Unicode para ASCII (transliteração) preservando o significado.
    nome_normalizado = unicodedata.normalize("NFKD", nome_cliente)
    nome_ascii = nome_normalizado.encode("ascii", errors="ignore").decode()
    # Permite apenas letras, números, espaços e hífens; substitui o resto por underscore
    nome_sanitizado = re.sub(r"[^\w\s-]", "", nome_ascii).strip()
    nome_sanitizado = re.sub(r"[\s]+", "_", nome_sanitizado) or "cliente"

    return f"{data_formatada}_{nome_sanitizado}"


def _validar_relatorio_id(relatorio_id: str) -> str:
    """
    Valida e sanitiza o ID do relatório para evitar path traversal.

    Aceita apenas caracteres alfanuméricos, hífens e underscores.
    Levanta ValueError se o ID contiver caracteres inválidos.

    Args:
        relatorio_id: ID a ser validado.

    Returns:
        ID sanitizado.
    """
    if not relatorio_id or not re.match(r"^[\w\-]+$", relatorio_id):
        raise ValueError(f"ID de relatório inválido: '{relatorio_id}'")
    return relatorio_id


def salvar_relatorio(relatorio: dict, relatorio_id: str) -> Path:
    """
    Salva o relatório em JSON na pasta /data/relatorios.

    Args:
        relatorio: Dados completos do relatório.
        relatorio_id: ID único do relatório (somente caracteres seguros).

    Returns:
        Caminho do arquivo salvo.
    """
    relatorio_id = _validar_relatorio_id(relatorio_id)
    PASTA_RELATORIOS.mkdir(parents=True, exist_ok=True)
    # Resolve o caminho absoluto e verifica que está dentro da pasta permitida
    pasta_base = PASTA_RELATORIOS.resolve()
    caminho = (pasta_base / f"{relatorio_id}.json").resolve()
    if not caminho.is_relative_to(pasta_base):
        raise ValueError(f"Caminho inválido detectado: {caminho}")

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(relatorio, f, ensure_ascii=False, indent=2)

    logger.info(f"💾 Relatório salvo em: {caminho}")
    return caminho


def carregar_relatorio(relatorio_id: str) -> Optional[dict]:
    """
    Carrega um relatório salvo pelo seu ID.

    Args:
        relatorio_id: ID do relatório (somente caracteres seguros).

    Returns:
        Dicionário com os dados do relatório ou None se não encontrado.
    """
    try:
        relatorio_id = _validar_relatorio_id(relatorio_id)
    except ValueError:
        return None

    # Resolve o caminho absoluto e verifica que está dentro da pasta permitida
    pasta_base = PASTA_RELATORIOS.resolve()
    caminho = (pasta_base / f"{relatorio_id}.json").resolve()
    if not caminho.is_relative_to(pasta_base):
        return None

    if not caminho.exists():
        return None

    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


def listar_relatorios() -> list[dict]:
    """
    Lista todos os relatórios salvos com seus metadados.

    Returns:
        Lista de dicionários com id, data, nome_cliente e arquivo.
    """
    if not PASTA_RELATORIOS.exists():
        return []

    relatorios = []
    for arquivo in sorted(PASTA_RELATORIOS.glob("*.json"), reverse=True):
        relatorio_id = arquivo.stem
        try:
            with open(arquivo, "r", encoding="utf-8") as f:
                dados = json.load(f)
            relatorios.append(
                {
                    "relatorio_id": relatorio_id,
                    "data": dados.get("data", "N/A"),
                    "nome_cliente": dados.get("nome_cliente", "N/A"),
                    "meeting_title": dados.get("meeting_title", "N/A"),
                    "arquivo": str(arquivo),
                }
            )
        except Exception as e:
            logger.warning(f"Erro ao ler relatório {arquivo}: {e}")

    return relatorios


async def processar_webhook_tactiq(payload: dict) -> dict:
    """
    Processa o webhook recebido do Tactiq de forma completa e automatizada.

    Fluxo:
    1. Valida que há transcrição
    2. Processa em paralelo: diagnóstico financeiro + perfil DISC
    3. Gera recapitulação completa com os resultados
    4. Salva relatório em JSON
    5. Notifica o vendedor (WhatsApp ou e-mail)

    Args:
        payload: Dados do webhook do Tactiq.

    Returns:
        Dicionário com status e ID do relatório gerado.
    """
    transcript = payload.get("transcript", "").strip()
    meeting_title = payload.get("meeting_title", "Reunião sem título")
    participants = payload.get("participants", [])
    data = payload.get("date", datetime.now(timezone.utc).isoformat())
    meeting_id = payload.get("meeting_id", "")

    # Validação: transcrição é obrigatória
    if not transcript:
        raise HTTPException(
            status_code=422,
            detail="Payload inválido: campo 'transcript' é obrigatório e não pode ser vazio.",
        )

    if len(transcript) < 50:
        raise HTTPException(
            status_code=422,
            detail="Transcrição muito curta para processamento. Mínimo de 50 caracteres.",
        )

    logger.info(f"🚀 Processando webhook Tactiq — Reunião: '{meeting_title}'")

    # Extrai nome do cliente
    nome_cliente = _extrair_nome_cliente(meeting_title, participants)

    # Processa em PARALELO: diagnóstico financeiro + perfil DISC
    logger.info("⚡ Iniciando processamento paralelo (diagnóstico + DISC)...")
    resultado_financeiro, resultado_disc = await asyncio.gather(
        diagnostico_financeiro(transcript),
        perfil_disc(transcript),
    )
    logger.info("✅ Processamento paralelo concluído")

    # Gera recapitulação completa com os resultados
    logger.info("🧠 Gerando recapitulação completa...")
    resultado_recapitulacao = await recapitulacao_completa(
        transcript, resultado_financeiro, resultado_disc
    )
    logger.info("✅ Recapitulação gerada")

    # Gera ID único do relatório
    relatorio_id = _gerar_relatorio_id(data, nome_cliente)

    # Monta o relatório completo
    relatorio_completo = {
        "relatorio_id": relatorio_id,
        "meeting_title": meeting_title,
        "nome_cliente": nome_cliente,
        "participants": participants,
        "data": data,
        "transcript_tamanho": len(transcript),
        **resultado_recapitulacao,
        "diagnostico_financeiro": resultado_financeiro,
        "perfil_disc_completo": resultado_disc,
        "processado_em": datetime.now(timezone.utc).isoformat(),
    }

    # Salva o relatório ANTES de notificar (garantia de não perder dados)
    caminho_arquivo = salvar_relatorio(relatorio_completo, relatorio_id)
    logger.info(f"💾 Relatório salvo: {caminho_arquivo}")

    # Notifica o vendedor (WhatsApp com fallback para e-mail)
    logger.info("📤 Enviando notificação ao vendedor...")
    resultado_notificacao = await notificar_vendedor(relatorio_completo)
    logger.info(f"📤 Notificação: {resultado_notificacao}")

    # Limpa o cache da reunião (se havia dados de tempo real)
    if meeting_id:
        limpar_cache_reuniao(meeting_id)

    return {
        "status": "processado",
        "relatorio_id": relatorio_id,
        "nome_cliente": nome_cliente,
        "notificacao": resultado_notificacao,
        "arquivo": str(caminho_arquivo),
    }


async def validar_e_processar_webhook(request: Request) -> dict:
    """
    Valida a assinatura do webhook e processa o payload.

    Args:
        request: Objeto da requisição FastAPI.

    Returns:
        Resultado do processamento.
    """
    # Lê o corpo bruto para validar assinatura
    payload_bytes = await request.body()

    # Valida assinatura (se configurada)
    assinatura = request.headers.get("X-Tactiq-Signature")
    if not _validar_assinatura_webhook(payload_bytes, assinatura):
        raise HTTPException(
            status_code=401,
            detail="Assinatura do webhook inválida. Verifique TACTIQ_WEBHOOK_SECRET.",
        )

    # Parseia o JSON
    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Payload inválido: não é um JSON válido.",
        )

    return await processar_webhook_tactiq(payload)
