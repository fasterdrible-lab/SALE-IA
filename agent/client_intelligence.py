"""
agent/client_intelligence.py — Client Intelligence (Sales Brain Fase 4)

T4.1 — Perfil persistente por cliente (nome, empresa, DISC, objeções, dores, score médio)
T4.2 — Timeline comercial (sequência de reuniões com progressão de scores)
T4.3 — Resumo automático injetado no prompt em tempo real ao detectar cliente vinculado

Tabelas criadas:
  client_profiles  — um registro por cliente
  client_meetings  — N:1 vinculação meeting → cliente
"""

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import pymysql
import pymysql.cursors
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
logger = logging.getLogger("saleia.client_intelligence")

STATUS_VALIDOS = {"ativo", "ganho", "perdido", "pausado"}


# ─────────────────────────────────────────────────────────
# CONEXÃO
# ─────────────────────────────────────────────────────────

def _get_conn():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER", "saleia"),
        password=os.getenv("DB_PASS", ""),
        database=os.getenv("DB_NAME", "saleia"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


# ─────────────────────────────────────────────────────────
# T4.1 — CRIAÇÃO DE TABELAS
# ─────────────────────────────────────────────────────────

def criar_tabelas_clientes() -> None:
    """Cria tabelas client_profiles e client_meetings. Idempotente."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS client_profiles (
                    id                   VARCHAR(36)  PRIMARY KEY,
                    nome                 VARCHAR(255) NOT NULL,
                    empresa              VARCHAR(255),
                    email                VARCHAR(255),
                    telefone             VARCHAR(50),
                    disc_profile         VARCHAR(20),
                    objecoes_recorrentes LONGTEXT,
                    dores_recorrentes    LONGTEXT,
                    score_medio          FLOAT        NOT NULL DEFAULT 0,
                    ultimo_score         INT          NOT NULL DEFAULT 0,
                    total_reunioes       INT          NOT NULL DEFAULT 0,
                    status_negociacao    VARCHAR(30)  NOT NULL DEFAULT 'ativo',
                    notas                TEXT,
                    created_at           DATETIME     NOT NULL,
                    updated_at           DATETIME     NOT NULL,
                    INDEX idx_nome   (nome),
                    INDEX idx_status (status_negociacao)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS client_meetings (
                    client_id  VARCHAR(36)  NOT NULL,
                    meeting_id VARCHAR(255) NOT NULL,
                    titulo     VARCHAR(255),
                    score      INT          NOT NULL DEFAULT 0,
                    data       DATETIME,
                    PRIMARY KEY (client_id, meeting_id),
                    INDEX idx_meeting (meeting_id),
                    INDEX idx_client  (client_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        conn.close()
        logger.info("✅ Tabelas client_profiles e client_meetings verificadas/criadas.")
    except Exception as e:
        logger.error("❌ Erro ao criar tabelas de clientes: %s", e)


# ─────────────────────────────────────────────────────────
# CRUD — PERFIS
# ─────────────────────────────────────────────────────────

def criar_cliente(
    nome: str,
    empresa: str = "",
    email: str = "",
    telefone: str = "",
    disc_profile: str = "",
    notas: str = "",
) -> str:
    """Cria um perfil de cliente. Retorna UUID."""
    cid = str(uuid.uuid4())
    agora = datetime.now()
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO client_profiles
                (id, nome, empresa, email, telefone, disc_profile,
                 objecoes_recorrentes, dores_recorrentes,
                 score_medio, ultimo_score, total_reunioes,
                 status_negociacao, notas, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,'[]','[]',0,0,0,'ativo',%s,%s,%s)
            """,
            (cid, nome.strip()[:255], empresa[:255], email[:255],
             telefone[:50], disc_profile[:20], notas, agora, agora),
        )
    conn.close()
    logger.info("[Clientes] Cliente '%s' criado (id=%s)", nome, cid)
    return cid


