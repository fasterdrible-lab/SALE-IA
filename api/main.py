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
import html as html_module
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from openai import OpenAI

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

# Cliente OpenAI (inicializado de forma lazy para não falhar se a chave não estiver configurada)
_openai_client: Optional[OpenAI] = None


def get_openai_client() -> OpenAI:
    """Retorna o cliente OpenAI, inicializando-o na primeira chamada."""
    global _openai_client
    if _openai_client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail="OPENAI_API_KEY não configurada. Defina a variável de ambiente."
            )
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client

# Armazenamento em memória do último relatório (em produção, usar banco de dados)
ultimo_relatorio: dict = {}

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
    """Chama o GPT-4o e retorna o JSON da resposta."""
    try:
        openai_client = get_openai_client()
        resposta = openai_client.chat.completions.create(
            model=modelo,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        conteudo = resposta.choices[0].message.content
        return json.loads(conteudo)
    except json.JSONDecodeError as e:
        logger.error("Erro ao parsear resposta da IA: %s", e)
        raise HTTPException(status_code=500, detail="Erro ao processar resposta da IA. Tente novamente.")
    except Exception as e:
        logger.error("Erro ao chamar GPT-4o: %s", e)
        raise HTTPException(status_code=500, detail="Erro ao conectar com a IA. Verifique a chave OPENAI_API_KEY.")


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

@app.get("/health")
def health_check():
    """Verificação de saúde do serviço."""
    return {
        "status": "online",
        "servico": "SALEIA Backend",
        "versao": "1.0.0",
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/tempo-real")
def analisar_tempo_real(req: TempoRealRequest):
    """
    Análise em tempo real durante a reunião.
    Chamado pela extensão Chrome a cada 60 segundos.
    """
    if not req.transcricao_parcial and not req.historico:
        raise HTTPException(status_code=400, detail="Transcrição vazia — ative as legendas no Meet")

    conteudo_usuario = f"""
TRANSCRIÇÃO DOS ÚLTIMOS 2 MINUTOS:
{req.transcricao_parcial or '(sem transcrição recente)'}

HISTÓRICO (últimos 5 minutos):
{req.historico or '(início da reunião)'}

PERFIL DISC JÁ IDENTIFICADO: {req.perfil_disc_atual or 'ainda não identificado'}
"""

    resultado = chamar_gpt(PROMPT_TEMPO_REAL, conteudo_usuario)
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


@app.get("/relatorio", response_class=HTMLResponse)
def ver_relatorio():
    """
    Exibe o último relatório gerado em formato HTML legível.
    """
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
