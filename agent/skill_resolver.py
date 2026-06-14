"""
agent/skill_resolver.py — Skill Resolver (Sales Brain Fase 3)

T3.1 — Carrega skills builtin (JSON) + skills customizadas (MySQL)
T3.2 — Resolve a melhor skill para o contexto atual da reunião
T3.3 — Cria novas skills via IA a partir de playbooks/reuniões

Integração:
    processador_tempo_real.py chama resolver_skill_context() antes de analisar_fragmento()
    O texto retornado é injetado no final do prompt da IA de tempo real.
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
logger = logging.getLogger("saleia.skill_resolver")

_SKILLS_DIR = Path(__file__).parent / "skills"
_PROMPT_PATH = Path(__file__).parent / "prompt_templates" / "skill_generation.txt"
_PROMPT_TEMPLATE: Optional[str] = None

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
# CRIAÇÃO DE TABELA
# ─────────────────────────────────────────────────────────

def criar_tabela_skills() -> None:
    """Cria a tabela skills no MySQL. Idempotente."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS skills (
                    id                  VARCHAR(36)  PRIMARY KEY,
                    name                VARCHAR(255) NOT NULL,
                    description         TEXT,
                    trigger_disc        TEXT,
                    trigger_min_score   INT          NOT NULL DEFAULT 0,
                    trigger_max_score   INT          NOT NULL DEFAULT 100,
                    trigger_stages      TEXT,
                    priority            INT          NOT NULL DEFAULT 50,
                    system_injection    LONGTEXT,
                    tactics             LONGTEXT,
                    is_active           TINYINT(1)   NOT NULL DEFAULT 1,
                    source              VARCHAR(50)  NOT NULL DEFAULT 'generated',
                    source_playbook_id  VARCHAR(36),
                    created_at          DATETIME     NOT NULL,
                    updated_at          DATETIME     NOT NULL,
                    INDEX idx_active (is_active),
                    INDEX idx_source (source)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        conn.close()
        logger.info("✅ Tabela skills verificada/criada.")
    except Exception as e:
        logger.error("❌ Erro ao criar tabela skills: %s", e)


# ─────────────────────────────────────────────────────────
# T3.1 — CARREGAMENTO DE SKILLS
# ─────────────────────────────────────────────────────────

def _carregar_skills_builtin() -> list:
    """Carrega as skills embutidas dos arquivos JSON em agent/skills/."""
    skills = []
    if not _SKILLS_DIR.exists():
        return skills
    for path in _SKILLS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["source"] = "builtin"
            skills.append(data)
        except Exception as e:
            logger.warning("[Skills] Erro ao carregar %s: %s", path.name, e)
    return skills


