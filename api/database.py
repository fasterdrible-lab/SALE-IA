"""
SALEIA — api/database.py
Camada de persistência com SQLModel.
Usa MySQL se as variáveis DB_* estiverem no .env, caso contrário SQLite local.
"""

import calendar
import json
import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

from dotenv import load_dotenv
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.engine import URL as SA_URL
from sqlalchemy.exc import OperationalError
from sqlmodel import Field, Session, SQLModel, create_engine, select

# TEXT do MySQL trunca em 64KB — texto extraído de um livro inteiro
# (ou o embedding de um item) estoura isso fácil. MEDIUMTEXT (até 16MB)
# só no MySQL; outros dialetos (SQLite em dev/teste) caem no TEXT comum,
# que lá não tem limite de tamanho de qualquer forma.
_LongText = Text().with_variant(MEDIUMTEXT, "mysql")

# Carrega .env do diretório raiz do projeto (sobe 2 níveis de api/)
load_dotenv(Path(__file__).parent.parent / ".env")
logger = logging.getLogger("saleia.db")
# Logger dedicado a mudancas de configuracao financeira (Cost Intelligence
# Fase 6) — filho de "saleia", herda o _JsonFormatter de api/main.py de
# graca. Permite `journalctl -u saleia | grep saleia.financeiro` sem
# precisar de acesso ao MySQL.
logger_financeiro = logging.getLogger("saleia.financeiro")


# ─────────────────────────────────────────────
# MODELO
# ─────────────────────────────────────────────
class Relatorio(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: str = Field(index=True)
    nome_reuniao: str = Field(default="Reunião de Vendas")
    criado_em: datetime = Field(default_factory=datetime.now)
    dados_json: str  # JSON serializado do relatório completo


class ClaudeConnection(SQLModel, table=True):
    """Conexao individual de um usuario com sua propria conta Claude (piloto).

    Uma linha por usuario (upsert). O token OAuth so e gravado criptografado
    (ver agent/claude_account.py) e nunca e devolvido pela API.
    """

    __tablename__ = "claude_connections"

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: str = Field(sa_column=Column(String(36), unique=True, index=True, nullable=False))
    status: str = Field(default="inativo", sa_column=Column(String(20), nullable=False))
    oauth_token_encrypted: Optional[str] = Field(default=None, sa_column=Column(Text))
    connected_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    last_used_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    updated_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))


class ClaudeMeetingAnalysis(SQLModel, table=True):
    """Analise de uma reuniao feita com a conta Claude individual do usuario (piloto).

    Cobre tanto o resultado (MeetingAnalysis) quanto o log de execucao
    (aiExecution) do spec do piloto — sao o mesmo registro.
    """

    __tablename__ = "claude_meeting_analyses"

    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: str = Field(sa_column=Column(String(200), index=True, nullable=False))
    usuario_id: str = Field(sa_column=Column(String(36), index=True, nullable=False))
    transcript_hash: str = Field(sa_column=Column(String(64), index=True, nullable=False))
    status: str = Field(default="pendente", sa_column=Column(String(20), nullable=False))
    result_json: Optional[str] = Field(default=None, sa_column=Column(Text))
    error_code: Optional[str] = Field(default=None, sa_column=Column(String(40)))
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    feedback_rating: Optional[str] = Field(default=None, sa_column=Column(String(20)))
    feedback_tags_json: Optional[str] = Field(default=None, sa_column=Column(Text))
    started_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))
    completed_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))


class MeetingMemory(SQLModel, table=True):
    """Memoria persistente da reuniao por meeting_id."""

    __tablename__ = "meeting_memory"

    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: str = Field(sa_column=Column(String(200), unique=True, index=True, nullable=False))
    opportunity_id: Optional[int] = Field(default=None, sa_column=Column(Integer, index=True))
    # Fase 18 / Tarefa 18.1 (Tenant/User Isolation) — dono da reunião,
    # carimbado uma única vez na primeira gravação com usuário logado
    # (nunca sobrescrito depois). Nullable de propósito: reuniões
    # criadas anonimamente (extensão sem login, V.1.4.49) ou anteriores
    # a esta versão nunca tiveram dono e continuam acessíveis a
    # qualquer usuário autenticado — só reuniões NOVAS com dono
    # registrado passam a ser isoladas. Ver `_verificar_dono_ou_admin()`
    # em api/main.py.
    usuario_id: Optional[str] = Field(default=None, sa_column=Column(String(36), index=True))
    transcript_full: str = Field(default="", sa_column=Column(_LongText, nullable=False))
    transcript_buffer: str = Field(default="", sa_column=Column(_LongText, nullable=False))
    accumulated_summary: str = Field(default="", sa_column=Column(_LongText, nullable=False))
    current_diagnosis: str = Field(default="", sa_column=Column(_LongText, nullable=False))
    # Mesmo fix ja aplicado 2x neste projeto (V.1.4.54, V.1.4.100): TEXT do
    # MySQL trunca em 64KB. Achado real em producao (18/09/2026) — uma
    # reuniao longa estourou key_moments_json ("Data too long for column
    # 'key_moments_json'"); score_history_json/events_json crescem pelo
    # mesmo mecanismo (acumulam 1 entrada por analise da reuniao) e nunca
    # tinham recebido o fix, so descobertos junto nesta rodada.
    score_history_json: str = Field(default="[]", sa_column=Column(_LongText, nullable=False))
    key_moments_json: str = Field(default="[]", sa_column=Column(_LongText, nullable=False))
    events_json: str = Field(default="[]", sa_column=Column(_LongText, nullable=False))
    last_ai_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    last_recap_trigger_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    provider_cost_estimate: float = Field(default=0.0, sa_column=Column(Float, nullable=False))
    created_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))
    updated_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))


class TranscricaoAudioRecente(SQLModel, table=True):
    """Texto que o servidor transcreveu do áudio de uma reunião (auditoria
    T01, P8). A mesma fala volta pela extensão no /tempo-real com rótulo de
    falante; só contra estes corpos a deduplicação por similaridade vale —
    duas pessoas dizendo quase a mesma coisa nunca são juntadas."""

    __tablename__ = "transcricoes_audio_recentes"

    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: str = Field(sa_column=Column(String(200), index=True, nullable=False))
    corpo: str = Field(sa_column=Column(Text, nullable=False))  # corpo_normalizado
    criado_em: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, index=True, nullable=False))


class GravacaoAudio(SQLModel, table=True):
    """Uma gravação contínua de uma trilha (T02, `agent/gravacao_rules.py`).
    A reunião tem várias: uma por trilha a cada rotação/pausa."""

    __tablename__ = "gravacoes_audio"

    id: Optional[int] = Field(default=None, primary_key=True)
    recording_id: str = Field(sa_column=Column(String(64), unique=True, index=True, nullable=False))
    meeting_id: str = Field(sa_column=Column(String(200), index=True, nullable=False))
    track_id: str = Field(sa_column=Column(String(20), nullable=False))
    usuario_id: str = Field(sa_column=Column(String(36), index=True, nullable=False))
    codec: str = Field(default="", sa_column=Column(String(80), nullable=False))
    sample_rate: Optional[int] = Field(default=None, sa_column=Column(Integer))
    consentimento_texto: str = Field(sa_column=Column(Text, nullable=False))
    consentimento_em: datetime = Field(sa_column=Column(DateTime, nullable=False))
    iniciada_em: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))
    encerrada_em: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    # gravando | encerrada | apagada
    status: str = Field(default="gravando", sa_column=Column(String(20), nullable=False))
    ultima_sequence_declarada: Optional[int] = Field(default=None, sa_column=Column(Integer))
    lacunas_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    # pendente | ok | erro
    integridade: str = Field(default="pendente", sa_column=Column(String(20), nullable=False))
    integridade_detalhe: str = Field(default="", sa_column=Column(Text, nullable=False))
    duracao_s: Optional[float] = Field(default=None, sa_column=Column(Float))
    apagar_em: datetime = Field(sa_column=Column(DateTime, index=True, nullable=False))


class GravacaoBloco(SQLModel, table=True):
    """Um bloco de áudio. Unicidade (recording_id, sequence): o reenvio
    do mesmo bloco não duplica e 2 workers não gravam versões diferentes."""

    __tablename__ = "gravacoes_blocos"
    __table_args__ = (UniqueConstraint("recording_id", "sequence", name="uq_gravacao_bloco_seq"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    recording_id: str = Field(sa_column=Column(String(64), index=True, nullable=False))
    sequence: int = Field(sa_column=Column(Integer, nullable=False))
    start_ms: int = Field(sa_column=Column(BigInteger, nullable=False))
    end_ms: int = Field(sa_column=Column(BigInteger, nullable=False))
    content_hash: str = Field(sa_column=Column(String(64), nullable=False))
    tamanho: int = Field(sa_column=Column(Integer, nullable=False))
    caminho: str = Field(sa_column=Column(String(400), nullable=False))
    recorded_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    recebido_em: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))


class GravacaoNivel(SQLModel, table=True):
    """Volume (dBFS) por janela de uma gravação encerrada — painel de
    gravações do Dashboard. Calculado uma vez decodificando o áudio."""

    __tablename__ = "gravacoes_niveis"

    id: Optional[int] = Field(default=None, primary_key=True)
    recording_id: str = Field(sa_column=Column(String(64), unique=True, index=True, nullable=False))
    janela_s: float = Field(sa_column=Column(Float, nullable=False))
    duracao_s: Optional[float] = Field(default=None, sa_column=Column(Float))
    niveis_json: str = Field(sa_column=Column(Text, nullable=False))
    calculado_em: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))


class GravacaoReferencia(SQLModel, table=True):
    """Trecho de referência (fase 2 do painel de gravações): o que foi dito
    de verdade × o que o sistema transcreveu, com o WER do trecho.
    `sessao_id` = recording_id da 1ª gravação da sessão."""

    __tablename__ = "gravacoes_referencias"

    id: Optional[int] = Field(default=None, primary_key=True)
    sessao_id: str = Field(sa_column=Column(String(64), index=True, nullable=False))
    meeting_id: str = Field(sa_column=Column(String(200), index=True, nullable=False))
    usuario_id: str = Field(sa_column=Column(String(36), index=True, nullable=False))
    trilha: str = Field(sa_column=Column(String(20), nullable=False))
    inicio_s: float = Field(sa_column=Column(Float, nullable=False))
    fim_s: float = Field(sa_column=Column(Float, nullable=False))
    texto_sistema: str = Field(default="", sa_column=Column(Text, nullable=False))
    texto_referencia: str = Field(sa_column=Column(Text, nullable=False))
    wer: Optional[float] = Field(default=None, sa_column=Column(Float))
    erros: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    substituicoes: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    delecoes: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    insercoes: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    palavras_referencia: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    observacao: str = Field(default="", sa_column=Column(Text, nullable=False))
    criado_em: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))
    atualizado_em: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))


class AiUsageEvent(SQLModel, table=True):
    """Evento de uso de IA — um registro por chamada a chamar_ia()/fallback
    Claude Account (Cost Intelligence Fase 1).

    Escrita e sempre melhor esforco: ver registrar_evento_uso_ia() — nunca
    deve derrubar o fluxo de vendas por falha aqui.
    """

    __tablename__ = "ai_usage_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    criado_em: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False, index=True))
    meeting_id: Optional[str] = Field(default=None, sa_column=Column(String(200), index=True))
    usuario_id: Optional[str] = Field(default=None, sa_column=Column(String(36), index=True))
    feature: str = Field(default="unspecified", sa_column=Column(String(80), index=True, nullable=False))
    provider: str = Field(sa_column=Column(String(40), index=True, nullable=False))
    model: Optional[str] = Field(default=None, sa_column=Column(String(120)))
    input_tokens: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    output_tokens: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    cached_input_tokens: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    usage_source: str = Field(default="estimated", sa_column=Column(String(20), nullable=False))
    cost_usd: float = Field(default=0.0, sa_column=Column(Float, nullable=False))
    latency_ms: Optional[int] = Field(default=None, sa_column=Column(Integer))
    success: bool = Field(default=True, sa_column=Column(Boolean, nullable=False))
    fallback_used: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    request_id: Optional[str] = Field(default=None, sa_column=Column(String(40), index=True))
    error_message: Optional[str] = Field(default=None, sa_column=Column(String(240)))


class OrcamentoIA(SQLModel, table=True):
    """Limite de gasto mensal de IA configurado pelo admin (Cost
    Intelligence Fase 3, Budget Guard). Linha unica (id=1, upsert) —
    limite_mensal_usd None/<=0 significa orcamento desativado (sem
    alerta), nunca um valor inventado."""

    __tablename__ = "orcamento_ia"

    id: Optional[int] = Field(default=None, primary_key=True)
    limite_mensal_usd: Optional[float] = Field(default=None, sa_column=Column(Float))
    atualizado_em: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))
    atualizado_por_id: Optional[str] = Field(default=None, sa_column=Column(String(36)))
    atualizado_por_email: Optional[str] = Field(default=None, sa_column=Column(String(200)))


class PlanoPreco(SQLModel, table=True):
    """Preco mensal (BRL) de cada plano de usuario (free/pro/enterprise),
    para calculo de margem por plano (Cost Intelligence Fase 3). So existe
    linha para planos com preco de fato configurado pelo admin — planos
    sem linha aqui ficam sem margem calculada (nunca um preco inventado)."""

    __tablename__ = "planos_preco"

    id: Optional[int] = Field(default=None, primary_key=True)
    plano: str = Field(sa_column=Column(String(50), unique=True, nullable=False))
    preco_mensal_brl: float = Field(sa_column=Column(Float, nullable=False))
    atualizado_em: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))
    atualizado_por_id: Optional[str] = Field(default=None, sa_column=Column(String(36)))
    atualizado_por_email: Optional[str] = Field(default=None, sa_column=Column(String(200)))


class AuditoriaFinanceira(SQLModel, table=True):
    """Registro de toda mudanca em configuracao financeira (orcamento,
    preco de plano) — Cost Intelligence Fase 3. Nao audita eventos de
    custo de IA (isso ja e o proprio ai_usage_events), so mudancas de
    configuracao feitas por um admin."""

    __tablename__ = "auditoria_financeira"

    id: Optional[int] = Field(default=None, primary_key=True)
    criado_em: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False, index=True))
    usuario_id: Optional[str] = Field(default=None, sa_column=Column(String(36)))
    usuario_email: Optional[str] = Field(default=None, sa_column=Column(String(200)))
    tipo: str = Field(sa_column=Column(String(40), index=True, nullable=False))
    campo: str = Field(sa_column=Column(String(80), nullable=False))
    valor_anterior: Optional[str] = Field(default=None, sa_column=Column(String(200)))
    valor_novo: Optional[str] = Field(default=None, sa_column=Column(String(200)))


class RouterDecisao(SQLModel, table=True):
    """Comparacao shadow-mode: o que o Cost Router recomendaria vs o que
    realmente foi usado numa chamada de IA (Cost Intelligence Fase 4).
    Nunca influencia a chamada real — so registro para analise posterior."""

    __tablename__ = "router_decisoes"

    id: Optional[int] = Field(default=None, primary_key=True)
    criado_em: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False, index=True))
    feature: str = Field(sa_column=Column(String(80), index=True, nullable=False))
    complexidade: str = Field(sa_column=Column(String(20), nullable=False))
    modo: str = Field(sa_column=Column(String(20), nullable=False))
    provider: str = Field(sa_column=Column(String(40), index=True, nullable=False))
    model_real: str = Field(sa_column=Column(String(120), nullable=False))
    custo_real_usd: float = Field(sa_column=Column(Float, nullable=False))
    model_recomendado: str = Field(sa_column=Column(String(120), nullable=False))
    custo_recomendado_usd: float = Field(sa_column=Column(Float, nullable=False))
    concordou: bool = Field(sa_column=Column(Boolean, nullable=False))


class OtimizacaoDecisao(SQLModel, table=True):
    """Comparacao shadow-mode de otimizacao de custo (Cost Intelligence
    Fase 5): o que uma otimizacao (cache de resposta, corte de contexto,
    bloqueio de loop caro por reuniao) teria feito numa chamada de IA
    real ja concluida. Nunca influencia a chamada real — so registro
    para analise posterior. `tipo` distingue as 3 otimizacoes:
    cache_hit | contexto_truncado | loop_bloqueado."""

    __tablename__ = "otimizacao_decisoes"

    id: Optional[int] = Field(default=None, primary_key=True)
    criado_em: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False, index=True))
    tipo: str = Field(sa_column=Column(String(30), index=True, nullable=False))
    feature: str = Field(sa_column=Column(String(80), index=True, nullable=False))
    meeting_id: Optional[str] = Field(default=None, sa_column=Column(String(200), index=True))
    prompt_hash: str = Field(sa_column=Column(String(12), nullable=False))
    custo_real_usd: float = Field(sa_column=Column(Float, nullable=False))
    economia_estimada_usd: float = Field(sa_column=Column(Float, nullable=False))
    detalhe: Optional[str] = Field(default=None, sa_column=Column(String(240)))


class KnowledgeSource(SQLModel, table=True):
    """Fonte de conhecimento comercial (livro, playbook, manual, etc.) para
    o Knowledge Compiler / "Biblioteca de Inteligencia". Fase 1: so guarda
    metadados + texto extraido deterministicamente (sem IA ainda — a
    estruturacao em KnowledgeItems e a Fase 2).

    Sem organization_id: decisao deliberada (mesma da V.1.4.40) — SALEIA e
    uso interno de uma unica empresa, multi-tenancy nao se aplica hoje.
    """

    __tablename__ = "knowledge_sources"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(sa_column=Column(String(255), nullable=False))
    author: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    source_type: str = Field(default="OTHER", sa_column=Column(String(30), nullable=False))
    original_filename: str = Field(sa_column=Column(String(255), nullable=False))
    mime_type: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    arquivo_path: str = Field(sa_column=Column(String(500), nullable=False))
    arquivo_tamanho: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    content_hash: str = Field(sa_column=Column(String(64), unique=True, index=True, nullable=False))
    status: str = Field(default="UPLOADED", sa_column=Column(String(20), nullable=False))
    texto_extraido: Optional[str] = Field(default=None, sa_column=Column(_LongText))
    sections_json: Optional[str] = Field(default=None, sa_column=Column(_LongText))
    char_count: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    section_count: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    error_message: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    created_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))
    updated_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))
    processed_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))


class KnowledgeItem(SQLModel, table=True):
    """Item de conhecimento comercial estruturado (framework, objecao,
    script, etc.) extraido via IA de uma secao de um KnowledgeSource
    (Knowledge Compiler Fase 2). Todo item nasce DRAFT — so entra em
    qualquer fase futura de RAG apos aprovacao humana (status=APPROVED).

    SQLModel (nao raw-pymysql como sales_memories/skills) por decisao
    deliberada: precisa ser testavel com SQLite em memoria para cobrir a
    logica de deduplicacao por similaridade, o coracao desta fase.
    """

    __tablename__ = "knowledge_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: int = Field(sa_column=Column(Integer, index=True, nullable=False))
    item_type: str = Field(sa_column=Column(String(30), index=True, nullable=False))
    title: str = Field(sa_column=Column(String(255), nullable=False))
    content: str = Field(sa_column=Column(_LongText, nullable=False))
    metadata_json: Optional[str] = Field(default=None, sa_column=Column(_LongText))
    tags_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    confidence: float = Field(default=0.75, sa_column=Column(Float, nullable=False))
    status: str = Field(default="DRAFT", sa_column=Column(String(20), index=True, nullable=False))
    possivel_duplicado_de: Optional[int] = Field(default=None, sa_column=Column(Integer))
    embedding_json: Optional[str] = Field(default=None, sa_column=Column(_LongText))
    embedding_provider: Optional[str] = Field(default=None, sa_column=Column(String(20)))
    embedding_model: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    embedding_dim: Optional[int] = Field(default=None, sa_column=Column(Integer))
    created_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))
    updated_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))


class SalesEvent(SQLModel, table=True):
    """Evento estruturado do modelo canônico da venda ("PROMPT MESTRE —
    SALE-IA V2", Fase 1 / Tarefa 1.1) — toda informação comercial
    relevante extraída de uma reunião (ou registrada manualmente) vira um
    SalesEvent, em vez de ficar só dentro do texto livre do relatório.

    opportunity_id fica solto (sem FK) de propósito: `Opportunity` só
    nasce na Fase 2 (Opportunity Memory) do mesmo roadmap, ainda não
    implementada — a coluna já existe aqui para não exigir migração
    quando a Fase 2 chegar.

    Validação (event_type/confidence/evidence_quote) mora em
    `agent/sales_event_rules.py::validar_sales_event`, aplicada por
    `criar_sales_event()` abaixo — diferente de AiUsageEvent/KnowledgeItem
    (escrita "melhor esforço"), SalesEvent é dado de domínio: entrada
    inválida levanta ValueError, nunca é descartada silenciosamente.
    """

    __tablename__ = "sales_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: str = Field(sa_column=Column(String(200), index=True, nullable=False))
    opportunity_id: Optional[int] = Field(default=None, sa_column=Column(Integer, index=True))
    client_id: Optional[str] = Field(default=None, sa_column=Column(String(36), index=True))
    seller_id: Optional[str] = Field(default=None, sa_column=Column(String(36), index=True))
    event_type: str = Field(sa_column=Column(String(40), index=True, nullable=False))
    timestamp: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))
    speaker: Optional[str] = Field(default=None, sa_column=Column(String(20)))
    evidence_quote: Optional[str] = Field(default=None, sa_column=Column(Text))
    source: str = Field(default="conversation", sa_column=Column(String(20), nullable=False))
    confidence: float = Field(default=1.0, sa_column=Column(Float, nullable=False))
    metadata_json: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))


