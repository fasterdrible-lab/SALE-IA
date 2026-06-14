"""
agent/sales_memory.py — Sales Memory (Fase 1 do SALEIA Sales Brain)

Memória persistente de conhecimento comercial extraído de reuniões.
Cada memória captura um aprendizado reutilizável (objeção, dor, sinal de compra, etc.)
que pode ser recuperado para enriquecer futuras análises em tempo real.

Tipos:
  objection          — objeção recorrente e como foi tratada
  pain_point         — dor do cliente com contexto de segmento/perfil
  buying_signal      — sinal de compra identificado e score no momento
  closing_signal     — sinal de fechamento e sequência usada
  discovery_pattern  — padrão eficaz de descoberta (perguntas que funcionaram)
  disc_pattern       — padrão comportamental DISC confirmado com evidências
  financial_pattern  — padrão financeiro do segmento (faturamento, budget médio)
  playbook_insight   — insight de playbook derivado de reunião ganha
"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

import numpy as np
import pymysql

logger = logging.getLogger("saleia.sales_memory")

# Tipos válidos de memória
MEMORY_TYPES = {
    "objection",
    "pain_point",
    "buying_signal",
    "closing_signal",
    "discovery_pattern",
    "disc_pattern",
    "financial_pattern",
    "playbook_insight",
}


# ─────────────────────────────────────────────────────────
# CONEXÃO
# ─────────────────────────────────────────────────────────

def _get_conn():
    required = ("DB_HOST", "DB_USER", "DB_PASS", "DB_NAME")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Variaveis de banco ausentes: {', '.join(missing)}")

    return pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 3306)),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASS"],
        database=os.environ["DB_NAME"],
        charset="utf8mb4",
        connect_timeout=10,
    )


# ─────────────────────────────────────────────────────────
# MIGRAÇÃO
# ─────────────────────────────────────────────────────────

def criar_tabela_sales_memories():
    """Cria a tabela sales_memories se não existir."""
    sql = """
    CREATE TABLE IF NOT EXISTS sales_memories (
        id                VARCHAR(36)  NOT NULL PRIMARY KEY,
        organization_id   VARCHAR(100),
        memory_type       VARCHAR(50)  NOT NULL,
        title             VARCHAR(255) NOT NULL,
        content           MEDIUMTEXT   NOT NULL,
        source_meeting_id VARCHAR(200),
        confidence        FLOAT        NOT NULL DEFAULT 0.8,
        tags              TEXT,
        created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_type        (memory_type),
        INDEX idx_meeting     (source_meeting_id),
        INDEX idx_org_type    (organization_id, memory_type),
        INDEX idx_created     (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        conn.close()
        logger.info("[SalesMemory] Tabela sales_memories criada/verificada.")
    except Exception as e:
        logger.error("[SalesMemory] Erro ao criar tabela: %s", e)


# ─────────────────────────────────────────────────────────
# ESCRITA
# ─────────────────────────────────────────────────────────

def salvar_memoria(
    memory_type: str,
    title: str,
    content: str,
    source_meeting_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    confidence: float = 0.8,
    tags: Optional[list] = None,
) -> str:
    """
    Persiste um aprendizado comercial. Retorna o id gerado.

    Args:
        memory_type: um dos 8 tipos definidos em MEMORY_TYPES
        title: título curto da memória (max 255 chars)
        content: conteúdo completo — contexto, o que aconteceu, o que funcionou
        source_meeting_id: meeting_id de origem (rastreabilidade)
        organization_id: tenant futuro (nullable por ora)
        confidence: confiança da IA na qualidade desta memória (0.0–1.0)
        tags: lista de strings para facilitar busca (ex: ["B2B", "SaaS", "preço"])

    Returns:
        id da memória criada (UUID v4)
    """
    if memory_type not in MEMORY_TYPES:
        raise ValueError(f"memory_type inválido: {memory_type}. Use um de: {MEMORY_TYPES}")

    mem_id = str(uuid.uuid4())
    tags_json = json.dumps(tags or [], ensure_ascii=False)

    sql = """
    INSERT INTO sales_memories
        (id, organization_id, memory_type, title, content,
         source_meeting_id, confidence, tags, created_at, updated_at)
    VALUES
        (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
    """
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, (
                mem_id, organization_id, memory_type,
                title, content, source_meeting_id,
                confidence, tags_json,
            ))
        conn.commit()
        conn.close()
        logger.info("[SalesMemory] Memória salva: %s (tipo=%s, reunião=%s)", mem_id, memory_type, source_meeting_id)
        return mem_id
    except Exception as e:
        logger.error("[SalesMemory] Erro ao salvar memória: %s", e)
        raise


def salvar_memorias_em_lote(memorias: list) -> list:
    """
    Salva uma lista de memórias de uma só vez (pós-extração pelo Knowledge Extractor).

    Args:
        memorias: lista de dicts com os mesmos campos de salvar_memoria()

    Returns:
        lista de ids criados
    """
    ids = []
    for mem in memorias:
        try:
            mem_id = salvar_memoria(
                memory_type=mem["memory_type"],
                title=mem["title"],
                content=mem["content"],
                source_meeting_id=mem.get("source_meeting_id"),
                organization_id=mem.get("organization_id"),
                confidence=float(mem.get("confidence", 0.8)),
                tags=mem.get("tags", []),
            )
            ids.append(mem_id)
        except Exception as e:
            logger.warning("[SalesMemory] Falha ao salvar memória em lote: %s — %s", mem.get("title"), e)
    return ids


# ─────────────────────────────────────────────────────────
# LEITURA
# ─────────────────────────────────────────────────────────

def _row_para_dict(row: tuple, columns: tuple) -> dict:
    d = dict(zip(columns, row))
    if "tags" in d and d["tags"]:
        try:
            d["tags"] = json.loads(d["tags"])
        except Exception:
            d["tags"] = []
    elif "tags" in d:
        d["tags"] = []
    if "created_at" in d and isinstance(d["created_at"], datetime):
        d["created_at"] = d["created_at"].isoformat()
    if "updated_at" in d and isinstance(d["updated_at"], datetime):
        d["updated_at"] = d["updated_at"].isoformat()
    return d


def listar_memorias(
    memory_type: Optional[str] = None,
    organization_id: Optional[str] = None,
    source_meeting_id: Optional[str] = None,
    confidence_min: float = 0.0,
    limit: int = 100,
    offset: int = 0,
) -> list:
    """
    Lista memórias com filtros opcionais.

    Returns:
        lista de dicts com todos os campos da tabela
    """
    conditions = ["confidence >= %s"]
    params: list = [confidence_min]

    if memory_type:
        conditions.append("memory_type = %s")
        params.append(memory_type)
    if organization_id:
        conditions.append("organization_id = %s")
        params.append(organization_id)
    if source_meeting_id:
        conditions.append("source_meeting_id = %s")
        params.append(source_meeting_id)

    where = " AND ".join(conditions)
    sql = f"""
        SELECT id, organization_id, memory_type, title, content,
               source_meeting_id, confidence, tags, created_at, updated_at
        FROM sales_memories
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """
    params += [limit, offset]

    columns = (
        "id", "organization_id", "memory_type", "title", "content",
        "source_meeting_id", "confidence", "tags", "created_at", "updated_at",
    )

    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        conn.close()
        return [_row_para_dict(r, columns) for r in rows]
    except Exception as e:
        logger.error("[SalesMemory] Erro ao listar memórias: %s", e)
        return []


def buscar_por_reuniao(meeting_id: str) -> list:
    """Retorna todas as memórias geradas a partir de uma reunião específica."""
    return listar_memorias(source_meeting_id=meeting_id, limit=200)


def contar_por_tipo() -> dict:
    """Retorna contagem de memórias agrupadas por memory_type."""
    sql = """
        SELECT memory_type, COUNT(*) as total
        FROM sales_memories
        GROUP BY memory_type
        ORDER BY total DESC
    """
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
        conn.close()
        return {row[0]: row[1] for row in rows}
    except Exception as e:
        logger.error("[SalesMemory] Erro ao contar por tipo: %s", e)
        return {}


# ─────────────────────────────────────────────────────────
# ATUALIZAÇÃO / EXCLUSÃO
# ─────────────────────────────────────────────────────────

def atualizar_memoria(mem_id: str, title: Optional[str] = None, content: Optional[str] = None,
                      confidence: Optional[float] = None, tags: Optional[list] = None) -> bool:
    """Atualiza campos de uma memória existente. Retorna True se encontrou e atualizou."""
    sets = []
    params = []

    if title is not None:
        sets.append("title = %s")
        params.append(title)
    if content is not None:
        sets.append("content = %s")
        params.append(content)
    if confidence is not None:
        sets.append("confidence = %s")
        params.append(confidence)
    if tags is not None:
        sets.append("tags = %s")
        params.append(json.dumps(tags, ensure_ascii=False))

    if not sets:
        return False

    sets.append("updated_at = NOW()")
    params.append(mem_id)

    sql = f"UPDATE sales_memories SET {', '.join(sets)} WHERE id = %s"
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, params)
            affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected > 0
    except Exception as e:
        logger.error("[SalesMemory] Erro ao atualizar memória %s: %s", mem_id, e)
        return False


