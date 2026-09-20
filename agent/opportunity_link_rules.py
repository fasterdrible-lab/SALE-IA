"""Bloco 3 / Tarefa 3.1 de docs/tasks-sales-reasoning-engine-completo.md
— vincula automaticamente uma reunião a uma `Opportunity` aberta do
mesmo cliente, quando não há ambiguidade.

Pré-requisito da Tarefa 2.1 (historical_patterns via Sales Science):
sem `MeetingMemory.opportunity_id` preenchido, não há como saber qual
estágio/produto filtrar pra buscar insight estatístico relevante.
Confirmado com o usuário: nunca existia nenhum caminho automático até
agora — `api/database.py::vincular_meeting_opportunity()` já existia
desde a Fase 2, mas nunca era chamada em lugar nenhum do sistema.

Regra confirmada: só vincula quando existe **exatamente 1** oportunidade
aberta do cliente da reunião — 0 ou 2+ candidatas nunca vinculam
sozinhas (ambiguidade fica pra vínculo manual, decisão de escopo desta
tarefa: não construir endpoint de vínculo manual). Nunca sobrescreve
um vínculo já existente.
"""

from typing import Optional


def escolher_opportunity_para_vincular(opportunities_abertas: list) -> Optional[int]:
    """Pura: dado uma lista de `Opportunity` (dict, já filtradas por
    `status="open"` e `client_id` do cliente da reunião), retorna o
    `id` a vincular só quando houver exatamente 1 candidata — `None`
    em qualquer outro caso (0 ou 2+, ambiguidade nunca resolvida
    automaticamente)."""
    if len(opportunities_abertas) == 1:
        return opportunities_abertas[0]["id"]
    return None


def vincular_automaticamente_se_possivel(meeting_id: str) -> Optional[int]:
    """Orquestra a Tarefa 3.1 pra uma reunião: já vinculada? retorna o
    `opportunity_id` existente sem tocar em nada (nunca sobrescreve).
    Sem cliente identificado pra reunião? `None`. Com cliente e
    exatamente 1 oportunidade aberta? vincula de verdade e retorna o
    id novo. Ambíguo (2+) ou sem oportunidade nenhuma pro cliente?
    `None`, sem vincular. Melhor esforço — nunca lança, o chamador
    (Tarefa 2.1) trata `None` como "sem oportunidade pra filtrar"."""
    from api.database import listar_opportunities, obter_meeting_memory, vincular_meeting_opportunity

    memoria = obter_meeting_memory(meeting_id)
    if memoria and memoria.get("opportunity_id"):
        return memoria["opportunity_id"]

    from agent.client_intelligence import buscar_cliente_por_reuniao
    client_id = buscar_cliente_por_reuniao(meeting_id)
    if not client_id:
        return None

    abertas = listar_opportunities(client_id=client_id, status="open")
    opportunity_id = escolher_opportunity_para_vincular(abertas)
    if opportunity_id is None:
        return None

    vincular_meeting_opportunity(meeting_id, opportunity_id)
    return opportunity_id
