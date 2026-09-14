"""
SALEIA — agent/data_warehouse_rules.py

Regras puras do Data Warehouse comercial mínimo (FASE 9 / TAREFA 9.1
do "PROMPT MESTRE — SALE-IA V2"). Nenhuma chamada de IA, nenhum acesso
a banco — mesmo padrão de agent/win_loss_rules.py.

Objetivo do prompt mestre: um dataset analítico derivado (não as
tabelas operacionais) com as dimensões de DIMENSOES_DATASET. Dimensões
de calendário (date/month/quarter/week/weekday/hour) são sempre
derivadas de uma data real, nunca informadas pelo chamador — mesmo
princípio de `outcome_rules.calcular_cycle_days()` (Fase 8): nunca
aceitar como input o que pode ser calculado com precisão a partir do
dado real.

Dimensões que a `Opportunity` ainda não rastreia (`team`,
`lead_source`, `objection_type`, `sales_strategy`) são aceitas via
`**dimensoes_extra` — quem extrai esse dado real (de qual sistema, com
qual regra) é integração futura não pedida por esta tarefa, mesmo
princípio já usado em `win_loss_rules.py` (Fase 8 / Tarefa 8.2) para as
15 variáveis do Win/Loss Intelligence.
"""

from datetime import datetime
from typing import Optional

# As 16 dimensões literais do prompt mestre.
DIMENSOES_DATASET = frozenset({
    "date", "month", "quarter", "week", "weekday", "hour",
    "seller", "team",
    "segment", "product", "lead_source",
    "opportunity_stage", "ticket",
    "objection_type", "sales_strategy",
    "won", "lost", "cycle_days",
})


def derivar_dimensoes_calendario(data: datetime) -> dict:
    """As 6 dimensões de calendário do prompt mestre, sempre calculadas
    a partir de uma data real — nunca aceitas como input separado."""
    if not isinstance(data, datetime):
        raise ValueError(f"data inválida: {data!r} (esperado datetime)")
    return {
        "date": data.date().isoformat(),
        "month": data.month,
        "quarter": (data.month - 1) // 3 + 1,
        "week": data.isocalendar()[1],
        "weekday": data.weekday(),  # 0 = segunda-feira
        "hour": data.hour,
    }


def construir_linha_analitica(
    opportunity: dict,
    campo_data: str = "close_date",
    **dimensoes_extra,
) -> dict:
    """Constrói uma linha do dataset analítico a partir de uma
    Opportunity (mesmo formato de `api.database.listar_opportunities()`
    / `_opportunity_to_dict()`).

    `campo_data` escolhe qual campo de data derivar as dimensões de
    calendário — default `"close_date"` (Fase 8), cai para
    `"created_at"` quando a oportunidade ainda não tem `close_date`
    (ainda aberta). Levanta `ValueError` quando nenhuma das duas
    existe — uma linha do warehouse sem nenhuma data é dado inválido,
    nunca um erro silencioso.

    `ticket` usa `outcome_value` (valor real de fechamento, Fase 8)
    quando disponível, senão `estimated_value` — nunca os dois
    somados/misturados."""
    data_bruta = opportunity.get(campo_data) or opportunity.get("created_at")
    if not data_bruta:
        raise ValueError("Opportunity sem nenhuma data válida para derivar dimensões de calendário")
    data = data_bruta if isinstance(data_bruta, datetime) else datetime.fromisoformat(data_bruta)

    status = opportunity.get("status")
    ticket = opportunity.get("outcome_value")
    if ticket is None:
        ticket = opportunity.get("estimated_value")

    linha = {
        **derivar_dimensoes_calendario(data),
        "seller": opportunity.get("seller_id"),
        "team": dimensoes_extra.get("team"),
        "segment": dimensoes_extra.get("segment"),
        "product": opportunity.get("product") or dimensoes_extra.get("product"),
        "lead_source": dimensoes_extra.get("lead_source"),
        "opportunity_stage": opportunity.get("stage"),
        "ticket": ticket,
        "objection_type": dimensoes_extra.get("objection_type"),
        "sales_strategy": dimensoes_extra.get("sales_strategy"),
        "won": status == "won",
        "lost": status == "lost",
        "cycle_days": opportunity.get("cycle_days"),
    }
    return linha


def construir_dataset_analitico(opportunities: list, **kwargs) -> list:
    """Aplica `construir_linha_analitica` a uma lista de Opportunities.
    Oportunidade sem data válida é **pulada, nunca derruba o dataset
    inteiro** — um dataset analítico precisa ser resiliente a dado
    operacional incompleto."""
    linhas = []
    for opp in opportunities:
        try:
            linhas.append(construir_linha_analitica(opp, **kwargs))
        except ValueError:
            continue
    return linhas


def pode_executar_analise_pesada(reunioes_ativas: int) -> bool:
    """Regra literal do prompt mestre: "nunca executar análises pesadas
    diretamente sobre tabelas operacionais em horário de reunião".
    Reaproveita o mesmo sinal `reunioes_ativas` que já governa todo
    deploy seguro do projeto (ver runbook de deploy em CLAUDE.md) — uma
    reunião ativa é o sinal mais direto de "estamos em horário de
    reunião" que o sistema já produz, não inventa um relógio de
    "horário comercial" novo."""
    if reunioes_ativas < 0:
        raise ValueError(f"reunioes_ativas inválido: {reunioes_ativas!r}")
    return reunioes_ativas == 0
