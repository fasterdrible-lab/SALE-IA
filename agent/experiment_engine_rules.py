"""
SALEIA — agent/experiment_engine_rules.py

Experiment Engine (FASE 14 / TAREFAS 14.1 e 14.2 do "PROMPT MESTRE —
SALE-IA V2"). Função pura, nenhuma chamada de IA, nenhum acesso a
banco — mesmo padrão de agent/negotiation_rules.py/agent/
deal_risk_rules.py.

TAREFA 14.1 — transforma uma hipótese de vendas num teste formal
(hypothesis/control/treatment/metric), schema literal do exemplo do
prompt mestre: hypothesis="Quantificar impacto antes de preço melhora
avanço.", control="fluxo atual", treatment="pergunta de impacto",
metric="stage advancement".

TAREFA 14.2 — configura o teste como A/B controlado
(pilot_group/control_group/duration/minimum_sample). Regra de
segurança explícita do prompt mestre — "experimento não pode
envolver: informação falsa, discriminação, preço enganoso, escassez
falsa, ocultação de informação relevante" — garantida
estruturalmente, não só por instrução: um experimento só é montado
com uma atestação explícita dos 5 itens (`EXPERIMENT_SAFETY_CHECKS`),
cada um fail-closed (ausente/False é sempre recusado, nunca aprovado
por omissão) — mesma disciplina de evidência obrigatória já usada em
SalesEvent/SalesEvidence (Fase 1) e nas guardas estruturais de
MEDDPICC/Objeções/Negociação (Fases 4/6).
"""

# TAREFA 14.2 — os 5 itens de segurança literais do prompt mestre.
# Um experimento só é montado com atestação explícita True em todos —
# omitir qualquer um levanta ValueError.
EXPERIMENT_SAFETY_CHECKS = (
    "no_false_information",
    "no_discrimination",
    "no_deceptive_pricing",
    "no_false_scarcity",
    "no_information_concealment",
)


def validar_experiment_hypothesis(hypothesis: str, control: str, treatment: str, metric: str) -> None:
    """TAREFA 14.1 — os 4 campos literais do prompt mestre são
    obrigatórios e não-vazios. Sem os quatro não há teste possível de
    ser rodado nem analisado depois."""
    campos = {"hypothesis": hypothesis, "control": control, "treatment": treatment, "metric": metric}
    for nome, valor in campos.items():
        if not valor or not str(valor).strip():
            raise ValueError(f"{nome} obrigatório e não pode ser vazio")


def montar_experiment_hypothesis(hypothesis: str, control: str, treatment: str, metric: str) -> dict:
    """Monta o registro de TAREFA 14.1 já validado."""
    validar_experiment_hypothesis(hypothesis, control, treatment, metric)
    return {
        "hypothesis": hypothesis,
        "control": control,
        "treatment": treatment,
        "metric": metric,
    }


def validar_seguranca_experimento(safety_attestation: dict) -> None:
    """TAREFA 14.2 — recusa (ValueError) qualquer experimento cuja
    atestação de segurança não confirme True nos 5 itens literais do
    prompt mestre. Fail-closed: item ausente é tratado como não
    atestado, nunca assumido seguro por omissão."""
    if not isinstance(safety_attestation, dict):
        raise ValueError("safety_attestation precisa ser um dict com os 5 itens de EXPERIMENT_SAFETY_CHECKS")
    for check in EXPERIMENT_SAFETY_CHECKS:
        if safety_attestation.get(check) is not True:
            raise ValueError(
                f"experimento recusado: item de segurança obrigatório não atestado ({check!r}) — "
                "experimento não pode envolver informação falsa, discriminação, preço enganoso, "
                "escassez falsa ou ocultação de informação relevante"
            )


def validar_experiment_config(
    pilot_group: str,
    control_group: str,
    duration: int,
    minimum_sample: int,
    safety_attestation: dict,
) -> None:
    """TAREFA 14.2 — valida a configuração do teste A/B controlado
    (pilot_group/control_group/duration em dias/minimum_sample)."""
    if not pilot_group or not str(pilot_group).strip():
        raise ValueError("pilot_group obrigatório e não pode ser vazio")
    if not control_group or not str(control_group).strip():
        raise ValueError("control_group obrigatório e não pode ser vazio")
    if pilot_group == control_group:
        raise ValueError("pilot_group e control_group precisam ser grupos distintos")
    if duration is None or duration <= 0:
        raise ValueError("duration precisa ser um inteiro positivo (dias)")
    if minimum_sample is None or minimum_sample <= 0:
        raise ValueError("minimum_sample precisa ser um inteiro positivo")
    validar_seguranca_experimento(safety_attestation)


def montar_experiment_config(
    hypothesis_test: dict,
    pilot_group: str,
    control_group: str,
    duration: int,
    minimum_sample: int,
    safety_attestation: dict,
) -> dict:
    """Monta a configuração completa do experimento A/B controlado
    (TAREFA 14.2) a partir de um `hypothesis_test` já validado pela
    TAREFA 14.1 (`montar_experiment_hypothesis()`)."""
    if not isinstance(hypothesis_test, dict) or "hypothesis" not in hypothesis_test:
        raise ValueError("hypothesis_test precisa ser o resultado de montar_experiment_hypothesis()")
    validar_experiment_hypothesis(
        hypothesis_test.get("hypothesis"),
        hypothesis_test.get("control"),
        hypothesis_test.get("treatment"),
        hypothesis_test.get("metric"),
    )
    validar_experiment_config(pilot_group, control_group, duration, minimum_sample, safety_attestation)

    return {
        **hypothesis_test,
        "pilot_group": pilot_group,
        "control_group": control_group,
        "duration": duration,
        "minimum_sample": minimum_sample,
        "safety_attestation": dict(safety_attestation),
    }
