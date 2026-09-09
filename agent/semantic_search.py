"""
agent/semantic_search.py — Busca semântica unificada (Sales Brain, gap da
Tarefa 1.3: "Criar embeddings para memórias, relatórios, transcrições").

Diferente de sales_memory.py (cujos embeddings alimentam RAG em tempo real),
os embeddings daqui são **só para busca humana** — nunca injetados no
prompt da IA em tempo real. Indexar o relatório/transcrição inteiro no
contexto de tempo real duplicaria o que sales_memory.py já extrai como
aprendizado reutilizável (mesmo princípio já usado para não mapear
KnowledgeItem → sales_memory).

Indexação é disparada em BackgroundTask, no mesmo hook onde
knowledge_extractor.extrair_e_salvar_memorias já roda (após geração do
relatório) — nunca bloqueia a resposta ao usuário.
"""

import json
import logging
import os
from typing import Optional

import numpy as np
import pymysql

from services.embeddings import get_embedding_provider

logger = logging.getLogger("saleia.semantic_search")

FONTES_VALIDAS = {"relatorio", "transcricao"}


# ─────────────────────────────────────────────────────────
# CONEXÃO / MIGRAÇÃO
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


def criar_tabela_semantic_index():
    """Cria a tabela semantic_index se não existir. Idempotente."""
    sql = """
    CREATE TABLE IF NOT EXISTS semantic_index (
        id                VARCHAR(64)  NOT NULL PRIMARY KEY,
        fonte             VARCHAR(20)  NOT NULL,
        meeting_id        VARCHAR(200) NOT NULL,
        titulo            VARCHAR(255),
        trecho            MEDIUMTEXT,
        embedding         LONGTEXT,
        embedding_provider VARCHAR(20),
        embedding_model    VARCHAR(100),
        embedding_dim      INT,
        created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_fonte    (fonte),
        INDEX idx_meeting  (meeting_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        conn.close()
        logger.info("[SemanticSearch] Tabela semantic_index criada/verificada.")
    except Exception as e:
        logger.error("[SemanticSearch] Erro ao criar tabela: %s", e)


# ─────────────────────────────────────────────────────────
# INDEXAÇÃO
# ─────────────────────────────────────────────────────────

def _montar_texto_relatorio(resultado: dict) -> str:
    """Extrai um resumo textual compacto do relatório para embedding."""
    recap = (resultado.get("recapitulacao") or {})
    partes = []
    if isinstance(recap, dict):
        if recap.get("resumo_executivo"):
            partes.append(str(recap["resumo_executivo"]))
        estrateg = recap.get("recapitulacao_estrategica") or {}
        if isinstance(estrateg, dict):
            for chave in ("dores_identificadas", "objecoes_levantadas"):
                itens = estrateg.get(chave) or []
                if itens:
                    partes.append(", ".join(str(i) for i in itens))
    fin = resultado.get("diagnostico_financeiro") or {}
    if isinstance(fin, dict) and fin.get("produto_recomendado"):
        partes.append(f"Produto recomendado: {fin['produto_recomendado']}")
    disc = resultado.get("perfil_disc") or {}
    if isinstance(disc, dict) and (disc.get("tipo") or disc.get("perfil_primario")):
        partes.append(f"Perfil DISC: {disc.get('tipo') or disc.get('perfil_primario')}")
    return "\n".join(partes)[:6000]


def _salvar_indice(idx_id: str, fonte: str, meeting_id: str, titulo: str, trecho: str) -> bool:
    if fonte not in FONTES_VALIDAS:
        raise ValueError(f"fonte inválida: {fonte}")
    if not trecho or not trecho.strip():
        return False
    try:
        provider = get_embedding_provider()
    except Exception as e:
        logger.warning("[SemanticSearch] Provedor de embedding mal configurado: %s", e)
        return False

    resultado = provider.embed(trecho[:6000])
    if resultado is None:
        logger.warning("[SemanticSearch] Falha ao gerar embedding (%s/%s).", fonte, meeting_id)
        return False

    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO semantic_index
                    (id, fonte, meeting_id, titulo, trecho, embedding,
                     embedding_provider, embedding_model, embedding_dim, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                ON DUPLICATE KEY UPDATE
                    titulo = VALUES(titulo), trecho = VALUES(trecho),
                    embedding = VALUES(embedding),
                    embedding_provider = VALUES(embedding_provider),
                    embedding_model = VALUES(embedding_model),
                    embedding_dim = VALUES(embedding_dim),
                    created_at = NOW()
                """,
                (
                    idx_id, fonte, meeting_id, (titulo or "")[:255], trecho[:6000],
                    json.dumps(resultado.vector), resultado.provider, resultado.model, resultado.dimension,
                ),
            )
        conn.commit()
        conn.close()
        invalidar_cache_semantic_index()
        return True
    except Exception as e:
        logger.error("[SemanticSearch] Erro ao salvar índice (%s/%s): %s", fonte, meeting_id, e)
        return False


def indexar_relatorio(meeting_id: str, titulo: str, resultado: dict) -> bool:
    """Gera e persiste o embedding do relatório de uma reunião. Best-effort
    — projetado para BackgroundTask, nunca lança."""
    try:
        texto = _montar_texto_relatorio(resultado or {})
        return _salvar_indice(f"relatorio:{meeting_id}", "relatorio", meeting_id, titulo, texto)
    except Exception as e:
        logger.error("[SemanticSearch] Erro ao indexar relatório %s: %s", meeting_id, e)
        return False


def indexar_transcricao(meeting_id: str, titulo: str, transcricao: str) -> bool:
    """Gera e persiste o embedding da transcrição de uma reunião. Best-effort
    — projetado para BackgroundTask, nunca lança."""
    try:
        return _salvar_indice(f"transcricao:{meeting_id}", "transcricao", meeting_id, titulo, transcricao or "")
    except Exception as e:
        logger.error("[SemanticSearch] Erro ao indexar transcrição %s: %s", meeting_id, e)
        return False


