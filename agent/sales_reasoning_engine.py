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

**Contrato (rodada anterior)**: schema/validação de entrada e saída —
`construir_input_vazio()`/`validar_input_raciocinio()`/
`montar_saida_raciocinio()`/`validar_output_raciocinio()` abaixo.

**Motor real (esta rodada, confirmado explicitamente pelo usuário)**:
`raciocinar_async()` — diferente das Fases 1-6 (regras determinísticas
sobre fatos já estruturados), este é o primeiro motor do roadmap que
precisa de raciocínio real via IA: sintetizar os 11 inputs (todos já
calculados por módulos determinísticos ou por memória persistida) numa
única recomendação coerente é, por natureza, um julgamento qualitativo,
não uma fórmula. Usa o mesmo caminho de produção dos 5 agentes de
`agent/multiagente/` (`chamar_ia_com_fallback_claude` — 4 provedores
centrais com fallback pra conta Claude pessoal do vendedor em caso de
esgotamento), prompt em `agent/prompt_templates/
sales_reasoning_engine.txt`. **Não integrado a `orquestrador.py`/
`processador_tempo_real.py` ainda** — mesma disciplina de "construir a
peça, decisão de plugar em produção é separada" já usada em todas as
Fases 1-6.

Golden Dataset de 50+ cenários (pedido explícito do prompt mestre,
validado semanticamente via `llm-rubric`, não por igualdade literal de
frase) vive em `evals/datasets/sales_reasoning/` — mesmo harness
Promptfoo do Coach/Finance (Fase 2), criado mas **nunca rodado nesta
rodada** (custa dinheiro real por cenário, mesma disciplina de
`evals/promptfooconfig.yaml`).

Nome do arquivo/módulo deliberadamente foge do padrão `*_rules.py` das
Fases 1-6 — o prompt mestre chama isso literalmente de "novo serviço:
SalesReasoningEngine", não mais uma função de regra isolada.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from agent.multiagente.claude_fallback import chamar_ia_com_fallback_claude
from api import ai_features

logger = logging.getLogger(__name__)

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

# Vocabulário fechado de `recommended_framework` — mesma disciplina das
# Fases 1-6 (taxonomias fechadas, nunca texto livre inventado pela IA
# por chamada). Cobre os frameworks já construídos no roadmap: os 4
# estágios SPIN (Fase 3), qualificação MEDDPICC (Fase 4), investigação
# de objeção antes de negociar (Fase 6.1), as 7 estratégias de
# negociação consultiva sob um rótulo único (Fase 6.2 — o motor escolhe
# a estratégia específica dentro de `next_best_action`, não aqui),
# mitigação de risco (Deal Risk, Fase 4.2) e fechamento.
SALES_REASONING_FRAMEWORKS = (
    "SPIN_SITUATION",
    "SPIN_PROBLEM",
    "SPIN_IMPLICATION",
    "SPIN_NEED_PAYOFF",
    "MEDDPICC_QUALIFICATION",
    "OBJECTION_INVESTIGATION",
    "NEGOTIATION",
    "RISK_MITIGATION",
    "CLOSING",
)

_PROMPT_PATH = Path(__file__).parent / "prompt_templates" / "sales_reasoning_engine.txt"

_SYSTEM_PROMPT = (
    "Você é o SalesReasoningEngine, o cérebro central de raciocínio comercial "
    "do co-piloto de vendas SALEIA. Responda SEMPRE em JSON válido, sem texto "
    "antes ou depois."
)


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


# Fase 18 / Tarefa 18.4 ("PROMPT MESTRE — SALE-IA V2", Audit Trail):
# versões literais deste módulo — bump manual sempre que o prompt
# (`agent/prompt_templates/sales_reasoning_engine.txt`) ou o contrato de
# entrada/saída deste arquivo mudar. Seção 34 do prompt mestre ("qual
# versão recomendou isso") não define formato — string livre, mesma
# decisão já tomada no schema do `AuditTrailEntry`.
_PROMPT_VERSION = "sales_reasoning_engine.v1"
_RULE_VERSION = "sales_reasoning_engine.v1"


