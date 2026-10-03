"""
SALEIA — agent/sales_evidence_persist_rules.py

Tarefa A2 de docs/tasks-prompt-mestre-v2-restante.md — persistir
SalesEvidence (Fase 1 / Tarefa 1.2, `criar_sales_evidence()` nunca
chamada até aqui) a partir dos extratores que já rodam no ciclo de tempo
real. Zero IA nova: só reaproveita o que os extratores já produzem e
descartavam no fim do ciclo.

Fontes (todas com `evidence_quote` já checada literalmente contra a
conversa pelo próprio extrator):
- `spin_state` (Bloco 4.1, `agent/spin_extractor.py`) → `SPIN_<STAGE>:<campo>`
- `behavioral_signals` (Bloco 4.2) → `BEHAVIOR:<signal>`
- `buyer_motivation` (Bloco 4.3, hipótese dominante) → `MOTIVATION:<motivation>`,
  1 evidência por citação da lista `evidence`
- `objections` (Blocos 1.2 + 4.4) → `OBJECTION:<category>` (o que foi dito)
  e `ROOT_CAUSE:<hypothesis>` (causa raiz, quando houver) — sempre 2
  evidências separadas, nunca fundidas (mesma regra de objection_rules.py).
- `meddpicc_fatos` (A5, `agent/meddpicc_extractor.py`) → `MEDDPICC:<item>`,
  com a confidence do extrator.

**Deduplicação entre ciclos** (a mesma fala reaparece a cada 60s, porque
os extratores recebem a transcrição acumulada): chave `(type, citação
normalizada)` — espaços colapsados + minúsculas — comparada contra o que
já está gravado para a reunião e contra o próprio lote do ciclo.

`confidence`: usa a do extrator quando ele a produz (motivação, causa
raiz); SPIN/sinais/objeção falada não têm confidence própria — caem no
default do schema (`1.0`, mesma semântica de `criar_sales_evidence()`:
a citação existe literalmente na conversa). `speaker` fica `None`:
os rótulos de falante não são confiáveis (achado da A1 — Whisper do
microfone sempre "vendedor").

Kill-switch `SALES_EVIDENCE_PERSIST_ENABLED` (default `true`, zero custo
de IA) — `false` no `.env` + restart desliga sem reverter deploy.
"""

import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Limite da coluna `sales_evidences.type` (String(60)).
_TYPE_MAX_CHARS = 60

# Teto de leitura das evidências já gravadas por reunião para o dedup —
# folgado de propósito (listar_sales_evidences() usa 200 por padrão, uma
# reunião longa passaria disso e voltaria a duplicar).
_LIMITE_LEITURA_DEDUP = 10000


def sales_evidence_persist_ativo() -> bool:
    return os.getenv("SALES_EVIDENCE_PERSIST_ENABLED", "true").strip().lower() != "false"


def _normalizar_quote(quote: str) -> str:
    return re.sub(r"\s+", " ", quote or "").strip().lower()


def chave_dedup(tipo: str, quote: str) -> tuple:
    return (tipo, _normalizar_quote(quote))


def _tipo(prefixo: str, rotulo) -> Optional[str]:
    rotulo = str(rotulo or "").strip()
    if not rotulo:
        return None
    return f"{prefixo}:{rotulo}"[:_TYPE_MAX_CHARS]


def _item(tipo: Optional[str], quote, confidence=None) -> Optional[dict]:
    if not tipo or not isinstance(quote, str) or not quote.strip():
        return None
    item = {"type": tipo, "quote": quote.strip()}
    if confidence is not None:
        try:
            valor = float(confidence)
        except (TypeError, ValueError):
            return None
        if not (0.0 <= valor <= 1.0):
            return None
        item["confidence"] = valor
    return item