class SalesEvidence(SQLModel, table=True):
    """Evidência bruta que sustenta uma interpretação/hipótese ("PROMPT
    MESTRE — SALE-IA V2", Fase 1 / Tarefa 1.2) — separa interpretação de
    evidência: `type` é o rótulo da hipótese (ex.: "ADOPTION_RISK"),
    `quote` é a fala real do cliente/vendedor que a sustenta. Nunca salvar
    só a interpretação ("cliente está inseguro") sem a fala que a gerou.

    Schema literal do prompt mestre (id/type/quote/speaker/timestamp/
    meeting_id/confidence/source) — sem FK para SalesEvent de propósito,
    mesma disciplina de escopo da Tarefa 1.1 (só o schema pedido).

    Validação (`quote` nunca vazia, `confidence` em [0,1]) mora em
    `agent/sales_evidence_rules.py::validar_sales_evidence`, aplicada por
    `criar_sales_evidence()` abaixo — mesma convenção da Tarefa 1.1:
    dado de domínio, entrada inválida levanta ValueError.
    """

    __tablename__ = "sales_evidences"

    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: str = Field(sa_column=Column(String(200), index=True, nullable=False))
    type: str = Field(sa_column=Column(String(60), index=True, nullable=False))
    quote: str = Field(sa_column=Column(Text, nullable=False))
    speaker: Optional[str] = Field(default=None, sa_column=Column(String(20)))
    timestamp: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))
    confidence: float = Field(default=1.0, sa_column=Column(Float, nullable=False))
    source: str = Field(default="conversation", sa_column=Column(String(20), nullable=False))
    created_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))


class Opportunity(SQLModel, table=True):
    """Oportunidade comercial ("PROMPT MESTRE — SALE-IA V2", Fase 2 /
    Tarefa 2.1) — entidade superior a `MeetingMemory`: uma oportunidade
    pode ter várias reuniões (via `MeetingMemory.opportunity_id`, ver
    acima), e-mails, follow-ups e propostas, todas contribuindo
    conhecimento para a mesma `OpportunityMemory` abaixo.

    Schema literal do prompt mestre. `stage` fica livre (string, sem
    enum) — o prompt mestre não define um vocabulário fechado de
    estágios de pipeline aqui (diferente do `conversation_stage` SPIN já
    existente em `processador_tempo_real.py`, que é por-reunião, não
    por-oportunidade); inventar uma taxonomia não pedida seria escopo
    fora da Tarefa 2.1. `status` é validado (`open`/`won`/`lost`/
    `abandoned`, o último adicionado na Fase 8 / Tarefa 8.1 — Outcome
    Tracking) em `agent/opportunity_memory_rules.py`.

    Colunas de desfecho (Fase 8 / Tarefa 8.1, aditivas): `outcome_value`/
    `product`/`close_date`/`cycle_days` para WON, `competitor` para
    LOST — `reason`/`stage`/`lost_at` do schema do prompt mestre
    reaproveitam `loss_reason`/`stage`/`lost_at` já existentes, nunca
    duplicados. Validação em `agent/outcome_rules.py`.
    """

    __tablename__ = "opportunities"

    id: Optional[int] = Field(default=None, primary_key=True)
    client_id: str = Field(sa_column=Column(String(36), index=True, nullable=False))
    seller_id: str = Field(sa_column=Column(String(36), index=True, nullable=False))
    created_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))
    updated_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))
    stage: str = Field(default="", sa_column=Column(String(60), nullable=False))
    status: str = Field(default="open", sa_column=Column(String(20), index=True, nullable=False))
    estimated_value: Optional[float] = Field(default=None, sa_column=Column(Float))
    won_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    lost_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    loss_reason: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    outcome_value: Optional[float] = Field(default=None, sa_column=Column(Float))
    product: Optional[str] = Field(default=None, sa_column=Column(String(200)))
    close_date: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    cycle_days: Optional[int] = Field(default=None, sa_column=Column(Integer))
    competitor: Optional[str] = Field(default=None, sa_column=Column(String(200)))


class OpportunityStageHistory(SQLModel, table=True):
    """Histórico de estágio de uma Opportunity (Tarefa B2 de
    docs/tasks-prompt-mestre-v2-restante.md). `Opportunity.stage` só
    guarda o valor atual; sem o histórico não dá para saber se a venda
    avançou entre a reunião de uma recomendação e a seguinte
    (`stage_advanced`, Fase 10.3). Uma linha por estágio assumido, com o
    momento em que passou a valer — append-only, nunca editada.

    Gravado por `criar_opportunity()` (estágio inicial) e
    `atualizar_stage_opportunity()` (só quando o valor muda). Oportunidade
    anterior à B2 ganha a linha do estágio original (com `created_at` da
    oportunidade) na primeira mudança."""

    __tablename__ = "opportunity_stage_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    opportunity_id: int = Field(sa_column=Column(Integer, index=True, nullable=False))
    stage: str = Field(default="", sa_column=Column(String(60), nullable=False))
    changed_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))


class OpportunityMemory(SQLModel, table=True):
    """Conhecimento agregado de uma Opportunity ao longo de várias
    reuniões ("PROMPT MESTRE — SALE-IA V2", Fase 2 / Tarefa 2.1) — 1
    registro por `opportunity_id` (1:1, mesmo padrão de `MeetingMemory`
    por `meeting_id`).

    Cada uma das 13 categorias do prompt mestre (`pain_points` a
    `unknowns`) é uma lista JSON **append-only** de "insights"
    (`{id, meeting_id, campo, valor, evidence, confidence, timestamp,
    contradiz}` — ver `agent/opportunity_memory_rules.py::
    adicionar_insight`). Nunca sobrescreve nem remove uma entrada
    anterior — regra explícita do prompt mestre ("informações históricas
    não desaparecem; contradições são registradas e não silenciosamente
    sobrescritas"): quando um novo valor para o mesmo `campo` diverge do
    valor mais recente já registrado, a entrada nova aponta `contradiz`
    para a entrada anterior, e AMBAS permanecem na lista.
    """

    __tablename__ = "opportunity_memories"

    id: Optional[int] = Field(default=None, primary_key=True)
    opportunity_id: int = Field(sa_column=Column(Integer, unique=True, index=True, nullable=False))
    pain_points_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    business_impact_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    goals_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    objections_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    competitors_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    decision_process_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    stakeholders_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    champion_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    economic_buyer_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    metrics_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    next_steps_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    risks_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    unknowns_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))
    updated_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))


class OpportunityGraphEdge(SQLModel, table=True):
    """Aresta do Opportunity Graph ("PROMPT MESTRE — SALE-IA V2", Fase 2
    / Tarefa 2.2) — relaciona nós do tipo CLIENT/PAIN/IMPACT/GOAL/
    OBJECTION/STAKEHOLDER/COMPETITOR/DECISION/NEXT_STEP dentro de uma
    mesma Opportunity.

    Diferente do `agent/knowledge_graph.py::graph_edges` já existente no
    projeto (Sales Brain Fase 7.2) — aquele conecta entidades de CRUD já
    persistidas (cliente/reunião/memória/playbook/skill) por
    `relacao`+`created_at`, sem evidência nem confiança por aresta, e é
    raw-pymysql (não testável com SQLite). Este é um grafo diferente,
    escopado por `opportunity_id`: relaciona **insights qualitativos**
    já registrados em `OpportunityMemory` (Tarefa 2.1) — os nós PAIN/
    IMPACT/GOAL/... referenciam o `id` do insight dentro da categoria
    correspondente (`from_id`/`to_id` como string), nunca duplicando o
    dado real. Só o nó CLIENT referencia `client_id` diretamente.

    Schema literal do prompt mestre para a aresta (`source`, `evidence`,
    `confidence`, `timestamp`) — `evidence` nunca vazia, mesma regra de
    `SalesEvidence` (Tarefa 1.2): "sem perder a origem". Validação em
    `agent/opportunity_graph_rules.py::validar_aresta`.
    """

    __tablename__ = "opportunity_graph_edges"

    id: Optional[int] = Field(default=None, primary_key=True)
    opportunity_id: int = Field(sa_column=Column(Integer, index=True, nullable=False))
    from_type: str = Field(sa_column=Column(String(20), index=True, nullable=False))
    from_id: str = Field(sa_column=Column(String(100), index=True, nullable=False))
    to_type: str = Field(sa_column=Column(String(20), index=True, nullable=False))
    to_id: str = Field(sa_column=Column(String(100), index=True, nullable=False))
    relation: str = Field(sa_column=Column(String(50), nullable=False))
    source: str = Field(default="conversation", sa_column=Column(String(20), nullable=False))
    evidence: str = Field(sa_column=Column(Text, nullable=False))
    confidence: float = Field(default=1.0, sa_column=Column(Float, nullable=False))
    timestamp: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))
    created_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))


class SellerDnaObservacao(SQLModel, table=True):
    """Observação individual de estilo do vendedor ("PROMPT MESTRE —
    SALE-IA V2", Fase 15 / plano de fechamento do SalesReasoningEngine,
    Bloco 5 / Tarefa 5.1, `docs/tasks-sales-reasoning-engine-completo.md`)
    — 1 linha por observação extraída de 1 reunião encerrada, nunca o
    perfil agregado (isso é `agent/seller_dna_rules.py::
    construir_seller_dna()`, que nunca lê banco).

    `campo` é validado pelo chamador contra `agent/seller_dna_rules.py::
    SELLER_DNA_CAMPOS` (vocabulário fechado dos 12 campos literais) —
    nunca travado por constraint de banco, mesmo padrão de `Opportunity
    Memory`/`OpportunityGraphEdge` (validação sempre na camada de
    domínio, nunca no schema SQL). `evidence_quote` é sempre uma
    citação real do vendedor (guarda aplicada em `agent/seller_dna_
    extractor.py` antes de persistir) — nunca uma observação sem
    lastro na conversa, mesma disciplina de `SalesEvidence`/`SPIN`/
    `MEDDPICC`.
    """

    __tablename__ = "seller_dna_observacoes"

    id: Optional[int] = Field(default=None, primary_key=True)
    seller_id: str = Field(sa_column=Column(String(36), index=True, nullable=False))
    meeting_id: str = Field(sa_column=Column(String(100), index=True, nullable=False))
    campo: str = Field(sa_column=Column(String(30), nullable=False))
    valor: str = Field(sa_column=Column(Text, nullable=False))
    evidence_quote: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))


class RecommendationEvent(SQLModel, table=True):
    """Recomendação mostrada ao vendedor ("PROMPT MESTRE — SALE-IA V2",
    Fase 10 / Tarefa 10.1) — schema literal do prompt mestre. Base para
    a Tarefa 10.2 (detectar se o vendedor usou a recomendação — estados
    USED/PARTIALLY_USED/IGNORED/UNKNOWN, não construída nesta rodada) e
    10.3 (efetividade real: recomendação → uso → reação → avanço de
    estágio → resultado da oportunidade, também não construída).

    `opportunity_id` fica solto (sem FK), mesmo padrão de `SalesEvent`
    (Fase 1) — uma recomendação pode acontecer antes da oportunidade
    estar formalmente vinculada à reunião. `used_at`/`seller_action`
    nascem sempre `None`; só `registrar_uso_recommendation_event()`
    (abaixo) os preenche, e nunca sobrescreve um valor já gravado —
    mesmo padrão de `won_at`/`lost_at` em `Opportunity` (Fase 2/8).

    Dado de domínio: validação em
    `agent/recommendation_rules.py::validar_recommendation_event`,
    `criar_recommendation_event()` propaga `ValueError` em dado
    inválido, nunca falha silenciosamente como `AiUsageEvent`/
    `KnowledgeItem`.
    """

    __tablename__ = "recommendation_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: str = Field(sa_column=Column(String(200), index=True, nullable=False))
    opportunity_id: Optional[int] = Field(default=None, sa_column=Column(Integer, index=True))
    strategy: str = Field(sa_column=Column(String(120), nullable=False))
    recommendation: str = Field(sa_column=Column(Text, nullable=False))
    reason: str = Field(sa_column=Column(Text, nullable=False))
    shown_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))
    used_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    seller_action: Optional[str] = Field(default=None, sa_column=Column(Text))
    outcome_window: Optional[str] = Field(default=None, sa_column=Column(String(60)))
    created_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))
    # Tarefa D6 (seção 34, "qual versão recomendou isso"): nullable,
    # migradas no startup por `migrar_colunas_versionamento()`.
    reasoning_engine_version: Optional[str] = Field(default=None, sa_column=Column(String(80)))
    policy_version: Optional[str] = Field(default=None, sa_column=Column(String(80)))
    knowledge_version: Optional[str] = Field(default=None, sa_column=Column(String(80)))
    model_version: Optional[str] = Field(default=None, sa_column=Column(String(80)))


