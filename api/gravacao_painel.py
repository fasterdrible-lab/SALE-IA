"""Painel de gravações do Dashboard (pedido de 12/10/2026).

Fase 1: lista das reuniões gravadas e, por reunião, as trilhas (aba e
microfone) numa linha do tempo única, o volume por janela de
`JANELA_NIVEL_S` e a transcrição da mesma reunião.
Fase 2: trechos de referência com WER.

Permissão: vendedor vê só as gravações dele; admin vê todas (mesma regra
de GET /gravacao/{id}/audio). Só leitura do que a T02 gravou — exceto a
tabela de referências e o cache de volume. Regras puras:
`agent/gravacao_revisao_rules.py`.
"""
from __future__ import annotations

import json
import logging
import math
import os
import tempfile
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, or_, select

from agent import gravacao_revisao_rules as regras
from api import database
from api.database import GravacaoAudio, GravacaoBloco, GravacaoNivel, GravacaoReferencia, MeetingMemory
from api.gravacao_store import GravacaoErro, montar_audio

logger = logging.getLogger("saleia.gravacao")


def _gravacoes_visiveis(session: Session, usuario_id: str, admin: bool, desde: Optional[datetime] = None,
                        meeting_id: Optional[str] = None) -> list:
    q = select(GravacaoAudio).where(GravacaoAudio.status != "apagada")
    if not admin:
        q = q.where(GravacaoAudio.usuario_id == usuario_id)
    if desde:
        q = q.where(GravacaoAudio.iniciada_em >= desde)
    if meeting_id:
        q = q.where(GravacaoAudio.meeting_id == meeting_id)
    return session.exec(q).all()


def _blocos_por_gravacao(session: Session, ids: list) -> dict:
    """recording_id → {blocos, bytes, inicio_ms, fim_ms, ultimo_recebido}."""
    resumo: dict = {}
    if not ids:
        return resumo
    for b in session.exec(select(GravacaoBloco).where(GravacaoBloco.recording_id.in_(ids))).all():
        r = resumo.setdefault(b.recording_id, {"blocos": 0, "bytes": 0, "inicio_ms": None, "fim_ms": None,
                                               "ultimo_recebido": None})
        r["blocos"] += 1
        r["bytes"] += b.tamanho
        r["inicio_ms"] = b.start_ms if r["inicio_ms"] is None else min(r["inicio_ms"], b.start_ms)
        r["fim_ms"] = b.end_ms if r["fim_ms"] is None else max(r["fim_ms"], b.end_ms)
        if r["ultimo_recebido"] is None or b.recebido_em > r["ultimo_recebido"]:
            r["ultimo_recebido"] = b.recebido_em
    return resumo


def _como_item(g: GravacaoAudio, blocos: dict) -> dict:
    b = blocos.get(g.recording_id) or {}
    # Fim = último bloco recebido, não encerrada_em: a gravação abandonada é
    # fechada pela manutenção horas depois (em 12/10 a lista mostrou 2h12 para
    # uma reunião de 20 min). Sem bloco nenhum, a gravação não tem duração.
    fim = b.get("ultimo_recebido") or g.iniciada_em
    return {
        "recording_id": g.recording_id, "meeting_id": g.meeting_id, "track_id": g.track_id,
        "usuario_id": g.usuario_id, "status": g.status, "integridade": g.integridade,
        "integridade_detalhe": g.integridade_detalhe, "lacunas": json.loads(g.lacunas_json or "[]"),
        "duracao_s": g.duracao_s, "inicio": g.iniciada_em, "fim": fim,
        "blocos": b.get("blocos", 0), "bytes": b.get("bytes", 0),
        "inicio_ms": b.get("inicio_ms"), "fim_ms": b.get("fim_ms"), "apagar_em": g.apagar_em,
    }


def _iso(d: Optional[datetime]) -> Optional[str]:
    return d.isoformat() if d else None


def _nomes(ids: list) -> dict:
    try:
        from agent.sessao_manager import obter_nomes_usuarios
        return obter_nomes_usuarios(list(set(ids)))
    except Exception:  # painel funciona sem os nomes
        return {}


