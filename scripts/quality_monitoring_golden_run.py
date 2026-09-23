"""
scripts/quality_monitoring_golden_run.py — Golden Sales Dataset (Fase
20) contra o pipeline real, alimentando 4 das 6 métricas de Quality
Monitoring (Tarefa 19.1) com dado real. Ver
`agent/quality_monitoring_golden_runner.py` para o detalhe completo de
como cada métrica é medida, e por que `event_precision`/
`recommendation_relevance` ficam de fora desta rodada.

**Custa dinheiro real de IA** (até 164 chamadas via DeepSeek por
padrão — 40 cenários × 4 chamadas cada, reasoning + spin + behavioral
+ motivation, + 4 no classificador de objeção — v2, contexto
estruturado real, ver docstring do runner). `--dry-run` (padrão) só
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
    from agent.quality_monitoring_golden_runner import ARQUIVO_OBJECOES, carregar_cenarios_golden_dataset

    cenarios = carregar_cenarios_golden_dataset()
    com_framework = sum(1 for c in cenarios if c.get("expected_framework"))
    objecoes = sum(1 for c in cenarios if c.get("_arquivo") == ARQUIVO_OBJECOES)

    print(f"[DRY-RUN] {len(cenarios)} cenários carregados de evals/datasets/golden_sales_dataset/")
    print(f"[DRY-RUN] contexto estruturado (spin/behavioral/motivation): {len(cenarios)} cenários × 3 chamadas cada")
    print(f"[DRY-RUN] framework_accuracy: {com_framework} cenários com expected_framework não-nulo")
    print(f"[DRY-RUN] hallucination_rate/evidence_coverage: reaproveitam as mesmas {len(cenarios)} chamadas de raciocinar_async()")
    print(f"[DRY-RUN] objection_precision: {objecoes} cenários em {ARQUIVO_OBJECOES}")
    print(f"[DRY-RUN] total de chamadas reais de IA se rodar com --real: até {len(cenarios) * 4 + objecoes}")
    print("[DRY-RUN] event_precision e recommendation_relevance NÃO são calculadas (gaps documentados).")
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
