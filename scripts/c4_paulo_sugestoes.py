"""
scripts/c4_paulo_sugestoes.py — Tarefa C4, passo 2: gera a sugestão da
SALEIA para cada momento real das reuniões do Paulo (objeção do cliente,
conversa cortada antes da resposta do vendedor — ver
`scripts/aprendizado_paulo/c4_montar_momentos.py`).

Duas sugestões por momento, pelo mesmo código da produção:
  - **coach**: `agent/multiagente/coach_agent.py::analisar_coach` — o que a
    sidebar mostra hoje (`next_best_action` / `texto_falavel`), com o mesmo
    contexto de RAG que `orquestrador.py::analisar_fragmento_multi` monta
    (base de conhecimento + Sales Memory + Biblioteca aprovada).
  - **motor**: `agent/sales_reasoning_engine.py::raciocinar_async` — o do
    Piloto, alimentado como no Golden Dataset (transcrição + spin/
    comportamento/motivação dos 3 extratores).

NÃO passa por `analisar_fragmento_multi` de propósito: lá o ciclo grava
RecommendationEvent e agenda Shadow Mode, o que poria dado falso no banco
de produção. As chamadas de IA ficam marcadas com `meeting_id=c4_paulo:<id>`
(custo separável); o motor grava o AuditTrailEntry normal dele.

**Custa IA de verdade** (~5 chamadas por momento). `--dry-run` (padrão)
só conta. Rodar de novo retoma (pula o que já está na saída).

Uso (na VPS, em /opt/saleia):
    venv/bin/python -m scripts.c4_paulo_sugestoes momentos.json saida.jsonl
    venv/bin/python -m scripts.c4_paulo_sugestoes momentos.json saida.jsonl --real
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

CONCORRENCIA = 4


async def _contexto_rag(transcricao: str, historico: str) -> str:
    """Mesmo contexto que analisar_fragmento_multi injeta no Coach."""
    from agent.base_conhecimento import buscar_contexto_similar
    from agent.sales_memory import buscar_contexto_para_reuniao
    from api.database import buscar_conhecimento_compilado_similar

    consulta = f"{transcricao} {historico}"
    partes = []
    for nome, fn in (("rag", None), ("memoria", buscar_contexto_para_reuniao), ("biblioteca", buscar_conhecimento_compilado_similar)):
        try:
            if nome == "rag":
                ctx = await buscar_contexto_similar(consulta, top_k=3)
            else:
                ctx = fn(consulta, top_k=3 if nome == "memoria" else 2)
            if ctx:
                partes.append(ctx)
        except Exception:
            pass
    return "\n\n".join(partes)


async def _coach(m: dict) -> dict:
    from agent.multiagente.coach_agent import analisar_coach

    contexto = await _contexto_rag(m["transcricao_parcial"], m["historico"])
    r = await analisar_coach(m["transcricao_parcial"], m["historico"], "Resumo ainda nao disponivel", {}, [],
                             "", contexto, None, f"c4_paulo:{m['id']}")
    nba = r.get("next_best_action") or {}
    return {"next_best_action": nba.get("message"), "categoria": nba.get("category"),
            "texto_falavel": r.get("texto_falavel") or r.get("proxima_fala"), "dica_vendedor": r.get("dica_vendedor"),
            "alerta_urgente": r.get("alerta_urgente"), "conversation_stage": r.get("conversation_stage"),
            "usou_biblioteca": "Biblioteca de Inteligência" in contexto}


async def _motor(m: dict) -> dict:
    from agent.behavioral_signal_extractor import extrair_sinais_comportamentais_async
    from agent.buyer_motivation_extractor import extrair_buyer_motivation_async
    from agent.sales_reasoning_engine import raciocinar_async
    from agent.spin_extractor import extrair_spin_state_async

    spin, sinais, motivacao = await asyncio.gather(
        extrair_spin_state_async(m["transcricao_parcial"], m["historico"]),
        extrair_sinais_comportamentais_async(m["transcricao_parcial"], m["historico"]),
        extrair_buyer_motivation_async(m["transcricao_parcial"], m["historico"]),
        return_exceptions=True,
    )
    entrada = {"meeting_memory": {"transcricao_parcial": m["transcricao_parcial"]},
               "spin_state": None if isinstance(spin, Exception) else spin,
               "behavioral_signals": None if isinstance(sinais, Exception) else sinais,
               "buyer_motivation": None if isinstance(motivacao, Exception) else motivacao}
    r = await raciocinar_async(entrada, meeting_id=f"c4_paulo:{m['id']}")
    return {k: r.get(k) for k in ("recommended_framework", "next_best_action", "next_best_question", "avoid",
                                  "reason", "confidence", "current_state")}


async def _rodar(momentos: list, saida: Path) -> None:
    feitos = set()
    if saida.exists():
        feitos = {json.loads(l)["id"] for l in saida.read_text(encoding="utf-8").splitlines() if l.strip()}
    pendentes = [m for m in momentos if m["id"] not in feitos]
    print(f"{len(feitos)} já feitos, {len(pendentes)} pendentes")
    sem = asyncio.Semaphore(CONCORRENCIA)
    trava = asyncio.Lock()

    async def um(m):
        async with sem:
            t0 = time.time()
            coach, motor = await asyncio.gather(_coach(m), _motor(m), return_exceptions=True)
            linha = {"id": m["id"], "segundos": round(time.time() - t0, 1),
                     "coach": None if isinstance(coach, Exception) else coach,
                     "motor": None if isinstance(motor, Exception) else motor,
                     "erros": [f"{n}: {type(x).__name__}: {x}" for n, x in (("coach", coach), ("motor", motor))
                               if isinstance(x, Exception)]}
            async with trava:
                with saida.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(linha, ensure_ascii=False) + "\n")
            print(m["id"], linha["segundos"], "s", "erros:" if linha["erros"] else "", *linha["erros"], flush=True)

    await asyncio.gather(*(um(m) for m in pendentes))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("momentos")
    parser.add_argument("saida")
    parser.add_argument("--real", action="store_true", help="Chama IA de verdade (custo real). Sem esta flag, só conta.")
    args = parser.parse_args()
    momentos = json.loads(Path(args.momentos).read_text(encoding="utf-8"))
    if not args.real:
        print(f"[DRY-RUN] {len(momentos)} momentos × (1 coach + 3 extratores + 1 motor) = até {len(momentos) * 5} chamadas de IA")
        return
    asyncio.run(_rodar(momentos, Path(args.saida)))


if __name__ == "__main__":
    main()
