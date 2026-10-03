"""
scripts/quality_monitoring_golden_run.py — Golden Sales Dataset (Fase
20) contra o pipeline real, alimentando 5 das 6 métricas de Quality
Monitoring (Tarefa 19.1) com dado real. Ver
`agent/quality_monitoring_golden_runner.py` para o detalhe completo de
como cada métrica é medida, e por que `recommendation_relevance` fica
de fora (`event_precision` entrou na Tarefa A7).

**Custa dinheiro real de IA** (até 234 chamadas via DeepSeek por
padrão — 40 cenários × 5 chamadas cada, reasoning + spin + behavioral
+ motivation + eventos de venda, + 4 + 30 no classificador de objeção
(Golden Dataset + conjunto da Tarefa D3) — ver docstring do runner).
`--dry-run` (padrão) só
mostra o que rodaria, ZERO custo — sempre confirme o `--dry-run` antes
de rodar com `--real`.

Uso:
    python -m scripts.quality_monitoring_golden_run             # dry-run, sem custo
    python -m scripts.quality_monitoring_golden_run --real      # roda de verdade (custo real)
    python -m scripts.quality_monitoring_golden_run --real --out relatorio.json
"""
from __future__ import annotations

import argparse
import asyncio
import json

from dotenv import load_dotenv

load_dotenv()


def _dry_run() -> None:
    from agent.quality_monitoring_golden_runner import (
        ARQUIVO_OBJECOES,
        carregar_cenarios_golden_dataset,
        carregar_conjunto_classificacao_objecoes,
    )

    cenarios = carregar_cenarios_golden_dataset()
    conjunto_objecoes = carregar_conjunto_classificacao_objecoes()
    com_framework = sum(1 for c in cenarios if c.get("expected_framework"))
    objecoes = sum(1 for c in cenarios if c.get("_arquivo") == ARQUIVO_OBJECOES)

    print(f"[DRY-RUN] {len(cenarios)} cenários carregados de evals/datasets/golden_sales_dataset/")
    print(f"[DRY-RUN] contexto estruturado (spin/behavioral/motivation): {len(cenarios)} cenários × 3 chamadas cada")
    print(f"[DRY-RUN] framework_accuracy: {com_framework} cenários com expected_framework não-nulo")
    print(f"[DRY-RUN] hallucination_rate/evidence_coverage: reaproveitam as mesmas {len(cenarios)} chamadas de raciocinar_async()")
    print(f"[DRY-RUN] objection_precision: {objecoes} cenários em {ARQUIVO_OBJECOES} "
          f"+ {len(conjunto_objecoes)} do conjunto de classificação (Tarefa D3)")
    print(f"[DRY-RUN] event_precision: {len(cenarios)} cenários × 1 chamada do extrator de SalesEvent (Tarefa A7)")
    print("[DRY-RUN] critical_hallucination: determinística sobre a saída do motor, sem chamada extra (Tarefa D2)")
    print(f"[DRY-RUN] total de chamadas reais de IA se rodar com --real: "
          f"até {len(cenarios) * 5 + objecoes + len(conjunto_objecoes)}")
    print("[DRY-RUN] recommendation_relevance NÃO é calculada (gap documentado — exige LLM-judge).")
    print("[DRY-RUN] Nenhuma chamada de IA foi feita.")


async def _real_run(out_path: str | None) -> None:
    from agent.quality_monitoring_golden_runner import executar_golden_dataset_async, montar_relatorio_metricas

    print("Rodando o Golden Sales Dataset contra o pipeline real — isso chama IA de verdade...")
    contagens = await executar_golden_dataset_async()
    relatorio = montar_relatorio_metricas(contagens)

    print(json.dumps(relatorio, ensure_ascii=False, indent=2))
    if contagens["erros"]:
        print(f"\n{len(contagens['erros'])} erro(s) durante a execução (não derrubaram o script):")
        for erro in contagens["erros"]:
            print(f"  - {erro}")

    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(relatorio, f, ensure_ascii=False, indent=2)
        print(f"\nRelatório salvo em {out_path}")

    # Tarefa D1: registra o resultado para GET /admin/readiness.
    try:
        from agent.readiness_rules import medicoes_do_golden_dataset
        from api.database import registrar_readiness_medicao
        for medicao in medicoes_do_golden_dataset(relatorio):
            registrar_readiness_medicao(fonte="scripts/quality_monitoring_golden_run.py", **medicao)
        print("Medições registradas no painel de prontidão (/admin/readiness).")
    except Exception as e:
        print(f"Aviso: não foi possível registrar no painel de prontidão: {type(e).__name__}: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", action="store_true", help="Roda de verdade contra IA real (custo real). Sem esta flag, só dry-run.")
    parser.add_argument("--out", default=None, help="Caminho pra salvar o relatório JSON (opcional).")
    args = parser.parse_args()

    if not args.real:
        _dry_run()
        return

    asyncio.run(_real_run(args.out))


if __name__ == "__main__":
    main()