def _resumo_trilhas(gravacoes: list) -> dict:
    trilhas = {}
    for t in ("aba", "microfone"):
        gs = [g for g in gravacoes if g["track_id"] == t]
        if not gs:
            continue
        seg = sum((g["fim_ms"] - g["inicio_ms"]) / 1000 for g in gs if g["inicio_ms"] is not None)
        trilhas[t] = {
            "gravacoes": len(gs),
            "segundos": round(seg, 1),
            "bytes": sum(g["bytes"] for g in gs),
            # Opus com fala dá ~1-2 KB/s; silêncio digital fica em ~0,1-0,3 KB/s.
            "provavel_silencio": seg > 30 and sum(g["bytes"] for g in gs) / seg < 600,
            "lacunas": sum(len(g["lacunas"]) for g in gs),
            "com_erro": sum(1 for g in gs if g["integridade"] == "erro"),
            "abertas": sum(1 for g in gs if g["status"] == "gravando"),
        }
    return trilhas


def listar_sessoes(usuario_id: str, admin: bool = False, dias: int = 90) -> list:
    desde = datetime.now() - timedelta(days=max(1, min(int(dias), 3650)))
    with Session(database.engine) as session:
        gravacoes = _gravacoes_visiveis(session, usuario_id, admin, desde=desde)
        blocos = _blocos_por_gravacao(session, [g.recording_id for g in gravacoes])
        itens = [_como_item(g, blocos) for g in gravacoes]
        sessoes = regras.agrupar_sessoes(itens)
        refs = {}
        if sessoes:
            for r in session.exec(select(GravacaoReferencia).where(
                    GravacaoReferencia.sessao_id.in_([s["sessao_id"] for s in sessoes]))).all():
                refs.setdefault(r.sessao_id, []).append(_ref_dict(r))
    nomes = _nomes([g["usuario_id"] for s in sessoes for g in s["gravacoes"]])
    saida = []
    for s in reversed(sessoes):  # mais recente primeiro
        donos = sorted({g["usuario_id"] for g in s["gravacoes"]})
        saida.append({
            "sessao_id": s["sessao_id"], "meeting_id": s["meeting_id"],
            "inicio": _iso(s["inicio"]), "fim": _iso(s["fim"]),
            "duracao_s": round((s["fim"] - s["inicio"]).total_seconds()),
            "vendedores": [(nomes.get(u) or {}).get("nome") or u for u in donos],
            "trilhas": _resumo_trilhas(s["gravacoes"]),
            "revisao": regras.resumir_referencias(refs.get(s["sessao_id"], [])),
        })
    return saida


