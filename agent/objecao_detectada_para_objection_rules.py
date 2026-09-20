"""Bloco 1 / Tarefa 1.2 + Bloco 4 / Tarefa 4.4 de docs/
tasks-sales-reasoning-engine-completo.md — traduz `resultado
["objecao_detectada"]` (Finance, calculado em todo ciclo de tempo
real) para o formato de `agent/objection_rules.py` (Fase 6.1),
alimentando o campo `objections` do SalesReasoningEngine (Fase 7) com
dado real em vez de sempre `None`.

`montar_objection_spoken()` é pura (sem IA/banco, testável sozinha).
`extrair_objecao_do_ciclo()` orquestra: chama `agent/
objection_category_classifier.py` pra obter a `category`, monta e
valida `objection_spoken`, depois chama `agent/
objection_root_cause_extractor.py` (Tarefa 4.4) usando a conversa
completa pra tentar uma hipótese de causa raiz real — e só então
registra via `agent/objection_rules.py::registrar_objecao()`.

Nunca fabrica categoria, evidência ou hipótese: sem objeção detectada
pelo Finance, sem classificação de categoria bem-sucedida, ou com
categoria fora do vocabulário fechado, o ciclo simplesmente não produz
fato nenhum (`None`) — mesma disciplina de honestidade do resto do
projeto. Falha na investigação de causa raiz (Tarefa 4.4) nunca derruba
a objeção inteira — `objection_spoken` sozinho já é dado estruturado
valioso; degrada pra `root_cause_hypothesis=None` (equivalente a
`precisa_investigar=True`, o comportamento seguro de sempre)."""

import logging
from typing import Optional

from agent.objection_rules import OBJECTION_TIPOS, registrar_objecao

logger = logging.getLogger(__name__)


def montar_objection_spoken(objecao_texto: str, categoria: str) -> dict:
    """Monta `objection_spoken` no formato de `agent/objection_
    rules.py` — `evidence_quote` é sempre a transcrição real da
    objeção (nunca reformulada/resumida). Levanta `ValueError` se
    `categoria` não pertencer ao vocabulário fechado de 13 valores ou
    se `objecao_texto` estiver vazio — mesma disciplina de
    `_validar_objection_spoken()`."""
    if not (objecao_texto or "").strip():
        raise ValueError("objecao_texto vazio — nenhuma objeção sem a fala real")
    if categoria not in OBJECTION_TIPOS:
        raise ValueError(f"categoria inválida: {categoria!r} (esperado um de {sorted(OBJECTION_TIPOS)})")
    return {"category": categoria, "evidence_quote": objecao_texto}


async def extrair_objecao_do_ciclo(
    objecao_detectada: Optional[dict],
    usuario_id: Optional[str] = None,
    meeting_id: Optional[str] = None,
    transcricao_parcial: str = "",
    historico: str = "",
) -> Optional[dict]:
    """Pipeline completo do ciclo: `objecao_detectada` (Finance) ->
    classificação de categoria (IA) -> investigação de causa raiz
    (IA, Tarefa 4.4, usando `transcricao_parcial`/`historico` como
    contexto) -> `registrar_objecao()` (Fase 6.1). Retorna `None` só
    quando não há dado suficiente pra montar a objeção em si (sem
    objeção no ciclo, classificação sem confiança, categoria
    inválida) — nunca lança por dado ausente, só por falha real de IA
    de categoria (4 provedores + fallback Claude esgotados), que o
    chamador decide como tratar (ver `agent/multiagente/
    orquestrador.py`, melhor esforço). Falha na investigação de causa
    raiz nunca propaga — é tratada aqui mesmo, degradando pra `root_
    cause_hypothesis=None`."""
    texto = (objecao_detectada or {}).get("objecao")
    if not (texto or "").strip():
        return None

    from agent.objection_category_classifier import classificar_categoria_objecao_async
    categoria = await classificar_categoria_objecao_async(texto, usuario_id=usuario_id, meeting_id=meeting_id)
    if not categoria:
        return None

    try:
        spoken = montar_objection_spoken(texto, categoria)
    except ValueError:
        return None

    hipotese = None
    try:
        from agent.objection_root_cause_extractor import investigar_causa_raiz_async
        hipotese = await investigar_causa_raiz_async(
            spoken, transcricao_parcial, historico, usuario_id=usuario_id, meeting_id=meeting_id,
        )
    except Exception as _e:
        logger.debug("Falha ao investigar causa raiz (melhor esforço, objeção mantida sem hipótese): %s", _e)

    return registrar_objecao(spoken, hipotese)
