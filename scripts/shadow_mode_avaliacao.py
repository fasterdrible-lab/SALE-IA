"""
scripts/shadow_mode_avaliacao.py — Tarefa C3
(docs/tasks-prompt-mestre-v2-restante.md): avalia o Shadow Mode (Fase
23 / Tarefa 6.2) com o dado real de `shadow_mode_comparisons` e
`ai_usage_events`, para decidir se o Piloto (C6) pode começar.

**Só leitura, custo de IA zero.** Nada é gravado no banco. A agregação
fica em `agent/shadow_mode_rules.py::avaliar_shadow_mode()`.

Recusa rodar se o engine caiu no SQLite local (o `api/database.py` faz
esse fallback calado quando o MySQL não responde) — um relatório vazio
pareceria "Shadow Mode sem dado", o que seria falso. Use
`--permitir-sqlite` só para testar o script.

Uso (na VPS, dentro de /opt/saleia com o venv ativo):
    python -m scripts.shadow_mode_avaliacao
    python -m scripts.shadow_mode_avaliacao --out docs/SHADOW_MODE_REPORT.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()


def _fmt_pct(valor) -> str:
    return "—" if valor is None else f"{valor:.1%}"


def _imprimir(relatorio: dict) -> None:
    for origem, dados in relatorio["por_origem"].items():
        print(f"\n== origem: {origem} ==")
        print(f"comparações: {dados['total_comparacoes']} (comparáveis {dados['comparaveis']}, "
              f"atual em fallback {dados['atual_em_fallback']})")
        print(f"reuniões: {dados['reunioes']} | com vendedor: {dados['com_vendedor']}")
        print(f"agreement: {_fmt_pct(dados['agreement_rate'])} | "
              f"sem fallback: {_fmt_pct(dados['agreement_rate_sem_fallback'])}")
        print(f"matriz pergunta: {dados['matriz_pergunta']}")
        print(f"error_rate: {_fmt_pct(dados['error_rate'])} | erros: {dados['erros_por_tipo']}")
        print(f"latência ms: média {dados['latency_ms_media']} | p50 {dados['latency_ms_p50']} | "
              f"p95 {dados['latency_ms_p95']} | p95 sem erro {dados['latency_ms_p95_sem_erro']}")
        print(f"custo do motor (só raciocínio): US$ {dados['cost_usd_total']}")
        print(f"recommended_framework: {dados['recommended_framework']}")
        print("por dia:")
        for linha in dados["por_dia"]:
            print(f"  {linha['chave']}: {linha['total']} comp., agreement {_fmt_pct(linha['agreement_rate'])}, "
                  f"erro {_fmt_pct(linha['error_rate'])}")

    custo = relatorio["custo"]
    print("\n== custo real no período (ai_usage_events) ==")
    print(f"caminho Shadow: US$ {custo['caminho_shadow_usd']} em {custo['caminho_shadow_chamadas']} chamadas")
    for linha in custo["caminho_shadow_por_feature"]:
        print(f"  {linha['feature']}: {linha['eventos']} chamadas, US$ {linha['total_usd']}")
    print(f"tempo real (realtime.*): US$ {custo['tempo_real_usd']} | "
          f"Shadow/tempo real: {_fmt_pct(custo['shadow_sobre_tempo_real'])}")

    prontidao = relatorio["prontidao_piloto"]
    print(f"\n== prontidão do Piloto (C6): {'SIM' if prontidao['pode_iniciar'] else 'NÃO'} ==")
    for c in prontidao["checagens"]:
        print(f"  [{'ok' if c['ok'] else '  '}] {c['criterio']} (valor: {c['valor']})")
    print(f"  {prontidao['observacao']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=None, help="Caminho para salvar o relatório JSON completo (opcional).")
    parser.add_argument("--permitir-sqlite", action="store_true", help="Só para teste: aceita rodar no SQLite local.")
    args = parser.parse_args()

    from agent.shadow_mode_rules import avaliar_shadow_mode
    from api.database import custos_resumo, engine, listar_shadow_mode_comparisons

    if engine.dialect.name != "mysql" and not args.permitir_sqlite:
        raise SystemExit(
            f"Banco atual é '{engine.dialect.name}', não MySQL de produção — relatório seria falso. "
            "Rode na VPS (ou use --permitir-sqlite só para testar)."
        )

    comparacoes = listar_shadow_mode_comparisons(limit=100000)
    datas = [c["criado_em"] for c in comparacoes if c.get("criado_em")]
    desde = datetime.fromisoformat(min(datas)) if datas else None
    custos = custos_resumo(date_from=desde)["por_feature"] if desde else []

    relatorio = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "periodo": {"desde": min(datas) if datas else None, "ate": max(datas) if datas else None},
        **avaliar_shadow_mode(comparacoes, custos),
    }
    _imprimir(relatorio)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(relatorio, f, ensure_ascii=False, indent=2, default=str)
        print(f"\nRelatório salvo em {args.out}")


if __name__ == "__main__":
    main()
