"""Tarefa A7 de docs/tasks-prompt-mestre-v2-restante.md — extrator de
SalesEvent (Fase 1.1) via IA. Até aqui `criar_sales_event()` nunca era
chamada e `event_precision` (Fase 25) era gap: não havia extrator para
comparar com o `expected_events` do Golden Dataset.

Mesmo padrão de `agent/spin_extractor.py`/`agent/meddpicc_extractor.py`:
- vocabulário fechado nos 14 tipos de `sales_event_rules.SALES_EVENT_TYPES`
  (a IA nunca inventa tipo);
- **guarda contra citação fabricada**: `evidence_quote` precisa existir
  literalmente na conversa (substring) — evento sem lastro é descartado;
- dedup por `(tipo, citação)` dentro da resposta.

Decisão de escopo: **uma IA para os 14 tipos**, em vez de derivar parte
deles das saídas da A2/A5 (SPIN, objeções, MEDDPICC). O gabarito também
espera eventos ditos na conversa que nenhum extrator cobre
(`BUYING_SIGNAL`, `DEAL_WON`, `DEAL_LOST`, `NEXT_STEP_AGREED`...), e
derivar metade dos tipos em produção faria o `event_precision` do
Golden Dataset medir um pipeline diferente do que roda de verdade.

Kill-switch `SALES_EVENT_EXTRACTOR_ENABLED` (default `true`): +1
chamada de IA por ciclo nos caminhos Shadow/Piloto.
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

from agent.multiagente.claude_fallback import chamar_ia_com_fallback_claude
from agent.sales_event_rules import SALES_EVENT_TYPES
from api import ai_features

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompt_templates" / "sales_event_extractor.txt"

_SYSTEM_PROMPT = (
    "Você identifica eventos de venda em conversas comerciais reais. "
    "Responda SEMPRE em JSON válido, sem texto antes ou depois."
)


def sales_event_extractor_ativo() -> bool:
    return os.getenv("SALES_EVENT_EXTRACTOR_ENABLED", "true").strip().lower() != "false"


def _norm(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip().lower()


def _evento_valido(evento, texto_completo: str) -> bool:
    if not isinstance(evento, dict) or evento.get("event_type") not in SALES_EVENT_TYPES:
        return False
    try:
        confidence = float(evento.get("confidence"))
    except (TypeError, ValueError):
        return False
    if not 0.0 <= confidence <= 1.0:
        return False
    citacao = evento.get("evidence_quote")
    if not isinstance(citacao, str) or not citacao.strip():
        return False
    return citacao.strip() in texto_completo


async def extrair_sales_events_async(
    transcricao_parcial: str,
    historico: str,
    usuario_id: Optional[str] = None,
    meeting_id: Optional[str] = None,
) -> list:
    """Eventos validados — **sempre lista** em sucesso (vazia é
    informação real). Cada um: `{"event_type", "confidence",
    "evidence_quote"}`. Propaga falha real de IA (o chamador trata como
    melhor esforço)."""
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    prompt = template.replace("{historico}", historico or "").replace("{transcricao_parcial}", transcricao_parcial or "")

    resposta = await chamar_ia_com_fallback_claude(
        _SYSTEM_PROMPT, prompt, usuario_id,
        feature=ai_features.SALES_EVENT_EXTRACAO, meeting_id=meeting_id,
    )
    brutos = (resposta or {}).get("eventos") if isinstance(resposta, dict) else None
    texto_completo = f"{historico or ''}\n{transcricao_parcial or ''}"

    eventos, vistos = [], set()
    for evento in brutos or []:
        if not _evento_valido(evento, texto_completo):
            continue
        chave = (evento["event_type"], _norm(evento["evidence_quote"]))
        if chave in vistos:
            continue
        vistos.add(chave)
        eventos.append({
            "event_type": evento["event_type"],
            "confidence": float(evento["confidence"]),
            "evidence_quote": evento["evidence_quote"].strip(),
        })
    return eventos


def persistir_sales_events_do_ciclo(
    meeting_id: Optional[str],
    eventos: Optional[list],
    opportunity_id: Optional[int] = None,
    seller_id: Optional[str] = None,
) -> int:
    """Grava os eventos novos da reunião como `SalesEvent`
    (`source="conversation"`). Dedup entre ciclos por `(tipo, citação
    normalizada)` contra o que já existe na reunião — a transcrição é
    acumulada e o mesmo evento reaparece a cada 60s. Reunião anônima
    nunca grava. Evento inválido é pulado; erro de banco propaga (o
    orquestrador isola)."""
    if not meeting_id or meeting_id == "default" or not eventos:
        return 0
    from api.database import criar_sales_event, listar_sales_events

    existentes = {
        (e["event_type"], _norm(e.get("evidence_quote")))
        for e in listar_sales_events(meeting_id=meeting_id, limit=10000)
    }
    criados = 0
    for evento in eventos:
        chave = (evento.get("event_type"), _norm(evento.get("evidence_quote")))
        if chave in existentes:
            continue
        try:
            criar_sales_event(
                meeting_id=meeting_id, event_type=evento["event_type"], source="conversation",
                confidence=evento["confidence"], evidence_quote=evento["evidence_quote"],
                opportunity_id=opportunity_id, seller_id=seller_id,
            )
        except (ValueError, KeyError) as e:
            logger.debug("[SalesEvent] Evento inválido pulado: %s", e)
            continue
        existentes.add(chave)
        criados += 1
    return criados


def contar_precisao_eventos(previstos: list, esperados: list) -> tuple[int, int, int]:
    """Função pura para o Golden Dataset: `(vp, fp, fn)` por **tipo** de
    evento num cenário. Previsto cujo tipo está entre os esperados = VP;
    fora = FP; esperado nunca previsto = FN (para o recall, informativo —
    o critério da Fase 25 é precisão)."""
    tipos_previstos = {e.get("event_type") for e in previstos or [] if isinstance(e, dict)}
    tipos_esperados = {t for t in esperados or [] if isinstance(t, str)}
    vp = len(tipos_previstos & tipos_esperados)
    fp = len(tipos_previstos - tipos_esperados)
    fn = len(tipos_esperados - tipos_previstos)
    return vp, fp, fn
