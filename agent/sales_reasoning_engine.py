"""
SALEIA — agent/sales_reasoning_engine.py

SalesReasoningEngine (FASE 7 / TAREFA 7.1 do "PROMPT MESTRE — SALE-IA
V2") — "o cérebro central" que consolida os motores das Fases 1-6
(SPINState, MEDDPICCState, BuyerMotivation, Objections,
BehavioralSignals, Deal Risk) junto de MeetingMemory/OpportunityMemory/
OpportunityGraph/RAGContext/SellerContext/HistoricalPatterns num único
raciocínio: estado atual, hipóteses, evidência, informação faltante,
framework recomendado, próxima melhor ação/pergunta, o que evitar,
motivo e confiança.

**Escopo desta rodada, decisão explícita do usuário**: só o CONTRATO —
schema/validação de entrada e saída — sem nenhuma chamada de IA. As
Fases 1-6 inteiras evitaram IA deliberadamente (regras determinísticas
sobre fatos já estruturados); esta tarefa é estruturalmente diferente —
o próprio prompt mestre pede um Golden Dataset de 50+ cenários
validados SEMANTICAMENTE ("o teste não deve depender de igualdade
literal de frase"), o que só faz sentido para um motor com raciocínio
real via IA. Construir esse motor de verdade (novo prompt/agente) e o
Golden Dataset ficam para uma tarefa futura, quando o usuário decidir —
mesma disciplina de "schema primeiro, decisão de produto depois" já
usada em todas as Fases anteriores, só que aplicada aqui a uma decisão
de escopo maior (não uma inferência simples).

Nome do arquivo/módulo deliberadamente foge do padrão `*_rules.py` das
Fases 1-6 — o prompt mestre chama isso literalmente de "novo serviço:
SalesReasoningEngine", não mais uma função de regra isolada.
"""

from typing import Optional

# Os 11 inputs literais do prompt mestre — o contrato de ENTRADA do
# SalesReasoningEngine. Cada um é o output de uma peça já construída
# (ou a construir) nas Fases 1-6/MeetingMemory/OpportunityMemory já
# existentes: `spin_state` vem de `spin_coverage_rules.calcular_
# cobertura_spin()`, `meddpicc_state` de `meddpicc_rules.calcular_
# qualificacao_meddpicc()`, `buyer_motivation` de `buyer_motivation_
# rules.motivacao_dominante()`, `objections` de uma lista de
# `objection_rules.registrar_objecao()`, `behavioral_signals` de
# `behavioral_signal_rules.detectar_sinais()`.
SALES_REASONING_INPUT_CAMPOS = (
    "meeting_memory",
    "opportunity_memory",
    "opportunity_graph",
    "spin_state",
    "meddpicc_state",
    "buyer_motivation",
    "objections",
    "behavioral_signals",
    "rag_context",
    "seller_context",
    "historical_patterns",
)

# Os 10 campos literais de SAÍDA do prompt mestre.
SALES_REASONING_OUTPUT_CAMPOS = (
    "current_state",
    "hypotheses",
    "evidence",
    "missing_information",
    "recommended_framework",
    "next_best_action",
    "next_best_question",
    "avoid",
    "reason",
    "confidence",
)

# Campos de saída que são sempre lista (podem vir vazios, nunca
# ausentes/None) — `next_best_question` fica de fora de propósito: nem
# sempre há uma pergunta a fazer (ex.: quando a ação recomendada não é
# uma pergunta), então é o único campo de texto opcional (`None`
# permitido).
_CAMPOS_LISTA = ("hypotheses", "evidence", "missing_information", "avoid")

# Campos de texto obrigatórios (não podem ser vazios/None).
_CAMPOS_TEXTO_OBRIGATORIOS = ("current_state", "recommended_framework", "next_best_action", "reason")


def construir_input_vazio() -> dict:
    """Bundle de entrada do SalesReasoningEngine com os 11 campos
    literais do prompt mestre, todos `None` por padrão — nenhum é
    obrigatoriamente preenchido (numa reunião real, nem todos existem
    ainda em qualquer ponto da conversa; ex.: `meddpicc_state` pode
    não ter nenhum item `CONFIRMED` na abertura da call)."""
    return {campo: None for campo in SALES_REASONING_INPUT_CAMPOS}


def validar_input_raciocinio(entrada: dict) -> None:
    """Valida que `entrada` só usa as chaves conhecidas do contrato de
    entrada — detecta campo inventado/erro de digitação cedo. Não
    exige que nenhum campo específico esteja preenchido (todos são
    opcionais, ver `construir_input_vazio()`)."""
    chaves_desconhecidas = set(entrada.keys()) - set(SALES_REASONING_INPUT_CAMPOS)
    if chaves_desconhecidas:
        raise ValueError(
            f"chaves desconhecidas em SalesReasoningInput: {sorted(chaves_desconhecidas)} "
            f"(esperado apenas {SALES_REASONING_INPUT_CAMPOS})"
        )


def montar_saida_raciocinio(
    current_state: str,
    recommended_framework: str,
    next_best_action: str,
    reason: str,
    confidence: float,
    hypotheses: Optional[list] = None,
    evidence: Optional[list] = None,
    missing_information: Optional[list] = None,
    next_best_question: Optional[str] = None,
    avoid: Optional[list] = None,
) -> dict:
    """Monta e valida a saída do SalesReasoningEngine — os 10 campos
    literais do prompt mestre. `hypotheses`/`evidence`/`missing_
    information`/`avoid` default pra lista vazia (nunca `None`);
    `next_best_question` é o único texto opcional (pode não haver
    pergunta pra fazer nesse momento)."""
    saida = {
        "current_state": current_state,
        "hypotheses": hypotheses if hypotheses is not None else [],
        "evidence": evidence if evidence is not None else [],
        "missing_information": missing_information if missing_information is not None else [],
        "recommended_framework": recommended_framework,
        "next_best_action": next_best_action,
        "next_best_question": next_best_question,
        "avoid": avoid if avoid is not None else [],
        "reason": reason,
        "confidence": confidence,
    }
    validar_output_raciocinio(saida)
    return saida


def validar_output_raciocinio(saida: dict) -> None:
    """Valida a saída do SalesReasoningEngine — os 10 campos literais
    do prompt mestre, cada um com seu tipo/obrigatoriedade."""
    for campo in _CAMPOS_TEXTO_OBRIGATORIOS:
        if not (saida.get(campo) or "").strip():
            raise ValueError(f"{campo} obrigatório e não pode ser vazio")

    for campo in _CAMPOS_LISTA:
        if not isinstance(saida.get(campo), list):
            raise ValueError(f"{campo} deve ser uma lista (pode ser vazia, nunca None/ausente)")

    next_best_question = saida.get("next_best_question")
    if next_best_question is not None and not isinstance(next_best_question, str):
        raise ValueError("next_best_question deve ser str ou None")

    confidence = saida.get("confidence")
    try:
        confidence_valor = float(confidence)
    except (TypeError, ValueError):
        raise ValueError(f"confidence inválida: {confidence!r} (esperado float entre 0 e 1)")
    if not (0.0 <= confidence_valor <= 1.0):
        raise ValueError(f"confidence fora do intervalo [0, 1]: {confidence_valor!r}")