def _registrar_audit_trail(
    bundle: dict,
    meeting_id: Optional[str],
    *,
    resultado,
    model: Optional[str] = None,
    reason: Optional[str] = None,
) -> None:
    """Grava 1 `AuditTrailEntry` por chamada real de `raciocinar_async()`
    — sucesso ou falha (choke-point único, nenhum outro caminho do
    sistema chama a IA do SalesReasoningEngine). Best-effort: uma falha
    aqui nunca pode derrubar o raciocínio real, mesma disciplina de todo
    hook best-effort já usado no projeto (Prompt Injection, Shadow
    Mode). `data_used` guarda só quais dos 11 campos de entrada vieram
    preenchidos, nunca o conteúdo — evita duplicar transcrição/PII já
    persistida em `MeetingMemory`/`OpportunityMemory` dentro de uma
    tabela de auditoria."""
    try:
        from api.database import criar_audit_trail_entry

        campos_preenchidos = sorted(k for k, v in bundle.items() if v is not None)
        if isinstance(resultado, dict):
            result_texto = f"{resultado.get('recommended_framework')}: {resultado.get('next_best_action')}"
        else:
            result_texto = str(resultado)
        criar_audit_trail_entry(
            actor="sales_reasoning_engine",
            action="gerar_recomendacao",
            reason=reason or "SalesReasoningEngine.raciocinar_async",
            result=result_texto,
            meeting_id=meeting_id,
            data_used={"campos_preenchidos": campos_preenchidos},
            model=model,
            prompt_version=_PROMPT_VERSION,
            rule_version=_RULE_VERSION,
        )
    except Exception as _e:
        logger.debug("[SalesReasoningEngine] Falha ao gravar audit trail (melhor esforço): %s", _e)


async def raciocinar_async(
    entrada: dict,
    usuario_id: Optional[str] = None,
    meeting_id: Optional[str] = None,
) -> dict:
    """Motor real do SalesReasoningEngine: sintetiza os 11 inputs (Fases
    1-6 + memória/grafo/RAG/contexto do vendedor/padrões históricos) numa
    única recomendação via IA.

    `entrada` pode vir parcialmente preenchida (campos ausentes viram
    `None`, mesma semântica de `construir_input_vazio()`) — nenhum dos
    11 campos é obrigatório. Levanta `ValueError` se `entrada` tiver
    chave desconhecida (`validar_input_raciocinio`) ou se a resposta da
    IA não bater com o contrato de saída (`montar_saida_raciocinio`) —
    dado de domínio, mesma convenção de `SalesEvent`/`SalesEvidence`
    (Fases 1-6): nunca falha silenciosa como `AiUsageEvent`.

    Toda chamada (sucesso ou falha) grava um `AuditTrailEntry` (Fase
    18.4) — ver `_registrar_audit_trail()`.
    """
    validar_input_raciocinio(entrada)
    bundle = {**construir_input_vazio(), **entrada}

    template = _PROMPT_PATH.read_text(encoding="utf-8")
    prompt = template
    for campo in SALES_REASONING_INPUT_CAMPOS:
        valor = bundle[campo]
        serializado = json.dumps(valor, ensure_ascii=False) if valor is not None else "null"
        prompt = prompt.replace("{" + campo + "}", serializado)

    try:
        resposta = await chamar_ia_com_fallback_claude(
            _SYSTEM_PROMPT,
            prompt,
            usuario_id,
            feature=ai_features.SALES_REASONING_RACIOCINIO,
            meeting_id=meeting_id,
        )

        saida = montar_saida_raciocinio(
            current_state=resposta.get("current_state"),
            recommended_framework=resposta.get("recommended_framework"),
            next_best_action=resposta.get("next_best_action"),
            reason=resposta.get("reason"),
            confidence=resposta.get("confidence"),
            hypotheses=resposta.get("hypotheses"),
            evidence=resposta.get("evidence"),
            missing_information=resposta.get("missing_information"),
            next_best_question=resposta.get("next_best_question"),
            avoid=resposta.get("avoid"),
        )
    except Exception as erro:
        _registrar_audit_trail(bundle, meeting_id, resultado=f"erro: {type(erro).__name__}: {erro}")
        raise

    _registrar_audit_trail(
        bundle,
        meeting_id,
        model=resposta.get("_modelo_ia"),
        reason=saida["reason"],
        resultado=saida,
    )
    return saida
