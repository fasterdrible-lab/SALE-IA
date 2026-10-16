"""
SALEIA — agent/readiness_rules.py

Tarefa D1 de docs/tasks-prompt-mestre-v2-restante.md — painel único de
prontidão para o Digital Sales Twin: os 9 critérios objetivos da Fase 25
do "PROMPT MESTRE — SALE-IA V2", cada um com valor atual, alvo, se bate
o alvo e a **origem do número**. Função pura, zero IA/banco — recebe as
contagens ao vivo e as medições em lote já buscadas pelo chamador
(`api/database.py::readiness_contagens_ao_vivo()`/
`ultimas_readiness_medicoes()`). Substitui as medições manuais feitas
por SSH nas V.1.4.136-141.

Origem de cada número (nunca disfarçar uma pela outra):
- `real`  — calculado sobre dado real do critério;
- `proxy` — número real, mas de uma grandeza aproximada (ex.: E2E success
  = 1 − taxa de erro de IA; alucinação crítica vinda de relatório
  anterior à Tarefa D2, que só tinha a alucinação total);
- `gap`   — não existe número; `motivo` diz por quê.

Status: `atinge` / `nao_atinge` / `sem_alvo` (alvo ainda não definido —
recommendation quality, Tarefa C4) / `sem_numero`.
"""

from typing import Optional

ORIGENS_MEDICAO = frozenset({"real", "proxy"})

# Ordem e alvos da tabela "Fase 25 — onde cada critério está" do plano.
# `comparacao`: "max" = valor ≤ alvo; "min" = valor ≥ alvo; None = sem alvo.
CRITERIOS = (
    {"nome": "transcription_reliability", "rotulo": "Transcription reliability (WER)",
     "alvo": 0.10, "comparacao": "max", "fonte": "lote", "alvo_texto": "WER ≤ 10%"},
    {"nome": "event_precision", "rotulo": "Event precision",
     "alvo": 0.90, "comparacao": "min", "fonte": "lote", "alvo_texto": "≥ 90%"},
    {"nome": "objection_classification", "rotulo": "Objection classification",
     "alvo": 0.90, "comparacao": "min", "fonte": "lote", "alvo_texto": "≥ 90%"},
    # "≈ 0" no prompt mestre; 1% é a tolerância adotada aqui (decisão da D1).
    {"nome": "critical_hallucination", "rotulo": "Critical hallucination",
     "alvo": 0.01, "comparacao": "max", "fonte": "lote", "alvo_texto": "≈ 0 (≤ 1%)"},
    {"nome": "policy_violation", "rotulo": "Policy violation",
     "alvo": 0, "comparacao": "max", "fonte": "ao_vivo", "alvo_texto": "= 0"},
    {"nome": "recommendation_quality", "rotulo": "Recommendation quality",
     "alvo": None, "comparacao": None, "fonte": "lote", "alvo_texto": "a definir (Tarefa C4)"},
    {"nome": "e2e_success", "rotulo": "E2E success",
     "alvo": 0.99, "comparacao": "min", "fonte": "ao_vivo", "alvo_texto": "≥ 99%"},
    {"nome": "audit_coverage", "rotulo": "Audit coverage",
     "alvo": 1.0, "comparacao": "min", "fonte": "ao_vivo", "alvo_texto": "100%"},
    {"nome": "human_escalation_functional", "rotulo": "Human escalation functional",
     "alvo": 1.0, "comparacao": "min", "fonte": "gap", "alvo_texto": "100%",
     "motivo_gap": "Mecanismo pronto e testado (V.1.4.134), mas nunca disparado: nada autônomo roda "
                   "em produção (AutonomyPolicy dormente), então não há escalonamento real para medir."},
)
CRITERIOS_POR_NOME = {c["nome"]: c for c in CRITERIOS}


def avaliar_status(valor: Optional[float], alvo, comparacao: Optional[str]) -> str:
    if valor is None:
        return "sem_numero"
    if comparacao is None or alvo is None:
        return "sem_alvo"
    atinge = valor <= alvo if comparacao == "max" else valor >= alvo
    return "atinge" if atinge else "nao_atinge"


def _taxa(numerador: int, denominador: int) -> Optional[float]:
    return round(numerador / denominador, 4) if denominador else None


def medidas_ao_vivo(contagens: dict) -> dict:
    """`{criterio: {valor, origem, amostra, detalhe}}` dos 3 critérios
    calculados a cada chamada."""
    audit = contagens.get("audit") or {}
    e2e = contagens.get("e2e") or {}
    janela = contagens.get("janela_dias")
    return {
        "audit_coverage": {
            "valor": _taxa(audit.get("auditadas", 0), audit.get("chamadas", 0)),
            "origem": "real", "amostra": audit.get("chamadas", 0),
            "detalhe": f"{audit.get('auditadas', 0)} auditorias / {audit.get('chamadas', 0)} chamadas do "
                       f"SalesReasoningEngine (últimos {janela} dias, desde a 1ª auditoria)",
        },
        "e2e_success": {
            "valor": _taxa(e2e.get("sucesso", 0), e2e.get("total", 0)),
            "origem": "proxy", "amostra": e2e.get("total", 0),
            "detalhe": f"1 − taxa de erro de IA: {e2e.get('sucesso', 0)}/{e2e.get('total', 0)} chamadas com "
                       f"sucesso (últimos {janela} dias). Não é E2E de reunião completa (Tarefa D4).",
        },
        "policy_violation": {
            "valor": float(contagens.get("policy_violations") or 0),
            "origem": "real", "amostra": None,
            "detalhe": "PolicyViolationEvent reais: cada (reunião, trechos) 1x, reavaliados com o detector atual (alarmes falsos antigos não contam).",
        },
    }


