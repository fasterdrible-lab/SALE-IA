"""
agent/playbook_generator.py — Playbook Engine (Sales Brain Fase 2)

T2.1 — Detector de reuniões de sucesso + gestão de status
T2.2 — Gerador de playbook via IA (implementado aqui)
T2.3 — Biblioteca de playbooks exposta via REST em api/main.py

Critérios de "reunião de sucesso":
  - probabilidade_fechamento == "alta" na recapitulação
  - OU score_compra > 80 no histórico da reunião
  - OU status == "won" (marcado manualmente)
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
logger = logging.getLogger("saleia.playbook_generator")

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
# CRIAÇÃO DE TABELAS
# ─────────────────────────────────────────────────────────

def criar_tabelas_playbook() -> None:
    """Cria as tabelas meeting_status e playbooks se não existirem. Idempotente."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS meeting_status (
                    meeting_id  VARCHAR(255) PRIMARY KEY,
                    status      VARCHAR(20)  NOT NULL DEFAULT 'open',
                    updated_at  DATETIME     NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS playbooks (
                    id                  VARCHAR(36)  PRIMARY KEY,
                    name                VARCHAR(255) NOT NULL,
                    target_persona      TEXT,
                    steps               LONGTEXT,
                    objections          LONGTEXT,
                    winning_arguments   LONGTEXT,
                    closing_sequence    LONGTEXT,
                    source_meeting_id   VARCHAR(255),
                    is_active           TINYINT(1)   NOT NULL DEFAULT 1,
                    created_at          DATETIME     NOT NULL,
                    updated_at          DATETIME     NOT NULL,
                    INDEX idx_active      (is_active),
                    INDEX idx_source      (source_meeting_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        conn.close()
        logger.info("✅ Tabelas meeting_status e playbooks verificadas/criadas.")
    except Exception as e:
        logger.error("❌ Erro ao criar tabelas de playbook: %s", e)


# ─────────────────────────────────────────────────────────
# T2.1 — DETECTOR DE REUNIÕES DE SUCESSO
# ─────────────────────────────────────────────────────────

def _eh_reuniao_de_sucesso(relatorio: dict, meeting_id: Optional[str] = None) -> bool:
    """
    Retorna True se a reunião qualifica para geração de playbook.

    Critérios (qualquer um basta):
      1. probabilidade_fechamento == "alta" na recapitulação
      2. Último score_compra > 80 no histórico da MeetingMemory
      3. Status manual == "won" na tabela meeting_status
    """
    # Critério 1 — probabilidade de fechamento alta
    recap = relatorio.get("recapitulacao") or {}
    if isinstance(recap, dict):
        prob = str(recap.get("probabilidade_fechamento") or "").lower().strip()
        if prob == "alta":
            logger.info("[Playbook] Reunião %s qualifica: probabilidade_fechamento=alta", meeting_id)
            return True

    # Critério 2 — score > 80 no histórico
    if meeting_id:
        try:
            from api.database import obter_meeting_memory
            mem = obter_meeting_memory(meeting_id)
            if mem:
                scores = json.loads(mem.get("score_history_json") or "[]")
                if scores:
                    ultimo = scores[-1]
                    valor = ultimo.get("valor") or ultimo.get("score") or (ultimo if isinstance(ultimo, (int, float)) else 0)
                    if float(valor) > 80:
                        logger.info("[Playbook] Reunião %s qualifica: score=%s", meeting_id, valor)
                        return True
        except Exception as e:
            logger.debug("[Playbook] Não foi possível checar score_history: %s", e)

    # Critério 3 — marcada manualmente como ganha
    if meeting_id:
        status = obter_status_reuniao(meeting_id)
        if status == "won":
            logger.info("[Playbook] Reunião %s qualifica: status=won", meeting_id)
            return True

    return False


# ─────────────────────────────────────────────────────────
# STATUS DE REUNIÃO
# ─────────────────────────────────────────────────────────

def atualizar_status_reuniao(meeting_id: str, status: str) -> bool:
    """
    Define o status de uma reunião (open/won/lost).
    Usa INSERT ... ON DUPLICATE KEY UPDATE para upsert.
    """
    if status not in ("open", "won", "lost"):
        raise ValueError(f"Status inválido: {status!r}. Use open, won ou lost.")
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meeting_status (meeting_id, status, updated_at)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE status = VALUES(status), updated_at = VALUES(updated_at)
                """,
                (meeting_id, status, datetime.now()),
            )
        conn.close()
        logger.info("[Playbook] Status da reunião %s atualizado para '%s'", meeting_id, status)
        return True
    except Exception as e:
        logger.error("[Playbook] Erro ao atualizar status da reunião %s: %s", meeting_id, e)
        return False


def obter_status_reuniao(meeting_id: str) -> str:
    """Retorna o status atual da reunião ('open' se não encontrado)."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM meeting_status WHERE meeting_id = %s",
                (meeting_id,),
            )
            row = cur.fetchone()
        conn.close()
        return row["status"] if row else "open"
    except Exception as e:
        logger.debug("[Playbook] Erro ao obter status da reunião %s: %s", meeting_id, e)
        return "open"


def listar_status_reunioes(meeting_ids: list) -> dict:
    """Retorna dict {meeting_id: status} para uma lista de IDs. Uso: enriquecer listagem."""
    if not meeting_ids:
        return {}
    try:
        placeholders = ",".join(["%s"] * len(meeting_ids))
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT meeting_id, status FROM meeting_status WHERE meeting_id IN ({placeholders})",
                tuple(meeting_ids),
            )
            rows = cur.fetchall()
        conn.close()
        return {r["meeting_id"]: r["status"] for r in rows}
    except Exception as e:
        logger.debug("[Playbook] Erro ao listar status: %s", e)
        return {}


