"""
SALEIA — agent/sales_science_pipeline.py

Tarefa B3 de docs/tasks-prompt-mestre-v2-restante.md (seção 31 do
"PROMPT MESTRE — SALE-IA V2"): pipeline analítico assíncrono, fora do
hot path.

Roda num processo próprio (`scripts/sales_science_pipeline.py`, timer
`saleia-sales-science.timer` com Nice/CPUQuota), nunca dentro dos workers
do uvicorn que atendem o `/tempo-real`. Só executa com
`pode_executar_analise_pesada()` (Fase 9.1: nenhuma reunião ativa); com
reunião em andamento pula e tenta na próxima volta.

Monta o mesmo payload de `GET /sales-science/insights`
(`montar_sales_science_insights`: Win/Loss, Seasonality, Conversion
Drivers, Objection Trends, Seller Benchmark sobre o dataset analítico) e
grava em `data/sales_science_snapshot.json` (escrita atômica — os 2
workers podem estar lendo). O endpoint serve esse retrato enquanto ele
tiver menos de `VALIDADE_HORAS`; mais velho ou ausente, calcula na hora
como antes.
"""

import json
import logging
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "data" / "sales_science_snapshot.json"
# Timer de hora em hora; com reuniões o dia todo ele pula várias voltas,
# então o retrato vale por mais de um dia antes de cair no cálculo ao vivo.
VALIDADE_HORAS = 26


def _gravar(dados: dict) -> None:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=SNAPSHOT_PATH.parent, prefix=".sales_science_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, default=str)
    os.chmod(tmp, 0o644)
    os.replace(tmp, SNAPSHOT_PATH)


def executar_pipeline(contar_ativas: Optional[Callable[[], int]] = None) -> dict:
    """Uma volta do pipeline. Retorna `{"executado": bool, ...}` —
    `executado=False` com `motivo` quando há reunião ativa."""
    from agent.data_warehouse_rules import pode_executar_analise_pesada
    from agent.sales_science_insights_rules import montar_sales_science_insights
    from api.database import contar_reunioes_ativas, listar_opportunities, listar_sales_evidences

    ativas = (contar_ativas or contar_reunioes_ativas)()
    if not pode_executar_analise_pesada(ativas):
        return {"executado": False, "motivo": f"{ativas} reunião(ões) ativa(s)", "reunioes_ativas": ativas}

    inicio = time.monotonic()
    opportunities = listar_opportunities(limit=5000)
    objecoes = listar_sales_evidences(type_prefix="OBJECTION:", limit=50000)
    payload = montar_sales_science_insights(opportunities, objecoes)
    duracao = round(time.monotonic() - inicio, 2)

    # Com fuso (UTC): o Dashboard converte para o horário do navegador.
    gerado_em = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _gravar({"gerado_em": gerado_em, "duracao_s": duracao, "payload": payload})
    return {
        "executado": True,
        "gerado_em": gerado_em,
        "duracao_s": duracao,
        "oportunidades": len(opportunities),
        "objecoes": len(objecoes),
        "caminho": str(SNAPSHOT_PATH),
    }


def ler_snapshot_valido(agora: Optional[datetime] = None) -> Optional[dict]:
    """O retrato gravado, se existir, for legível e tiver menos de
    `VALIDADE_HORAS`. Qualquer problema → `None` (o chamador calcula ao
    vivo), nunca levanta."""
    try:
        dados = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        gerado_em = datetime.fromisoformat(dados["gerado_em"])
        payload = dados["payload"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    if gerado_em.tzinfo is None:
        gerado_em = gerado_em.replace(tzinfo=timezone.utc)
    if (agora or datetime.now(timezone.utc)) - gerado_em > timedelta(hours=VALIDADE_HORAS):
        return None
    return dados
