"""
agent/quality_monitoring_rules.py

Tarefa 19.1 do "PROMPT MESTRE — SALE-IA V2" (Quality Monitoring): as 6
métricas comerciais literais — event_precision, objection_precision,
framework_accuracy, recommendation_relevance, hallucination_rate,
evidence_coverage.

Escopo confirmado com o usuário (pergunta direta de escopo, mesma
disciplina das Fases 7/10/13/14/16/18.2-18.4/19): só as fórmulas
corretas de cada métrica, como funções puras testáveis — **sem dado
real por trás**. As 6 exigem comparar a saída da IA contra um gabarito
rotulado, que é exatamente o que a Fase 20 ("Golden Sales Dataset"),
ainda não construída, deveria fornecer. Sem esse gabarito, qualquer
número aqui seria inventado — mesma disciplina de honestidade já usada
nos 2 gaps da Fase 19 (`RAG_LATENCY_NAO_CAPTURADA`/
`RECOMMENDATION_EFFECTIVENESS_NAO_DISPONIVEL`,
`agent/observability_metrics_rules.py`).

Mesmo padrão de `*_rules.py` (função pura, zero IA/banco). Reaproveita
`calcular_taxa()` (Fase 19) para a aritmética comum, em vez de
duplicá-la.
"""
from agent.observability_metrics_rules import calcular_taxa

QUALITY_METRIC_SEM_GABARITO = {
    "disponivel": False,
    "motivo": (
        "Exige comparar a saída da IA contra um gabarito rotulado "
        "(Fase 20 — Golden Sales Dataset — ainda não construída). Sem "
        "gabarito real, calcular isso geraria um número sem lastro."
    ),
}


def _precisao(verdadeiros_positivos: int, falsos_positivos: int):
    """Precisão = VP / (VP + FP) — mesma fórmula usada por
    event_precision e objection_precision, domínios diferentes."""
    return calcular_taxa(verdadeiros_positivos, verdadeiros_positivos + falsos_positivos)


def calcular_event_precision(verdadeiros_positivos: int, falsos_positivos: int):
    """event_precision: dos `SalesEvent`s que a IA classificou como um
    dado tipo, quantos realmente eram desse tipo segundo o gabarito
    (Fase 20)."""
    return _precisao(verdadeiros_positivos, falsos_positivos)


def calcular_objection_precision(verdadeiros_positivos: int, falsos_positivos: int):
    """objection_precision: das objeções que a IA classificou numa
    categoria (Fase 6, `agent/objection_rules.py`), quantas realmente
    eram dessa categoria segundo o gabarito."""
    return _precisao(verdadeiros_positivos, falsos_positivos)


def calcular_framework_accuracy(corretos: int, total: int):
    """framework_accuracy: das vezes que o `SalesReasoningEngine`
    (Fase 7) recomendou um framework (`recommended_framework`), quantas
    bateram com o framework correto segundo o gabarito."""
    return calcular_taxa(corretos, total)


def calcular_recommendation_relevance(relevantes: int, avaliadas: int):
    """recommendation_relevance: das recomendações avaliadas (por
    humano ou LLM-judge contra o gabarito), quantas foram consideradas
    relevantes pra situação real da reunião."""
    return calcular_taxa(relevantes, avaliadas)


def calcular_hallucination_rate(afirmacoes_sem_evidencia: int, total_afirmacoes: int):
    """hallucination_rate: % de afirmações da IA que NÃO têm respaldo
    em evidência real (`evidence_quote`) — quanto menor, melhor."""
    return calcular_taxa(afirmacoes_sem_evidencia, total_afirmacoes)


def calcular_evidence_coverage(afirmacoes_com_evidencia: int, total_afirmacoes: int):
    """evidence_coverage: % de afirmações da IA que TÊM respaldo em
    evidência real. Complementar a hallucination_rate, mas medido
    independentemente — nem toda afirmação sem evidência é
    necessariamente uma alucinação (pode ser uma inferência razoável
    ainda não fact-checkada)."""
    return calcular_taxa(afirmacoes_com_evidencia, total_afirmacoes)
