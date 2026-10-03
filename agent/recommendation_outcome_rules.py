"""
SALEIA — agent/recommendation_outcome_rules.py

Tarefa B2 de docs/tasks-prompt-mestre-v2-restante.md — captura de
`stage_advanced` e `opportunity_result` para cada `RecommendationEvent`,
os dois sinais que `recommendation_effectiveness_rules.
calcular_efetividade_por_estrategia()` (Fase 10.3) espera e que até aqui
vinham sempre `None`. Fecha o elo "o resultado é registrado" do Learning
Loop. Determinístico, zero IA.

Definições (decisões desta tarefa):
- **`stage_advanced`**: o estágio da oportunidade no momento em que a
  recomendação foi mostrada (`shown_at`) é diferente do estágio no início
  da **reunião seguinte** da mesma oportunidade. `stage` é texto livre
  (Fase 2, sem enum ordenado), então "avançar" = "mudar de estágio" — não
  dá para saber se foi para frente ou para trás. Oportunidade perdida
  antes da reunião seguinte não conta como avanço (`False`).
  `None` (nunca `False` por omissão, regra da Fase 10.3) quando: a
  reunião não está vinculada a oportunidade, ainda não houve reunião
  seguinte, ou não há histórico de estágio cobrindo os dois momentos.
- **`opportunity_result`**: `won`/`lost` da oportunidade vinculada;
  `None` enquanto aberta. `abandoned` também vira `None` — a Fase 10.3
  só define won/lost como desfecho, e abandono não é "perdida para
  alguém".

Associação, nunca causa: os dois números continuam separados e com o
template fixo da Fase 10.3 — mudar de estágio depois de uma recomendação
não prova que a recomendação causou a mudança.
"""

from datetime import datetime
from typing import Optional


def _data(valor) -> Optional[datetime]:
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, str) and valor.strip():
        try:
            return datetime.fromisoformat(valor.strip())
        except ValueError:
            return None
    return None


def estagio_em(historico: list, momento) -> Optional[str]:
    """Estágio vigente em `momento` (última linha do histórico com
    `changed_at <= momento`), ou `None` se o histórico não cobre esse
    momento."""
    momento = _data(momento)
    if momento is None:
        return None
    vigente = None
    for linha in sorted(
        (h for h in historico or [] if isinstance(h, dict) and _data(h.get("changed_at"))),
        key=lambda h: _data(h["changed_at"]),
    ):
        if _data(linha["changed_at"]) <= momento:
            vigente = linha.get("stage") or ""
        else:
            break
    return vigente


def proxima_reuniao(reunioes: list, meeting_id: str) -> Optional[dict]:
    """Primeira reunião vinculada que começou depois da reunião
    `meeting_id` (por `created_at`), ou `None`."""
    validas = [r for r in reunioes or [] if isinstance(r, dict) and _data(r.get("created_at"))]
    atual = next((r for r in validas if r.get("meeting_id") == meeting_id), None)
    if atual is None:
        return None
    inicio_atual = _data(atual["created_at"])
    seguintes = sorted(
        (r for r in validas if r.get("meeting_id") != meeting_id and _data(r["created_at"]) > inicio_atual),
        key=lambda r: _data(r["created_at"]),
    )
    return seguintes[0] if seguintes else None


def calcular_stage_advanced(
    historico: list,
    momento_recomendacao,
    momento_reuniao_seguinte,
    lost_at=None,
) -> Optional[bool]:
    """`True`/`False` quando os dois momentos são cobertos pelo
    histórico; `None` caso contrário. Perdida antes da reunião seguinte
    → `False`."""
    if momento_reuniao_seguinte is None:
        return None
    perdida_em = _data(lost_at)
    seguinte = _data(momento_reuniao_seguinte)
    if perdida_em is not None and seguinte is not None and perdida_em <= seguinte:
        return False
    antes = estagio_em(historico, momento_recomendacao)
    depois = estagio_em(historico, momento_reuniao_seguinte)
    if antes is None or depois is None:
        return None
    return antes != depois


def resultado_da_oportunidade(status: Optional[str]) -> Optional[str]:
    return status if status in ("won", "lost") else None


def resultados_do_evento(evento: dict, oportunidade: Optional[dict], reunioes: list, historico: list) -> dict:
    """Função pura: `{"stage_advanced", "opportunity_result"}` de um
    evento, dado o contexto da oportunidade vinculada à reunião dele."""
    if not oportunidade:
        return {"stage_advanced": None, "opportunity_result": None}
    seguinte = proxima_reuniao(reunioes, evento.get("meeting_id"))
    return {
        "stage_advanced": calcular_stage_advanced(
            historico,
            evento.get("shown_at") or evento.get("created_at"),
            seguinte.get("created_at") if seguinte else None,
            lost_at=oportunidade.get("lost_at"),
        ),
        "opportunity_result": resultado_da_oportunidade(oportunidade.get("status")),
    }


def anexar_resultados(eventos: list) -> list:
    """Busca o contexto de cada evento no banco (reunião → oportunidade
    → reuniões vinculadas + histórico de estágio, com cache por
    reunião/oportunidade) e devolve cópias dos eventos com
    `stage_advanced`/`opportunity_result`. O cruzamento reunião →
    oportunidade é feito em Python via `obter_meeting_memory()`, nunca
    por JOIN (collations diferentes entre tabelas, achado da Fase 6)."""
    from api.database import (
        listar_meetings_da_opportunity,
        listar_stage_history_opportunity,
        obter_meeting_memory,
        obter_opportunity,
    )

    opp_por_reuniao: dict = {}
    contexto_por_opp: dict = {}
    saida = []
    for evento in eventos or []:
        meeting_id = evento.get("meeting_id")
        if meeting_id not in opp_por_reuniao:
            memoria = obter_meeting_memory(meeting_id) if meeting_id else None
            opp_por_reuniao[meeting_id] = (memoria or {}).get("opportunity_id") or evento.get("opportunity_id")
        opportunity_id = opp_por_reuniao[meeting_id]

        if opportunity_id and opportunity_id not in contexto_por_opp:
            contexto_por_opp[opportunity_id] = (
                obter_opportunity(opportunity_id),
                listar_meetings_da_opportunity(opportunity_id),
                listar_stage_history_opportunity(opportunity_id),
            )
        oportunidade, reunioes, historico = contexto_por_opp.get(opportunity_id, (None, [], []))
        saida.append({**evento, **resultados_do_evento(evento, oportunidade, reunioes, historico)})
    return saida
