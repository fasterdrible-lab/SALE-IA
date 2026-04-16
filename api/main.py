"""
API Principal do Agente SALEIA — FastAPI
Substitui 100% do trabalho manual do vendedor e fornece inteligência em tempo real.

Endpoints:
  GET  /                        — health check
  POST /webhook/tactiq          — recebe transcrição do Tactiq, processa tudo e retorna relatório
  POST /tempo-real              — análise em tempo real durante a reunião (a cada 60s)
  POST /diagnostico-financeiro  — extrai perfil financeiro da transcrição
  POST /perfil-disc             — identifica perfil DISC + objeções
  POST /recapitulacao-completa  — gera relatório completo pós-reunião
  POST /produto-recomendado     — retorna produto ideal com base no diagnóstico financeiro
"""

import asyncio
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.models import (
    DiagnosticoFinanceiroOutput,
    PerfilDiscOutput,
    RelatorioCompletoOutput,
    TactiqWebhookPayload,
    TempoRealInput,
    TranscricaoInput,
)
from agent.agente_tempo_real import analisar_fragmento
from agent.diagnostico_financeiro import extrair_diagnostico_financeiro
from agent.perfil_disc import identificar_perfil_disc
from agent.recapitulacao import gerar_recapitulacao_completa

# ──────────────────────────────────────────────
# Inicialização da aplicação
# ──────────────────────────────────────────────
app = FastAPI(
    title="SALEIA — Agente de Vendas com IA",
    description=(
        "Sistema de Automação de Leads, Engajamento e Inteligência Artificial em Atendimento. "
        "Substitui 100% do trabalho manual do vendedor com inteligência em tempo real."
    ),
    version="1.0.0",
)

# Permite requisições do frontend HTML (painel.html abre diretamente no navegador)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# Endpoint 1 — Health Check
# ──────────────────────────────────────────────
@app.get("/", tags=["Status"])
async def health_check():
    """Verifica se a API está no ar e com a chave OpenAI configurada."""
    chave_configurada = bool(os.environ.get("OPENAI_API_KEY"))
    return {
        "status": "online",
        "agente": "SALEIA v1.0",
        "openai_configurado": chave_configurada,
        "mensagem": "API do agente SALEIA está operacional." if chave_configurada
                    else "⚠️ OPENAI_API_KEY não configurada. Defina no arquivo .env",
    }


