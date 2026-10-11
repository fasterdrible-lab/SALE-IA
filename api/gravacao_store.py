"""Armazenamento da gravação contínua do áudio (T02).

Blocos ficam em disco (`GRAVACAO_DIR`, padrão `data/gravacoes/`) em
`<reunião>/<trilha>/<recording_id>/<sequence>-<hash>.webm` e no banco
(`gravacoes_blocos`, único por recording_id + sequence). O nome com o
hash impede que dois workers sobrescrevam o arquivo um do outro; quem
perde a corrida no banco apaga o próprio arquivo.

Regras puras (validação, caminho, lacunas): `agent/gravacao_rules.py`.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from agent import gravacao_rules as regras
from api import database
from api.database import GravacaoAudio, GravacaoBloco

logger = logging.getLogger("saleia.gravacao")

ABANDONO_SEM_BLOCO = timedelta(minutes=30)


class GravacaoErro(Exception):
    def __init__(self, status: int, mensagem: str):
        super().__init__(mensagem)
        self.status = status
        self.mensagem = mensagem


def raiz() -> Path:
    return Path(os.getenv("GRAVACAO_DIR") or "data/gravacoes")


def _dict(g: GravacaoAudio) -> dict:
    return {
        "recording_id": g.recording_id,
        "meeting_id": g.meeting_id,
        "track_id": g.track_id,
        "status": g.status,
        "codec": g.codec,
        "sample_rate": g.sample_rate,
        "iniciada_em": g.iniciada_em.isoformat() if g.iniciada_em else None,
        "encerrada_em": g.encerrada_em.isoformat() if g.encerrada_em else None,
        "lacunas": json.loads(g.lacunas_json or "[]"),
        "integridade": g.integridade,
        "integridade_detalhe": g.integridade_detalhe,
        "duracao_s": g.duracao_s,
        "apagar_em": g.apagar_em.isoformat() if g.apagar_em else None,
    }


def _da_pessoa(session: Session, recording_id: str, usuario_id: str, admin: bool = False) -> GravacaoAudio:
    g = session.exec(select(GravacaoAudio).where(GravacaoAudio.recording_id == recording_id)).first()
    # 404 também para gravação de outra pessoa: não confirma que existe.
    if not g or (g.usuario_id != usuario_id and not admin):
        raise GravacaoErro(404, "Gravação não encontrada.")
    return g


def iniciar_gravacao(usuario_id: str, meeting_id: str, track_id: str, recording_id: str,
                     codec: str = "", sample_rate: Optional[int] = None,
                     consentimento: bool = False, agora: Optional[datetime] = None) -> dict:
    """Idempotente por recording_id (a extensão reenvia depois de queda)."""
    erros = regras.validar_inicio(meeting_id, track_id, recording_id, consentimento)
    if erros:
        raise GravacaoErro(400, "; ".join(erros))
    agora = agora or datetime.now()
    retencao = regras.configuracao()["retencao_dias"]
    for _ in range(2):
        with Session(database.engine) as session:
            existente = session.exec(select(GravacaoAudio).where(GravacaoAudio.recording_id == recording_id)).first()
            if existente:
                if existente.usuario_id != usuario_id:
                    raise GravacaoErro(404, "Gravação não encontrada.")
                return {**_dict(existente), "ja_existia": True}
            g = GravacaoAudio(
                recording_id=recording_id, meeting_id=meeting_id, track_id=track_id,
                usuario_id=usuario_id, codec=(codec or "")[:80], sample_rate=sample_rate,
                consentimento_texto=regras.TEXTO_CONSENTIMENTO, consentimento_em=agora,
                iniciada_em=agora, apagar_em=regras.data_para_apagar(agora, retencao),
            )
            session.add(g)
            try:
                session.commit()
            except IntegrityError:  # o outro worker criou ao mesmo tempo
                session.rollback()
                continue
            session.refresh(g)
            logger.info("[Gravacao] iniciada %s meeting=%s trilha=%s", recording_id, meeting_id, track_id)
            return {**_dict(g), "ja_existia": False}
    raise GravacaoErro(409, "Conflito ao criar a gravação.")


def receber_bloco(usuario_id: str, recording_id: str, sequence: int, start_ms: int, end_ms: int,
                  content_hash: str, dados: bytes, recorded_at: Optional[datetime] = None) -> dict:
    erros = regras.validar_bloco(sequence, start_ms, end_ms, content_hash, dados)
    if erros:
        raise GravacaoErro(400, "; ".join(erros))
    with Session(database.engine) as session:
        g = _da_pessoa(session, recording_id, usuario_id)
        if g.status != "gravando":
            raise GravacaoErro(409, "Gravação já encerrada.")
        existente = session.exec(select(GravacaoBloco).where(
            GravacaoBloco.recording_id == recording_id, GravacaoBloco.sequence == sequence)).first()
        if existente:
            if existente.content_hash != content_hash:
                raise GravacaoErro(409, f"Bloco {sequence} já recebido com outro conteúdo.")
            return {"recording_id": recording_id, "sequence": sequence, "duplicado": True}

        base = regras.caminho_do_bloco(raiz(), g.meeting_id, g.track_id, recording_id, sequence)
        caminho = base.with_name(f"{base.stem}-{content_hash[:12]}.webm")
        caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = caminho.with_name(f".{caminho.name}.{uuid.uuid4().hex}.tmp")
        tmp.write_bytes(dados)
        os.replace(tmp, caminho)  # atômico: nunca fica meio arquivo com o nome final

        session.add(GravacaoBloco(
            recording_id=recording_id, sequence=sequence, start_ms=start_ms, end_ms=end_ms,
            content_hash=content_hash, tamanho=len(dados), caminho=str(caminho), recorded_at=recorded_at,
        ))
        try:
            session.commit()
        except IntegrityError:  # outro worker gravou a mesma sequência agora
            session.rollback()
            vencedor = session.exec(select(GravacaoBloco).where(
                GravacaoBloco.recording_id == recording_id, GravacaoBloco.sequence == sequence)).first()
            if vencedor and vencedor.content_hash == content_hash:
                return {"recording_id": recording_id, "sequence": sequence, "duplicado": True}
            caminho.unlink(missing_ok=True)
            raise GravacaoErro(409, f"Bloco {sequence} já recebido com outro conteúdo.")
    return {"recording_id": recording_id, "sequence": sequence, "duplicado": False}


def _blocos_em_ordem(session: Session, recording_id: str) -> list:
    return list(session.exec(select(GravacaoBloco).where(GravacaoBloco.recording_id == recording_id)
                             .order_by(GravacaoBloco.sequence)).all())


def montar_audio(blocos: list) -> bytes:
    return b"".join(Path(b.caminho).read_bytes() for b in blocos)


def verificar_integridade(dados: bytes) -> tuple:
    """(ok, duracao_s, sample_rate, detalhe) decodificando todo o áudio com
    PyAV (as mesmas bibliotecas do FFmpeg que o faster-whisper usa)."""
    if not dados:
        return False, None, None, "sem áudio"
    import av

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(dados)
        caminho = f.name
    try:
        with av.open(caminho) as arquivo:
            if not arquivo.streams.audio:
                return False, None, None, "arquivo sem trilha de áudio"
            stream = arquivo.streams.audio[0]
            amostras, taxa = 0, None
            for frame in arquivo.decode(stream):
                amostras += frame.samples
                taxa = frame.sample_rate
        if not amostras or not taxa:
            return False, None, None, "nenhuma amostra decodificada"
        return True, round(amostras / taxa, 3), taxa, ""
    except Exception as e:
        return False, None, None, f"falha ao decodificar: {str(e)[:300]}"
    finally:
        os.unlink(caminho)


def encerrar_gravacao(usuario_id: str, recording_id: str, ultima_sequence: Optional[int] = None,
                      admin: bool = False, agora: Optional[datetime] = None) -> dict:
    """Fecha a gravação, registra as lacunas e confere se o áudio toca.
    Idempotente: encerrar de novo devolve o mesmo resultado."""
    with Session(database.engine) as session:
        g = _da_pessoa(session, recording_id, usuario_id, admin=admin)
        if g.status != "gravando":
            return _dict(g)
        blocos = _blocos_em_ordem(session, recording_id)
        faltam = regras.lacunas([b.sequence for b in blocos], ultima_sequence)
        if blocos and 0 in faltam:
            ok, duracao, taxa, detalhe = False, None, None, "falta o bloco 0 (cabeçalho do áudio)"
        else:
            ok, duracao, taxa, detalhe = verificar_integridade(montar_audio(blocos))
            if ok and faltam:
                detalhe = f"áudio toca, mas faltam {len(faltam)} bloco(s)"
        g.status = "encerrada"
        g.encerrada_em = agora or datetime.now()
        g.ultima_sequence_declarada = ultima_sequence
        g.lacunas_json = json.dumps(faltam)
        g.integridade = "ok" if ok and not faltam else "erro"
        g.integridade_detalhe = detalhe
        g.duracao_s = duracao
        if taxa:
            g.sample_rate = taxa
        session.add(g)
        session.commit()
        session.refresh(g)
        logger.info("[Gravacao] encerrada %s blocos=%s lacunas=%s integridade=%s", recording_id,
                    len(blocos), len(faltam), g.integridade)
        return _dict(g)


def audio_da_gravacao(usuario_id: str, recording_id: str, admin: bool = False) -> bytes:
    with Session(database.engine) as session:
        g = _da_pessoa(session, recording_id, usuario_id, admin=admin)
        if g.status == "apagada":
            raise GravacaoErro(410, "Gravação apagada pela política de retenção.")
        return montar_audio(_blocos_em_ordem(session, recording_id))


def manutencao(agora: Optional[datetime] = None) -> dict:
    """Roda 1x/h: encerra gravação abandonada (extensão fechada sem
    encerrar) e apaga as vencidas (retenção)."""
    agora = agora or datetime.now()
    encerradas = apagadas = 0
    with Session(database.engine) as session:
        abertas = session.exec(select(GravacaoAudio).where(GravacaoAudio.status == "gravando")).all()
        ids_abandonados = []
        for g in abertas:
            ultimo = session.exec(select(GravacaoBloco.recebido_em).where(GravacaoBloco.recording_id == g.recording_id)
                                  .order_by(GravacaoBloco.recebido_em.desc())).first()
            if (ultimo or g.iniciada_em) < agora - ABANDONO_SEM_BLOCO:
                ids_abandonados.append((g.usuario_id, g.recording_id))
        vencidas = session.exec(select(GravacaoAudio).where(
            GravacaoAudio.apagar_em < agora, GravacaoAudio.status != "apagada")).all()
        for g in vencidas:
            shutil.rmtree(raiz() / g.meeting_id / g.track_id / g.recording_id, ignore_errors=True)
            for b in session.exec(select(GravacaoBloco).where(GravacaoBloco.recording_id == g.recording_id)).all():
                session.delete(b)
            g.status = "apagada"
            session.add(g)
            apagadas += 1
        session.commit()
    for usuario_id, recording_id in ids_abandonados:
        try:
            encerrar_gravacao(usuario_id, recording_id, None, agora=agora)
            encerradas += 1
        except Exception as e:
            logger.warning("[Gravacao] não encerrou %s: %s", recording_id, e)
    if encerradas or apagadas:
        logger.info("[Gravacao] manutenção: %s encerrada(s) por abandono, %s apagada(s)", encerradas, apagadas)
    return {"encerradas_por_abandono": encerradas, "apagadas": apagadas}
