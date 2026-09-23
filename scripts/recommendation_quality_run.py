"""
scripts/recommendation_quality_run.py — Fase 25 ("o que falta pra
ligar") — recalcula o estado (USED/PARTIALLY_USED/IGNORED/UNKNOWN,
Tarefa 10.2) de cada `RecommendationEvent` real com `seller_action` já
registrado, via embeddings locais (Ollama — **mesma decisão de custo
zero já confirmada na Tarefa 10.2**, `agent/
recommendation_usage_rules.py::detectar_uso_recomendacao`), e agrega
em `recommendation_quality` real (Fase 25,
`agent/recommendation_effectiveness_rules.py::resumir_uso_geral`) +
efetividade por estratégia (Tarefa 10.3,
`calcular_efetividade_por_estrategia`).

`taxa_avanco`/`taxa_desfecho_positivo` (Tarefa 10.3) continuam `None`
nesta rodada — `stage_advanced`/`opportunity_result` não são
capturados em nenhum lugar da produção ainda (gap documentado à
parte, fora do escopo deste script). O que este script fecha é só a
classificação real de USO (state), que antes só era logada, nunca
agregada.

**Custo real de IA: zero** — usa só embeddings locais (Ollama), mesmo
provedor já usado pelo RAG/Sales Memory, nunca uma API paga.
`--dry-run` (padrão) só mostra quantos eventos existem, sem classificar
nada.

Uso:
    python -m scripts.recommendation_quality_run               # dry-run
    python -m scripts.recommendation_quality_run --real         # roda de verdade (grátis, mas real)
    python -m scripts.recommendation_quality_run --real --out relatorio.json
"""
from __future__ import annotations

import argparse
import asyncio
import json

from dotenv import load_dotenv

load_dotenv()


def _dry_run() -> None:
    from api.database import listar_recommendation_events_respondidos

    eventos = listar_recommendation_events_respondidos()
    print(f"[DRY-RUN] {len(eventos)} RecommendationEvent(s) com seller_action registrado")
    print("[DRY-RUN] custo real de IA: $0.00 (embeddings locais Ollama, mesma decisão da Tarefa 10.2)")
    print("[DRY-RUN] Nenhuma classificação foi feita.")


async def _real_run(out_path: str | None) -> None:
    from agent.recommendation_effectiveness_rules import (
        calcular_efetividade_por_estrategia,
        resumir_uso_geral,
    )
    from agent.recommendation_usage_rules import detectar_uso_recomendacao
    from api.database import listar_recommendation_events_respondidos

    eventos_brutos = listar_recommendation_events_respondidos()
    print(f"Classificando {len(eventos_brutos)} RecommendationEvent(s) via embeddings locais (grátis)...")

    eventos_classificados: list[dict] = []
    erros: list[str] = []

    for ev in eventos_brutos:
        try:
            classificacao = await detectar_uso_recomendacao(ev["recommendation"], ev["seller_action"])
        except Exception as e:
            erros.append(f"evento {ev['id']}: {type(e).__name__}: {e}")
            classificacao = {"state": "UNKNOWN", "similarity": None}

        eventos_classificados.append({
            "id": ev["id"],
            "strategy": ev["strategy"],
            "state": classificacao["state"],
            "similarity": classificacao.get("similarity"),
            "stage_advanced": None,
            "opportunity_result": None,
        })

    resumo_geral = resumir_uso_geral([e["state"] for e in eventos_classificados])
    efetividade_por_estrategia = calcular_efetividade_por_estrategia(eventos_classificados)

    saida_console = {
        "recommendation_quality": resumo_geral,
        "efetividade_por_estrategia": efetividade_por_estrategia,
    }
    print(json.dumps(saida_console, ensure_ascii=False, indent=2))
    if erros:
        print(f"\n{len(erros)} erro(s) durante a execução (não derrubaram o script):")
        for erro in erros:
            print(f"  - {erro}")

    if out_path:
        relatorio = {**saida_console, "eventos_classificados": eventos_classificados, "erros": erros}
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(relatorio, f, ensure_ascii=False, indent=2)
        print(f"\nRelatório salvo em {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", action="store_true", help="Roda de verdade (embeddings locais, grátis, mas real). Sem esta flag, só dry-run.")
    parser.add_argument("--out", default=None, help="Caminho pra salvar o relatório JSON (opcional).")
    args = parser.parse_args()

    if not args.real:
        _dry_run()
        return

    asyncio.run(_real_run(args.out))


if __name__ == "__main__":
    main()