# ─────────────────────────────────────────────
# ENGINE — MySQL ou SQLite
# ─────────────────────────────────────────────
def _build_engine():
    host = os.getenv("DB_HOST", "")
    port = os.getenv("DB_PORT", "3306")
    user = os.getenv("DB_USER", "")
    passwd = os.getenv("DB_PASS", "")
    name = os.getenv("DB_NAME", "")

    if host and user and passwd and name:
        # MySQL — usa URL.create() para escapar corretamente @, # e outros caracteres especiais na senha
        url = SA_URL.create(
            "mysql+pymysql",
            username=user,
            password=passwd,
            host=host,
            port=int(port),
            database=name,
            query={"charset": "utf8mb4"},
        )
        logger.info("🗄️  Banco: MySQL em %s:%s/%s", host, port, name)
        return create_engine(url, echo=False, pool_pre_ping=True)

    # Fallback SQLite local
    db_path = Path("data/saleia.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("🗄️  Banco: SQLite em %s", db_path)
    return create_engine(f"sqlite:///{db_path}", echo=False)


def _build_engine_safe():
    """Tenta MySQL; se falhar conectar, cai no SQLite sem derrubar a aplicação."""
    eng = _build_engine()
    # Testa conexão imediatamente para detectar falha cedo e acionar fallback
    try:
        with eng.connect():
            pass
        return eng
    except Exception as exc:
        logger.warning("⚠️  MySQL indisponível (%s) — usando SQLite local.", exc)
        try:
            from agent.alertas import alertar
            alertar(
                f"🗄️ MySQL indisponível — fallback para SQLite ativo.\n`{str(exc)[:200]}`",
                nivel="🔴",
            )
        except Exception:
            pass
        db_path = Path("data/saleia.db")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return create_engine(f"sqlite:///{db_path}", echo=False)


engine = _build_engine_safe()


_TRANSCRIPT_BUFFER_SEPARATOR = "\n\n---\n\n"
_TRANSCRIPT_BUFFER_MAX_CHARS = int(os.getenv("SALEIA_MEMORY_BUFFER_MAX_CHARS", "12000"))


def _json_dump(value, fallback):
    if value is None:
        return fallback
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _json_load(value, fallback):
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _extrair_custo_estimado(valor) -> float:
    if not isinstance(valor, dict):
        return 0.0

    candidatos = (
        valor.get("_custo_ciclo_ia_usd"),
        valor.get("_custo_estimado_ia"),
        valor.get("custo_estimado_ia"),
        valor.get("custo_estimado_usd"),
        valor.get("_estimated_cost_usd"),
    )
    for candidato in candidatos:
        if candidato in (None, ""):
            continue
        try:
            return float(candidato)
        except Exception:
            continue
    return 0.0


def _append_transcript(base: str, fragment: str) -> str:
    base = (base or "").strip()
    fragment = (fragment or "").strip()
    if not fragment:
        return base
    if not base:
        return fragment
    return f"{base}\n\n{fragment}"


def _merge_transcript_buffer(current_buffer: str, fragment: str) -> str:
    current_buffer = (current_buffer or "").strip()
    fragment = (fragment or "").strip()

    chunks = [chunk.strip() for chunk in current_buffer.split(_TRANSCRIPT_BUFFER_SEPARATOR) if chunk.strip()]
    if fragment:
        chunks.append(fragment)

    if not chunks:
        return ""

    merged = _TRANSCRIPT_BUFFER_SEPARATOR.join(chunks)
    while len(merged) > _TRANSCRIPT_BUFFER_MAX_CHARS and len(chunks) > 1:
        chunks.pop(0)
        merged = _TRANSCRIPT_BUFFER_SEPARATOR.join(chunks)
    return merged


def _meeting_memory_to_dict(row: MeetingMemory) -> dict:
    return {
        "id": row.id,
        "meeting_id": row.meeting_id,
        "usuario_id": row.usuario_id,
        "opportunity_id": row.opportunity_id,
        "transcript_full": row.transcript_full or "",
        "transcript_buffer": row.transcript_buffer or "",
        "accumulated_summary": row.accumulated_summary or "",
        "current_diagnosis": row.current_diagnosis or "",
        "score_history": _json_load(row.score_history_json, []),
        "key_moments": _json_load(row.key_moments_json, []),
        "events": _json_load(row.events_json, []),
        "last_ai_at": row.last_ai_at.isoformat() if row.last_ai_at else None,
        "last_recap_trigger_at": row.last_recap_trigger_at.isoformat() if row.last_recap_trigger_at else None,
        "provider_cost_estimate": row.provider_cost_estimate or 0.0,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def obter_meeting_memory(meeting_id: str) -> Optional[dict]:
    """Retorna a memoria persistente mais recente de uma reuniao, ou None."""
    if not meeting_id:
        return None

    with Session(engine) as session:
        stmt = select(MeetingMemory).where(MeetingMemory.meeting_id == meeting_id)
        row = session.exec(stmt).first()
        if row:
            return _meeting_memory_to_dict(row)
    return None


def obter_trecho_final_transcricao(meeting_id: str, max_chars: int = 3000) -> str:
    """Só o fim de `transcript_full` (A12: vocabulário do Whisper). Lê só
    essa coluna, sem o resto da MeetingMemory; o corte é em Python porque
    `SUBSTR(x, -n)` do MySQL devolve '' quando o texto é menor que n.
    Memória parada há mais de `INATIVIDADE_NOVA_REUNIAO` é de outra
    reunião da mesma sala (P5) — não entra."""
    if not meeting_id or meeting_id == "default":
        return ""
    with Session(engine) as session:
        linha = session.exec(
            select(MeetingMemory.transcript_full, MeetingMemory.updated_at)
            .where(MeetingMemory.meeting_id == meeting_id)
        ).first()
    if not linha:
        return ""
    texto, atualizado = linha
    if atualizado and datetime.now() - atualizado > INATIVIDADE_NOVA_REUNIAO:
        return ""
    return (texto or "")[-max_chars:]


# Auditoria T01 (P5): sala fixa do Meet tem o mesmo código todo dia
# (`mnk-kvoo-pyj` em 36 dias) e virava uma MeetingMemory só, misturando
# reuniões no contexto da IA, na deduplicação e no prompt do Whisper.
# Parada há mais que isto, a próxima gravação abre uma memória nova e a
# antiga fica arquivada com o código + data de início.
INATIVIDADE_NOVA_REUNIAO = timedelta(hours=6)
_TENTATIVAS_GRAVACAO = 5


def _arquivar_se_outra_reuniao(session: Session, row: Optional[MeetingMemory]) -> Optional[MeetingMemory]:
    if not row or not row.updated_at or datetime.now() - row.updated_at <= INATIVIDADE_NOVA_REUNIAO:
        return row
    original = row.meeting_id
    inicio = row.created_at or row.updated_at
    row.meeting_id = f"{original}#{inicio:%Y%m%d%H%M}-{row.id}"[:200]
    session.add(row)
    session.commit()
    logger.info("[MeetingMemory] %s parada desde %s — arquivada como %s", original, row.updated_at, row.meeting_id)
    return None


def registrar_transcricao_audio(meeting_id: str, texto: str) -> None:
    """Guarda o corpo de um texto transcrito do áudio (P8). Melhor esforço."""
    if not meeting_id or meeting_id == "default" or not (texto or "").strip():
        return
    from agent.transcript_dedup_rules import corpo_normalizado

    agora = datetime.now()
    with Session(engine) as session:
        session.add(TranscricaoAudioRecente(meeting_id=meeting_id, corpo=corpo_normalizado(texto), criado_em=agora))
        session.execute(
            TranscricaoAudioRecente.__table__.delete().where(
                TranscricaoAudioRecente.criado_em < agora - timedelta(days=1)
            )
        )
        session.commit()


def corpos_de_audio_recentes(meeting_id: str, minutos: int = 15) -> set:
    """Corpos transcritos do áudio desta reunião nos últimos `minutos`.
    Falha de leitura vira conjunto vazio (só desliga a regra de similaridade)."""
    try:
        limite = datetime.now() - timedelta(minutes=minutos)
        with Session(engine) as session:
            return set(session.exec(
                select(TranscricaoAudioRecente.corpo).where(
                    TranscricaoAudioRecente.meeting_id == meeting_id,
                    TranscricaoAudioRecente.criado_em >= limite,
                )
            ).all())
    except Exception as e:
        logger.warning("[MeetingMemory] sem corpos de áudio para %s: %s", meeting_id, e)
        return set()


def salvar_meeting_memory(meeting_id: str, **campos) -> dict:
    """Cria ou atualiza a memoria persistente da reuniao."""
    if not meeting_id:
        raise ValueError("meeting_id e obrigatorio")

    now = datetime.now()
    with Session(engine) as session:
        stmt = select(MeetingMemory).where(MeetingMemory.meeting_id == meeting_id)
        row = session.exec(stmt).first()

        if not row:
            row = MeetingMemory(meeting_id=meeting_id)

        for nome_campo in ("transcript_full", "transcript_buffer", "accumulated_summary", "current_diagnosis"):
            if nome_campo in campos and campos[nome_campo] is not None:
                setattr(row, nome_campo, str(campos[nome_campo]))

        if "score_history" in campos and campos["score_history"] is not None:
            row.score_history_json = _json_dump(campos["score_history"], "[]")
        if "key_moments" in campos and campos["key_moments"] is not None:
            row.key_moments_json = _json_dump(campos["key_moments"], "[]")
        if "events" in campos and campos["events"] is not None:
            row.events_json = _json_dump(campos["events"], "[]")

        if "last_ai_at" in campos and campos["last_ai_at"] is not None:
            row.last_ai_at = campos["last_ai_at"]
        if "last_recap_trigger_at" in campos and campos["last_recap_trigger_at"] is not None:
            row.last_recap_trigger_at = campos["last_recap_trigger_at"]
        if "provider_cost_estimate_delta" in campos and campos["provider_cost_estimate_delta"] is not None:
            row.provider_cost_estimate = float(row.provider_cost_estimate or 0.0) + float(campos["provider_cost_estimate_delta"])
        elif "provider_cost_estimate" in campos and campos["provider_cost_estimate"] is not None:
            row.provider_cost_estimate = float(campos["provider_cost_estimate"])
        if "created_at" in campos and campos["created_at"] is not None:
            row.created_at = campos["created_at"]

        row.updated_at = now
        session.add(row)
        session.commit()
        session.refresh(row)
        return _meeting_memory_to_dict(row)


def registrar_transcricao_meeting(
    meeting_id: str, fragmento: str, substituir: bool = False, usuario_id: Optional[str] = None
) -> dict:
    """Atualiza transcript_full e transcript_buffer da reuniao.

    `usuario_id` (Fase 18 / Tarefa 18.1): carimba o dono da reunião na
    criação da linha, ou faz backfill se a linha já existe mas ainda
    não tem dono (ex.: reunião começou anônima e o vendedor logou no
    meio) — nunca sobrescreve um dono já registrado.

    Auditoria T01 (P6): com 2 workers, ler-deduplicar-gravar sem trava
    perdia o fragmento de quem gravasse primeiro. A gravação agora só vale
    se o tamanho de `transcript_full` ainda for o lido (compare-and-swap);
    senão relê e refaz, até `_TENTATIVAS_GRAVACAO` vezes."""
    if not meeting_id:
        raise ValueError("meeting_id e obrigatorio")

    from sqlalchemy import update
    from sqlalchemy.exc import IntegrityError
    from agent.transcript_dedup_rules import deduplicar_fragmento

    fragmento = (fragmento or "").strip()
    tamanho_sql = func.coalesce(func.length(MeetingMemory.transcript_full), 0)
    for _ in range(_TENTATIVAS_GRAVACAO):
        with Session(engine) as session:
            achado = session.exec(
                select(MeetingMemory, tamanho_sql).where(MeetingMemory.meeting_id == meeting_id)
            ).first()
            row, tamanho = achado if achado else (None, 0)
            row = _arquivar_se_outra_reuniao(session, row)
            base = "" if (substituir or not row) else row.transcript_full

            if substituir:
                aceito = fragmento
            else:
                # Tarefa A1 + T01: reenvio do delta, artefato colado e a
                # mesma fala vinda do áudio (só contra o que o servidor
                # transcreveu — P8).
                aceito, descartadas = deduplicar_fragmento(
                    base, fragmento, corpos_audio=corpos_de_audio_recentes(meeting_id)
                )
                if descartadas:
                    logger.info("[MeetingMemory] %s linha(s) duplicada(s) descartada(s) meeting=%s", descartadas, meeting_id)
            novo_full = aceito if substituir else _append_transcript(base, aceito)
            novo_buffer = _merge_transcript_buffer("" if (substituir or not row) else row.transcript_buffer, aceito)
            agora = datetime.now()

            if not row:
                row = MeetingMemory(meeting_id=meeting_id, usuario_id=usuario_id,
                                    transcript_full=novo_full, transcript_buffer=novo_buffer,
                                    created_at=agora, updated_at=agora)
                session.add(row)
                try:
                    session.commit()
                except IntegrityError:  # outro worker criou a linha agora
                    session.rollback()
                    continue
            else:
                valores = {"transcript_full": novo_full, "transcript_buffer": novo_buffer, "updated_at": agora}
                if usuario_id and not row.usuario_id:
                    valores["usuario_id"] = usuario_id
                gravou = session.execute(
                    update(MeetingMemory)
                    .where(MeetingMemory.id == row.id, tamanho_sql == tamanho)
                    .values(**valores)
                    .execution_options(synchronize_session=False)
                ).rowcount
                if not gravou:  # outro worker gravou entre a leitura e aqui
                    session.rollback()
                    continue
                session.commit()

            session.expire_all()  # o UPDATE acima não passa pelo objeto carregado
            row = session.exec(select(MeetingMemory).where(MeetingMemory.meeting_id == meeting_id)).first()
            resultado = _meeting_memory_to_dict(row)
            resultado["fragmento_aceito"] = aceito
            return resultado
    raise RuntimeError(f"MeetingMemory {meeting_id}: gravação em conflito {_TENTATIVAS_GRAVACAO} vezes seguidas")


def _normalizar_estruturado_item(
    item,
    default_type: str,
    default_speaker: str = "incerto",
    default_fact_or_inference: str = "inference",
    source: str = "ai",
    fallback_timestamp: Optional[str] = None,
):
    if not isinstance(item, dict):
        return None

    normalizado = dict(item)
    normalizado["type"] = str(normalizado.get("type") or default_type).strip() or default_type
    normalizado["quote"] = str(normalizado.get("quote") or "").strip()
    normalizado["speaker"] = str(normalizado.get("speaker") or default_speaker).strip() or default_speaker
    normalizado["timestamp"] = str(normalizado.get("timestamp") or fallback_timestamp or "").strip() or fallback_timestamp

    importance = str(normalizado.get("importance") or "medium").strip().lower()
    if importance not in {"low", "medium", "high"}:
        importance = "medium"
    normalizado["importance"] = importance

    confidence = str(normalizado.get("confidence") or "medium").strip().lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "medium"
    normalizado["confidence"] = confidence

    fact_or_inference = str(normalizado.get("fact_or_inference") or default_fact_or_inference).strip().lower()
    if fact_or_inference not in {"fact", "inference"}:
        fact_or_inference = default_fact_or_inference
    normalizado["fact_or_inference"] = fact_or_inference

    if source:
        normalizado["source"] = str(normalizado.get("source") or source).strip() or source

    return normalizado


def _normalizar_lista_estruturada(
    itens,
    default_type: str,
    default_speaker: str = "incerto",
    default_fact_or_inference: str = "inference",
    source: str = "ai",
    fallback_timestamp: Optional[str] = None,
):
    itens = itens or []
    normalizados = []
    vistos = set()

    for item in itens:
        normalizado = _normalizar_estruturado_item(
            item,
            default_type=default_type,
            default_speaker=default_speaker,
            default_fact_or_inference=default_fact_or_inference,
            source=source,
            fallback_timestamp=fallback_timestamp,
        )
        if not normalizado:
            continue

        chave = (
            normalizado.get("type"),
            normalizado.get("quote"),
            normalizado.get("speaker"),
            normalizado.get("timestamp"),
            normalizado.get("importance"),
            normalizado.get("confidence"),
            normalizado.get("fact_or_inference"),
        )
        if chave in vistos:
            continue
        vistos.add(chave)
        normalizados.append(normalizado)

    return normalizados


def _derivar_eventos_da_analise(analise: dict, fallback_timestamp: str) -> tuple[list, list]:
    eventos = []
    key_moments = []

    objecao = analise.get("objecao_detectada") or {}
    if isinstance(objecao, dict) and objecao.get("objecao"):
        quote = str(objecao.get("objecao")).strip()
        quote_lower = quote.lower()
        if any(palavra in quote_lower for palavra in ("caro", "preco", "preço", "valor", "invest", "orçamento", "orcamento")):
            tipo = "pricing_resistance"
            importance = "high"
        else:
            tipo = "objection_detected"
            importance = "medium"

        evento = {
            "type": tipo,
            "quote": quote,
            "speaker": "cliente",
            "timestamp": fallback_timestamp,
            "importance": importance,
            "confidence": "medium",
            "fact_or_inference": "fact",
            "source": "derived",
        }
        eventos.append(evento)
        key_moments.append(dict(evento))

    if analise.get("alerta_urgente"):
        evento = {
            "type": "alerta_urgente",
            "quote": str(analise.get("alerta_urgente")).strip(),
            "speaker": "incerto",
            "timestamp": fallback_timestamp,
            "importance": "high",
            "confidence": "medium",
            "fact_or_inference": "inference",
            "source": "derived",
        }
        eventos.append(evento)

    return eventos, key_moments


def registrar_analise_meeting(meeting_id: str, analise: dict) -> dict:
    """Persiste resumo vivo, diagnostico atual e score da analise ao vivo."""
    if not meeting_id:
        raise ValueError("meeting_id e obrigatorio")

    analise = analise or {}
    now = datetime.now()
    memoria = obter_meeting_memory(meeting_id) or {
        "score_history": [],
        "key_moments": [],
        "events": [],
        "accumulated_summary": "",
        "current_diagnosis": "",
        "transcript_full": "",
        "transcript_buffer": "",
    }

    resumo_vivo = analise.get("recapitulacao") or analise.get("historico_resumido") or memoria["accumulated_summary"]
    diagnostico_atual = {
        "alerta_urgente": analise.get("alerta_urgente"),
        "perfil_disc": analise.get("perfil_disc"),
        "perfil_bigfive": analise.get("perfil_bigfive"),
        "mapa_financeiro": analise.get("mapa_financeiro"),
        "temperatura": analise.get("temperatura"),
        "proxima_fala": analise.get("proxima_fala"),
        "objecao_detectada": analise.get("objecao_detectada"),
        "dado_esquecido": analise.get("dado_esquecido"),
        "score_compra": analise.get("score_compra"),
        "next_best_question": analise.get("next_best_question"),
    }

    score_history = list(memoria.get("score_history") or [])
    score = analise.get("score_compra") or {}
    custo_estimado = _extrair_custo_estimado(analise)
    if isinstance(score, dict) and score.get("valor") is not None:
        score_history.append(
            {
                "timestamp": now.isoformat(),
                "valor": score.get("valor"),
                "justificativa": score.get("justificativa"),
                "fonte": "tempo_real",
            }
        )

    key_moments = _normalizar_lista_estruturada(
        memoria.get("key_moments") or [],
        default_type="key_moment",
        default_speaker="incerto",
        default_fact_or_inference="inference",
        source="memory",
    )
    eventos = _normalizar_lista_estruturada(
        memoria.get("events") or [],
        default_type="evento",
        default_speaker="incerto",
        default_fact_or_inference="inference",
        source="memory",
    )

    eventos_analise = analise.get("eventos") or analise.get("events") or []
    key_moments_analise = analise.get("key_moments") or []

    eventos.extend(
        _normalizar_lista_estruturada(
            eventos_analise,
            default_type="evento",
            default_speaker="incerto",
            default_fact_or_inference="inference",
            source="ai",
            fallback_timestamp=now.isoformat(),
        )
    )
    key_moments.extend(
        _normalizar_lista_estruturada(
            key_moments_analise,
            default_type="key_moment",
            default_speaker="incerto",
            default_fact_or_inference="inference",
            source="ai",
            fallback_timestamp=now.isoformat(),
        )
    )

    eventos_derivados, key_moments_derivados = _derivar_eventos_da_analise(analise, now.isoformat())
    eventos.extend(eventos_derivados)
    key_moments.extend(key_moments_derivados)

    eventos = _normalizar_lista_estruturada(eventos, default_type="evento", default_speaker="incerto", default_fact_or_inference="inference", source="merged")
    key_moments = _normalizar_lista_estruturada(key_moments, default_type="key_moment", default_speaker="incerto", default_fact_or_inference="inference", source="merged")

    if any(item.get("type") == "recap_trigger" for item in eventos + key_moments):
        ultima_deixa = now
    else:
        ultima_deixa = memoria.get("last_recap_trigger_at")
        if isinstance(ultima_deixa, str) and ultima_deixa.strip():
            try:
                ultima_deixa = datetime.fromisoformat(ultima_deixa.replace("Z", "+00:00"))
            except Exception:
                ultima_deixa = None

    return salvar_meeting_memory(
        meeting_id,
        accumulated_summary=resumo_vivo or "",
        current_diagnosis=json.dumps(analise, ensure_ascii=False),
        score_history=score_history,
        key_moments=key_moments,
        events=eventos,
        last_ai_at=now,
        last_recap_trigger_at=ultima_deixa,
        provider_cost_estimate_delta=custo_estimado,
    )


def registrar_evento_uso_ia(
    *,
    feature: str,
    provider: str,
    model: Optional[str],
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    usage_source: str,
    cost_usd: float,
    latency_ms: Optional[int] = None,
    success: bool,
    fallback_used: bool = False,
    meeting_id: Optional[str] = None,
    usuario_id: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    """Grava um evento de uso de IA (Cost Intelligence Fase 1).

    Melhor esforco: nunca propaga excecao — uma falha aqui nao pode derrubar
    o fluxo de vendas (tempo real, relatorios, etc.).
    """
    try:
        try:
            from api.main import _cid_var  # import tardio — api.main importa api.ai_router no topo
            request_id = _cid_var.get("-")
        except Exception:
            request_id = "-"

        evento = AiUsageEvent(
            feature=feature,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            usage_source=usage_source,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            success=success,
            fallback_used=fallback_used,
            meeting_id=meeting_id,
            usuario_id=usuario_id,
            request_id=None if request_id == "-" else request_id,
            error_message=(error_message or "")[:240] or None,
        )
        with Session(engine) as session:
            session.add(evento)
            session.commit()
    except Exception as exc:
        logger.warning("[CostIntelligence] Falha ao registrar evento de uso de IA: %s", exc)


def custo_por_reuniao(meeting_id: str) -> dict:
    """Agrega custo/tokens de ai_usage_events para uma reuniao.

    So leitura, sem endpoint HTTP nesta fase (Cost Intelligence Fase 1) —
    prova que a fundacao de dados funciona ponta a ponta.
    """
    with Session(engine) as session:
        eventos = session.exec(
            select(AiUsageEvent).where(AiUsageEvent.meeting_id == meeting_id)
        ).all()

    por_feature: dict = {}
    por_provider: dict = {}
    for evento in eventos:
        pf = por_feature.setdefault(
            evento.feature, {"chamadas": 0, "custo_usd": 0.0, "tokens_entrada": 0, "tokens_saida": 0}
        )
        pf["chamadas"] += 1
        pf["custo_usd"] = round(pf["custo_usd"] + evento.cost_usd, 6)
        pf["tokens_entrada"] += evento.input_tokens
        pf["tokens_saida"] += evento.output_tokens

        pp = por_provider.setdefault(evento.provider, {"chamadas": 0, "custo_usd": 0.0, "falhas": 0})
        pp["chamadas"] += 1
        pp["custo_usd"] = round(pp["custo_usd"] + evento.cost_usd, 6)
        if not evento.success:
            pp["falhas"] += 1

    return {
        "meeting_id": meeting_id,
        "total_eventos": len(eventos),
        "total_usd": round(sum(e.cost_usd for e in eventos), 6),
        "por_feature": por_feature,
        "por_provider": por_provider,
    }


def _com_filtro_data(stmt, date_from: Optional[datetime], date_to: Optional[datetime]):
    """Aplica filtro opcional de periodo em AiUsageEvent.criado_em (Cost
    Intelligence Fase 2). date_to e exclusivo (< date_to) — o chamador que
    quiser incluir o dia inteiro de date_to deve passar "dia seguinte 00:00".
    """
    if date_from is not None:
        stmt = stmt.where(AiUsageEvent.criado_em >= date_from)
    if date_to is not None:
        stmt = stmt.where(AiUsageEvent.criado_em < date_to)
    return stmt


def custos_resumo(date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> dict:
    """Agregados gerais de custo de IA (Cost Intelligence Fase 2)."""
    with Session(engine) as session:
        total_eventos, total_usd = session.exec(
            _com_filtro_data(
                select(func.count(AiUsageEvent.id), func.coalesce(func.sum(AiUsageEvent.cost_usd), 0.0)),
                date_from, date_to,
            )
        ).one()

        eventos_sucesso = session.exec(
            _com_filtro_data(select(func.count(AiUsageEvent.id)).where(AiUsageEvent.success), date_from, date_to)
        ).one() or 0

        eventos_falha = session.exec(
            _com_filtro_data(select(func.count(AiUsageEvent.id)).where(~AiUsageEvent.success), date_from, date_to)
        ).one() or 0

        fallback_eventos, fallback_usd = session.exec(
            _com_filtro_data(
                select(func.count(AiUsageEvent.id), func.coalesce(func.sum(AiUsageEvent.cost_usd), 0.0))
                .where(AiUsageEvent.fallback_used),
                date_from, date_to,
            )
        ).one()

        por_provider_stmt = _com_filtro_data(
            select(
                AiUsageEvent.provider,
                func.count(AiUsageEvent.id),
                func.coalesce(func.sum(AiUsageEvent.cost_usd), 0.0),
                func.coalesce(func.sum(AiUsageEvent.input_tokens), 0),
                func.coalesce(func.sum(AiUsageEvent.output_tokens), 0),
            ).group_by(AiUsageEvent.provider),
            date_from, date_to,
        )
        por_provider = sorted(
            (
                {
                    "provider": provider,
                    "eventos": eventos_p,
                    "total_usd": round(custo_p, 6),
                    "input_tokens": int(tokens_in),
                    "output_tokens": int(tokens_out),
                }
                for provider, eventos_p, custo_p, tokens_in, tokens_out in session.exec(por_provider_stmt).all()
            ),
            key=lambda r: r["total_usd"], reverse=True,
        )

        por_model_stmt = _com_filtro_data(
            select(
                AiUsageEvent.provider,
                AiUsageEvent.model,
                func.count(AiUsageEvent.id),
                func.coalesce(func.sum(AiUsageEvent.cost_usd), 0.0),
            ).group_by(AiUsageEvent.provider, AiUsageEvent.model),
            date_from, date_to,
        )
        por_model = sorted(
            (
                {"provider": provider, "model": model, "eventos": eventos_m, "total_usd": round(custo_m, 6)}
                for provider, model, eventos_m, custo_m in session.exec(por_model_stmt).all()
            ),
            key=lambda r: r["total_usd"], reverse=True,
        )

        por_feature_stmt = _com_filtro_data(
            select(
                AiUsageEvent.feature,
                func.count(AiUsageEvent.id),
                func.coalesce(func.sum(AiUsageEvent.cost_usd), 0.0),
            ).group_by(AiUsageEvent.feature),
            date_from, date_to,
        )
        por_feature = sorted(
            (
                {"feature": feature, "eventos": eventos_f, "total_usd": round(custo_f, 6)}
                for feature, eventos_f, custo_f in session.exec(por_feature_stmt).all()
            ),
            key=lambda r: r["total_usd"], reverse=True,
        )

    return {
        "total_eventos": total_eventos or 0,
        "total_usd": round(total_usd or 0.0, 6),
        "eventos_sucesso": eventos_sucesso,
        "eventos_falha": eventos_falha,
        "fallback_eventos": fallback_eventos or 0,
        "fallback_usd": round(fallback_usd or 0.0, 6),
        "por_provider": por_provider,
        "por_model": por_model,
        "por_feature": por_feature,
    }


def custos_por_usuario(date_from: Optional[datetime] = None, date_to: Optional[datetime] = None, limit: int = 50) -> list:
    """Agregados de custo de IA por usuario_id (Cost Intelligence Fase 2).

    So os ids + agregados — nome/email sao enriquecidos na camada do endpoint
    via agent.sessao_manager.obter_nomes_usuarios (mesmo padrao ja usado por
    /historico/uso, que mescla SQLModel + pymysql em Python no endpoint).
    usuario_id pode ser None (uso anonimo da extensao, sem login).
    """
    with Session(engine) as session:
        stmt = _com_filtro_data(
            select(
                AiUsageEvent.usuario_id,
                func.count(AiUsageEvent.id),
                func.coalesce(func.sum(AiUsageEvent.cost_usd), 0.0),
            ).group_by(AiUsageEvent.usuario_id),
            date_from, date_to,
        )
        linhas = session.exec(stmt).all()

    resultado = sorted(
        (
            {"usuario_id": usuario_id, "eventos": eventos, "total_usd": round(custo, 6)}
            for usuario_id, eventos, custo in linhas
        ),
        key=lambda r: r["total_usd"], reverse=True,
    )
    return resultado[:limit]


def custos_reunioes_mais_caras(date_from: Optional[datetime] = None, date_to: Optional[datetime] = None, limit: int = 20) -> list:
    """Reunioes com maior custo de IA acumulado (Cost Intelligence Fase 2).

    So meeting_id + agregados + janela de tempo — cliente/empresa sao
    enriquecidos na camada do endpoint via
    agent.sessao_manager.obter_clientes_por_reunioes.
    """
    with Session(engine) as session:
        stmt = _com_filtro_data(
            select(
                AiUsageEvent.meeting_id,
                func.count(AiUsageEvent.id),
                func.coalesce(func.sum(AiUsageEvent.cost_usd), 0.0),
                func.min(AiUsageEvent.criado_em),
                func.max(AiUsageEvent.criado_em),
            )
            .where(AiUsageEvent.meeting_id.is_not(None))
            .group_by(AiUsageEvent.meeting_id)
            .order_by(func.sum(AiUsageEvent.cost_usd).desc())
            .limit(limit),
            date_from, date_to,
        )
        linhas = session.exec(stmt).all()

    return [
        {
            "meeting_id": meeting_id,
            "eventos": eventos,
            "total_usd": round(custo, 6),
            "inicio": inicio.isoformat() if inicio else None,
            "fim": fim.isoformat() if fim else None,
        }
        for meeting_id, eventos, custo, inicio, fim in linhas
    ]


def eventos_de_reuniao(meeting_id: str) -> list:
    """Lista crua dos eventos de uso de IA de uma reuniao, em ordem cronologica
    (Cost Intelligence Fase 2) — alimenta a timeline de detalhe no dashboard.
    """
    with Session(engine) as session:
        eventos = session.exec(
            select(AiUsageEvent)
            .where(AiUsageEvent.meeting_id == meeting_id)
            .order_by(AiUsageEvent.criado_em)
        ).all()

    return [
        {
            "criado_em": e.criado_em.isoformat() if e.criado_em else None,
            "feature": e.feature,
            "provider": e.provider,
            "model": e.model,
            "cost_usd": round(e.cost_usd, 6),
            "usage_source": e.usage_source,
            "success": e.success,
            "fallback_used": e.fallback_used,
        }
        for e in eventos
    ]


def exportar_eventos_uso_ia(date_from: Optional[datetime] = None, date_to: Optional[datetime] = None, limit: int = 20000) -> list:
    """Linhas cruas de ai_usage_events para exportacao CSV/JSON (Cost
    Intelligence Fase 2). `limit` e um teto de seguranca — a tabela cresce a
    cada ciclo de tempo real, exportar sem limite seria imprudente.
    """
    with Session(engine) as session:
        stmt = _com_filtro_data(
            select(AiUsageEvent).order_by(AiUsageEvent.criado_em.desc()).limit(limit),
            date_from, date_to,
        )
        eventos = session.exec(stmt).all()

    return [
        {
            "criado_em": e.criado_em.isoformat() if e.criado_em else None,
            "meeting_id": e.meeting_id,
            "usuario_id": e.usuario_id,
            "feature": e.feature,
            "provider": e.provider,
            "model": e.model,
            "input_tokens": e.input_tokens,
            "output_tokens": e.output_tokens,
            "cached_input_tokens": e.cached_input_tokens,
            "usage_source": e.usage_source,
            "cost_usd": round(e.cost_usd, 6),
            "latency_ms": e.latency_ms,
            "success": e.success,
            "fallback_used": e.fallback_used,
        }
        for e in eventos
    ]


def obter_orcamento_ia() -> Optional[dict]:
    """Orcamento mensal de IA configurado (Cost Intelligence Fase 3).
    None se o admin nunca configurou nenhum limite."""
    with Session(engine) as session:
        row = session.exec(select(OrcamentoIA).where(OrcamentoIA.id == 1)).first()
    if not row:
        return None
    return {
        "limite_mensal_usd": row.limite_mensal_usd,
        "atualizado_em": row.atualizado_em.isoformat() if row.atualizado_em else None,
        "atualizado_por_email": row.atualizado_por_email,
    }


def definir_orcamento_ia(limite_mensal_usd: float, usuario_id: str, usuario_email: str) -> dict:
    """Define (upsert, linha unica id=1) o limite mensal de gasto de IA e
    grava a mudanca em AuditoriaFinanceira (Cost Intelligence Fase 3)."""
    with Session(engine) as session:
        row = session.exec(select(OrcamentoIA).where(OrcamentoIA.id == 1)).first()
        valor_anterior = row.limite_mensal_usd if row else None

        if row:
            row.limite_mensal_usd = limite_mensal_usd
            row.atualizado_em = datetime.now()
            row.atualizado_por_id = usuario_id
            row.atualizado_por_email = usuario_email
        else:
            row = OrcamentoIA(
                id=1, limite_mensal_usd=limite_mensal_usd,
                atualizado_por_id=usuario_id, atualizado_por_email=usuario_email,
            )
        session.add(row)

        session.add(AuditoriaFinanceira(
            usuario_id=usuario_id, usuario_email=usuario_email,
            tipo="orcamento", campo="limite_mensal_usd",
            valor_anterior=str(valor_anterior) if valor_anterior is not None else None,
            valor_novo=str(limite_mensal_usd),
        ))
        session.commit()

    logger_financeiro.info(
        "Orcamento de IA alterado: limite_mensal_usd %s -> %s (por %s)",
        valor_anterior, limite_mensal_usd, usuario_email,
    )
    return obter_orcamento_ia()


def obter_precos_planos() -> dict:
    """{plano: preco_mensal_brl} — so planos com preco configurado pelo
    admin aparecem aqui (Cost Intelligence Fase 3)."""
    with Session(engine) as session:
        rows = session.exec(select(PlanoPreco)).all()
    return {r.plano: r.preco_mensal_brl for r in rows}


def definir_preco_plano(plano: str, preco_mensal_brl: float, usuario_id: str, usuario_email: str) -> dict:
    """Define (upsert por `plano`) o preco mensal (BRL) de um plano e grava
    a mudanca em AuditoriaFinanceira (Cost Intelligence Fase 3)."""
    with Session(engine) as session:
        row = session.exec(select(PlanoPreco).where(PlanoPreco.plano == plano)).first()
        valor_anterior = row.preco_mensal_brl if row else None

        if row:
            row.preco_mensal_brl = preco_mensal_brl
            row.atualizado_em = datetime.now()
            row.atualizado_por_id = usuario_id
            row.atualizado_por_email = usuario_email
        else:
            row = PlanoPreco(
                plano=plano, preco_mensal_brl=preco_mensal_brl,
                atualizado_por_id=usuario_id, atualizado_por_email=usuario_email,
            )
        session.add(row)

        session.add(AuditoriaFinanceira(
            usuario_id=usuario_id, usuario_email=usuario_email,
            tipo="preco_plano", campo=f"preco_mensal_brl:{plano}",
            valor_anterior=str(valor_anterior) if valor_anterior is not None else None,
            valor_novo=str(preco_mensal_brl),
        ))
        session.commit()

    logger_financeiro.info(
        "Preco do plano '%s' alterado: preco_mensal_brl %s -> %s (por %s)",
        plano, valor_anterior, preco_mensal_brl, usuario_email,
    )
    return {"plano": plano, "preco_mensal_brl": preco_mensal_brl}


def listar_auditoria_financeira(limit: int = 50) -> list:
    """Ultimas mudancas de configuracao financeira (orcamento/preco de
    plano) — Cost Intelligence Fase 3."""
    with Session(engine) as session:
        rows = session.exec(
            select(AuditoriaFinanceira).order_by(AuditoriaFinanceira.criado_em.desc()).limit(limit)
        ).all()
    return [
        {
            "criado_em": r.criado_em.isoformat() if r.criado_em else None,
            "usuario_id": r.usuario_id,
            "usuario_email": r.usuario_email,
            "tipo": r.tipo,
            "campo": r.campo,
            "valor_anterior": r.valor_anterior,
            "valor_novo": r.valor_novo,
        }
        for r in rows
    ]


def gasto_mes_usd(ano: int, mes: int) -> float:
    """Soma de cost_usd de ai_usage_events no mes informado (Cost
    Intelligence Fase 3) — usa o mesmo _com_filtro_data da Fase 2."""
    inicio = datetime(ano, mes, 1)
    if mes == 12:
        fim = datetime(ano + 1, 1, 1)
    else:
        fim = datetime(ano, mes + 1, 1)

    with Session(engine) as session:
        total = session.exec(
            _com_filtro_data(select(func.coalesce(func.sum(AiUsageEvent.cost_usd), 0.0)), inicio, fim)
        ).one()
    return round(total or 0.0, 6)


def projecao_mensal_custo() -> dict:
    """Projecao de gasto do mes corrente + comparacao com o mes anterior
    (Cost Intelligence Fase 3) — regra de tres simples sobre os dias ja
    decorridos, sem nenhum modelo estatistico sofisticado."""
    agora = datetime.now()
    dias_no_mes = calendar.monthrange(agora.year, agora.month)[1]
    dias_decorridos = agora.day

    gasto_atual = gasto_mes_usd(agora.year, agora.month)
    projecao_fim_mes = round((gasto_atual / dias_decorridos) * dias_no_mes, 6) if dias_decorridos else 0.0

    if agora.month == 1:
        ano_anterior, mes_anterior = agora.year - 1, 12
    else:
        ano_anterior, mes_anterior = agora.year, agora.month - 1
    gasto_mes_anterior = gasto_mes_usd(ano_anterior, mes_anterior)

    crescimento_pct = None
    if gasto_mes_anterior > 0:
        crescimento_pct = round((projecao_fim_mes - gasto_mes_anterior) / gasto_mes_anterior * 100, 2)

    return {
        "mes": f"{agora.year:04d}-{agora.month:02d}",
        "dias_decorridos": dias_decorridos,
        "dias_no_mes": dias_no_mes,
        "gasto_atual_usd": gasto_atual,
        "projecao_fim_mes_usd": projecao_fim_mes,
        "gasto_mes_anterior_usd": gasto_mes_anterior,
        "crescimento_pct": crescimento_pct,
    }


def registrar_decisao_router(
    *,
    feature: str,
    complexidade: str,
    modo: str,
    provider: str,
    model_real: str,
    custo_real_usd: float,
    model_recomendado: str,
    custo_recomendado_usd: float,
    concordou: bool,
) -> None:
    """Grava 1 comparacao shadow-mode do Cost Router (Fase 4). Melhor
    esforco — nunca propaga excecao, mesmo padrao de
    registrar_evento_uso_ia."""
    try:
        with Session(engine) as session:
            session.add(RouterDecisao(
                feature=feature, complexidade=complexidade, modo=modo,
                provider=provider, model_real=model_real, custo_real_usd=custo_real_usd,
                model_recomendado=model_recomendado, custo_recomendado_usd=custo_recomendado_usd,
                concordou=concordou,
            ))
            session.commit()
    except Exception as exc:
        logger.warning("[CostRouter] Falha ao registrar decisao shadow: %s", exc)


def resumo_router_shadow(date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> dict:
    """Agregados do shadow mode do Cost Router (Fase 4): quanto o router
    concordaria com o que ja e feito hoje, e quanto teria economizado se
    a recomendacao tivesse sido seguida."""

    def _filtro(stmt):
        if date_from is not None:
            stmt = stmt.where(RouterDecisao.criado_em >= date_from)
        if date_to is not None:
            stmt = stmt.where(RouterDecisao.criado_em < date_to)
        return stmt

    with Session(engine) as session:
        total, custo_real, custo_recomendado = session.exec(
            _filtro(select(
                func.count(RouterDecisao.id),
                func.coalesce(func.sum(RouterDecisao.custo_real_usd), 0.0),
                func.coalesce(func.sum(RouterDecisao.custo_recomendado_usd), 0.0),
            ))
        ).one()

        concordancias = session.exec(
            _filtro(select(func.count(RouterDecisao.id)).where(RouterDecisao.concordou))
        ).one() or 0

        por_modo_stmt = _filtro(
            select(RouterDecisao.modo, func.count(RouterDecisao.id))
            .group_by(RouterDecisao.modo)
        )
        por_modo = {modo: n for modo, n in session.exec(por_modo_stmt).all()}

        por_complexidade_stmt = _filtro(
            select(RouterDecisao.complexidade, func.count(RouterDecisao.id))
            .group_by(RouterDecisao.complexidade)
        )
        por_complexidade = {c: n for c, n in session.exec(por_complexidade_stmt).all()}

    total = total or 0
    economia_usd = round((custo_real or 0.0) - (custo_recomendado or 0.0), 6)
    return {
        "total_decisoes": total,
        "pct_concordancia": round(concordancias / total * 100, 1) if total else None,
        "custo_real_usd": round(custo_real or 0.0, 6),
        "custo_recomendado_usd": round(custo_recomendado or 0.0, 6),
        "economia_potencial_usd": economia_usd,
        "economia_potencial_pct": round(economia_usd / custo_real * 100, 1) if custo_real else None,
        "por_modo": por_modo,
        "por_complexidade": por_complexidade,
    }


def registrar_decisao_otimizacao(
    *,
    tipo: str,
    feature: str,
    meeting_id: Optional[str],
    prompt_hash: str,
    custo_real_usd: float,
    economia_estimada_usd: float,
    detalhe: Optional[str],
) -> None:
    """Grava 1 decisao shadow de otimizacao (Fase 5). Melhor esforco —
    nunca propaga excecao, mesmo padrao de registrar_evento_uso_ia."""
    try:
        with Session(engine) as session:
            session.add(OtimizacaoDecisao(
                tipo=tipo, feature=feature, meeting_id=meeting_id, prompt_hash=prompt_hash,
                custo_real_usd=custo_real_usd, economia_estimada_usd=economia_estimada_usd,
                detalhe=(detalhe or "")[:240] or None,
            ))
            session.commit()
    except Exception as exc:
        logger.warning("[Otimizacao] Falha ao registrar decisao shadow: %s", exc)


def resumo_otimizacao_shadow(date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> dict:
    """Agregados do shadow mode de otimizacao (Fase 5): quanto cada
    otimizacao (cache/contexto/loop) teria economizado, se tivesse
    agido de verdade."""

    def _filtro(stmt):
        if date_from is not None:
            stmt = stmt.where(OtimizacaoDecisao.criado_em >= date_from)
        if date_to is not None:
            stmt = stmt.where(OtimizacaoDecisao.criado_em < date_to)
        return stmt

    with Session(engine) as session:
        por_tipo_stmt = _filtro(
            select(
                OtimizacaoDecisao.tipo,
                func.count(OtimizacaoDecisao.id),
                func.coalesce(func.sum(OtimizacaoDecisao.economia_estimada_usd), 0.0),
            ).group_by(OtimizacaoDecisao.tipo)
        )
        linhas = session.exec(por_tipo_stmt).all()

    por_tipo = {
        tipo: {"eventos": eventos, "economia_estimada_usd": round(economia, 6)}
        for tipo, eventos, economia in linhas
    }
    total_eventos = sum(v["eventos"] for v in por_tipo.values())
    total_economia = round(sum(v["economia_estimada_usd"] for v in por_tipo.values()), 6)

    return {
        "total_decisoes": total_eventos,
        "economia_potencial_total_usd": total_economia,
        "por_tipo": por_tipo,
    }


def detectar_anomalias_custo(dias_janela: int = 7, limiar_multiplicador: float = 3.0) -> list:
    """Compara o custo medio por chamada de cada feature na janela atual
    contra a janela anterior de mesmo tamanho (Cost Intelligence Fase 5).
    So considera features com volume minimo (>=5 chamadas) nas duas
    janelas, para nao alarmar com ruido estatistico de pouca amostra."""
    agora = datetime.now()
    inicio_atual = agora - timedelta(days=dias_janela)
    inicio_anterior = inicio_atual - timedelta(days=dias_janela)

    with Session(engine) as session:
        stmt_atual = (
            select(
                AiUsageEvent.feature,
                func.count(AiUsageEvent.id),
                func.coalesce(func.sum(AiUsageEvent.cost_usd), 0.0),
            )
            .where(AiUsageEvent.criado_em >= inicio_atual)
            .group_by(AiUsageEvent.feature)
        )
        stmt_anterior = (
            select(
                AiUsageEvent.feature,
                func.count(AiUsageEvent.id),
                func.coalesce(func.sum(AiUsageEvent.cost_usd), 0.0),
            )
            .where(AiUsageEvent.criado_em >= inicio_anterior, AiUsageEvent.criado_em < inicio_atual)
            .group_by(AiUsageEvent.feature)
        )
        dados_atual = {f: (n, c) for f, n, c in session.exec(stmt_atual).all()}
        dados_anterior = {f: (n, c) for f, n, c in session.exec(stmt_anterior).all()}

    anomalias = []
    for feature, (n_atual, custo_atual) in dados_atual.items():
        n_anterior, custo_anterior = dados_anterior.get(feature, (0, 0.0))
        if n_atual < 5 or n_anterior < 5:
            continue  # amostra insuficiente pra confiar na comparacao

        media_atual = custo_atual / n_atual
        media_anterior = custo_anterior / n_anterior
        if media_anterior <= 0:
            continue

        if media_atual >= media_anterior * limiar_multiplicador:
            anomalias.append({
                "feature": feature,
                "media_atual_usd": round(media_atual, 6),
                "media_anterior_usd": round(media_anterior, 6),
                "multiplicador": round(media_atual / media_anterior, 2),
                "eventos_janela_atual": n_atual,
            })

    anomalias.sort(key=lambda a: a["multiplicador"], reverse=True)
    return anomalias


def analise_custo_latencia_qualidade(date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> dict:
    """Custo x latencia por (provider, model) — dados que ja existem em
    ai_usage_events. Qualidade: so o unico sinal real disponivel hoje
    (feedback do piloto Conta Claude) — cobertura deliberadamente
    limitada, nao existe metrica de qualidade universal no sistema."""

    def _filtro(stmt):
        if date_from is not None:
            stmt = stmt.where(AiUsageEvent.criado_em >= date_from)
        if date_to is not None:
            stmt = stmt.where(AiUsageEvent.criado_em < date_to)
        return stmt

    with Session(engine) as session:
        stmt = _filtro(
            select(
                AiUsageEvent.provider,
                AiUsageEvent.model,
                func.count(AiUsageEvent.id),
                func.coalesce(func.avg(AiUsageEvent.cost_usd), 0.0),
                func.coalesce(func.avg(AiUsageEvent.latency_ms), 0.0),
            )
            .where(AiUsageEvent.success)
            .group_by(AiUsageEvent.provider, AiUsageEvent.model)
        )
        linhas = session.exec(stmt).all()

    custo_latencia = sorted(
        (
            {
                "provider": provider,
                "model": model,
                "eventos": eventos,
                "custo_medio_usd": round(custo_medio, 6),
                "latencia_media_ms": round(latencia_media, 1),
            }
            for provider, model, eventos, custo_medio, latencia_media in linhas
        ),
        key=lambda r: r["custo_medio_usd"], reverse=True,
    )

    try:
        qualidade_claude_account = metricas_claude_account().get("avaliacoes", {})
    except Exception:
        qualidade_claude_account = {}

    return {
        "custo_latencia": custo_latencia,
        "qualidade_claude_account": qualidade_claude_account,
    }


# ── Fase 19 do "PROMPT MESTRE — SALE-IA V2" (Observabilidade) ──────────
# Reaproveita ai_usage_events/recommendation_events já existentes — sem
# tabela/coluna nova. Ver agent/observability_metrics_rules.py para o
# porquê de RAG latency/recommendation effectiveness ficarem de fora.

def latencia_por_feature(date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> list[dict]:
    """AI latency (Fase 19): média/mín/máx de latência real por feature,
    a partir de `ai_usage_events.latency_ms` — só eventos com sucesso e
    latência registrada (cache hit/bloqueio de loop caro nunca chamam o
    provedor, então nunca têm `latency_ms`)."""
    with Session(engine) as session:
        stmt = _com_filtro_data(
            select(
                AiUsageEvent.feature,
                func.count(AiUsageEvent.id),
                func.avg(AiUsageEvent.latency_ms),
                func.min(AiUsageEvent.latency_ms),
                func.max(AiUsageEvent.latency_ms),
            )
            .where(AiUsageEvent.success, AiUsageEvent.latency_ms.is_not(None))
            .group_by(AiUsageEvent.feature),
            date_from, date_to,
        )
        linhas = session.exec(stmt).all()

    return sorted(
        (
            {
                "feature": feature,
                "amostra": eventos,
                "media_ms": round(media, 1) if media is not None else None,
                "minimo_ms": minimo,
                "maximo_ms": maximo,
            }
            for feature, eventos, media, minimo, maximo in linhas
        ),
        key=lambda r: r["amostra"], reverse=True,
    )


def custo_medio_por_reuniao(date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> dict:
    """Cost per meeting (Fase 19) — custo médio de IA por reunião no
    período, agrupando `ai_usage_events` por `meeting_id`. Chamada sem
    `meeting_id` (ex.: geração de playbook/skill, fora do fluxo de uma
    reunião específica) fica de fora — nunca conta como "reunião
    grátis"."""
    with Session(engine) as session:
        subquery = _com_filtro_data(
            select(
                AiUsageEvent.meeting_id,
                func.sum(AiUsageEvent.cost_usd).label("custo_total"),
            )
            .where(AiUsageEvent.meeting_id.is_not(None))
            .group_by(AiUsageEvent.meeting_id),
            date_from, date_to,
        ).subquery()

        total_reunioes, custo_medio, custo_total = session.exec(
            select(
                func.count(),
                func.avg(subquery.c.custo_total),
                func.coalesce(func.sum(subquery.c.custo_total), 0.0),
            )
        ).one()

    return {
        "reunioes_com_custo": total_reunioes or 0,
        "custo_medio_usd": round(custo_medio, 6) if custo_medio is not None else None,
        "custo_total_usd": round(custo_total or 0.0, 6),
    }


def custo_medio_por_opportunity(date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> dict:
    """Cost per opportunity (Fase 19) — custo médio de IA por
    oportunidade no período. Cruza `ai_usage_events` (por `meeting_id`)
    com `meeting_memory` (`meeting_id` → `opportunity_id`) em Python,
    **nunca via JOIN SQL direto entre as duas tabelas** — mesmo cuidado
    já registrado em `agent/sales_memory.py` (Fase 6 do outro roadmap):
    colunas `meeting_id` com collations diferentes entre tabelas já
    causaram `Illegal mix of collations` neste projeto."""
    with Session(engine) as session:
        custo_por_meeting_stmt = _com_filtro_data(
            select(AiUsageEvent.meeting_id, func.sum(AiUsageEvent.cost_usd))
            .where(AiUsageEvent.meeting_id.is_not(None))
            .group_by(AiUsageEvent.meeting_id),
            date_from, date_to,
        )
        custo_por_meeting = dict(session.exec(custo_por_meeting_stmt).all())

        if not custo_por_meeting:
            return {"oportunidades_com_custo": 0, "custo_medio_usd": None, "custo_total_usd": 0.0}

        mapa_stmt = (
            select(MeetingMemory.meeting_id, MeetingMemory.opportunity_id)
            .where(MeetingMemory.meeting_id.in_(list(custo_por_meeting.keys())))
            .where(MeetingMemory.opportunity_id.is_not(None))
        )
        mapa_meeting_opportunity = dict(session.exec(mapa_stmt).all())

    custo_por_opportunity: dict = {}
    for meeting_id, custo in custo_por_meeting.items():
        opportunity_id = mapa_meeting_opportunity.get(meeting_id)
        if opportunity_id is None:
            continue
        custo_por_opportunity[opportunity_id] = custo_por_opportunity.get(opportunity_id, 0.0) + custo

    if not custo_por_opportunity:
        return {"oportunidades_com_custo": 0, "custo_medio_usd": None, "custo_total_usd": 0.0}

    valores = list(custo_por_opportunity.values())
    return {
        "oportunidades_com_custo": len(valores),
        "custo_medio_usd": round(sum(valores) / len(valores), 6),
        "custo_total_usd": round(sum(valores), 6),
    }


def taxa_resposta_recomendacoes(date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> dict:
    """Recommendation acceptance rate (Fase 19) — PROXY barato: % de
    `RecommendationEvent` com `used_at` preenchido (o vendedor disse
    algo depois da recomendação), **não** a classificação semântica
    real USED/PARTIALLY_USED/IGNORED (Fase 10.2, que exige 1 chamada de
    embedding por evento e não roda automaticamente em produção hoje)."""
    from agent.observability_metrics_rules import calcular_taxa

    def _filtro(stmt):
        if date_from is not None:
            stmt = stmt.where(RecommendationEvent.shown_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(RecommendationEvent.shown_at < date_to)
        return stmt

    with Session(engine) as session:
        total = session.exec(_filtro(select(func.count(RecommendationEvent.id)))).one() or 0
        respondidas = session.exec(
            _filtro(select(func.count(RecommendationEvent.id)).where(RecommendationEvent.used_at.is_not(None)))
        ).one() or 0

    return {
        "total_recomendacoes": total,
        "com_resposta_do_vendedor": respondidas,
        "taxa_resposta": calcular_taxa(respondidas, total),
    }


def _erro_tabela_ja_existe(exc: OperationalError) -> bool:
    """Detecta corrida benigna de create_all em apps com multiplos workers.

    1050 = tabela já existe; 1684 = tabela "pulada" porque outro worker
    está alterando a definição dela (incidente real de 17/09/2026, V.1.4.108
    — derrubou o processo inteiro por ~12s)."""
    original = getattr(exc, "orig", None)
    codigo = None
    if original is not None and getattr(original, "args", None):
        codigo = original.args[0]

    mensagem = str(exc).lower()
    return (
        codigo in (1050, 1684)
        or "already exists" in mensagem
        or "ja existe" in mensagem
        or "concurrent ddl" in mensagem
    )


def _criar_metadata_tolerante():
    """`create_all` com 1 nova tentativa: um erro de corrida interrompe o
    `create_all` no meio (as tabelas seguintes ficariam sem criar neste
    worker); a 2ª passada, com `checkfirst`, completa só o que faltou."""
    for tentativa in (1, 2):
        try:
            SQLModel.metadata.create_all(engine)
            return
        except OperationalError as exc:
            if not _erro_tabela_ja_existe(exc):
                raise
            logger.warning("Corrida de DDL no startup (tentativa %s): %s", tentativa, exc.orig if hasattr(exc, "orig") else exc)
            if tentativa == 2:
                return
            time.sleep(1)


_NOME_LOCK_SCHEMA = "saleia_schema_startup"


@contextmanager
def lock_de_schema(timeout_s: int = 120):
    """Tarefa D8: serializa o DDL do startup entre os workers do uvicorn
    (`--workers 2`). Sem isso, os dois rodavam `create_all()` e as
    migrações raw (`ALTER TABLE ... ADD COLUMN`) ao mesmo tempo e podiam
    colidir (erro 1684), derrubando o processo. Lock nomeado do MySQL
    (`GET_LOCK`, por sessão): o 1º worker faz o DDL, o 2º espera e depois
    só confirma que tudo já existe. SQLite (dev/teste): sem lock.
    Nunca impede o boot — se o lock não vier no tempo, segue sem ele
    (mesmo comportamento de antes) e registra warning."""
    if engine.dialect.name != "mysql":
        yield
        return
    conn = None
    obtido = False
    try:
        conn = engine.connect()
        obtido = conn.execute(text("SELECT GET_LOCK(:n, :t)"), {"n": _NOME_LOCK_SCHEMA, "t": timeout_s}).scalar() == 1
        if not obtido:
            logger.warning("Lock de schema não obtido em %ss; seguindo sem serializar o DDL.", timeout_s)
    except Exception as exc:
        logger.warning("Falha ao obter lock de schema (%s); seguindo sem serializar o DDL.", exc)
    try:
        yield
    finally:
        if conn is not None:
            try:
                if obtido:
                    conn.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": _NOME_LOCK_SCHEMA})
            except Exception as exc:
                logger.warning("Falha ao liberar lock de schema: %s", exc)
            finally:
                conn.close()


def db_health() -> dict:
    """Retorna latência de conexão e tipo de banco ativo."""
    host = os.getenv("DB_HOST", "")
    resultado = {"banco": "mysql" if host else "sqlite", "latencia_ms": -1, "erro": None}
    try:
        t0 = time.perf_counter()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        resultado["latencia_ms"] = round((time.perf_counter() - t0) * 1000)
    except Exception as exc:
        resultado["erro"] = str(exc)[:200]
        resultado["banco"] = "sqlite_fallback" if host else "sqlite"
    return resultado


def contar_reunioes_ativas(minutos: int = 5) -> int:
    """Conta reuniões com atividade nos últimos N minutos."""
    threshold = datetime.now() - timedelta(minutes=minutos)
    try:
        with Session(engine) as session:
            stmt = select(func.count(MeetingMemory.id)).where(MeetingMemory.updated_at >= threshold)
            return session.exec(stmt).one() or 0
    except Exception:
        return 0


def contar_reunioes_hoje() -> int:
    """Conta reuniões criadas hoje."""
    from datetime import date
    hoje = datetime.combine(date.today(), datetime.min.time())
    try:
        with Session(engine) as session:
            stmt = select(func.count(MeetingMemory.id)).where(MeetingMemory.created_at >= hoje)
            return session.exec(stmt).one() or 0
    except Exception:
        return 0


def criar_tabelas():
    """Cria as tabelas se ainda não existirem. Chamar no startup."""
    try:
        _criar_metadata_tolerante()
        logger.info("✅ Tabelas verificadas/criadas com sucesso.")
    except Exception as exc:
        logger.error("❌ Falha ao criar tabelas: %s", exc)
        raise


# ─────────────────────────────────────────────
# OPERAÇÕES
# ─────────────────────────────────────────────
def salvar_relatorio(meeting_id: str, nome_reuniao: str, dados: dict) -> Relatorio:
    """Persiste um relatório no banco. Retorna o objeto salvo."""
    relatorio = Relatorio(
        meeting_id=meeting_id,
        nome_reuniao=nome_reuniao,
        dados_json=json.dumps(dados, ensure_ascii=False),
    )
    with Session(engine) as session:
        session.add(relatorio)
        session.commit()
        session.refresh(relatorio)
    return relatorio


def buscar_relatorio(meeting_id: str) -> Optional[dict]:
    """Retorna o relatório mais recente de um meeting_id, ou None."""
    with Session(engine) as session:
        stmt = (
            select(Relatorio)
            .where(Relatorio.meeting_id == meeting_id)
            .order_by(Relatorio.criado_em.desc())
        )
        row = session.exec(stmt).first()
        if row:
            return json.loads(row.dados_json)
    return None


def listar_relatorios(limite: int = 20) -> List[dict]:
    """Retorna os últimos N relatórios com metadados."""
    with Session(engine) as session:
        stmt = select(Relatorio).order_by(Relatorio.criado_em.desc()).limit(limite)
        rows = session.exec(stmt).all()
        return [
            {
                "id": r.id,
                "meeting_id": r.meeting_id,
                "nome_reuniao": r.nome_reuniao,
                "criado_em": r.criado_em.isoformat(),
                "dados": json.loads(r.dados_json),
            }
            for r in rows
        ]


def buscar_ultimo_relatorio() -> Optional[dict]:
    """Retorna o relatório mais recente de todos."""
    with Session(engine) as session:
        stmt = select(Relatorio).order_by(Relatorio.criado_em.desc())
        row = session.exec(stmt).first()
        if row:
            return json.loads(row.dados_json)
    return None


# ─────────────────────────────────────────────
# CLAUDE ACCOUNT MODE — piloto de conta Claude individual por usuário
# ─────────────────────────────────────────────
def _claude_connection_to_dict(row: ClaudeConnection) -> dict:
    return {
        "id": row.id,
        "usuario_id": row.usuario_id,
        "status": row.status,
        "oauth_token_encrypted": row.oauth_token_encrypted,
        "connected_at": row.connected_at.isoformat() if row.connected_at else None,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def obter_claude_connection(usuario_id: str) -> Optional[dict]:
    """Retorna a conexão Claude do usuário, ou None se ele nunca conectou."""
    if not usuario_id:
        return None
    with Session(engine) as session:
        stmt = select(ClaudeConnection).where(ClaudeConnection.usuario_id == usuario_id)
        row = session.exec(stmt).first()
        return _claude_connection_to_dict(row) if row else None


def salvar_claude_connection(usuario_id: str, oauth_token_encrypted: str) -> dict:
    """Cria ou substitui a conexão Claude do usuário (conectar/reconectar)."""
    if not usuario_id:
        raise ValueError("usuario_id e obrigatorio")

    now = datetime.now()
    with Session(engine) as session:
        stmt = select(ClaudeConnection).where(ClaudeConnection.usuario_id == usuario_id)
        row = session.exec(stmt).first()
        if not row:
            row = ClaudeConnection(usuario_id=usuario_id)

        row.status = "ativo"
        row.oauth_token_encrypted = oauth_token_encrypted
        row.connected_at = now
        row.updated_at = now
        session.add(row)
        session.commit()
        session.refresh(row)
        return _claude_connection_to_dict(row)


def desconectar_claude_connection(usuario_id: str) -> Optional[dict]:
    """Marca a conexão como inativa e apaga o token — reconectar exige novo token."""
    with Session(engine) as session:
        stmt = select(ClaudeConnection).where(ClaudeConnection.usuario_id == usuario_id)
        row = session.exec(stmt).first()
        if not row:
            return None
        row.status = "inativo"
        row.oauth_token_encrypted = None
        row.updated_at = datetime.now()
        session.add(row)
        session.commit()
        session.refresh(row)
        return _claude_connection_to_dict(row)


def marcar_status_claude_connection(usuario_id: str, status: str) -> None:
    """Atualiza apenas o status da conexão (ex.: 'expirado' após falha de auth do provedor)."""
    with Session(engine) as session:
        stmt = select(ClaudeConnection).where(ClaudeConnection.usuario_id == usuario_id)
        row = session.exec(stmt).first()
        if not row:
            return
        row.status = status
        row.updated_at = datetime.now()
        session.add(row)
        session.commit()


def registrar_uso_claude_connection(usuario_id: str) -> None:
    """Atualiza last_used_at após uma execução bem-sucedida."""
    with Session(engine) as session:
        stmt = select(ClaudeConnection).where(ClaudeConnection.usuario_id == usuario_id)
        row = session.exec(stmt).first()
        if not row:
            return
        row.last_used_at = datetime.now()
        session.add(row)
        session.commit()


def _claude_analysis_to_dict(row: ClaudeMeetingAnalysis) -> dict:
    return {
        "id": row.id,
        "meeting_id": row.meeting_id,
        "usuario_id": row.usuario_id,
        "transcript_hash": row.transcript_hash,
        "status": row.status,
        "resultado": _json_load(row.result_json, None),
        "error_code": row.error_code,
        "error_message": row.error_message,
        "feedback_rating": row.feedback_rating,
        "feedback_tags": _json_load(row.feedback_tags_json, None),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


def obter_claude_analysis_por_hash(meeting_id: str, usuario_id: str, transcript_hash: str) -> Optional[dict]:
    """Retorna a última análise bem-sucedida deste usuário para essa versão exata da transcrição."""
    with Session(engine) as session:
        stmt = (
            select(ClaudeMeetingAnalysis)
            .where(
                ClaudeMeetingAnalysis.meeting_id == meeting_id,
                ClaudeMeetingAnalysis.usuario_id == usuario_id,
                ClaudeMeetingAnalysis.transcript_hash == transcript_hash,
                ClaudeMeetingAnalysis.status == "sucesso",
            )
            .order_by(ClaudeMeetingAnalysis.completed_at.desc())
        )
        row = session.exec(stmt).first()
        return _claude_analysis_to_dict(row) if row else None


def criar_claude_analysis_pendente(meeting_id: str, usuario_id: str, transcript_hash: str) -> dict:
    with Session(engine) as session:
        row = ClaudeMeetingAnalysis(
            meeting_id=meeting_id,
            usuario_id=usuario_id,
            transcript_hash=transcript_hash,
            status="pendente",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _claude_analysis_to_dict(row)


def finalizar_claude_analysis(
    analysis_id: int,
    *,
    status: str,
    resultado: Optional[dict] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Optional[dict]:
    with Session(engine) as session:
        row = session.get(ClaudeMeetingAnalysis, analysis_id)
        if not row:
            return None
        row.status = status
        row.result_json = json.dumps(resultado, ensure_ascii=False) if resultado is not None else None
        row.error_code = error_code
        row.error_message = error_message
        row.completed_at = datetime.now()
        session.add(row)
        session.commit()
        session.refresh(row)
        return _claude_analysis_to_dict(row)


def listar_claude_analyses(meeting_id: str, usuario_id: str, limite: int = 20) -> List[dict]:
    with Session(engine) as session:
        stmt = (
            select(ClaudeMeetingAnalysis)
            .where(
                ClaudeMeetingAnalysis.meeting_id == meeting_id,
                ClaudeMeetingAnalysis.usuario_id == usuario_id,
            )
            .order_by(ClaudeMeetingAnalysis.started_at.desc())
            .limit(limite)
        )
        rows = session.exec(stmt).all()
        return [_claude_analysis_to_dict(row) for row in rows]


def obter_claude_analysis(analysis_id: int) -> Optional[dict]:
    with Session(engine) as session:
        row = session.get(ClaudeMeetingAnalysis, analysis_id)
        return _claude_analysis_to_dict(row) if row else None


def salvar_claude_analysis_feedback(analysis_id: int, usuario_id: str, rating: str, tags: Optional[list] = None) -> Optional[dict]:
    """Grava o feedback do piloto. Só o dono da análise pode avaliar."""
    with Session(engine) as session:
        row = session.get(ClaudeMeetingAnalysis, analysis_id)
        if not row or row.usuario_id != usuario_id:
            return None
        row.feedback_rating = rating
        row.feedback_tags_json = json.dumps(tags, ensure_ascii=False) if tags else None
        session.add(row)
        session.commit()
        session.refresh(row)
        return _claude_analysis_to_dict(row)


def metricas_claude_account() -> dict:
    """Agregados simples para o painel admin do piloto (Tarefa 20)."""
    with Session(engine) as session:
        total_analises = session.exec(select(func.count(ClaudeMeetingAnalysis.id))).one() or 0
        sucesso = session.exec(
            select(func.count(ClaudeMeetingAnalysis.id)).where(ClaudeMeetingAnalysis.status == "sucesso")
        ).one() or 0
        erros = session.exec(
            select(func.count(ClaudeMeetingAnalysis.id)).where(ClaudeMeetingAnalysis.status == "erro")
        ).one() or 0
        limite_atingido = session.exec(
            select(func.count(ClaudeMeetingAnalysis.id)).where(ClaudeMeetingAnalysis.error_code == "USAGE_LIMIT_REACHED")
        ).one() or 0
        usuarios_ativos = session.exec(
            select(func.count(func.distinct(ClaudeMeetingAnalysis.usuario_id)))
        ).one() or 0
        reunioes_analisadas = session.exec(
            select(func.count(func.distinct(ClaudeMeetingAnalysis.meeting_id))).where(ClaudeMeetingAnalysis.status == "sucesso")
        ).one() or 0
        conexoes_ativas = session.exec(
            select(func.count(ClaudeConnection.id)).where(ClaudeConnection.status == "ativo")
        ).one() or 0

        avaliacoes = {"positivo": 0, "parcial": 0, "negativo": 0}
        stmt_avaliacoes = select(ClaudeMeetingAnalysis.feedback_rating, func.count(ClaudeMeetingAnalysis.id)).where(
            ClaudeMeetingAnalysis.feedback_rating.is_not(None)
        ).group_by(ClaudeMeetingAnalysis.feedback_rating)
        for rating, contagem in session.exec(stmt_avaliacoes).all():
            if rating in avaliacoes:
                avaliacoes[rating] = contagem

    return {
        "reunioes_analisadas": reunioes_analisadas,
        "usuarios_ativos_no_piloto": usuarios_ativos,
        "conexoes_ativas": conexoes_ativas,
        "analises_total": total_analises,
        "analises_sucesso": sucesso,
        "analises_erro": erros,
        "limites_atingidos": limite_atingido,
        "avaliacoes": avaliacoes,
    }


# ─────────────────────────────────────────────
# KNOWLEDGE COMPILER — Biblioteca de Inteligência (Fase 1)
# ─────────────────────────────────────────────
def _knowledge_source_to_dict(row: "KnowledgeSource", incluir_texto: bool = False) -> dict:
    d = {
        "id": row.id,
        "title": row.title,
        "author": row.author,
        "source_type": row.source_type,
        "original_filename": row.original_filename,
        "mime_type": row.mime_type,
        "arquivo_tamanho": row.arquivo_tamanho,
        "content_hash": row.content_hash,
        "status": row.status,
        "char_count": row.char_count,
        "section_count": row.section_count,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "processed_at": row.processed_at.isoformat() if row.processed_at else None,
    }
    if incluir_texto:
        d["texto_extraido"] = row.texto_extraido
        d["sections"] = json.loads(row.sections_json) if row.sections_json else []
    return d


def obter_knowledge_source_por_hash(content_hash: str) -> Optional[dict]:
    """Usado para deduplicação no upload: se o hash já existe, o chamador
    reaproveita o registro em vez de reprocessar."""
    with Session(engine) as session:
        stmt = select(KnowledgeSource).where(KnowledgeSource.content_hash == content_hash)
        row = session.exec(stmt).first()
        return _knowledge_source_to_dict(row) if row else None


def criar_knowledge_source(
    title: str,
    original_filename: str,
    arquivo_path: str,
    content_hash: str,
    source_type: str = "OTHER",
    author: Optional[str] = None,
    mime_type: Optional[str] = None,
    arquivo_tamanho: int = 0,
) -> dict:
    with Session(engine) as session:
        row = KnowledgeSource(
            title=title,
            author=author,
            source_type=source_type,
            original_filename=original_filename,
            mime_type=mime_type,
            arquivo_path=arquivo_path,
            arquivo_tamanho=arquivo_tamanho,
            content_hash=content_hash,
            status="UPLOADED",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _knowledge_source_to_dict(row)


def obter_knowledge_source(source_id: int, incluir_texto: bool = False) -> Optional[dict]:
    with Session(engine) as session:
        row = session.get(KnowledgeSource, source_id)
        return _knowledge_source_to_dict(row, incluir_texto=incluir_texto) if row else None


def obter_knowledge_source_arquivo(source_id: int) -> Optional[tuple[str, str]]:
    """Retorna (arquivo_path, mime_type) para uso interno da extração —
    não exposto no dict público (é um caminho de disco no servidor)."""
    with Session(engine) as session:
        row = session.get(KnowledgeSource, source_id)
        return (row.arquivo_path, row.mime_type or "") if row else None


def listar_knowledge_sources() -> List[dict]:
    with Session(engine) as session:
        stmt = select(KnowledgeSource).order_by(KnowledgeSource.created_at.desc())
        rows = session.exec(stmt).all()
        return [_knowledge_source_to_dict(r) for r in rows]


def marcar_knowledge_source_status(source_id: int, status: str, error_message: Optional[str] = None) -> None:
    with Session(engine) as session:
        row = session.get(KnowledgeSource, source_id)
        if not row:
            return
        row.status = status
        row.error_message = error_message
        row.updated_at = datetime.now()
        session.add(row)
        session.commit()


def salvar_extracao_knowledge_source(
    source_id: int,
    texto: str,
    sections: list,
    char_count: int,
    section_count: int,
) -> Optional[dict]:
    """Persiste o resultado da extração determinística (Fase 1) e marca
    status=EXTRACTED. `sections` é uma lista de dicts (já serializável)."""
    with Session(engine) as session:
        row = session.get(KnowledgeSource, source_id)
        if not row:
            return None
        row.texto_extraido = texto
        row.sections_json = json.dumps(sections, ensure_ascii=False)
        row.char_count = char_count
        row.section_count = section_count
        row.status = "EXTRACTED"
        row.error_message = None
        row.processed_at = datetime.now()
        row.updated_at = datetime.now()
        session.add(row)
        session.commit()
        session.refresh(row)
        return _knowledge_source_to_dict(row)


# ─────────────────────────────────────────────
# KNOWLEDGE COMPILER — Knowledge Items (Fase 2)
# ─────────────────────────────────────────────
def _knowledge_item_to_dict(row: "KnowledgeItem") -> dict:
    return {
        "id": row.id,
        "source_id": row.source_id,
        "item_type": row.item_type,
        "title": row.title,
        "content": row.content,
        "metadata": json.loads(row.metadata_json) if row.metadata_json else {},
        "tags": json.loads(row.tags_json) if row.tags_json else [],
        "confidence": row.confidence,
        "status": row.status,
        "possivel_duplicado_de": row.possivel_duplicado_de,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def criar_knowledge_item(source_id: int, item: dict) -> Optional[dict]:
    """Insere um KnowledgeItem (dict com item_type/title/content/metadata/
    tags/confidence/possivel_duplicado_de opcionais). Retorna None (nunca
    lança) se o item for malformado — um item ruim não derruba o lote."""
    try:
        with Session(engine) as session:
            row = KnowledgeItem(
                source_id=source_id,
                item_type=item["item_type"],
                title=item["title"],
                content=item["content"],
                metadata_json=json.dumps(item.get("metadata") or {}, ensure_ascii=False),
                tags_json=json.dumps(item.get("tags") or [], ensure_ascii=False),
                confidence=float(item.get("confidence", 0.75)),
                possivel_duplicado_de=item.get("possivel_duplicado_de"),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return _knowledge_item_to_dict(row)
    except Exception as exc:
        logger.warning("[KnowledgeCompiler] Falha ao salvar item '%s': %s", item.get("title"), exc)
        return None


def criar_knowledge_items_em_lote(source_id: int, itens: list) -> list:
    """Insere uma lista de candidatos a KnowledgeItem — ver criar_knowledge_item()."""
    criados = [criar_knowledge_item(source_id, item) for item in itens]
    return [c for c in criados if c is not None]


def obter_knowledge_item(item_id: int) -> Optional[dict]:
    with Session(engine) as session:
        row = session.get(KnowledgeItem, item_id)
        return _knowledge_item_to_dict(row) if row else None


def listar_knowledge_items(
    source_id: Optional[int] = None,
    item_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 200,
) -> List[dict]:
    with Session(engine) as session:
        stmt = select(KnowledgeItem)
        if source_id is not None:
            stmt = stmt.where(KnowledgeItem.source_id == source_id)
        if item_type:
            stmt = stmt.where(KnowledgeItem.item_type == item_type)
        if status:
            stmt = stmt.where(KnowledgeItem.status == status)
        stmt = stmt.order_by(KnowledgeItem.created_at.desc()).limit(limit)
        rows = session.exec(stmt).all()
        return [_knowledge_item_to_dict(r) for r in rows]


def contar_knowledge_items_por_tipo(source_id: int) -> dict:
    with Session(engine) as session:
        stmt = (
            select(KnowledgeItem.item_type, func.count(KnowledgeItem.id))
            .where(KnowledgeItem.source_id == source_id)
            .group_by(KnowledgeItem.item_type)
        )
        return {tipo: total for tipo, total in session.exec(stmt).all()}


def atualizar_status_knowledge_item(item_id: int, status: str) -> Optional[dict]:
    with Session(engine) as session:
        row = session.get(KnowledgeItem, item_id)
        if not row:
            return None
        row.status = status
        row.updated_at = datetime.now()
        session.add(row)
        session.commit()
        session.refresh(row)
        return _knowledge_item_to_dict(row)


def salvar_embedding_knowledge_item(item_id: int, vector: list, provider: str, model: str, dimension: int) -> bool:
    with Session(engine) as session:
        row = session.get(KnowledgeItem, item_id)
        if not row:
            return False
        row.embedding_json = json.dumps(vector)
        row.embedding_provider = provider
        row.embedding_model = model
        row.embedding_dim = dimension
        row.updated_at = datetime.now()
        session.add(row)
        session.commit()
        return True


def buscar_knowledge_item_similar(item_type: str, vector: list, threshold: float = 0.92) -> Optional[dict]:
    """Retorna o KnowledgeItem existente mais parecido (mesmo item_type,
    com embedding salvo) se a similaridade de cosseno for >= threshold,
    ou None. Usado para sinalizar (nunca bloquear) possiveis duplicatas —
    ver criar_knowledge_items_em_lote/possivel_duplicado_de."""
    import numpy as np
    from services.embeddings import cosine_top_k

    with Session(engine) as session:
        stmt = select(KnowledgeItem).where(
            KnowledgeItem.item_type == item_type,
            KnowledgeItem.embedding_json.is_not(None),
        )
        candidatos = session.exec(stmt).all()
        if not candidatos:
            return None

        matriz = np.array([json.loads(c.embedding_json) for c in candidatos], dtype=np.float32)
        vec = np.array(vector, dtype=np.float32)
        if matriz.shape[1] != vec.shape[0]:
            return None

        (idx, sim), = cosine_top_k(vec, matriz, 1)
        if sim < threshold:
            return None
        return {**_knowledge_item_to_dict(candidatos[idx]), "similarity": round(sim, 4)}


def buscar_conhecimento_compilado_similar(query: str, top_k: int = 2, similarity_min: float = 0.30) -> Optional[str]:
    """Busca por texto livre entre KnowledgeItems aprovados (status=APPROVED)
    e retorna um bloco de texto pronto para injeção em prompt, ou None se
    vazio/sem match — mesmo formato de agent/sales_memory.py::
    buscar_contexto_para_reuniao (Knowledge Compiler Fase 3).

    Sync (nao async) de proposito: mesmo padrao de
    buscar_contexto_para_reuniao, que tambem e chamada sem await de dentro
    de agent/multiagente/orquestrador.py (funcao async)."""
    import numpy as np
    from services.embeddings import cosine_top_k, get_embedding_provider

    try:
        provider = get_embedding_provider()
    except Exception as e:
        logger.debug("[KnowledgeCompiler] Provedor de embedding indisponível: %s", e)
        return None

    resultado = provider.embed(query[:4000])
    if not resultado:
        return None

    with Session(engine) as session:
        stmt = select(KnowledgeItem).where(
            KnowledgeItem.status == "APPROVED",
            KnowledgeItem.embedding_json.is_not(None),
        )
        candidatos = session.exec(stmt).all()
        if not candidatos:
            return None

        try:
            matriz = np.array([json.loads(c.embedding_json) for c in candidatos], dtype=np.float32)
            vec = np.array(resultado.vector, dtype=np.float32)
            if matriz.shape[1] != vec.shape[0]:
                return None
        except Exception:
            return None

        top = cosine_top_k(vec, matriz, min(top_k, len(candidatos)))
        selecionados = [candidatos[idx] for idx, sim in top if sim >= similarity_min]
        if not selecionados:
            return None

        blocos = [
            f"[{item.item_type}] {item.title}: {item.content}"
            for item in selecionados
        ]
        return "CONHECIMENTO COMERCIAL RELEVANTE (Biblioteca de Inteligência):\n" + "\n".join(blocos)


def _sales_event_to_dict(row: "SalesEvent") -> dict:
    return {
        "id": row.id,
        "meeting_id": row.meeting_id,
        "opportunity_id": row.opportunity_id,
        "client_id": row.client_id,
        "seller_id": row.seller_id,
        "event_type": row.event_type,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "speaker": row.speaker,
        "evidence_quote": row.evidence_quote,
        "source": row.source,
        "confidence": row.confidence,
        "metadata": json.loads(row.metadata_json) if row.metadata_json else {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def criar_sales_event(
    *,
    meeting_id: str,
    event_type: str,
    source: str = "conversation",
    confidence: float = 1.0,
    evidence_quote: Optional[str] = None,
    opportunity_id: Optional[int] = None,
    client_id: Optional[str] = None,
    seller_id: Optional[str] = None,
    speaker: Optional[str] = None,
    timestamp: Optional[datetime] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """Cria e persiste um SalesEvent (Fase 1 / Tarefa 1.1 do "PROMPT
    MESTRE — SALE-IA V2"). Valida via agent/sales_event_rules antes de
    tocar no banco — ValueError propaga para o chamador (dado de domínio,
    nunca falha silenciosa como AiUsageEvent/KnowledgeItem)."""
    from agent.sales_event_rules import validar_sales_event

    dados = {
        "meeting_id": meeting_id,
        "event_type": event_type,
        "source": source,
        "confidence": confidence,
        "evidence_quote": evidence_quote,
    }
    validar_sales_event(dados)

    with Session(engine) as session:
        row = SalesEvent(
            meeting_id=meeting_id,
            event_type=event_type,
            source=source,
            confidence=confidence,
            evidence_quote=evidence_quote,
            opportunity_id=opportunity_id,
            client_id=client_id,
            seller_id=seller_id,
            speaker=speaker,
            timestamp=timestamp or datetime.now(),
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _sales_event_to_dict(row)


def obter_sales_event(event_id: int) -> Optional[dict]:
    with Session(engine) as session:
        row = session.get(SalesEvent, event_id)
        return _sales_event_to_dict(row) if row else None


def listar_sales_events(
    meeting_id: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 200,
) -> List[dict]:
    with Session(engine) as session:
        stmt = select(SalesEvent)
        if meeting_id:
            stmt = stmt.where(SalesEvent.meeting_id == meeting_id)
        if event_type:
            stmt = stmt.where(SalesEvent.event_type == event_type)
        stmt = stmt.order_by(SalesEvent.timestamp.asc()).limit(limit)
        rows = session.exec(stmt).all()
        return [_sales_event_to_dict(r) for r in rows]


def _sales_evidence_to_dict(row: "SalesEvidence") -> dict:
    return {
        "id": row.id,
        "meeting_id": row.meeting_id,
        "type": row.type,
        "quote": row.quote,
        "speaker": row.speaker,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "confidence": row.confidence,
        "source": row.source,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def criar_sales_evidence(
    *,
    meeting_id: str,
    type: str,
    quote: str,
    source: str = "conversation",
    confidence: float = 1.0,
    speaker: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> dict:
    """Cria e persiste um SalesEvidence (Fase 1 / Tarefa 1.2 do "PROMPT
    MESTRE — SALE-IA V2"). Valida via agent/sales_evidence_rules antes de
    tocar no banco — ValueError propaga para o chamador: uma hipótese
    sem a fala que a sustenta nunca é persistida (mesma convenção de
    criar_sales_event, Tarefa 1.1)."""
    from agent.sales_evidence_rules import validar_sales_evidence

    dados = {"meeting_id": meeting_id, "type": type, "quote": quote, "confidence": confidence}
    validar_sales_evidence(dados)

    with Session(engine) as session:
        row = SalesEvidence(
            meeting_id=meeting_id,
            type=type,
            quote=quote,
            source=source,
            confidence=confidence,
            speaker=speaker,
            timestamp=timestamp or datetime.now(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _sales_evidence_to_dict(row)


def obter_sales_evidence(evidence_id: int) -> Optional[dict]:
    with Session(engine) as session:
        row = session.get(SalesEvidence, evidence_id)
        return _sales_evidence_to_dict(row) if row else None


def listar_sales_evidences(
    meeting_id: Optional[str] = None,
    type: Optional[str] = None,
    limit: int = 200,
) -> List[dict]:
    with Session(engine) as session:
        stmt = select(SalesEvidence)
        if meeting_id:
            stmt = stmt.where(SalesEvidence.meeting_id == meeting_id)
        if type:
            stmt = stmt.where(SalesEvidence.type == type)
        stmt = stmt.order_by(SalesEvidence.timestamp.asc()).limit(limit)
        rows = session.exec(stmt).all()
        return [_sales_evidence_to_dict(r) for r in rows]


def _opportunity_to_dict(row: "Opportunity") -> dict:
    return {
        "id": row.id,
        "client_id": row.client_id,
        "seller_id": row.seller_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "stage": row.stage,
        "status": row.status,
        "estimated_value": row.estimated_value,
        "won_at": row.won_at.isoformat() if row.won_at else None,
        "lost_at": row.lost_at.isoformat() if row.lost_at else None,
        "loss_reason": row.loss_reason,
        "outcome_value": row.outcome_value,
        "product": row.product,
        "close_date": row.close_date.isoformat() if row.close_date else None,
        "cycle_days": row.cycle_days,
        "competitor": row.competitor,
    }


def criar_opportunity(
    *,
    client_id: str,
    seller_id: str,
    stage: str = "",
    estimated_value: Optional[float] = None,
) -> dict:
    """Cria uma Opportunity (Fase 2 / Tarefa 2.1 do "PROMPT MESTRE —
    SALE-IA V2"). `status` nasce sempre "open" — mudar para won/lost é
    responsabilidade de `atualizar_status_opportunity()`."""
    with Session(engine) as session:
        row = Opportunity(
            client_id=client_id,
            seller_id=seller_id,
            stage=stage,
            status="open",
            estimated_value=estimated_value,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        # Tarefa B2: estágio inicial entra no histórico.
        session.add(OpportunityStageHistory(opportunity_id=row.id, stage=stage, changed_at=row.created_at))
        session.commit()
        return _opportunity_to_dict(row)


def obter_opportunity(opportunity_id: int) -> Optional[dict]:
    with Session(engine) as session:
        row = session.get(Opportunity, opportunity_id)
        return _opportunity_to_dict(row) if row else None


def listar_opportunities(
    client_id: Optional[str] = None,
    seller_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 200,
) -> List[dict]:
    with Session(engine) as session:
        stmt = select(Opportunity)
        if client_id:
            stmt = stmt.where(Opportunity.client_id == client_id)
        if seller_id:
            stmt = stmt.where(Opportunity.seller_id == seller_id)
        if status:
            stmt = stmt.where(Opportunity.status == status)
        stmt = stmt.order_by(Opportunity.created_at.desc()).limit(limit)
        rows = session.exec(stmt).all()
        return [_opportunity_to_dict(r) for r in rows]


def atualizar_stage_opportunity(opportunity_id: int, stage: str) -> Optional[dict]:
    """Atualiza só o `stage` (string livre, sem enum — mesma decisão da
    Fase 2) — nunca mexe em `status`/`won_at`/`lost_at`, que são
    exclusividade de `atualizar_status_opportunity()`."""
    with Session(engine) as session:
        row = session.get(Opportunity, opportunity_id)
        if not row:
            return None
        agora = datetime.now()
        if (row.stage or "") != (stage or ""):
            # Tarefa B2: histórico de estágio. Oportunidade anterior à B2
            # (sem histórico) ganha antes a linha do estágio original.
            tem_historico = session.exec(
                select(OpportunityStageHistory.id).where(OpportunityStageHistory.opportunity_id == opportunity_id)
            ).first()
            if tem_historico is None:
                session.add(OpportunityStageHistory(
                    opportunity_id=opportunity_id, stage=row.stage or "", changed_at=row.created_at or agora,
                ))
            session.add(OpportunityStageHistory(opportunity_id=opportunity_id, stage=stage, changed_at=agora))
        row.stage = stage
        row.updated_at = agora
        session.add(row)
        session.commit()
        session.refresh(row)
        return _opportunity_to_dict(row)


def listar_stage_history_opportunity(opportunity_id: int) -> List[dict]:
    """Histórico de estágio da oportunidade (Tarefa B2), do mais antigo ao
    mais recente. Vazio para oportunidade anterior à B2 que nunca mudou
    de estágio — o chamador trata como "estágio desconhecido no tempo"."""
    with Session(engine) as session:
        rows = session.exec(
            select(OpportunityStageHistory)
            .where(OpportunityStageHistory.opportunity_id == opportunity_id)
            .order_by(OpportunityStageHistory.changed_at.asc(), OpportunityStageHistory.id.asc())
        ).all()
        return [
            {"stage": r.stage, "changed_at": r.changed_at.isoformat() if r.changed_at else None}
            for r in rows
        ]


def atualizar_status_opportunity(
    opportunity_id: int,
    status: str,
    loss_reason: Optional[str] = None,
    *,
    value: Optional[float] = None,
    product: Optional[str] = None,
    close_date: Optional[datetime] = None,
    competitor: Optional[str] = None,
) -> Optional[dict]:
    """Atualiza o status (open/won/lost/abandoned, Fase 8 / Tarefa 8.1
    adiciona "abandoned") — grava won_at/lost_at automaticamente na
    primeira vez que o status muda para won/lost (nunca sobrescreve um
    won_at/lost_at já gravado, mesmo que o status seja setado de novo).

    Para "won": `value`/`product`/`close_date` são obrigatórios
    (validados por `agent.outcome_rules.validar_dados_won`); `close_date`
    default é `won_at` quando omitido. `cycle_days` é sempre calculado
    (`agent.outcome_rules.calcular_cycle_days`), nunca aceito como
    input. Para "lost": `loss_reason` é obrigatório (validado por
    `validar_dados_lost`); `competitor` é opcional (nem toda perda vai
    para um concorrente identificado). "abandoned" não exige nenhum
    dado extra — mesmo padrão de "não inventar requisito não pedido"
    das fases anteriores."""
    from agent.opportunity_memory_rules import validar_status
    from agent.outcome_rules import calcular_cycle_days, validar_dados_lost, validar_dados_won

    validar_status(status)

    with Session(engine) as session:
        row = session.get(Opportunity, opportunity_id)
        if not row:
            return None

        if status == "won" and row.won_at is None:
            efetiva_close_date = close_date or datetime.now()
            validar_dados_won({"value": value, "product": product, "close_date": efetiva_close_date})
            row.won_at = efetiva_close_date
            row.outcome_value = value
            row.product = product
            row.close_date = efetiva_close_date
            row.cycle_days = calcular_cycle_days(row.created_at, efetiva_close_date)
        if status == "lost" and row.lost_at is None:
            validar_dados_lost({"reason": loss_reason, "competitor": competitor})
            row.lost_at = datetime.now()
            row.loss_reason = loss_reason
            row.competitor = competitor

        row.status = status
        row.updated_at = datetime.now()
        session.add(row)
        session.commit()
        session.refresh(row)
        return _opportunity_to_dict(row)


def vincular_meeting_opportunity(meeting_id: str, opportunity_id: int) -> bool:
    """Associa uma MeetingMemory já existente a uma Opportunity —
    MeetingMemory continua isolada (transcrição/diagnóstico/eventos
    próprios), só ganha a referência de qual oportunidade ela alimenta."""
    with Session(engine) as session:
        row = session.exec(select(MeetingMemory).where(MeetingMemory.meeting_id == meeting_id)).first()
        if not row:
            return False
        row.opportunity_id = opportunity_id
        row.updated_at = datetime.now()
        session.add(row)
        session.commit()
        return True


def listar_meetings_da_opportunity(opportunity_id: int) -> List[dict]:
    with Session(engine) as session:
        stmt = (
            select(MeetingMemory)
            .where(MeetingMemory.opportunity_id == opportunity_id)
            .order_by(MeetingMemory.created_at.asc())
        )
        rows = session.exec(stmt).all()
        return [
            {
                "meeting_id": r.meeting_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]


_OPPORTUNITY_MEMORY_CATEGORY_TO_COLUMN = {
    "pain_points": "pain_points_json",
    "business_impact": "business_impact_json",
    "goals": "goals_json",
    "objections": "objections_json",
    "competitors": "competitors_json",
    "decision_process": "decision_process_json",
    "stakeholders": "stakeholders_json",
    "champion": "champion_json",
    "economic_buyer": "economic_buyer_json",
    "metrics": "metrics_json",
    "next_steps": "next_steps_json",
    "risks": "risks_json",
    "unknowns": "unknowns_json",
}


def _opportunity_memory_to_dict(row: "OpportunityMemory") -> dict:
    return {
        "id": row.id,
        "opportunity_id": row.opportunity_id,
        **{
            categoria: json.loads(getattr(row, coluna))
            for categoria, coluna in _OPPORTUNITY_MEMORY_CATEGORY_TO_COLUMN.items()
        },
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def obter_opportunity_memory(opportunity_id: int, criar_se_ausente: bool = True) -> Optional[dict]:
    """Retorna a OpportunityMemory da oportunidade, criando uma vazia
    (1:1, mesmo padrão de MeetingMemory por meeting_id) se ainda não
    existir e criar_se_ausente=True."""
    with Session(engine) as session:
        row = session.exec(
            select(OpportunityMemory).where(OpportunityMemory.opportunity_id == opportunity_id)
        ).first()
        if not row:
            if not criar_se_ausente:
                return None
            row = OpportunityMemory(opportunity_id=opportunity_id)
            session.add(row)
            session.commit()
            session.refresh(row)
        return _opportunity_memory_to_dict(row)


def registrar_conhecimento_opportunity(
    opportunity_id: int,
    categoria: str,
    *,
    meeting_id: str,
    valor,
    campo: Optional[str] = None,
    evidence: Optional[str] = None,
    confidence: float = 1.0,
    status: Optional[str] = None,
) -> dict:
    """Adiciona um insight a uma categoria da OpportunityMemory (Fase 2 /
    Tarefa 2.1). Dado de domínio — ValueError propaga em categoria
    desconhecida ou confidence/meeting_id inválidos (mesma convenção de
    criar_sales_event/criar_sales_evidence). Nunca sobrescreve/remove um
    insight anterior — ver agent/opportunity_memory_rules.py::
    adicionar_insight.

    Retorna {"insights": [...lista completa da categoria...],
    "contradicao": {...} ou None}."""
    from agent.opportunity_memory_rules import adicionar_insight

    if categoria not in _OPPORTUNITY_MEMORY_CATEGORY_TO_COLUMN:
        raise ValueError(
            f"categoria inválida: {categoria!r} (esperado um de {sorted(_OPPORTUNITY_MEMORY_CATEGORY_TO_COLUMN)})"
        )
    coluna = _OPPORTUNITY_MEMORY_CATEGORY_TO_COLUMN[categoria]

    with Session(engine) as session:
        row = session.exec(
            select(OpportunityMemory).where(OpportunityMemory.opportunity_id == opportunity_id)
        ).first()
        if not row:
            row = OpportunityMemory(opportunity_id=opportunity_id)
            session.add(row)
            session.commit()
            session.refresh(row)

        insights_existentes = json.loads(getattr(row, coluna))
        nova_lista, contradicao = adicionar_insight(
            insights_existentes,
            meeting_id=meeting_id,
            valor=valor,
            campo=campo,
            evidence=evidence,
            confidence=confidence,
            status=status,
        )

        setattr(row, coluna, json.dumps(nova_lista, ensure_ascii=False))
        row.updated_at = datetime.now()
        session.add(row)
        session.commit()

        return {"insights": nova_lista, "contradicao": contradicao}


def _opportunity_graph_edge_to_dict(row: "OpportunityGraphEdge") -> dict:
    return {
        "id": row.id,
        "opportunity_id": row.opportunity_id,
        "from_type": row.from_type,
        "from_id": row.from_id,
        "to_type": row.to_type,
        "to_id": row.to_id,
        "relation": row.relation,
        "source": row.source,
        "evidence": row.evidence,
        "confidence": row.confidence,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def criar_aresta_opportunity_graph(
    opportunity_id: int,
    *,
    from_type: str,
    from_id,
    to_type: str,
    to_id,
    relation: str,
    evidence: str,
    source: str = "conversation",
    confidence: float = 1.0,
    timestamp: Optional[datetime] = None,
) -> dict:
    """Cria uma aresta do Opportunity Graph (Fase 2 / Tarefa 2.2 do
    "PROMPT MESTRE — SALE-IA V2"). Valida via agent/opportunity_graph_rules
    antes de tocar no banco — ValueError propaga para o chamador (mesma
    convenção de dado de domínio da Tarefa 1.1/1.2/2.1). `from_id`/`to_id`
    de nós PAIN/IMPACT/GOAL/... são o `id` do insight correspondente em
    `OpportunityMemory` (ver `registrar_conhecimento_opportunity`), nunca
    um dado duplicado."""
    from agent.opportunity_graph_rules import validar_aresta

    dados = {
        "from_type": from_type, "from_id": from_id, "to_type": to_type, "to_id": to_id,
        "relation": relation, "evidence": evidence, "confidence": confidence,
    }
    validar_aresta(dados)

    with Session(engine) as session:
        row = OpportunityGraphEdge(
            opportunity_id=opportunity_id,
            from_type=from_type,
            from_id=str(from_id),
            to_type=to_type,
            to_id=str(to_id),
            relation=relation,
            source=source,
            evidence=evidence,
            confidence=confidence,
            timestamp=timestamp or datetime.now(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _opportunity_graph_edge_to_dict(row)


def listar_arestas_opportunity(
    opportunity_id: int,
    node_type: Optional[str] = None,
    node_id: Optional[str] = None,
) -> List[dict]:
    """Lista as arestas de uma Opportunity — opcionalmente filtradas por
    um nó especifico (`node_type`+`node_id`), em qualquer direção
    (from ou to), mesmo padrão de agent/knowledge_graph.py::buscar_conexoes."""
    with Session(engine) as session:
        stmt = select(OpportunityGraphEdge).where(OpportunityGraphEdge.opportunity_id == opportunity_id)
        if node_type and node_id is not None:
            node_id = str(node_id)
            stmt = stmt.where(
                ((OpportunityGraphEdge.from_type == node_type) & (OpportunityGraphEdge.from_id == node_id))
                | ((OpportunityGraphEdge.to_type == node_type) & (OpportunityGraphEdge.to_id == node_id))
            )
        stmt = stmt.order_by(OpportunityGraphEdge.created_at.asc())
        rows = session.exec(stmt).all()
        return [_opportunity_graph_edge_to_dict(r) for r in rows]


def _seller_dna_observacao_to_dict(row: "SellerDnaObservacao") -> dict:
    return {
        "id": row.id,
        "seller_id": row.seller_id,
        "meeting_id": row.meeting_id,
        "campo": row.campo,
        "valor": row.valor,
        "evidence_quote": row.evidence_quote,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def criar_seller_dna_observacao(
    seller_id: str,
    meeting_id: str,
    campo: str,
    valor: str,
    evidence_quote: str,
) -> dict:
    """Persiste 1 observação de estilo do vendedor (Bloco 5 / Tarefa
    5.1). Dado de domínio — propaga `ValueError` em campo fora do
    vocabulário `agent/seller_dna_rules.py::SELLER_DNA_CAMPOS` ou
    campo obrigatório vazio, mesma convenção de `SalesEvent`/
    `SalesEvidence`/`RecommendationEvent` (nunca falha silenciosa como
    `AiUsageEvent`)."""
    from agent.seller_dna_rules import SELLER_DNA_CAMPOS

    if campo not in SELLER_DNA_CAMPOS:
        raise ValueError(f"campo inválido: {campo!r} (esperado um de {SELLER_DNA_CAMPOS})")
    if not (seller_id or "").strip():
        raise ValueError("seller_id obrigatório e não pode ser vazio")
    if not (meeting_id or "").strip():
        raise ValueError("meeting_id obrigatório e não pode ser vazio")
    if not (valor or "").strip():
        raise ValueError("valor obrigatório e não pode ser vazio")
    if not (evidence_quote or "").strip():
        raise ValueError("evidence_quote obrigatório e não pode ser vazio")

    with Session(engine) as session:
        row = SellerDnaObservacao(
            seller_id=seller_id,
            meeting_id=meeting_id,
            campo=campo,
            valor=valor,
            evidence_quote=evidence_quote,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _seller_dna_observacao_to_dict(row)


def listar_seller_dna_observacoes(seller_id: str) -> List[dict]:
    """Todas as observações já persistidas de um vendedor, ordenadas da
    mais antiga pra mais recente — insumo de `agent/seller_dna_rules.py::
    agregar_observacoes_por_campo()`, nunca consumido diretamente pelo
    SalesReasoningEngine."""
    with Session(engine) as session:
        stmt = (
            select(SellerDnaObservacao)
            .where(SellerDnaObservacao.seller_id == seller_id)
            .order_by(SellerDnaObservacao.created_at.asc())
        )
        rows = session.exec(stmt).all()
        return [_seller_dna_observacao_to_dict(r) for r in rows]


def _recommendation_event_to_dict(row: "RecommendationEvent") -> dict:
    return {
        "id": row.id,
        "meeting_id": row.meeting_id,
        "opportunity_id": row.opportunity_id,
        "strategy": row.strategy,
        "recommendation": row.recommendation,
        "reason": row.reason,
        "shown_at": row.shown_at.isoformat() if row.shown_at else None,
        "used_at": row.used_at.isoformat() if row.used_at else None,
        "seller_action": row.seller_action,
        "outcome_window": row.outcome_window,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        **{k: getattr(row, k) for k in VERSOES_INTELIGENCIA},
    }


def criar_recommendation_event(
    *,
    meeting_id: str,
    strategy: str,
    recommendation: str,
    reason: str,
    opportunity_id: Optional[int] = None,
    outcome_window: Optional[str] = None,
    shown_at: Optional[datetime] = None,
    versoes: Optional[dict] = None,
) -> dict:
    """Cria e persiste um RecommendationEvent (Fase 10 / Tarefa 10.1 do
    "PROMPT MESTRE — SALE-IA V2"). Valida via
    agent/recommendation_rules antes de tocar no banco — ValueError
    propaga para o chamador (dado de domínio, mesma disciplina de
    `criar_sales_event()`/`criar_sales_evidence()`, Fase 1)."""
    from agent.recommendation_rules import validar_recommendation_event

    dados = {
        "meeting_id": meeting_id,
        "strategy": strategy,
        "recommendation": recommendation,
        "reason": reason,
    }
    validar_recommendation_event(dados)

    with Session(engine) as session:
        row = RecommendationEvent(
            meeting_id=meeting_id,
            opportunity_id=opportunity_id,
            strategy=strategy,
            recommendation=recommendation,
            reason=reason,
            outcome_window=outcome_window,
            shown_at=shown_at or datetime.now(),
            **_versoes_validas(versoes),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _recommendation_event_to_dict(row)


def obter_recommendation_event(event_id: int) -> Optional[dict]:
    with Session(engine) as session:
        row = session.get(RecommendationEvent, event_id)
        return _recommendation_event_to_dict(row) if row else None


def listar_recommendation_events(
    meeting_id: Optional[str] = None,
    opportunity_id: Optional[int] = None,
    limit: int = 200,
) -> List[dict]:
    with Session(engine) as session:
        stmt = select(RecommendationEvent)
        if meeting_id:
            stmt = stmt.where(RecommendationEvent.meeting_id == meeting_id)
        if opportunity_id is not None:
            stmt = stmt.where(RecommendationEvent.opportunity_id == opportunity_id)
        stmt = stmt.order_by(RecommendationEvent.shown_at.asc()).limit(limit)
        rows = session.exec(stmt).all()
        return [_recommendation_event_to_dict(r) for r in rows]


def listar_recommendation_events_respondidos(
    meeting_id: Optional[str] = None,
    limit: int = 1000,
) -> List[dict]:
    """`RecommendationEvent`s com `seller_action` já registrado — o
    dado real que `agent/recommendation_usage_rules.py::
    detectar_uso_recomendacao()` (Tarefa 10.2) precisa pra classificar
    o estado de uso. Usado pelo recálculo em lote da Fase 25
    (`recommendation_quality`, `scripts/recommendation_quality_run.py`)."""
    with Session(engine) as session:
        stmt = select(RecommendationEvent).where(RecommendationEvent.seller_action.is_not(None))
        if meeting_id:
            stmt = stmt.where(RecommendationEvent.meeting_id == meeting_id)
        stmt = stmt.order_by(RecommendationEvent.shown_at.asc()).limit(limit)
        rows = session.exec(stmt).all()
        return [_recommendation_event_to_dict(r) for r in rows]


def registrar_uso_recommendation_event(
    event_id: int,
    seller_action: str,
    used_at: Optional[datetime] = None,
) -> Optional[dict]:
    """Grava `seller_action`/`used_at` numa recomendação já existente —
    persistência mecânica, não decide USED/PARTIALLY_USED/IGNORED
    (essa classificação é a Tarefa 10.2, não construída nesta rodada).
    Nunca sobrescreve um `used_at` já gravado, mesmo padrão de
    `won_at`/`lost_at` em `Opportunity` (Fase 2/8)."""
    if not seller_action:
        raise ValueError("seller_action é obrigatório")

    with Session(engine) as session:
        row = session.get(RecommendationEvent, event_id)
        if not row:
            return None
        if row.used_at is None:
            row.used_at = used_at or datetime.now()
            row.seller_action = seller_action
        session.add(row)
        session.commit()
        session.refresh(row)
        return _recommendation_event_to_dict(row)


class AuditTrailEntry(SQLModel, table=True):
    """Registro de auditoria genérico ("PROMPT MESTRE — SALE-IA V2",
    Fase 18 / Tarefa 18.4 — fecha a Fase 18, Segurança) — schema literal
    do prompt mestre: quem (`actor`), quando (`timestamp`), ação
    (`action`), motivo (`reason`), dados usados (`data_used_json`),
    modelo (`model`), versão do prompt (`prompt_version`), versão da
    regra (`rule_version`), resultado (`result`). "Especialmente para
    recomendações autônomas futuras" — a `AutonomyPolicy` da Fase 17
    continua dormente (nenhum nível de autonomia ativo em produção);
    esta tabela só prepara o schema/persistência pra quando isso mudar.

    `meeting_id`/`opportunity_id` ficam soltos (sem FK), mesmo padrão de
    `SalesEvent`/`RecommendationEvent` — nem toda ação auditada está
    ligada a uma reunião/oportunidade específica (ex.: uma ação
    administrativa). `model`/`prompt_version`/`rule_version` são
    opcionais — nem toda ação auditada envolve IA.

    Dado de domínio: validação em
    `agent/audit_trail_rules.py::validar_audit_trail_entry`,
    `criar_audit_trail_entry()` propaga `ValueError` em dado inválido,
    nunca falha silenciosamente como `AiUsageEvent`/`KnowledgeItem` —
    um audit trail que falha silenciosamente não serve pra auditoria
    nenhuma."""

    __tablename__ = "audit_trail_entries"

    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: Optional[str] = Field(default=None, sa_column=Column(String(200), index=True))
    opportunity_id: Optional[int] = Field(default=None, sa_column=Column(Integer, index=True))
    actor: str = Field(sa_column=Column(String(120), index=True, nullable=False))
    timestamp: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))
    action: str = Field(sa_column=Column(String(120), index=True, nullable=False))
    reason: str = Field(sa_column=Column(Text, nullable=False))
    data_used_json: Optional[str] = Field(default=None, sa_column=Column(Text))
    model: Optional[str] = Field(default=None, sa_column=Column(String(80)))
    prompt_version: Optional[str] = Field(default=None, sa_column=Column(String(40)))
    rule_version: Optional[str] = Field(default=None, sa_column=Column(String(40)))
    result: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))
    # Tarefa D6 (seção 34): mesmas 4 colunas de RecommendationEvent.
    reasoning_engine_version: Optional[str] = Field(default=None, sa_column=Column(String(80)))
    policy_version: Optional[str] = Field(default=None, sa_column=Column(String(80)))
    knowledge_version: Optional[str] = Field(default=None, sa_column=Column(String(80)))
    model_version: Optional[str] = Field(default=None, sa_column=Column(String(80)))


# Tarefa D6: as 4 versões da inteligência (seção 34 do prompt mestre),
# gravadas em RecommendationEvent e AuditTrailEntry.
VERSOES_INTELIGENCIA = ("reasoning_engine_version", "policy_version", "knowledge_version", "model_version")


def _versoes_validas(versoes: Optional[dict]) -> dict:
    """Só as 4 chaves conhecidas, cortadas no tamanho da coluna."""
    return {
        k: (str(versoes[k])[:80] if versoes.get(k) is not None else None)
        for k in VERSOES_INTELIGENCIA if versoes and k in versoes
    }


def migrar_colunas_versionamento() -> list:
    """Tarefa D6: adiciona as 4 colunas de versão em
    `recommendation_events`/`audit_trail_entries` quando faltarem —
    `create_all()` não migra coluna em tabela já existente (mesmo
    problema das V.1.4.54/1.4.100). Idempotente, roda no startup dentro
    do lock de DDL da D8. Funciona em MySQL e SQLite. Retorna o que
    adicionou."""
    from sqlalchemy import inspect

    adicionadas = []
    inspetor = inspect(engine)
    tabelas = set(inspetor.get_table_names())
    with engine.begin() as conn:
        for tabela in ("recommendation_events", "audit_trail_entries"):
            if tabela not in tabelas:
                continue
            existentes = {c["name"] for c in inspetor.get_columns(tabela)}
            for coluna in VERSOES_INTELIGENCIA:
                if coluna in existentes:
                    continue
                try:
                    conn.execute(text(f"ALTER TABLE {tabela} ADD COLUMN {coluna} VARCHAR(80) NULL"))
                    adicionadas.append(f"{tabela}.{coluna}")
                except Exception as exc:
                    if "1060" in str(exc) or "duplicate column" in str(exc).lower():
                        continue  # outro worker já adicionou
                    raise
    if adicionadas:
        logger.info("Colunas de versionamento adicionadas: %s", ", ".join(adicionadas))
    return adicionadas


def _audit_trail_entry_to_dict(row: "AuditTrailEntry") -> dict:
    return {
        "id": row.id,
        "meeting_id": row.meeting_id,
        "opportunity_id": row.opportunity_id,
        "actor": row.actor,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "action": row.action,
        "reason": row.reason,
        "data_used": json.loads(row.data_used_json) if row.data_used_json else None,
        "model": row.model,
        "prompt_version": row.prompt_version,
        "rule_version": row.rule_version,
        "result": row.result,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        **{k: getattr(row, k) for k in VERSOES_INTELIGENCIA},
    }


def criar_audit_trail_entry(
    *,
    actor: str,
    action: str,
    reason: str,
    result: str,
    meeting_id: Optional[str] = None,
    opportunity_id: Optional[int] = None,
    data_used: Optional[dict] = None,
    model: Optional[str] = None,
    prompt_version: Optional[str] = None,
    rule_version: Optional[str] = None,
    timestamp: Optional[datetime] = None,
    versoes: Optional[dict] = None,
) -> dict:
    """Cria e persiste um AuditTrailEntry (Fase 18 / Tarefa 18.4). Valida
    via agent/audit_trail_rules antes de tocar no banco — ValueError
    propaga para o chamador (dado de domínio, nunca falha silenciosa
    como AiUsageEvent/KnowledgeItem). `versoes` (Tarefa D6): as 4
    versões da inteligência, ver `VERSOES_INTELIGENCIA`."""
    from agent.audit_trail_rules import validar_audit_trail_entry

    dados = {"actor": actor, "action": action, "reason": reason, "result": result}
    validar_audit_trail_entry(dados)

    with Session(engine) as session:
        row = AuditTrailEntry(
            meeting_id=meeting_id,
            opportunity_id=opportunity_id,
            actor=actor,
            timestamp=timestamp or datetime.now(),
            action=action,
            reason=reason,
            data_used_json=json.dumps(data_used, ensure_ascii=False) if data_used else None,
            model=model,
            prompt_version=prompt_version,
            rule_version=rule_version,
            result=result,
            **_versoes_validas(versoes),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _audit_trail_entry_to_dict(row)


def obter_audit_trail_entry(entry_id: int) -> Optional[dict]:
    with Session(engine) as session:
        row = session.get(AuditTrailEntry, entry_id)
        return _audit_trail_entry_to_dict(row) if row else None


def listar_audit_trail_entries(
    meeting_id: Optional[str] = None,
    opportunity_id: Optional[int] = None,
    actor: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 200,
) -> List[dict]:
    with Session(engine) as session:
        stmt = select(AuditTrailEntry)
        if meeting_id:
            stmt = stmt.where(AuditTrailEntry.meeting_id == meeting_id)
        if opportunity_id is not None:
            stmt = stmt.where(AuditTrailEntry.opportunity_id == opportunity_id)
        if actor:
            stmt = stmt.where(AuditTrailEntry.actor == actor)
        if action:
            stmt = stmt.where(AuditTrailEntry.action == action)
        stmt = stmt.order_by(AuditTrailEntry.timestamp.asc()).limit(limit)
        rows = session.exec(stmt).all()
        return [_audit_trail_entry_to_dict(r) for r in rows]


class PolicyViolationEvent(SQLModel, table=True):
    """Fase 25 ("o que falta pra ligar") — alimenta o critério literal
    `policy violation = 0`. Um registro por detecção real de
    `agent/prompt_injection_rules.py::detectar_tentativas_injection()`
    no choke-point único de IA (`api/ai_router.py::chamar_ia`) — o
    único tipo de violação com detector determinístico hoje (Tarefa
    18.2). `meeting_id` fica solto (sem FK), mesmo padrão de
    `SalesEvent`/`AuditTrailEntry` — nem toda chamada de IA está
    ligada a uma reunião específica.

    Escrita best-effort (mesma disciplina de `AiUsageEvent`) — uma
    falha aqui nunca pode derrubar a chamada de IA real que ela está
    observando."""

    __tablename__ = "policy_violation_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: Optional[str] = Field(default=None, sa_column=Column(String(200), index=True))
    usuario_id: Optional[str] = Field(default=None, sa_column=Column(String(36), index=True))
    feature: Optional[str] = Field(default=None, sa_column=Column(String(80), index=True))
    tipo: str = Field(sa_column=Column(String(40), index=True, nullable=False))
    trechos_detectados_json: str = Field(sa_column=Column(Text, nullable=False))
    criado_em: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False, index=True))


def _policy_violation_event_to_dict(row: "PolicyViolationEvent") -> dict:
    return {
        "id": row.id,
        "meeting_id": row.meeting_id,
        "usuario_id": row.usuario_id,
        "feature": row.feature,
        "tipo": row.tipo,
        "trechos_detectados": json.loads(row.trechos_detectados_json),
        "criado_em": row.criado_em.isoformat() if row.criado_em else None,
    }


def criar_policy_violation_event(
    *,
    tipo: str,
    trechos_detectados: list,
    meeting_id: Optional[str] = None,
    usuario_id: Optional[str] = None,
    feature: Optional[str] = None,
) -> dict:
    """Cria e persiste um PolicyViolationEvent (Fase 25). Valida via
    agent/policy_violation_rules antes de tocar no banco — ValueError
    propaga pro chamador (dado de domínio, nunca falha silenciosa como
    AiUsageEvent)."""
    from agent.policy_violation_rules import validar_policy_violation_event

    dados = {"tipo": tipo, "trechos_detectados": trechos_detectados}
    validar_policy_violation_event(dados)

    with Session(engine) as session:
        row = PolicyViolationEvent(
            meeting_id=meeting_id,
            usuario_id=usuario_id,
            feature=feature,
            tipo=tipo,
            trechos_detectados_json=json.dumps(trechos_detectados, ensure_ascii=False),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _policy_violation_event_to_dict(row)


def listar_policy_violation_events(
    meeting_id: Optional[str] = None,
    tipo: Optional[str] = None,
    limit: int = 200,
) -> List[dict]:
    with Session(engine) as session:
        stmt = select(PolicyViolationEvent)
        if meeting_id:
            stmt = stmt.where(PolicyViolationEvent.meeting_id == meeting_id)
        if tipo:
            stmt = stmt.where(PolicyViolationEvent.tipo == tipo)
        stmt = stmt.order_by(PolicyViolationEvent.criado_em.asc()).limit(limit)
        rows = session.exec(stmt).all()
        return [_policy_violation_event_to_dict(r) for r in rows]


def contar_policy_violations(
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> int:
    """Total de `PolicyViolationEvent` no período — o número real do
    critério `policy_violation` da Fase 25 (alvo: 0)."""
    with Session(engine) as session:
        stmt = select(func.count(PolicyViolationEvent.id))
        if date_from:
            stmt = stmt.where(PolicyViolationEvent.criado_em >= date_from)
        if date_to:
            stmt = stmt.where(PolicyViolationEvent.criado_em <= date_to)
        return session.exec(stmt).one()


class ReadinessMedicao(SQLModel, table=True):
    """Último resultado de cada medição em lote de um critério da Fase 25
    (Tarefa D1 de docs/tasks-prompt-mestre-v2-restante.md). Golden
    Dataset, benchmark de transcrição e qualidade de recomendação só
    rodam por script (custo/tempo) e antes só deixavam um JSON opcional —
    agora cada `--real` registra aqui, e `GET /admin/readiness` mostra o
    último valor com a data (fica visível quando a medição envelheceu).
    Append-only: cada rodada é uma linha; o painel lê a mais recente."""

    __tablename__ = "readiness_medicoes"

    id: Optional[int] = Field(default=None, primary_key=True)
    criterio: str = Field(sa_column=Column(String(60), index=True, nullable=False))
    valor: Optional[float] = Field(default=None, sa_column=Column(Float))
    origem: str = Field(default="real", sa_column=Column(String(10), nullable=False))
    amostra: Optional[int] = Field(default=None, sa_column=Column(Integer))
    fonte: str = Field(default="", sa_column=Column(String(120), nullable=False))
    detalhe_json: Optional[str] = Field(default=None, sa_column=Column(Text))
    medido_em: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False, index=True))


def registrar_readiness_medicao(
    criterio: str,
    valor: Optional[float],
    *,
    origem: str = "real",
    fonte: str = "",
    amostra: Optional[int] = None,
    detalhe: Optional[dict] = None,
) -> dict:
    """Registra uma medição em lote (Tarefa D1). `ValueError` em critério
    fora dos 9 da Fase 25 ou origem fora de real/proxy — dado de domínio,
    mesma convenção de `criar_sales_evidence()`."""
    from agent.readiness_rules import CRITERIOS_POR_NOME, ORIGENS_MEDICAO

    if criterio not in CRITERIOS_POR_NOME:
        raise ValueError(f"critério desconhecido: {criterio!r} (esperado um de {sorted(CRITERIOS_POR_NOME)})")
    if origem not in ORIGENS_MEDICAO:
        raise ValueError(f"origem inválida: {origem!r} (esperado um de {sorted(ORIGENS_MEDICAO)})")
    with Session(engine) as session:
        row = ReadinessMedicao(
            criterio=criterio,
            valor=None if valor is None else float(valor),
            origem=origem,
            amostra=amostra,
            fonte=fonte,
            detalhe_json=json.dumps(detalhe, ensure_ascii=False, default=str) if detalhe is not None else None,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _readiness_medicao_to_dict(row)


def _readiness_medicao_to_dict(row: "ReadinessMedicao") -> dict:
    return {
        "criterio": row.criterio,
        "valor": row.valor,
        "origem": row.origem,
        "amostra": row.amostra,
        "fonte": row.fonte,
        "detalhe": json.loads(row.detalhe_json) if row.detalhe_json else None,
        "medido_em": row.medido_em.isoformat() if row.medido_em else None,
    }


def ultimas_readiness_medicoes() -> dict:
    """`{criterio: medição mais recente}` (Tarefa D1)."""
    with Session(engine) as session:
        rows = session.exec(
            select(ReadinessMedicao).order_by(ReadinessMedicao.medido_em.asc(), ReadinessMedicao.id.asc())
        ).all()
        ultimas = {}
        for row in rows:
            ultimas[row.criterio] = _readiness_medicao_to_dict(row)
        return ultimas


def readiness_contagens_ao_vivo(dias: int = 7, agora: Optional[datetime] = None) -> dict:
    """Contagens que alimentam os critérios calculados ao vivo da Tarefa
    D1 — leitura pura:
    - `audit_coverage`: chamadas `sales_reasoning.raciocinio` × entradas
      de AuditTrail do motor, desde a 1ª auditoria (o audit trail só
      existe desde a V.1.4.130; contar chamadas anteriores foi o erro de
      medição achado na V.1.4.141), limitado à janela de `dias`;
    - `e2e`: chamadas de IA com e sem sucesso na janela (proxy
      1 − error_rate, mesmo da medição da V.1.4.136);
    - `policy_violations`: total histórico (alvo da Fase 25 é 0)."""
    from api import ai_features

    agora = agora or datetime.now()
    inicio_janela = agora - timedelta(days=dias)
    with Session(engine) as session:
        primeira_auditoria = session.exec(
            select(func.min(AuditTrailEntry.created_at)).where(AuditTrailEntry.actor == "sales_reasoning_engine")
        ).one()
        chamadas_motor = audits_motor = 0
        if primeira_auditoria:
            inicio_audit = max(primeira_auditoria, inicio_janela)
            # A auditoria é gravada DEPOIS que a chamada de IA termina:
            # contar chamadas só a partir da 1ª auditoria deixaria de fora
            # justamente a chamada que a gerou (achado da D4 — cobertura
            # aparecia > 100%). O denominador começa na última chamada do
            # motor anterior a esse ponto.
            chamada_ancora = session.exec(
                select(func.max(AiUsageEvent.criado_em)).where(
                    AiUsageEvent.feature == ai_features.SALES_REASONING_RACIOCINIO,
                    AiUsageEvent.criado_em <= inicio_audit,
                    AiUsageEvent.criado_em >= inicio_janela,
                )
            ).one()
            chamadas_motor = session.exec(
                select(func.count(AiUsageEvent.id)).where(
                    AiUsageEvent.feature == ai_features.SALES_REASONING_RACIOCINIO,
                    AiUsageEvent.criado_em >= (chamada_ancora or inicio_audit),
                )
            ).one()
            audits_motor = session.exec(
                select(func.count(AuditTrailEntry.id)).where(
                    AuditTrailEntry.actor == "sales_reasoning_engine",
                    AuditTrailEntry.created_at >= inicio_audit,
                )
            ).one()
        total_ia = session.exec(
            select(func.count(AiUsageEvent.id)).where(AiUsageEvent.criado_em >= inicio_janela)
        ).one()
        sucesso_ia = session.exec(
            select(func.count(AiUsageEvent.id)).where(
                AiUsageEvent.criado_em >= inicio_janela, AiUsageEvent.success.is_(True),
            )
        ).one()
    return {
        "janela_dias": dias,
        "audit": {"chamadas": chamadas_motor, "auditadas": audits_motor},
        "e2e": {"total": total_ia, "sucesso": sucesso_ia},
        "policy_violations": contar_policy_violations(),
    }


class ShadowModeComparison(SQLModel, table=True):
    """Fase 23 do "PROMPT MESTRE — SALE-IA V2" — Teste em Shadow Mode.
    Um registro por ciclo de `/tempo-real` em que o
    `agent/sales_reasoning_engine.py::raciocinar_async()` (Fase 7) rodou
    silenciosamente em paralelo ao modelo atual (`agent/multiagente/
    orquestrador.py`), sem nunca influenciar o que o vendedor viu.
    Aditiva.

    `recomendacao_nova_json`/`concordancia`/`latency_ms`/`cost_usd`
    nulos significam que o modelo novo falhou nesse ciclo (`erro`
    preenchido) — erro nunca vira discordância, ver
    `agent/shadow_mode_rules.py`. Escrita é sempre melhor esforço (mesmo
    padrão de `AiUsageEvent`) — uma falha aqui nunca pode derrubar o
    ciclo real de `/tempo-real`.

    `origem` (Fase 24, Piloto — coluna aditiva desde V.1.4.120) distingue
    `"shadow"` (nunca influenciou o vendedor, fire-and-forget) de
    `"piloto"` (o vendedor estava dentro do rollout da Fase 24 e
    `recomendacao_nova`, quando bem-sucedida, é literalmente o que ele
    viu) — nunca misturar as duas leituras: agreement/latency/cost do
    piloto são o dado real de produto, do shadow é só observação.
    """

    __tablename__ = "shadow_mode_comparisons"

    id: Optional[int] = Field(default=None, primary_key=True)
    criado_em: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False, index=True))
    meeting_id: Optional[str] = Field(default=None, sa_column=Column(String(200), index=True))
    usuario_id: Optional[str] = Field(default=None, sa_column=Column(String(36), index=True))
    origem: str = Field(default="shadow", sa_column=Column(String(20), nullable=False, index=True))
    recomendacao_atual_json: str = Field(default="{}", sa_column=Column(_LongText, nullable=False))
    recomendacao_nova_json: Optional[str] = Field(default=None, sa_column=Column(_LongText))
    concordancia: Optional[bool] = Field(default=None, sa_column=Column(Boolean))
    atual_e_pergunta: Optional[bool] = Field(default=None, sa_column=Column(Boolean))
    novo_e_pergunta: Optional[bool] = Field(default=None, sa_column=Column(Boolean))
    latency_ms: Optional[int] = Field(default=None, sa_column=Column(Integer))
    cost_usd: Optional[float] = Field(default=None, sa_column=Column(Float))
    erro: Optional[str] = Field(default=None, sa_column=Column(String(500)))


def _shadow_mode_comparison_to_dict(row: "ShadowModeComparison") -> dict:
    return {
        "id": row.id,
        "criado_em": row.criado_em.isoformat() if row.criado_em else None,
        "meeting_id": row.meeting_id,
        "usuario_id": row.usuario_id,
        "origem": row.origem,
        "recomendacao_atual": json.loads(row.recomendacao_atual_json) if row.recomendacao_atual_json else {},
        "recomendacao_nova": json.loads(row.recomendacao_nova_json) if row.recomendacao_nova_json else None,
        "concordancia": row.concordancia,
        "atual_e_pergunta": row.atual_e_pergunta,
        "novo_e_pergunta": row.novo_e_pergunta,
        "latency_ms": row.latency_ms,
        "cost_usd": row.cost_usd,
        "erro": row.erro,
    }


def criar_shadow_mode_comparison(
    *,
    meeting_id: Optional[str],
    usuario_id: Optional[str],
    recomendacao_atual: dict,
    recomendacao_nova: Optional[dict],
    concordancia: Optional[bool],
    atual_e_pergunta: Optional[bool],
    novo_e_pergunta: Optional[bool],
    latency_ms: Optional[int],
    cost_usd: Optional[float],
    erro: Optional[str],
    origem: str = "shadow",
    **_ignorados,
) -> dict:
    """Persiste um registro de `agent/shadow_mode_rules.py::
    montar_registro_shadow()`. `origem` (`"shadow"`/`"piloto"`, Fase 24)
    marca se a recomendação nova só foi observada ou se de fato
    influenciou o vendedor. `**_ignorados` absorve o campo `quality`
    do registro (nunca persistido — é sempre o mesmo gap explícito,
    recomputado em `resumo_shadow_mode()`, não faz sentido gravar em
    milhares de linhas). Escrita melhor esforço — chamador decide se
    envolve em try/except (ver `agent/multiagente/orquestrador.py`)."""
    with Session(engine) as session:
        row = ShadowModeComparison(
            meeting_id=meeting_id,
            usuario_id=usuario_id,
            origem=origem,
            recomendacao_atual_json=json.dumps(recomendacao_atual or {}, ensure_ascii=False),
            recomendacao_nova_json=json.dumps(recomendacao_nova, ensure_ascii=False) if recomendacao_nova else None,
            concordancia=concordancia,
            atual_e_pergunta=atual_e_pergunta,
            novo_e_pergunta=novo_e_pergunta,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            erro=erro,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _shadow_mode_comparison_to_dict(row)


def listar_shadow_mode_comparisons(limit: int = 5000, origem: Optional[str] = None) -> List[dict]:
    with Session(engine) as session:
        stmt = select(ShadowModeComparison)
        if origem:
            stmt = stmt.where(ShadowModeComparison.origem == origem)
        stmt = stmt.order_by(ShadowModeComparison.criado_em.desc()).limit(limit)
        rows = session.exec(stmt).all()
        return [_shadow_mode_comparison_to_dict(r) for r in rows]


def obter_ultimo_ai_usage_event(feature: str, meeting_id: Optional[str]) -> Optional[dict]:
    """Melhor esforço: última linha de `ai_usage_events` pra uma
    `feature`+`meeting_id`, usada pelo Shadow Mode (Fase 23) pra
    recuperar o custo real de uma chamada de `raciocinar_async()`
    (que não retorna custo diretamente ao chamador — só
    `api/ai_router.py::chamar_ia` grava em `AiUsageEvent`). Correlação
    por "mais recente pra essa feature+reunião", não por id exato —
    mesmo princípio de melhor esforço já usado em
    `custo_medio_por_opportunity()` (Fase 19)."""
    if not meeting_id:
        return None
    with Session(engine) as session:
        stmt = (
            select(AiUsageEvent)
            .where(AiUsageEvent.feature == feature, AiUsageEvent.meeting_id == meeting_id)
            .order_by(AiUsageEvent.criado_em.desc())
            .limit(1)
        )
        row = session.exec(stmt).first()
        if not row:
            return None
        return {"cost_usd": row.cost_usd, "latency_ms": row.latency_ms, "success": row.success,
                "provider": row.provider, "model": row.model}


def coletar_dados_qualidade() -> dict:
    """Tarefa B1 (Data Quality, seção 33): carrega só as colunas que
    `agent/data_quality_rules.py` precisa — nunca `transcript_full` e
    afins (MEDIUMTEXT), para a varredura continuar barata com o banco
    crescendo. Datas voltam como `datetime` (não ISO), prontas pra
    comparação. Leitura pura."""
    with Session(engine) as session:
        meetings = [
            {"meeting_id": r[0], "usuario_id": r[1], "opportunity_id": r[2], "created_at": r[3], "updated_at": r[4]}
            for r in session.exec(select(
                MeetingMemory.meeting_id, MeetingMemory.usuario_id, MeetingMemory.opportunity_id,
                MeetingMemory.created_at, MeetingMemory.updated_at,
            )).all()
        ]
        opportunities = [
            {"id": r[0], "seller_id": r[1], "status": r[2], "estimated_value": r[3], "outcome_value": r[4],
             "product": r[5], "loss_reason": r[6], "created_at": r[7], "close_date": r[8],
             "won_at": r[9], "lost_at": r[10]}
            for r in session.exec(select(
                Opportunity.id, Opportunity.seller_id, Opportunity.status, Opportunity.estimated_value,
                Opportunity.outcome_value, Opportunity.product, Opportunity.loss_reason, Opportunity.created_at,
                Opportunity.close_date, Opportunity.won_at, Opportunity.lost_at,
            )).all()
        ]
        recommendation_events = [
            {"id": r[0], "meeting_id": r[1], "opportunity_id": r[2], "recommendation": r[3],
             "shown_at": r[4], "used_at": r[5]}
            for r in session.exec(select(
                RecommendationEvent.id, RecommendationEvent.meeting_id, RecommendationEvent.opportunity_id,
                RecommendationEvent.recommendation, RecommendationEvent.shown_at, RecommendationEvent.used_at,
            )).all()
        ]
        sales_events = [
            {"id": r[0], "meeting_id": r[1], "seller_id": r[2], "event_type": r[3],
             "evidence_quote": r[4], "timestamp": r[5]}
            for r in session.exec(select(
                SalesEvent.id, SalesEvent.meeting_id, SalesEvent.seller_id, SalesEvent.event_type,
                SalesEvent.evidence_quote, SalesEvent.timestamp,
            )).all()
        ]
    return {
        "meetings": meetings,
        "opportunities": opportunities,
        "recommendation_events": recommendation_events,
        "sales_events": sales_events,
    }
