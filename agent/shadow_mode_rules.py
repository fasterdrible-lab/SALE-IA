"""Fase 23 do "PROMPT MESTRE — SALE-IA V2" — Teste em Shadow Mode.

"Antes de permitir que o novo Sales Reasoning Engine influencie
vendedores reais: executá-lo silenciosamente. Modelo atual continua
recomendando; novo modelo analisa silenciosamente. Comparar resultados.
Medir: agreement, disagreement, latency, errors, cost, quality. Só
liberar após avaliação."

Função pura — zero IA/banco — que monta o registro de uma comparação
entre a recomendação real (`agent/multiagente/orquestrador.py`, os 4-5
agentes já em produção) e a recomendação silenciosa do
`agent/sales_reasoning_engine.py::raciocinar_async()` (Fase 7). Quem
chama a IA e persiste o registro é `orquestrador.py`/`api/database.py`
— este módulo só decide o que os campos significam.

**Concordância estrutural, não semântica**: o único sinal comparável
sem chamar IA de novo é binário — os dois modelos recomendam uma
PERGUNTA ao cliente agora, ou não? O modelo atual expõe isso via
`next_best_action.type` (vocabulário fechado `question|insight|
warning|next_step`, `agent/prompt_templates/multiagente_coach.txt`); o
modelo novo via `next_best_question` (presente ou `None`,
`agent/sales_reasoning_engine.py`). **Nunca tenta mapear** a `category`
do modelo atual (12 valores de vocabulário livre da IA) para o
`recommended_framework` do modelo novo (9 valores de vocabulário
fechado) — nenhuma função traduz um formato pro outro, mesmo princípio
já usado em `agent/opportunity_intelligence_rules.py` (SPIN/MEDDPICC
vs. categorias de `OpportunityMemory`): inventar esse mapeamento seria
fabricar concordância, não medi-la.

`quality` (a recomendação nova é de fato BOA, não só estruturalmente
comparável) fica como gap explícito — exigiria um LLM-judge (mesmo
mecanismo de `evals/promptfooconfig.*.yaml`, `llm-rubric`), custo real
de IA por comparação, decisão de produto separada desta rodada.
"""

SHADOW_MODE_METRICAS = ("agreement", "latency_ms", "cost_usd", "errors", "quality")

QUALITY_NAO_DISPONIVEL = {
    "disponivel": False,
    "motivo": (
        "Avaliar se a recomendação do modelo novo é de fato boa (não só "
        "estruturalmente comparável à do modelo atual) exigiria um "
        "LLM-judge (mesmo mecanismo de evals/promptfooconfig.*.yaml, "
        "llm-rubric) — custo real de IA por comparação, decisão de "
        "produto separada, nunca rodada nesta rodada."
    ),
}


def avaliar_concordancia_estrutural(recomendacao_atual: dict | None, recomendacao_nova: dict | None) -> dict:
    """Único sinal de concordância calculado hoje, sem IA: os dois
    modelos recomendam uma pergunta ao cliente agora, ou não?
    `recomendacao_nova=None` (o modelo novo falhou/não rodou) sempre
    retorna `concordancia=None` — erro nunca é discordância."""
    if recomendacao_nova is None:
        return {"concordancia": None, "atual_e_pergunta": None, "novo_e_pergunta": None}

    atual_e_pergunta = (recomendacao_atual or {}).get("type") == "question"
    novo_e_pergunta = bool((recomendacao_nova.get("next_best_question") or "").strip())
    return {
        "concordancia": atual_e_pergunta == novo_e_pergunta,
        "atual_e_pergunta": atual_e_pergunta,
        "novo_e_pergunta": novo_e_pergunta,
    }


def montar_registro_shadow(
    recomendacao_atual: dict | None,
    recomendacao_nova: dict | None,
    latency_ms: int | None,
    cost_usd: float | None,
    erro: str | None,
) -> dict:
    """Monta o registro completo de uma comparação Shadow Mode — pronto
    pra `api/database.py::criar_shadow_mode_comparison()` persistir.
    Nunca acessa banco ou chama IA."""
    concordancia = avaliar_concordancia_estrutural(recomendacao_atual, recomendacao_nova)
    return {
        "recomendacao_atual": recomendacao_atual or {},
        "recomendacao_nova": recomendacao_nova,
        "concordancia": concordancia["concordancia"],
        "atual_e_pergunta": concordancia["atual_e_pergunta"],
        "novo_e_pergunta": concordancia["novo_e_pergunta"],
        "latency_ms": latency_ms,
        "cost_usd": cost_usd,
        "erro": erro,
        "quality": dict(QUALITY_NAO_DISPONIVEL),
    }


def resumir_comparacoes(comparacoes: list[dict]) -> dict:
    """Agrega uma lista de comparações já persistidas (formato de
    `api/database.py::listar_shadow_mode_comparisons()`) nas métricas
    literais da Fase 23: agreement/disagreement (%), latency (média),
    errors (taxa), cost (total). `quality` continua gap explícito —
    agregado nenhum resolve a ausência do LLM-judge."""
    total = len(comparacoes)
    com_erro = [c for c in comparacoes if c.get("erro")]
    comparaveis = [c for c in comparacoes if c.get("concordancia") is not None]
    concordantes = [c for c in comparaveis if c["concordancia"] is True]
    latencias = [c["latency_ms"] for c in comparacoes if isinstance(c.get("latency_ms"), (int, float))]
    custos = [c["cost_usd"] for c in comparacoes if isinstance(c.get("cost_usd"), (int, float))]

    return {
        "total_comparacoes": total,
        "comparaveis": len(comparaveis),
        "agreement_rate": (len(concordantes) / len(comparaveis)) if comparaveis else None,
        "disagreement_rate": (1 - len(concordantes) / len(comparaveis)) if comparaveis else None,
        "error_rate": (len(com_erro) / total) if total else None,
        "latency_ms_media": (sum(latencias) / len(latencias)) if latencias else None,
        "cost_usd_total": round(sum(custos), 6) if custos else 0.0,
        "quality": dict(QUALITY_NAO_DISPONIVEL),
    }
