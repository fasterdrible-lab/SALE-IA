"""
SALEIA — api/main.py
Backend FastAPI para o Assistente de Vendas em Tempo Real.

Endpoints:
  POST /tempo-real           → análise em tempo real durante a reunião
  POST /webhook/tactiq       → recebe transcrição completa do Tactiq
  POST /diagnostico-financeiro → extrai dados financeiros da transcrição
  POST /perfil-disc          → identifica perfil DISC + objeções
  POST /recapitulacao-completa → recapitulação pós-reunião completa
  GET  /relatorio            → página HTML com último relatório
  GET  /health               → verificação de saúde do serviço
"""

import os
import re
import json
import uuid
import asyncio
import html as html_module
import logging
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Header, Form, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from api.ai_router import chamar_ia, definir_provedor_preferido, rotacionar_provedor_preferido, snapshot_provedores, snapshot_metricas, status_provedores
from api.database import (
    criar_tabelas,
    salvar_relatorio as db_salvar,
    listar_relatorios as db_listar,
    buscar_ultimo_relatorio as db_ultimo,
    obter_meeting_memory,
    db_health,
    contar_reunioes_ativas,
    contar_reunioes_hoje,
)

# ─────────────────────────────────────────────
# LOGGING ESTRUTURADO JSON
# ─────────────────────────────────────────────
_cid_var: ContextVar[str] = ContextVar("cid", default="-")


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        doc: dict = {
            "ts":     self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level":  record.levelname,
            "logger": record.name,
            "msg":    record.getMessage(),
            "cid":    _cid_var.get("-"),
        }
        if record.exc_info:
            doc["exc"] = self.formatException(record.exc_info)
        return json.dumps(doc, ensure_ascii=False)


def _configurar_logging() -> None:
    fmt = _JsonFormatter()
    saleia_log = logging.getLogger("saleia")
    saleia_log.setLevel(logging.INFO)
    if not saleia_log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(fmt)
        saleia_log.addHandler(h)
    else:
        for h in saleia_log.handlers:
            h.setFormatter(fmt)


logger = logging.getLogger("saleia.main")


# ─────────────────────────────────────────────
# MIDDLEWARE — CORRELATION ID
# ─────────────────────────────────────────────
class _CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        cid = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
        token = _cid_var.set(cid)
        try:
            response = await call_next(request)
        finally:
            _cid_var.reset(token)
        response.headers["X-Request-ID"] = cid
        return response

# ─────────────────────────────────────────────
# CONFIGURAÇÃO
# ─────────────────────────────────────────────
app = FastAPI(
    title="SALEIA — Assistente de Vendas IA",
    description="Backend para o assistente de vendas em tempo real no Google Meet",
    version="1.4.38",
)

app.add_middleware(_CorrelationMiddleware)

# CORS — permite requisições da extensão Chrome (chrome-extension://)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenTelemetry — chamado no nível do módulo para que o middleware
# seja registrado antes da primeira requisição (instrument_app em
# on_startup é tarde demais em algumas versões do Starlette).
def _configurar_opentelemetry() -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if not endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        headers_raw = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
        headers: dict = {}
        for part in headers_raw.split(","):
            if "=" in part:
                k, _, v = part.strip().partition("=")
                headers[k.strip()] = v.strip()

        resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "saleia")})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint + "/v1/traces", headers=headers)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        logging.getLogger("saleia.main").info("OpenTelemetry ativo → %s", endpoint)
    except Exception as _e:
        logging.getLogger("saleia.main").warning("OpenTelemetry não configurado: %s", _e)

_configurar_opentelemetry()

# Armazenamento em memória do último relatório (cache rápido)
ultimo_relatorio: dict = {}

# Pasta para persistência de relatórios em arquivo (fallback legado)
PASTA_RELATORIOS = Path("data/relatorios")
PASTA_RELATORIOS.mkdir(parents=True, exist_ok=True)

# Pasta para os arquivos originais anexados a documentos da Base de Conhecimento
PASTA_BASE_ARQUIVOS = Path("data/base_arquivos")
PASTA_BASE_ARQUIVOS.mkdir(parents=True, exist_ok=True)

async def _loop_metricas() -> None:
    """Background task: grava snapshot de métricas a cada 60s e verifica thresholds."""
    from api.metricas_historico import registrar
    from agent.alertas import verificar_thresholds
    await asyncio.sleep(15)  # aguarda startup completo
    while True:
        try:
            banco   = await asyncio.to_thread(db_health)
            ativas  = await asyncio.to_thread(contar_reunioes_ativas)
            hoje    = await asyncio.to_thread(contar_reunioes_hoje)
            ia_snap = snapshot_metricas()
            await asyncio.to_thread(
                registrar, banco, ativas, hoje,
                ia_snap.get("chamadas_total", 0),
                ia_snap.get("chamadas_falha", 0),
            )
            await asyncio.to_thread(verificar_thresholds, ia_snap, banco)
        except Exception as _e:
            logger.warning("Erro no loop de métricas: %s", _e)
        await asyncio.sleep(60)


@app.on_event("startup")
async def on_startup():
    _configurar_logging()
    criar_tabelas()
    logger.info("✅ Banco de dados inicializado.")
    try:
        from agent.sessao_manager import criar_tabela_sessoes, criar_tabela_usuarios, migrar_colunas_usuarios
        criar_tabela_sessoes()
        criar_tabela_usuarios()
        migrar_colunas_usuarios()
    except Exception as e:
        logger.warning("Tabelas MySQL não criadas: %s", e)
    try:
        from agent.visual_scenario import criar_tabela_visual_scenarios
        criar_tabela_visual_scenarios()
    except Exception as e:
        logger.warning("Tabela visual_scenarios não criada: %s", e)
    try:
        from agent.sales_memory import criar_tabela_sales_memories, migrar_coluna_embedding_memories
        criar_tabela_sales_memories()
        migrar_coluna_embedding_memories()
    except Exception as e:
        logger.warning("Tabela sales_memories não criada/migrada: %s", e)
    try:
        from agent.sales_memory import migrar_colunas_embedding_metadata_memories
        migrar_colunas_embedding_metadata_memories()
    except Exception as e:
        logger.warning("Colunas de metadados de embedding (sales_memories) não migradas: %s", e)
    try:
        from agent.sessao_manager import migrar_colunas_embedding_metadata_base_conhecimento
        migrar_colunas_embedding_metadata_base_conhecimento()
    except Exception as e:
        logger.warning("Tabela/colunas base_conhecimento não migradas: %s", e)
    try:
        from agent.playbook_generator import criar_tabelas_playbook
        criar_tabelas_playbook()
    except Exception as e:
        logger.warning("Tabelas de playbook não criadas: %s", e)
    try:
        from agent.skill_resolver import criar_tabela_skills
        criar_tabela_skills()
    except Exception as e:
        logger.warning("Tabela skills não criada: %s", e)
    try:
        from agent.client_intelligence import criar_tabelas_clientes
        criar_tabelas_clientes()
    except Exception as e:
        logger.warning("Tabelas de clientes não criadas: %s", e)
    try:
        from agent.followup_generator import criar_tabela_followups
        criar_tabela_followups()
    except Exception as e:
        logger.warning("Tabela followups não criada: %s", e)
    try:
        from api.metricas_historico import criar_tabela_metricas, criar_tabela_teste_provedores
        criar_tabela_metricas()
        criar_tabela_teste_provedores()
    except Exception as e:
        logger.warning("Tabela metricas_historico não criada: %s", e)
    asyncio.create_task(_loop_metricas())

# ─────────────────────────────────────────────
# TABELA DE PREÇOS DOS PRODUTOS
# ─────────────────────────────────────────────
PRODUTOS = {
    "base": {
        "nome": "Produto Base",
        "valor": "3.000 - 4.000",
        "perfil": "Clientes com faturamento baixo, CLT ou micro-empreendedor com estoque"
    },
    "intermediario": {
        "nome": "Produto Intermediário",
        "valor": "15.984,00",
        "perfil": "Clientes com capacidade média de investimento"
    },
    "completo": {
        "nome": "Produto Completo",
        "valor": "29.892,00",
        "perfil": "Clientes com boa capacidade financeira e alto potencial de crescimento"
    }
}

# ─────────────────────────────────────────────
# MODELOS PYDANTIC
# ─────────────────────────────────────────────
class TempoRealRequest(BaseModel):
    transcricao_parcial: str
    historico: Optional[str] = ""
    perfil_disc_atual: Optional[str] = None
    mapa_financeiro: Optional[dict] = None
    meeting_id: Optional[str] = "default"
    transcricao_nova: Optional[str] = None  # delta: only new entries since last send


class TactiqWebhookRequest(BaseModel):
    meeting_title: Optional[str] = "Reunião de Vendas"
    participants: Optional[List[str]] = []
    date: Optional[str] = None
    transcript: str
    duration: Optional[int] = None


class DiagnosticoFinanceiroRequest(BaseModel):
    transcricao: str


class PerfilDiscRequest(BaseModel):
    transcricao: str


class RecapitulacaoRequest(BaseModel):
    transcricao: str
    titulo_reuniao: Optional[str] = "Reunião de Vendas"
    data: Optional[str] = None
    meeting_id: Optional[str] = None


class RecapitulacaoVivaRequest(BaseModel):
    meeting_id: str


class ProvedorIARequest(BaseModel):
    provedor: str


class IniciarSessaoRequest(BaseModel):
    meeting_id: str


class ConducaoRequest(BaseModel):
    tipo: str
    dados: Optional[dict] = None


class ExportarBaseRequest(BaseModel):
    titulo: Optional[str] = ""
    tipo: Optional[str] = "reuniao"




class AudioTranscricaoRequest(BaseModel):
    audio_base64: str          # formato: "data:audio/webm;base64,XXXX"
    mime_type: Optional[str] = "audio/webm"
    meeting_id: Optional[str] = "default"


class VisualScenarioRequest(BaseModel):
    meeting_id: str
    transcript: Optional[str] = ""
    score: Optional[int] = 0
    disc_profile: Optional[str] = ""
    emotional_state: Optional[str] = ""


# ─────────────────────────────────────────────
# PROMPTS DO SISTEMA
# ─────────────────────────────────────────────
PROMPT_TEMPO_REAL = """Você é SALEIA, um assistente de IA especializado em vendas consultivas em tempo real.

Analise a transcrição parcial de uma reunião de vendas e retorne um JSON com dicas imediatas para o vendedor.

CONTEXTO DOS PRODUTOS:
- Produto Base: R$ 3.000-4.000 → para quem fatura pouco ou CLT/baixo salário
- Produto Intermediário: R$ 15.984 → capacidade média
- Produto Completo: R$ 29.892 → boa capacidade financeira

MÉTODO DISC:
- D (Dominante): direto, quer resultados rápidos, não gosta de rodeios
- I (Influente): emotivo, gosta de histórias, precisa de empolgação e conexão
- S (Estável): cauteloso, precisa de segurança e garantias, medo de errar
- C (Consciente): analítico, quer dados concretos, compara, questiona tudo

Retorne APENAS um JSON válido com esta estrutura (sem markdown, sem explicações):
{
  "alerta_urgente": "texto se houver algo crítico, ou null",
  "perfil_disc": {
    "tipo": "D|I|S|C",
    "confianca": "alta|média|baixa",
    "evidencia": "trecho que evidencia o perfil",
    "acao_sugerida": "como adaptar a abordagem agora"
  },
  "proxima_acao": "próxima fala ou ação sugerida ao vendedor",
  "sinal_financeiro": "sinal financeiro identificado ou null",
  "produto_indicado": {
    "nome": "nome do produto",
    "valor": "valor",
    "justificativa": "por que este produto"
  },
  "oportunidade_perdida": "oportunidade não explorada ou null",
  "objecoes": [
    {
      "objecao": "objeção identificada ou provável",
      "resposta": "como responder"
    }
  ],
  "historico_resumido": "resumo de 2-3 linhas do que foi discutido"
}"""

PROMPT_DIAGNOSTICO_FINANCEIRO = """Você é um especialista em análise financeira para vendas consultivas.

Com base na transcrição da reunião, extraia as informações financeiras do cliente.

Retorne APENAS um JSON válido (sem markdown):
{
  "faturamento_mensal": "valor estimado ou 'não mencionado'",
  "capacidade_investimento": "quanto tem disponível para investir",
  "tem_cartao_credito": true/false/null,
  "limite_cartao": "valor ou 'não mencionado'",
  "tipo_renda": "CLT|autônomo|empresário|não identificado",
  "salario_clt": "valor se CLT ou null",
  "tem_estoque": true/false/null,
  "produto_recomendado": "base|intermediario|completo",
  "justificativa": "por que este produto baseado no perfil financeiro",
  "sinais_financeiros": ["lista de sinais detectados na conversa"],
  "capacidade_pagamento": "à vista|parcelado|cartão|misto|não identificado"
}"""

PROMPT_PERFIL_DISC = """Você é especialista no método DISC aplicado a vendas consultivas.

Analise a transcrição e identifique o perfil comportamental do cliente.

PERFIS:
- D (Dominante): assertivo, direto, orientado a resultados, impaciente, competitivo
- I (Influente): entusiasta, sociável, emotivo, otimista, gosta de reconhecimento
- S (Estável): paciente, leal, resistente a mudanças, precisa de segurança, evita conflitos
- C (Consciente): analítico, perfeccionista, meticuloso, questiona tudo, precisa de dados

Retorne APENAS um JSON válido (sem markdown):
{
  "perfil_primario": "D|I|S|C",
  "perfil_secundario": "D|I|S|C ou null",
  "confianca": "alta|média|baixa",
  "evidencias": ["lista de comportamentos/falas que indicam o perfil"],
  "como_abordar": "estratégia ideal para este perfil",
  "o_que_evitar": "o que NÃO fazer com este perfil",
  "gatilhos_emocionais": ["gatilhos que funcionam para este perfil"],
  "objecoes_provaveis": [
    {
      "objecao": "objeção típica deste perfil",
      "resposta": "como responder efetivamente"
    }
  ],
  "nivel_engajamento": "alto|médio|baixo",
  "momento_reuniao": "abertura|desenvolvimento|negociação|fechamento|resistência"
}"""

