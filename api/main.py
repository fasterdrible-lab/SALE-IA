"""
main.py — Backend SALEIA (FastAPI)

Endpoints:
  GET  /health           — verificação de status
  POST /tempo-real       — análise em tempo real durante reunião
  POST /recapitulacao    — recapitulação pós-reunião
  POST /webhook/tactiq   — webhook do Tactiq (transcrição automática)
"""

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from api.llm_router import chamar_llm

load_dotenv()

app = FastAPI(
    title="SALEIA — Sistema de Automação de Leads e Inteligência em Atendimento",
    version="1.0.0",
)

# Permite requisições da extensão Chrome (qualquer origem local)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Modelos de entrada ───────────────────────────────────────────────────────

class TempoRealInput(BaseModel):
    transcricao_parcial: str
    historico: str = ""
    perfil_disc_atual: str = ""
    llm_model: str = "gpt-4o"           # modelo escolhido pelo usuário
    llm_provider: str = "openai"         # openai | anthropic | google
    api_key_override: str = None         # chave enviada pela extensão (opcional)


class RecapitulacaoInput(BaseModel):
    transcricao_completa: str
    titulo_reuniao: str = ""
    llm_model: str = "gpt-4o"
    llm_provider: str = "openai"
    api_key_override: str = None


class TactiqWebhookPayload(BaseModel):
    meeting_title: str = ""
    participants: list = []
    date: str = ""
    transcript: str


# ─── Prompts de sistema ───────────────────────────────────────────────────────

PROMPT_TEMPO_REAL = """
Você é o SALEIA, um assistente de vendas em tempo real que analisa conversas e
ajuda o vendedor a fechar mais negócios.

Analise o trecho de transcrição abaixo e retorne um JSON com as seguintes chaves:
- "alerta_urgente": string ou null — alerta crítico que exige ação imediata
- "perfil_disc": string ("D", "I", "S" ou "C") — perfil DISC identificado
- "disc_confianca": int — % de confiança na identificação (0-100)
- "disc_evidencia": string — frase do cliente que evidencia o perfil
- "sinal_oculto": string — o que o cliente sinalizou sem perceber
- "proxima_acao": string — o que o vendedor deve falar nos próximos 60 segundos
- "sinal_financeiro": string ou null — menção a valores, limites ou estoque

Responda APENAS com o JSON, sem explicações adicionais.

HISTÓRICO ANTERIOR:
{historico}

PERFIL DISC JÁ IDENTIFICADO: {perfil_disc_atual}

TRECHO ATUAL:
{transcricao_parcial}
"""

PROMPT_RECAPITULACAO = """
Você é o SALEIA. Analise a transcrição completa da reunião de vendas e gere uma
recapitulação detalhada em português brasileiro.

Retorne um JSON com:
- "recapitulacao_emocional": string — o que o cliente sentiu/verbalizou
- "recapitulacao_estrategica": string — dores, objeções, interesses identificados
- "diagnostico_financeiro": objeto com:
    - "faturamento_estimado": string
    - "capacidade_investimento": string
    - "tem_cartao": bool ou null
    - "limite_cartao": string ou null
    - "renda_tipo": string ("CLT" | "autônomo" | "empresário" | null)
    - "tem_estoque": bool ou null
- "produto_recomendado": objeto com:
    - "nome": string
    - "valor": string
    - "justificativa": string
- "perfil_disc": string
- "top_3_objecoes": lista de objetos com "objecao" e "resposta_sugerida"
- "o_que_nao_percebi": lista de strings — insights ocultos
- "proximos_passos": lista de strings (ações para as próximas 24-48h)
- "resumo_executivo": string de 3 linhas

TABELA DE PRODUTOS:
- Produto Base: R$3.000 - R$4.000 (para clientes com baixa capacidade)
- Produto Intermediário: R$15.984,00
- Produto Completo: R$29.892,00

TRANSCRIÇÃO COMPLETA:
{transcricao_completa}
"""


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Verifica se o servidor está no ar."""
    return {"status": "ok", "servico": "SALEIA"}


@app.post("/tempo-real")
async def tempo_real(data: TempoRealInput):
    """
    Analisa um trecho de transcrição em tempo real e retorna dicas para o vendedor.
    Chamado pela extensão Chrome a cada 60 segundos durante a reunião.
    """
    prompt = PROMPT_TEMPO_REAL.format(
        historico=data.historico or "Nenhum histórico ainda.",
        perfil_disc_atual=data.perfil_disc_atual or "Não identificado",
        transcricao_parcial=data.transcricao_parcial,
    )

    try:
        resposta = await chamar_llm(
            prompt=prompt,
            model=data.llm_model,
            provider=data.llm_provider,
            api_key=data.api_key_override,
        )
        # Tenta parsear o JSON retornado pela IA
        import json
        return json.loads(resposta)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/recapitulacao")
async def recapitulacao(data: RecapitulacaoInput):
    """
    Gera a recapitulação completa pós-reunião.
    Pode ser chamado manualmente ou via webhook do Tactiq.
    """
    prompt = PROMPT_RECAPITULACAO.format(
        transcricao_completa=data.transcricao_completa,
    )

    try:
        resposta = await chamar_llm(
            prompt=prompt,
            model=data.llm_model,
            provider=data.llm_provider,
            api_key=data.api_key_override,
        )
        import json
        resultado = json.loads(resposta)
        resultado["titulo_reuniao"] = data.titulo_reuniao
        return resultado
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/tactiq")
async def webhook_tactiq(payload: TactiqWebhookPayload):
    """
    Recebe a transcrição completa do Tactiq via webhook ao fim da reunião.
    Processa automaticamente e gera a recapitulação.
    """
    # Usa o modelo padrão configurado no .env (ou gpt-4o)
    model = os.getenv("OPENAI_MODEL", "gpt-4o")

    prompt = PROMPT_RECAPITULACAO.format(
        transcricao_completa=payload.transcript,
    )

    try:
        resposta = await chamar_llm(
            prompt=prompt,
            model=model,
            provider="openai",
            api_key=None,
        )
        import json
        resultado = json.loads(resposta)
        resultado["titulo_reuniao"] = payload.meeting_title
        resultado["data_reuniao"] = payload.date
        resultado["participantes"] = payload.participants
        return {"status": "recapitulação gerada com sucesso", "relatorio": resultado}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
