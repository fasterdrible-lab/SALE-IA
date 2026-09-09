"""
agent/knowledge_graph.py — Knowledge Graph (Sales Brain Fase 7.2)

Relaciona as entidades já existentes do Sales Brain (cliente, reunião,
memória, playbook, skill) por arestas simples — sem lib de grafo nova,
sem duplicar dado primário (as arestas só guardam referências por id, os
dados reais continuam em client_profiles/sales_memories/playbooks/skills).

Gravação é sempre best-effort (idempotente, nunca lança) — chamada nos
próprios pontos de criação de cada entidade (vincular cliente↔reunião,
extrair memória, gerar playbook, gerar skill), como um hook a mais que
nunca pode quebrar o fluxo principal.
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Optional

import pymysql
import pymysql.cursors

logger = logging.getLogger("saleia.knowledge_graph")

TIPOS_VALIDOS = {"cliente", "reuniao", "memoria", "playbook", "skill"}


# ─────────────────────────────────────────────────────────
# CONEXÃO / MIGRAÇÃO
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


def criar_tabela_graph_edges() -> None:
    """Cria a tabela graph_edges. Idempotente."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS graph_edges (
                    id          VARCHAR(36)  PRIMARY KEY,
                    from_type   VARCHAR(30)  NOT NULL,
                    from_id     VARCHAR(100) NOT NULL,
                    to_type     VARCHAR(30)  NOT NULL,
                    to_id       VARCHAR(100) NOT NULL,
                    relacao     VARCHAR(50)  NOT NULL,
                    created_at  DATETIME     NOT NULL,
                    INDEX idx_from (from_type, from_id),
                    INDEX idx_to   (to_type, to_id),
                    UNIQUE KEY uq_aresta (from_type, from_id, to_type, to_id, relacao)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        conn.close()
        logger.info("✅ Tabela graph_edges verificada/criada.")
    except Exception as e:
        logger.error("❌ Erro ao criar tabela graph_edges: %s", e)


# ─────────────────────────────────────────────────────────
# ESCRITA
# ─────────────────────────────────────────────────────────

def registrar_aresta(from_type: str, from_id: str, to_type: str, to_id: str, relacao: str) -> bool:
    """Registra uma conexão entre duas entidades. Idempotente (a mesma
    aresta nunca duplica, graças à UNIQUE KEY) e best-effort — projetada
    para ser chamada de dentro de um try/except no ponto de criação de
    cada entidade, sem nunca derrubar o fluxo principal se falhar."""
    if from_type not in TIPOS_VALIDOS or to_type not in TIPOS_VALIDOS:
        logger.warning("[KnowledgeGraph] Tipo de entidade inválido: %s/%s", from_type, to_type)
        return False
    if not from_id or not to_id:
        return False
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT IGNORE INTO graph_edges
                    (id, from_type, from_id, to_type, to_id, relacao, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                (str(uuid.uuid4()), from_type, str(from_id), to_type, str(to_id), relacao, datetime.now()),
            )
        conn.close()
        return True
    except Exception as e:
        logger.warning("[KnowledgeGraph] Falha ao registrar aresta %s:%s -> %s:%s: %s",
                        from_type, from_id, to_type, to_id, e)
        return False


# ─────────────────────────────────────────────────────────
# LEITURA
# ─────────────────────────────────────────────────────────

def _rotulo_por_query(modulo_conn, tabela: str, coluna: str, entity_id: str) -> Optional[str]:
    """Busca pontual de rótulo (SELECT de 1 coluna por id) — mais barato
    que carregar a entidade inteira só para exibir um nome numa lista de
    conexões."""
    try:
        conn = modulo_conn()
        with conn.cursor() as cur:
            cur.execute(f"SELECT {coluna} FROM {tabela} WHERE id = %s", (entity_id,))
            row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return row[coluna] if isinstance(row, dict) else row[0]
    except Exception:
        return None


def _resolver_rotulo(tipo: str, entity_id: str) -> Optional[str]:
    """Resolve um rótulo legível (nome/título) para uma entidade conectada.
    Best-effort — nunca lança; retorna None se a entidade não existir mais
    ou o lookup falhar."""
    try:
        if tipo == "cliente":
            from agent.client_intelligence import obter_cliente
            c = obter_cliente(entity_id)
            return c.get("nome") if c else None
        if tipo == "reuniao":
            return entity_id  # meeting_id já é o identificador legível hoje
        if tipo == "memoria":
            from agent.sales_memory import _get_conn as _mem_conn
            return _rotulo_por_query(_mem_conn, "sales_memories", "title", entity_id)
        if tipo == "playbook":
            from agent.playbook_generator import obter_playbook
            p = obter_playbook(entity_id)
            return p.get("name") if p else None
        if tipo == "skill":
            from agent.skill_resolver import _get_conn as _skill_conn
            return _rotulo_por_query(_skill_conn, "skills", "name", entity_id)
    except Exception:
        return None
    return None


def buscar_conexoes(tipo: str, entity_id: str) -> list:
    """Retorna as conexões diretas (1 salto, nos dois sentidos) de uma
    entidade, com rótulo legível resolvido quando possível. Nunca lança —
    retorna lista vazia em qualquer falha."""
    if tipo not in TIPOS_VALIDOS or not entity_id:
        return []
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT from_type, from_id, to_type, to_id, relacao, created_at FROM graph_edges "
                "WHERE (from_type = %s AND from_id = %s) OR (to_type = %s AND to_id = %s) "
                "ORDER BY created_at DESC LIMIT 100",
                (tipo, entity_id, tipo, entity_id),
            )
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        logger.warning("[KnowledgeGraph] Erro ao buscar conexões de %s:%s: %s", tipo, entity_id, e)
        return []

    conexoes = []
    for row in rows:
        eh_origem = row["from_type"] == tipo and row["from_id"] == entity_id
        outro_tipo = row["to_type"] if eh_origem else row["from_type"]
        outro_id = row["to_id"] if eh_origem else row["from_id"]
        conexoes.append({
            "tipo": outro_tipo,
            "id": outro_id,
            "rotulo": _resolver_rotulo(outro_tipo, outro_id) or outro_id,
            "relacao": row["relacao"],
            "direcao": "saida" if eh_origem else "entrada",
        })
    return conexoes
