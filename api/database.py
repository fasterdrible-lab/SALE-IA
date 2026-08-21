"""
SALEIA — api/database.py
Camada de persistência com SQLModel.
Usa MySQL se as variáveis DB_* estiverem no .env, caso contrário SQLite local.
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

from dotenv import load_dotenv
from sqlalchemy import Column, DateTime, Float, String, Text, func, text
from sqlalchemy.engine import URL as SA_URL
from sqlalchemy.exc import OperationalError
from sqlmodel import Field, Session, SQLModel, create_engine, select

# Carrega .env do diretório raiz do projeto (sobe 2 níveis de api/)
load_dotenv(Path(__file__).parent.parent / ".env")
logger = logging.getLogger("saleia.db")


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
