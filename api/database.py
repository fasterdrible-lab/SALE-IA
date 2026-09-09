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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

from dotenv import load_dotenv
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, func, text
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
    transcript_full: str = Field(default="", sa_column=Column(Text, nullable=False))
    transcript_buffer: str = Field(default="", sa_column=Column(Text, nullable=False))
    accumulated_summary: str = Field(default="", sa_column=Column(Text, nullable=False))
    current_diagnosis: str = Field(default="", sa_column=Column(Text, nullable=False))
    score_history_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    key_moments_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    events_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    last_ai_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    last_recap_trigger_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    provider_cost_estimate: float = Field(default=0.0, sa_column=Column(Float, nullable=False))
    created_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))
    updated_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))


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


def registrar_transcricao_meeting(meeting_id: str, fragmento: str, substituir: bool = False) -> dict:
    """Atualiza transcript_full e transcript_buffer da reuniao."""
    if not meeting_id:
        raise ValueError("meeting_id e obrigatorio")

    fragmento = (fragmento or "").strip()
    with Session(engine) as session:
        stmt = select(MeetingMemory).where(MeetingMemory.meeting_id == meeting_id)
        row = session.exec(stmt).first()

        if not row:
            row = MeetingMemory(meeting_id=meeting_id)

        if substituir:
            row.transcript_full = fragmento
            row.transcript_buffer = _merge_transcript_buffer("", fragmento)
        else:
            row.transcript_full = _append_transcript(row.transcript_full, fragmento)
            row.transcript_buffer = _merge_transcript_buffer(row.transcript_buffer, fragmento)

        row.updated_at = datetime.now()
        session.add(row)
        session.commit()
        session.refresh(row)
        return _meeting_memory_to_dict(row)


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


def _erro_tabela_ja_existe(exc: OperationalError) -> bool:
    """Detecta corrida benigna de create_all em apps com multiplos workers."""
    original = getattr(exc, "orig", None)
    codigo = None
    if original is not None and getattr(original, "args", None):
        codigo = original.args[0]

    mensagem = str(exc).lower()
    return codigo == 1050 or "already exists" in mensagem or "ja existe" in mensagem


def _criar_metadata_tolerante():
    try:
        SQLModel.metadata.create_all(engine)
    except OperationalError as exc:
        if _erro_tabela_ja_existe(exc):
            logger.warning("Tabela ja existia durante startup concorrente; seguindo normalmente.")
            return
        raise


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