def obter_cliente(client_id: str) -> Optional[dict]:
    """Retorna perfil completo de um cliente com sua timeline."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM client_profiles WHERE id = %s", (client_id,))
            row = cur.fetchone()
            if not row:
                conn.close()
                return None
            cur.execute(
                "SELECT meeting_id, titulo, score, data FROM client_meetings "
                "WHERE client_id = %s ORDER BY data ASC",
                (client_id,),
            )
            reunioes = cur.fetchall()
        conn.close()
        return _deserializar_cliente(row, reunioes)
    except Exception as e:
        logger.error("[Clientes] Erro ao obter cliente %s: %s", client_id, e)
        return None


def listar_clientes(
    busca: str = "",
    status: str = "",
    limit: int = 50,
    offset: int = 0,
) -> list:
    """Lista clientes com filtros opcionais."""
    where, params = [], []
    if busca:
        where.append("(nome LIKE %s OR empresa LIKE %s OR email LIKE %s)")
        b = f"%{busca}%"
        params += [b, b, b]
    if status:
        where.append("status_negociacao = %s")
        params.append(status)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM client_profiles {clause} ORDER BY updated_at DESC LIMIT %s OFFSET %s",
                params + [limit, offset],
            )
            rows = cur.fetchall()
        conn.close()
        return [_deserializar_cliente(r) for r in rows]
    except Exception as e:
        logger.error("[Clientes] Erro ao listar clientes: %s", e)
        return []


def atualizar_cliente(client_id: str, campos: dict) -> bool:
    """Atualiza campos editáveis do perfil."""
    _EDITAVEIS = {
        "nome", "empresa", "email", "telefone", "disc_profile",
        "notas", "status_negociacao",
        "objecoes_recorrentes", "dores_recorrentes",
    }
    sets, vals = [], []
    for k, v in campos.items():
        if k not in _EDITAVEIS:
            continue
        if k in ("status_negociacao",) and v not in STATUS_VALIDOS:
            continue
        if k in ("objecoes_recorrentes", "dores_recorrentes") and isinstance(v, list):
            v = json.dumps(v, ensure_ascii=False)
        sets.append(f"{k} = %s")
        vals.append(v)
    if not sets:
        return False
    sets.append("updated_at = %s")
    vals.append(datetime.now())
    vals.append(client_id)
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(f"UPDATE client_profiles SET {', '.join(sets)} WHERE id = %s", vals)
        conn.close()
        return True
    except Exception as e:
        logger.error("[Clientes] Erro ao atualizar cliente %s: %s", client_id, e)
        return False


def deletar_cliente(client_id: str) -> bool:
    """Remove cliente e todos os vínculos de reuniões."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM client_meetings WHERE client_id = %s", (client_id,))
            cur.execute("DELETE FROM client_profiles WHERE id = %s", (client_id,))
            affected = cur.rowcount
        conn.close()
        return affected > 0
    except Exception as e:
        logger.error("[Clientes] Erro ao deletar cliente %s: %s", client_id, e)
        return False


# ─────────────────────────────────────────────────────────
# T4.2 — VINCULAR REUNIÕES / TIMELINE
# ─────────────────────────────────────────────────────────

def vincular_reuniao(
    client_id: str,
    meeting_id: str,
    titulo: str = "",
    score: int = 0,
    data: Optional[datetime] = None,
) -> bool:
    """Vincula uma reunião a um cliente e atualiza as estatísticas do perfil."""
    data = data or datetime.now()
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO client_meetings (client_id, meeting_id, titulo, score, data)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE titulo = VALUES(titulo), score = VALUES(score), data = VALUES(data)
                """,
                (client_id, meeting_id, titulo[:255], int(score), data),
            )
            _recalcular_stats(cur, client_id)
        conn.close()
        logger.info("[Clientes] Reunião %s vinculada ao cliente %s (score=%s)", meeting_id, client_id, score)
        return True
    except Exception as e:
        logger.error("[Clientes] Erro ao vincular reunião: %s", e)
        return False


def desvincular_reuniao(client_id: str, meeting_id: str) -> bool:
    """Remove o vínculo de uma reunião e recalcula estatísticas."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM client_meetings WHERE client_id = %s AND meeting_id = %s",
                (client_id, meeting_id),
            )
            _recalcular_stats(cur, client_id)
        conn.close()
        return True
    except Exception as e:
        logger.error("[Clientes] Erro ao desvincular reunião: %s", e)
        return False


