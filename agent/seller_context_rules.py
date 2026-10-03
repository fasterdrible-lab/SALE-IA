"""
SALEIA — agent/seller_context_rules.py

Tarefa C2 de docs/tasks-prompt-mestre-v2-restante.md — liga o SellerDNA
agregado (Bloco 5 / Tarefa 5.1 de docs/tasks-sales-reasoning-engine-
completo.md) no campo `seller_context` do SalesReasoningEngine, o 11º e
último campo que ainda vinha sempre `None`.

Leitura pura, zero IA nova: as observações já são extraídas e gravadas
pós-reunião (`agent/seller_dna_extractor.py`, atrás do kill-switch
`SELLER_DNA_OBSERVACAO_ENABLED`); aqui só se agrega o que existe via
`seller_dna_rules.construir_seller_dna_de_observacoes()`.

Regras herdadas, nunca reimplementadas:
- **Amostra mínima** (Fase 15.1, `SELLER_DNA_AMOSTRA_MINIMA_PADRAO` = 10
  reuniões distintas): abaixo disso `construir_seller_dna()` recusa e o
  contexto fica `None` — nunca "clona personalidade" de poucas conversas.
- **Comportamento ≠ eficácia** (Fase 15.2): a mesma função recusa
  qualquer valor com alegação de eficácia; se isso acontecer, o contexto
  inteiro fica `None` (nunca entrega um perfil parcialmente filtrado).

`seller_id` é o vendedor autenticado do ciclo (`usuario_id` de
`/tempo-real`) — o mesmo que `MeetingMemory.usuario_id` usa para
atribuir as observações.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def seller_context_ativo() -> bool:
    """Kill-switch `SELLER_CONTEXT_ENABLED` (default `true`) — `false`
    volta a mandar `seller_context=None` ao motor, sem reverter deploy.
    Independente de `SELLER_DNA_OBSERVACAO_ENABLED` (que governa a
    extração pós-reunião, a parte com custo de IA)."""
    return os.getenv("SELLER_CONTEXT_ENABLED", "true").strip().lower() != "false"


def obter_seller_context(seller_id: Optional[str]) -> Optional[dict]:
    """SellerDNA agregado do vendedor, no formato de
    `construir_seller_dna()` (`{"seller_id", "n_reunioes_analisadas",
    "campos": {campo: [valores distintos] | None}}`), ou `None` quando
    não há vendedor, a amostra é insuficiente ou uma guarda de domínio
    recusou o perfil. Erro de banco propaga (o orquestrador isola)."""
    if not seller_id or not str(seller_id).strip() or not seller_context_ativo():
        return None

    from agent.seller_dna_rules import construir_seller_dna_de_observacoes
    from api.database import listar_seller_dna_observacoes

    observacoes = listar_seller_dna_observacoes(seller_id)
    if not observacoes:
        return None
    try:
        return construir_seller_dna_de_observacoes(seller_id, observacoes)
    except ValueError as e:
        logger.debug("[SellerContext] Perfil indisponível para seller=%s: %s", seller_id, e)
        return None