def deletar_memoria(mem_id: str) -> bool:
    """Remove uma memória permanentemente. Retorna True se existia."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sales_memories WHERE id = %s", (mem_id,))
            affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected > 0
    except Exception as e:
        logger.error("[SalesMemory] Erro ao deletar memória %s: %s", mem_id, e)
        return False


# ─────────────────────────────────────────────────────────
# EMBEDDINGS — MIGRAÇÃO
# ─────────────────────────────────────────────────────────

def migrar_coluna_embedding_memories():
    """Adiciona coluna embedding (LONGTEXT) à tabela sales_memories se não existir."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM sales_memories LIKE 'embedding'")
            if cur.fetchone() is None:
                cur.execute("ALTER TABLE sales_memories ADD COLUMN embedding LONGTEXT")
                logger.info("[SalesMemory] Coluna embedding adicionada à tabela sales_memories.")
            else:
                logger.debug("[SalesMemory] Coluna embedding já existe.")
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("[SalesMemory] Erro ao migrar coluna embedding: %s", e)


# ─────────────────────────────────────────────────────────
# EMBEDDINGS — CACHE EM MEMÓRIA
# ─────────────────────────────────────────────────────────

_cache_memorias: Optional[dict] = None


def invalidar_cache_memorias():
    """Força recarregamento do cache na próxima busca."""
    global _cache_memorias
    _cache_memorias = None


