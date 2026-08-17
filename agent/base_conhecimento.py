"""
Módulo de Base de Conhecimento — RAG (Retrieval-Augmented Generation)

Busca as transcrições históricas mais similares à conversa atual para
contextualizar e enriquecer as análises em tempo real.

Todos os embeddings são carregados em memória no primeiro acesso (cache).
Com 49 documentos, o cache ocupa ~300 KB de RAM — desprezível.

A geração de embeddings passa pelo EmbeddingProvider (services/embeddings) —
este módulo não sabe se o provedor ativo é Ollama ou OpenAI.
"""
import json
import logging
import os
from typing import Optional

import numpy as np
import pymysql

from services.embeddings import cosine_top_k, get_embedding_provider, is_dimension_compatible

logger = logging.getLogger("saleia.base_conhecimento")

# Cache global — carregado uma vez, compartilhado entre workers
_cache: Optional[dict] = None


def _get_db_conn():
    required = ("DB_HOST", "DB_USER", "DB_PASS", "DB_NAME")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Variaveis de banco ausentes: {', '.join(missing)}")

    return pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASS"],
        database=os.environ["DB_NAME"],
        charset="utf8mb4",
        connect_timeout=10,
    )


def _fetch_rows_com_metadados(conn):
    """Busca linhas com as colunas de metadados de embedding.

    Faz fallback para uma consulta sem essas colunas se a migração
    (migrar_colunas_embedding_metadata_base_conhecimento) ainda não tiver
    rodado nesta base — nesse caso todas as linhas são tratadas como legado
    (metadados None), sem quebrar o carregamento do cache.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, titulo, tipo, texto, embedding, "
                "embedding_provider, embedding_model, embedding_dim "
                "FROM base_conhecimento WHERE embedding IS NOT NULL"
            )
            return cur.fetchall(), True
    except Exception as e:
        logger.debug("[RAG] Colunas de metadados de embedding ausentes, usando fallback legado: %s", e)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, titulo, tipo, texto, embedding "
                "FROM base_conhecimento WHERE embedding IS NOT NULL"
            )
            return cur.fetchall(), False


def _carregar_cache() -> dict:
    """Carrega todos os embeddings da DB em memória e retorna o cache."""
    global _cache
    if _cache is not None:
        return _cache

    try:
        conn = _get_db_conn()
        rows, tem_metadados = _fetch_rows_com_metadados(conn)
        conn.close()
    except Exception as e:
        logger.error("[RAG] Erro ao conectar ao banco: %s", e)
        _cache = {"vazio": True}
        return _cache

    if not rows:
        logger.info("[RAG] Base de conhecimento vazia.")
        _cache = {"vazio": True}
        return _cache

    # Primeira passagem: determina a metadados majoritária (provider, model, dim)
    # entre as linhas que a possuem — vetores de outras combinações são excluídos
    # do cache em vez de serem misturados na mesma matriz numpy.
    contagem_meta: dict[tuple, int] = {}
    for row in rows:
        if tem_metadados:
            _, _, _, _, _, prov, model, dim = row
            if prov and model and dim:
                chave = (prov, model, int(dim))
                contagem_meta[chave] = contagem_meta.get(chave, 0) + 1

    meta_majoritaria = max(contagem_meta.items(), key=lambda kv: kv[1])[0] if contagem_meta else None

    ids, titulos, tipos, textos, vecs = [], [], [], [], []
    excluidas = 0
    for row in rows:
        if tem_metadados:
            rid, titulo, tipo, texto, emb, prov, model, dim = row
        else:
            rid, titulo, tipo, texto, emb = row
            prov, model, dim = None, None, None

        if isinstance(emb, str):
            try:
                emb = json.loads(emb)
            except Exception:
                excluidas += 1
                continue

        if meta_majoritaria is not None:
            linha_meta = (prov, model, int(dim)) if (prov and model and dim) else None
            if linha_meta != meta_majoritaria:
                # Linha legada (sem metadados) ou de outro modelo/dimensão —
                # não entra na matriz para não quebrar a comparação de cosseno.
                excluidas += 1
                continue

        ids.append(rid)
        titulos.append(titulo or "")
        tipos.append(tipo or "outro")
        # Guarda apenas os primeiros 1000 chars para injeção no prompt
        textos.append((texto or "")[:1000])
        vecs.append(emb)

    if excluidas:
        logger.warning(
            "[RAG] %d linha(s) com embedding de provedor/dimensão divergente "
            "(ou legado) ignorada(s) no cache — pendente(s) de reindexação.",
            excluidas,
        )

    if not vecs:
        logger.info("[RAG] Nenhum embedding compatível para carregar no cache.")
        _cache = {"vazio": True}
        return _cache

    matrix = np.array(vecs, dtype=np.float32)

    embedding_meta = None
    if meta_majoritaria is not None:
        embedding_meta = {
            "provider": meta_majoritaria[0],
            "model": meta_majoritaria[1],
            "dim": meta_majoritaria[2],
        }

    _cache = {
        "vazio": False,
        "ids": ids,
        "titulos": titulos,
        "tipos": tipos,
        "textos": textos,
        "matrix": matrix,
        "embedding_meta": embedding_meta,
    }
    logger.info("[RAG] Cache carregado: %d transcrições.", len(ids))
    return _cache


async def buscar_contexto_similar(texto: str, top_k: int = 3) -> Optional[str]:
    """
    Gera embedding para `texto`, busca as top_k transcrições mais similares
    e retorna um bloco formatado para injetar no prompt da IA.

    Retorna None se a base estiver vazia, o serviço de embedding falhar ou
    a dimensão do embedding da consulta for incompatível com o cache.
    """
    cache = _carregar_cache()
    if cache.get("vazio"):
        return None

    try:
        provider = get_embedding_provider()
        resultado = await provider.embed_async(texto[:4000])
    except Exception as e:
        logger.error("[RAG] Erro ao gerar embedding: %s", e)
        return None

    if resultado is None:
        logger.warning("[RAG] Provedor de embedding não retornou vetor para a consulta.")
        return None

    if not is_dimension_compatible(resultado.dimension, cache.get("embedding_meta")):
        logger.warning(
            "[RAG] Dimensão do embedding da consulta (%s, %s) incompatível com o cache "
            "(%s) — pulei a comparação. Base pode precisar de reindexação.",
            resultado.provider, resultado.dimension, cache.get("embedding_meta"),
        )
        return None

    vec = np.array(resultado.vector, dtype=np.float32)
    resultados = cosine_top_k(vec, cache["matrix"], top_k)

    blocos = []
    for idx, sim in resultados:
        if sim < 0.25:  # Similaridade mínima — abaixo disso não agrega valor
            continue
        tipo = cache["tipos"][idx]
        titulo = cache["titulos"][idx][:80]
        trecho = cache["textos"][idx]

        tipo_legivel = {
            "diagnostico": "Diagnóstico",
            "consultoria": "Consultoria gratuita",
            "programa_aceleracao": "Programa de Aceleração",
            "reuniao_1_1": "Reunião 1:1 (coaching)",
        }.get(tipo, tipo)

        blocos.append(
            f"• [{tipo_legivel}] {titulo}\n"
            f"  Conteúdo: {trecho}"
        )

    if not blocos:
        return None

    return (
        "REFERÊNCIAS DE CONVERSAS ANTERIORES SIMILARES "
        "(use como parâmetro para calibrar sua análise):\n\n"
        + "\n\n".join(blocos)
    )


def invalidar_cache():
    """Força recarregamento do cache na próxima consulta (após nova importação)."""
    global _cache
    _cache = None
    logger.info("[RAG] Cache invalidado.")