def _recalcular_stats(cur, client_id: str) -> None:
    """Recalcula score_medio, ultimo_score e total_reunioes a partir dos vínculos."""
    cur.execute(
        "SELECT COUNT(*) as total, AVG(score) as media "
        "FROM client_meetings WHERE client_id = %s",
        (client_id,),
    )
    row = cur.fetchone() or {}
    total = int(row.get("total") or 0)
    media = float(row.get("media") or 0)
    cur.execute(
        "SELECT score FROM client_meetings WHERE client_id = %s ORDER BY data DESC LIMIT 1",
        (client_id,),
    )
    last_row = cur.fetchone()
    ultimo = int((last_row or {}).get("score") or 0)
    cur.execute(
        "UPDATE client_profiles SET score_medio=%s, ultimo_score=%s, total_reunioes=%s, updated_at=%s WHERE id=%s",
        (round(media, 1), ultimo, total, datetime.now(), client_id),
    )


def obter_timeline(client_id: str) -> list:
    """Retorna timeline ordenada cronologicamente para o cliente."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT meeting_id, titulo, score, data FROM client_meetings "
                "WHERE client_id = %s ORDER BY data ASC",
                (client_id,),
            )
            rows = cur.fetchall()
        conn.close()
        for r in rows:
            if isinstance(r.get("data"), datetime):
                r["data"] = r["data"].isoformat()
        return rows
    except Exception as e:
        logger.error("[Clientes] Erro ao obter timeline de %s: %s", client_id, e)
        return []


# ─────────────────────────────────────────────────────────
# T4.3 — RESUMO AUTOMÁTICO PARA PROMPT
# ─────────────────────────────────────────────────────────

def buscar_cliente_por_reuniao(meeting_id: str) -> Optional[str]:
    """Retorna o client_id vinculado à reunião, ou None."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT client_id FROM client_meetings WHERE meeting_id = %s LIMIT 1",
                (meeting_id,),
            )
            row = cur.fetchone()
        conn.close()
        return row["client_id"] if row else None
    except Exception as e:
        logger.debug("[Clientes] Erro ao buscar cliente por reunião %s: %s", meeting_id, e)
        return None


def buscar_resumo_cliente_para_reuniao(meeting_id: str) -> str:
    """
    Retorna contexto do cliente para injeção no prompt de análise em tempo real.
    Retorna "" se não houver cliente vinculado ou se o perfil estiver vazio.
    """
    client_id = buscar_cliente_por_reuniao(meeting_id)
    if not client_id:
        return ""
    cliente = obter_cliente(client_id)
    if not cliente:
        return ""

    partes = [f"[CONTEXTO DO CLIENTE — {cliente['nome']}]"]
    if cliente.get("empresa"):
        partes.append(f"Empresa: {cliente['empresa']}")
    if cliente.get("disc_profile"):
        partes.append(f"Perfil DISC: {cliente['disc_profile']}")

    timeline = cliente.get("reunioes", [])
    if len(timeline) > 1:
        partes.append(f"Histórico: {len(timeline)} reuniões anteriores | Score médio: {cliente['score_medio']:.0f} | Último score: {cliente['ultimo_score']}")
        evolucao = " → ".join([f"{r['score']}" for r in timeline[-5:]])
        partes.append(f"Evolução dos scores: {evolucao}")

    objecoes = cliente.get("objecoes_recorrentes") or []
    if objecoes:
        partes.append(f"Objeções recorrentes: {'; '.join(str(o) for o in objecoes[:3])}")

    dores = cliente.get("dores_recorrentes") or []
    if dores:
        partes.append(f"Dores recorrentes: {'; '.join(str(d) for d in dores[:3])}")

    if cliente.get("notas"):
        partes.append(f"Notas: {str(cliente['notas'])[:200]}")

    if len(partes) <= 1:
        return ""

    return "\n\n" + "\n".join(partes)


