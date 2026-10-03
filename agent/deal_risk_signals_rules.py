"""
SALEIA — agent/deal_risk_signals_rules.py

Tarefa A6 de docs/tasks-prompt-mestre-v2-restante.md — sinais REAIS para
o Deal Risk Engine (Fase 4.2, `agent/deal_risk_rules.py`), que até aqui
só existia como função pura sem ninguém calculando as entradas. Função
pura, zero IA/banco: recebe `Opportunity` + `OpportunityMemory` + as
reuniões vinculadas (já buscadas pelo chamador) e devolve o payload de
`risks_calculados` do Opportunity Intelligence.

De onde vem cada sinal (dado já gravado pelas Tarefas A3/A5/A6):
- `NO_ECONOMIC_BUYER` / `NO_CHAMPION` / `NO_METRICS`: status MEDDPICC dos
  insights da memória (a A3 grava o `status` do fato da A5). O estado é
  recalculado por `meddpicc_rules.calcular_qualificacao_meddpicc()`
  (nunca aqui) — o status mais avançado já visto vence.
- `NO_NEXT_STEP`: nenhum `next_steps` registrado para a **última**
  reunião vinculada (os `proximos_passos` da recapitulação, gravados no
  gancho pós-recapitulação da B7). Uma reunião sem recapitulação gerada
  também aparece aqui — "sem próximo passo registrado", não "o cliente
  recusou próximo passo".
- `HIGH_PRICE_RESISTANCE`: objeções `PRICE` registradas na oportunidade
  (já deduplicadas pela A3) ≥ limiar da Fase 4.2 (3).
- `STALE_OPPORTUNITY`: dias desde a última atividade de reunião
  vinculada (sem reunião: desde a atualização da própria oportunidade)
  ≥ limiar da Fase 4.2 (21).
- `COMPETITOR_ADVANTAGE`: **sem fonte** — nada no sistema diz quem está
  na frente (o item `competition` do MEDDPICC só diz que o cenário foi
  mapeado). Vai em `nao_avaliados`, nunca como "sem risco".

Oportunidade encerrada (won/lost/abandoned) não tem risco de deal em
aberto: `riscos=[]` com `encerrada=True`.
"""

from datetime import datetime
from typing import Optional

# (categoria da OpportunityMemory, campo) → item MEDDPICC — inverso de
# `opportunity_memory_writer_rules.MEDDPICC_PARA_CATEGORIA`. Só insights
# com `status` entram (vieram da A5); os demais são ignorados.
CATEGORIA_PARA_MEDDPICC = {
    ("metrics", None): "metrics",
    ("economic_buyer", "economic_buyer"): "economic_buyer",
    ("champion", "champion"): "champion",
    ("decision_process", "decision_process"): "decision_process",
    ("decision_process", "paper_process"): "paper_process",
    ("decision_process", None): "decision_criteria",
    ("competitors", None): "competition",
}

NAO_AVALIADO_COMPETITOR = {
    "risco": "COMPETITOR_ADVANTAGE",
    "motivo": "Nenhuma fonte no sistema diz se um concorrente está em vantagem — o item "
              "`competition` do MEDDPICC só indica que o cenário competitivo foi mapeado.",
}


def estado_meddpicc_da_memoria(memoria: Optional[dict]) -> Optional[dict]:
    """Estado MEDDPICC reconstruído dos insights com `status` — `None`
    quando nenhum insight da memória tem status (nada qualificado pela
    A5 ainda, diferente de "tudo UNKNOWN")."""
    from agent.meddpicc_rules import calcular_qualificacao_meddpicc

    fatos = []
    for (categoria, campo), item in CATEGORIA_PARA_MEDDPICC.items():
        for insight in (memoria or {}).get(categoria) or []:
            if not isinstance(insight, dict) or insight.get("status") not in ("PARTIAL", "CONFIRMED"):
                continue
            if (insight.get("campo") or None) != campo or not (insight.get("evidence") or "").strip():
                continue
            fatos.append({
                "item": item, "status": insight["status"],
                "confidence": insight.get("confidence", 1.0), "evidence_quote": insight["evidence"],
            })
    return calcular_qualificacao_meddpicc(fatos) if fatos else None


