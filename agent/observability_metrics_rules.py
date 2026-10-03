"""
agent/observability_metrics_rules.py

Fase 19 do "PROMPT MESTRE — SALE-IA V2" (Observabilidade): funções
puras de agregação para as métricas literais da fase (AI latency,
recommendation latency, RAG latency, cost per meeting, cost per
opportunity, tokens, fallback rate, error rate, recommendation
acceptance rate, recommendation effectiveness). Mesmo padrão de
`win_loss_rules.py`/`data_warehouse_rules.py` — zero IA/banco,
genéricas sobre listas/números já extraídos pelo chamador
(`api/database.py`).

Levantamento antes de codar (achado real, não suposição): a maior
parte do dado bruto já existia (`AiUsageEvent.latency_ms`/`success`/
`fallback_used` desde a Fase 1 do Cost Intelligence; `RecommendationEvent`
desde a Fase 10), só faltava agregação. Duas métricas NÃO têm dado real
hoje e ficam documentadas como gap, nunca inventadas:

- **RAG latency**: nenhuma cronometragem existe nos pontos de busca de
  RAG/Sales Memory hoje — só o Langfuse Observability opcional (Fase 1
  do OUTRO roadmap "PROMPT MESTRE — EVOLUÇÃO DA SALEIA.txt",
  `OBSERVABILITY_ENABLED=false` por padrão) rastreia isso como span.
- **recommendation effectiveness**: a fórmula já existe e funciona
  (`agent/recommendation_effectiveness_rules.py`, Fase 10.3), mas
  exige `RecommendationEvent` classificado (`state`/`stage_advanced`/
  `opportunity_result`) — nenhuma dessas classificações roda de
  verdade em produção ainda (Fase 10.2 nunca foi plugada em nenhum
  fluxo real). Sem essa entrada, a função só devolveria um resultado
  vazio — documentado como gap em vez de forçar um número sem lastro.

**recommendation acceptance rate** é exposta como um proxy barato
("taxa de resposta" — `RecommendationEvent.used_at` preenchido), não a
classificação semântica real USED/PARTIALLY_USED/IGNORED (Fase 10.2,
que exige 1 chamada de embedding por evento e não roda automaticamente
hoje) — deixado explícito no retorno, nunca disfarçado de dado
equivalente.
"""

RAG_LATENCY_NAO_CAPTURADA = {
    "capturado": False,
    "motivo": (
        "Nenhuma cronometragem existe nos pontos de busca de RAG/Sales "
        "Memory hoje. Só o Langfuse Observability opcional (Fase 1 do "
        "roadmap \"PROMPT MESTRE — EVOLUÇÃO DA SALEIA\", "
        "OBSERVABILITY_ENABLED=false por padrão) rastreia retrieval "
        "como span — instrumentar isso de verdade é decisão de escopo "
        "separada, fora da Fase 19."
    ),
}

RECOMMENDATION_EFFECTIVENESS_NAO_DISPONIVEL = {
    "disponivel": False,
    "motivo": (
        "agent/recommendation_effectiveness_rules.py (Fase 10.3) calcula "
        "a métrica corretamente, mas exige o estado de uso de cada "
        "RecommendationEvent (detectar_uso_recomendacao, Fase 10.2), que "
        "não é persistido — só é calculado em lote, via embeddings "
        "locais, por scripts/recommendation_quality_run.py. "
        "stage_advanced/opportunity_result já são capturados desde a "
        "Tarefa B2 (agent/recommendation_outcome_rules.py); rode o script "
        "para o número real."
    ),
}


def calcular_estatisticas_latencia(latencias_ms: list) -> dict:
    """Média/mínimo/máximo/p50/p95 sobre uma lista de latências em ms
    (ignora `None`). Lista vazia (ou só `None`) devolve tudo `None` —
    nunca inventa um número pra amostra vazia."""
    valores = sorted(v for v in latencias_ms if v is not None)
    if not valores:
        return {
            "amostra": 0, "media_ms": None, "minimo_ms": None,
            "maximo_ms": None, "p50_ms": None, "p95_ms": None,
        }

    def _percentil(p: float) -> float:
        if len(valores) == 1:
            return valores[0]
        indice = min(len(valores) - 1, int(round(p * (len(valores) - 1))))
        return valores[indice]

    return {
        "amostra": len(valores),
        "media_ms": round(sum(valores) / len(valores), 1),
        "minimo_ms": valores[0],
        "maximo_ms": valores[-1],
        "p50_ms": _percentil(0.50),
        "p95_ms": _percentil(0.95),
    }


def calcular_taxa(numerador: int, denominador: int):
    """Razão numerador/denominador, arredondada em 4 casas — `None` se
    `denominador` for 0 (nunca divide por zero, nunca finge que a taxa
    é 0%)."""
    if not denominador:
        return None
    return round(numerador / denominador, 4)
