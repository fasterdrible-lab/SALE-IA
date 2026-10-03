"""
SALEIA — agent/opportunity_graph_writer_rules.py

Tarefa A4 de docs/tasks-prompt-mestre-v2-restante.md — escritor de
OpportunityGraph (Fase 2.2). Deriva arestas dos insights que a A3 grava
na OpportunityMemory, por **regras fixas por categoria — nunca IA**.
Os nós referenciam o `id` do insight na categoria (nunca duplicam o
dado); só o nó CLIENT referencia `client_id` da Opportunity.

Regras (as únicas que o dado de hoje sustenta):
- `PAIN --causa--> IMPACT`: no SPIN, a implicação é por definição a
  consequência do problema (exemplo literal da Fase 2.2: dor "leads
  esquecidos" → impacto "R$20.000/mês").
- `PAIN --motiva--> GOAL`: o valor da solução (need_payoff) é o valor de
  resolver a dor.
- `CLIENT --sente--> PAIN` e `CLIENT --levanta--> OBJECTION`, quando a
  oportunidade tem `client_id`.

A relação é inferida pela estrutura (qual categoria é consequência de
qual), não dita literalmente — por isso `source="regra_memoria"`, e a
`evidence` guarda as citações dos dois lados, sem perder a origem. A
`confidence` é a menor entre os dois insights.

Só dores **vigentes** ganham arestas novas: dor contradita por uma mais
recente (outra entrada com `contradiz` apontando para ela) não é mais
ligada — as arestas antigas continuam (append-only, histórico).

Fora, de propósito: causas raiz (`ROOT_CAUSE:` em `objections`) — a
memória não guarda qual objeção falada gerou cada causa raiz, e ligar
sem esse vínculo seria inventar a relação; OBJECTION↔PAIN (nenhuma
regra determinística diz qual dor sustenta qual objeção);
STAKEHOLDER/COMPETITOR/DECISION/NEXT_STEP (categorias ainda sem
escritor — dependem da A5).

Dedup: aresta com o mesmo `(from_type, from_id, to_type, to_id,
relation)` já existente é pulada.

Kill-switch `OPPORTUNITY_GRAPH_WRITE_ENABLED` (default `true`).
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

SOURCE_REGRA = "regra_memoria"
PREFIXO_CAUSA_RAIZ = "ROOT_CAUSE:"


def opportunity_graph_write_ativo() -> bool:
    return os.getenv("OPPORTUNITY_GRAPH_WRITE_ENABLED", "true").strip().lower() != "false"


def _validos(insights) -> list:
    return [i for i in (insights or []) if isinstance(i, dict) and i.get("id") is not None and (i.get("evidence") or "").strip()]


def _vigentes(insights: list) -> list:
    superados = {i.get("contradiz") for i in insights if i.get("contradiz") is not None}
    return [i for i in insights if i["id"] not in superados]


def _confidence(*insights) -> float:
    valores = []
    for i in insights:
        try:
            valores.append(float(i.get("confidence", 1.0)))
        except (TypeError, ValueError):
            valores.append(1.0)
    return max(0.0, min(1.0, min(valores)))


def _rotulo(tipo: str, insight: dict) -> str:
    return f"{tipo} ({insight.get('valor')}): \"{insight['evidence'].strip()}\""


def _aresta(from_type, from_id, to_type, to_id, relation, evidence, confidence) -> dict:
    return {
        "from_type": from_type, "from_id": str(from_id), "to_type": to_type, "to_id": str(to_id),
        "relation": relation, "evidence": evidence, "confidence": confidence, "source": SOURCE_REGRA,
    }


def chave_aresta(aresta: dict) -> tuple:
    return (aresta["from_type"], str(aresta["from_id"]), aresta["to_type"], str(aresta["to_id"]), aresta["relation"])


def calcular_arestas(memoria: Optional[dict], client_id: Optional[str] = None) -> list:
    """Função pura: arestas que a memória atual sustenta, na ordem
    CLIENT→PAIN, PAIN→IMPACT, PAIN→GOAL, CLIENT→OBJECTION. Memória
    ausente/malformada devolve `[]`, nunca levanta."""
    if not isinstance(memoria, dict):
        return []

    dores = _vigentes(_validos(memoria.get("pain_points")))
    impactos = _validos(memoria.get("business_impact"))
    objetivos = _validos(memoria.get("goals"))
    objecoes = [
        o for o in _validos(memoria.get("objections"))
        if not str(o.get("valor") or "").startswith(PREFIXO_CAUSA_RAIZ)
    ]
    client_id = str(client_id).strip() if client_id else ""

    arestas = []
    if client_id:
        for dor in dores:
            arestas.append(_aresta("CLIENT", client_id, "PAIN", dor["id"], "sente",
                                   _rotulo("dor", dor), _confidence(dor)))
    for dor in dores:
        for impacto in impactos:
            arestas.append(_aresta("PAIN", dor["id"], "IMPACT", impacto["id"], "causa",
                                   f"{_rotulo('dor', dor)} -> {_rotulo('impacto', impacto)}",
                                   _confidence(dor, impacto)))
    for dor in dores:
        for objetivo in objetivos:
            arestas.append(_aresta("PAIN", dor["id"], "GOAL", objetivo["id"], "motiva",
                                   f"{_rotulo('dor', dor)} -> {_rotulo('objetivo', objetivo)}",
                                   _confidence(dor, objetivo)))
    if client_id:
        for objecao in objecoes:
            arestas.append(_aresta("CLIENT", client_id, "OBJECTION", objecao["id"], "levanta",
                                   _rotulo("objeção", objecao), _confidence(objecao)))
    return arestas


def gravar_opportunity_graph(opportunity_id: Optional[int]) -> int:
    """Lê a memória atual da oportunidade e grava só as arestas novas;
    retorna quantas foram criadas. Aresta que falhe a validação de
    domínio é pulada e logada; erro de banco propaga (o orquestrador
    isola em `try/except`)."""
    if not opportunity_id or not opportunity_graph_write_ativo():
        return 0

    from api.database import (
        criar_aresta_opportunity_graph,
        listar_arestas_opportunity,
        obter_opportunity,
        obter_opportunity_memory,
    )

    memoria = obter_opportunity_memory(opportunity_id, criar_se_ausente=False)
    if not memoria:
        return 0
    oportunidade = obter_opportunity(opportunity_id) or {}
    arestas = calcular_arestas(memoria, oportunidade.get("client_id"))
    if not arestas:
        return 0

    existentes = {chave_aresta(a) for a in listar_arestas_opportunity(opportunity_id)}
    criadas = 0
    for aresta in arestas:
        chave = chave_aresta(aresta)
        if chave in existentes:
            continue
        try:
            criar_aresta_opportunity_graph(opportunity_id, **aresta)
        except ValueError as e:
            logger.debug("[OpportunityGraph] Aresta inválida pulada (%s): %s", aresta["relation"], e)
            continue
        existentes.add(chave)
        criadas += 1
    return criadas
