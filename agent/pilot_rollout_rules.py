"""Fase 24 do "PROMPT MESTRE — SALE-IA V2" — Piloto.

"Liberar inicialmente para 1 vendedor, depois 5%, depois 20%, depois
50%, e somente então 100%. Feature flag obrigatória. Rollback precisa
funcionar sem deploy."

Função pura — zero IA/banco — que decide, para um `usuario_id`, se o
`agent/sales_reasoning_engine.py::raciocinar_async()` (Fase 7) deve
**influenciar de verdade** a recomendação que o vendedor vê (diferente
da Fase 23, Shadow Mode, que só observa em silêncio). Quem lê a feature
flag (`PILOT_MODE`) e chama a IA é `agent/multiagente/orquestrador.py`
— este módulo só decide o que os campos significam.

**Pré-condição desta fase, documentada e confirmada com o usuário**: o
motor novo raciocina hoje com 4 dos 11 campos de entrada reais
(`meeting_memory` parcial, `rag_context`, `objections` — Bloco 1 /
Tarefa 1.2, e `historical_patterns` — Bloco 2/3 / Tarefas 2.1+3.1 de
`docs/tasks-sales-reasoning-engine-completo.md`) — os outros 7 seguem
gap. A infraestrutura de rollout gradual é construída e testada nesta
rodada, mas **nenhum vendedor real entra no piloto por padrão**
(`PILOT_MODE` default `off`) — ativar é decisão de produto separada,
só depois de avaliar dado real do Shadow Mode.
"""

import hashlib

PILOT_MODES = ("off", "pilot_user", "5pct", "20pct", "50pct", "100pct")

# Percentual de cada modo — usado por usuario_no_percentual(). "off" e
# "pilot_user" ficam de fora (tratados por regra própria, não por
# bucket percentual).
_PILOT_MODE_PERCENTUAL = {
    "5pct": 5,
    "20pct": 20,
    "50pct": 50,
    "100pct": 100,
}


def usuario_no_percentual(usuario_id: str, percentual: int) -> bool:
    """Bucket determinístico e estável em [0, 100) por `usuario_id` —
    o mesmo vendedor sempre cai no mesmo bucket entre ciclos (nunca
    sorteado de novo a cada chamada, o que alternaria o vendedor entre
    modelo atual/novo de forma confusa). Subir o percentual (5%→20%→
    50%→100%) é sempre **superconjunto**: ninguém que já estava dentro
    de um percentual menor sai ao aumentar — propriedade garantida por
    usar o mesmo hash em toda faixa, só o limiar de comparação muda."""
    if not usuario_id:
        return False
    bucket = int(hashlib.sha256(usuario_id.encode("utf-8")).hexdigest(), 16) % 100
    return bucket < percentual


def deve_usar_modelo_novo(usuario_id: str | None, modo: str, usuarios_piloto=()) -> bool:
    """Decide se `usuario_id` está dentro do rollout da Fase 24 neste
    ciclo. `usuario_id=None` (extensão anônima, sem login) nunca entra
    — não há identidade estável pra fazer bucket nem pra reconectar o
    vendedor ao mesmo tratamento entre ciclos."""
    if not usuario_id or modo not in PILOT_MODES:
        return False
    if modo == "off":
        return False
    if modo == "pilot_user":
        return usuario_id in set(usuarios_piloto)
    percentual = _PILOT_MODE_PERCENTUAL.get(modo)
    return percentual is not None and usuario_no_percentual(usuario_id, percentual)


def mapear_para_next_best_action(saida_raciocinio: dict) -> dict:
    """Converte a saída de `raciocinar_async()` (10 campos do prompt
    mestre, Fase 7) pro schema que a extensão já sabe renderizar
    (`agent/prompt_templates/multiagente_coach.txt::next_best_action`
    — type/category/title/message/objective/reason/expected_effect/
    risk_if_ignored/follow_up/evite/confidence). Só chamado quando o
    Piloto (Fase 24) está ativo pra este `usuario_id` — nunca no ciclo
    normal, nunca em Shadow Mode (Fase 23, que nunca expõe nada ao
    vendedor).

    **`category` nunca é inventada por tradução de
    `recommended_framework`** — mesmo princípio de honestidade de
    `agent/shadow_mode_rules.py::avaliar_concordancia_estrutural()`:
    o vocabulário fechado de `recommended_framework` (9 valores) é
    usado como `category` diretamente (a extensão trata categoria
    desconhecida como texto simples, `_NBA_CATEGORY_LABEL[catKey] ||
    catKey`, nunca quebra), em vez de forçar uma tradução pro
    vocabulário livre de 12 valores que a IA do modelo atual usa.
    `type` é derivado de forma honesta (presença de
    `next_best_question`), nunca dos 4 valores originais
    (`insight`/`warning`/`next_step` não são distinguíveis pelo motor
    novo hoje — tudo que não é pergunta vira `insight`, o mais neutro
    dos 3).
    """
    next_best_question = (saida_raciocinio.get("next_best_question") or "").strip() or None
    avoid = saida_raciocinio.get("avoid") or []
    return {
        "type": "question" if next_best_question else "insight",
        "category": saida_raciocinio.get("recommended_framework") or "",
        "title": "",
        "message": next_best_question or (saida_raciocinio.get("next_best_action") or ""),
        "objective": saida_raciocinio.get("current_state") or "",
        "reason": saida_raciocinio.get("reason") or "",
        "expected_effect": None,
        "risk_if_ignored": None,
        "follow_up": None,
        "evite": "; ".join(avoid) if avoid else None,
        "confidence": saida_raciocinio.get("confidence"),
    }
