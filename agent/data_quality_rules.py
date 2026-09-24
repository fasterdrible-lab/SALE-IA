"""Data Quality — seção 33 do "PROMPT MESTRE — SALE-IA V2" (Tarefa B1 de
`docs/tasks-prompt-mestre-v2-restante.md`).

"Sem dados confiáveis não existe Sales Science confiável." Função pura,
sem IA/banco — recebe linhas já carregadas (dicts) e devolve os achados.
Nunca corrige nem apaga nada: só aponta, com amostra de ids, para decisão
humana (mesma disciplina de `precisa_investigar()`/gaps explícitos).

Os 7 códigos são os literais da seção 33. Severidade:
- `erro` — dado inconsistente que distorce qualquer análise (valor
  negativo, timestamp impossível, referência quebrada, duplicata).
- `aviso` — dado incompleto mas legítimo no fluxo atual (reunião anônima
  sem vendedor, reunião sem oportunidade vinculada, desfecho não
  registrado). Mede o quanto Sales Science ainda não enxerga.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

from agent.opportunity_memory_rules import OPPORTUNITY_STATUSES

DATA_QUALITY_CHECKS = {
    "missing_seller_id": ("aviso", "Registro sem vendedor (seller_id/usuario_id) — não entra em análise por vendedor."),
    "missing_opportunity_id": ("aviso", "Registro sem oportunidade vinculada — não entra em Win/Loss nem Learning Loop."),
    "negative_deal_value": ("erro", "Valor de negócio negativo (estimated_value/outcome_value)."),
    "invalid_timestamps": ("erro", "Timestamp no futuro ou fora de ordem (fim antes do início)."),
    "duplicate_events": ("erro", "Evento repetido (mesmo conteúdo, mesma reunião, janela curta)."),
    "orphan_meetings": ("erro", "Referência quebrada: aponta para reunião/oportunidade que não existe."),
    "unknown_outcomes": ("aviso", "Oportunidade sem desfecho confiável (status inválido, fechada sem dados, ou aberta há muito tempo)."),
}

TOLERANCIA_FUTURO_PADRAO = timedelta(minutes=10)
JANELA_DUPLICATA_PADRAO = timedelta(minutes=5)
DIAS_SEM_DESFECHO_PADRAO = 90
MAX_EXEMPLOS = 5


def _vazio(valor) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _norm(texto) -> str:
    return re.sub(r"\s+", " ", str(texto or "").strip().lower())


class _Acumulador:
    def __init__(self):
        self._itens = {}

    def registrar(self, codigo: str, tabela: str, avaliados: int, ids_problema: list) -> None:
        severidade, descricao = DATA_QUALITY_CHECKS[codigo]
        self._itens[(codigo, tabela)] = {
            "codigo": codigo,
            "tabela": tabela,
            "severidade": severidade,
            "descricao": descricao,
            "avaliados": avaliados,
            "problemas": len(ids_problema),
            "taxa": round(len(ids_problema) / avaliados, 4) if avaliados else None,
            "exemplos": ids_problema[:MAX_EXEMPLOS],
        }

    def itens(self) -> list:
        return list(self._itens.values())


def _no_futuro(dt: Optional[datetime], agora: datetime, tolerancia: timedelta) -> bool:
    return dt is not None and dt > agora + tolerancia


def verificar_meetings(meetings: list, opportunity_ids: set, agora: datetime,
                       tolerancia_futuro: timedelta = TOLERANCIA_FUTURO_PADRAO) -> list:
    """`meetings`: dicts com meeting_id, usuario_id, opportunity_id,
    created_at, updated_at."""
    acc = _Acumulador()
    n = len(meetings)
    acc.registrar("missing_seller_id", "meeting_memory", n,
                  [m["meeting_id"] for m in meetings if _vazio(m.get("usuario_id"))])
    acc.registrar("missing_opportunity_id", "meeting_memory", n,
                  [m["meeting_id"] for m in meetings if m.get("opportunity_id") is None])
    acc.registrar("orphan_meetings", "meeting_memory", n,
                  [m["meeting_id"] for m in meetings
                   if m.get("opportunity_id") is not None and m["opportunity_id"] not in opportunity_ids])
    acc.registrar("invalid_timestamps", "meeting_memory", n, [
        m["meeting_id"] for m in meetings
        if _no_futuro(m.get("created_at"), agora, tolerancia_futuro)
        or _no_futuro(m.get("updated_at"), agora, tolerancia_futuro)
        or (m.get("created_at") and m.get("updated_at") and m["updated_at"] < m["created_at"])
    ])
    return acc.itens()


def _desfecho_desconhecido(o: dict, agora: datetime, dias: int) -> bool:
    status = o.get("status")
    if status not in OPPORTUNITY_STATUSES:
        return True
    if status == "won":
        return o.get("outcome_value") is None or _vazio(o.get("product")) or o.get("close_date") is None
    if status == "lost":
        return _vazio(o.get("loss_reason"))
    if status == "open":
        criado = o.get("created_at")
        return criado is not None and agora - criado > timedelta(days=dias)
    return False


def verificar_opportunities(opportunities: list, agora: datetime,
                            dias_sem_desfecho: int = DIAS_SEM_DESFECHO_PADRAO,
                            tolerancia_futuro: timedelta = TOLERANCIA_FUTURO_PADRAO) -> list:
    """`opportunities`: dicts no formato de `listar_opportunities()`."""
    acc = _Acumulador()
    n = len(opportunities)
    acc.registrar("missing_seller_id", "opportunities", n,
                  [o["id"] for o in opportunities if _vazio(o.get("seller_id"))])
    acc.registrar("negative_deal_value", "opportunities", n, [
        o["id"] for o in opportunities
        if (o.get("estimated_value") is not None and o["estimated_value"] < 0)
        or (o.get("outcome_value") is not None and o["outcome_value"] < 0)
    ])

    def _ts_invalido(o):
        criado = o.get("created_at")
        if _no_futuro(criado, agora, tolerancia_futuro):
            return True
        for campo in ("close_date", "won_at", "lost_at"):
            valor = o.get(campo)
            if _no_futuro(valor, agora, tolerancia_futuro):
                return True
            # close_date é informado pelo usuário (data, não instante) —
            # compara por dia para não acusar "fechou às 00:00 do dia em
            # que foi criada".
            if criado and valor and valor.date() < criado.date():
                return True
        return False

    acc.registrar("invalid_timestamps", "opportunities", n, [o["id"] for o in opportunities if _ts_invalido(o)])
    acc.registrar("unknown_outcomes", "opportunities", n,
                  [o["id"] for o in opportunities if _desfecho_desconhecido(o, agora, dias_sem_desfecho)])
    return acc.itens()


def _ids_duplicados(linhas: list, chave, janela: timedelta, campo_tempo: str) -> list:
    ultimos = {}
    duplicados = []
    for linha in sorted(linhas, key=lambda l: (l.get(campo_tempo) or datetime.min)):
        k = chave(linha)
        t = linha.get(campo_tempo)
        anterior = ultimos.get(k)
        if anterior is not None and t is not None and t - anterior <= janela:
            duplicados.append(linha["id"])
        ultimos[k] = t
    return duplicados


def verificar_recommendation_events(eventos: list, meeting_ids: set, agora: datetime,
                                    janela_duplicata: timedelta = JANELA_DUPLICATA_PADRAO,
                                    tolerancia_futuro: timedelta = TOLERANCIA_FUTURO_PADRAO) -> list:
    """`eventos`: dicts com id, meeting_id, opportunity_id, recommendation,
    shown_at, used_at."""
    acc = _Acumulador()
    n = len(eventos)
    acc.registrar("missing_opportunity_id", "recommendation_events", n,
                  [e["id"] for e in eventos if e.get("opportunity_id") is None])
    acc.registrar("orphan_meetings", "recommendation_events", n,
                  [e["id"] for e in eventos if e.get("meeting_id") not in meeting_ids])
    acc.registrar("invalid_timestamps", "recommendation_events", n, [
        e["id"] for e in eventos
        if _no_futuro(e.get("shown_at"), agora, tolerancia_futuro)
        or (e.get("used_at") and e.get("shown_at") and e["used_at"] < e["shown_at"])
    ])
    acc.registrar("duplicate_events", "recommendation_events", n, _ids_duplicados(
        eventos, lambda e: (e.get("meeting_id"), _norm(e.get("recommendation"))), janela_duplicata, "shown_at"))
    return acc.itens()


def verificar_sales_events(eventos: list, meeting_ids: set, agora: datetime,
                           janela_duplicata: timedelta = JANELA_DUPLICATA_PADRAO,
                           tolerancia_futuro: timedelta = TOLERANCIA_FUTURO_PADRAO) -> list:
    """`eventos`: dicts com id, meeting_id, seller_id, event_type,
    evidence_quote, timestamp."""
    acc = _Acumulador()
    n = len(eventos)
    acc.registrar("missing_seller_id", "sales_events", n, [e["id"] for e in eventos if _vazio(e.get("seller_id"))])
    acc.registrar("orphan_meetings", "sales_events", n,
                  [e["id"] for e in eventos if e.get("meeting_id") not in meeting_ids])
    acc.registrar("invalid_timestamps", "sales_events", n,
                  [e["id"] for e in eventos if _no_futuro(e.get("timestamp"), agora, tolerancia_futuro)])
    acc.registrar("duplicate_events", "sales_events", n, _ids_duplicados(
        eventos, lambda e: (e.get("meeting_id"), e.get("event_type"), _norm(e.get("evidence_quote"))),
        janela_duplicata, "timestamp"))
    return acc.itens()


def gerar_relatorio_qualidade(dados: dict, agora: datetime, dias_sem_desfecho: int = DIAS_SEM_DESFECHO_PADRAO) -> dict:
    """Roda todas as verificações sobre a saída de
    `api.database.coletar_dados_qualidade()`."""
    meetings = dados.get("meetings") or []
    opportunities = dados.get("opportunities") or []
    meeting_ids = {m["meeting_id"] for m in meetings}
    opportunity_ids = {o["id"] for o in opportunities}
    itens = (
        verificar_meetings(meetings, opportunity_ids, agora)
        + verificar_opportunities(opportunities, agora, dias_sem_desfecho=dias_sem_desfecho)
        + verificar_recommendation_events(dados.get("recommendation_events") or [], meeting_ids, agora)
        + verificar_sales_events(dados.get("sales_events") or [], meeting_ids, agora)
    )
    return montar_relatorio(itens, agora)


def montar_relatorio(itens: list, agora: datetime) -> dict:
    """Consolida os achados. `ok` só é True sem nenhum `erro` — `aviso`
    mede cobertura, não bloqueia."""
    erros = sum(i["problemas"] for i in itens if i["severidade"] == "erro")
    avisos = sum(i["problemas"] for i in itens if i["severidade"] == "aviso")
    ordem = list(DATA_QUALITY_CHECKS)
    return {
        "gerado_em": agora.isoformat(timespec="seconds"),
        "ok": erros == 0,
        "total_erros": erros,
        "total_avisos": avisos,
        "verificacoes": sorted(itens, key=lambda i: (ordem.index(i["codigo"]), i["tabela"])),
    }
