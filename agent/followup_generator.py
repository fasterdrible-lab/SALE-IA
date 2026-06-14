"""
Fase 6 — Follow-up Inteligente.

T6.1: Geração de mensagens por canal (WhatsApp, Email, LinkedIn)
T6.2: Adaptação por perfil DISC
T6.3: Agenda inteligente baseada no score
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pymysql
import pymysql.cursors

from api.ai_router import chamar_ia

logger = logging.getLogger(__name__)

_PROMPT = Path(__file__).parent / "prompt_templates" / "followup_generator.txt"

CANAIS = ["whatsapp", "email", "linkedin"]

STATUS_VALIDOS = {"pendente", "enviado", "descartado"}


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
# TABELA
# ─────────────────────────────────────────────────────────

def criar_tabela_followups():
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS followups (
                    id          CHAR(36)      PRIMARY KEY,
                    meeting_id  VARCHAR(255)  NOT NULL,
                    client_id   CHAR(36)      NULL,
                    canal       VARCHAR(20)   NOT NULL,
                    assunto     VARCHAR(500)  NULL,
                    mensagem    LONGTEXT      NOT NULL,
                    call_to_action VARCHAR(500) NULL,
                    tom         VARCHAR(100)  NULL,
                    disc_profile VARCHAR(5)   NULL,
                    score       INT           DEFAULT 0,
                    dias_apos   INT           DEFAULT 3,
                    agendado_para DATETIME    NULL,
                    status      VARCHAR(20)   DEFAULT 'pendente',
                    created_at  DATETIME      DEFAULT CURRENT_TIMESTAMP,
                    updated_at  DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_fu_meeting (meeting_id),
                    INDEX idx_fu_status (status)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            """)


# ─────────────────────────────────────────────────────────
# T6.3 — AGENDA INTELIGENTE
# ─────────────────────────────────────────────────────────

def agenda_inteligente(score: int) -> list[dict]:
    """
    Retorna sugestões de timing baseadas no score de compra.
    Score alto → follow-up rápido; score baixo → espaçado para não pressionar.
    """
    if score >= 65:
        # Hot: strike while iron is hot
        return [
            {"dias": 1, "canal": "whatsapp", "prioridade": "alta",
             "motivo": "Score alto — agilize o contato para manter momentum"},
            {"dias": 4, "canal": "email",    "prioridade": "media",
             "motivo": "Reforce o valor antes de o entusiasmo esfriar"},
            {"dias": 10, "canal": "linkedin", "prioridade": "baixa",
             "motivo": "Mantenha presença profissional se ainda não decidiu"},
        ]
    elif score >= 35:
        # Warm: standard nurture
        return [
            {"dias": 3, "canal": "whatsapp", "prioridade": "alta",
             "motivo": "Score médio — retome enquanto a conversa ainda está fresca"},
            {"dias": 7, "canal": "email",    "prioridade": "media",
             "motivo": "Envie conteúdo de valor para avançar a decisão"},
            {"dias": 15, "canal": "linkedin", "prioridade": "baixa",
             "motivo": "Toque leve para manter a relação viva"},
        ]
    else:
        # Cold: soft recovery
        return [
            {"dias": 2,  "canal": "whatsapp", "prioridade": "alta",
             "motivo": "Score baixo — recupere o contato rapidamente com nova angulagem"},
            {"dias": 5,  "canal": "email",    "prioridade": "media",
             "motivo": "Apresente ângulo diferente ou case de sucesso similar"},
            {"dias": 14, "canal": "linkedin", "prioridade": "baixa",
             "motivo": "Abordagem de longo prazo sem pressão"},
        ]


# ─────────────────────────────────────────────────────────
# T6.1 + T6.2 — GERAÇÃO COM IA
# ─────────────────────────────────────────────────────────