# ─────────────────────────────────────────────────────────
# BUSCA — CACHE EM MEMÓRIA (mesmo padrão de agent/sales_memory.py)
# ─────────────────────────────────────────────────────────

_cache_indice: Optional[dict] = None


def invalidar_cache_semantic_index():
    global _cache_indice
    _cache_indice = None


def _carregar_cache_indice() -> dict:
    global _cache_indice
    if _cache_indice is not None:
        return _cache_indice

    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, fonte, meeting_id, titulo, trecho, embedding, "
                "embedding_provider, embedding_model, embedding_dim "
                "FROM semantic_index WHERE embedding IS NOT NULL"
            )
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        logger.error("[SemanticSearch] Erro ao carregar cache: %s", e)
        _cache_indice = {"vazio": True}
        return _cache_indice

    if not rows:
        _cache_indice = {"vazio": True}
        return _cache_indice

    contagem_meta: dict[tuple, int] = {}
    for row in rows:
        prov, model, dim = row[6], row[7], row[8]
        if prov and model and dim:
            chave = (prov, model, int(dim))
            contagem_meta[chave] = contagem_meta.get(chave, 0) + 1
    meta_majoritaria = max(contagem_meta.items(), key=lambda kv: kv[1])[0] if contagem_meta else None

    ids, fontes, meeting_ids, titulos, trechos, vecs = [], [], [], [], [], []
    for row in rows:
        emb = row[5]
        prov, model, dim = row[6], row[7], row[8]
        if isinstance(emb, str):
            try:
                emb = json.loads(emb)
            except Exception:
                continue
        if not emb:
            continue
        if meta_majoritaria is not None:
            linha_meta = (prov, model, int(dim)) if (prov and model and dim) else None
            if linha_meta != meta_majoritaria:
                continue
        ids.append(row[0])
        fontes.append(row[1])
        meeting_ids.append(row[2])
        titulos.append(row[3] or "")
        trechos.append((row[4] or "")[:800])
        vecs.append(emb)

    if not vecs:
        _cache_indice = {"vazio": True}
        return _cache_indice

    _cache_indice = {
        "vazio": False,
        "ids": ids,
        "fontes": fontes,
        "meeting_ids": meeting_ids,
        "titulos": titulos,
        "trechos": trechos,
        "matrix": np.array(vecs, dtype=np.float32),
        "embedding_meta": (
            {"provider": meta_majoritaria[0], "model": meta_majoritaria[1], "dim": meta_majoritaria[2]}
            if meta_majoritaria else None
        ),
    }
    return _cache_indice


def _buscar_no_indice(query: str, fontes: Optional[list], top_k: int) -> list:
    from services.embeddings import cosine_top_k, is_dimension_compatible

    cache = _carregar_cache_indice()
    if cache.get("vazio"):
        return []

    try:
        provider = get_embedding_provider()
    except Exception:
        return []

    resultado = provider.embed(query[:2000])
    if resultado is None:
        return []

    meta = cache.get("embedding_meta")
    if meta and not is_dimension_compatible(resultado.dimension, meta):
        logger.warning(
            "[SemanticSearch] Dimensão da query (%s) incompatível com o índice (%s) — busca ignorada.",
            resultado.dimension, meta.get("dim"),
        )
        return []

    n = min(top_k * 3, len(cache["ids"]))
    top = cosine_top_k(resultado.vector, cache["matrix"], n)

    saida = []
    for idx, score in top:
        fonte = cache["fontes"][idx]
        if fontes and fonte not in fontes:
            continue
        saida.append({
            "fonte": fonte,
            "meeting_id": cache["meeting_ids"][idx],
            "titulo": cache["titulos"][idx],
            "trecho": cache["trechos"][idx],
            "similarity": round(float(score), 4),
        })
        if len(saida) >= top_k:
            break
    return saida


def buscar_semantico_unificado(query: str, fontes: Optional[list] = None, top_k: int = 5) -> list:
    """
    Busca semântica sobre relatórios/transcrições (semantic_index) e,
    opcionalmente, memórias comerciais (sales_memories) — resultado
    misturado e reordenado por similaridade. Só para consulta humana
    (Workspace Comercial), nunca injetada de volta no prompt em tempo real.

    Args:
        query: texto da busca
        fontes: subconjunto de {"relatorios", "transcricoes", "memorias"};
                None = todas
        top_k: máximo de resultados retornados
    """
    fontes_norm = set(fontes) if fontes else {"relatorios", "transcricoes", "memorias"}
    resultados = []

    indice_fontes = []
    if "relatorios" in fontes_norm:
        indice_fontes.append("relatorio")
    if "transcricoes" in fontes_norm:
        indice_fontes.append("transcricao")
    if indice_fontes:
        resultados.extend(_buscar_no_indice(query, indice_fontes, top_k))

    if "memorias" in fontes_norm:
        try:
            from agent.sales_memory import buscar_memorias_semantico
            for mem in buscar_memorias_semantico(query, top_k=top_k):
                resultados.append({
                    "fonte": "memoria",
                    "meeting_id": mem.get("source_meeting_id"),
                    "titulo": mem.get("title"),
                    "trecho": (mem.get("content") or "")[:800],
                    "similarity": mem.get("similarity"),
                    "id": mem.get("id"),
                })
        except Exception as e:
            logger.warning("[SemanticSearch] Erro ao buscar memórias: %s", e)

    resultados.sort(key=lambda r: r.get("similarity") or 0.0, reverse=True)
    return resultados[:top_k]
