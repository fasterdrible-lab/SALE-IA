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
import json
import asyncio
import html as html_module
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from api.ai_router import chamar_ia, definir_provedor_preferido, rotacionar_provedor_preferido, snapshot_provedores
from api.database import criar_tabelas, salvar_relatorio as db_salvar, listar_relatorios as db_listar, buscar_ultimo_relatorio as db_ultimo, obter_meeting_memory

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# CONFIGURAÇÃO
# ─────────────────────────────────────────────
app = FastAPI(
    title="SALEIA — Assistente de Vendas IA",
    description="Backend para o assistente de vendas em tempo real no Google Meet",
    version="1.0.0",
)

# CORS — permite requisições da extensão Chrome (chrome-extension://)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Clientes de IA gerenciados pelo ai_router (com fallback automático)

# Armazenamento em memória do último relatório (cache rápido)
ultimo_relatorio: dict = {}

# Pasta para persistência de relatórios em arquivo (fallback legado)
PASTA_RELATORIOS = Path("data/relatorios")
PASTA_RELATORIOS.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────
# BANCO DE DADOS — SQLite via SQLModel
# ─────────────────────────────────────────────
from api.database import criar_tabelas, salvar_relatorio as db_salvar, listar_relatorios as db_listar, buscar_ultimo_relatorio as db_ultimo

@app.on_event("startup")
def on_startup():
    criar_tabelas()
    logger.info("✅ Banco de dados inicializado.")
    # Criar tabela de sessões no MySQL
    try:
        from agent.sessao_manager import criar_tabela_sessoes
        criar_tabela_sessoes()
    except Exception as e:
        logger.warning("Tabela sessoes não criada no MySQL: %s", e)

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


class RecapitulacaoVivaRequest(BaseModel):
    meeting_id: str


class ProvedorIARequest(BaseModel):
    provedor: str


class IniciarSessaoRequest(BaseModel):
    meeting_id: str


class ExportarBaseRequest(BaseModel):
    titulo: Optional[str] = ""
    tipo: Optional[str] = "reuniao"


class AdicionarBaseRequest(BaseModel):
    titulo: str
    tipo: Optional[str] = "instrucao"
    texto: str


class AudioTranscricaoRequest(BaseModel):
    audio_base64: str          # formato: "data:audio/webm;base64,XXXX"
    mime_type: Optional[str] = "audio/webm"
    meeting_id: Optional[str] = "default"


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
  "justificativa_probabilidade": "por que esta probabilidade"
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
    """Verificação de saúde do serviço — inclui status dos provedores de IA."""
    snapshot = snapshot_provedores()
    provedores = snapshot["ia"]
    ia_ok = any(
        p.get("status") == "ok" or p.get("status", "").startswith("degradado")
        for p in provedores.values()
    )
    return {
        "status": "online" if ia_ok else "degradado",
        "servico": "SALEIA Backend",
        "versao": "1.3.0",
        "timestamp": datetime.now().isoformat(),
        "ia": provedores,
        "ordem_ia": snapshot["ordem_ia"],
        "provedor_preferido": snapshot["provedor_preferido"],
        "banco": "mysql" if os.environ.get("DB_HOST") else "sqlite",
    }


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
def recapitulacao_completa(req: RecapitulacaoRequest):
    """
    Gera recapitulação emocional e estratégica completa pós-reunião.
    Substitui o processo manual de colar transcrição no Claude.
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

    # Armazenar como último relatório
    global ultimo_relatorio
    ultimo_relatorio = resultado

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


@app.get("/relatorios")
def listar_relatorios_endpoint():
    """Lista todos os relatórios salvos (banco SQLite + fallback arquivos JSON)."""
    try:
        # Tentar banco primeiro
        try:
            rows = db_listar(limite=20)
            if rows:
                return {"total": len(rows), "fonte": "sqlite", "relatorios": [
                    {
                        "id": r["id"],
                        "titulo": r["nome_reuniao"],
                        "data": r["criado_em"],
                        "probabilidade_fechamento": r["dados"].get("recapitulacao", {}).get("probabilidade_fechamento", ""),
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
                })
            except Exception:
                continue
        return {"total": len(relatorios), "fonte": "arquivos", "relatorios": relatorios}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/recapitulacao-manual")
def recapitulacao_manual(req: RecapitulacaoRequest):
    """
    Endpoint simplificado: cola a transcrição e gera recapitulação + DISC + diagnóstico financeiro.
    Ideal para uso no painel HTML sem a extensão Chrome.
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
        sessoes = listar_sessoes(limite=50)
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
    from agent.sessao_manager import _get_conn
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, titulo, tipo, CHAR_LENGTH(texto) AS chars, created_at "
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
        }
        for r in rows
    ]
    return {"docs": docs, "total": len(docs)}


@app.post("/base")
async def adicionar_base(req: AdicionarBaseRequest):
    """Adiciona um documento à base de conhecimento, gerando embedding via OpenAI."""
    if not req.titulo or not req.titulo.strip():
        raise HTTPException(status_code=400, detail="Título obrigatório")
    if not req.texto or len(req.texto.strip()) < 10:
        raise HTTPException(status_code=400, detail="Texto muito curto (mínimo 10 caracteres)")

    import json as _json
    from openai import AsyncOpenAI
    try:
        client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        resp = await client.embeddings.create(
            model="text-embedding-3-small",
            input=req.texto[:8000],
        )
        embedding_json = _json.dumps(resp.data[0].embedding)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro ao gerar embedding: {e}")

    from agent.sessao_manager import _get_conn
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO base_conhecimento (titulo, tipo, texto, embedding) VALUES (%s, %s, %s, %s)",
                (req.titulo.strip(), req.tipo or "instrucao", req.texto, embedding_json),
            )
            novo_id = cur.lastrowid
        conn.commit()
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    from agent.base_conhecimento import invalidar_cache
    invalidar_cache()
    return {"ok": True, "id": novo_id, "chars": len(req.texto)}


