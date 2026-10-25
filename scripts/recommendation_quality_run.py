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

`taxa_avanco`/`taxa_desfecho_positivo` (Tarefa 10.3) vêm de
`stage_advanced`/`opportunity_result`, capturados desde a Tarefa B2
(`agent/recommendation_outcome_rules.py::anexar_resultados`: reunião →
oportunidade vinculada → histórico de estágio + status final). Continuam
`None` para recomendação de reunião sem oportunidade vinculada, sem
reunião seguinte ou de oportunidade ainda aberta — nunca `False` por
omissão.

**Custo real de IA: zero** — usa só embeddings locais (Ollama), mesmo
provedor já usado pelo RAG/Sales Memory, nunca uma API paga.
`--dry-run` (padrão) só mostra quantos eventos existem, sem classificar
nada.

`--real` também grava `data/efetividade_estrategias.json`, o retrato que
o motor do Piloto/Shadow lê em `historical_patterns` (C5).

Uso:
    python -m scripts.recommendation_quality_run               # dry-run
    python -m scripts.recommendation_quality_run --real         # roda de verdade (grátis, mas real)
    python -m scripts.recommendation_quality_run --real --out relatorio.json
    python -m scripts.recommendation_quality_run --real --registrar-readiness  # substitui o número da C4 no painel
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


async def _real_run(out_path: str | None, registrar_readiness: bool = False) -> None:
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
            "meeting_id": ev["meeting_id"],
            "opportunity_id": ev.get("opportunity_id"),
            "shown_at": ev.get("shown_at"),
            "strategy": ev["strategy"],
            "state": classificacao["state"],
            "similarity": classificacao.get("similarity"),
        })

    # Tarefa B2: stage_advanced/opportunity_result reais (determinístico).
    try:
        from agent.recommendation_outcome_rules import anexar_resultados
        eventos_classificados = anexar_resultados(eventos_classificados)
    except Exception as e:
        erros.append(f"resultados (B2): {type(e).__name__}: {e}")
        eventos_classificados = [
            {**evento, "stage_advanced": None, "opportunity_result": None} for evento in eventos_classificados
        ]
    com_resultado = sum(
        1 for e in eventos_classificados
        if e.get("stage_advanced") is not None or e.get("opportunity_result") is not None
    )
    print(f"{com_resultado} evento(s) com stage_advanced/opportunity_result conhecido (B2).")

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

    # C5: retrato da efetividade por estratégia lido pelo motor
    # (agent/historical_pattern_rules.py).
    try:
        from agent.historical_pattern_rules import salvar_snapshot_efetividade
        caminho = salvar_snapshot_efetividade(efetividade_por_estrategia, len(eventos_classificados))
        print(f"Retrato da efetividade por estratégia salvo em {caminho} (C5).")
    except Exception as e:
        print(f"Aviso: não foi possível salvar o retrato da efetividade: {type(e).__name__}: {e}")

    # Tarefa D1: desde a C4 (23/10/2026) o recommendation_quality do painel
    # é a métrica da C4 (IA juíza sobre as reuniões do Paulo); a taxa de uso
    # por embeddings daqui não é confiável (C8) e só substitui com a flag.
    if not registrar_readiness:
        print("recommendation_quality NÃO registrado no /admin/readiness (use --registrar-readiness).")
    else:
        try:
            from api.database import registrar_readiness_medicao
            registrar_readiness_medicao(
                "recommendation_quality", resumo_geral["taxa_uso_real"], origem="real",
                fonte="scripts/recommendation_quality_run.py", amostra=resumo_geral["total"],
                detalhe={"por_estado": resumo_geral["por_estado"]},
            )
            print("recommendation_quality registrado no painel de prontidão (/admin/readiness).")
        except Exception as e:
            print(f"Aviso: não foi possível registrar no painel de prontidão: {type(e).__name__}: {e}")

    if out_path:
        relatorio = {**saida_console, "eventos_classificados": eventos_classificados, "erros": erros}
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(relatorio, f, ensure_ascii=False, indent=2)
        print(f"\nRelatório salvo em {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", action="store_true", help="Roda de verdade (embeddings locais, grátis, mas real). Sem esta flag, só dry-run.")
    parser.add_argument("--out", default=None, help="Caminho pra salvar o relatório JSON (opcional).")
    parser.add_argument("--registrar-readiness", action="store_true",
                        help="Substitui o recommendation_quality do /admin/readiness (hoje é o da C4) pela taxa de uso daqui.")
    args = parser.parse_args()

    if not args.real:
        _dry_run()
        return

    asyncio.run(_real_run(args.out, args.registrar_readiness))


if __name__ == "__main__":
    main()
