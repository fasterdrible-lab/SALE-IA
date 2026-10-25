"""Bloco 2 / Tarefa 2.1 de docs/tasks-sales-reasoning-engine-completo.md
— alimenta o campo `historical_patterns` do SalesReasoningEngine (Fase
7) com o insight de Win/Loss real (Fase 8/13) que bate com o estágio
atual da oportunidade vinculada à reunião.

Depende da Tarefa 3.1 (`agent/opportunity_link_rules.py`) já ter
vinculado a reunião a uma `Opportunity` — sem `opportunity_id`, este
módulo nunca tem o que filtrar.

**Só filtra por `stage`, nunca por `product`/`competitor`**: esses 2
campos só nascem quando a oportunidade fecha (`Opportunity.product`/
`competitor`, Fase 8) — uma oportunidade ainda aberta (o caso real de
toda reunião em andamento) nunca tem esses campos preenchidos.

**Nunca recalcula estatística** — reaproveita `agent/win_loss_
rules.py::comparar_por_variavel_categorica()` (Fase 8) e `agent/
sales_science_engine.py::insight_de_win_loss_analyzer()` (Fase 13)
exatamente como `agent/sales_science_insights_rules.py` (Fase 22/bloco
3) já faz — só que filtrado a 1 categoria (`stage`) em vez das 3
(`stage`/`product`/`competitor`) que `montar_sales_science_insights()`
computa de uma vez, para não recalcular win_loss/seasonality/
conversion_drivers inteiros a cada ciclo de `/tempo-real` sem
necessidade.

**C5 (24/10/2026) — estratégias com efetividade medida.** Classificar o
uso de cada recomendação exige embeddings (lento demais para o ciclo),
então `scripts/recommendation_quality_run.py --real` grava um retrato de
`calcular_efetividade_por_estrategia()` (Fase 10.3 + B2) em
`data/efetividade_estrategias.json` e este módulo só lê esse arquivo.
Entram só estratégias com amostra de avanço suficiente
(`insight_de_strategy_effectiveness`), sempre como associação. Sem
nenhuma estratégia elegível, `historical_patterns` fica exatamente como
antes (só o insight de Win/Loss). Kill-switch
`ESTRATEGIAS_EFETIVAS_NO_MOTOR_ENABLED` (default `true`).
"""

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SNAPSHOT_EFETIVIDADE_PATH = Path(__file__).resolve().parent.parent / "data" / "efetividade_estrategias.json"
MAX_ESTRATEGIAS_NO_MOTOR = 5

_cache_snapshot: dict = {"mtime": None, "dados": None}


def estrategias_no_motor_ativo() -> bool:
    return os.getenv("ESTRATEGIAS_EFETIVAS_NO_MOTOR_ENABLED", "true").strip().lower() != "false"


def salvar_snapshot_efetividade(efetividade_por_estrategia: dict, total_eventos: int) -> Path:
    """Grava o retrato (escrita atômica: os 2 workers podem estar lendo)."""
    caminho = SNAPSHOT_EFETIVIDADE_PATH
    caminho.parent.mkdir(parents=True, exist_ok=True)
    dados = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "total_eventos": total_eventos,
        "efetividade_por_estrategia": efetividade_por_estrategia,
    }
    fd, tmp = tempfile.mkstemp(dir=caminho.parent, prefix=".efetividade_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    os.replace(tmp, caminho)
    return caminho


def _ler_snapshot() -> Optional[dict]:
    caminho = SNAPSHOT_EFETIVIDADE_PATH
    try:
        mtime = caminho.stat().st_mtime
    except OSError:
        return None
    if _cache_snapshot["mtime"] != mtime:
        try:
            _cache_snapshot["dados"] = json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            logger.warning("[C5] Retrato de efetividade ilegível (%s): %s", caminho, e)
            _cache_snapshot["dados"] = None
        _cache_snapshot["mtime"] = mtime
    return _cache_snapshot["dados"]


def estrategias_com_efetividade() -> list:
    """Insights de Strategy Effectiveness do último retrato, só os com
    amostra de avanço suficiente, mais usados primeiro (até
    `MAX_ESTRATEGIAS_NO_MOTOR`). Lista vazia quando não há retrato,
    nenhuma estratégia elegível ou o kill-switch está desligado."""
    if not estrategias_no_motor_ativo():
        return []
    snapshot = _ler_snapshot()
    if not isinstance(snapshot, dict):
        return []
    from agent.sales_science_engine import insight_de_strategy_effectiveness

    insights = []
    for strategy, resumo in (snapshot.get("efetividade_por_estrategia") or {}).items():
        if not isinstance(resumo, dict):
            continue
        insight = insight_de_strategy_effectiveness(resumo, strategy)
        if insight:
            insight["evidence"]["taxa_avanco"] = resumo.get("taxa_avanco")
            insights.append(insight)
    insights.sort(key=lambda i: -i["sample"])
    return insights[:MAX_ESTRATEGIAS_NO_MOTOR]


def _win_loss_do_estagio(opportunity_id: int) -> Optional[dict]:
    from api.database import listar_opportunities, obter_opportunity
    from agent.sales_science_engine import insight_de_win_loss_analyzer
    from agent.win_loss_rules import comparar_por_variavel_categorica

    opportunity = obter_opportunity(opportunity_id)
    if not opportunity:
        return None

    stage = opportunity.get("stage")
    if not stage:
        return None

    opportunities = listar_opportunities(limit=5000)
    resultado = comparar_por_variavel_categorica(opportunities, "stage")
    grupo = resultado["grupos"].get(stage)
    if not grupo:
        return None

    return insight_de_win_loss_analyzer(grupo, "stage", stage)


def obter_historical_pattern_da_opportunity(opportunity_id: int) -> Optional[dict]:
    """Busca o insight de Win/Loss por `stage` relevante pra esta
    oportunidade. Retorna `None` (nunca fabrica sinal) quando: a
    oportunidade não existe, não tem `stage` definido, ou não há
    amostra estatística suficiente pra esse `stage` ainda
    (`amostra_suficiente=False` em `win_loss_rules`, Fase 8).

    C5: havendo estratégia com efetividade medida, devolve
    `{"win_loss_do_estagio", "estrategias_com_efetividade", "aviso"}`."""
    win_loss = _win_loss_do_estagio(opportunity_id)
    estrategias = estrategias_com_efetividade()
    if not estrategias:
        return win_loss
    return {
        "win_loss_do_estagio": win_loss,
        "estrategias_com_efetividade": estrategias,
        "aviso": "associação observada nesta amostra, nunca causa da venda",
    }