def _carregar_skills_db() -> list:
    """Carrega skills customizadas ativas do MySQL."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM skills WHERE is_active = 1 ORDER BY priority DESC"
            )
            rows = cur.fetchall()
        conn.close()
        result = []
        for r in rows:
            for campo in ("trigger_disc", "trigger_stages", "tactics"):
                if isinstance(r.get(campo), str):
                    try:
                        r[campo] = json.loads(r[campo])
                    except Exception:
                        r[campo] = []
            result.append(r)
        return result
    except Exception as e:
        logger.debug("[Skills] Não foi possível carregar skills do DB: %s", e)
        return []


def listar_skills(apenas_ativas: bool = False) -> list:
    """Retorna lista de todas as skills (builtin + DB), opcionalmente só ativas."""
    builtin = _carregar_skills_builtin()
    db = _carregar_skills_db()

    # Marca builtins como ativas por padrão (não estão no DB)
    for s in builtin:
        s.setdefault("is_active", 1)
        s.setdefault("priority", 50)

    todas = builtin + db

    if apenas_ativas:
        todas = [s for s in todas if s.get("is_active", 1)]

    todas.sort(key=lambda s: int(s.get("priority") or 50), reverse=True)
    return todas


# ─────────────────────────────────────────────────────────
# T3.2 — SKILL RESOLVER
# ─────────────────────────────────────────────────────────

def _disc_match(skill: dict, disc_profile: str) -> bool:
    """Verifica se o perfil DISC do cliente bate com os triggers da skill."""
    triggers = skill.get("triggers", {}) or {}
    disc_triggers = triggers.get("disc_profiles") or skill.get("trigger_disc") or []
    if not disc_triggers:
        return True  # lista vazia = qualquer perfil
    disc_upper = (disc_profile or "").strip().upper()
    return any(d.upper() in disc_upper for d in disc_triggers)


def _score_match(skill: dict, score: float) -> bool:
    """Verifica se o score atual está dentro do range da skill."""
    triggers = skill.get("triggers", {}) or {}
    min_s = int(triggers.get("min_score") if "triggers" in skill else skill.get("trigger_min_score") or 0)
    max_s = int(triggers.get("max_score") if "triggers" in skill else skill.get("trigger_max_score") or 100)
    return min_s <= score <= max_s


def _stage_match(skill: dict, conversation_stage: str) -> bool:
    """Verifica se o estágio da conversa bate com os triggers da skill."""
    triggers = skill.get("triggers", {}) or {}
    stage_triggers = triggers.get("stages") or skill.get("trigger_stages") or []
    if not stage_triggers:
        return True  # lista vazia = qualquer estágio
    stage_lower = (conversation_stage or "").lower()
    return any(s.lower() in stage_lower or stage_lower in s.lower() for s in stage_triggers)


def resolver_melhor_skill(
    disc_profile: str = "",
    score: float = 50.0,
    conversation_stage: str = "abertura",
) -> Optional[dict]:
    """
    Seleciona a skill mais adequada para o contexto atual.

    Args:
        disc_profile: Perfil DISC identificado (ex: "D", "DISC Dominante")
        score: Score de compra atual (0-100)
        conversation_stage: Estágio da conversa (ex: "fechamento", "negociacao")

    Returns:
        Dict da skill vencedora, ou None se nenhuma se aplica.
    """
    skills = listar_skills(apenas_ativas=True)
    candidatos = []

    for skill in skills:
        if _disc_match(skill, disc_profile) and _score_match(skill, score) and _stage_match(skill, conversation_stage):
            candidatos.append(skill)

    if not candidatos:
        return None

    # Maior priority vence; empate: prefere builtin
    candidatos.sort(
        key=lambda s: (int(s.get("priority") or 50), 1 if s.get("source") == "builtin" else 0),
        reverse=True,
    )
    return candidatos[0]


def resolver_skill_context(
    disc_profile: str = "",
    score: float = 50.0,
    conversation_stage: str = "abertura",
) -> str:
    """
    Retorna o texto de injeção da skill escolhida, ou "" se nenhuma aplicável.
    Este texto é adicionado ao final do prompt de tempo real da IA.
    """
    skill = resolver_melhor_skill(disc_profile, score, conversation_stage)
    if not skill:
        return ""

    injection = (skill.get("system_injection") or "").strip()
    if not injection:
        return ""

    logger.debug("[Skills] Skill aplicada: %s (score=%.0f, disc=%s, stage=%s)",
                 skill.get("name"), score, disc_profile, conversation_stage)
    return f"\n\n{injection}"


# ─────────────────────────────────────────────────────────
# CRUD DE SKILLS (DB)
# ─────────────────────────────────────────────────────────

def salvar_skill(skill: dict) -> str:
    """Persiste uma skill customizada no MySQL. Retorna UUID."""
    sid = str(uuid.uuid4())
    agora = datetime.now()
    triggers = skill.get("triggers") or {}
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO skills
                (id, name, description, trigger_disc, trigger_min_score, trigger_max_score,
                 trigger_stages, priority, system_injection, tactics,
                 is_active, source, source_playbook_id, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s,%s,%s)
            """,
            (
                sid,
                str(skill.get("name") or "")[:255],
                str(skill.get("description") or ""),
                json.dumps(triggers.get("disc_profiles") or skill.get("trigger_disc") or [], ensure_ascii=False),
                int(triggers.get("min_score") if triggers else skill.get("trigger_min_score") or 0),
                int(triggers.get("max_score") if triggers else skill.get("trigger_max_score") or 100),
                json.dumps(triggers.get("stages") or skill.get("trigger_stages") or [], ensure_ascii=False),
                int(skill.get("priority") or 70),
                str(skill.get("system_injection") or ""),
                json.dumps(skill.get("tactics") or [], ensure_ascii=False),
                str(skill.get("source") or "generated"),
                skill.get("source_playbook_id"),
                agora,
                agora,
            ),
        )
    conn.close()
    return sid


