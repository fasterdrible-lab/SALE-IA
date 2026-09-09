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
                    status              VARCHAR(20)  NOT NULL DEFAULT 'approved',
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


def _candidatos_aplicaveis(disc_profile: str, score: float, conversation_stage: str) -> list:
    """Skills ativas cujos triggers batem com o contexto, ordenadas por
    prioridade (maior primeiro; empate prefere builtin). Extraído para ser
    compartilhado por resolver_melhor_skill() e resolver_skill_context() —
    listar_skills() bate em arquivo+MySQL, não deve rodar duas vezes por
    resolução."""
    skills = listar_skills(apenas_ativas=True)
    candidatos = [
        skill for skill in skills
        if _disc_match(skill, disc_profile) and _score_match(skill, score) and _stage_match(skill, conversation_stage)
    ]
    candidatos.sort(
        key=lambda s: (int(s.get("priority") or 50), 1 if s.get("source") == "builtin" else 0),
        reverse=True,
    )
    return candidatos


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
    candidatos = _candidatos_aplicaveis(disc_profile, score, conversation_stage)
    return candidatos[0] if candidatos else None


# ─────────────────────────────────────────────────────────
# SKILL RESOLVER V2 (Fase 5 do PROMPT MESTRE)
# ─────────────────────────────────────────────────────────
#
# TAREFA 5.1 — Expandir triggers: o prompt mestre pede 11 sinais novos
# (objection_type, pain_type, budget_status, decision_maker_status,
# buying_signal, risk, product, segment, competitor, meeting_type,
# urgency). Só 4 têm hoje um sinal estruturado real em algum agente —
# os outros 7 exigiriam um agente novo pra extrair esse dado (nenhum
# lugar do sistema classifica objection_type/pain_type/product/segment/
# competitor/meeting_type hoje) e por isso NAO foram adicionados aqui,
# pra nao inventar filtro sobre dado que nao existe:
#   - buying_signal          <- key_moments/eventos com type="buying_signal"
#   - budget_status          <- Closer::maturity_score.budget_identificado
#   - decision_maker_status  <- Closer::maturity_score.decisores_mapeados
#   - urgency                <- Closer::maturity_score.urgencia_identificada
#
# TAREFA 5.2/5.3 — resolver_skills_relevantes() substitui o conceito de
# "1 vencedora" por 3 baldes (primary/supporting/cases), com os limites
# pedidos (max primary=1, supporting=2, cases=1).
#
# Deliberadamente NAO plugado em processador_tempo_real.py ainda — trocar
# resolver_skill_context() (1 skill) por multiplas skills no prompt muda
# tamanho/custo de contexto em producao real, mesmo padrao de
# "ativar so depois de confirmar com o usuario" ja usado no Cost Router/
# Otimizacao (Fases 4/5 do Cost Intelligence). resolver_melhor_skill() e
# resolver_skill_context() continuam sendo o caminho ativo em producao,
# sem nenhuma mudanca de comportamento.

def _sinal_bool_match(skill: dict, chave_trigger: str, valor_real: Optional[bool]) -> bool:
    """Trigger booleano opcional e generico (buying_signal, budget_status,
    decision_maker_status, urgency). Skill que nao declara `chave_trigger`
    em `triggers` nao tem restricao (mesmo espirito de "lista vazia =
    qualquer valor" dos matches existentes) — condicao necessaria pra
    nenhuma das 5 skills builtin/custom existentes mudar de comportamento."""
    triggers = skill.get("triggers", {}) or {}
    exigido = triggers.get(chave_trigger)
    if exigido is None:
        return True
    return bool(valor_real) == bool(exigido)


def _candidatos_aplicaveis_v2(
    disc_profile: str,
    score: float,
    conversation_stage: str,
    buying_signal: Optional[bool] = None,
    budget_status: Optional[bool] = None,
    decision_maker_status: Optional[bool] = None,
    urgency: Optional[bool] = None,
) -> list:
    """Mesmo filtro de _candidatos_aplicaveis() (DISC/score/stage) mais os
    4 triggers novos suportados (TAREFA 5.1). Skills que nao usam os
    triggers novos continuam batendo exatamente como antes."""
    skills = listar_skills(apenas_ativas=True)
    candidatos = [
        skill for skill in skills
        if _disc_match(skill, disc_profile)
        and _score_match(skill, score)
        and _stage_match(skill, conversation_stage)
        and _sinal_bool_match(skill, "requires_buying_signal", buying_signal)
        and _sinal_bool_match(skill, "requires_budget_status", budget_status)
        and _sinal_bool_match(skill, "requires_decision_maker_status", decision_maker_status)
        and _sinal_bool_match(skill, "requires_urgency", urgency)
    ]
    candidatos.sort(
        key=lambda s: (int(s.get("priority") or 50), 1 if s.get("source") == "builtin" else 0),
        reverse=True,
    )
    return candidatos


