"""
SALEIA — agent/recommendation_rules.py

Regras puras do RecommendationEvent (FASE 10 / TAREFA 10.1 do "PROMPT
MESTRE — SALE-IA V2"). Nenhuma chamada de IA, nenhum acesso a banco —
mesmo padrão de agent/sales_event_rules.py / agent/sales_evidence_rules.py.

RecommendationEvent registra toda recomendação mostrada ao vendedor
(estratégia sugerida, texto da recomendação, motivo) — base para a
Tarefa 10.2 (detectar se foi usada) e 10.3 (efetividade real:
recomendação → uso → reação → avanço de estágio → resultado da
oportunidade), nenhuma das duas construída nesta rodada.

Mesma disciplina de `sales_event_rules.py`: RecommendationEvent é dado
de domínio, não telemetria — `criar_recommendation_event()` propaga
`ValueError` em dado inválido, nunca falha silenciosamente como
`AiUsageEvent`/`KnowledgeItem`. Sem recomendação registrada, não há
como medir efetividade nenhuma — cada campo exigido aqui é
literalmente necessário pras Tarefas 10.2/10.3 funcionarem depois.
"""

from typing import Optional


def validar_recommendation_event(dados: dict) -> None:
    """Valida os campos obrigatórios de um RecommendationEvent antes de
    persistir: `meeting_id`, `strategy`, `recommendation` e `reason`
    precisam existir e não ser vazios. `opportunity_id`/`outcome_window`
    são opcionais (schema literal do prompt mestre não os marca como
    obrigatórios); `used_at`/`seller_action` nascem sempre `None` — só
    a Tarefa 10.2 (detecção de uso) os preenche depois."""
    meeting_id = dados.get("meeting_id")
    if not meeting_id:
        raise ValueError("meeting_id é obrigatório")

    strategy = dados.get("strategy")
    if not strategy:
        raise ValueError("strategy é obrigatória")

    recommendation = dados.get("recommendation")
    if not recommendation:
        raise ValueError("recommendation é obrigatória")

    reason = dados.get("reason")
    if not reason:
        raise ValueError("reason é obrigatória")
