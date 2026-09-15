"""
SALEIA — agent/recommendation_usage_rules.py

Detecção de uso de recomendação (FASE 10 / TAREFA 10.2 do "PROMPT
MESTRE — SALE-IA V2"). Constrói sobre o `RecommendationEvent` da
Tarefa 10.1 — `agent/recommendation_rules.py`, este arquivo próprio,
mesmo padrão de cada Tarefa ganhar seu módulo mesmo construindo sobre
a anterior (`deal_risk_rules.py` sobre `meddpicc_rules.py`, Fase 4).

Regra central do prompt mestre — "não exigir correspondência
literal": uma recomendação como "Pergunte sobre impacto financeiro."
precisa ser reconhecida como usada quando o vendedor pergunta "Quanto
vocês estimam que isso custa todo mês?", mesmo sem nenhuma palavra em
comum. String matching/keyword overlap não resolve esse caso — decisão
confirmada com o usuário: usar **embeddings** (`services/embeddings/`,
mesmo provedor já usado no RAG/Sales Memory — Ollama local por
padrão), comparados por similaridade de cosseno, em vez de uma chamada
de IA nova por detecção.

**Estado nunca é uma coluna nova em `RecommendationEvent`** — o schema
literal da Tarefa 10.1 não tem campo de status; o estado é sempre
*derivado* de `recommendation` + `seller_action` já persistidos,
calculado sob demanda (mesmo princípio de `outcome_rules.
calcular_cycle_days()`: nunca armazenar o que pode ser recalculado com
precisão a partir do dado real).
"""

from typing import Optional

import numpy as np

from services.embeddings import get_embedding_provider

# Os 4 estados literais do prompt mestre.
RECOMMENDATION_USAGE_STATES = frozenset({"USED", "PARTIALLY_USED", "IGNORED", "UNKNOWN"})

# Limiares de similaridade de cosseno — decisão desta rodada, o prompt
# mestre não define os números exatos, só pede os 4 estados e "não
# exigir correspondência literal". Sobrescrevíveis por chamada, mesmo
# padrão de AMOSTRA_MINIMA_PADRAO (win_loss_rules.py, Fase 8).
LIMIAR_USED_PADRAO = 0.55
LIMIAR_PARTIALLY_USED_PADRAO = 0.35


def cosine_similarity(vetor_a: list, vetor_b: list) -> float:
    """Similaridade de cosseno entre 2 vetores — helper simples para um
    par único (`services.embeddings.provider.cosine_top_k` compara 1
    vetor contra uma matriz de muitos, não serve aqui direto)."""
    a = np.array(vetor_a, dtype=float)
    b = np.array(vetor_b, dtype=float)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def classificar_uso_por_similaridade(
    similaridade: Optional[float],
    seller_action: Optional[str],
    limiar_used: float = LIMIAR_USED_PADRAO,
    limiar_partially_used: float = LIMIAR_PARTIALLY_USED_PADRAO,
) -> str:
    """Classifica em um dos 4 estados a partir de uma similaridade de
    cosseno já calculada — função pura, nunca gera embedding sozinha
    (isso é `detectar_uso_recomendacao()`, abaixo). `UNKNOWN` quando
    não há `seller_action` registrado ainda (recomendação mostrada mas
    ninguém sabe se foi usada) ou quando `similaridade` é `None`
    (embedding falhou — nunca interpretado como "ignorado")."""
    if not seller_action or similaridade is None:
        return "UNKNOWN"
    if similaridade >= limiar_used:
        return "USED"
    if similaridade >= limiar_partially_used:
        return "PARTIALLY_USED"
    return "IGNORED"


async def detectar_uso_recomendacao(
    recommendation: str,
    seller_action: Optional[str],
    limiar_used: float = LIMIAR_USED_PADRAO,
    limiar_partially_used: float = LIMIAR_PARTIALLY_USED_PADRAO,
) -> dict:
    """Motor real: gera embeddings de `recommendation` e `seller_action`
    via `services.embeddings.factory.get_embedding_provider()` (mesmo
    caminho do RAG/Sales Memory) e classifica por similaridade de
    cosseno. Falha de embedding (rede/timeout — `embed_async()` retorna
    `None`, nunca lança) vira `UNKNOWN`, nunca `IGNORED` — não sabemos
    se foi usada, é diferente de saber que não foi."""
    if not seller_action:
        return {"state": "UNKNOWN", "similarity": None, "reason": "sem seller_action registrado"}

    provider = get_embedding_provider()
    resultado_recomendacao = await provider.embed_async(recommendation)
    resultado_seller = await provider.embed_async(seller_action)

    if resultado_recomendacao is None or resultado_seller is None:
        return {"state": "UNKNOWN", "similarity": None, "reason": "falha ao gerar embedding"}

    similaridade = cosine_similarity(resultado_recomendacao.vector, resultado_seller.vector)
    estado = classificar_uso_por_similaridade(similaridade, seller_action, limiar_used, limiar_partially_used)
    return {"state": estado, "similarity": similaridade, "reason": None}