@app.delete("/base/{doc_id}")
def remover_base(doc_id: int):
    """Remove um documento da base de conhecimento."""
    from agent.sessao_manager import _get_conn
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM base_conhecimento WHERE id = %s", (doc_id,))
            affected = cur.rowcount
        conn.commit()
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if affected == 0:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
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
# WHISPER — transcrição de áudio em tempo real
# ─────────────────────────────────────────────
@app.post("/audio-transcricao")
async def audio_transcricao(req: AudioTranscricaoRequest):
    """
    Recebe um chunk de áudio (base64, audio/webm) da extensão Chrome,
    transcreve via OpenAI Whisper-1 e retorna o texto.
    Chamado pelo background.js a cada ~15 segundos durante a captura.
    """
    import base64
    import tempfile
    import re as _re

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

    # Extensão baseada no mime_type
    ext = '.webm' if 'webm' in (req.mime_type or '') else '.ogg'
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY não configurada")

        from openai import OpenAI
        client = OpenAI(api_key=openai_key)

        with open(tmp_path, 'rb') as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="pt",
            )

        texto = transcript.text.strip() if transcript.text else ""

        # Persiste na transcrição bruta da sessão (mesmo pipeline das legendas CC)
        # Garante que a sessão exista — registrar_sessao() cria se não houver
        if texto and req.meeting_id and req.meeting_id != "default":
            try:
                from agent.sessao_manager import registrar_sessao, salvar_transcricao_bruta
                registrar_sessao(req.meeting_id)  # no-op se já existe
                salvar_transcricao_bruta(req.meeting_id, f"[Whisper] {texto}")
            except Exception as _e:
                logger.warning("[Whisper] Não foi possível salvar transcrição: %s", _e)

        return {"texto": texto, "ok": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[Whisper] Erro na transcrição: %s", e)
        return {"texto": "", "ok": False, "error": str(e)}
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


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


@app.post("/auth/recuperar-senha")
def auth_recuperar_senha(req: AuthRecuperarSenhaRequest):
    # Stub — apenas confirma recebimento (envio de e-mail não implementado)
    return {"ok": True, "mensagem": "Se o e-mail estiver cadastrado, você receberá as instruções em breve."}


# ─────────────────────────────────────────────
# ADMIN — gerenciamento de usuários e APIs
# ─────────────────────────────────────────────
from fastapi import Header as _Header


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


# ── APIs / Provedores ─────────────────────────

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
        chave = env.get(conf["env_key"], "")
        tem_chave = bool(chave and len(chave) > 8)
        ativo = tem_chave
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
    try:
        if pid == "openai":
            from openai import AsyncOpenAI as _OAI
            c = _OAI(api_key=chave)
            await c.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":"ping"}], max_tokens=1)
        elif pid == "deepseek":
            from openai import AsyncOpenAI as _OAI
            c = _OAI(api_key=chave, base_url="https://api.deepseek.com")
            await c.chat.completions.create(model="deepseek-chat", messages=[{"role":"user","content":"ping"}], max_tokens=1)
        elif pid == "anthropic":
            import anthropic as _anth
            c = _anth.AsyncAnthropic(api_key=chave)
            await c.messages.create(model="claude-haiku-4-5-20251001", max_tokens=1, messages=[{"role":"user","content":"ping"}])
        elif pid == "gemini":
            import google.generativeai as _gem
            _gem.configure(api_key=chave)
            m = _gem.GenerativeModel("gemini-2.0-flash")
            await asyncio.to_thread(m.generate_content, "ping")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "detalhe": str(e)[:120]}


class AdminStatusRequest(BaseModel):
    ativo: bool


@app.patch("/admin/api/provedores/{pid}/status")
def admin_status_provedor(pid: str, req: AdminStatusRequest, authorization: str | None = _Header(default=None)):
    _req_admin(authorization)
    if pid not in _PROVEDORES_CONF:
        raise HTTPException(status_code=404, detail="Provedor desconhecido.")
    # ativo=False → remove chave do env em memória sem apagar o arquivo
    # ativo=True → apenas confirma (a chave já precisa existir)
    env = _ler_env()
    chave = env.get(_PROVEDORES_CONF[pid]["env_key"], "")
    if req.ativo and not chave:
        raise HTTPException(status_code=400, detail="Configure a chave de API antes de ativar.")
    return {"ok": True}


class AdminPrincipalRequest(BaseModel):
    provedor: str


@app.post("/admin/api/principal")
def admin_definir_principal(req: AdminPrincipalRequest, authorization: str | None = _Header(default=None)):
    _req_admin(authorization)
    if req.provedor not in _PROVEDORES_CONF:
        raise HTTPException(status_code=404, detail="Provedor desconhecido.")
    _salvar_env_key("PROVEDOR_PREFERIDO", req.provedor)
    os.environ["PROVEDOR_PREFERIDO"] = req.provedor
    return {"ok": True}