def resolver_skills_relevantes(
    disc_profile: str = "",
    score: float = 50.0,
    conversation_stage: str = "abertura",
    buying_signal: Optional[bool] = None,
    budget_status: Optional[bool] = None,
    decision_maker_status: Optional[bool] = None,
    urgency: Optional[bool] = None,
) -> dict:
    """
    TAREFA 5.2/5.3 do PROMPT MESTRE — em vez de eleger 1 unica skill
    vencedora, retorna ate 3 grupos:
        {"primary": dict|None, "supporting": list[dict], "cases": list[dict]}

    Limites (TAREFA 5.3): max 1 primary, max 2 supporting, max 1 case.
    "cases" sao skills geradas a partir de KnowledgeItems tipo CASE
    (Biblioteca de Inteligencia Fase 4/Fase 3 de integracao) — reconhecidas
    pelo prefixo "[CASE]" que mapear_knowledge_item_para_skill() ja grava
    no system_injection; nao existe hoje nenhum campo separado marcando
    "isto e um case", entao a deteccao usa o dado que ja existe em vez de
    criar uma coluna nova so pra isso.
    """
    candidatos = _candidatos_aplicaveis_v2(
        disc_profile, score, conversation_stage,
        buying_signal, budget_status, decision_maker_status, urgency,
    )

    cases = [c for c in candidatos if (c.get("system_injection") or "").startswith("[CASE]")]
    demais = [c for c in candidatos if c not in cases]

    return {
        "primary": demais[0] if demais else None,
        "supporting": demais[1:3],
        "cases": cases[:1],
    }


def resolver_skill_context(
    disc_profile: str = "",
    score: float = 50.0,
    conversation_stage: str = "abertura",
    meeting_id: Optional[str] = None,
) -> str:
    """
    Retorna o texto de injeção da skill escolhida, ou "" se nenhuma aplicável.
    Este texto é adicionado ao final do prompt de tempo real da IA.

    Instrumentação (Observability Fase 1): registra span "skill_resolver"
    com quantas skills foram consideradas, qual foi selecionada, score,
    DISC, estágio e prioridade — nunca bloqueia a resolução se o provider
    de observabilidade falhar.
    """
    candidatos = _candidatos_aplicaveis(disc_profile, score, conversation_stage)
    skill = candidatos[0] if candidatos else None

    try:
        from services.observability.factory import get_observability_provider
        obs = get_observability_provider()
        span = obs.start_span(
            name="skill_resolver",
            meeting_id=meeting_id,
            input={"disc_profile": disc_profile, "score": score, "conversation_stage": conversation_stage},
            metadata={
                "candidatos_considerados": len(candidatos),
                "skill_selecionada": skill.get("name") if skill else None,
                "skill_priority": skill.get("priority") if skill else None,
                "skill_source": skill.get("source") if skill else None,
            },
        )
        obs.end_span(span, output={"skill_selecionada": skill.get("name") if skill else None})
    except Exception:
        pass

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