def _carregar_cache_memorias() -> dict:
    """
    Carrega todos os embeddings de sales_memories em memória (lazy, com cache).
    Mesmo padrão de base_conhecimento.py.
    """
    global _cache_memorias
    if _cache_memorias is not None:
        return _cache_memorias

    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, memory_type, title, content, confidence, tags, embedding "
                "FROM sales_memories WHERE embedding IS NOT NULL"
            )
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        logger.error("[SalesMemory] Erro ao carregar cache de embeddings: %s", e)
        _cache_memorias = {"vazio": True}
        return _cache_memorias

    if not rows:
        _cache_memorias = {"vazio": True}
        return _cache_memorias

    ids, tipos, titulos, conteudos, confs, tags_list, vecs = [], [], [], [], [], [], []
    for row in rows:
        emb = row[6]
        if isinstance(emb, str):
            try:
                emb = json.loads(emb)
            except Exception:
                continue
        if not emb:
            continue
        ids.append(row[0])
        tipos.append(row[1] or "")
        titulos.append(row[2] or "")
        conteudos.append((row[3] or "")[:800])
        confs.append(float(row[4] or 0.0))
        try:
            tags_list.append(json.loads(row[5] or "[]"))
        except Exception:
            tags_list.append([])
        vecs.append(emb)

    _cache_memorias = {
        "vazio": False,
        "ids": ids,
        "tipos": tipos,
        "titulos": titulos,
        "conteudos": conteudos,
        "confs": confs,
        "tags": tags_list,
        "matrix": np.array(vecs, dtype=np.float32),
    }
    logger.info("[SalesMemory] Cache de embeddings carregado: %d memórias.", len(ids))
    return _cache_memorias


def _cosine_top_k(vec: np.ndarray, matrix: np.ndarray, k: int) -> list:
    vec_norm = vec / (np.linalg.norm(vec) + 1e-9)
    mat_norm = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
    sims = mat_norm @ vec_norm
    top_indices = np.argsort(sims)[::-1][:k]
    return [(int(idx), float(sims[idx])) for idx in top_indices]


# ─────────────────────────────────────────────────────────
# EMBEDDINGS — GERAÇÃO E PERSISTÊNCIA
# ─────────────────────────────────────────────────────────

