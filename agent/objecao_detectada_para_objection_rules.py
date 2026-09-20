"""Bloco 1 / Tarefa 1.2 de docs/tasks-sales-reasoning-engine-completo.md
— traduz `resultado["objecao_detectada"]` (Finance, calculado em todo
ciclo de tempo real) para o formato de `agent/objection_rules.py`
(Fase 6.1), alimentando o campo `objections` do SalesReasoningEngine
(Fase 7) com dado real em vez de sempre `None`.

`montar_objection_spoken()` é pura (sem IA/banco, testável sozinha).
`extrair_objecao_do_ciclo()` orquestra: chama `agent/
objection_category_classifier.py` (a única parte com IA desta tarefa)
pra obter a `category`, depois monta e valida o fato via `agent/
objection_rules.py::registrar_objecao()` — sem `root_cause_hypothesis`
ainda (isso é a Tarefa 4.4 do plano, investigação de causa raiz).

Nunca fabrica categoria nem evidência: sem objeção detectada pelo
Finance, sem classificação de categoria bem-sucedida, ou com categoria
fora do vocabulário fechado, o ciclo simplesmente não produz fato
nenhum (`None`) — mesma disciplina de honestidade do resto do
projeto."""

from typing import Optional

from agent.objection_rules import OBJECTION_TIPOS, registrar_objecao


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
) -> Optional[dict]:
    """Pipeline completo do ciclo: `objecao_detectada` (Finance) ->
    classificação de categoria (IA) -> `registrar_objecao()` (Fase
    6.1). Retorna `None` em qualquer ponto sem dado suficiente (sem
    objeção no ciclo, classificação sem confiança, categoria
    inválida) — nunca lança por dado ausente, só por falha real de IA
    (4 provedores + fallback Claude esgotados), que o chamador decide
    como tratar (ver `agent/multiagente/orquestrador.py`, melhor
    esforço)."""
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

    return registrar_objecao(spoken)
