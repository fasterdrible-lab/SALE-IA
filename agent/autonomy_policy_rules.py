# -*- coding: utf-8 -*-
"""
SALEIA — agent/autonomy_policy_rules.py

Preparação para Autonomia (FASE 17 / TAREFA 17.1 do "PROMPT MESTRE —
SALE-IA V2"). Função pura, nenhuma chamada de IA, nenhum acesso a
banco — mesmo padrão dos demais módulos `*_rules.py` das Fases 1-16.

Regra explícita da Fase 17 — "ainda não colocar agente para vender
sozinho": este módulo só define o CONCEITO de `AutonomyPolicy` (os 6
níveis literais) e as fronteiras de decisão (Tarefa 17.1) — nenhum
nível é ativado, nenhuma ação é de fato executada por este módulo, e
não há integração com `orquestrador.py`. Ele existe pra que, quando a
decisão de habilitar execução autônoma for tomada (fase futura, fora
do escopo desta rodada), já exista uma camada de governança
verificável em vez de confiar na instrução de um prompt.

Regra literal da Tarefa 17.1, garantida estruturalmente — "nenhum LLM
pode contornar políticas": `pode_executar_autonomamente()` é o único
portão de decisão, e as classes `FORBIDDEN`/`HUMAN_REQUIRED`/
`HUMAN_APPROVAL` retornam sempre `False`, **em qualquer nível de
autonomia** — nem o nível máximo (`AUTONOMOUS_WITHIN_POLICY`, 5)
muda esse resultado. Ação sem fronteira de decisão mapeada nunca é
tratada como `AUTONOMOUS` por omissão (`avaliar_acao()` levanta
`ValueError`, fail-closed).
"""

from typing import Optional

# Os 6 níveis literais do prompt mestre — o índice na tupla É o número
# do nível (0-5), mesma numeração do documento original.
AUTONOMY_LEVELS = (
    "OBSERVE",                     # 0
    "RECOMMEND",                   # 1
    "DRAFT",                       # 2
    "EXECUTE_LOW_RISK",            # 3
    "EXECUTE_HUMAN_APPROVAL",      # 4
    "AUTONOMOUS_WITHIN_POLICY",    # 5
)

# TAREFA 17.1 — as 5 fronteiras de decisão literais do prompt mestre.
DECISION_BOUNDARIES = (
    "AUTONOMOUS",
    "POLICY_DEPENDENT",
    "HUMAN_APPROVAL",
    "HUMAN_REQUIRED",
    "FORBIDDEN",
)

# Fronteiras que NUNCA permitem execução autônoma, em nenhum nível de
# autonomia — a garantia estrutural central da Tarefa 17.1.
_FRONTEIRAS_SEMPRE_BLOQUEADAS = frozenset({"FORBIDDEN", "HUMAN_REQUIRED", "HUMAN_APPROVAL"})

# Nível mínimo de autonomia do sistema pra qualquer execução (mesmo
# ações AUTONOMOUS) ser sequer considerada — em OBSERVE/RECOMMEND/DRAFT
# (0-2) nada é executado, só observado/recomendado/rascunhado.
_NIVEL_MINIMO_PARA_EXECUTAR = AUTONOMY_LEVELS.index("EXECUTE_LOW_RISK")

# Exemplo literal do prompt mestre (Tarefa 17.1) — as 4 ações de
# fronteira fixa. "desconto" fica de fora por ser parametrizado por
# percentual, não uma ação fixa — ver `avaliar_desconto()`.
DECISION_BOUNDARIES_PADRAO = {
    "dar_informacao_publica": "AUTONOMOUS",
    "qualificar": "AUTONOMOUS",
    "agendar_reuniao": "AUTONOMOUS",
    "enviar_followup": "AUTONOMOUS",
    "alteracao_juridica": "HUMAN_REQUIRED",
    "promessa_nao_documentada": "FORBIDDEN",
}

LIMITE_DESCONTO_POLICY_DEPENDENT_PADRAO = 5.0


def avaliar_acao(acao: str, boundaries: Optional[dict] = None) -> str:
    """Retorna a fronteira de decisão (`DECISION_BOUNDARIES`) de uma
    ação de catálogo fixo. Fail-closed: ação sem mapeamento explícito
    levanta `ValueError` — nunca é assumida `AUTONOMOUS` por omissão."""
    boundaries = boundaries if boundaries is not None else DECISION_BOUNDARIES_PADRAO
    if acao not in boundaries:
        raise ValueError(
            f"ação {acao!r} não tem fronteira de decisão definida — fail-closed, nunca "
            "assumida AUTONOMOUS por omissão"
        )
    return boundaries[acao]


def avaliar_desconto(percentual: float, limite: float = LIMITE_DESCONTO_POLICY_DEPENDENT_PADRAO) -> str:
    """Fronteira de decisão pro caso parametrizado do exemplo literal
    do prompt mestre: `desconto <= 5%` é `POLICY_DEPENDENT`,
    `desconto > 5%` é `HUMAN_APPROVAL`. `limite` sobrescrevível por
    chamada (política de desconto pode mudar por plano/segmento)."""
    if percentual is None:
        raise ValueError("percentual obrigatório")
    return "POLICY_DEPENDENT" if percentual <= limite else "HUMAN_APPROVAL"


def pode_executar_autonomamente(
    fronteira: str,
    nivel_autonomia_atual: int,
    policy_dependente_aprovado: bool = False,
) -> bool:
    """Único portão de decisão de execução autônoma — regra central
    da Tarefa 17.1: "nenhum LLM pode contornar políticas".

    - `FORBIDDEN`/`HUMAN_REQUIRED`/`HUMAN_APPROVAL`: sempre `False`,
      em QUALQUER `nivel_autonomia_atual` (inclusive o nível máximo,
      5 — `AUTONOMOUS_WITHIN_POLICY`). Elevar o nível de autonomia do
      sistema nunca contorna uma fronteira que exige humano ou proíbe
      a ação.
    - `POLICY_DEPENDENT`: só `True` quando `policy_dependente_aprovado`
      vem explicitamente `True` (aprovação de uma política externa a
      este módulo — nunca assumida) **e** o sistema já está em nível
      suficiente pra executar (`EXECUTE_LOW_RISK` ou acima).
    - `AUTONOMOUS`: `True` só quando o sistema está em nível
      suficiente pra executar — em `OBSERVE`/`RECOMMEND`/`DRAFT`
      (níveis 0-2) nada é executado, mesmo uma ação de fronteira
      `AUTONOMOUS`."""
    if fronteira not in DECISION_BOUNDARIES:
        raise ValueError(f"fronteira inválida: {fronteira!r} (esperada uma de {DECISION_BOUNDARIES})")
    if not (0 <= nivel_autonomia_atual < len(AUTONOMY_LEVELS)):
        raise ValueError(f"nivel_autonomia_atual fora do intervalo válido (0-{len(AUTONOMY_LEVELS) - 1})")

    if fronteira in _FRONTEIRAS_SEMPRE_BLOQUEADAS:
        return False

    nivel_suficiente = nivel_autonomia_atual >= _NIVEL_MINIMO_PARA_EXECUTAR

    if fronteira == "POLICY_DEPENDENT":
        return bool(policy_dependente_aprovado) and nivel_suficiente

    return nivel_suficiente  # AUTONOMOUS