# ──────────────────────────────────────────────
# Endpoint 2 — Webhook Tactiq (integração automática)
# ──────────────────────────────────────────────
@app.post("/webhook/tactiq", response_model=RelatorioCompletoOutput, tags=["Automação"])
async def webhook_tactiq(payload: TactiqWebhookPayload):
    """
    Recebe automaticamente a transcrição do Tactiq ao fim da reunião no Google Meet.

    Processa em paralelo:
      1. Diagnóstico financeiro
      2. Perfil DISC + objeções
      3. Análise do agente em tempo real

    Em seguida gera o relatório completo combinando todos os resultados.
    Substitui completamente o processo manual de copiar/colar no Claude.
    """
    try:
        # Executa diagnóstico financeiro e perfil DISC em paralelo para máxima velocidade
        diagnostico, perfil = await asyncio.gather(
            extrair_diagnostico_financeiro(payload.transcript),
            identificar_perfil_disc(payload.transcript),
        )

        # Gera a recapitulação completa com base nos resultados anteriores
        relatorio = await gerar_recapitulacao_completa(
            transcricao=payload.transcript,
            diagnostico_financeiro=diagnostico,
            perfil_disc=perfil,
        )

        return RelatorioCompletoOutput(
            relatorio_formatado=relatorio,
            diagnostico_financeiro=diagnostico,
            perfil_disc=perfil,
            titulo_reuniao=payload.meeting_title,
            participantes=payload.participants,
            data_reuniao=payload.date,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar webhook Tactiq: {str(e)}")


# ──────────────────────────────────────────────
# Endpoint 3 — Análise em Tempo Real
# ──────────────────────────────────────────────
@app.post("/tempo-real", tags=["Tempo Real"])
async def analise_tempo_real(dados: TempoRealInput):
    """
    Recebe um fragmento da transcrição a cada ~60 segundos e retorna dicas ao vendedor.

    Analisa:
    - Sinais emocionais ocultos na fala do cliente
    - Perfil DISC em formação
    - Sinais financeiros (valores, cartão, salário, estoque)
    - Nível de empolgação do cliente
    - Janelas de fechamento detectadas
    - Objeções silenciosas
    - Próxima ação recomendada para os próximos 60 segundos
    """
    try:
        resultado = await analisar_fragmento(
            transcricao_parcial=dados.transcricao_parcial,
            historico=dados.historico or "Início da conversa",
            perfil_disc_atual=dados.perfil_disc_atual or "Ainda não identificado",
        )
        return resultado
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na análise em tempo real: {str(e)}")


# ──────────────────────────────────────────────
# Endpoint 4 — Diagnóstico Financeiro
# ──────────────────────────────────────────────
@app.post("/diagnostico-financeiro", tags=["Análise"])
async def diagnostico_financeiro(dados: TranscricaoInput):
    """
    Extrai automaticamente da transcrição todas as informações financeiras do cliente:
    faturamento, salário CLT, limite de cartão, estoque e recomenda o produto ideal.
    """
    try:
        resultado = await extrair_diagnostico_financeiro(dados.transcricao)
        return resultado
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no diagnóstico financeiro: {str(e)}")


# ──────────────────────────────────────────────
# Endpoint 5 — Perfil DISC + Objeções
# ──────────────────────────────────────────────
@app.post("/perfil-disc", tags=["Análise"])
async def perfil_disc(dados: TranscricaoInput):
    """
    Identifica o perfil DISC dominante do cliente e gera as top 3 objeções previstas
    com respostas personalizadas para o perfil identificado.
    """
    try:
        resultado = await identificar_perfil_disc(dados.transcricao)
        return resultado
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na análise DISC: {str(e)}")


# ──────────────────────────────────────────────
# Endpoint 6 — Recapitulação Completa
# ──────────────────────────────────────────────
@app.post("/recapitulacao-completa", response_model=RelatorioCompletoOutput, tags=["Relatório"])
async def recapitulacao_completa(dados: TranscricaoInput):
    """
    Gera o relatório completo da reunião.
    Substitui completamente o processo manual de copiar a transcrição do Tactiq e jogar no Claude.

    Processa em paralelo diagnóstico financeiro e perfil DISC,
    depois gera o relatório unificado.
    """
    try:
        # Processa diagnóstico financeiro e DISC em paralelo
        diagnostico, perfil = await asyncio.gather(
            extrair_diagnostico_financeiro(dados.transcricao),
            identificar_perfil_disc(dados.transcricao),
        )

        # Gera o relatório completo
        relatorio = await gerar_recapitulacao_completa(
            transcricao=dados.transcricao,
            diagnostico_financeiro=diagnostico,
            perfil_disc=perfil,
        )

        return RelatorioCompletoOutput(
            relatorio_formatado=relatorio,
            diagnostico_financeiro=diagnostico,
            perfil_disc=perfil,
            titulo_reuniao=dados.titulo_reuniao,
            participantes=dados.participantes,
            data_reuniao=dados.data_reuniao,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar recapitulação: {str(e)}")


# ──────────────────────────────────────────────
# Endpoint 7 — Produto Recomendado
# ──────────────────────────────────────────────
@app.post("/produto-recomendado", tags=["Análise"])
async def produto_recomendado(dados: TranscricaoInput):
    """
    Com base no diagnóstico financeiro da transcrição, retorna o produto ideal para o cliente.

    Tabela de produtos:
      - Produto Base:          R$ 3.000 – R$ 4.000  (fatura pouco / tem estoque)
      - Produto Intermediário: R$ 15.984,00
      - Produto Completo:      R$ 29.892,00
    """
    try:
        diagnostico = await extrair_diagnostico_financeiro(dados.transcricao)
        return {
            "produto_recomendado": diagnostico.get("produto_recomendado"),
            "perfil_financeiro": diagnostico.get("perfil_financeiro"),
            "estrategia_pagamento": diagnostico.get("estrategia_pagamento"),
            "capacidade_investimento": diagnostico.get("capacidade_investimento"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao recomendar produto: {str(e)}")