def gerar_embedding(texto: str) -> Optional[list]:
    """
    Gera embedding via OpenAI text-embedding-3-small (1536 dimensões).
    Retorna lista de floats ou None em caso de falha.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        logger.warning("[SalesMemory] OPENAI_API_KEY não configurada — embedding ignorado.")
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, timeout=30)
        resp = client.embeddings.create(
            model="text-embedding-3-small",
            input=texto[:6000],
        )
        return resp.data[0].embedding
    except Exception as e:
        logger.error("[SalesMemory] Erro ao gerar embedding: %s", e)
        return None


def salvar_embedding_memoria(mem_id: str, embedding: list) -> bool:
    """Persiste o embedding JSON na coluna embedding da memória."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sales_memories SET embedding = %s WHERE id = %s",
                (json.dumps(embedding), mem_id),
            )
            affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected > 0
    except Exception as e:
        logger.error("[SalesMemory] Erro ao salvar embedding da memória %s: %s", mem_id, e)
        return False


def gerar_e_salvar_embeddings_em_lote(itens: list) -> int:
    """
    Gera e persiste embeddings para uma lista de (mem_id, conteudo).
    Invalida o cache após salvar.

    Args:
        itens: lista de tuplas (mem_id: str, conteudo: str)

    Returns:
        número de embeddings salvos com sucesso
    """
    salvos = 0
    for mem_id, conteudo in itens:
        emb = gerar_embedding(conteudo)
        if emb and salvar_embedding_memoria(mem_id, emb):
            salvos += 1

    if salvos:
        invalidar_cache_memorias()
        logger.info("[SalesMemory] %d embeddings gerados e salvos.", salvos)

    return salvos


# ─────────────────────────────────────────────────────────
# BUSCA SEMÂNTICA
# ─────────────────────────────────────────────────────────

def buscar_memorias_semantico(
    query: str,
    top_k: int = 5,
    memory_type: Optional[str] = None,
    confidence_min: float = 0.0,
    similarity_min: float = 0.25,
) -> list:
    """
    Busca memórias comerciais por similaridade semântica com a query.

    Args:
        query: texto livre (fragmento da reunião, objeção, pergunta, etc.)
        top_k: número máximo de resultados
        memory_type: filtro opcional por tipo de memória
        confidence_min: filtrar memórias com confidence abaixo deste limiar
        similarity_min: score mínimo de cosseno para retornar (0.0-1.0)

    Returns:
        lista de dicts com campos da memória + "similarity" (float 0-1)
    """
    cache = _carregar_cache_memorias()
    if cache.get("vazio"):
        return []

    vec_query = gerar_embedding(query)
    if vec_query is None:
        return []

    vec = np.array(vec_query, dtype=np.float32)
    resultados_brutos = _cosine_top_k(vec, cache["matrix"], min(top_k * 3, len(cache["ids"])))

    resultados = []
    for idx, sim in resultados_brutos:
        if sim < similarity_min:
            continue
        if memory_type and cache["tipos"][idx] != memory_type:
            continue
        if cache["confs"][idx] < confidence_min:
            continue

        resultados.append({
            "id":          cache["ids"][idx],
            "memory_type": cache["tipos"][idx],
            "title":       cache["titulos"][idx],
            "content":     cache["conteudos"][idx],
            "confidence":  cache["confs"][idx],
            "tags":        cache["tags"][idx],
            "similarity":  round(sim, 4),
        })

        if len(resultados) >= top_k:
            break

    return resultados


def buscar_contexto_para_reuniao(fragmento: str, top_k: int = 3) -> Optional[str]:
    """
    Versão formatada de buscar_memorias_semantico() para injeção direta em prompts.
    Retorna bloco de texto pronto para uso no contexto da IA, ou None se vazio.
    """
    memorias = buscar_memorias_semantico(fragmento, top_k=top_k, similarity_min=0.30)
    if not memorias:
        return None

    _TIPO_LABEL = {
        "objection":         "Objeção",
        "pain_point":        "Dor",
        "buying_signal":     "Sinal de Compra",
        "closing_signal":    "Sinal de Fechamento",
        "discovery_pattern": "Padrão de Descoberta",
        "disc_pattern":      "Padrão DISC",
        "financial_pattern": "Padrão Financeiro",
        "playbook_insight":  "Insight de Playbook",
    }

    blocos = []
    for m in memorias:
        label = _TIPO_LABEL.get(m["memory_type"], m["memory_type"])
        blocos.append(
            f"• [{label}] {m['title']}\n"
            f"  {m['content'][:600]}"
        )

    return (
        "MEMÓRIAS COMERCIAIS RELEVANTES "
        "(aprendizados de reuniões anteriores similares — use para calibrar a análise):\n\n"
        + "\n\n".join(blocos)
    )