def atualizar_skill(skill_id: str, campos: dict) -> bool:
    """Atualiza campos editáveis de uma skill DB."""
    _EDITAVEIS = {"name", "description", "system_injection", "tactics", "priority", "is_active",
                  "trigger_disc", "trigger_min_score", "trigger_max_score", "trigger_stages"}
    sets, vals = [], []
    for k, v in campos.items():
        if k not in _EDITAVEIS:
            continue
        if k in ("tactics", "trigger_disc", "trigger_stages") and isinstance(v, list):
            v = json.dumps(v, ensure_ascii=False)
        sets.append(f"{k} = %s")
        vals.append(v)
    if not sets:
        return False
    sets.append("updated_at = %s")
    vals.append(datetime.now())
    vals.append(skill_id)
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(f"UPDATE skills SET {', '.join(sets)} WHERE id = %s", vals)
        conn.close()
        return True
    except Exception as e:
        logger.error("[Skills] Erro ao atualizar skill %s: %s", skill_id, e)
        return False


def deletar_skill(skill_id: str) -> bool:
    """Remove uma skill do DB."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM skills WHERE id = %s", (skill_id,))
            affected = cur.rowcount
        conn.close()
        return affected > 0
    except Exception as e:
        logger.error("[Skills] Erro ao deletar skill %s: %s", skill_id, e)
        return False


# ─────────────────────────────────────────────────────────
# T3.3 — GERADOR DE SKILL VIA IA
# ─────────────────────────────────────────────────────────

def _get_prompt_skill() -> str:
    global _PROMPT_TEMPLATE
    if _PROMPT_TEMPLATE is None:
        _PROMPT_TEMPLATE = _PROMPT_PATH.read_text(encoding="utf-8")
    return _PROMPT_TEMPLATE


def gerar_skill(contexto: str, source_playbook_id: Optional[str] = None) -> Optional[dict]:
    """
    Chama a IA para gerar uma skill comercial reutilizável.

    Args:
        contexto: Texto descrevendo o caso (playbook, reunião, situação específica)
        source_playbook_id: UUID do playbook de origem (para rastreabilidade)

    Returns:
        Dict com campos da skill, ou None se falhou.
    """
    from api.ai_router import chamar_ia
    prompt = _get_prompt_skill().replace("{contexto}", contexto)

    try:
        resposta = chamar_ia(
            system_prompt=prompt,
            user_content="Crie uma skill reutilizável baseada neste caso.",
        )
    except Exception as e:
        logger.error("[Skills] Erro ao chamar IA: %s", e)
        return None

    if isinstance(resposta, dict):
        if "skill" in resposta and isinstance(resposta["skill"], dict):
            resposta = resposta["skill"]
        if "name" not in resposta:
            logger.warning("[Skills] IA não retornou campo 'name'. Keys: %s", list(resposta.keys()))
            return None
        resposta["source_playbook_id"] = source_playbook_id
        return resposta

    logger.warning("[Skills] Resposta IA inválida: %s", type(resposta))
    return None


def gerar_e_salvar_skill(contexto: str, source_playbook_id: Optional[str] = None) -> Optional[str]:
    """Pipeline completo: gera via IA e persiste. Retorna UUID ou None."""
    try:
        skill = gerar_skill(contexto, source_playbook_id)
        if not skill:
            return None
        sid = salvar_skill(skill)
        logger.info("✅ [Skills] Skill '%s' salva (id=%s)", skill.get("name"), sid)
        return sid
    except Exception as e:
        logger.error("[Skills] Erro no pipeline de geração: %s", e)
        return None
