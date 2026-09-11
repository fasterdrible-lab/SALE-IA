"""
SALEIA — agent/negotiation_rules.py

Negotiation Engine (FASE 6 / TAREFA 6.2 do "PROMPT MESTRE — SALE-IA
V2"). Função pura, nenhuma chamada de IA, nenhum acesso a banco — mesmo
padrão de agent/objection_rules.py (Tarefa 6.1), sobre o qual esta
tarefa constrói diretamente.

Regra explícita do prompt mestre — "nunca permitir: ameaça, mentira,
escassez falsa, manipulação, informações inventadas" — garantida por
construção, não por instrução: `NEGOTIATION_TIPOS` é um vocabulário
FECHADO com só as 7 estratégias consultivas abaixo. Nenhuma tática
manipulativa (desconto arbitrário, ameaça, urgência falsa) é sequer
representável neste módulo — não existe campo de texto livre em lugar
nenhum da API pública.

Teste específico do prompt mestre reproduzido: cliente diz "Está caro."
→ resultado proibido "Posso dar 20% agora." → resultado esperado:
estratégia de INVESTIGAÇÃO. Implementado reaproveitando `agent.
objection_rules.precisa_investigar()` (Tarefa 6.1) — enquanto uma
objeção não foi investigada de verdade, só estratégias investigativas
são permitidas; qualquer tentativa de pular direto pra uma estratégia
pós-investigação (inclui `VALUE_REFRAME`, que é o caminho mais próximo
de "oferecer algo" neste vocabulário) é recusada.
"""

from typing import Optional

from agent.objection_rules import precisa_investigar

# As 7 estratégias consultivas (TAREFA 6.2), inspiradas em negociação
# consultiva/tática (ex.: Chris Voss) — vocabulário fechado.
NEGOTIATION_TIPOS = frozenset({
    "LABEL",
    "MIRROR",
    "CALIBRATED_QUESTION",
    "SUMMARIZE",
    "CLARIFY",
    "VALUE_REFRAME",
    "RISK_REDUCTION",
})

# Estratégias usadas ENQUANTO a causa raiz ainda não foi investigada —
# todas puramente exploratórias, nenhuma propõe nada ao cliente ainda.
ESTRATEGIAS_INVESTIGATIVAS = frozenset({"LABEL", "MIRROR", "CALIBRATED_QUESTION", "CLARIFY"})

# Estratégias só permitidas DEPOIS que a causa raiz já foi investigada
# (`precisa_investigar()` retornou `False`) — aqui sim é seguro
# responder ao que foi de fato entendido.
ESTRATEGIAS_POS_INVESTIGACAO = frozenset({"SUMMARIZE", "VALUE_REFRAME", "RISK_REDUCTION"})

# Descrição canônica e sóbria de cada estratégia — nunca texto livre
# gerado por chamador/IA (mesmo espírito de `DESCRICOES_SINAIS` em
# `agent/behavioral_signal_rules.py`, Fase 5). Nenhuma menciona
# desconto/ameaça/urgência falsa — a garantia central da Tarefa 6.2.
DESCRICOES_ESTRATEGIAS = {
    "LABEL": "Nomeia a emoção/preocupação percebida no cliente, sem julgar (ex.: 'parece que o timing pesa bastante aqui').",
    "MIRROR": "Repete as últimas palavras do cliente pra convidar mais elaboração, sem interpretar.",
    "CALIBRATED_QUESTION": "Pergunta aberta que devolve a decisão ao cliente e revela mais informação (ex.: 'o que faria esse valor fazer sentido pra você?').",
    "SUMMARIZE": "Resume o que foi entendido e busca confirmação explícita do cliente antes de avançar.",
    "CLARIFY": "Pede esclarecimento direto sobre um ponto ambíguo levantado pelo cliente.",
    "VALUE_REFRAME": "Reconecta o preço ao valor/resultado concreto já validado com o cliente, sem propor número novo.",
    "RISK_REDUCTION": "Reduz o risco percebido da decisão (ex.: prova social real, piloto, garantia contratual), sempre com prazos e condições reais.",
}


def _validar_estrategia(estrategia: str) -> None:
    if estrategia not in NEGOTIATION_TIPOS:
        raise ValueError(f"estrategia inválida: {estrategia!r} (esperado um de {sorted(NEGOTIATION_TIPOS)})")


def recomendar_estrategia(
    objection_spoken: dict,
    root_cause_hypothesis: Optional[dict] = None,
    estrategia_desejada: Optional[str] = None,
) -> dict:
    """Recomenda uma estratégia de negociação consultiva pra uma
    objeção, sempre respeitando se a causa raiz já foi investigada
    (reaproveita `objection_rules.precisa_investigar()`, Tarefa 6.1).

    - Sem `estrategia_desejada`: escolhe `CALIBRATED_QUESTION` enquanto
      a objeção não foi investigada, ou `VALUE_REFRAME` depois que foi.
    - Com `estrategia_desejada`: valida que está no vocabulário fechado
      e, se a objeção ainda precisa de investigação, recusa
      (`ValueError`) qualquer estratégia fora de `ESTRATEGIAS_
      INVESTIGATIVAS` — reproduz a regra do prompt mestre: "'Está
      caro.' não pode resultar em 'posso dar 20% agora', o esperado é
      estratégia de investigação"."""
    precisa = precisa_investigar(objection_spoken, root_cause_hypothesis)

    if estrategia_desejada is not None:
        _validar_estrategia(estrategia_desejada)
        if precisa and estrategia_desejada not in ESTRATEGIAS_INVESTIGATIVAS:
            raise ValueError(
                f"objeção ainda não foi investigada (precisa_investigar=True) — estratégia "
                f"{estrategia_desejada!r} não é permitida agora, use uma de "
                f"{sorted(ESTRATEGIAS_INVESTIGATIVAS)} primeiro"
            )
        estrategia = estrategia_desejada
    else:
        estrategia = "CALIBRATED_QUESTION" if precisa else "VALUE_REFRAME"

    return {
        "estrategia": estrategia,
        "precisa_investigar": precisa,
        "descricao": DESCRICOES_ESTRATEGIAS[estrategia],
    }
