"""
Modelos Pydantic para todos os endpoints da API SALEIA.
Define estrutura de entrada e saída para validação automática com FastAPI.
"""

from typing import Optional
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# MODELOS DE ENTRADA
# ──────────────────────────────────────────────

class TranscricaoInput(BaseModel):
    """Entrada principal: transcrição completa + metadados da reunião."""
    transcricao: str = Field(..., description="Transcrição completa da reunião")
    titulo_reuniao: Optional[str] = Field(None, description="Título ou assunto da reunião")
    participantes: Optional[list[str]] = Field(default_factory=list, description="Nomes dos participantes")
    data_reuniao: Optional[str] = Field(None, description="Data/hora da reunião (ISO 8601)")


class TempoRealInput(BaseModel):
    """Entrada para análise em tempo real: fragmento parcial + contexto acumulado."""
    transcricao_parcial: str = Field(..., description="Fragmento mais recente da transcrição (últimos 60s)")
    historico: Optional[str] = Field(
        default="Início da conversa",
        description="Resumo do que foi discutido até agora"
    )
    perfil_disc_atual: Optional[str] = Field(
        default="Ainda não identificado",
        description="Perfil DISC identificado nas análises anteriores"
    )


class TactiqWebhookPayload(BaseModel):
    """Payload recebido automaticamente do Tactiq ao fim da reunião no Google Meet."""
    meeting_title: Optional[str] = Field(None, description="Título da reunião no Google Meet")
    participants: Optional[list[str]] = Field(default_factory=list, description="Lista de participantes")
    date: Optional[str] = Field(None, description="Data/hora da reunião")
    transcript: str = Field(..., description="Transcrição completa gerada pelo Tactiq")


# ──────────────────────────────────────────────
# MODELOS DE SAÍDA
# ──────────────────────────────────────────────

class ProdutoRecomendado(BaseModel):
    """Produto ideal baseado no perfil financeiro do cliente."""
    nome: str
    valor: str
    justificativa: str


class DiagnosticoFinanceiroOutput(BaseModel):
    """Resultado completo do diagnóstico financeiro extraído da transcrição."""
    faturamento_mensal: str
    ganho_mensal_clt: str
    capacidade_investimento: str
    tem_cartao_credito: Optional[bool]
    limite_cartao: str
    tem_estoque: Optional[bool]
    descricao_estoque: str
    perfil_financeiro: str  # micro | pequeno | medio
    produto_recomendado: ProdutoRecomendado
    estrategia_pagamento: str


class PerfilDiscObjecao(BaseModel):
    """Uma objeção prevista com resposta personalizada para o perfil DISC."""
    objecao: str
    resposta_ideal: str
    gatilho_emocional: str


class PerfilDiscOutput(BaseModel):
    """Resultado completo da análise DISC com estratégia de objeções."""
    perfil_primario: str  # D | I | S | C
    perfil_secundario: Optional[str]
    caracteristicas_identificadas: list[str]
    como_se_comunicar: str
    o_que_evitar: str
    top_3_objecoes_previstas: list[PerfilDiscObjecao]
    momento_ideal_fechamento: str
    frase_de_fechamento: str


class RelatorioCompletoOutput(BaseModel):
    """Relatório final completo gerado pelo agente SALEIA após a reunião."""
    relatorio_formatado: str = Field(..., description="Relatório completo em texto formatado")
    diagnostico_financeiro: dict = Field(..., description="Dados financeiros estruturados")
    perfil_disc: dict = Field(..., description="Perfil DISC e objeções estruturadas")
    titulo_reuniao: Optional[str] = None
    participantes: Optional[list[str]] = None
    data_reuniao: Optional[str] = None