def migrar_coluna_status_skills():
    """Adiciona coluna status (VARCHAR, default 'approved') à tabela
    skills, se ainda não existir. Preparação para o pipeline
    automático-com-aprovação (Sales Brain Fase 7.3) — skills já
    existentes ficam 'approved' pelo DEFAULT, sem mudança de comportamento
    até o gate de aprovação entrar em vigor."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM skills LIKE 'status'")
            if cur.fetchone() is None:
                cur.execute(
                    "ALTER TABLE skills ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'approved'"
                )
                logger.info("[Skills] Coluna status adicionada à tabela skills.")
        conn.close()
    except Exception as e:
        logger.error("[Skills] Erro ao migrar coluna status: %s", e)


def salvar_skill(skill: dict) -> str:
    """Persiste uma skill customizada no MySQL. Retorna UUID.

    `skill.get("status")` controla o gate de aprovação (Sales Brain Fase
    7.3): 'pending' nasce inativa (`is_active=0`, some do skill_resolver
    até aprovação); qualquer outro valor (default 'approved') nasce ativa
    como sempre — mantém compatibilidade com todos os chamadores
    existentes, que não passam esse campo."""
    sid = str(uuid.uuid4())
    agora = datetime.now()
    triggers = skill.get("triggers") or {}
    status = str(skill.get("status") or "approved")
    is_active = 0 if status == "pending" else 1
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO skills
                (id, name, description, trigger_disc, trigger_min_score, trigger_max_score,
                 trigger_stages, priority, system_injection, tactics,
                 is_active, status, source, source_playbook_id, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                is_active,
                status,
                str(skill.get("source") or "generated"),
                skill.get("source_playbook_id"),
                agora,
                agora,
            ),
        )
    conn.close()
    return sid


# ─────────────────────────────────────────────────────────
# KNOWLEDGE COMPILER (Fase 3) — Skill a partir de um KnowledgeItem aprovado
# ─────────────────────────────────────────────────────────

def _montar_system_injection_de_item(item: dict) -> str:
    """Monta o texto de injeção a partir dos campos já estruturados do
    KnowledgeItem (Fase 2) — nunca do texto cru do documento original."""
    tipo = item.get("item_type", "")
    titulo = item.get("title", "")
    conteudo = item.get("content", "")
    metadata = item.get("metadata") or {}

    partes = [f"[{tipo}] {titulo}", conteudo]

    if tipo == "FRAMEWORK":
        if metadata.get("when_to_use"):
            partes.append(f"Quando usar: {metadata['when_to_use']}")
        if metadata.get("steps"):
            partes.append("Passos: " + "; ".join(metadata["steps"]))
    elif tipo == "OBJECTION":
        if metadata.get("recommended_actions"):
            partes.append("Ações recomendadas: " + "; ".join(metadata["recommended_actions"]))
        if metadata.get("questions"):
            partes.append("Perguntas úteis: " + "; ".join(metadata["questions"]))
    elif tipo == "DECISION_RULE":
        if metadata.get("conditions"):
            partes.append("Condições: " + "; ".join(metadata["conditions"]))
        if metadata.get("action"):
            partes.append(f"Ação: {metadata['action']}")
    elif tipo == "SCRIPT":
        if metadata.get("objetivo"):
            partes.append(f"Objetivo: {metadata['objetivo']}")
    elif tipo == "ANTI_PATTERN":
        if metadata.get("alternative"):
            partes.append(f"Alternativa: {metadata['alternative']}")

    return "\n".join(partes)


def mapear_knowledge_item_para_skill(item: dict) -> dict:
    """Mapeamento puro (sem I/O) de um KnowledgeItem aprovado para o dict
    aceito por salvar_skill(). Extraído separado para ser testável sem
    tocar o MySQL real. Triggers ficam amplos por padrão (qualquer DISC/
    estágio/score) — resolver_melhor_skill() elege só 1 vencedora por
    prioridade, então uma skill nova não deve competir com prioridade alta
    sem o usuário revisar antes (aba Skills do dashboard)."""
    return {
        "name": (item.get("title") or "Skill sem nome")[:255],
        "description": f"Gerada da Biblioteca de Inteligência ({item.get('item_type')}, fonte #{item.get('source_id')}).",
        "system_injection": _montar_system_injection_de_item(item),
        "tactics": [],
        "priority": 60,
        "source": "knowledge_compiler",
        "trigger_disc": [],
        "trigger_min_score": 0,
        "trigger_max_score": 100,
        "trigger_stages": [],
    }


def gerar_skill_de_knowledge_item(item: dict) -> str:
    """Cria uma Skill customizada a partir de um KnowledgeItem aprovado.
    Retorna o id da skill criada."""
    return salvar_skill(mapear_knowledge_item_para_skill(item))


def atualizar_skill(skill_id: str, campos: dict) -> bool:
    """Atualiza campos editáveis de uma skill DB."""
    _EDITAVEIS = {"name", "description", "system_injection", "tactics", "priority", "is_active", "status",
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
    from api import ai_features
    prompt = _get_prompt_skill().replace("{contexto}", contexto)

    try:
        resposta = chamar_ia(
            system_prompt=prompt,
            user_content="Crie uma skill reutilizável baseada neste caso.",
            feature=ai_features.SKILL_GERACAO,
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


def _autopilot_ativo() -> bool:
    """Mesmo kill-switch de agent/playbook_generator.py::autopilot_ativo()
    (SALES_BRAIN_AUTOPILOT_ENABLED) — duplicado aqui de propósito, mesmo
    padrão de kill-switch checado localmente em cada módulo já usado no
    Cost Intelligence (ex.: OTIMIZACAO_*_ATIVO)."""
    return os.getenv("SALES_BRAIN_AUTOPILOT_ENABLED", "true").strip().lower() != "false"


def gerar_e_salvar_skill(contexto: str, source_playbook_id: Optional[str] = None) -> Optional[str]:
    """Pipeline completo: gera via IA e persiste. Retorna UUID ou None.

    Toda skill gerada por IA (manual, pelo botão '🧠 Skill', ou automática,
    após um playbook nascer — Sales Brain Fase 7.3) nasce 'pending' —
    mesma rede de segurança já usada no Knowledge Compiler (DRAFT/APPROVED)
    — enquanto SALES_BRAIN_AUTOPILOT_ENABLED estiver ativo. Skills mapeadas
    de um KnowledgeItem já aprovado (gerar_skill_de_knowledge_item) não
    passam por aqui, e continuam nascendo aprovadas."""
    try:
        skill = gerar_skill(contexto, source_playbook_id)
        if not skill:
            return None
        skill["status"] = "pending" if _autopilot_ativo() else "approved"
        sid = salvar_skill(skill)
        logger.info("✅ [Skills] Skill '%s' salva (id=%s, status=%s)", skill.get("name"), sid, skill["status"])

        if source_playbook_id:
            try:
                from agent.knowledge_graph import registrar_aresta
                registrar_aresta("playbook", source_playbook_id, "skill", sid, "gerou_skill")
            except Exception:
                pass

        return sid
    except Exception as e:
        logger.error("[Skills] Erro no pipeline de geração: %s", e)
        return None