# ─────────────────────────────────────────────────────────
# T2.2 — PLAYBOOKS (CRUD)
# ─────────────────────────────────────────────────────────

def salvar_playbook(playbook: dict) -> str:
    """Persiste um playbook gerado. Retorna o UUID criado."""
    pid = str(uuid.uuid4())
    agora = datetime.now()
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO playbooks
                (id, name, target_persona, steps, objections,
                 winning_arguments, closing_sequence, source_meeting_id,
                 is_active, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s)
            """,
            (
                pid,
                str(playbook.get("name") or "")[:255],
                str(playbook.get("targetPersona") or ""),
                json.dumps(playbook.get("steps") or [], ensure_ascii=False),
                json.dumps(playbook.get("objections") or [], ensure_ascii=False),
                json.dumps(playbook.get("winningArguments") or [], ensure_ascii=False),
                json.dumps(playbook.get("closingSequence") or [], ensure_ascii=False),
                playbook.get("source_meeting_id"),
                agora,
                agora,
            ),
        )
    conn.close()
    return pid


def listar_playbooks(apenas_ativos: bool = False, limit: int = 50, offset: int = 0) -> list:
    """Lista playbooks com filtro opcional por ativos."""
    where = "WHERE is_active = 1" if apenas_ativos else ""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM playbooks {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (limit, offset),
            )
            rows = cur.fetchall()
        conn.close()
        return [_deserializar_playbook(r) for r in rows]
    except Exception as e:
        logger.error("[Playbook] Erro ao listar playbooks: %s", e)
        return []


def obter_playbook(playbook_id: str) -> Optional[dict]:
    """Retorna um playbook por ID, ou None."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM playbooks WHERE id = %s", (playbook_id,))
            row = cur.fetchone()
        conn.close()
        return _deserializar_playbook(row) if row else None
    except Exception as e:
        logger.error("[Playbook] Erro ao obter playbook %s: %s", playbook_id, e)
        return None


def atualizar_playbook(playbook_id: str, campos: dict) -> bool:
    """Atualiza campos editáveis de um playbook (name, targetPersona, is_active, steps, etc.)."""
    _EDITAVEIS = {"name", "target_persona", "steps", "objections",
                  "winning_arguments", "closing_sequence", "is_active"}
    sets, vals = [], []
    for k, v in campos.items():
        if k not in _EDITAVEIS:
            continue
        if k in ("steps", "objections", "winning_arguments", "closing_sequence") and isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)
        sets.append(f"{k} = %s")
        vals.append(v)
    if not sets:
        return False
    sets.append("updated_at = %s")
    vals.append(datetime.now())
    vals.append(playbook_id)
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(f"UPDATE playbooks SET {', '.join(sets)} WHERE id = %s", vals)
        conn.close()
        return True
    except Exception as e:
        logger.error("[Playbook] Erro ao atualizar playbook %s: %s", playbook_id, e)
        return False


