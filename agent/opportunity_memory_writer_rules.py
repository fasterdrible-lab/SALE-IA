"""
SALEIA — agent/opportunity_memory_writer_rules.py

Tarefa A3 de docs/tasks-prompt-mestre-v2-restante.md — escritor de
OpportunityMemory (Fase 2.1). Quando a reunião está vinculada a uma
Opportunity (Tarefa 3.1), grava os fatos do ciclo nas categorias da
memória da oportunidade, pelo caminho append-only + contradição que já
existe (`api/database.py::registrar_conhecimento_opportunity()` →
`agent/opportunity_memory_rules.py::adicionar_insight()`). Zero IA nova.

Mapeamento (só o que os extratores do ciclo já produzem, com evidência
checada literalmente contra a conversa):
- SPIN `problem.main_pain`            → `pain_points`     (campo `main_pain`)
- SPIN `implication.*`                → `business_impact` (campo = campo SPIN)
- SPIN `need_payoff.solution_value`   → `goals`           (campo `solution_value`)
- objeção falada                      → `objections` (valor = categoria)
- causa raiz da objeção               → `objections` (valor = `ROOT_CAUSE:<hipótese>`)

Objeções vão **sem `campo`** de propósito: duas objeções de preço com
falas diferentes não são contradição, são duas objeções. Nos fatos SPIN,
`campo` é o que faz um valor divergente (ex.: outra dor principal)
preencher `contradiz` — nada é apagado.

Fora do mapeamento (decisão deliberada, sem categoria certa ou sem
extrator): SPIN `situation` (tamanho de equipe/ferramenta atual),
sinais comportamentais e motivação (são leitura do comprador, não fato
da oportunidade), e `champion`/`economic_buyer`/`decision_process`/
`competitors`/`next_steps`/`stakeholders`/`metrics`/`risks`/`unknowns`
— nenhum extrator produz esses hoje (a A5, MEDDPICC, é quem destrava a
maior parte).

**Dedup entre ciclos**: a transcrição é acumulada, então o mesmo fato
reaparece a cada 60s. Um insight com a mesma `(categoria, campo, valor,
evidência)` já registrado (em qualquer reunião da oportunidade) é pulado
— espaços colapsados + minúsculas na comparação.

Kill-switch `OPPORTUNITY_MEMORY_WRITE_ENABLED` (default `true`).
"""

import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

# (stage SPIN, campo) → categoria da OpportunityMemory. Campo fora do
# dict (ex.: todo o estágio `situation`) nunca é gravado.
SPIN_PARA_CATEGORIA = {
    ("problem", "main_pain"): "pain_points",
    ("implication", "financial_impact"): "business_impact",
    ("implication", "conversion_impact"): "business_impact",
    ("need_payoff", "solution_value"): "goals",
}


def opportunity_memory_write_ativo() -> bool:
    return os.getenv("OPPORTUNITY_MEMORY_WRITE_ENABLED", "true").strip().lower() != "false"


def _norm(valor) -> str:
    return re.sub(r"\s+", " ", str(valor if valor is not None else "")).strip().lower()


def chave_dedup(categoria: str, insight: dict) -> tuple:
    return (categoria, insight.get("campo") or None, _norm(insight.get("valor")), _norm(insight.get("evidence")))


def _texto(valor) -> Optional[str]:
    return valor.strip() if isinstance(valor, str) and valor.strip() else None


def montar_insights_do_ciclo(spin_state: Optional[dict] = None, objections: Optional[list] = None) -> list:
    """Função pura: `[{"categoria", "campo", "valor", "evidence",
    "confidence"?}]` na ordem SPIN → objeções, já sem duplicata dentro
    do lote. Entrada ausente/malformada nunca levanta."""
    candidatos = []

    spin_state = spin_state if isinstance(spin_state, dict) else {}
    for stage, bloco in spin_state.items():
        if not isinstance(bloco, dict):
            continue
        for fato in bloco.get("known") or []:
            if not isinstance(fato, dict):
                continue
            categoria = SPIN_PARA_CATEGORIA.get((stage, fato.get("campo")))
            evidencia = _texto(fato.get("evidence_quote"))
            valor = fato.get("valor")
            if categoria and evidencia and _norm(valor):
                candidatos.append({"categoria": categoria, "campo": fato["campo"], "valor": valor, "evidence": evidencia})

    for objecao in objections or []:
        if not isinstance(objecao, dict):
            continue
        spoken = objecao.get("objection_spoken")
        if isinstance(spoken, dict):
            categoria_obj = _texto(spoken.get("category"))
            evidencia = _texto(spoken.get("evidence_quote"))
            if categoria_obj and evidencia:
                candidatos.append({"categoria": "objections", "campo": None, "valor": categoria_obj, "evidence": evidencia})
        root = objecao.get("root_cause_hypothesis")
        if isinstance(root, dict):
            hipotese = _texto(root.get("hypothesis"))
            evidencia = _texto(root.get("evidence_quote"))
            try:
                confidence = float(root.get("confidence"))
            except (TypeError, ValueError):
                confidence = None
            if hipotese and evidencia and confidence is not None and 0.0 <= confidence <= 1.0:
                candidatos.append({
                    "categoria": "objections", "campo": None, "valor": f"ROOT_CAUSE:{hipotese}",
                    "evidence": evidencia, "confidence": confidence,
                })

    insights, vistas = [], set()
    for item in candidatos:
        chave = chave_dedup(item["categoria"], item)
        if chave not in vistas:
            vistas.add(chave)
            insights.append(item)
    return insights


def gravar_opportunity_memory_do_ciclo(
    opportunity_id: Optional[int],
    meeting_id: Optional[str],
    spin_state: Optional[dict] = None,
    objections: Optional[list] = None,
) -> dict:
    """Grava os insights novos do ciclo e retorna `{"criados": N,
    "contradicoes": M}`. Sem oportunidade vinculada ou reunião anônima,
    nada é gravado. Insight que falhe a validação de domínio é pulado e
    logado, nunca derruba os outros; erro de banco propaga (o
    orquestrador isola em `try/except`)."""
    resultado = {"criados": 0, "contradicoes": 0}
    if not opportunity_id or not meeting_id or meeting_id == "default" or not opportunity_memory_write_ativo():
        return resultado

    insights = montar_insights_do_ciclo(spin_state, objections)
    if not insights:
        return resultado

    from api.database import obter_opportunity_memory, registrar_conhecimento_opportunity

    memoria = obter_opportunity_memory(opportunity_id, criar_se_ausente=False) or {}
    existentes = {
        chave_dedup(item["categoria"], anterior)
        for item in insights
        for anterior in memoria.get(item["categoria"]) or []
    }

    for item in insights:
        if chave_dedup(item["categoria"], item) in existentes:
            continue
        kwargs = {k: item[k] for k in ("campo", "valor", "evidence", "confidence") if k in item}
        try:
            gravado = registrar_conhecimento_opportunity(
                opportunity_id, item["categoria"], meeting_id=meeting_id, **kwargs,
            )
        except ValueError as e:
            logger.debug("[OpportunityMemory] Insight inválido pulado (%s): %s", item["categoria"], e)
            continue
        resultado["criados"] += 1
        if gravado.get("contradicao"):
            resultado["contradicoes"] += 1
    return resultado
