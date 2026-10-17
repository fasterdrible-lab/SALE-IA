"""Métricas da conversa (A8, V.1.4.187): junta as falas temporizadas
(`turnos_fala`) com o "quem é quem" da sessão e calcula com
`agent/turnos_rules.py`. Usado pelo detalhe da sessão no Dashboard e pelo
Seller Coaching (Talk Ratio / Question Quality)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from agent.participantes_rules import de_json
from agent.turnos_rules import agregar_vendedor, metricas_da_reuniao

logger = logging.getLogger("saleia.metricas_conversa")

# A sessão nasce quando a extensão abre (/iniciar-sessao), antes da 1ª fala.
FOLGA_INICIO = timedelta(minutes=2)


def _data(valor) -> datetime | None:
    if isinstance(valor, datetime):
        return valor
    try:
        return datetime.fromisoformat(str(valor)) if valor else None
    except ValueError:
        return None


def metricas_da_sessao(sessao: dict) -> dict:
    """`sessao` = dict de `buscar_sessao` (meeting_id, created_at,
    participantes_json). Só as falas desta sessão (sala fixa do Meet reusa
    o código)."""
    from api.database import listar_turnos

    inicio = _data(sessao.get("created_at"))
    turnos = listar_turnos(sessao.get("meeting_id") or "", desde=(inicio - FOLGA_INICIO) if inicio else None)
    return metricas_da_reuniao(turnos, de_json(sessao.get("participantes_json")))


def metricas_do_vendedor(seller_id: str, dias: int = 30) -> dict:
    """Agregado das reuniões do vendedor (dono da MeetingMemory) nos
    últimos `dias`. {} quando não há reunião com fala temporizada."""
    from sqlmodel import Session, select

    from agent.sessao_manager import obter_participantes
    from api.database import MeetingMemory, engine, listar_turnos

    desde = datetime.now() - timedelta(days=dias)
    with Session(engine) as session:
        mids = session.exec(select(MeetingMemory.meeting_id).where(
            MeetingMemory.usuario_id == seller_id, MeetingMemory.updated_at >= desde)).all()
    metricas = []
    for mid in mids:
        try:
            turnos = listar_turnos(mid, desde=desde)
            if turnos:
                metricas.append(metricas_da_reuniao(turnos, de_json(obter_participantes(mid))))
        except Exception as exc:  # uma reunião ruim não derruba o agregado
            logger.warning("[MetricasConversa] %s: %s", mid, exc)
    agregado = agregar_vendedor(metricas)
    if agregado:
        agregado["dias"] = dias
    return agregado
