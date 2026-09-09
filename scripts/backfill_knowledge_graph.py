"""
scripts/backfill_knowledge_graph.py — Backfill do Knowledge Graph

Popula agent/knowledge_graph.py::graph_edges para dados históricos que
existiam antes da Fase 7.2 (client_meetings, sales_memories.
source_meeting_id, playbooks.source_meeting_id, skills.source_playbook_id).
Depois deste backfill, o hook em cada ponto de criação (client_intelligence,
knowledge_extractor, playbook_generator, skill_resolver) mantém o grafo
atualizado sozinho para dados novos.

Idempotente: registrar_aresta() usa INSERT IGNORE numa UNIQUE KEY — rodar
este script mais de uma vez nunca duplica arestas.

Uso:
    python -m scripts.backfill_knowledge_graph [--dry-run]
"""
from __future__ import annotations

import argparse

from dotenv import load_dotenv

load_dotenv()


def _contar_e_talvez_gravar(descricao: str, linhas: list, montar_aresta, dry_run: bool) -> int:
    from agent.knowledge_graph import registrar_aresta

    gravadas = 0
    for linha in linhas:
        aresta = montar_aresta(linha)
        if not aresta:
            continue
        if dry_run:
            print(f"[DRY-RUN] {descricao}: {aresta}")
            gravadas += 1
            continue
        if registrar_aresta(*aresta):
            gravadas += 1
    return gravadas


def backfill_cliente_reuniao(dry_run: bool) -> int:
    from agent.client_intelligence import _get_conn
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT client_id, meeting_id FROM client_meetings")
        linhas = cur.fetchall()
    conn.close()
    return _contar_e_talvez_gravar(
        "cliente->reuniao", linhas,
        lambda r: ("cliente", r["client_id"], "reuniao", r["meeting_id"], "teve_reuniao"),
        dry_run,
    )


def backfill_reuniao_memoria(dry_run: bool) -> int:
    from agent.sales_memory import _get_conn
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT id, source_meeting_id FROM sales_memories WHERE source_meeting_id IS NOT NULL")
        linhas = cur.fetchall()
    conn.close()
    return _contar_e_talvez_gravar(
        "reuniao->memoria", linhas,
        lambda r: ("reuniao", r[1], "memoria", r[0], "gerou_memoria"),
        dry_run,
    )


def backfill_reuniao_playbook(dry_run: bool) -> int:
    from agent.playbook_generator import _get_conn
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT id, source_meeting_id FROM playbooks WHERE source_meeting_id IS NOT NULL")
        linhas = cur.fetchall()
    conn.close()
    return _contar_e_talvez_gravar(
        "reuniao->playbook", linhas,
        lambda r: ("reuniao", r[1], "playbook", r[0], "gerou_playbook"),
        dry_run,
    )


def backfill_playbook_skill(dry_run: bool) -> int:
    from agent.skill_resolver import _get_conn
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT id, source_playbook_id FROM skills WHERE source_playbook_id IS NOT NULL")
        linhas = cur.fetchall()
    conn.close()
    return _contar_e_talvez_gravar(
        "playbook->skill", linhas,
        lambda r: ("playbook", r["source_playbook_id"], "skill", r["id"], "gerou_skill"),
        dry_run,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill do Knowledge Graph (Sales Brain Fase 7.2)")
    parser.add_argument("--dry-run", action="store_true", help="Só lista as arestas, sem gravar.")
    args = parser.parse_args()

    if not args.dry_run:
        from agent.knowledge_graph import criar_tabela_graph_edges
        criar_tabela_graph_edges()

    total = 0
    total += backfill_cliente_reuniao(args.dry_run)
    total += backfill_reuniao_memoria(args.dry_run)
    total += backfill_reuniao_playbook(args.dry_run)
    total += backfill_playbook_skill(args.dry_run)

    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}Total de arestas {'identificadas' if args.dry_run else 'gravadas'}: {total}")


if __name__ == "__main__":
    main()