PROMPT_RECAPITULACAO = """Você é SALEIA, especialista em recapitulação de reuniões de vendas consultivas.

Gere uma recapitulação completa e estratégica da reunião com base na transcrição.

CONTEXTO DOS PRODUTOS:
- Produto Base: R$ 3.000-4.000
- Produto Intermediário: R$ 15.984
- Produto Completo: R$ 29.892

REGRAS PARA O BLOCO "propensao" (classificação de propensão de compra):
- Cada fator em fatores_positivos/fatores_negativos precisa vir de algo
  realmente dito na transcrição — nunca invente um fator genérico sem
  evidência. Quando houver uma fala que sustente o fator, cite-a
  literalmente (curta) em "evidencia"; se não houver fala específica,
  use null em "evidencia" em vez de inventar uma citação.
- fatores_pendentes lista o que ainda não foi identificado/confirmado na
  conversa (não são "negativos", são lacunas de informação).
- como_avancar são ações objetivas e práticas para o vendedor, não
  reafirmações do resumo.
- Se a transcrição for curta ou insuficiente para uma leitura confiável,
  retorne "nivel": "nao_determinada" (nunca force alta/media/baixa sem
  base) e explique a insuficiência em "resumo".
- Ao identificar os fatores, avalie estas dimensões (só inclua como fator
  a dimensão que realmente apareceu na conversa — não force as 9): Dor,
  Urgência, Orçamento, Autoridade (quem decide), Interesse, Intenção de
  compra, Engajamento, Próximo passo e Objeções.
- Nunca inclua raciocínio interno, apenas fatores/evidências/conclusões.

Retorne APENAS um JSON válido (sem markdown):
{
  "resumo_executivo": "3 linhas resumindo o essencial",
  "recapitulacao_emocional": {
    "estado_emocional_cliente": "como o cliente estava emocionalmente",
    "motivacoes_principais": ["o que realmente motiva este cliente"],
    "medos_objecoes": ["medos e resistências identificadas"],
    "nivel_interesse": "alto|médio|baixo",
    "rapport": "como foi a conexão com o vendedor"
  },
  "recapitulacao_estrategica": {
    "dores_identificadas": ["problemas que o cliente quer resolver"],
    "objetivos_cliente": ["o que o cliente quer alcançar"],
    "capacidade_financeira": "diagnóstico financeiro resumido",
    "produto_recomendado": {
      "nome": "nome do produto",
      "valor": "valor",
      "justificativa": "por que este produto para este cliente"
    },
    "objecoes_levantadas": ["objeções que surgiram"],
    "pontos_positivos": ["o que funcionou bem"]
  },
  "perfil_disc": {
    "tipo": "D|I|S|C",
    "descricao": "como o perfil se manifestou",
    "estrategia_fechamento": "melhor abordagem para fechar com este perfil"
  },
  "proximos_passos": [
    {
      "acao": "ação a ser tomada",
      "prazo": "quando",
      "responsavel": "vendedor|cliente"
    }
  ],
  "probabilidade_fechamento": "alta|média|baixa",
  "justificativa_probabilidade": "por que esta probabilidade",
  "propensao": {
    "nivel": "alta|media|baixa|nao_determinada",
    "confianca": "alta|media|baixa",
    "resumo": "1-2 linhas sobre a leitura geral de propensão",
    "fatores_positivos": [
      {"fator": "sinal objetivo identificado", "evidencia": "citação curta e literal ou null"}
    ],
    "fatores_negativos": [
      {"fator": "sinal de atenção identificado", "evidencia": "citação curta e literal ou null"}
    ],
    "fatores_pendentes": ["o que ainda não foi identificado/confirmado"],
    "como_avancar": ["próximas ações objetivas para aumentar a propensão"]
  }
}"""

# ─────────────────────────────────────────────
# FUNÇÃO AUXILIAR — CHAMAR GPT-4o
# ─────────────────────────────────────────────
def chamar_gpt(system_prompt: str, user_content: str, modelo: str = "gpt-4o") -> dict:
    """Chama a IA com fallback automático: OpenAI → Anthropic → Gemini."""
    return chamar_ia(system_prompt, user_content)


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

@app.get("/health")
def health_check():
    """Verificação de saúde do serviço — provedores de IA, banco e reuniões ativas."""
    snapshot  = snapshot_provedores()
    provedores = snapshot["ia"]
    banco     = db_health()
    ia_ok = any(
        p.get("status") == "ok" or p.get("status", "").startswith("degradado")
        for p in provedores.values()
    )
    status = "online" if ia_ok and banco.get("erro") is None else "degradado"
    return {
        "status":              status,
        "servico":             "SALEIA Backend",
        "versao":              "1.4.45",
        "timestamp":           datetime.now().isoformat(),
        "ia":                  provedores,
        "ordem_ia":            snapshot["ordem_ia"],
        "provedor_preferido":  snapshot["provedor_preferido"],
        "banco":               banco["banco"],
        "banco_latencia_ms":   banco["latencia_ms"],
        "banco_erro":          banco["erro"],
        "reunioes_ativas":     contar_reunioes_ativas(minutos=5),
        "reunioes_hoje":       contar_reunioes_hoje(),
    }


@app.get("/monitor/metricas")
def monitor_metricas(authorization: str | None = Header(default=None)):
    """Métricas de uso da IA em memória desde o último restart do serviço."""
    _req_auth(authorization)
    metricas = snapshot_metricas()
    banco = db_health()
    prov_transc = os.getenv("TRANSCRICAO_PROVEDOR", "whisper")
    groq_ok     = bool(os.getenv("GROQ_API_KEY", ""))
    whisper_ok  = bool(os.getenv("OPENAI_API_KEY", ""))
    return {
        "ia": metricas,
        "provedores_status": status_provedores(),
        "ultimo_teste": _ler_testes_compartilhados(),
        "banco": {
            "modo":        banco["banco"],
            "latencia_ms": banco["latencia_ms"],
            "erro":        banco["erro"],
        },
        "transcricao": {
            "provedor_ativo": prov_transc,
            "groq":           {"configurado": groq_ok,    "status": "ok" if groq_ok    else "sem_chave"},
            "openai_whisper": {"configurado": whisper_ok, "status": "ok" if whisper_ok else "sem_chave"},
        },
        "reunioes_ativas": contar_reunioes_ativas(minutos=5),
        "reunioes_hoje":   contar_reunioes_hoje(),
        "versao":          "1.4.45",
        "timestamp":       datetime.now().isoformat(),
    }


@app.get("/monitor/historico")
def monitor_historico(horas: int = 6, authorization: str | None = Header(default=None)):
    """Série temporal das métricas das últimas N horas (máx 24h). Requer JWT."""
    _req_auth(authorization)
    from api.metricas_historico import obter
    pontos = obter(min(max(horas, 1), 24))
    return {"pontos": pontos, "total": len(pontos), "horas": horas}


@app.post("/ai/provedor/proximo")
def trocar_provedor_preferido():
    """Rotaciona a prioridade dos provedores de IA sem expor credenciais."""
    return rotacionar_provedor_preferido()


@app.post("/ai/provedor/preferido")
def definir_provedor_ia(req: ProvedorIARequest):
    """Define manualmente o provedor preferido da IA sem expor credenciais."""
    return definir_provedor_preferido(req.provedor)


@app.websocket("/ws/heartbeat")
async def websocket_heartbeat(websocket: WebSocket):
    """
    Heartbeat WebSocket — a extensão Chrome mantém conexão aberta.
    Se o backend reiniciar, a extensão detecta a desconexão e tenta reconectar
    automaticamente, sem o vendedor precisar recarregar a página.
    """
    await websocket.accept()
    try:
        while True:
            await websocket.send_json({"status": "online", "ts": datetime.now().isoformat()})
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass


@app.post("/tempo-real")
async def analisar_tempo_real(req: TempoRealRequest):
    """
    Análise em tempo real durante a reunião.
    Chamado pela extensão Chrome a cada 60 segundos.
    """
    if not req.transcricao_parcial and not req.historico:
        raise HTTPException(status_code=400, detail="Transcrição vazia — ative as legendas no Meet")

    # Salvar transcrição bruta ANTES do GPT — garante persistência mesmo se GPT falhar
    # Usa transcricao_nova (delta) se disponível para evitar duplicatas no DB.
    _para_salvar = (req.transcricao_nova or "").strip() or (req.transcricao_parcial or "").strip()
    if _para_salvar:
        try:
            from agent.sessao_manager import salvar_transcricao_bruta
            salvar_transcricao_bruta(req.meeting_id or "default", _para_salvar)
        except Exception as _e:
            logger.warning("[Sessões] Não foi possível salvar transcrição bruta: %s", _e)

    from api.processador_tempo_real import processar_fragmento_tempo_real

    try:
        resultado = await processar_fragmento_tempo_real(
            transcricao_parcial=req.transcricao_parcial or "",
            historico=req.historico or "",
            perfil_disc_atual=req.perfil_disc_atual or "",
            mapa_financeiro=req.mapa_financeiro,
            meeting_id=req.meeting_id or "default",
            transcricao_nova=req.transcricao_nova or "",
        )
    except Exception as e:
        logger.error("Erro ao processar fragmento tempo real: %s", e)
        raise HTTPException(status_code=500, detail="Erro ao processar transcricao. Verifique as APIs de IA configuradas.")

    # Persistir última análise para o endpoint /cenario
    try:
        from agent.sessao_manager import salvar_analise
        salvar_analise(req.meeting_id or "default", req.transcricao_parcial or "", resultado)
    except Exception as _e:
        logger.warning("[Cenário] Não foi possível salvar análise: %s", _e)

    return resultado


@app.post("/webhook/tactiq")
def receber_webhook_tactiq(req: TactiqWebhookRequest, background_tasks: BackgroundTasks):
    """
    Recebe transcrição completa do Tactiq ao final da reunião.
    Processa automaticamente e armazena o relatório.
    """
    if not req.transcript:
        raise HTTPException(status_code=400, detail="Transcrição vazia")

    # Processar em background para não bloquear a resposta
    background_tasks.add_task(processar_transcricao_completa, req)

    return {
        "status": "recebido",
        "mensagem": "Transcrição recebida. Processando recapitulação...",
        "reuniao": req.meeting_title,
    }