def calcular_niveis(dados: bytes, janela_s: float = regras.JANELA_NIVEL_S) -> tuple:
    """(niveis dBFS por janela — None = sem amostra —, duração em s)."""
    if not dados:
        return [], 0.0
    import av
    import numpy as np

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(dados)
        caminho = f.name
    try:
        soma: dict = {}
        total = 0.0
        with av.open(caminho) as arquivo:
            if not arquivo.streams.audio:
                return [], 0.0
            st = arquivo.streams.audio[0]
            try:
                for quadro in arquivo.decode(st):
                    a = quadro.to_ndarray().astype(np.float64)
                    if np.abs(a).max(initial=0) > 1.5:  # inteiro → -1..1
                        a = a / 32768.0
                    taxa = quadro.sample_rate or 48000
                    t = float(quadro.pts * st.time_base) if quadro.pts is not None else total
                    s = soma.setdefault(int(t // janela_s), [0.0, 0])
                    s[0] += float((a ** 2).sum())
                    s[1] += a.size
                    total = max(total, t + quadro.samples / taxa)
            except av.error.InvalidDataError:
                pass  # áudio cortado no fim (bloco perdido): fica o que decodificou
        n = int(math.ceil(total / janela_s)) if total else 0
        niveis = []
        for k in range(n):
            sq, cont = soma.get(k, (0.0, 0))
            if not cont:
                niveis.append(None)
                continue
            rms = math.sqrt(sq / cont)
            niveis.append(round(20 * math.log10(rms), 1) if rms > 1e-6 else -120.0)
        return niveis, round(total, 2)
    finally:
        os.unlink(caminho)


def _niveis(session: Session, g: GravacaoAudio) -> tuple:
    cache = session.exec(select(GravacaoNivel).where(GravacaoNivel.recording_id == g.recording_id)).first()
    if cache:
        return json.loads(cache.niveis_json), cache.duracao_s
    blocos = session.exec(select(GravacaoBloco).where(GravacaoBloco.recording_id == g.recording_id)
                          .order_by(GravacaoBloco.sequence)).all()
    try:
        niveis, duracao = calcular_niveis(montar_audio(blocos))
    except Exception as e:
        logger.warning("[Gravacao] volume de %s não calculado: %s", g.recording_id, e)
        return [], None
    if g.status == "encerrada":  # gravando ainda muda: não guarda
        session.add(GravacaoNivel(recording_id=g.recording_id, janela_s=regras.JANELA_NIVEL_S,
                                  duracao_s=duracao, niveis_json=json.dumps(niveis)))
        try:
            session.commit()
        except Exception:  # outro worker guardou ao mesmo tempo
            session.rollback()
    return niveis, duracao


def _sessao_da_pessoa(session: Session, usuario_id: str, admin: bool, sessao_id: str) -> dict:
    primeira = session.exec(select(GravacaoAudio).where(GravacaoAudio.recording_id == sessao_id)).first()
    if not primeira or primeira.status == "apagada" or (primeira.usuario_id != usuario_id and not admin):
        raise GravacaoErro(404, "Gravação não encontrada.")
    gravacoes = _gravacoes_visiveis(session, usuario_id, admin, meeting_id=primeira.meeting_id)
    blocos = _blocos_por_gravacao(session, [g.recording_id for g in gravacoes])
    por_id = {g.recording_id: g for g in gravacoes}
    for s in regras.agrupar_sessoes([_como_item(g, blocos) for g in gravacoes]):
        if s["sessao_id"] == sessao_id:
            s["_modelos"] = [por_id[i["recording_id"]] for i in s["gravacoes"]]
            return s
    raise GravacaoErro(404, "Gravação não encontrada.")


def _transcricao(session: Session, meeting_id: str, inicio: datetime, fim: datetime) -> dict:
    candidatas = session.exec(select(MeetingMemory).where(or_(
        MeetingMemory.meeting_id == meeting_id, MeetingMemory.meeting_id.like(meeting_id + "#%")))).all()
    m = regras.escolher_memoria(
        [{"meeting_id": c.meeting_id, "created_at": c.created_at, "updated_at": c.updated_at, "_row": c}
         for c in candidatas], inicio - timedelta(minutes=10), fim + timedelta(minutes=10))
    if not m:
        return {"disponivel": False, "texto": "", "fonte": None}
    row = m["_row"]
    return {"disponivel": True, "texto": row.transcript_full or "", "fonte": row.meeting_id,
            "inicio": _iso(row.created_at), "fim": _iso(row.updated_at),
            "observacao": "Legenda do Meet + áudio, sem horário por fala (o sincronismo vem com a T03)."}


def detalhe_sessao(usuario_id: str, admin: bool, sessao_id: str) -> dict:
    with Session(database.engine) as session:
        s = _sessao_da_pessoa(session, usuario_id, admin, sessao_id)
        # Relógio da sessão: o da extensão (start_ms dos blocos), igual nas 2 trilhas.
        com_relogio = [g["inicio_ms"] for g in s["gravacoes"] if g["inicio_ms"] is not None]
        zero_ms = min(com_relogio) if com_relogio else None
        trilhas: dict = {}
        for item, modelo in zip(s["gravacoes"], s["_modelos"]):
            niveis, duracao_audio = _niveis(session, modelo)
            if item["inicio_ms"] is not None and zero_ms is not None:
                offset = (item["inicio_ms"] - zero_ms) / 1000
            else:
                offset = (item["inicio"] - s["inicio"]).total_seconds()
            relogio = (item["fim_ms"] - item["inicio_ms"]) / 1000 if item["inicio_ms"] is not None else 0
            trilhas.setdefault(item["track_id"], []).append({
                "recording_id": item["recording_id"], "offset_s": round(offset, 2),
                "duracao_s": duracao_audio if duracao_audio else round(relogio, 2),
                "duracao_relogio_s": round(relogio, 2), "status": item["status"],
                "integridade": item["integridade"], "integridade_detalhe": item["integridade_detalhe"],
                "lacunas": item["lacunas"], "blocos": item["blocos"], "bytes": item["bytes"],
                "janela_s": regras.JANELA_NIVEL_S, "niveis": niveis,
                "som": regras.resumir_niveis([n for n in niveis if n is not None]),
                "apagar_em": _iso(item["apagar_em"]),
            })
        for lista in trilhas.values():
            lista.sort(key=lambda x: x["offset_s"])
        duracao_total = max([seg["offset_s"] + (seg["duracao_s"] or 0) for lista in trilhas.values() for seg in lista] or [0])
        transcricao = _transcricao(session, s["meeting_id"], s["inicio"], s["fim"])
        refs = [_ref_dict(r) for r in session.exec(select(GravacaoReferencia).where(
            GravacaoReferencia.sessao_id == sessao_id).order_by(GravacaoReferencia.inicio_s)).all()]
    donos = sorted({g["usuario_id"] for g in s["gravacoes"]})
    nomes = _nomes(donos + [r["usuario_id"] for r in refs])
    for r in refs:
        r["autor"] = (nomes.get(r["usuario_id"]) or {}).get("nome") or r["usuario_id"]
    return {
        "sessao_id": sessao_id, "meeting_id": s["meeting_id"], "inicio": _iso(s["inicio"]), "fim": _iso(s["fim"]),
        "inicio_relogio_ms": zero_ms, "duracao_total_s": round(duracao_total, 2),
        "vendedores": [(nomes.get(u) or {}).get("nome") or u for u in donos],
        "trilhas": trilhas, "transcricao": transcricao,
        "referencias": refs, "revisao": regras.resumir_referencias(refs),
    }


# ── Fase 2: trechos de referência ───────────────────────────────────────

def _ref_dict(r: GravacaoReferencia) -> dict:
    return {
        "id": r.id, "sessao_id": r.sessao_id, "usuario_id": r.usuario_id, "trilha": r.trilha,
        "inicio_s": r.inicio_s, "fim_s": r.fim_s, "texto_sistema": r.texto_sistema,
        "texto_referencia": r.texto_referencia, "observacao": r.observacao, "wer": r.wer,
        "erros": r.erros, "substituicoes": r.substituicoes, "delecoes": r.delecoes, "insercoes": r.insercoes,
        "referencia_palavras": r.palavras_referencia,
        "criado_em": _iso(r.criado_em), "atualizado_em": _iso(r.atualizado_em),
    }


def _aplicar_medicao(r: GravacaoReferencia, dados: dict) -> None:
    erros = regras.validar_referencia(dados.get("inicio_s"), dados.get("fim_s"), dados.get("trilha"),
                                      dados.get("texto_referencia"), dados.get("texto_sistema") or "")
    if erros:
        raise GravacaoErro(400, "; ".join(erros))
    m = regras.medir_trecho(dados["texto_referencia"], dados.get("texto_sistema") or "")
    r.trilha = dados["trilha"]
    r.inicio_s, r.fim_s = float(dados["inicio_s"]), float(dados["fim_s"])
    r.texto_sistema = dados.get("texto_sistema") or ""
    r.texto_referencia = dados["texto_referencia"]
    r.observacao = (dados.get("observacao") or "")[:2000]
    r.wer, r.erros = m["wer"], m["erros"]
    r.substituicoes, r.delecoes, r.insercoes = m["substitutions"], m["deletions"], m["insertions"]
    r.palavras_referencia = m["referencia_palavras"]
    r.atualizado_em = datetime.now()


def criar_referencia(usuario_id: str, admin: bool, sessao_id: str, dados: dict) -> dict:
    with Session(database.engine) as session:
        s = _sessao_da_pessoa(session, usuario_id, admin, sessao_id)
        r = GravacaoReferencia(sessao_id=sessao_id, meeting_id=s["meeting_id"], usuario_id=usuario_id,
                               trilha="ambas", inicio_s=0, fim_s=0, texto_referencia="")
        _aplicar_medicao(r, dados)
        session.add(r)
        session.commit()
        session.refresh(r)
        logger.info("[Gravacao] referência %s na sessão %s: wer=%s (%s palavras)", r.id, sessao_id, r.wer,
                    r.palavras_referencia)
        return _ref_dict(r)


def _referencia_da_pessoa(session: Session, usuario_id: str, admin: bool, ref_id: int) -> GravacaoReferencia:
    r = session.get(GravacaoReferencia, ref_id)
    if not r:
        raise GravacaoErro(404, "Trecho não encontrado.")
    _sessao_da_pessoa(session, usuario_id, admin, r.sessao_id)  # precisa enxergar a sessão
    if r.usuario_id != usuario_id and not admin:
        raise GravacaoErro(403, "Só quem criou o trecho (ou um admin) pode alterá-lo.")
    return r


def atualizar_referencia(usuario_id: str, admin: bool, ref_id: int, dados: dict) -> dict:
    with Session(database.engine) as session:
        r = _referencia_da_pessoa(session, usuario_id, admin, ref_id)
        _aplicar_medicao(r, dados)
        session.add(r)
        session.commit()
        session.refresh(r)
        return _ref_dict(r)


def apagar_referencia(usuario_id: str, admin: bool, ref_id: int) -> dict:
    with Session(database.engine) as session:
        r = _referencia_da_pessoa(session, usuario_id, admin, ref_id)
        session.delete(r)
        session.commit()
    return {"ok": True}