# ─────────────────────────────────────────────────────────
# ENRIQUECIMENTO AUTOMÁTICO PÓS-RELATÓRIO
# ─────────────────────────────────────────────────────────

def enriquecer_perfil_apos_relatorio(
    client_id: str,
    relatorio: dict,
    score: int = 0,
    meeting_id: Optional[str] = None,
    meeting_titulo: Optional[str] = None,
) -> None:
    """
    Atualiza o perfil do cliente com dados extraídos do relatório.
    Chamado em background após geração de relatório se houver cliente vinculado.
    """
    try:
        campos = {}
        recap = relatorio.get("recapitulacao") or {}
        disc = relatorio.get("perfil_disc") or recap.get("perfil_disc") or {}

        # DISC
        disc_tipo = (
            disc.get("tipo") or disc.get("perfil_primario") or disc.get("perfil_disc") or ""
        )
        if disc_tipo:
            campos["disc_profile"] = disc_tipo[:20]

        # Objeções e dores (merge com existentes)
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT objecoes_recorrentes, dores_recorrentes FROM client_profiles WHERE id = %s",
                    (client_id,),
                )
                row = cur.fetchone() or {}
        finally:
            conn.close()

        def _json_list(val):
            if isinstance(val, list): return val
            if isinstance(val, str):
                try: return json.loads(val)
                except: return []
            return []

        objecoes = _json_list(row.get("objecoes_recorrentes"))
        dores = _json_list(row.get("dores_recorrentes"))

        estrateg = (recap.get("recapitulacao_estrategica") or {}) if isinstance(recap, dict) else {}
        novas_objecoes = estrateg.get("objecoes_levantadas") or []
        novas_dores = estrateg.get("dores_identificadas") or []

        for o in novas_objecoes:
            o_str = str(o).strip()
            if o_str and o_str not in objecoes:
                objecoes.append(o_str)

        for d in novas_dores:
            d_str = str(d).strip()
            if d_str and d_str not in dores:
                dores.append(d_str)

        campos["objecoes_recorrentes"] = objecoes[:20]
        campos["dores_recorrentes"] = dores[:20]

        atualizar_cliente(client_id, campos)

        # Vincula reunião se meeting_id informado
        if meeting_id:
            vincular_reuniao(
                client_id=client_id,
                meeting_id=meeting_id,
                titulo=meeting_titulo or relatorio.get("titulo") or "",
                score=score,
            )

        logger.info("[Clientes] Perfil %s enriquecido após relatório (reunião %s, score %s)",
                    client_id, meeting_id, score)
    except Exception as e:
        logger.error("[Clientes] Erro ao enriquecer perfil %s: %s", client_id, e)


# ─────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────

def _deserializar_cliente(row: dict, reunioes: list = None) -> dict:
    for campo in ("objecoes_recorrentes", "dores_recorrentes"):
        val = row.get(campo)
        if isinstance(val, str):
            try:
                row[campo] = json.loads(val)
            except Exception:
                row[campo] = []
    for campo in ("created_at", "updated_at"):
        if isinstance(row.get(campo), datetime):
            row[campo] = row[campo].isoformat()
    if reunioes is not None:
        for r in reunioes:
            if isinstance(r.get("data"), datetime):
                r["data"] = r["data"].isoformat()
        row["reunioes"] = reunioes
    return row
