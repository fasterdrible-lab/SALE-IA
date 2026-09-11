"""
SALEIA — agent/meddpicc_rules.py

Opportunity Qualification Engine (FASE 4 / TAREFA 4.1 do "PROMPT MESTRE
— SALE-IA V2"). Função pura, nenhuma chamada de IA, nenhum acesso a
banco — mesmo padrão de agent/spin_coverage_rules.py e
agent/question_gap_rules.py (Fase 3): computa estado a partir de fatos
JÁ estruturados e evidenciados, nunca extrai/infere a partir de
transcrição livre (fora do enunciado da Tarefa 4.1).

Escopo desta tarefa: só o motor de qualificação MEDDPICC em si — Tarefa
4.2 (Deal Risk, regras determinísticas de risco) NÃO começou.

Regra de evidência — mesma disciplina de SalesEvent/SalesEvidence/SPIN
(Fases 1 e 3), estendida aqui por decisão deliberada desta rodada (o
prompt mestre não repete a frase "não invente informação faltante" na
Tarefa 4.1, mas o schema pedido — status/confidence/evidence[] por item
— só faz sentido com a mesma disciplina): nenhum item pode avançar de
UNKNOWN sem pelo menos uma evidence_quote real.
"""

# Os 8 itens do MEDDPICC (TAREFA 4.1), na ordem literal do prompt mestre.
MEDDPICC_ITENS = (
    "metrics",
    "economic_buyer",
    "decision_criteria",
    "decision_process",
    "paper_process",
    "identify_pain",
    "champion",
    "competition",
)

# Progressão de status — usada tanto para validar quanto para decidir
# qual status "vence" quando há múltiplos fatos sobre o mesmo item.
STATUS_ORDEM = ("UNKNOWN", "PARTIAL", "CONFIRMED")
STATUS_VALIDOS = frozenset(STATUS_ORDEM)

# Nível geral de qualificação — usado por `resumo_qualificacao()` pra dar
# o veredito único que os 3 cenários de teste da Tarefa 4.1 pedem (mal
# qualificada / intermediária / enterprise avançada). Limiares por
# contagem de itens CONFIRMED entre os 8 — decisão desta rodada (o
# prompt mestre não define o número exato, só pede os 3 cenários de
# teste), mesmo tipo de decisão documentada de `STAGE_PRIORIDADE_PADRAO`
# em `agent/question_gap_rules.py` (Tarefa 3.2).
NIVEL_MINIMO_AVANCADA = 6
NIVEL_MINIMO_INTERMEDIARIA = 3


def _validar_fato(fato: dict) -> None:
    item = fato.get("item")
    if item not in MEDDPICC_ITENS:
        raise ValueError(f"item MEDDPICC inválido: {item!r} (esperado um de {MEDDPICC_ITENS})")

    status = fato.get("status")
    if status not in STATUS_VALIDOS:
        raise ValueError(f"status inválido: {status!r} (esperado um de {STATUS_ORDEM})")

    confidence = fato.get("confidence")
    try:
        confidence_valor = float(confidence)
    except (TypeError, ValueError):
        raise ValueError(f"confidence inválida: {confidence!r} (esperado float entre 0 e 1)")
    if not (0.0 <= confidence_valor <= 1.0):
        raise ValueError(f"confidence fora do intervalo [0, 1]: {confidence_valor!r}")

    if status != "UNKNOWN" and not (fato.get("evidence_quote") or "").strip():
        raise ValueError(
            f"evidence_quote obrigatória para {item!r} com status={status!r} "
            "(regra: não inventar informação faltante)"
        )


def calcular_qualificacao_meddpicc(fatos_conhecidos: list) -> dict:
    """Computa o estado dos 8 itens MEDDPICC a partir de fatos já
    estruturados e evidenciados.

    `fatos_conhecidos`: lista de {"item", "status", "confidence",
    "evidence_quote"} — cada um validado (`ValueError` propaga na
    primeira violação, nenhum fato entra parcialmente).

    Retorna `{item: {"status", "confidence", "evidence": [...]}}` para
    os 8 itens (item sem nenhum fato fica `UNKNOWN`/`0.0`/`[]`).

    Agregação quando há múltiplos fatos sobre o mesmo item: `status`
    nunca regride (usa o mais avançado já visto na ordem UNKNOWN →
    PARTIAL → CONFIRMED — mesmo espírito de "informação não desaparece"
    já usado em `agent/opportunity_memory_rules.py`), `confidence` usa o
    maior valor já visto, `evidence` acumula todas as quotes na ordem
    recebida (nunca descarta)."""
    for fato in fatos_conhecidos:
        _validar_fato(fato)

    ordem_status = {status: indice for indice, status in enumerate(STATUS_ORDEM)}
    estado = {item: {"status": "UNKNOWN", "confidence": 0.0, "evidence": []} for item in MEDDPICC_ITENS}

    for fato in fatos_conhecidos:
        item_estado = estado[fato["item"]]
        if ordem_status[fato["status"]] > ordem_status[item_estado["status"]]:
            item_estado["status"] = fato["status"]
        item_estado["confidence"] = max(item_estado["confidence"], float(fato["confidence"]))
        item_estado["evidence"].append(fato["evidence_quote"])

    return estado


def resumo_qualificacao(estado_meddpicc: dict) -> dict:
    """Resumo de alto nível do estado MEDDPICC: contagem de itens por
    status e um `nivel` geral (`fraca`/`intermediaria`/`avancada`),
    baseado em quantos dos 8 itens estão `CONFIRMED` — resposta direta
    aos 3 cenários de teste da Tarefa 4.1 (oportunidade mal qualificada/
    intermediária/enterprise avançada)."""
    contagem = {status: 0 for status in STATUS_ORDEM}
    for item in MEDDPICC_ITENS:
        contagem[estado_meddpicc.get(item, {}).get("status", "UNKNOWN")] += 1

    confirmados = contagem["CONFIRMED"]
    if confirmados >= NIVEL_MINIMO_AVANCADA:
        nivel = "avancada"
    elif confirmados >= NIVEL_MINIMO_INTERMEDIARIA:
        nivel = "intermediaria"
    else:
        nivel = "fraca"

    return {"nivel": nivel, "contagem_por_status": contagem}


def itens_pendentes(estado_meddpicc: dict) -> list:
    """Itens MEDDPICC ainda não `CONFIRMED` (inclui `PARTIAL` e
    `UNKNOWN`), na ordem literal do prompt mestre — útil pra saber o que
    ainda falta qualificar."""
    return [
        item
        for item in MEDDPICC_ITENS
        if estado_meddpicc.get(item, {}).get("status", "UNKNOWN") != "CONFIRMED"
    ]
