"""
scripts/reindex_embeddings.py — Reindexação de embeddings

Regera embeddings de `base_conhecimento` e/ou `sales_memories` sob o
provedor atualmente configurado (ou um forçado via --provider), sem
apagar embeddings antigos antes de validar os novos.

Uso:
    python -m scripts.reindex_embeddings [--table base_conhecimento|sales_memories|all]
                                          [--dry-run] [--batch-size 32]
                                          [--provider ollama|openai] [--limit N]
                                          [--report-file relatorio.json]

Idempotente: linhas cujo (embedding_provider, embedding_model) já bate
com o alvo são puladas — seguro para re-executar após uma interrupção,
sem arquivo de progresso separado (o próprio estado da linha no banco é
o checkpoint).

Nunca deleta antes de validar: o vetor novo só é gravado (UPDATE único
de embedding + metadados) depois de confirmado válido — se o processo
cair no meio, toda linha ainda não processada mantém seu embedding
antigo intacto.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class TabelaResultado:
    tabela: str
    total: int = 0
    ja_atual: int = 0
    sucesso: int = 0
    falha: int = 0
    erros: list = field(default_factory=list)  # [{"id":, "erro":}]
    dry_run: bool = False

    def to_dict(self) -> dict:
        return {
            "tabela": self.tabela,
            "total": self.total,
            "ja_atual": self.ja_atual,
            "sucesso": self.sucesso,
            "falha": self.falha,
            "erros": self.erros,
            "dry_run": self.dry_run,
        }


def _vetor_valido(vec: list) -> bool:
    if not vec:
        return False
    if all(v == 0 for v in vec):
        return False
    if any(isinstance(v, float) and math.isnan(v) for v in vec):
        return False
    return True


def _reindexar_base_conhecimento(provider, batch_size: int, dry_run: bool, limit: int | None) -> TabelaResultado:
    from agent.sessao_manager import _get_conn, migrar_colunas_embedding_metadata_base_conhecimento
    from agent.base_conhecimento import invalidar_cache

    migrar_colunas_embedding_metadata_base_conhecimento()

    resultado = TabelaResultado(tabela="base_conhecimento", dry_run=dry_run)

    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM base_conhecimento")
        resultado.total = cur.fetchone()[0]
    conn.close()

    processados = 0
    offset = 0
    while True:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, texto, embedding_provider, embedding_model "
                "FROM base_conhecimento ORDER BY id LIMIT %s OFFSET %s",
                (batch_size, offset),
            )
            rows = cur.fetchall()
        conn.close()

        if not rows:
            break

        pendentes = []
        for rid, texto, emb_prov, emb_model in rows:
            if limit is not None and processados >= limit:
                break
            if emb_prov == provider.provider_name and emb_model == provider.model_name:
                resultado.ja_atual += 1
                processados += 1
                continue
            pendentes.append((rid, texto or ""))
            processados += 1

        if pendentes:
            vetores = provider.embed_batch([t for _, t in pendentes])
            conn = _get_conn()
            with conn.cursor() as cur:
                for (rid, _texto), item in zip(pendentes, vetores):
                    if item is None or not _vetor_valido(item.vector):
                        resultado.falha += 1
                        resultado.erros.append({"id": rid, "erro": "embedding ausente ou inválido"})
                        continue
                    if dry_run:
                        resultado.sucesso += 1
                        print(f"[DRY-RUN] base_conhecimento id={rid} seria atualizado "
                              f"(dim={item.dimension}, provider={item.provider})")
                        continue
                    cur.execute(
                        "UPDATE base_conhecimento SET embedding=%s, embedding_provider=%s, "
                        "embedding_model=%s, embedding_dim=%s WHERE id=%s",
                        (json.dumps(item.vector), item.provider, item.model, item.dimension, rid),
                    )
                    resultado.sucesso += 1
            conn.commit()
            conn.close()

        offset += batch_size
        if limit is not None and processados >= limit:
            break

    if resultado.sucesso and not dry_run:
        invalidar_cache()

    return resultado


def _reindexar_sales_memories(provider, batch_size: int, dry_run: bool, limit: int | None) -> TabelaResultado:
    from agent.sales_memory import (
        _get_conn,
        migrar_colunas_embedding_metadata_memories,
        invalidar_cache_memorias,
    )

    migrar_colunas_embedding_metadata_memories()

    resultado = TabelaResultado(tabela="sales_memories", dry_run=dry_run)

    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM sales_memories")
        resultado.total = cur.fetchone()[0]
    conn.close()

    processados = 0
    offset = 0
    while True:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, content, embedding_provider, embedding_model "
                "FROM sales_memories ORDER BY id LIMIT %s OFFSET %s",
                (batch_size, offset),
            )
            rows = cur.fetchall()
        conn.close()

        if not rows:
            break

        pendentes = []
        for mem_id, content, emb_prov, emb_model in rows:
            if limit is not None and processados >= limit:
                break
            if emb_prov == provider.provider_name and emb_model == provider.model_name:
                resultado.ja_atual += 1
                processados += 1
                continue
            pendentes.append((mem_id, (content or "")[:6000]))
            processados += 1

        if pendentes:
            vetores = provider.embed_batch([c for _, c in pendentes])
            conn = _get_conn()
            with conn.cursor() as cur:
                for (mem_id, _content), item in zip(pendentes, vetores):
                    if item is None or not _vetor_valido(item.vector):
                        resultado.falha += 1
                        resultado.erros.append({"id": mem_id, "erro": "embedding ausente ou inválido"})
                        continue
                    if dry_run:
                        resultado.sucesso += 1
                        print(f"[DRY-RUN] sales_memories id={mem_id} seria atualizado "
                              f"(dim={item.dimension}, provider={item.provider})")
                        continue
                    cur.execute(
                        "UPDATE sales_memories SET embedding=%s, embedding_provider=%s, "
                        "embedding_model=%s, embedding_dim=%s WHERE id=%s",
                        (json.dumps(item.vector), item.provider, item.model, item.dimension, mem_id),
                    )
                    resultado.sucesso += 1
            conn.commit()
            conn.close()

        offset += batch_size
        if limit is not None and processados >= limit:
            break

    if resultado.sucesso and not dry_run:
        invalidar_cache_memorias()

    return resultado


def main() -> int:
    parser = argparse.ArgumentParser(description="Reindexa embeddings do SALEIA sob o provedor configurado.")
    parser.add_argument("--table", choices=["base_conhecimento", "sales_memories", "all"], default="all")
    parser.add_argument("--dry-run", action="store_true", help="Executa os embeds mas não grava nada no banco.")
    parser.add_argument("--batch-size", type=int, default=int(os.environ.get("EMBEDDING_BATCH_SIZE", "32")))
    parser.add_argument("--provider", choices=["ollama", "openai"], default=None,
                         help="Força um provedor específico para esta execução (sobrepõe EMBEDDING_PROVIDER).")
    parser.add_argument("--limit", type=int, default=None, help="Processa no máximo N linhas por tabela.")
    parser.add_argument("--report-file", default=None, help="Caminho para salvar o relatório final em JSON.")
    args = parser.parse_args()

    if args.provider:
        os.environ["EMBEDDING_PROVIDER"] = args.provider

    from services.embeddings import get_embedding_provider, EmbeddingProviderError

    try:
        provider = get_embedding_provider(refresh=True)
    except EmbeddingProviderError as e:
        print(f"ERRO: {e}")
        return 2

    print(f"Provider alvo: {provider.provider_name} (modelo={provider.model_name})")
    if args.dry_run:
        print("Modo --dry-run: nenhuma alteração será gravada no banco.")

    inicio = time.time()
    resultados: list[TabelaResultado] = []

    if args.table in ("base_conhecimento", "all"):
        resultados.append(_reindexar_base_conhecimento(provider, args.batch_size, args.dry_run, args.limit))
    if args.table in ("sales_memories", "all"):
        resultados.append(_reindexar_sales_memories(provider, args.batch_size, args.dry_run, args.limit))

    elapsed = time.time() - inicio

    print("\n=== RELATÓRIO DE REINDEXAÇÃO ===")
    houve_falha = False
    for r in resultados:
        print(f"\n[{r.tabela}] total={r.total} ja_atual={r.ja_atual} sucesso={r.sucesso} falha={r.falha}")
        if r.erros:
            houve_falha = True
            for erro in r.erros[:10]:
                print(f"  - id={erro['id']}: {erro['erro']}")
            if len(r.erros) > 10:
                print(f"  ... e mais {len(r.erros) - 10} erro(s)")
    print(f"\nTempo total: {elapsed:.1f}s")

    if not args.dry_run:
        print(
            "\nAVISO: este script não invalida o cache em memória de processos "
            "saleia.service já em execução. Reinicie o serviço "
            "(systemctl restart saleia) para os workers usarem os novos embeddings."
        )

    if args.report_file:
        payload = {
            "provider": provider.provider_name,
            "model": provider.model_name,
            "dry_run": args.dry_run,
            "elapsed_seconds": round(elapsed, 1),
            "tabelas": [r.to_dict() for r in resultados],
        }
        with open(args.report_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"Relatório salvo em: {args.report_file}")

    return 1 if houve_falha else 0


if __name__ == "__main__":
    sys.exit(main())
