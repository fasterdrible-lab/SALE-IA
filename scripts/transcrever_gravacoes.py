"""
scripts/transcrever_gravacoes.py — transcreve as gravações de reuniões já
encerradas pelo Groq e grava em `transcricao_definitiva`.

Processo próprio, um arquivo por vez, fora do uvicorn. Respeita a cota grátis
do Groq e pode ser interrompido: o que já foi feito não é repetido, e gravação
com erro volta a ser tentada na próxima execução. Vencimento mais próximo
primeiro. Só as reuniões pedidas; não muda a retenção nem apaga áudio.

Na VPS, de /opt/saleia:
    ./venv/bin/python3 -m scripts.transcrever_gravacoes --reunioes a,b --dry-run
    systemd-run --unit=saleia-transcricao -p Nice=19 -p WorkingDirectory=/opt/saleia \\
        ./venv/bin/python3 -m scripts.transcrever_gravacoes --reunioes a,b
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import func
from sqlmodel import Session, select

from agent.transcricao_definitiva_rules import eh_silencio, espera_por_cota, filtrar_segmentos
from api.database import GravacaoAudio, TranscricaoDefinitiva, engine
from api.gravacao_store import _blocos_em_ordem, montar_audio

logger = logging.getLogger("saleia.transcricao")

MODELO = "whisper-large-v3"
ESPERA_429_PADRAO_S = 600
ESPERA_429_MAX_S = 3600


def medir_pico_db(caminho: str) -> float | None:
    """Pico de volume do arquivo (dB), ou None se o ffmpeg não informar."""
    saida = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", caminho, "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, timeout=300, check=False,
    ).stderr
    achado = re.search(r"max_volume:\s*(-?[\d.]+|-inf) dB", saida)
    if not achado:
        return None
    return -999.0 if achado.group(1) == "-inf" else float(achado.group(1))


def _como_dict(segmento) -> dict:
    return segmento if isinstance(segmento, dict) else segmento.model_dump()


def transcrever_groq(caminho: str) -> list:
    """Segmentos crus do Whisper. Sem retentativa no SDK: o 429 volta para
    `processar`, que espera o tempo pedido pelo Groq."""
    from groq import Groq

    cliente = Groq(api_key=os.getenv("GROQ_API_KEY", ""), max_retries=0, timeout=180)
    with open(caminho, "rb") as f:
        resposta = cliente.audio.transcriptions.create(
            file=(Path(caminho).name, f.read()), model=MODELO, language="pt",
            temperature=0, response_format="verbose_json",
        )
    return [_como_dict(s) for s in (getattr(resposta, "segments", None) or [])]


def _espera_do_429(erro: Exception) -> int | None:
    """Segundos pedidos num 429, ou None se o erro não for de limite."""
    resposta = getattr(erro, "response", None)
    if getattr(resposta, "status_code", None) != 429:
        return None
    try:
        return min(ESPERA_429_MAX_S, max(30, int(float(resposta.headers.get("retry-after")))))
    except (TypeError, ValueError):
        return ESPERA_429_PADRAO_S


def pendentes(engine_, reunioes: list, agora: datetime) -> list:
    """Gravações íntegras ainda sem transcrição, vencimento mais próximo primeiro."""
    with Session(engine_) as s:
        feitas = set(s.exec(select(TranscricaoDefinitiva.recording_id).where(
            TranscricaoDefinitiva.status.in_(["ok", "silencio"]))).all())
        gravacoes = s.exec(
            select(GravacaoAudio)
            .where(GravacaoAudio.meeting_id.in_(reunioes), GravacaoAudio.status == "encerrada",
                   GravacaoAudio.integridade == "ok", GravacaoAudio.apagar_em > agora)
            .order_by(GravacaoAudio.apagar_em, GravacaoAudio.iniciada_em, GravacaoAudio.track_id)
        ).all()
    return [g for g in gravacoes if g.recording_id not in feitas]


def _usado_desde(engine_, desde: datetime) -> float:
    with Session(engine_) as s:
        return float(s.exec(select(func.coalesce(func.sum(TranscricaoDefinitiva.duracao_s), 0)).where(
            TranscricaoDefinitiva.status == "ok", TranscricaoDefinitiva.criada_em >= desde)).one())


def _salvar(engine_, g: GravacaoAudio, status: str, segmentos: list | None = None, detalhe: str = "") -> None:
    segmentos = segmentos or []
    with Session(engine_) as s:
        linha = s.exec(select(TranscricaoDefinitiva).where(
            TranscricaoDefinitiva.recording_id == g.recording_id)).first()
        if linha is None:
            linha = TranscricaoDefinitiva(recording_id=g.recording_id, meeting_id=g.meeting_id, trilha=g.track_id,
                                          inicio=g.iniciada_em, status=status)
        linha.fim = g.encerrada_em
        linha.texto = " ".join(x["texto"] for x in segmentos)
        linha.segmentos_json = json.dumps(segmentos, ensure_ascii=False)
        linha.status = status
        linha.detalhe = detalhe[:500]
        linha.modelo = MODELO if status == "ok" else ""
        linha.duracao_s = float(g.duracao_s or 0)
        linha.criada_em = datetime.now()
        s.add(linha)
        s.commit()


def _montar_arquivo(engine_, recording_id: str) -> str:
    with Session(engine_) as s:
        dados = montar_audio(_blocos_em_ordem(s, recording_id))
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(dados)
        return f.name


def processar(engine_, reunioes: list, transcrever=transcrever_groq, medir=medir_pico_db,
              montar=_montar_arquivo, dormir=time.sleep, agora=datetime.now) -> dict:
    """Passa uma vez por tudo que falta. Devolve a contagem por resultado."""
    contagem = {"ok": 0, "silencio": 0, "erro": 0}
    for g in pendentes(engine_, reunioes, agora()):
        duracao = float(g.duracao_s or 0)
        caminho = None
        try:
            caminho = montar(engine_, g.recording_id)
            if eh_silencio(medir(caminho)):
                _salvar(engine_, g, "silencio")
                contagem["silencio"] += 1
                continue
            while True:
                momento = agora()
                espera = espera_por_cota(_usado_desde(engine_, momento - timedelta(hours=1)),
                                         _usado_desde(engine_, momento - timedelta(days=1)), duracao)
                if espera:
                    dormir(espera)
                    continue
                try:
                    segmentos = filtrar_segmentos(transcrever(caminho))
                    break
                except Exception as e:  # noqa: BLE001 — classificado logo abaixo
                    espera = _espera_do_429(e)
                    if espera is None:
                        raise
                    logger.warning("limite do Groq: esperando %s s", espera)
                    dormir(espera)
            _salvar(engine_, g, "ok", segmentos)
            contagem["ok"] += 1
            logger.warning("%s %s %s: %s segmentos", g.meeting_id, g.track_id, g.recording_id[:8], len(segmentos))
        except Exception as e:  # noqa: BLE001 — uma gravação ruim não para as outras
            _salvar(engine_, g, "erro", detalhe=f"{type(e).__name__}: {e}")
            contagem["erro"] += 1
            logger.warning("%s %s %s: erro %s", g.meeting_id, g.track_id, g.recording_id[:8], type(e).__name__)
        finally:
            if caminho:
                Path(caminho).unlink(missing_ok=True)
    return contagem


def resumo_pendente(engine_, reunioes: list) -> dict:
    por_reuniao: dict = {}
    for g in pendentes(engine_, reunioes, datetime.now()):
        item = por_reuniao.setdefault(g.meeting_id, {"gravacoes": 0, "segundos": 0.0, "apagar_em": str(g.apagar_em)})
        item["gravacoes"] += 1
        item["segundos"] += float(g.duracao_s or 0)
    return por_reuniao


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reunioes", required=True, help="meeting_ids separados por vírgula")
    parser.add_argument("--dry-run", action="store_true", help="só mostra o que falta; não envia nada")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s")
    reunioes = [r.strip() for r in args.reunioes.split(",") if r.strip()]
    TranscricaoDefinitiva.__table__.create(engine, checkfirst=True)
    if args.dry_run:
        print(json.dumps(resumo_pendente(engine, reunioes), indent=2, ensure_ascii=False))
        return
    print(json.dumps(processar(engine, reunioes)))


if __name__ == "__main__":
    main()