def montar_painel(contagens_ao_vivo: dict, medicoes_lote: Optional[dict] = None) -> dict:
    """Painel com os 9 critérios na ordem da Fase 25 + resumo. Critério
    de lote sem nenhuma medição registrada aparece como `sem_numero`,
    com a orientação de qual script rodar."""
    ao_vivo = medidas_ao_vivo(contagens_ao_vivo or {})
    medicoes_lote = medicoes_lote or {}

    criterios = []
    for c in CRITERIOS:
        item = {
            "criterio": c["nome"], "rotulo": c["rotulo"], "alvo": c["alvo"], "alvo_texto": c["alvo_texto"],
            "valor": None, "origem": "gap", "amostra": None, "detalhe": None, "medido_em": None,
        }
        if c["fonte"] == "ao_vivo":
            item.update(ao_vivo[c["nome"]])
            item["medido_em"] = "agora"
        elif c["fonte"] == "lote":
            medicao = medicoes_lote.get(c["nome"])
            if medicao:
                item.update({k: medicao.get(k) for k in ("valor", "origem", "amostra", "medido_em")})
                item["detalhe"] = medicao.get("detalhe")
                item["fonte"] = medicao.get("fonte")
            else:
                item["detalhe"] = f"Nenhuma medição registrada ainda — rode {SCRIPT_POR_CRITERIO[c['nome']]} --real."
        else:
            item["detalhe"] = c["motivo_gap"]
        item["status"] = avaliar_status(item["valor"], c["alvo"], c["comparacao"])
        criterios.append(item)

    contagem = {s: 0 for s in ("atinge", "nao_atinge", "sem_alvo", "sem_numero")}
    for item in criterios:
        contagem[item["status"]] += 1
    return {
        "criterios": criterios,
        "resumo": {
            **contagem,
            "total": len(criterios),
            # Critério de entrada no Digital Twin (plano): os 9 no alvo,
            # com número real (proxy não conta).
            "pronto_para_digital_twin": all(
                i["status"] == "atinge" and i["origem"] == "real" for i in criterios
            ),
        },
    }


SCRIPT_POR_CRITERIO = {
    "transcription_reliability": "scripts/transcription_benchmark_run.py",
    "event_precision": "scripts/quality_monitoring_golden_run.py",
    "objection_classification": "scripts/quality_monitoring_golden_run.py",
    "critical_hallucination": "scripts/quality_monitoring_golden_run.py",
    "recommendation_quality": "scripts/recommendation_quality_run.py",
}


def medicoes_do_golden_dataset(relatorio: dict) -> list:
    """Converte o relatório de `quality_monitoring_golden_runner.
    montar_relatorio_metricas()` nas medições a registrar. Alucinação
    crítica é `real` desde a Tarefa D2; relatório antigo, sem ela, cai
    no `proxy` da alucinação total."""
    amostra = (relatorio or {}).get("amostra") or {}
    medicoes = []
    # Tarefa A7: event_precision real (por tipo, contra expected_events).
    if isinstance(relatorio.get("event_precision"), (int, float)):
        medicoes.append({"criterio": "event_precision", "valor": relatorio["event_precision"],
                         "origem": "real", "amostra": amostra.get("eventos_previstos"),
                         "detalhe": {"event_recall": relatorio.get("event_recall")}})
    if relatorio.get("objection_precision") is not None:
        medicoes.append({"criterio": "objection_classification", "valor": relatorio["objection_precision"],
                         "origem": "real", "amostra": amostra.get("objecao_total")})
    if relatorio.get("critical_hallucination_rate") is not None:
        # Tarefa D2: alucinação crítica real (preço/número, promessa ou
        # dado do cliente inventado), por cenário.
        medicoes.append({"criterio": "critical_hallucination", "valor": relatorio["critical_hallucination_rate"],
                         "origem": "real", "amostra": amostra.get("cenarios_avaliados_criticas"),
                         "detalhe": {"casos": relatorio.get("alucinacoes_criticas") or [],
                                     "hallucination_rate_total": relatorio.get("hallucination_rate")}})
    elif relatorio.get("hallucination_rate") is not None:
        medicoes.append({"criterio": "critical_hallucination", "valor": relatorio["hallucination_rate"],
                         "origem": "proxy", "amostra": amostra.get("afirmacoes_total"),
                         "detalhe": {"nota": "alucinação total — relatório anterior à Tarefa D2"}})
    return medicoes


def medicao_da_transcricao(resumo_por_provider: dict, provider_ativo: Optional[str]) -> Optional[dict]:
    """WER do provider de transcrição ativo em produção; os outros vão no
    detalhe. Sem número para o ativo → `None` (nunca troca pelo melhor
    provider calado)."""
    resumo = (resumo_por_provider or {}).get(provider_ativo) or {}
    if resumo.get("wer_medio") is None:
        return None
    return {"criterio": "transcription_reliability", "valor": resumo["wer_medio"], "origem": "real",
            "amostra": resumo.get("n") or resumo.get("amostra"),
            "detalhe": {"provider_ativo": provider_ativo, "por_provider": resumo_por_provider}}