def gerar_followups(
    meeting_id: str,
    disc_profile: str = "",
    score: int = 0,
    resumo: str = "",
    dores: list | None = None,
    proximos_passos: list | None = None,
    nome_cliente: str = "",
) -> dict:
    """Chama IA e retorna dict com mensagens para whatsapp, email, linkedin."""
    template = _PROMPT.read_text(encoding="utf-8")
    prompt = (
        template
        .replace("{nome_cliente}", nome_cliente or "cliente")
        .replace("{disc_profile}", disc_profile or "Não identificado")
        .replace("{score}", str(score))
        .replace("{resumo}", resumo or "Reunião de vendas consultiva")
        .replace("{dores}", json.dumps(dores or [], ensure_ascii=False))
        .replace("{proximos_passos}", json.dumps(proximos_passos or [], ensure_ascii=False))
    )
    return chamar_ia(
        "Voce e um especialista em follow-up de vendas consultivas. Responda SEMPRE em JSON valido, sem texto antes ou depois.",
        prompt,
    )


def gerar_e_salvar_followups(
    meeting_id: str,
    disc_profile: str = "",
    score: int = 0,
    resumo: str = "",
    dores: list | None = None,
    proximos_passos: list | None = None,
    nome_cliente: str = "",
    client_id: str | None = None,
) -> list[dict]:
    """Gera follow-ups via IA, calcula agenda e salva no MySQL. Retorna lista de follow-ups."""
    raw = gerar_followups(
        meeting_id=meeting_id,
        disc_profile=disc_profile,
        score=score,
        resumo=resumo,
        dores=dores,
        proximos_passos=proximos_passos,
        nome_cliente=nome_cliente,
    )

    if not isinstance(raw, dict):
        try:
            raw = json.loads(raw) if isinstance(raw, str) else {}
        except Exception:
            raw = {}

    agenda = agenda_inteligente(score)
    now = datetime.utcnow()

    saved = []
    with _get_conn() as conn:
        with conn.cursor() as cur:
            for item in agenda:
                canal = item["canal"]
                canal_data = raw.get(canal) or {}
                if not canal_data.get("mensagem"):
                    continue

                dias = item["dias"]
                fid = str(uuid.uuid4())
                agendado = now + timedelta(days=dias)

                cur.execute("""
                    INSERT INTO followups
                        (id, meeting_id, client_id, canal, assunto, mensagem,
                         call_to_action, tom, disc_profile, score, dias_apos,
                         agendado_para, status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pendente')
                """, (
                    fid, meeting_id, client_id, canal,
                    canal_data.get("assunto"),
                    canal_data.get("mensagem", ""),
                    canal_data.get("call_to_action"),
                    canal_data.get("tom"),
                    disc_profile or None,
                    score,
                    dias,
                    agendado,
                ))

                saved.append({
                    "id": fid,
                    "meeting_id": meeting_id,
                    "canal": canal,
                    "assunto": canal_data.get("assunto"),
                    "mensagem": canal_data.get("mensagem", ""),
                    "call_to_action": canal_data.get("call_to_action"),
                    "tom": canal_data.get("tom"),
                    "disc_profile": disc_profile,
                    "score": score,
                    "dias_apos": dias,
                    "agendado_para": agendado.isoformat(),
                    "status": "pendente",
                    "prioridade": item["prioridade"],
                    "motivo_agenda": item["motivo"],
                })

    return saved


# ─────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────

def listar_followups(meeting_id: str) -> list[dict]:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM followups WHERE meeting_id=%s ORDER BY dias_apos ASC",
                (meeting_id,),
            )
            rows = cur.fetchall()
    return [_ser(r) for r in rows]


def obter_followup(fid: str) -> dict | None:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM followups WHERE id=%s", (fid,))
            row = cur.fetchone()
    return _ser(row) if row else None


def atualizar_followup(fid: str, **kwargs) -> dict | None:
    campos_validos = {"mensagem", "assunto", "call_to_action", "status", "agendado_para"}
    updates = {k: v for k, v in kwargs.items() if k in campos_validos}
    if not updates:
        return obter_followup(fid)
    if "status" in updates and updates["status"] not in STATUS_VALIDOS:
        raise ValueError(f"Status inválido: {updates['status']}")
    set_clause = ", ".join(f"{k}=%s" for k in updates)
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE followups SET {set_clause} WHERE id=%s",
                (*updates.values(), fid),
            )
    return obter_followup(fid)


def deletar_followup(fid: str) -> bool:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM followups WHERE id=%s", (fid,))
            return cur.rowcount > 0


def _ser(row: dict) -> dict:
    r = dict(row)
    for k in ("created_at", "updated_at", "agendado_para"):
        if k in r and hasattr(r[k], "isoformat"):
            r[k] = r[k].isoformat()
    return r
