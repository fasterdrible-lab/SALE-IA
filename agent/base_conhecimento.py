"""
Módulo de Base de Conhecimento — RAG (Retrieval-Augmented Generation)

Busca as transcrições históricas mais similares à conversa atual para
contextualizar e enriquecer as análises em tempo real.

Todos os embeddings são carregados em memória no primeiro acesso (cache).
Com 49 documentos, o cache ocupa ~300 KB de RAM — desprezível.
"""
import json
import os
from typing import Optional

import numpy as np
import pymysql
from openai import AsyncOpenAI

# Cache global — carregado uma vez, compartilhado entre workers
_cache: Optional[dict] = None

# Singleton do cliente OpenAI — recriado apenas se a chave de API mudar
_openai_client: Optional[AsyncOpenAI] = None
_openai_client_key: str = ""


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client, _openai_client_key
    current_key = os.environ.get("OPENAI_API_KEY", "")
    if _openai_client is None or current_key != _openai_client_key:
        _openai_client = AsyncOpenAI(api_key=current_key)
        _openai_client_key = current_key
    return _openai_client


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


def _carregar_cache() -> dict:
    """Carrega todos os embeddings da DB em memória e retorna o cache."""
    global _cache
    if _cache is not None:
        return _cache

    try:
        conn = _get_db_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, titulo, tipo, texto, embedding "
                "FROM base_conhecimento WHERE embedding IS NOT NULL"
            )
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        print(f"[RAG] Erro ao conectar ao banco: {e}")
        _cache = {"vazio": True}
        return _cache

    if not rows:
        print("[RAG] Base de conhecimento vazia.")
        _cache = {"vazio": True}
        return _cache

    ids, titulos, tipos, textos, vecs = [], [], [], [], []
    for row in rows:
        ids.append(row[0])
        titulos.append(row[1] or "")
        tipos.append(row[2] or "outro")
        # Guarda apenas os primeiros 1000 chars para injeção no prompt
        textos.append((row[3] or "")[:1000])
        emb = row[4]
        if isinstance(emb, str):
            emb = json.loads(emb)
        vecs.append(emb)

    matrix = np.array(vecs, dtype=np.float32)

    _cache = {
        "vazio": False,
        "ids": ids,
        "titulos": titulos,
        "tipos": tipos,
        "textos": textos,
        "matrix": matrix,
    }
    print(f"[RAG] Cache carregado: {len(ids)} transcrições.")
    return _cache


def _cosine_top_k(vec: np.ndarray, matrix: np.ndarray, k: int) -> list[int]:
    """Retorna os índices dos k vetores mais similares por cosseno."""
    vec_norm = vec / (np.linalg.norm(vec) + 1e-9)
    mat_norm = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
    sims = mat_norm @ vec_norm
    top_indices = np.argsort(sims)[::-1][:k]
    return [(int(idx), float(sims[idx])) for idx in top_indices]


async def buscar_contexto_similar(texto: str, top_k: int = 3) -> Optional[str]:
    """
    Gera embedding para `texto`, busca as top_k transcrições mais similares
    e retorna um bloco formatado para injetar no prompt da IA.

    Retorna None se a base estiver vazia ou o serviço de embedding falhar.
    """
    cache = _carregar_cache()
    if cache.get("vazio"):
        return None

    try:
        client = _get_openai_client()
        resp = await client.embeddings.create(
            model="text-embedding-3-small",
            input=texto[:4000],
        )
        vec = np.array(resp.data[0].embedding, dtype=np.float32)
    except Exception as e:
        print(f"[RAG] Erro ao gerar embedding: {e}")
        return None

    resultados = _cosine_top_k(vec, cache["matrix"], top_k)

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
    print("[RAG] Cache invalidado.")