def deletar_playbook(playbook_id: str) -> bool:
    """Remove permanentemente um playbook."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM playbooks WHERE id = %s", (playbook_id,))
            affected = cur.rowcount
        conn.close()
        return affected > 0
    except Exception as e:
        logger.error("[Playbook] Erro ao deletar playbook %s: %s", playbook_id, e)
        return False


def _deserializar_playbook(row: dict) -> dict:
    for campo in ("steps", "objections", "winning_arguments", "closing_sequence"):
        val = row.get(campo)
        if isinstance(val, str):
            try:
                row[campo] = json.loads(val)
            except Exception:
                row[campo] = []
    for campo in ("created_at", "updated_at"):
        if isinstance(row.get(campo), datetime):
            row[campo] = row[campo].isoformat()
    return row


# ─────────────────────────────────────────────────────────
# T2.2 — GERADOR DE PLAYBOOK VIA IA
# ─────────────────────────────────────────────────────────

_PROMPT_PATH = Path(__file__).parent / "prompt_templates" / "playbook_generation.txt"
_PROMPT_TEMPLATE: Optional[str] = None


def _get_prompt_playbook() -> str:
    global _PROMPT_TEMPLATE
    if _PROMPT_TEMPLATE is None:
        _PROMPT_TEMPLATE = _PROMPT_PATH.read_text(encoding="utf-8")
    return _PROMPT_TEMPLATE


def _montar_contexto_playbook(relatorio: dict, transcricao: str) -> str:
    partes = []
    titulo = relatorio.get("titulo") or relatorio.get("nome_reuniao") or "Reunião"
    partes.append(f"TÍTULO: {titulo}")

    recap = relatorio.get("recapitulacao") or {}
    if isinstance(recap, dict):
        resumo = recap.get("resumo_executivo") or ""
        if resumo:
            partes.append(f"\nRESUMO EXECUTIVO: {resumo}")
        estrategica = recap.get("recapitulacao_estrategica") or {}
        if isinstance(estrategica, dict):
            dores = estrategica.get("dores_identificadas") or []
            objecoes = estrategica.get("objecoes_levantadas") or []
            positivos = estrategica.get("pontos_positivos") or []
            prod = estrategica.get("produto_recomendado") or {}
            if dores:
                partes.append(f"DORES: {json.dumps(dores, ensure_ascii=False)}")
            if objecoes:
                partes.append(f"OBJEÇÕES: {json.dumps(objecoes, ensure_ascii=False)}")
            if positivos:
                partes.append(f"PONTOS POSITIVOS: {json.dumps(positivos, ensure_ascii=False)}")
            if isinstance(prod, dict):
                partes.append(f"PRODUTO VENDIDO: {prod.get('nome','')} — {prod.get('valor','')}")
        proximo = recap.get("proximos_passos") or []
        if proximo:
            partes.append(f"PRÓXIMOS PASSOS: {json.dumps(proximo, ensure_ascii=False)[:300]}")
        prob = recap.get("probabilidade_fechamento") or ""
        if prob:
            partes.append(f"PROBABILIDADE: {prob}")

    disc = relatorio.get("perfil_disc") or {}
    if isinstance(disc, dict):
        partes.append(f"\nPERFIL DISC: {disc.get('perfil_primario') or disc.get('tipo') or ''}")
        partes.append(f"ESTRATÉGIA DISC: {str(disc.get('como_abordar') or disc.get('estrategia_fechamento') or '')[:300]}")

    if transcricao:
        partes.append(f"\nTRANSCRIÇÃO:\n{transcricao.strip()[:6000]}")

    return "\n".join(partes)


def gerar_playbook(relatorio: dict, transcricao: str, meeting_id: Optional[str] = None) -> Optional[dict]:
    """
    Chama a IA para gerar um playbook comercial reutilizável.
    Retorna dict com name/targetPersona/steps/objections/winningArguments/closingSequence.
    """
    from api.ai_router import chamar_ia
    contexto = _montar_contexto_playbook(relatorio, transcricao)
    prompt = _get_prompt_playbook().replace("{contexto}", contexto)

    try:
        resposta = chamar_ia(
            system_prompt=prompt,
            user_content="Gere o playbook comercial desta reunião de sucesso.",
        )
    except Exception as e:
        logger.error("[Playbook] Erro ao chamar IA: %s", e)
        return None

    # Normaliza resposta: suporta dict direto ou encapsulado em "playbook"
    if isinstance(resposta, dict):
        if "playbook" in resposta and isinstance(resposta["playbook"], dict):
            resposta = resposta["playbook"]
        if "name" not in resposta:
            logger.warning("[Playbook] IA não retornou campo 'name'. Resposta: %s", list(resposta.keys()))
            return None
        resposta["source_meeting_id"] = meeting_id
        return resposta

    logger.warning("[Playbook] Resposta IA inválida: %s", type(resposta))
    return None


def gerar_e_salvar_playbook(
    relatorio: dict,
    transcricao: str,
    meeting_id: Optional[str] = None,
) -> Optional[str]:
    """
    Pipeline completo: detecta sucesso → gera playbook via IA → persiste.
    Projetado para execução em BackgroundTask.

    Returns:
        UUID do playbook criado, ou None.
    """
    try:
        playbook = gerar_playbook(relatorio, transcricao, meeting_id)
        if not playbook:
            logger.info("[Playbook] IA não retornou playbook válido para reunião %s", meeting_id)
            return None

        pid = salvar_playbook(playbook)
        logger.info("✅ [Playbook] Playbook '%s' salvo (id=%s) para reunião %s",
                    playbook.get("name"), pid, meeting_id)
        return pid
    except Exception as e:
        logger.error("[Playbook] Erro no pipeline de geração (reunião %s): %s", meeting_id, e)
        return None
