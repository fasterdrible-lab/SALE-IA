"""
SALEIA — agent/behavioral_signal_rules.py

Behavioral Signal Engine (FASE 5 / TAREFA 5.2 do "PROMPT MESTRE —
SALE-IA V2"). Função pura, nenhuma chamada de IA, nenhum acesso a
banco — mesmo padrão de agent/buyer_motivation_rules.py (Tarefa 5.1).

Objetivo do prompt mestre: "implementar somente sinais observáveis" —
os 6 vieses/sinais comportamentais literais abaixo, cada um exigindo o
trecho real da conversa que o sustenta. "Evitar alegações como 'o
cérebro reptiliano foi ativado'": este módulo nunca gera explicação
livre/pseudocientífica — cada sinal tem uma descrição canônica sóbria e
fixa (`DESCRICOES_SINAIS`), nunca um texto inventado por chamador ou
por IA.
"""

# Os 6 sinais comportamentais observáveis (TAREFA 5.2), literais do
# prompt mestre.
BEHAVIORAL_SIGNAL_TIPOS = frozenset({
    "LOSS_AVERSION",
    "STATUS_QUO_BIAS",
    "SOCIAL_PROOF_REQUEST",
    "AUTHORITY_REQUEST",
    "PRICE_ANCHOR",
    "RISK_AVERSION",
})

# Descrição canônica e sóbria de cada sinal — nunca um texto livre
# gerado por IA/chamador (regra do prompt mestre: evitar alegações
# pseudocientíficas). Descreve o comportamento OBSERVÁVEL, nunca um
# mecanismo interno/neurológico especulativo.
DESCRICOES_SINAIS = {
    "LOSS_AVERSION": "Cliente enfatiza o que pode perder mais do que o que pode ganhar.",
    "STATUS_QUO_BIAS": "Cliente prefere manter a solução/processo atual mesmo reconhecendo o problema.",
    "SOCIAL_PROOF_REQUEST": "Cliente pede referências, cases ou outros clientes semelhantes antes de decidir.",
    "AUTHORITY_REQUEST": "Cliente pede validação de uma autoridade/especialista externo antes de decidir.",
    "PRICE_ANCHOR": "Cliente ancora a negociação num valor de referência (concorrente, orçamento anterior, etc.).",
    "RISK_AVERSION": "Cliente prioriza evitar risco/erro sobre maximizar o ganho potencial.",
}


def _validar_sinal(sinal: dict) -> None:
    tipo = sinal.get("signal")
    if tipo not in BEHAVIORAL_SIGNAL_TIPOS:
        raise ValueError(f"signal inválido: {tipo!r} (esperado um de {sorted(BEHAVIORAL_SIGNAL_TIPOS)})")

    if not (sinal.get("evidence_quote") or "").strip():
        raise ValueError(
            f"evidence_quote obrigatória para o sinal {tipo!r} — regra do prompt mestre: "
            "'cada sinal precisa apresentar trecho da conversa que o sustenta'"
        )


def validar_sinais_comportamentais(sinais: list) -> None:
    """Valida uma lista de sinais comportamentais (`{"signal",
    "evidence_quote"}` cada) — `ValueError` propaga na primeira
    violação, nenhum sinal entra parcialmente."""
    for sinal in sinais:
        _validar_sinal(sinal)


def detectar_sinais(sinais_observados: list) -> list:
    """Valida `sinais_observados` e devolve cada um enriquecido com a
    descrição canônica sóbria do tipo (`DESCRICOES_SINAIS` — nunca um
    texto livre) — `[{"signal", "evidence_quote", "descricao"}]`, na
    mesma ordem recebida."""
    validar_sinais_comportamentais(sinais_observados)
    return [
        {
            "signal": sinal["signal"],
            "evidence_quote": sinal["evidence_quote"],
            "descricao": DESCRICOES_SINAIS[sinal["signal"]],
        }
        for sinal in sinais_observados
    ]


def contagem_por_sinal(sinais_observados: list) -> dict:
    """Contagem de ocorrências por tipo de sinal (`{signal: count}`),
    só para os tipos efetivamente observados — útil pra saber quais
    vieses apareceram mais numa reunião."""
    validar_sinais_comportamentais(sinais_observados)
    contagem = {}
    for sinal in sinais_observados:
        contagem[sinal["signal"]] = contagem.get(sinal["signal"], 0) + 1
    return contagem
