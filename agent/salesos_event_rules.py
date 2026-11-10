"""Envio da reunião analisada ao SalesOS (tarefa V2-7.2 do SalesOS).

Contrato: `docs/INTEGRACAO_SALEIA.md` no repositório do SalesOS (evento
`meeting.analyzed`, versão 1). O SalesOS é a fonte de verdade comercial: o
evento só informa e sugere, nada muda lá sem uma pessoa.

Tudo vem do relatório pós-reunião automático (V.1.4.185) já gerado — nenhuma
chamada de IA a mais. Funções puras: zero IA, zero banco, zero rede.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

from agent.auto_opportunity_rules import extrair_cliente_identificado
from agent.opportunity_memory_writer_rules import montar_proximos_passos

# Limites do contrato (o SalesOS recusa com 400 acima disso).
MAX_TITULO = 200
MAX_RESUMO = 20_000
MAX_TEXTO = 2_000
MAX_INSIGHTS = 50
MAX_PARTICIPANTES = 50
MAX_BYTES = 256 * 1024

STATUS_ANTERIOR = "anterior"    # sessões que já existiam antes do recurso
STATUS_ENVIANDO = "enviando"
STATUS_OK = "ok"
STATUS_ERRO = "erro"            # vale reenviar (rede ou 5xx)
STATUS_RECUSADO = "recusado"    # 400/401: reenviar não adianta
STATUS_PULADO = "pulado"        # relatório sem resumo

# Espera antes de cada reenvio, pelo número de tentativas já feitas.
ESPERAS = (timedelta(minutes=5), timedelta(minutes=30), timedelta(hours=2), timedelta(hours=6))
MAX_TENTATIVAS = len(ESPERAS) + 1

# Etapa sugerida: palavras dos próximos passos → nome da etapa no funil
# padrão do SalesOS. Só sugestão; a pessoa decide lá. A mais avançada vence.
_ETAPAS_POR_PALAVRA = (
    ("Negociação", re.compile(r"\b(contrato|assinatura|assinar|fechamento|fechar|negocia\w*)\b", re.I)),
    ("Proposta", re.compile(r"\bproposta\w*\b", re.I)),
)


def configuracao(env: dict | None = None) -> tuple[str, str] | None:
    """(url, segredo) ou None: sem os dois no .env, o envio fica desligado."""
    env = os.environ if env is None else env
    url = str(env.get("SALESOS_EVENTS_URL") or "").strip()
    segredo = str(env.get("SALESOS_EVENTS_SECRET") or "").strip()
    if not url.startswith("https://") and not url.startswith("http://localhost"):
        return None
    return (url, segredo) if segredo else None


def assinar(segredo: str, timestamp: str, corpo: str) -> str:
    digest = hmac.new(segredo.encode(), f"{timestamp}.{corpo}".encode(), hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def cabecalhos(segredo: str, corpo: str, agora: datetime) -> dict:
    timestamp = str(int(agora.replace(tzinfo=agora.tzinfo or timezone.utc).timestamp()))
    return {
        "Content-Type": "application/json",
        "X-Saleia-Timestamp": timestamp,
        "X-Saleia-Signature": assinar(segredo, timestamp, corpo),
    }


def _texto(valor, limite: int = MAX_TEXTO) -> str:
    return " ".join(str(valor or "").split())[:limite]


def _lista(valor) -> list:
    return valor if isinstance(valor, list) else []


def _dict(valor) -> dict:
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except (ValueError, TypeError):
            return {}
    return valor if isinstance(valor, dict) else {}


def _iso_utc(momento: datetime) -> str:
    """Datas do SALE-IA são UTC sem fuso (NOW() do MySQL na VPS)."""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def montar_resumo(recap: dict) -> str:
    partes = [_texto(recap.get("resumo_executivo"), MAX_RESUMO)]
    propensao = _dict(recap.get("propensao"))
    if _texto(propensao.get("nivel")) and propensao.get("nivel") != "nao_determinada":
        partes.append(f"Propensão de compra: {_texto(propensao.get('nivel'))}. {_texto(propensao.get('resumo'))}".strip())
    if _texto(recap.get("probabilidade_fechamento")):
        partes.append(
            f"Probabilidade de fechamento: {_texto(recap.get('probabilidade_fechamento'))}. "
            f"{_texto(recap.get('justificativa_probabilidade'))}".strip()
        )
    return "\n\n".join(p for p in partes if p)[:MAX_RESUMO]


def sugerir_etapa(passos: list[str]) -> dict | None:
    for etapa, padrao in _ETAPAS_POR_PALAVRA:
        for passo in passos:
            if padrao.search(passo):
                return {"kind": "STAGE_SUGGESTION", "text": f"Próximo passo combinado: {passo}"[:MAX_TEXTO], "stageName": etapa}
    return None


def montar_insights(recap: dict) -> list[dict]:
    estrategica = _dict(recap.get("recapitulacao_estrategica"))
    propensao = _dict(recap.get("propensao"))
    passos = montar_proximos_passos(recap)

    insights: list[dict] = [{"kind": "RECOMMENDATION", "text": _texto(p)} for p in passos]
    insights += [{"kind": "RECOMMENDATION", "text": _texto(a)} for a in _lista(propensao.get("como_avancar"))]
    etapa = sugerir_etapa(passos)
    if etapa:
        insights.append(etapa)
    insights += [{"kind": "OBJECTION", "text": _texto(o)} for o in _lista(estrategica.get("objecoes_levantadas"))]
    insights += [{"kind": "PAIN", "text": _texto(d)} for d in _lista(estrategica.get("dores_identificadas"))]
    for kind, chave, prefixo in (("BUYING_SIGNAL", "fatores_positivos", ""), ("EVIDENCE", "fatores_negativos", "Atenção: ")):
        for fator in _lista(propensao.get(chave)):
            fator = _dict(fator) if not isinstance(fator, str) else {"fator": fator}
            texto = _texto(fator.get("fator"))
            if texto:
                item = {"kind": kind, "text": _texto(prefixo + texto)}
                if _texto(fator.get("evidencia")):
                    item["quote"] = _texto(fator.get("evidencia"))
                insights.append(item)

    vistos, unicos = set(), []
    for item in insights:
        chave = (item["kind"], item["text"].lower())
        if item["text"] and chave not in vistos:
            vistos.add(chave)
            unicos.append(item)
    return unicos[:MAX_INSIGHTS]


# Texto de exemplo do schema de "oferta" no PROMPT_RECAPITULACAO, caso a IA o copie.
_MOTIVOS_PLACEHOLDER = {"motivo ou null", "null", "none", "n/a", "-", "nao informado", "não informado"}


def montar_oferta(recap: dict) -> dict | None:
    """`offer` do contrato (V2-8.2 do SalesOS), ou None quando não deu para avaliar.

    Só um booleano de verdade conta: "true", "sim" ou o texto do schema
    copiado pela IA viram None (reunião "não avaliada" no SalesOS).
    """
    oferta = _dict(recap.get("oferta"))
    apresentada = oferta.get("apresentada")
    if not isinstance(apresentada, bool):
        return None
    if apresentada:
        return {"presented": True, "reason": None}
    motivo = _texto(oferta.get("motivo_nao_apresentada"))
    if motivo.lower() in _MOTIVOS_PLACEHOLDER or len(motivo) < 2:
        motivo = ""
    return {"presented": False, "reason": motivo or None}


def montar_evento(
    *,
    meeting_id: str,
    titulo: str,
    inicio: datetime | None,
    fim: datetime | None,
    participantes: list[dict],
    relatorio: dict,
    agora: datetime,
    event_id: str | None = None,
) -> dict | None:
    """Evento `meeting.analyzed` v1, ou None quando o relatório não tem resumo."""
    recap = _dict(relatorio.get("recapitulacao"))
    resumo = montar_resumo(recap)
    if not resumo:
        return None

    cliente = extrair_cliente_identificado(recap) or {}
    quem = cliente.get("empresa") or cliente.get("nome")
    duracao = None
    if inicio and fim and fim >= inicio:
        duracao = min(int((fim - inicio).total_seconds() // 60), 24 * 60)

    return {
        "version": 1,
        "event": "meeting.analyzed",
        "eventId": event_id or str(uuid.uuid4()),
        "occurredAt": _iso_utc(agora),
        "meeting": {
            "externalId": _texto(meeting_id, 100),
            "title": _texto(f"Reunião com {quem}" if quem else titulo, MAX_TITULO) or "Reunião",
            "startedAt": _iso_utc(inicio or agora),
            "durationMinutes": duracao,
            # O SALE-IA não guarda e-mail dos participantes: o vínculo no SalesOS
            # vem do nome da empresa (links.companyName).
            "participants": [
                {"name": _texto(p.get("nome"), 160)}
                for p in participantes[:MAX_PARTICIPANTES]
                if _texto(p.get("nome"))
            ],
            "summary": resumo,
        },
        "links": {"opportunityId": None, "companyName": cliente.get("empresa")},
        "insights": montar_insights(recap),
        "offer": montar_oferta(recap),
    }


def serializar(evento: dict) -> str | None:
    """Corpo exato que será assinado. None se passar do limite do contrato."""
    corpo = json.dumps(evento, ensure_ascii=False, separators=(",", ":"))
    return corpo if len(corpo.encode()) <= MAX_BYTES else None


def classificar_resposta(status: int | None) -> str:
    """Rede/5xx: tentar de novo. 400/401 e outros 4xx: não adianta."""
    if status is not None and 200 <= status < 300:
        return STATUS_OK
    if status is None or status >= 500 or status == 429:
        return STATUS_ERRO
    return STATUS_RECUSADO


def pode_reenviar(tentativas: int, ultima: datetime | None, agora: datetime) -> bool:
    if tentativas <= 0:
        return True
    if tentativas >= MAX_TENTATIVAS:
        return False
    return ultima is None or agora - ultima >= ESPERAS[tentativas - 1]