def coletar_evidencias(
    spin_state: Optional[dict] = None,
    behavioral_signals: Optional[list] = None,
    buyer_motivation: Optional[dict] = None,
    objections: Optional[list] = None,
    meddpicc_fatos: Optional[list] = None,
) -> list:
    """Função pura: converte a saída dos extratores do ciclo em
    `[{"type", "quote", "confidence"?}]`, já deduplicada dentro do
    próprio lote. Entrada ausente/malformada nunca levanta — só não gera
    evidência (os extratores são melhor esforço, qualquer um pode vir
    `None`)."""
    candidatos = []

    spin_state = spin_state if isinstance(spin_state, dict) else {}
    for stage, bloco in spin_state.items():
        if not isinstance(bloco, dict):
            continue
        for fato in bloco.get("known") or []:
            if isinstance(fato, dict):
                candidatos.append(_item(
                    _tipo(f"SPIN_{str(stage).upper()}", fato.get("campo")), fato.get("evidence_quote"),
                ))

    for sinal in behavioral_signals or []:
        if isinstance(sinal, dict):
            candidatos.append(_item(_tipo("BEHAVIOR", sinal.get("signal")), sinal.get("evidence_quote")))

    if isinstance(buyer_motivation, dict):
        tipo = _tipo("MOTIVATION", buyer_motivation.get("motivation"))
        for quote in buyer_motivation.get("evidence") or []:
            candidatos.append(_item(tipo, quote, buyer_motivation.get("confidence")))

    for objecao in objections or []:
        if not isinstance(objecao, dict):
            continue
        spoken = objecao.get("objection_spoken") or {}
        if isinstance(spoken, dict):
            candidatos.append(_item(_tipo("OBJECTION", spoken.get("category")), spoken.get("evidence_quote")))
        root = objecao.get("root_cause_hypothesis") or {}
        if isinstance(root, dict):
            candidatos.append(_item(
                _tipo("ROOT_CAUSE", root.get("hypothesis")), root.get("evidence_quote"), root.get("confidence"),
            ))

    # A5: fatos do extrator de MEDDPICC (`agent/meddpicc_extractor.py`).
    for fato in meddpicc_fatos or []:
        if isinstance(fato, dict):
            candidatos.append(_item(
                _tipo("MEDDPICC", fato.get("item")), fato.get("evidence_quote"), fato.get("confidence"),
            ))

    evidencias = []
    vistas = set()
    for item in candidatos:
        if not item:
            continue
        chave = chave_dedup(item["type"], item["quote"])
        if chave in vistas:
            continue
        vistas.add(chave)
        evidencias.append(item)
    return evidencias


def persistir_evidencias_do_ciclo(
    meeting_id: Optional[str],
    spin_state: Optional[dict] = None,
    behavioral_signals: Optional[list] = None,
    buyer_motivation: Optional[dict] = None,
    objections: Optional[list] = None,
    meddpicc_fatos: Optional[list] = None,
) -> int:
    """Grava as evidências novas do ciclo (as já gravadas para a reunião
    são puladas) e retorna quantas foram criadas. Reunião anônima
    (`meeting_id` ausente/`"default"`, mesmo padrão de
    `_rastrear_recomendacao()`) nunca grava nada.

    Melhor esforço por item: uma evidência que falhe a validação de
    `criar_sales_evidence()` é pulada e logada, nunca derruba as outras.
    Erro de banco na leitura do dedup propaga — o chamador (orquestrador)
    já isola isto em `try/except` e nunca deixa chegar ao vendedor."""
    if not meeting_id or meeting_id == "default" or not sales_evidence_persist_ativo():
        return 0

    evidencias = coletar_evidencias(spin_state, behavioral_signals, buyer_motivation, objections, meddpicc_fatos)
    if not evidencias:
        return 0

    from api.database import criar_sales_evidence, listar_sales_evidences

    existentes = {
        chave_dedup(e["type"], e["quote"])
        for e in listar_sales_evidences(meeting_id=meeting_id, limit=_LIMITE_LEITURA_DEDUP)
    }

    criadas = 0
    for item in evidencias:
        if chave_dedup(item["type"], item["quote"]) in existentes:
            continue
        try:
            criar_sales_evidence(meeting_id=meeting_id, source="conversation", **item)
            criadas += 1
        except ValueError as e:
            logger.debug("[SalesEvidence] Evidência inválida pulada (%s): %s", item.get("type"), e)
    return criadas
