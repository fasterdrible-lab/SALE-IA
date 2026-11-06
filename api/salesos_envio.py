"""Envio da reunião analisada ao SalesOS (tarefa V2-7.2 do SalesOS). Regras
em `agent/salesos_event_rules.py`.

Roda no laço do relatório automático (`api/main.py::_loop_relatorio_automatico`,
a cada ~2 min), depois dele: pega sessões com relatório `ok` ainda não
enviadas, reserva uma por vez no banco (os 2 workers não enviam em dobro) e
faz o POST assinado. Falha de rede ou 5xx volta para a fila com espera
crescente; 400/401 fica `recusado` (reenviar não adianta).

Estado em `sessoes.salesos_status` / `salesos_tentativas` / `salesos_em` /
`salesos_detalhe`. Desligado enquanto `SALESOS_EVENTS_URL` e
`SALESOS_EVENTS_SECRET` não estiverem no .env.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from agent.salesos_event_rules import (
    MAX_TENTATIVAS,
    STATUS_ENVIANDO,
    STATUS_ERRO,
    STATUS_OK,
    STATUS_PULADO,
    STATUS_RECUSADO,
    cabecalhos,
    classificar_resposta,
    configuracao,
    montar_evento,
    pode_reenviar,
    serializar,
)

logger = logging.getLogger("saleia.salesos_envio")

TIMEOUT_S = 15


def _conn():
    from agent.sessao_manager import _get_conn
    return _get_conn()


def _candidatas() -> list[tuple]:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, meeting_id, salesos_status, COALESCE(salesos_tentativas, 0), salesos_em,
                          encerrada_em, updated_at
                   FROM sessoes
                   WHERE relatorio_status = 'ok'
                     AND (salesos_status IS NULL OR salesos_status = %s
                          OR (salesos_status = %s AND salesos_em < NOW() - INTERVAL 30 MINUTE))
                     AND COALESCE(salesos_tentativas, 0) < %s
                   ORDER BY relatorio_em LIMIT 20""",
                (STATUS_ERRO, STATUS_ENVIANDO, MAX_TENTATIVAS),
            )
            return list(cur.fetchall())
    finally:
        conn.close()


def _reservar(sessao_id: int, status_lido) -> bool:
    """Só 1 worker leva a sessão: a troca só vale se o status não mudou."""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE sessoes SET salesos_status = %s, salesos_em = NOW(), updated_at = updated_at
                   WHERE id = %s AND salesos_status <=> %s""",
                (STATUS_ENVIANDO, sessao_id, status_lido),
            )
            ganhou = cur.rowcount == 1
        conn.commit()
        return ganhou
    finally:
        conn.close()


def _marcar(sessao_id: int, status: str, detalhe: str, tentou: bool) -> None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE sessoes SET salesos_status = %s, salesos_detalhe = %s, salesos_em = NOW(),
                          salesos_tentativas = COALESCE(salesos_tentativas, 0) + %s,
                          updated_at = updated_at WHERE id = %s""",
                (status, (detalhe or "")[:200], 1 if tentou else 0, sessao_id),
            )
        conn.commit()
    finally:
        conn.close()


def _dados_da_reuniao(meeting_id: str) -> tuple[dict | None, datetime | None, list[dict]]:
    from agent.participantes_rules import de_json
    from agent.sessao_manager import obter_participantes
    from api.database import buscar_relatorio, obter_meeting_memory

    relatorio = buscar_relatorio(meeting_id)
    memoria = obter_meeting_memory(meeting_id) or {}
    try:
        inicio = datetime.fromisoformat(memoria["created_at"]) if memoria.get("created_at") else None
    except ValueError:
        inicio = None
    try:
        participantes = de_json(obter_participantes(meeting_id))
    except Exception:
        participantes = []
    return relatorio, inicio, participantes


def _post(url: str, corpo: str, headers: dict) -> tuple[int | None, str]:
    import httpx
    try:
        resposta = httpx.post(url, content=corpo.encode(), headers=headers, timeout=TIMEOUT_S)
    except httpx.HTTPError as exc:
        return None, type(exc).__name__
    detalhe = f"HTTP {resposta.status_code}"
    try:
        dados = resposta.json()
        via = (dados.get("linked") or {}).get("via")
        detalhe += f" via={via}" if 200 <= resposta.status_code < 300 else f" {dados.get('code', '')}"
    except Exception:
        pass
    return resposta.status_code, detalhe


def enviar_sessao(sessao: tuple, config: tuple[str, str], agora: datetime) -> dict:
    sessao_id, meeting_id, _status, _tentativas, _em, encerrada_em, updated_at = sessao
    url, segredo = config
    relatorio, inicio, participantes = _dados_da_reuniao(meeting_id)

    evento = montar_evento(
        meeting_id=meeting_id,
        titulo=(relatorio or {}).get("titulo") or f"Reunião {meeting_id}",
        inicio=inicio,
        fim=encerrada_em or updated_at,
        participantes=participantes,
        relatorio=relatorio or {},
        agora=agora,
    )
    corpo = serializar(evento) if evento else None
    if not corpo:
        motivo = "sem resumo" if not evento else "evento acima de 256 KB"
        _marcar(sessao_id, STATUS_PULADO, motivo, tentou=False)
        return {"sessao_id": sessao_id, "status": STATUS_PULADO, "detalhe": motivo}

    codigo, detalhe = _post(url, corpo, cabecalhos(segredo, corpo, agora))
    status = classificar_resposta(codigo)
    _marcar(sessao_id, status, detalhe, tentou=True)
    nivel = logging.INFO if status == STATUS_OK else logging.WARNING
    logger.log(nivel, "[SalesOS] %s sessão %s (%s): %s", status, sessao_id, meeting_id, detalhe)
    return {"sessao_id": sessao_id, "status": status, "detalhe": detalhe}


def processar_envios(max_por_vez: int = 5, agora: datetime | None = None) -> list[dict]:
    """Uma volta da fila. Retorna o que aconteceu com cada sessão tocada."""
    config = configuracao()
    if not config:
        return []
    # UTC sem fuso, como o NOW() do MySQL na VPS (salesos_em).
    agora = agora or datetime.now(timezone.utc).replace(tzinfo=None)
    feitos: list[dict] = []
    for sessao in _candidatas():
        if len(feitos) >= max_por_vez:
            break
        sessao_id, _meeting, status, tentativas, em = sessao[:5]
        if status == STATUS_ERRO and not pode_reenviar(tentativas, em, agora):
            continue
        if not _reservar(sessao_id, status):
            continue
        try:
            feitos.append(enviar_sessao(sessao, config, agora))
        except Exception as exc:  # nunca derruba o laço
            logger.warning("[SalesOS] erro na sessão %s: %s", sessao_id, exc)
            try:
                _marcar(sessao_id, STATUS_ERRO, type(exc).__name__, tentou=True)
            except Exception:
                pass
            feitos.append({"sessao_id": sessao_id, "status": STATUS_ERRO, "detalhe": type(exc).__name__})
    return feitos


__all__ = ["processar_envios", "enviar_sessao", "STATUS_RECUSADO"]
