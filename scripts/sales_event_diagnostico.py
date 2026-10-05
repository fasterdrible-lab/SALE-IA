"""Tarefa A7b de docs/tasks-prompt-mestre-v2-restante.md — diagnóstico do
extrator de SalesEvent cenário a cenário.

Roda só `extrair_sales_events_async` nos 40 cenários do Golden Sales
Dataset (40 chamadas de IA, contra ~234 da rodada completa) e lista, por
cenário, o previsto (tipo, confiança, citação) contra `expected_events`,
com a precisão/recall por tipo — o mesmo cálculo do runner
(`contar_precisao_eventos`).

Uso (custo real de IA):
    python -m scripts.sales_event_diagnostico --real --out diag.json
"""

import argparse
import asyncio
import json
import sys
from collections import Counter


async def diagnosticar(cenarios: list) -> dict:
    from agent.quality_monitoring_golden_runner import HISTORICO_PADRAO
    from agent.sales_event_extractor import contar_precisao_eventos, extrair_sales_events_async

    vp = fp = fn = 0
    fp_por_tipo, fn_por_tipo = Counter(), Counter()
    detalhes, erros = [], []
    for c in cenarios:
        esperados = c.get("expected_events") or []
        try:
            previstos = await extrair_sales_events_async(c["input"], HISTORICO_PADRAO)
        except Exception as e:
            erros.append(f"{c.get('id')}: {type(e).__name__}: {e}")
            continue
        v, f, n = contar_precisao_eventos(previstos, esperados)
        vp, fp, fn = vp + v, fp + f, fn + n
        tipos_prev = {e["event_type"] for e in previstos}
        fp_por_tipo.update(tipos_prev - set(esperados))
        fn_por_tipo.update(set(esperados) - tipos_prev)
        detalhes.append({
            "cenario": c.get("id"),
            "input": c["input"].strip(),
            "esperados": esperados,
            "previstos": previstos,
            "falsos_positivos": sorted(tipos_prev - set(esperados)),
            "falsos_negativos": sorted(set(esperados) - tipos_prev),
        })
    return {
        "event_precision": round(vp / (vp + fp), 4) if (vp + fp) else None,
        "event_recall": round(vp / (vp + fn), 4) if (vp + fn) else None,
        "vp": vp, "fp": fp, "fn": fn,
        "fp_por_tipo": dict(fp_por_tipo.most_common()),
        "fn_por_tipo": dict(fn_por_tipo.most_common()),
        "cenarios": detalhes,
        "erros": erros,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", action="store_true", help="Chama IA de verdade (custo real). Sem a flag, não faz nada.")
    parser.add_argument("--out", default=None, help="Caminho do relatório JSON.")
    args = parser.parse_args()
    if not args.real:
        print("Dry-run: passe --real para chamar a IA (40 chamadas).")
        return

    from agent.quality_monitoring_golden_runner import carregar_cenarios_golden_dataset

    relatorio = asyncio.run(diagnosticar(carregar_cenarios_golden_dataset()))
    texto = json.dumps(relatorio, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(texto)
    resumo = {k: relatorio[k] for k in ("event_precision", "event_recall", "vp", "fp", "fn", "fp_por_tipo", "fn_por_tipo", "erros")}
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    sys.exit(1 if relatorio["erros"] else 0)


if __name__ == "__main__":
    main()