def processar_transcricao_completa(req: TactiqWebhookRequest):
    """Processa a transcrição completa e armazena o relatório."""
    global ultimo_relatorio
    try:
        # Gerar recapitulação completa
        recapitulacao = chamar_gpt(
            PROMPT_RECAPITULACAO,
            f"REUNIÃO: {req.meeting_title}\nTRANSCRIÇÃO:\n{req.transcript}"
        )

        # Gerar diagnóstico financeiro
        diagnostico = chamar_gpt(
            PROMPT_DIAGNOSTICO_FINANCEIRO,
            req.transcript
        )

        # Gerar perfil DISC completo
        disc = chamar_gpt(
            PROMPT_PERFIL_DISC,
            req.transcript
        )

        ultimo_relatorio = {
            "titulo": req.meeting_title,
            "data": req.date or datetime.now().isoformat(),
            "participantes": req.participants,
            "recapitulacao": recapitulacao,
            "diagnostico_financeiro": diagnostico,
            "perfil_disc": disc,
            "gerado_em": datetime.now().isoformat(),
        }

        # Persistir no banco SQLite
        try:
            db_salvar(
                meeting_id=req.meeting_title or "default",
                nome_reuniao=req.meeting_title or "Reunião de Vendas",
                dados=ultimo_relatorio,
            )
            logger.info("📄 Relatório salvo no banco SQLite.")
        except Exception as e:
            logger.warning("Erro ao salvar no banco: %s — salvando em arquivo.", e)
            import unicodedata, re
            nome_safe = unicodedata.normalize("NFKD", req.meeting_title or "reuniao")
            nome_safe = re.sub(r"[^\w\s-]", "", nome_safe).strip().replace(" ", "_")[:40]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            caminho = PASTA_RELATORIOS / f"{timestamp}_{nome_safe}.json"
            caminho.write_text(json.dumps(ultimo_relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        ultimo_relatorio = {"erro": str(e), "gerado_em": datetime.now().isoformat()}


@app.post("/diagnostico-financeiro")
def diagnostico_financeiro(req: DiagnosticoFinanceiroRequest):
    """
    Extrai informações financeiras do cliente a partir da transcrição.
    """
    if not req.transcricao:
        raise HTTPException(status_code=400, detail="Transcrição vazia")

    resultado = chamar_gpt(PROMPT_DIAGNOSTICO_FINANCEIRO, req.transcricao)
    return resultado


@app.post("/perfil-disc")
def identificar_perfil_disc(req: PerfilDiscRequest):
    """
    Identifica o perfil DISC do cliente e sugere estratégias.
    """
    if not req.transcricao:
        raise HTTPException(status_code=400, detail="Transcrição vazia")

    resultado = chamar_gpt(PROMPT_PERFIL_DISC, req.transcricao)
    return resultado


@app.post("/recapitulacao-completa")
def recapitulacao_completa(req: RecapitulacaoRequest, background_tasks: BackgroundTasks):
    """
    Gera recapitulação emocional e estratégica completa pós-reunião.
    Substitui o processo manual de colar transcrição no Claude.
    Após gerar, dispara extração de memórias comerciais em background.
    """
    if not req.transcricao:
        raise HTTPException(status_code=400, detail="Transcrição vazia")

    conteudo = f"REUNIÃO: {req.titulo_reuniao}\nDATA: {req.data or 'não informada'}\n\nTRANSCRIÇÃO:\n{req.transcricao}"

    recapitulacao = chamar_gpt(PROMPT_RECAPITULACAO, conteudo)
    diagnostico = chamar_gpt(PROMPT_DIAGNOSTICO_FINANCEIRO, req.transcricao)
    disc = chamar_gpt(PROMPT_PERFIL_DISC, req.transcricao)

    resultado = {
        "titulo": req.titulo_reuniao,
        "data": req.data or datetime.now().isoformat(),
        "recapitulacao": recapitulacao,
        "diagnostico_financeiro": diagnostico,
        "perfil_disc": disc,
        "gerado_em": datetime.now().isoformat(),
    }

    global ultimo_relatorio
    ultimo_relatorio = resultado

    try:
        from agent.knowledge_extractor import extrair_e_salvar_memorias
        from agent.playbook_generator import _eh_reuniao_de_sucesso, gerar_e_salvar_playbook
        meeting_id = req.meeting_id or f"completa_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        background_tasks.add_task(extrair_e_salvar_memorias, resultado, req.transcricao, meeting_id)
        if _eh_reuniao_de_sucesso(resultado, meeting_id):
            background_tasks.add_task(gerar_e_salvar_playbook, resultado, req.transcricao, meeting_id)
    except Exception as e:
        logger.warning("Não foi possível agendar pipeline pós-reunião: %s", e)

    return resultado


@app.post("/recapitulacao-viva")
async def recapitulacao_viva(req: RecapitulacaoVivaRequest):
    """
    Gera ou regenera a recapitulação guiada usando a MeetingMemory persistida.
    """
    if not req.meeting_id:
        raise HTTPException(status_code=400, detail="meeting_id é obrigatório")

    memoria = obter_meeting_memory(req.meeting_id)
    if not memoria:
        raise HTTPException(status_code=404, detail="MeetingMemory não encontrada para este meeting_id")

    from agent.recapitulacao import generateLiveRecapMindMap

    current_diagnosis = {}
    if memoria.get("current_diagnosis"):
        try:
            current_diagnosis = json.loads(memoria["current_diagnosis"])
        except Exception:
            current_diagnosis = {}

    trigger = {
        "triggered": True,
        "reason": "manual_regenerate",
        "trigger_phrase": "regenerar manualmente",
        "confidence": "medium",
        "fact_or_inference": "inference",
        "timestamp": datetime.now().isoformat(),
    }

    resultado = await generateLiveRecapMindMap(
        transcricao_recente=memoria.get("transcript_buffer") or memoria.get("transcript_full") or "",
        resumo_vivo=memoria.get("accumulated_summary") or "",
        diagnostico_atual=current_diagnosis,
        score_history=memoria.get("score_history") or [],
        key_moments=memoria.get("key_moments") or [],
        events=memoria.get("events") or [],
        trigger=trigger,
    )

    return {
        "meeting_id": req.meeting_id,
        "recapitulacao_viva": resultado,
        "live_recap": resultado,
    }


@app.get("/relatorio", response_class=HTMLResponse)
def ver_relatorio():
    """
    Exibe o último relatório gerado em formato HTML legível.
    Se não há relatório em memória, carrega o arquivo mais recente.
    """
    global ultimo_relatorio

    if not ultimo_relatorio:
        try:
            ultimo_relatorio = db_ultimo() or {}
        except Exception:
            pass
    if not ultimo_relatorio:
        try:
            arquivos = sorted(PASTA_RELATORIOS.glob("*.json"), reverse=True)
            if arquivos:
                ultimo_relatorio = json.loads(arquivos[0].read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Erro ao carregar relatório do arquivo: %s", e)

    if not ultimo_relatorio:
        return HTMLResponse(content="""
            <html><body style="font-family:Arial;background:#1a1a2e;color:#e0e0e0;padding:40px;text-align:center">
            <h2>🤖 SALEIA</h2>
            <p>Nenhum relatório disponível ainda.</p>
            <p>Complete uma reunião no Google Meet com a extensão ativa.</p>
            </body></html>
        """)

    # Escapar todos os valores dinâmicos para evitar XSS
    relatorio_json_escaped = html_module.escape(
        json.dumps(ultimo_relatorio, ensure_ascii=False, indent=2)
    )
    titulo_escaped = html_module.escape(str(ultimo_relatorio.get('titulo', 'Reunião de Vendas')))
    data_escaped = html_module.escape(str(ultimo_relatorio.get('data', ''))[:10])
    gerado_em_escaped = html_module.escape(str(ultimo_relatorio.get('gerado_em', '')))

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>SALEIA — Relatório de Reunião</title>
  <style>
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #1a1a2e; color: #e0e0e0;
            max-width: 900px; margin: 0 auto; padding: 40px 20px; }}
    h1 {{ color: #90caf9; }}
    h2 {{ color: #81c784; margin-top: 30px; }}
    h3 {{ color: #ffeb3b; }}
    pre {{ background: #16213e; padding: 16px; border-radius: 8px; overflow-x: auto;
           white-space: pre-wrap; font-size: 13px; }}
    .badge {{ background: #0f3460; padding: 4px 10px; border-radius: 12px; margin-right: 8px; }}
    .header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 30px; }}
  </style>
</head>
<body>
  <div class="header">
    <span style="font-size:48px">🤖</span>
    <div>
      <h1>SALEIA — Relatório de Reunião</h1>
      <p>{titulo_escaped} · {data_escaped}</p>
    </div>
  </div>

  <h2>📋 Dados Completos</h2>
  <pre>{relatorio_json_escaped}</pre>

  <p style="color:#555577;margin-top:30px;text-align:center">
    Gerado em: {gerado_em_escaped}
  </p>
</body>
</html>"""

    return HTMLResponse(content=html)


@app.patch("/relatorios/{meeting_id}/status")
def atualizar_status_relatorio(
    meeting_id: str,
    body: dict,
    authorization: str | None = Header(default=None),
):
    """Define o status de uma reunião: open | won | lost. Marcar como 'won' dispara geração de playbook."""
    _req_auth(authorization)
    status = (body.get("status") or "").strip().lower()
    if status not in ("open", "won", "lost"):
        raise HTTPException(status_code=400, detail="Status inválido. Use: open, won ou lost.")
    try:
        from agent.playbook_generator import atualizar_status_reuniao
        atualizar_status_reuniao(meeting_id, status)
        return {"meeting_id": meeting_id, "status": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/relatorios/{meeting_id}/status")
def obter_status_relatorio(
    meeting_id: str,
    authorization: str | None = Header(default=None),
):
    """Retorna o status atual de uma reunião."""
    _req_auth(authorization)
    try:
        from agent.playbook_generator import obter_status_reuniao
        return {"meeting_id": meeting_id, "status": obter_status_reuniao(meeting_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/playbooks")
def listar_playbooks_endpoint(
    apenas_ativos: bool = False,
    limit: int = 50,
    offset: int = 0,
    authorization: str | None = Header(default=None),
):
    """Lista todos os playbooks (ou apenas os ativos)."""
    _req_auth(authorization)
    try:
        from agent.playbook_generator import listar_playbooks
        items = listar_playbooks(apenas_ativos=apenas_ativos, limit=limit, offset=offset)
        return {"total": len(items), "playbooks": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/playbooks/{playbook_id}")
def obter_playbook_endpoint(
    playbook_id: str,
    authorization: str | None = Header(default=None),
):
    """Retorna um playbook por ID."""
    _req_auth(authorization)
    try:
        from agent.playbook_generator import obter_playbook
        item = obter_playbook(playbook_id)
        if not item:
            raise HTTPException(status_code=404, detail="Playbook não encontrado.")
        return item
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/playbooks/{playbook_id}")
def atualizar_playbook_endpoint(
    playbook_id: str,
    body: dict,
    authorization: str | None = Header(default=None),
):
    """Edita campos de um playbook ou ativa/desativa (is_active: 0|1)."""
    _req_auth(authorization)
    try:
        from agent.playbook_generator import atualizar_playbook
        ok = atualizar_playbook(playbook_id, body)
        if not ok:
            raise HTTPException(status_code=404, detail="Playbook não encontrado ou sem campos válidos.")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/playbooks/{playbook_id}")
def deletar_playbook_endpoint(
    playbook_id: str,
    authorization: str | None = Header(default=None),
):
    """Remove permanentemente um playbook."""
    _req_admin(authorization)
    try:
        from agent.playbook_generator import deletar_playbook
        ok = deletar_playbook(playbook_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Playbook não encontrado.")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/playbooks/gerar/{meeting_id}")
def gerar_playbook_manual_endpoint(
    meeting_id: str,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
):
    """Força geração de playbook para uma reunião específica (admin)."""
    _req_admin(authorization)
    try:
        from agent.sessao_manager import buscar_relatorio_por_meeting
        relatorio = buscar_relatorio_por_meeting(meeting_id) or {}
    except Exception:
        relatorio = {}
    try:
        from agent.playbook_generator import gerar_e_salvar_playbook
        background_tasks.add_task(gerar_e_salvar_playbook, relatorio, "", meeting_id)
        return {"status": "gerando", "meeting_id": meeting_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/clientes")
def listar_clientes_endpoint(
    busca: str = "",
    status: str = "",
    limit: int = 50,
    offset: int = 0,
    authorization: str | None = Header(default=None),
):
    """Lista perfis de clientes com filtro por nome/empresa/email e status."""
    _req_auth(authorization)
    try:
        from agent.client_intelligence import listar_clientes
        items = listar_clientes(busca=busca, status=status, limit=limit, offset=offset)
        return {"total": len(items), "clientes": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/clientes")
def criar_cliente_endpoint(body: dict, authorization: str | None = Header(default=None)):
    """Cria um perfil de cliente."""
    _req_auth(authorization)
    nome = (body.get("nome") or "").strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Campo 'nome' é obrigatório.")
    try:
        from agent.client_intelligence import criar_cliente
        cid = criar_cliente(
            nome=nome,
            empresa=body.get("empresa") or "",
            email=body.get("email") or "",
            telefone=body.get("telefone") or "",
            disc_profile=body.get("disc_profile") or "",
            notas=body.get("notas") or "",
        )
        return {"id": cid, "nome": nome}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/clientes/{client_id}")
def obter_cliente_endpoint(client_id: str, authorization: str | None = Header(default=None)):
    """Retorna perfil completo do cliente com timeline."""
    _req_auth(authorization)
    try:
        from agent.client_intelligence import obter_cliente
        item = obter_cliente(client_id)
        if not item:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        return item
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/clientes/{client_id}")
def atualizar_cliente_endpoint(
    client_id: str,
    body: dict,
    authorization: str | None = Header(default=None),
):
    """Atualiza campos do perfil do cliente."""
    _req_auth(authorization)
    try:
        from agent.client_intelligence import atualizar_cliente
        ok = atualizar_cliente(client_id, body)
        if not ok:
            raise HTTPException(status_code=404, detail="Cliente não encontrado ou sem campos válidos.")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/clientes/{client_id}")
def deletar_cliente_endpoint(client_id: str, authorization: str | None = Header(default=None)):
    """Remove um cliente e todos os vínculos de reuniões."""
    _req_admin(authorization)
    try:
        from agent.client_intelligence import deletar_cliente
        ok = deletar_cliente(client_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/clientes/{client_id}/reunioes")
def vincular_reuniao_endpoint(
    client_id: str,
    body: dict,
    authorization: str | None = Header(default=None),
):
    """Vincula uma reunião ao cliente e atualiza as estatísticas."""
    _req_auth(authorization)
    meeting_id = (body.get("meeting_id") or "").strip()
    if not meeting_id:
        raise HTTPException(status_code=400, detail="Campo 'meeting_id' é obrigatório.")
    try:
        from agent.client_intelligence import vincular_reuniao
        from datetime import datetime as _dt
        data_str = body.get("data")
        data = _dt.fromisoformat(data_str) if data_str else _dt.now()
        ok = vincular_reuniao(
            client_id=client_id,
            meeting_id=meeting_id,
            titulo=body.get("titulo") or "",
            score=int(body.get("score") or 0),
            data=data,
        )
        return {"ok": ok}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/clientes/{client_id}/reunioes/{meeting_id}")
def desvincular_reuniao_endpoint(
    client_id: str,
    meeting_id: str,
    authorization: str | None = Header(default=None),
):
    """Remove o vínculo de uma reunião com o cliente."""
    _req_auth(authorization)
    try:
        from agent.client_intelligence import desvincular_reuniao
        ok = desvincular_reuniao(client_id, meeting_id)
        return {"ok": ok}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/clientes/por-reuniao/{meeting_id}")
def cliente_por_reuniao_endpoint(
    meeting_id: str,
    authorization: str | None = Header(default=None),
):
    """Retorna o cliente vinculado a uma reunião, ou null."""
    _req_auth(authorization)
    try:
        from agent.client_intelligence import buscar_cliente_por_reuniao, obter_cliente
        cid = buscar_cliente_por_reuniao(meeting_id)
        if not cid:
            return {"cliente": None}
        return {"cliente": obter_cliente(cid)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/skills")
def listar_skills_endpoint(
    apenas_ativas: bool = False,
    authorization: str | None = Header(default=None),
):
    """Lista todas as skills (builtins + customizadas)."""
    _req_auth(authorization)
    try:
        from agent.skill_resolver import listar_skills
        return {"skills": listar_skills(apenas_ativas=apenas_ativas)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/skills/gerar")
def gerar_skill_endpoint(
    body: dict,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
):
    """Gera uma skill via IA a partir de um contexto (playbook, reunião ou texto livre)."""
    _req_auth(authorization)
    contexto = (body.get("contexto") or "").strip()
    if not contexto or len(contexto) < 20:
        raise HTTPException(status_code=400, detail="Campo 'contexto' deve ter pelo menos 20 caracteres.")
    playbook_id = body.get("source_playbook_id")
    try:
        from agent.skill_resolver import gerar_e_salvar_skill
        background_tasks.add_task(gerar_e_salvar_skill, contexto, playbook_id)
        return {"status": "gerando", "source_playbook_id": playbook_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/skills/{skill_id}")
def atualizar_skill_endpoint(
    skill_id: str,
    body: dict,
    authorization: str | None = Header(default=None),
):
    """Edita campos de uma skill customizada (name, system_injection, priority, is_active, etc.)."""
    _req_auth(authorization)
    try:
        from agent.skill_resolver import atualizar_skill
        ok = atualizar_skill(skill_id, body)
        if not ok:
            raise HTTPException(status_code=404, detail="Skill não encontrada ou sem campos válidos.")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/skills/{skill_id}")
def deletar_skill_endpoint(
    skill_id: str,
    authorization: str | None = Header(default=None),
):
    """Remove uma skill customizada (admin). Skills builtin não podem ser removidas via API."""
    _req_admin(authorization)
    try:
        from agent.skill_resolver import deletar_skill
        ok = deletar_skill(skill_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Skill não encontrada.")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sales-memories")
def listar_sales_memories(
    memory_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    authorization: str | None = Header(default=None),
):
    """Lista memórias comerciais com filtro opcional por tipo."""
    _req_auth(authorization)
    try:
        from agent.sales_memory import listar_memorias
        return {"memorias": listar_memorias(memory_type=memory_type, limit=limit, offset=offset)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sales-memories/buscar")
def buscar_sales_memories(
    q: str,
    top_k: int = 5,
    memory_type: Optional[str] = None,
    authorization: str | None = Header(default=None),
):
    """Busca semântica em memórias comerciais por similaridade de cosseno."""
    _req_auth(authorization)
    if not q or len(q.strip()) < 3:
        raise HTTPException(status_code=400, detail="Parâmetro 'q' deve ter pelo menos 3 caracteres")
    try:
        from agent.sales_memory import buscar_memorias_semantico
        resultados = buscar_memorias_semantico(q.strip(), top_k=top_k, memory_type=memory_type)
        return {"query": q, "total": len(resultados), "resultados": resultados}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sales-memories/stats")
def stats_sales_memories(authorization: str | None = Header(default=None)):
    """Estatísticas de memórias por tipo."""
    _req_auth(authorization)
    try:
        from agent.sales_memory import contar_por_tipo
        return {"por_tipo": contar_por_tipo()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/relatorios")
def listar_relatorios_endpoint():
    """Lista todos os relatórios salvos (banco SQLite + fallback arquivos JSON)."""
    try:
        # Tentar banco primeiro
        try:
            rows = db_listar(limite=20)
            if rows:
                try:
                    from agent.playbook_generator import listar_status_reunioes
                    mids = [r["meeting_id"] for r in rows]
                    status_map = listar_status_reunioes(mids)
                except Exception:
                    status_map = {}
                return {"total": len(rows), "fonte": "sqlite", "relatorios": [
                    {
                        "id": r["id"],
                        "meeting_id": r["meeting_id"],
                        "titulo": r["nome_reuniao"],
                        "data": r["criado_em"],
                        "probabilidade_fechamento": r["dados"].get("recapitulacao", {}).get("probabilidade_fechamento", ""),
                        "provedor": (
                            r["dados"].get("recapitulacao", {}).get("_provedor_ia")
                            or r["dados"].get("perfil_disc", {}).get("_provedor_ia")
                            or r["dados"].get("diagnostico_financeiro", {}).get("_provedor_ia")
                            or ""
                        ),
                        "status": status_map.get(r["meeting_id"], "open"),
                    }
                    for r in rows
                ]}
        except Exception:
            pass

        # Fallback: arquivos JSON
        arquivos = sorted(PASTA_RELATORIOS.glob("*.json"), reverse=True)
        relatorios = []
        for arq in arquivos[:20]:
            try:
                dados = json.loads(arq.read_text(encoding="utf-8"))
                relatorios.append({
                    "arquivo": arq.name,
                    "titulo": dados.get("titulo", ""),
                    "data": dados.get("data", ""),
                    "gerado_em": dados.get("gerado_em", ""),
                    "probabilidade_fechamento": (
                        dados.get("recapitulacao", {}).get("probabilidade_fechamento", "")
                    ),
                    "provedor": (
                        dados.get("recapitulacao", {}).get("_provedor_ia")
                        or dados.get("perfil_disc", {}).get("_provedor_ia")
                        or dados.get("diagnostico_financeiro", {}).get("_provedor_ia")
                        or ""
                    ),
                })
            except Exception:
                continue
        return {"total": len(relatorios), "fonte": "arquivos", "relatorios": relatorios}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
# FOLLOW-UPS (Fase 6)
# ─────────────────────────────────────────────

@app.post("/relatorios/{meeting_id}/followups/gerar")
def gerar_followups_reuniao(
    meeting_id: str,
    authorization: str | None = Header(default=None),
):
    """Gera follow-ups para os 3 canais (WhatsApp, Email, LinkedIn) com agenda inteligente."""
    _req_auth(authorization)
    try:
        from agent.followup_generator import gerar_e_salvar_followups
        from api.database import obter_meeting_memory

        mem = obter_meeting_memory(meeting_id) or {}

        # Extrai score
        score = 0
        try:
            hist = json.loads(mem.get("score_history_json") or "[]")
            if hist:
                last = hist[-1]
                score = int(last.get("valor") or last.get("score") or 0)
        except Exception:
            pass

        # Extrai DISC e dores do current_diagnosis
        disc_profile = ""
        dores: list = []
        proximos_passos: list = []
        try:
            diag = mem.get("current_diagnosis") or "{}"
            if isinstance(diag, str):
                diag = json.loads(diag)
            if isinstance(diag, dict):
                disc_profile = (
                    diag.get("perfil_disc", {}) or {}
                ).get("tipo", "") or ""
                fc = diag.get("filtro_cliente") or {}
                dores = fc.get("dores_e_travas") or []
                ps = diag.get("proxima_acao") or ""
                if ps:
                    proximos_passos = [ps]
        except Exception:
            pass

        resumo = mem.get("accumulated_summary") or ""

        # Tenta buscar nome do cliente vinculado
        nome_cliente = ""
        client_id = None
        try:
            from agent.client_intelligence import buscar_cliente_por_reuniao, obter_cliente
            client_id = buscar_cliente_por_reuniao(meeting_id)
            if client_id:
                cli = obter_cliente(client_id)
                if cli:
                    nome_cliente = cli.get("empresa") or cli.get("nome") or ""
        except Exception:
            pass

        followups = gerar_e_salvar_followups(
            meeting_id=meeting_id,
            disc_profile=disc_profile,
            score=score,
            resumo=resumo,
            dores=dores if isinstance(dores, list) else [],
            proximos_passos=proximos_passos,
            nome_cliente=nome_cliente,
            client_id=client_id,
        )
        return {"meeting_id": meeting_id, "total": len(followups), "followups": followups}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/relatorios/{meeting_id}/followups")
def listar_followups_reuniao(
    meeting_id: str,
    authorization: str | None = Header(default=None),
):
    """Lista todos os follow-ups de uma reunião."""
    _req_auth(authorization)
    try:
        from agent.followup_generator import listar_followups
        items = listar_followups(meeting_id)
        return {"meeting_id": meeting_id, "total": len(items), "followups": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/followups/{fid}")
def atualizar_followup_endpoint(
    fid: str,
    body: dict,
    authorization: str | None = Header(default=None),
):
    """Atualiza mensagem ou status de um follow-up."""
    _req_auth(authorization)
    try:
        from agent.followup_generator import atualizar_followup
        updated = atualizar_followup(fid, **body)
        if not updated:
            raise HTTPException(status_code=404, detail="Follow-up não encontrado")
        return updated
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/followups/{fid}")
def deletar_followup_endpoint(
    fid: str,
    authorization: str | None = Header(default=None),
):
    """Remove um follow-up."""
    _req_auth(authorization)
    try:
        from agent.followup_generator import deletar_followup
        ok = deletar_followup(fid)
        if not ok:
            raise HTTPException(status_code=404, detail="Follow-up não encontrado")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
# HISTÓRICO DE USO / CUSTO
# ─────────────────────────────────────────────

@app.get("/historico/uso")
def historico_uso(authorization: str | None = Header(default=None)):
    """Lista o histórico de uso e custo estimado por reunião (últimas 100)."""
    _req_auth(authorization)

    from sqlmodel import Session as _Session, select as _select
    from api.database import engine as _engine, MeetingMemory as _MM
    import json as _j

    with _Session(_engine) as session:
        rows = session.exec(
            _select(_MM).order_by(_MM.updated_at.desc()).limit(100)
        ).all()

    sessoes_map: dict = {}
    try:
        from agent.sessao_manager import _get_conn
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT meeting_id, num_analises, disc_identificado "
                "FROM sessoes ORDER BY updated_at DESC"
            )
            for mid, num, disc in cur.fetchall():
                if mid not in sessoes_map:
                    sessoes_map[mid] = {"num_analises": num or 0, "disc": disc}
        conn.close()
    except Exception:
        pass

    reunioes = []
    custo_total = 0.0
    for row in rows:
        score_history = _j.loads(row.score_history_json or "[]")
        score_final = score_history[-1]["valor"] if score_history else None
        sessao = sessoes_map.get(row.meeting_id, {})
        custo = float(row.provider_cost_estimate or 0.0)
        custo_total += custo
        reunioes.append({
            "meeting_id": row.meeting_id,
            "data": row.updated_at.isoformat() if row.updated_at else None,
            "custo_estimado_usd": round(custo, 6),
            "score_final": score_final,
            "disc_identificado": sessao.get("disc") or None,
            "num_analises": sessao.get("num_analises", 0),
            "num_key_moments": len(_j.loads(row.key_moments_json or "[]")),
            "num_eventos": len(_j.loads(row.events_json or "[]")),
        })

    return {
        "reunioes": reunioes,
        "total": len(reunioes),
        "custo_total_usd": round(custo_total, 6),
    }


@app.get("/historico/uso/{meeting_id}")
def historico_uso_reuniao(meeting_id: str, authorization: str | None = Header(default=None)):
    """Retorna o detalhamento de uso e custo de uma reunião específica."""
    _req_auth(authorization)
    import re as _re3
    if not _re3.match(r'^[a-z]{3}-[a-z]{4}-[a-z]{3}$', meeting_id, _re3.IGNORECASE):
        raise HTTPException(status_code=400, detail="meeting_id inválido")

    memoria = obter_meeting_memory(meeting_id)
    if not memoria:
        raise HTTPException(status_code=404, detail="Reunião não encontrada.")

    sessao_info: dict = {}
    try:
        from agent.sessao_manager import _get_conn
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT num_analises, disc_identificado, created_at "
                "FROM sessoes WHERE meeting_id=%s ORDER BY created_at DESC LIMIT 1",
                (meeting_id,),
            )
            row = cur.fetchone()
            if row:
                sessao_info = {
                    "num_analises": row[0] or 0,
                    "disc_identificado": row[1],
                    "iniciada_em": row[2].isoformat() if row[2] else None,
                }
        conn.close()
    except Exception:
        pass

    score_history = memoria.get("score_history") or []
    score_final = score_history[-1]["valor"] if score_history else None

    return {
        "meeting_id": meeting_id,
        "data": memoria.get("updated_at"),
        "custo_estimado_usd": round(float(memoria.get("provider_cost_estimate") or 0.0), 6),
        "score_final": score_final,
        "score_history": score_history,
        "key_moments": memoria.get("key_moments") or [],
        "eventos": memoria.get("events") or [],
        **sessao_info,
    }


@app.post("/recapitulacao-manual")
def recapitulacao_manual(req: RecapitulacaoRequest, background_tasks: BackgroundTasks):
    """
    Endpoint simplificado: cola a transcrição e gera recapitulação + DISC + diagnóstico financeiro.
    Ideal para uso no painel HTML sem a extensão Chrome.
    Após salvar o relatório, dispara extração de memórias comerciais em background.
    """
    if not req.transcricao:
        raise HTTPException(status_code=400, detail="Transcrição vazia")

    conteudo = f"REUNIÃO: {req.titulo_reuniao}\nDATA: {req.data or 'não informada'}\n\nTRANSCRIÇÃO:\n{req.transcricao}"

    recapitulacao = chamar_gpt(PROMPT_RECAPITULACAO, conteudo)
    diagnostico = chamar_gpt(PROMPT_DIAGNOSTICO_FINANCEIRO, req.transcricao)
    disc = chamar_gpt(PROMPT_PERFIL_DISC, req.transcricao)

    resultado = {
        "titulo": req.titulo_reuniao,
        "data": req.data or datetime.now().isoformat(),
        "recapitulacao": recapitulacao,
        "diagnostico_financeiro": diagnostico,
        "perfil_disc": disc,
        "gerado_em": datetime.now().isoformat(),
    }

    global ultimo_relatorio
    ultimo_relatorio = resultado

    # Salvar em arquivo
    try:
        import unicodedata, re
        nome_safe = unicodedata.normalize("NFKD", req.titulo_reuniao or "manual")
        nome_safe = re.sub(r"[^\w\s-]", "", nome_safe).strip().replace(" ", "_")[:40]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho = PASTA_RELATORIOS / f"{timestamp}_{nome_safe}.json"
        caminho.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("Não foi possível salvar relatório manual: %s", e)

    # Pipeline pós-reunião em background (não bloqueia a resposta)
    try:
        from agent.knowledge_extractor import extrair_e_salvar_memorias
        from agent.playbook_generator import _eh_reuniao_de_sucesso, gerar_e_salvar_playbook
        meeting_id = req.meeting_id or f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        background_tasks.add_task(extrair_e_salvar_memorias, resultado, req.transcricao, meeting_id)
        if _eh_reuniao_de_sucesso(resultado, meeting_id):
            background_tasks.add_task(gerar_e_salvar_playbook, resultado, req.transcricao, meeting_id)
    except Exception as e:
        logger.warning("Não foi possível agendar pipeline pós-reunião: %s", e)

    return resultado


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def login_page():
    """Página de login."""
    caminho = Path(__file__).parent.parent / "frontend" / "login.html"
    try:
        return HTMLResponse(content=caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="login.html não encontrado")


@app.get("/dashboard.", response_class=HTMLResponse, include_in_schema=False)
@app.get("/dashboard/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """Dashboard web para visualizar reuniões e analisar transcrições."""
    caminho = Path(__file__).parent.parent / "frontend" / "dashboard.html"
    try:
        return HTMLResponse(content=caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="dashboard.html não encontrado")


@app.get("/manual", response_class=HTMLResponse)
def manual():
    """Manual do usuário em HTML."""
    caminho = Path(__file__).parent.parent / "frontend" / "manual.html"
    try:
        return HTMLResponse(content=caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="manual.html não encontrado")


@app.get("/manual-tecnico", response_class=HTMLResponse)
def manual_tecnico():
    """Manual técnico para apresentação a compradores."""
    caminho = Path(__file__).parent.parent / "frontend" / "manual_tecnico.html"
    try:
        return HTMLResponse(content=caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="manual_tecnico.html não encontrado")


# ─────────────────────────────────────────────
# SESSÕES EM TEMPO REAL
# ─────────────────────────────────────────────

@app.get("/sessoes")
def listar_sessoes_endpoint():
    """
    Lista todas as sessões gravadas durante reuniões ao vivo.
    Cada sessão contém a transcrição acumulada e a última análise da IA.
    """
    try:
        from agent.sessao_manager import listar_sessoes
        sessoes = listar_sessoes(limite=200)
        return {"total": len(sessoes), "sessoes": sessoes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessoes/{sessao_id}")
def buscar_sessao_endpoint(sessao_id: int):
    """
    Retorna a sessão completa com transcrição e última análise da IA.
    """
    try:
        from agent.sessao_manager import buscar_sessao
        s = buscar_sessao(sessao_id)
        if not s:
            raise HTTPException(status_code=404, detail="Sessão não encontrada")
        return s
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/sessoes/{sessao_id}")
def deletar_sessao_endpoint(sessao_id: int):
    """
    Remove uma sessão pelo ID.
    """
    try:
        from agent.sessao_manager import deletar_sessao
        ok = deletar_sessao(sessao_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Sessão não encontrada")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/iniciar-sessao")
def iniciar_sessao_endpoint(req: IniciarSessaoRequest):
    """
    Registra uma sessão imediatamente ao carregar a extensão no Meet,
    mesmo antes de qualquer transcrição ser capturada.
    """
    try:
        from agent.sessao_manager import registrar_sessao
        sessao_id = registrar_sessao(req.meeting_id)
        return {"ok": True, "sessao_id": sessao_id}
    except Exception as e:
        logger.error("Erro ao iniciar sessão: %s", e)
        return {"ok": False, "sessao_id": 0}


@app.post("/sessoes/{sessao_id}/exportar-base")
def exportar_base_endpoint(sessao_id: int, req: ExportarBaseRequest):
    """
    Exporta a transcrição de uma sessão para a base de conhecimento da IA.
    Gera embedding e insere na tabela base_conhecimento.
    """
    try:
        from agent.sessao_manager import exportar_para_base_conhecimento
        resultado = exportar_para_base_conhecimento(sessao_id, req.titulo or "", req.tipo or "reuniao")
        if not resultado.get("ok"):
            raise HTTPException(status_code=400, detail=resultado.get("erro", "Erro ao exportar"))
        return resultado
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/base")
def listar_base():
    """Lista todos os documentos da base de conhecimento (sem embeddings)."""
    from agent.sessao_manager import _get_conn, migrar_colunas_embedding_metadata_base_conhecimento
    migrar_colunas_embedding_metadata_base_conhecimento()
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, titulo, tipo, CHAR_LENGTH(texto) AS chars, created_at, "
                "arquivo_nome_original, arquivo_tamanho "
                "FROM base_conhecimento ORDER BY created_at DESC"
            )
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    docs = [
        {
            "id": r[0], "titulo": r[1], "tipo": r[2], "chars": r[3],
            "created_at": r[4].isoformat() if r[4] else None,
            "arquivo_nome": r[5], "arquivo_tamanho": r[6],
        }
        for r in rows
    ]
    return {"docs": docs, "total": len(docs)}


@app.post("/base")
async def adicionar_base(
    titulo: str = Form(...),
    tipo: str = Form("instrucao"),
    texto: str = Form(...),
    arquivo: Optional[UploadFile] = File(None),
):
    """Adiciona um documento à base de conhecimento, gerando embedding via
    o EmbeddingProvider configurado (Ollama por padrão, OpenAI opcional).

    O texto continua sendo o já extraído/colado pelo usuário (mesmo fluxo de
    sempre, incl. via OCR) — `arquivo`, quando enviado, é preservado à parte
    em disco só para permitir o download do documento original depois.
    """
    if not titulo or not titulo.strip():
        raise HTTPException(status_code=400, detail="Título obrigatório")
    if not texto or len(texto.strip()) < 10:
        raise HTTPException(status_code=400, detail="Texto muito curto (mínimo 10 caracteres)")

    import json as _json
    from services.embeddings import EmbeddingProviderError, get_embedding_provider

    embedding_json = None
    aviso = None
    embedding_provider = embedding_model = embedding_dim = None
    provider_name_configurado = os.environ.get("EMBEDDING_PROVIDER", "ollama").strip().lower()
    try:
        provider = get_embedding_provider()
        resultado = await provider.embed_async(texto[:8000])
        if resultado is None:
            raise RuntimeError("provedor de embedding não retornou vetor")
        embedding_json = _json.dumps(resultado.vector)
        embedding_provider = resultado.provider
        embedding_model = resultado.model
        embedding_dim = resultado.dimension
    except EmbeddingProviderError as e:
        aviso = f"Documento salvo sem embedding: configuração de embedding inválida ({e})."
        logger.error("[base] configuração de embedding inválida: %s", e)
    except Exception as e:
        aviso = (
            f"Documento salvo sem embedding (provedor '{provider_name_configurado}' indisponível). "
            "Verifique Configurações."
        )
        logger.warning("[base] embedding falhou, salvando sem: %s", e)

    arquivo_nome_original = arquivo_path = arquivo_mime = None
    arquivo_tamanho = None
    if arquivo is not None and arquivo.filename:
        conteudo = await arquivo.read()
        if len(conteudo) > 20 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Arquivo muito grande (máx 20 MB).")
        nome_seguro = re.sub(r"[^A-Za-z0-9._-]+", "_", arquivo.filename)[:150]
        arquivo_path = str(PASTA_BASE_ARQUIVOS / f"{uuid.uuid4().hex}_{nome_seguro}")
        with open(arquivo_path, "wb") as f:
            f.write(conteudo)
        arquivo_nome_original = arquivo.filename
        arquivo_mime = arquivo.content_type
        arquivo_tamanho = len(conteudo)

    from agent.sessao_manager import _get_conn, migrar_colunas_embedding_metadata_base_conhecimento
    migrar_colunas_embedding_metadata_base_conhecimento()
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO base_conhecimento "
                "(titulo, tipo, texto, embedding, embedding_provider, embedding_model, embedding_dim, "
                "arquivo_nome_original, arquivo_path, arquivo_mime, arquivo_tamanho) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (titulo.strip(), tipo or "instrucao", texto, embedding_json,
                 embedding_provider, embedding_model, embedding_dim,
                 arquivo_nome_original, arquivo_path, arquivo_mime, arquivo_tamanho),
            )
            novo_id = cur.lastrowid
        conn.commit()
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    from agent.base_conhecimento import invalidar_cache
    invalidar_cache()
    return {"ok": True, "id": novo_id, "chars": len(texto), "aviso": aviso}


@app.get("/base/{doc_id}/download")
def baixar_documento_base(doc_id: int, authorization: str | None = Header(default=None)):
    """Baixa o arquivo original de um documento da Base. Exige usuário
    autenticado (JWT) — a base é global/compartilhada, sem conceito de
    tenant hoje, então a permissão é simplesmente "estar logado"."""
    _req_auth(authorization)
    from agent.sessao_manager import _get_conn
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT arquivo_path, arquivo_nome_original, arquivo_mime "
                "FROM base_conhecimento WHERE id = %s",
                (doc_id,),
            )
            row = cur.fetchone()
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="Este documento não possui arquivo original para download.")
    arquivo_path, nome_original, mime = row
    if not os.path.isfile(arquivo_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no servidor.")
    return FileResponse(arquivo_path, filename=nome_original or "documento", media_type=mime or "application/octet-stream")


@app.delete("/base/{doc_id}")
def remover_base(doc_id: int):
    """Remove um documento da base de conhecimento (e o arquivo original, se houver)."""
    from agent.sessao_manager import _get_conn
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT arquivo_path FROM base_conhecimento WHERE id = %s", (doc_id,))
            row = cur.fetchone()
            cur.execute("DELETE FROM base_conhecimento WHERE id = %s", (doc_id,))
            affected = cur.rowcount
        conn.commit()
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if affected == 0:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    if row and row[0]:
        try:
            os.remove(row[0])
        except OSError:
            pass
    from agent.base_conhecimento import invalidar_cache
    invalidar_cache()
    return {"ok": True}


@app.get("/cenario/{meeting_id}", response_class=HTMLResponse)
def cenario_cliente_page(meeting_id: str):
    """
    Página de apresentação visual do cenário do cliente (slides para compartilhar na tela).
    """
    import re
    if not re.match(r'^[a-z]{3}-[a-z]{4}-[a-z]{3}$', meeting_id, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="meeting_id inválido")
    caminho = Path(__file__).parent.parent / "frontend" / "cenario.html"
    try:
        return HTMLResponse(content=caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="cenario.html não encontrado")


@app.get("/api/cenario/{meeting_id}")
def api_cenario_dados(meeting_id: str):
    """
    JSON com a última análise da IA para o meeting_id.
    Consumido pela página cenario.html via polling a cada 30s.
    """
    import re
    if not re.match(r'^[a-z]{3}-[a-z]{4}-[a-z]{3}$', meeting_id, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="meeting_id inválido")
    from agent.sessao_manager import obter_ultima_analise
    return obter_ultima_analise(meeting_id)


# ─────────────────────────────────────────────
# CONDUÇÃO — scripts de venda ao vivo
# ─────────────────────────────────────────────
_CONDUCAO_TEMPLATES = {
    "recapitulacao":       "conducao_recapitulacao.txt",
    "programa-aceleracao": "conducao_programa_aceleracao.txt",
    "performance":         "conducao_performance.txt",
    "fechamento":          "conducao_fechamento.txt",
}
# Mapa: tipo de condução → tipo de documento na base_conhecimento
_CONDUCAO_TIPO_BASE = {
    "programa-aceleracao": "programa_aceleracao",
    "performance":         "performance",
}
_CONDUCAO_PROMPT_DIR = Path(__file__).parent.parent / "agent" / "prompt_templates"


def _buscar_conteudo_programa(tipo_base: str) -> str:
    """Busca documentos da base_conhecimento pelo tipo e retorna texto concatenado."""
    try:
        from agent.sessao_manager import _get_conn
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT titulo, texto FROM base_conhecimento WHERE tipo = %s ORDER BY created_at ASC",
                (tipo_base,),
            )
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        logger.warning("[conducao] Erro ao buscar docs da base: %s", e)
        return "(Nenhum documento de programa cadastrado na Base de IA)"

    if not rows:
        return "(Nenhum documento cadastrado para este programa na Base de IA)"

    partes = []
    for titulo, texto in rows:
        partes.append(f"### {titulo}\n{(texto or '').strip()}")
    return "\n\n".join(partes)


@app.post("/cenario/{meeting_id}/conducao")
async def cenario_conducao(meeting_id: str, req: ConducaoRequest, authorization: str | None = Header(default=None)):
    """
    Gera script de condução ao vivo (recapitulação / apresentação / fechamento)
    usando o prompt template correspondente ao tipo solicitado.
    Para Apresentação, injeta os documentos da Base de IA do programa correspondente.
    """
    _req_auth(authorization)
    import re as _re2
    if not _re2.match(r'^[a-z]{3}-[a-z]{4}-[a-z]{3}$', meeting_id, _re2.IGNORECASE):
        raise HTTPException(status_code=400, detail="meeting_id inválido")
    template_file = _CONDUCAO_TEMPLATES.get(req.tipo)
    if not template_file:
        raise HTTPException(status_code=400, detail=f"Tipo de condução desconhecido: {req.tipo}")

    template_path = _CONDUCAO_PROMPT_DIR / template_file
    try:
        template = template_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail=f"Template não encontrado: {template_file}")

    # Extrai variáveis do objeto dados enviado pelo cenario.html
    d = req.dados or {}
    disc = d.get("perfil_disc") or {}
    mapa = d.get("mapa_financeiro") or {}
    score_obj = d.get("score_compra") or {}
    temp_obj = d.get("temperatura") or {}
    produto = mapa.get("produto_indicado") or {}

    disc_tipo = disc.get("tipo") or "não identificado"
    disc_desc = disc.get("descricao") or disc.get("evidencia") or "perfil não detalhado"
    faturamento = mapa.get("faturamento_mensal") or mapa.get("renda_clt") or "não informado"
    capacidade = mapa.get("capacidade_investimento") or "não informado"
    produto_nome = produto.get("nome") or "produto recomendado"
    produto_just = produto.get("justificativa") or "alinhado ao perfil e capacidade financeira"
    score_val = str(score_obj.get("valor") or "—")
    temperatura = temp_obj.get("nivel") or temp_obj.get("valor") or "não informada"

    # Busca documentos do programa na Base de IA (apenas para Apresentação)
    tipo_base = _CONDUCAO_TIPO_BASE.get(req.tipo)
    conteudo_programa = _buscar_conteudo_programa(tipo_base) if tipo_base else ""

    prompt = (
        template
        .replace("{perfil_disc_tipo}", disc_tipo)
        .replace("{perfil_disc_descricao}", disc_desc)
        .replace("{faturamento}", faturamento)
        .replace("{capacidade_investimento}", capacidade)
        .replace("{produto_nome}", produto_nome)
        .replace("{produto_justificativa}", produto_just)
        .replace("{score}", score_val)
        .replace("{temperatura}", str(temperatura))
        .replace("{conteudo_programa}", conteudo_programa)
    )

    # chamar_ia_async espera JSON — instruímos o modelo a retornar {"conteudo": "..."}
    system_prompt = (
        'Você é um assistente de vendas. '
        'Responda APENAS com um JSON válido sem markdown, no formato: '
        '{"conteudo": "script do vendedor aqui"}'
    )
    from api.ai_router import chamar_ia_async
    try:
        resultado = await chamar_ia_async(system_prompt, prompt)
        conteudo = (
            resultado.get("conteudo")
            or resultado.get("texto")
            or resultado.get("resposta")
            or resultado.get("resultado")
            or next((v for v in resultado.values() if isinstance(v, str) and len(v) > 10), "")
        )
        if not isinstance(conteudo, str):
            import json as _json2
            conteudo = _json2.dumps(conteudo, ensure_ascii=False)
    except Exception as e:
        logger.error("[conducao] Erro ao chamar IA: %s", e)
        raise HTTPException(status_code=503, detail="Serviço de IA indisponível. Tente novamente.")

    return {"conteudo": conteudo}


# ─────────────────────────────────────────────
# WHISPER — transcrição de áudio em tempo real
# ─────────────────────────────────────────────
@app.post("/audio-transcricao")
async def audio_transcricao(req: AudioTranscricaoRequest):
    """
    Recebe um chunk de áudio (base64, audio/webm) da extensão Chrome,
    transcreve via Whisper (OpenAI) ou Groq e retorna o texto.
    O provedor ativo é controlado pela variável TRANSCRICAO_PROVEDOR no .env.
    Chamado pelo background.js a cada ~15 segundos durante a captura.
    """
    import base64
    import tempfile

    # Decodifica base64 — aceita tanto data-URL quanto base64 puro
    raw = req.audio_base64
    if ',' in raw:
        raw = raw.split(',', 1)[1]
    try:
        audio_bytes = base64.b64decode(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="audio_base64 inválido")

    if len(audio_bytes) < 512:
        return {"texto": "", "ok": True, "motivo": "chunk muito pequeno"}

    provedor_transcricao = os.getenv("TRANSCRICAO_PROVEDOR", "whisper")
    ext = '.webm' if 'webm' in (req.mime_type or '') else '.ogg'
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        if provedor_transcricao == "groq":
            groq_key = os.getenv("GROQ_API_KEY", "")
            if not groq_key:
                raise HTTPException(status_code=500, detail="GROQ_API_KEY não configurada. Configure em Configurações > Transcrição de Áudio.")
            from groq import Groq as GroqClient
            groq_client = GroqClient(api_key=groq_key)
            with open(tmp_path, 'rb') as f:
                transcript = groq_client.audio.transcriptions.create(
                    file=(tmp_path, f.read()),
                    model="whisper-large-v3",
                    language="pt",
                    temperature=0,
                    response_format="verbose_json",
                )
            label = "[Groq]"
        else:
            from openai import OpenAI
            openai_key = os.getenv("OPENAI_API_KEY", "")
            if not openai_key:
                raise HTTPException(status_code=500, detail="OPENAI_API_KEY não configurada. Configure em Configurações > APIs.")
            with OpenAI(api_key=openai_key) as openai_client, open(tmp_path, 'rb') as f:
                transcript = openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language="pt",
                )
            label = "[Whisper]"

        texto = transcript.text.strip() if transcript.text else ""

        if texto and req.meeting_id and req.meeting_id != "default":
            try:
                from agent.sessao_manager import registrar_sessao, salvar_transcricao_bruta
                registrar_sessao(req.meeting_id)
                salvar_transcricao_bruta(req.meeting_id, f"{label} {texto}")
            except Exception as _e:
                logger.warning("[Transcricao] Não foi possível salvar: %s", _e)

        return {"texto": texto, "ok": True, "provedor": provedor_transcricao}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[Transcricao/%s] Erro: %s", provedor_transcricao, e)
        return {"texto": "", "ok": False, "error": str(e)}
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ─────────────────────────────────────────────
# VISUAL SCENARIO AI
# ─────────────────────────────────────────────

@app.post("/generate-visual-scenario")
async def generate_visual_scenario(req: VisualScenarioRequest):
    """
    Gera cenários visuais atual e futuro do cliente via DALL-E 3.
    Usa transcrição + perfil DISC + score para extrair contexto e criar imagens.
    """
    if not req.meeting_id:
        raise HTTPException(status_code=400, detail="meeting_id obrigatório.")
    if not req.transcript or len(req.transcript.strip()) < 50:
        raise HTTPException(status_code=400, detail="Transcrição insuficiente para análise (mínimo 50 caracteres).")

    from agent.visual_scenario import ScenarioComposer
    composer = ScenarioComposer()
    try:
        result = await composer.compose(
            meeting_id=req.meeting_id,
            transcript=req.transcript,
            score=req.score or 0,
            disc_profile=req.disc_profile or "",
            emotional_state=req.emotional_state or "",
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("[visual-scenario] Erro inesperado: %s", e)
        raise HTTPException(status_code=500, detail="Erro interno ao gerar cenário visual.")

    return result


@app.get("/visual-scenarios/{meeting_id}")
def listar_visual_scenarios(meeting_id: str):
    """Lista os cenários visuais gerados para um meeting_id (últimos 10)."""
    from agent.visual_scenario import listar_cenarios
    try:
        cenarios = listar_cenarios(meeting_id)
    except Exception as e:
        logger.error("[visual-scenarios] Erro ao listar: %s", e)
        raise HTTPException(status_code=500, detail="Erro ao buscar cenários.")
    return {"cenarios": cenarios, "total": len(cenarios)}


@app.get("/visual-scenario", response_class=HTMLResponse)
def visual_scenario_page():
    """Serve a página Visual Scenario AI."""
    caminho = Path(__file__).parent.parent / "frontend" / "visual-scenario.html"
    try:
        return HTMLResponse(content=caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="visual-scenario.html não encontrado")


# ─────────────────────────────────────────────
# AUTH — login, cadastro, recuperar senha
# ─────────────────────────────────────────────
import uuid as _uuid
import bcrypt as _bcrypt
import jwt as _jwt
from datetime import timedelta

_JWT_SECRET = os.environ.get("JWT_SECRET", "saleia-secret-change-me")
_JWT_ALGO = "HS256"
_JWT_EXP_HOURS = 72


def _hash_senha(senha: str) -> str:
    return _bcrypt.hashpw(senha.encode(), _bcrypt.gensalt()).decode()


def _verificar_senha(senha: str, hash_: str) -> bool:
    try:
        return _bcrypt.checkpw(senha.encode(), hash_.encode())
    except Exception:
        return False


def _gerar_token(user_id: str, email: str, perfil: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "perfil": perfil,
        "exp": datetime.utcnow() + timedelta(hours=_JWT_EXP_HOURS),
    }
    return _jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGO)


class AuthLoginRequest(BaseModel):
    email: str
    senha: str


class AuthCadastroRequest(BaseModel):
    nome: str
    email: str
    senha: str


class AuthRecuperarSenhaRequest(BaseModel):
    email: str


class AuthRedefinirSenhaRequest(BaseModel):
    token: str
    nova_senha: str


@app.post("/auth/login")
def auth_login(req: AuthLoginRequest):
    from agent.sessao_manager import _get_conn
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nome, email, senha_hash, perfil, status FROM usuarios WHERE email=%s LIMIT 1",
                (req.email.strip().lower(),),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
    uid, nome, email, senha_hash, perfil, status = row

    if not _verificar_senha(req.senha, senha_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")

    if status == "pendente":
        raise HTTPException(status_code=403, detail="Conta aguardando aprovação do administrador.")

    if status == "inativo":
        raise HTTPException(status_code=403, detail="Conta desativada. Entre em contato com o administrador.")

    token = _gerar_token(str(uid), email, perfil)

    conn2 = _get_conn()
    try:
        with conn2.cursor() as cur:
            cur.execute("UPDATE usuarios SET ultimo_acesso=NOW() WHERE id=%s", (uid,))
        conn2.commit()
    finally:
        conn2.close()

    return {
        "token": token,
        "usuario": {"id": str(uid), "nome": nome, "email": email, "perfil": perfil},
    }


@app.post("/auth/cadastro")
def auth_cadastro(req: AuthCadastroRequest):
    if not req.nome or not req.nome.strip():
        raise HTTPException(status_code=400, detail="Nome obrigatório.")
    if not req.email or "@" not in req.email:
        raise HTTPException(status_code=400, detail="E-mail inválido.")
    if not req.senha or len(req.senha) < 6:
        raise HTTPException(status_code=400, detail="Senha deve ter pelo menos 6 caracteres.")

    from agent.sessao_manager import _get_conn
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM usuarios WHERE email=%s LIMIT 1", (req.email.strip().lower(),))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="E-mail já cadastrado.")

            novo_id = str(_uuid.uuid4())
            senha_hash = _hash_senha(req.senha)
            # primeiro usuário a se cadastrar vira admin automaticamente
            cur.execute("SELECT COUNT(*) FROM usuarios")
            total = cur.fetchone()[0]
            perfil = "admin" if total == 0 else "operador"
            status = "ativo" if perfil == "admin" else "pendente"

            cur.execute(
                """INSERT INTO usuarios (id, nome, email, senha_hash, perfil, status)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (novo_id, req.nome.strip(), req.email.strip().lower(), senha_hash, perfil, status),
            )
        conn.commit()
    finally:
        conn.close()

    return {"ok": True, "perfil": perfil, "status": status}


_RESET_TOKEN_EXP_HORAS = 1


@app.post("/auth/recuperar-senha")
def auth_recuperar_senha(req: AuthRecuperarSenhaRequest, background_tasks: BackgroundTasks):
    import secrets
    from agent.sessao_manager import _get_conn
    from agent.email_service import enviar_email_recuperacao

    # Resposta neutra sempre — não vaza se o e-mail existe ou não
    _resposta_neutra = {"ok": True, "mensagem": "Se o e-mail estiver cadastrado, você receberá as instruções em breve."}

    email = (req.email or "").strip().lower()
    if not email or "@" not in email:
        return _resposta_neutra

    try:
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM usuarios WHERE email=%s AND status='ativo' LIMIT 1", (email,))
                row = cur.fetchone()
                if not row:
                    return _resposta_neutra

                token = secrets.token_urlsafe(32)
                exp = datetime.utcnow() + timedelta(hours=_RESET_TOKEN_EXP_HORAS)
                cur.execute(
                    "UPDATE usuarios SET reset_token=%s, reset_token_exp=%s WHERE email=%s",
                    (token, exp, email),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.error("[Auth] Erro ao gerar token de reset: %s", e)
        return _resposta_neutra

    # Envia e-mail em background para não bloquear a resposta
    background_tasks.add_task(enviar_email_recuperacao, email, token)
    return _resposta_neutra


_RESET_PAGE_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Redefinir Senha — SALEIA</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:#0f172a;color:#e2e8f0;font-family:Arial,sans-serif;
       min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px}
  .card{background:#1e293b;border-radius:12px;padding:32px;width:100%;max-width:400px}
  h2{color:#38bdf8;margin-bottom:16px;font-size:1.25rem}
  label{display:block;font-size:.85rem;color:#94a3b8;margin-bottom:4px;margin-top:16px}
  input{width:100%;padding:10px 12px;background:#0f172a;border:1px solid #334155;
        border-radius:8px;color:#e2e8f0;font-size:.95rem;outline:none}
  input:focus{border-color:#38bdf8}
  button{width:100%;margin-top:24px;padding:12px;background:#38bdf8;color:#0f172a;
         border:none;border-radius:8px;font-weight:bold;font-size:1rem;cursor:pointer}
  button:disabled{opacity:.5;cursor:not-allowed}
  #msg{margin-top:16px;font-size:.9rem;min-height:20px}
  .ok{color:#4ade80} .err{color:#f87171}
</style>
</head>
<body>
<div class="card">
  <h2>Redefinir senha</h2>
  <div id="form-wrap">
    <label for="senha">Nova senha</label>
    <input type="password" id="senha" placeholder="Mínimo 6 caracteres">
    <label for="confirmar">Confirmar senha</label>
    <input type="password" id="confirmar" placeholder="Repita a nova senha">
    <button id="btn" onclick="redefinir()">Salvar nova senha</button>
    <div id="msg"></div>
  </div>
  <div id="ok-wrap" style="display:none">
    <p class="ok">✅ Senha redefinida com sucesso!</p>
    <p style="margin-top:12px;font-size:.9rem">
      <a href="/login" style="color:#38bdf8">Ir para o login</a>
    </p>
  </div>
</div>
<script>
  const token = new URLSearchParams(location.search).get('token') || '';

  async function redefinir() {
    const nova = document.getElementById('senha').value;
    const conf = document.getElementById('confirmar').value;
    const msg  = document.getElementById('msg');
    msg.textContent = '';
    if (!nova || nova.length < 6) { msg.className='err'; msg.textContent='Mínimo 6 caracteres.'; return; }
    if (nova !== conf) { msg.className='err'; msg.textContent='As senhas não coincidem.'; return; }

    document.getElementById('btn').disabled = true;
    msg.className=''; msg.textContent='Aguarde...';
    try {
      const r = await fetch('/auth/redefinir-senha', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ token, nova_senha: nova }),
      });
      const d = await r.json().catch(() => ({}));
      if (r.ok) {
        document.getElementById('form-wrap').style.display='none';
        document.getElementById('ok-wrap').style.display='block';
      } else {
        msg.className='err';
        msg.textContent = d.detail || d.mensagem || 'Token inválido ou expirado.';
        document.getElementById('btn').disabled = false;
      }
    } catch(e) {
      msg.className='err'; msg.textContent='Erro de conexão. Tente novamente.';
      document.getElementById('btn').disabled = false;
    }
  }
</script>
</body>
</html>"""


@app.get("/reset", response_class=HTMLResponse)
def pagina_reset_senha(token: str = ""):
    if not token:
        return HTMLResponse("<p>Link inválido.</p>", status_code=400)
    return HTMLResponse(_RESET_PAGE_HTML)


@app.post("/auth/redefinir-senha")
def auth_redefinir_senha(req: AuthRedefinirSenhaRequest):
    from agent.sessao_manager import _get_conn

    if not req.token or not req.nova_senha or len(req.nova_senha) < 6:
        raise HTTPException(status_code=400, detail="Senha deve ter pelo menos 6 caracteres.")

    try:
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, reset_token_exp FROM usuarios WHERE reset_token=%s LIMIT 1",
                    (req.token,),
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=400, detail="Token inválido ou já utilizado.")

                uid, exp = row
                if not exp or datetime.utcnow() > exp:
                    raise HTTPException(status_code=400, detail="Token expirado. Solicite um novo link.")

                novo_hash = _hash_senha(req.nova_senha)
                cur.execute(
                    "UPDATE usuarios SET senha_hash=%s, reset_token=NULL, reset_token_exp=NULL WHERE id=%s",
                    (novo_hash, uid),
                )
            conn.commit()
        finally:
            conn.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[Auth] Erro ao redefinir senha: %s", e)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")

    return {"ok": True, "mensagem": "Senha redefinida com sucesso."}


# ─────────────────────────────────────────────
# OCR de imagem via AI Vision
# ─────────────────────────────────────────────
import base64 as _b64


@app.post("/base/ocr")
async def base_ocr_imagem(arquivo: UploadFile = File(...)):
    """Extrai texto de uma imagem (JPEG/PNG/WEBP/GIF) via AI Vision."""
    conteudo = await arquivo.read()
    if len(conteudo) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Imagem muito grande (máx 10 MB).")

    mime = arquivo.content_type or "image/jpeg"
    b64 = _b64.b64encode(conteudo).decode()
    data_url = f"data:{mime};base64,{b64}"

    prompt = (
        "Extraia TODO o texto visível nesta imagem, mantendo a estrutura original. "
        "Inclua títulos, parágrafos, listas, tabelas e qualquer texto escrito. "
        "Retorne APENAS o texto extraído, sem comentários ou explicações."
    )

    # Tenta Anthropic (Claude vision)
    try:
        import anthropic as _anth
        chave = os.environ.get("ANTHROPIC_API_KEY", "")
        if chave:
            async with _anth.AsyncAnthropic(api_key=chave) as cliente:
                msg = await cliente.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=4096,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
                            {"type": "text", "text": prompt},
                        ],
                    }],
                )
            texto = msg.content[0].text.strip()
            if texto:
                return {"ok": True, "texto": texto, "provedor": "anthropic"}
    except Exception as e:
        logger.warning("[OCR] Anthropic falhou: %s", e)

    # Fallback OpenAI GPT-4o Vision
    try:
        from openai import AsyncOpenAI as _OAI
        chave = os.environ.get("OPENAI_API_KEY", "")
        if chave:
            async with _OAI(api_key=chave) as cliente:
                resp = await cliente.chat.completions.create(
                    model="gpt-4o",
                    max_tokens=4096,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": data_url}},
                            {"type": "text", "text": prompt},
                        ],
                    }],
                )
            texto = resp.choices[0].message.content.strip()
            if texto:
                return {"ok": True, "texto": texto, "provedor": "openai"}
    except Exception as e:
        logger.warning("[OCR] OpenAI falhou: %s", e)

    raise HTTPException(status_code=502, detail="Nenhum provedor de visão disponível. Verifique as chaves de API em Configurações.")


# ─────────────────────────────────────────────
# ADMIN — gerenciamento de usuários e APIs
# ─────────────────────────────────────────────
from fastapi import Header as _Header


def _req_auth(authorization: str | None) -> dict:
    """Verifica JWT. Retorna payload sem exigir perfil específico."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token não fornecido.")
    token = authorization[7:]
    try:
        payload = _jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGO])
    except _jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado.")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido.")
    return payload


def _req_admin(authorization: str | None) -> dict:
    """Verifica JWT e exige perfil admin. Retorna payload."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token não fornecido.")
    token = authorization[7:]
    try:
        payload = _jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGO])
    except _jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado.")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido.")
    if payload.get("perfil") != "admin":
        raise HTTPException(status_code=403, detail="Apenas administradores têm acesso.")
    return payload


# ── Usuários ──────────────────────────────────

@app.get("/admin/usuarios")
def admin_listar_usuarios(authorization: str | None = _Header(default=None)):
    _req_admin(authorization)
    from agent.sessao_manager import _get_conn
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nome, email, perfil, plano, status, data_cadastro, ultimo_acesso "
                "FROM usuarios ORDER BY data_cadastro DESC"
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    usuarios = [
        {
            "id": str(r[0]), "nome": r[1], "email": r[2], "perfil": r[3],
            "plano": r[4] or "free", "status": r[5],
            "data_cadastro": r[6].isoformat() if r[6] else None,
            "ultimo_acesso": r[7].isoformat() if r[7] else None,
        }
        for r in rows
    ]
    return {"usuarios": usuarios, "total": len(usuarios)}


@app.patch("/admin/usuarios/{uid}/inativar")
def admin_inativar_usuario(uid: str, authorization: str | None = _Header(default=None)):
    _req_admin(authorization)
    _admin_set_status(uid, "inativo")
    return {"ok": True}


@app.patch("/admin/usuarios/{uid}/reativar")
def admin_reativar_usuario(uid: str, authorization: str | None = _Header(default=None)):
    _req_admin(authorization)
    _admin_set_status(uid, "ativo")
    return {"ok": True}


@app.patch("/admin/usuarios/{uid}/resetar-senha")
def admin_resetar_senha(uid: str, authorization: str | None = _Header(default=None)):
    _req_admin(authorization)
    nova_senha = "Saleia@2025"
    from agent.sessao_manager import _get_conn
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE usuarios SET senha_hash=%s WHERE id=%s",
                (_hash_senha(nova_senha), uid),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "nova_senha": nova_senha}


class AdminPerfilRequest(BaseModel):
    perfil: str


class AdminPlanoRequest(BaseModel):
    plano: str


@app.patch("/admin/usuarios/{uid}/perfil")
def admin_alterar_perfil(uid: str, req: AdminPerfilRequest, authorization: str | None = _Header(default=None)):
    _req_admin(authorization)
    if req.perfil not in ("admin", "gerente", "operador", "usuario"):
        raise HTTPException(status_code=400, detail="Perfil inválido.")
    from agent.sessao_manager import _get_conn
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE usuarios SET perfil=%s WHERE id=%s", (req.perfil, uid))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@app.patch("/admin/usuarios/{uid}/plano")
def admin_alterar_plano(uid: str, req: AdminPlanoRequest, authorization: str | None = _Header(default=None)):
    _req_admin(authorization)
    if req.plano not in ("free", "pro", "enterprise"):
        raise HTTPException(status_code=400, detail="Plano inválido.")
    from agent.sessao_manager import _get_conn
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE usuarios SET plano=%s WHERE id=%s", (req.plano, uid))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


class AdminSetStatusRequest(BaseModel):
    status: str


@app.patch("/admin/usuarios/{uid}/status")
def admin_set_status_usuario(uid: str, req: AdminSetStatusRequest, authorization: str | None = _Header(default=None)):
    _req_admin(authorization)
    if req.status not in ("ativo", "inativo", "pendente"):
        raise HTTPException(status_code=400, detail="Status inválido.")
    _admin_set_status(uid, req.status)
    return {"ok": True}


@app.delete("/admin/usuarios/{uid}")
def admin_excluir_usuario(uid: str, authorization: str | None = _Header(default=None)):
    _req_admin(authorization)
    from agent.sessao_manager import _get_conn
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM usuarios WHERE id=%s", (uid,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


def _admin_set_status(uid: str, status: str):
    from agent.sessao_manager import _get_conn
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE usuarios SET status=%s WHERE id=%s", (status, uid))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        conn.commit()
    finally:
        conn.close()


# ─────────────────────────────────────────────
# CLAUDE ACCOUNT MODE — piloto: cada usuário usa sua própria conta Claude
#
# Modo experimental e controlado (Tarefa 22). Não é infraestrutura definitiva
# de produção — pode ser desativado a qualquer momento via CLAUDE_ACCOUNT_PILOT.
# ─────────────────────────────────────────────
import hashlib as _hashlib

from agent.claude_account import (
    PROMPT_ANALISE_CLAUDE_ACCOUNT,
    ClaudeAccountError,
    claude_account_executor,
    claude_pilot_habilitado,
    criptografar_token,
    sanitizar_erro_claude,
)
from api.database import (
    criar_claude_analysis_pendente,
    desconectar_claude_connection,
    finalizar_claude_analysis,
    listar_claude_analyses,
    metricas_claude_account,
    obter_claude_analysis_por_hash,
    obter_claude_connection,
    salvar_claude_analysis_feedback,
    salvar_claude_connection,
)


def _req_claude_pilot(authorization: str | None) -> dict:
    """Confirma JWT válido e que a feature flag do piloto está ativa."""
    payload = _req_auth(authorization)
    if not claude_pilot_habilitado():
        raise HTTPException(status_code=404, detail="Funcionalidade indisponível.")
    return payload


class ClaudeConnectRequest(BaseModel):
    oauth_token: str


class ClaudeAnalisarRequest(BaseModel):
    meeting_id: str
    # Transcrição colada diretamente (análise manual) — quando presente, pula
    # a busca por sessão gravada em `sessoes` e usa esse texto como contexto.
    transcricao: Optional[str] = None


class ClaudeFeedbackRequest(BaseModel):
    rating: str  # positivo | parcial | negativo
    tags: Optional[list[str]] = None


def _claude_connection_publica(conexao: dict | None) -> dict:
    """Formato seguro para o frontend — nunca inclui o token."""
    if not conexao:
        return {"conectado": False, "status": "inativo"}
    return {
        "conectado": conexao["status"] == "ativo",
        "status": conexao["status"],
        "connected_at": conexao.get("connected_at"),
        "last_used_at": conexao.get("last_used_at"),
    }


@app.get("/claude-account/status")
def claude_account_status(authorization: str | None = _Header(default=None)):
    payload = _req_claude_pilot(authorization)
    conexao = obter_claude_connection(payload["sub"])
    return _claude_connection_publica(conexao)


@app.post("/claude-account/connect")
def claude_account_connect(req: ClaudeConnectRequest, authorization: str | None = _Header(default=None)):
    payload = _req_claude_pilot(authorization)
    token = (req.oauth_token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token da conta Claude não informado.")

    token_criptografado = criptografar_token(token)
    conexao = salvar_claude_connection(payload["sub"], token_criptografado)
    logger.info("[ClaudeAccount] Usuário %s conectou sua conta Claude.", payload["sub"])
    return _claude_connection_publica(conexao)


@app.post("/claude-account/disconnect")
def claude_account_disconnect(authorization: str | None = _Header(default=None)):
    payload = _req_claude_pilot(authorization)
    conexao = desconectar_claude_connection(payload["sub"])
    logger.info("[ClaudeAccount] Usuário %s desconectou sua conta Claude.", payload["sub"])
    return _claude_connection_publica(conexao)


@app.post("/claude-account/analisar")
async def claude_account_analisar(req: ClaudeAnalisarRequest, authorization: str | None = _Header(default=None)):
    payload = _req_claude_pilot(authorization)
    usuario_id = payload["sub"]
    meeting_id = (req.meeting_id or "").strip()
    if not meeting_id:
        raise HTTPException(status_code=400, detail="meeting_id é obrigatório.")

    transcricao_colada = (req.transcricao or "").strip()
    if transcricao_colada:
        transcricao = transcricao_colada
    else:
        from agent.sessao_manager import obter_transcricao_mais_recente

        transcricao = obter_transcricao_mais_recente(meeting_id)
        if not transcricao.strip():
            raise HTTPException(status_code=404, detail="Nenhuma transcrição encontrada para esta reunião.")

    transcript_hash = _hashlib.sha256(transcricao.encode("utf-8")).hexdigest()

    existente = obter_claude_analysis_por_hash(meeting_id, usuario_id, transcript_hash)
    if existente:
        return {**existente, "reused": True}

    registro = criar_claude_analysis_pendente(meeting_id, usuario_id, transcript_hash)

    try:
        resultado = await claude_account_executor.execute(
            usuario_id=usuario_id,
            prompt=PROMPT_ANALISE_CLAUDE_ACCOUNT,
            context=transcricao,
        )
    except ClaudeAccountError as exc:
        finalizar_claude_analysis(
            registro["id"],
            status="erro",
            error_code=exc.code,
            error_message=sanitizar_erro_claude(exc.detalhe or exc.message),
        )
        raise HTTPException(status_code=422, detail={"erro": exc.message, "codigo": exc.code}) from exc
    except Exception as exc:  # nunca deixar exceção crua vazar token/detalhe não sanitizado
        detalhe = sanitizar_erro_claude(str(exc))
        finalizar_claude_analysis(registro["id"], status="erro", error_code="GENERIC_ERROR", error_message=detalhe)
        logger.error("[ClaudeAccount] Falha não classificada ao analisar meeting_id=%s: %s", meeting_id, detalhe)
        raise HTTPException(status_code=500, detail={"erro": "Não foi possível concluir a análise.", "codigo": "GENERIC_ERROR"}) from exc

    final = finalizar_claude_analysis(registro["id"], status="sucesso", resultado=resultado)
    return {**final, "reused": False}


@app.get("/claude-account/analises/{meeting_id}")
def claude_account_listar_analises(meeting_id: str, authorization: str | None = _Header(default=None)):
    payload = _req_claude_pilot(authorization)
    return {"analises": listar_claude_analyses(meeting_id, payload["sub"])}


@app.post("/claude-account/analises/{analysis_id}/feedback")
def claude_account_feedback(analysis_id: int, req: ClaudeFeedbackRequest, authorization: str | None = _Header(default=None)):
    payload = _req_claude_pilot(authorization)
    if req.rating not in ("positivo", "parcial", "negativo"):
        raise HTTPException(status_code=400, detail="rating inválido.")

    atualizado = salvar_claude_analysis_feedback(analysis_id, payload["sub"], req.rating, req.tags)
    if not atualizado:
        raise HTTPException(status_code=404, detail="Análise não encontrada.")
    return atualizado


@app.get("/admin/claude-account/metricas")
def claude_account_metricas_admin(authorization: str | None = _Header(default=None)):
    _req_admin(authorization)
    return metricas_claude_account()


# ── APIs / Provedores ─────────────────────────

_ultimo_teste: dict[str, dict] = {}  # {pid: {"ok": bool, "ts": float, "detalhe": str}} — cache local do worker


def _ler_testes_compartilhados() -> dict:
    """Lê resultados de teste do SQLite (compartilhado entre todos os workers uvicorn)."""
    try:
        from api.metricas_historico import ler_testes_provedores
        db_testes = ler_testes_provedores()
        # Mescla com in-memory: o mais recente vence
        resultado = dict(db_testes)
        for pid, v in _ultimo_teste.items():
            if pid not in resultado or v["ts"] > resultado[pid]["ts"]:
                resultado[pid] = v
        return resultado
    except Exception:
        return dict(_ultimo_teste)

_PROVEDORES_CONF = {
    "deepseek":  {"nome": "DeepSeek",   "modelo": "deepseek-chat",   "env_key": "DEEPSEEK_API_KEY"},
    "openai":    {"nome": "OpenAI",     "modelo": "gpt-4o",          "env_key": "OPENAI_API_KEY"},
    "anthropic": {"nome": "Anthropic",  "modelo": "claude-sonnet-4-6","env_key": "ANTHROPIC_API_KEY"},
    "gemini":    {"nome": "Gemini",     "modelo": "gemini-2.0-flash", "env_key": "GEMINI_API_KEY"},
}


def _env_path() -> Path:
    return Path(__file__).parent.parent / ".env"


def _ler_env() -> dict:
    env = {}
    p = _env_path()
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _salvar_env_key(chave_env: str, valor: str):
    p = _env_path()
    linhas = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    encontrou = False
    novas = []
    for linha in linhas:
        if linha.strip().startswith(chave_env + "="):
            novas.append(f'{chave_env}="{valor}"')
            encontrou = True
        else:
            novas.append(linha)
    if not encontrou:
        novas.append(f'{chave_env}="{valor}"')
    p.write_text("\n".join(novas) + "\n", encoding="utf-8")
    os.environ[chave_env] = valor
    load_dotenv(override=True)


@app.get("/admin/api/provedores")
def admin_listar_provedores(authorization: str | None = _Header(default=None)):
    _req_admin(authorization)
    env = _ler_env()
    principal = env.get("PROVEDOR_PREFERIDO", "deepseek")
    provedores = []
    for pid, conf in _PROVEDORES_CONF.items():
        chave_arquivo = env.get(conf["env_key"], "")
        tem_chave = bool(chave_arquivo and len(chave_arquivo) > 8)
        chave_runtime = os.environ.get(conf["env_key"], "")
        ativo = bool(chave_runtime and len(chave_runtime) > 8)
        provedores.append({
            "id": pid,
            "nome": conf["nome"],
            "modelo": conf["modelo"],
            "ativo": ativo,
            "principal": pid == principal,
            "tem_chave": tem_chave,
        })
    return {"provedores": provedores}


class AdminChaveRequest(BaseModel):
    chave: str


@app.post("/admin/api/provedores/{pid}/chave")
def admin_salvar_chave(pid: str, req: AdminChaveRequest, authorization: str | None = _Header(default=None)):
    _req_admin(authorization)
    if pid not in _PROVEDORES_CONF:
        raise HTTPException(status_code=404, detail="Provedor desconhecido.")
    if not req.chave or len(req.chave.strip()) < 8:
        raise HTTPException(status_code=400, detail="Chave inválida.")
    env_key = _PROVEDORES_CONF[pid]["env_key"]
    _salvar_env_key(env_key, req.chave.strip())
    return {"ok": True}


class AdminTesteRequest(BaseModel):
    provedor: str


@app.post("/admin/api/teste")
async def admin_testar_provedor(req: AdminTesteRequest, authorization: str | None = _Header(default=None)):
    _req_admin(authorization)
    pid = req.provedor
    if pid not in _PROVEDORES_CONF:
        raise HTTPException(status_code=404, detail="Provedor desconhecido.")
    env = _ler_env()
    chave = env.get(_PROVEDORES_CONF[pid]["env_key"], "")
    if not chave:
        return {"ok": False, "detalhe": "Chave não configurada."}
    import time as _time
    try:
        if pid == "openai":
            from openai import AsyncOpenAI as _OAI
            async with _OAI(api_key=chave) as c:
                await c.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":"ping"}], max_tokens=1)
        elif pid == "deepseek":
            from openai import AsyncOpenAI as _OAI
            async with _OAI(api_key=chave, base_url="https://api.deepseek.com") as c:
                await c.chat.completions.create(model="deepseek-chat", messages=[{"role":"user","content":"ping"}], max_tokens=1)
        elif pid == "anthropic":
            import anthropic as _anth
            async with _anth.AsyncAnthropic(api_key=chave) as c:
                await c.messages.create(model="claude-haiku-4-5-20251001", max_tokens=1, messages=[{"role":"user","content":"ping"}])
        elif pid == "gemini":
            import google.generativeai as _gem
            _gem.configure(api_key=chave)
            modelo_gemini = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
            m = _gem.GenerativeModel(modelo_gemini)
            await asyncio.to_thread(m.generate_content, "ping")
        ts_ok = _time.time()
        _ultimo_teste[pid] = {"ok": True, "ts": ts_ok, "detalhe": ""}
        try:
            from api.metricas_historico import salvar_teste_provedor
            salvar_teste_provedor(pid, True, ts_ok, "")
        except Exception:
            pass
        return {"ok": True}
    except Exception as e:
        detalhe = str(e)[:120]
        ts_fail = _time.time()
        _ultimo_teste[pid] = {"ok": False, "ts": ts_fail, "detalhe": detalhe}
        try:
            from api.metricas_historico import salvar_teste_provedor
            salvar_teste_provedor(pid, False, ts_fail, detalhe)
        except Exception:
            pass
        return {"ok": False, "detalhe": detalhe}


class AdminStatusRequest(BaseModel):
    ativo: bool


@app.patch("/admin/api/provedores/{pid}/status")
def admin_status_provedor(pid: str, req: AdminStatusRequest, authorization: str | None = _Header(default=None)):
    _req_admin(authorization)
    if pid not in _PROVEDORES_CONF:
        raise HTTPException(status_code=404, detail="Provedor desconhecido.")
    env_key = _PROVEDORES_CONF[pid]["env_key"]
    env = _ler_env()
    chave = env.get(env_key, "")
    if req.ativo and not chave:
        raise HTTPException(status_code=400, detail="Configure a chave de API antes de ativar.")
    # Propaga ativação/desativação ao processo atual sem alterar o arquivo .env
    if req.ativo:
        os.environ[env_key] = chave
    else:
        os.environ[env_key] = ""
    return {"ok": True}


class AdminPrincipalRequest(BaseModel):
    provedor: str


@app.post("/admin/api/principal")
def admin_definir_principal(req: AdminPrincipalRequest, authorization: str | None = _Header(default=None)):
    _req_admin(authorization)
    if req.provedor not in _PROVEDORES_CONF:
        raise HTTPException(status_code=404, detail="Provedor desconhecido.")
    _salvar_env_key("PROVEDOR_PREFERIDO", req.provedor)  # já seta os.environ internamente
    return {"ok": True}


@app.get("/admin/embeddings/status")
async def admin_embeddings_status(authorization: str | None = _Header(default=None)):
    """Diagnóstico do provedor de embeddings ativo — nunca retorna chaves,
    conteúdo do .env, texto de documentos/memórias ou vetores brutos."""
    _req_admin(authorization)
    from services.embeddings import EmbeddingProviderError, get_embedding_provider

    resposta = {
        "provider": None,
        "model": None,
        "dimension": None,
        "ok": False,
        "detalhe": "",
        "fallback_provider": os.environ.get("EMBEDDING_FALLBACK_PROVIDER", "").strip() or None,
        "indexado": {
            "base_conhecimento": {"total": 0, "com_embedding": 0, "provider_atual": 0},
            "sales_memories": {"total": 0, "com_embedding": 0, "provider_atual": 0},
        },
        "cache": {
            "base_conhecimento": {"carregado": False, "itens": 0},
            "sales_memories": {"carregado": False, "itens": 0},
        },
    }

    try:
        provider = get_embedding_provider()
        resposta["provider"] = provider.provider_name
        resposta["model"] = provider.model_name
        hc = await provider.health_check(5.0)
        resposta["ok"] = hc.get("ok", False)
        resposta["detalhe"] = str(hc.get("detalhe", ""))[:200]
        resposta["dimension"] = hc.get("dimension")
    except EmbeddingProviderError as e:
        resposta["detalhe"] = f"Configuração inválida: {str(e)[:180]}"
    except Exception as e:
        resposta["detalhe"] = f"Erro inesperado: {str(e)[:180]}"

    provider_nome = resposta["provider"]
    modelo_nome = resposta["model"]

    from agent.sessao_manager import _get_conn as _base_conn
    try:
        conn = _base_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM base_conhecimento")
            resposta["indexado"]["base_conhecimento"]["total"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM base_conhecimento WHERE embedding IS NOT NULL")
            resposta["indexado"]["base_conhecimento"]["com_embedding"] = cur.fetchone()[0]
            if provider_nome and modelo_nome:
                cur.execute(
                    "SELECT COUNT(*) FROM base_conhecimento "
                    "WHERE embedding_provider = %s AND embedding_model = %s",
                    (provider_nome, modelo_nome),
                )
                resposta["indexado"]["base_conhecimento"]["provider_atual"] = cur.fetchone()[0]
        conn.close()
    except Exception as e:
        logger.debug("[admin_embeddings_status] contagem base_conhecimento falhou: %s", e)

    try:
        from agent.sales_memory import _get_conn as _mem_conn
        conn = _mem_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM sales_memories")
            resposta["indexado"]["sales_memories"]["total"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM sales_memories WHERE embedding IS NOT NULL")
            resposta["indexado"]["sales_memories"]["com_embedding"] = cur.fetchone()[0]
            if provider_nome and modelo_nome:
                cur.execute(
                    "SELECT COUNT(*) FROM sales_memories "
                    "WHERE embedding_provider = %s AND embedding_model = %s",
                    (provider_nome, modelo_nome),
                )
                resposta["indexado"]["sales_memories"]["provider_atual"] = cur.fetchone()[0]
        conn.close()
    except Exception as e:
        logger.debug("[admin_embeddings_status] contagem sales_memories falhou: %s", e)

    try:
        import agent.base_conhecimento as _bc
        cache_bc = _bc._cache
        resposta["cache"]["base_conhecimento"]["carregado"] = cache_bc is not None
        if cache_bc and not cache_bc.get("vazio"):
            resposta["cache"]["base_conhecimento"]["itens"] = len(cache_bc.get("ids", []))
    except Exception:
        pass

    try:
        import agent.sales_memory as _sm
        cache_sm = _sm._cache_memorias
        resposta["cache"]["sales_memories"]["carregado"] = cache_sm is not None
        if cache_sm and not cache_sm.get("vazio"):
            resposta["cache"]["sales_memories"]["itens"] = len(cache_sm.get("ids", []))
    except Exception:
        pass

    return resposta


# ─────────────────────────────────────────────
# TRANSCRIÇÃO DE ÁUDIO — configuração
# ─────────────────────────────────────────────

_TRANSCRICAO_PROVEDORES = {
    "whisper": {
        "nome":    "OpenAI Whisper",
        "modelo":  "whisper-1",
        "env_key": "OPENAI_API_KEY",
        "nota":    "Usa a mesma chave configurada nos provedores de IA (OPENAI_API_KEY).",
    },
    "groq": {
        "nome":    "Groq (Whisper Large v3)",
        "modelo":  "whisper-large-v3",
        "env_key": "GROQ_API_KEY",
        "nota":    "Mais rápido e gratuito até o limite da cota Groq. Crie uma chave em console.groq.com.",
    },
}


@app.get("/admin/transcricao/config")
def admin_get_transcricao(authorization: str | None = _Header(default=None)):
    """Retorna configuração atual do provedor de transcrição de áudio."""
    _req_admin(authorization)
    env = _ler_env()
    provedor_atual = env.get("TRANSCRICAO_PROVEDOR", "whisper")
    provedores = []
    for pid, conf in _TRANSCRICAO_PROVEDORES.items():
        chave = env.get(conf["env_key"], "")
        provedores.append({
            "id":        pid,
            "nome":      conf["nome"],
            "modelo":    conf["modelo"],
            "nota":      conf["nota"],
            "ativo":     pid == provedor_atual,
            "tem_chave": bool(chave and len(chave) > 8),
        })
    return {"provedores": provedores, "provedor_atual": provedor_atual}


class TranscricaoConfigRequest(BaseModel):
    provedor: str
    groq_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    apenas_salvar: Optional[bool] = False


class TranscricaoTesteRequest(BaseModel):
    provedor: str


@app.post("/admin/transcricao/teste")
async def admin_testar_transcricao(req: TranscricaoTesteRequest, authorization: str | None = _Header(default=None)):
    """Valida a chave do provedor de transcrição via models.list() — sem enviar áudio."""
    _req_admin(authorization)
    pid = req.provedor
    if pid not in _TRANSCRICAO_PROVEDORES:
        raise HTTPException(status_code=404, detail="Provedor desconhecido.")
    try:
        if pid == "groq":
            from groq import AsyncGroq
            chave = os.getenv("GROQ_API_KEY", "")
            if not chave:
                return {"ok": False, "detalhe": "GROQ_API_KEY não configurada."}
            client = AsyncGroq(api_key=chave)
            await client.models.list()
        elif pid in ("whisper", "openai_whisper"):
            from openai import AsyncOpenAI as _OAI
            chave = os.getenv("OPENAI_API_KEY", "")
            if not chave:
                return {"ok": False, "detalhe": "OPENAI_API_KEY não configurada. Configure em Configuração de APIs."}
            client = _OAI(api_key=chave)
            await client.models.list()
        return {"ok": True}
    except Exception as e:
        detalhe = str(e)[:150]
        return {"ok": False, "detalhe": detalhe}


@app.post("/admin/transcricao/config")
def admin_set_transcricao(req: TranscricaoConfigRequest, authorization: str | None = _Header(default=None)):
    """Define o provedor de transcrição de áudio e opcionalmente salva a chave Groq."""
    _req_admin(authorization)
    if req.provedor not in _TRANSCRICAO_PROVEDORES:
        raise HTTPException(status_code=400, detail="Provedor desconhecido.")
    conf = _TRANSCRICAO_PROVEDORES[req.provedor]
    # Salvar chaves se fornecidas
    if req.provedor == "groq" and req.groq_api_key and req.groq_api_key.strip():
        _salvar_env_key("GROQ_API_KEY", req.groq_api_key.strip())
    if req.provedor in ("whisper", "openai_whisper") and req.openai_api_key and req.openai_api_key.strip():
        _salvar_env_key("OPENAI_API_KEY", req.openai_api_key.strip())
    # Apenas salvar a chave, sem ativar o provedor
    if req.apenas_salvar:
        return {"ok": True, "msg": "Chave salva com sucesso."}
    # Verificar se a chave necessária existe antes de ativar
    env = _ler_env()
    chave = env.get(conf["env_key"], "")
    if not chave:
        raise HTTPException(
            status_code=400,
            detail=f"Chave de API do {conf['nome']} não configurada. Adicione antes de ativar.",
        )
    _salvar_env_key("TRANSCRICAO_PROVEDOR", req.provedor)
    return {"ok": True, "provedor": req.provedor, "modelo": conf["modelo"]}
