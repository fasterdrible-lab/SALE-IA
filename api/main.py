# Backend principal do SALEIA — Sistema de Automação de Leads, Engajamento e IA
# Desenvolvido com FastAPI + OpenAI GPT-4o

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List

# Importa os módulos de agentes de IA
from agent.diagnostico import gerar_diagnostico
from agent.suporte_venda import gerar_suporte_venda
from agent.recapitulacao import gerar_recapitulacao

# Inicializa a aplicação FastAPI
app = FastAPI(
    title="SALEIA API",
    description="Sistema de Automação de Leads, Engajamento e Inteligência Artificial em Atendimento de Vendas",
    version="1.0.0",
)


# ─── Modelos de entrada (validados pelo Pydantic) ────────────────────────────

class EntradaDiagnostico(BaseModel):
    """Dados do cliente para geração de diagnóstico pré-reunião."""
    nome: str
    segmento: str
    dores: List[str]
    objetivos: List[str]


class EntradaSuporteVenda(BaseModel):
    """Contexto da conversa em andamento para suporte em tempo real."""
    perfil_cliente: str
    fase: str
    ultima_fala: str
    historico: str


class EntradaRecapitulacao(BaseModel):
    """Transcrição da reunião para geração de recapitulação."""
    transcricao: str


# ─── Modelos de saída ────────────────────────────────────────────────────────

class RespostaDiagnostico(BaseModel):
    diagnostico: str


class RespostaSuporteVenda(BaseModel):
    proxima_fala: str
    gatilho_emocional: str
    objecao_e_resposta: str
    melhor_oferta: str


class RespostaRecapitulacao(BaseModel):
    recapitulacao: str


# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/", summary="Health check")
def health_check():
    """Verifica se o sistema está online."""
    return {"status": "SALEIA online"}


@app.post(
    "/diagnostico",
    response_model=RespostaDiagnostico,
    summary="Gera diagnóstico personalizado do cliente",
)
async def diagnostico(dados: EntradaDiagnostico):
    """
    Recebe dados do cliente e retorna um diagnóstico personalizado
    gerado pela OpenAI GPT-4o para preparar o vendedor antes da reunião.
    """
    try:
        resultado = await gerar_diagnostico(
            nome=dados.nome,
            segmento=dados.segmento,
            dores=dados.dores,
            objetivos=dados.objetivos,
        )
        return RespostaDiagnostico(diagnostico=resultado)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/suporte-venda",
    response_model=RespostaSuporteVenda,
    summary="Suporte em tempo real ao vendedor durante a conversa",
)
async def suporte_venda(dados: EntradaSuporteVenda):
    """
    Recebe o contexto da conversa em andamento e retorna sugestões imediatas:
    próxima fala, gatilho emocional identificado, resposta a objeções e melhor oferta.
    """
    try:
        resultado = await gerar_suporte_venda(
            perfil_cliente=dados.perfil_cliente,
            fase=dados.fase,
            ultima_fala=dados.ultima_fala,
            historico=dados.historico,
        )
        return RespostaSuporteVenda(**resultado)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/recapitulacao",
    response_model=RespostaRecapitulacao,
    summary="Gera recapitulação emocional e estratégica pós-reunião",
)
async def recapitulacao(dados: EntradaRecapitulacao):
    """
    Recebe a transcrição da reunião e retorna uma recapitulação completa:
    emocional, estratégica e próximos passos recomendados.
    """
    try:
        resultado = await gerar_recapitulacao(transcricao=dados.transcricao)
        return RespostaRecapitulacao(recapitulacao=resultado)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