def _data(valor) -> Optional[datetime]:
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, str) and valor.strip():
        try:
            return datetime.fromisoformat(valor.strip())
        except ValueError:
            return None
    return None


def calcular_sinais(
    opportunity: dict,
    memoria: Optional[dict],
    reunioes: Optional[list],
    agora: Optional[datetime] = None,
) -> dict:
    """Sinais de entrada de `deal_risk_rules.calcular_riscos()` a partir
    do dado real. `tem_proximo_passo` é `None` quando não há reunião
    vinculada para olhar (não avaliável)."""
    agora = agora or datetime.now()
    memoria = memoria or {}
    reunioes = [r for r in (reunioes or []) if isinstance(r, dict) and r.get("meeting_id")]

    def _momento(r):
        return _data(r.get("updated_at")) or _data(r.get("created_at"))

    ultima = max(reunioes, key=lambda r: _momento(r) or datetime.min) if reunioes else None

    tem_proximo_passo = None
    if ultima:
        tem_proximo_passo = any(
            isinstance(p, dict) and p.get("meeting_id") == ultima["meeting_id"]
            for p in memoria.get("next_steps") or []
        )

    total_objecoes_preco = sum(
        1 for o in memoria.get("objections") or []
        if isinstance(o, dict) and str(o.get("valor") or "").strip().upper() == "PRICE"
    )

    ultima_atividade = (
        (_momento(ultima) if ultima else None)
        or _data(opportunity.get("updated_at"))
        or _data(opportunity.get("created_at"))
    )
    dias = max(0, (agora - ultima_atividade).days) if ultima_atividade else None

    return {
        "estado_meddpicc": estado_meddpicc_da_memoria(memoria),
        "tem_proximo_passo": tem_proximo_passo,
        "ultima_reuniao": ultima["meeting_id"] if ultima else None,
        "total_objecoes_preco": total_objecoes_preco,
        "dias_desde_ultima_atividade": dias,
    }


def montar_riscos_calculados(
    opportunity: dict,
    memoria: Optional[dict],
    reunioes: Optional[list],
    agora: Optional[datetime] = None,
) -> dict:
    """Payload de `risks_calculados` (Opportunity Intelligence): riscos
    detectados por `deal_risk_rules.calcular_riscos()` + os sinais que os
    sustentam + o que não pôde ser avaliado (nunca omitido)."""
    from agent.deal_risk_rules import calcular_riscos

    sinais = calcular_sinais(opportunity, memoria, reunioes, agora)
    nao_avaliados = [dict(NAO_AVALIADO_COMPETITOR)]

    if (opportunity.get("status") or "open") != "open":
        return {"disponivel": True, "encerrada": True, "riscos": [], "sinais": sinais, "nao_avaliados": []}

    if sinais["tem_proximo_passo"] is None:
        nao_avaliados.append({
            "risco": "NO_NEXT_STEP",
            "motivo": "Nenhuma reunião vinculada a esta oportunidade para verificar o próximo passo.",
        })
    if sinais["dias_desde_ultima_atividade"] is None:
        nao_avaliados.append({
            "risco": "STALE_OPPORTUNITY",
            "motivo": "Sem data de atividade registrada nesta oportunidade.",
        })

    riscos = calcular_riscos(
        estado_meddpicc=sinais["estado_meddpicc"],
        tem_proximo_passo=sinais["tem_proximo_passo"] is not False,
        total_objecoes_preco=sinais["total_objecoes_preco"],
        competidor_em_vantagem=False,
        dias_desde_ultima_atividade=sinais["dias_desde_ultima_atividade"] or 0,
    )
    return {"disponivel": True, "encerrada": False, "riscos": riscos, "sinais": sinais, "nao_avaliados": nao_avaliados}
