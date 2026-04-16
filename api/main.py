"""
SALEIA — Sistema de Automação de Leads, Engajamento e Inteligência Artificial em Atendimento.

API principal do backend com todos os endpoints do pipeline automatizado.
"""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Carrega variáveis de ambiente do .env
load_dotenv()

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Eventos de inicialização e encerramento da aplicação."""
    logger.info("🚀 SALEIA iniciando...")
    # Garante que a pasta de relatórios existe
    from pathlib import Path
    Path("data/relatorios").mkdir(parents=True, exist_ok=True)
    logger.info("📁 Pasta de relatórios verificada")
    yield
    logger.info("🛑 SALEIA encerrando...")


# Inicializa a aplicação FastAPI
app = FastAPI(
    title="SALEIA — Sistema de Automação de Leads com IA",
    description=(
        "Pipeline 100% automatizado de transcrição, análise e relatório de reuniões de vendas. "
        "Integração com Tactiq (Google Meet) + GPT-4o + Z-API (WhatsApp)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Configuração de CORS para acesso do painel frontend.
# Em produção, defina CORS_ORIGINS com as origens permitidas explicitamente.
# Ex: CORS_ORIGINS=https://meupainel.com,https://app.meupainel.com
# Em desenvolvimento local, use CORS_ORIGINS=http://localhost:3000
cors_origins_env = os.getenv("CORS_ORIGINS", "")
cors_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
if not cors_origins:
    logger.warning(
        "⚠️ CORS_ORIGINS não configurado. "
        "Definindo como ['http://localhost:3000'] para desenvolvimento. "
        "Configure explicitamente em produção."
    )
    cors_origins = ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# MODELOS DE DADOS
# ─────────────────────────────────────────────


class PayloadTactiq(BaseModel):
    """Estrutura do payload enviado pelo Tactiq via webhook."""

    meeting_title: str
    participants: list[str] = []
    date: str
    transcript: str
    meeting_id: str = ""


class PayloadTranscricaoManual(BaseModel):
    """Para processamento manual de transcrição colada pelo vendedor."""

    transcript: str
    meeting_title: str = "Reunião Manual"
    nome_cliente: str = ""


class PayloadTranscricaoParcial(BaseModel):
    """Para atualizar transcrição parcial durante a reunião."""

    meeting_id: str
    transcript: str


# ─────────────────────────────────────────────
# ENDPOINTS PRINCIPAIS
# ─────────────────────────────────────────────


@app.get("/", tags=["Sistema"])
async def raiz():
    """Verifica se o sistema está no ar."""
    return {
        "status": "online",
        "sistema": "SALEIA",
        "versao": "1.0.0",
        "descricao": "Pipeline automatizado de análise de reuniões de vendas",
    }


@app.get("/health", tags=["Sistema"])
async def health_check():
    """Health check para monitoramento."""
    openai_configurado = bool(os.getenv("OPENAI_API_KEY"))
    zapi_configurado = bool(os.getenv("ZAPI_INSTANCE") and os.getenv("ZAPI_TOKEN"))
    smtp_configurado = bool(os.getenv("SMTP_USER") and os.getenv("SMTP_PASS"))

    return {
        "status": "ok",
        "openai": "configurado" if openai_configurado else "não configurado",
        "whatsapp_zapi": "configurado" if zapi_configurado else "não configurado",
        "email_smtp": "configurado" if smtp_configurado else "não configurado",
    }


# ─────────────────────────────────────────────
# WEBHOOK TACTIQ — PROCESSAMENTO AUTOMÁTICO
# ─────────────────────────────────────────────


@app.post("/webhook/tactiq", tags=["Webhook Tactiq"])
async def webhook_tactiq(request: Request):
    """
    Endpoint principal do pipeline automatizado.

    Recebe o webhook do Tactiq ao final de uma reunião no Google Meet.
    Processa automaticamente:
    - Diagnóstico financeiro
    - Perfil DISC
    - Recapitulação completa
    - Salva relatório
    - Notifica o vendedor (WhatsApp ou e-mail)

    O vendedor não precisa fazer nada — o sistema cuida de tudo.
    """
    from api.webhook_tactiq import validar_e_processar_webhook

    resultado = await validar_e_processar_webhook(request)
    return resultado


@app.post("/processar/manual", tags=["Processamento Manual"])
async def processar_manual(payload: PayloadTranscricaoManual):
    """
    Processamento manual de transcrição.

    Use quando o vendedor cola a transcrição do Tactiq manualmente
    (fluxo de transição antes do webhook automático estar configurado).
    """
    from api.webhook_tactiq import processar_webhook_tactiq
    from datetime import datetime, timezone

    dados = {
        "transcript": payload.transcript,
        "meeting_title": payload.meeting_title,
        "participants": [],
        "date": datetime.now(timezone.utc).isoformat(),
        "meeting_id": "",
    }

    # Adiciona nome do cliente se fornecido
    if payload.nome_cliente:
        dados["meeting_title"] = f"Reunião - {payload.nome_cliente}"

    resultado = await processar_webhook_tactiq(dados)
    return resultado


# ─────────────────────────────────────────────
# RELATÓRIOS
# ─────────────────────────────────────────────


@app.get("/relatorios", tags=["Relatórios"])
async def listar_relatorios():
    """
    Lista todos os relatórios gerados automaticamente.
    Ordenados do mais recente para o mais antigo.
    """
    from api.webhook_tactiq import listar_relatorios as _listar

    relatorios = _listar()
    return {
        "total": len(relatorios),
        "relatorios": relatorios,
    }


@app.get("/relatorio/{relatorio_id}", tags=["Relatórios"])
async def buscar_relatorio(relatorio_id: str):
    """
    Busca um relatório específico pelo ID.

    O ID é gerado automaticamente no formato: AAAA-MM-DD_HH-MM_NomeCliente
    """
    from api.webhook_tactiq import carregar_relatorio

    relatorio = carregar_relatorio(relatorio_id)
    if not relatorio:
        raise HTTPException(
            status_code=404,
            detail=f"Relatório '{relatorio_id}' não encontrado.",
        )
    return relatorio


# ─────────────────────────────────────────────
# NOTIFICAÇÕES
# ─────────────────────────────────────────────


@app.post("/notificar/{relatorio_id}", tags=["Notificações"])
async def reenviar_notificacao(relatorio_id: str):
    """
    Reenvia a notificação de um relatório já processado.

    Use quando o vendedor não recebeu a notificação automática.
    """
    from api.notificador import notificar_vendedor
    from api.webhook_tactiq import carregar_relatorio

    relatorio = carregar_relatorio(relatorio_id)
    if not relatorio:
        raise HTTPException(
            status_code=404,
            detail=f"Relatório '{relatorio_id}' não encontrado.",
        )

    resultado_notificacao = await notificar_vendedor(relatorio)

    return {
        "relatorio_id": relatorio_id,
        "notificacao": resultado_notificacao,
    }


# ─────────────────────────────────────────────
# PROCESSAMENTO EM TEMPO REAL (DURANTE A REUNIÃO)
# ─────────────────────────────────────────────


@app.get("/tactiq/status/{meeting_id}", tags=["Tempo Real"])
async def status_reuniao(meeting_id: str):
    """
    Consulta o status de uma reunião em andamento.

    O painel frontend chama este endpoint a cada 60 segundos.
    Retorna dicas baseadas na transcrição parcial atual.

    Se a API do Tactiq estiver disponível (plano pago), busca automaticamente.
    Caso contrário, instrui o vendedor a colar manualmente.
    """
    from api.processador_tempo_real import processar_status_reuniao

    return await processar_status_reuniao(meeting_id)


@app.post("/tactiq/transcript/{meeting_id}", tags=["Tempo Real"])
async def atualizar_transcript_parcial(meeting_id: str, payload: PayloadTranscricaoParcial):
    """
    Atualiza a transcrição parcial de uma reunião em andamento.

    Usado quando o vendedor cola manualmente a transcrição do Tactiq
    durante a reunião para receber dicas em tempo real.
    """
    from api.processador_tempo_real import atualizar_transcript_parcial

    atualizar_transcript_parcial(meeting_id, payload.transcript)
    return {
        "status": "atualizado",
        "meeting_id": meeting_id,
        "tamanho_transcript": len(payload.transcript),
    }


# ─────────────────────────────────────────────
# AGENTES INDIVIDUAIS (USO AVANÇADO)
# ─────────────────────────────────────────────


class PayloadTranscricao(BaseModel):
    """Payload para endpoints de agentes individuais."""
    transcript: str


@app.post("/diagnostico-financeiro", tags=["Agentes IA"])
async def endpoint_diagnostico_financeiro(payload: PayloadTranscricao):
    """
    Executa apenas o diagnóstico financeiro sobre uma transcrição.
    Útil para testes ou uso isolado do agente.
    """
    from agent.diagnostico import diagnostico_financeiro as _diagnostico

    if not payload.transcript.strip():
        raise HTTPException(status_code=422, detail="Transcrição não pode ser vazia.")

    return await _diagnostico(payload.transcript)


@app.post("/perfil-disc", tags=["Agentes IA"])
async def endpoint_perfil_disc(payload: PayloadTranscricao):
    """
    Executa apenas a análise de perfil DISC sobre uma transcrição.
    Útil para testes ou uso isolado do agente.
    """
    from agent.perfil_disc import perfil_disc as _perfil_disc

    if not payload.transcript.strip():
        raise HTTPException(status_code=422, detail="Transcrição não pode ser vazia.")

    return await _perfil_disc(payload.transcript)


@app.post("/recapitulacao", tags=["Agentes IA"])
async def endpoint_recapitulacao(payload: PayloadTranscricao):
    """
    Executa o pipeline completo de análise sobre uma transcrição.
    Processa em paralelo: diagnóstico financeiro + DISC + recapitulação.
    """
    import asyncio
    from agent.diagnostico import diagnostico_financeiro as _diagnostico
    from agent.perfil_disc import perfil_disc as _perfil_disc
    from agent.recapitulacao import recapitulacao_completa as _recapitulacao

    if not payload.transcript.strip():
        raise HTTPException(status_code=422, detail="Transcrição não pode ser vazia.")

    # Processamento paralelo
    resultado_financeiro, resultado_disc = await asyncio.gather(
        _diagnostico(payload.transcript),
        _perfil_disc(payload.transcript),
    )

    resultado_final = await _recapitulacao(
        payload.transcript, resultado_financeiro, resultado_disc
    )

    return {
        "recapitulacao": resultado_final,
        "diagnostico_financeiro": resultado_financeiro,
        "perfil_disc": resultado_disc,
    }
