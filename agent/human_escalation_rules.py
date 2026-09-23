# -*- coding: utf-8 -*-
"""
SALEIA — agent/human_escalation_rules.py

Fase 25 do "PROMPT MESTRE — SALE-IA V2" (Critério para iniciar o
Digital Sales Twin), item 5/5 de "o que falta pra ligar" —
escalonamento humano, alimentando o critério literal `human escalation
functional = 100%`. Função pura, mesmo padrão de
`autonomy_policy_rules.py` (Fase 17) — decide QUANDO escalar; o
disparo real da notificação vive em
`agent/alertas.py::escalar_para_humano()` (mesmo padrão arquitetural
de `verificar_orcamento`/`verificar_anomalia`, que também são funções
de decisão que chamam `alertar()`).

Escopo confirmado com o usuário antes de codar: "funcional" (diferente
da maioria das fases do roadmap, que ficam só no contrato) significa
que este item precisa de fato notificar alguém, não só existir como
estrutura de dados — reaproveita o canal Telegram já ativo em produção
(`agent/alertas.py::alertar()`), nunca um canal novo. Reaproveita as
fronteiras de decisão de `autonomy_policy_rules.py` (Fase 17) em vez
de inventar um vocabulário paralelo — a mesma decisão que bloqueia
execução autônoma (`FORBIDDEN`/`HUMAN_REQUIRED`/`HUMAN_APPROVAL`, e
`POLICY_DEPENDENT` sem aprovação) é o gatilho de quando escalar.

Decisão de correção desta rodada: `precisa_escalar_para_humano()` NÃO
depende do nível de autonomia atual do sistema — só da fronteira em
si. Sistema em `OBSERVE`/`RECOMMEND` (níveis baixos) não executa ações
`AUTONOMOUS` porque essa capacidade ainda não foi ligada pelo operador
(decisão de operação), não porque um humano precisa decidir algo —
misturar os dois geraria escalonamento falso a cada ação `AUTONOMOUS`
tentada em qualquer nível abaixo de `EXECUTE_LOW_RISK`, mesmo sem
nenhum motivo real pra envolver um humano.

Ainda sem integração com `orquestrador.py`: nada autônomo roda em
produção hoje (`AutonomyPolicy`, Fase 17, segue dormente) — não existe
hoje nenhuma ação real do sistema que precise ser escalada
automaticamente. Este módulo fica pronto pra quando isso mudar (mesmo
princípio de `autonomy_policy_rules.py`: governança antes da
capacidade de agir sozinho).
"""

from typing import Optional

from agent.autonomy_policy_rules import DECISION_BOUNDARIES

# Fronteiras que sempre exigem um humano, independente do nível de
# autonomia do sistema — mesmo conjunto de
# `autonomy_policy_rules._FRONTEIRAS_SEMPRE_BLOQUEADAS`, reaproveitado
# aqui só como leitura (não importado por nome "privado" de outro
# módulo).
_FRONTEIRAS_SEMPRE_ESCALAM = frozenset({"FORBIDDEN", "HUMAN_REQUIRED", "HUMAN_APPROVAL"})

# Urgência por fronteira — usada só pra escolher o nível/ícone do
# alerta Telegram (mesmo vocabulário de `nivel` já usado em
# `agent/alertas.py`: 🔴 crítico, 🟠 alto, ⚠️ aviso). FORBIDDEN é a
# mais urgente: a IA tentou uma ação proibida, não só uma que precisa
# de aprovação — sinal de possível violação de política (critério
# adjacente da Fase 25, `policy violation = 0`).
URGENCIA_POR_FRONTEIRA = {
    "FORBIDDEN": "🔴",
    "HUMAN_REQUIRED": "🔴",
    "HUMAN_APPROVAL": "⚠️",
    "POLICY_DEPENDENT": "🟠",
}


def precisa_escalar_para_humano(fronteira: str, policy_dependente_aprovado: bool = False) -> bool:
    """`True` quando a fronteira de decisão (Fase 17) exige
    envolvimento humano: sempre para
    `FORBIDDEN`/`HUMAN_REQUIRED`/`HUMAN_APPROVAL`, e para
    `POLICY_DEPENDENT` só quando ainda não foi aprovado.
    `AUTONOMOUS` nunca escala."""
    if fronteira not in DECISION_BOUNDARIES:
        raise ValueError(f"fronteira inválida: {fronteira!r} (esperada uma de {DECISION_BOUNDARIES})")
    if fronteira in _FRONTEIRAS_SEMPRE_ESCALAM:
        return True
    if fronteira == "POLICY_DEPENDENT":
        return not policy_dependente_aprovado
    return False  # AUTONOMOUS


def montar_escalonamento(
    acao: str,
    fronteira: str,
    motivo: str,
    contexto: Optional[dict] = None,
) -> dict:
    """Monta o registro de 1 escalonamento. `motivo` é obrigatório e
    não-vazio — um escalonamento sem explicação não serve pra um
    humano decidir nada, mesma disciplina de `actor`/`action`/
    `reason`/`result` obrigatórios em `audit_trail_rules.py` (Fase
    18.4). `contexto` é livre (ex.: `opportunity_id`, valor do
    desconto) — nunca interpretado por este módulo, só repassado pra
    mensagem que `agent/alertas.py::escalar_para_humano()` monta."""
    if fronteira not in DECISION_BOUNDARIES:
        raise ValueError(f"fronteira inválida: {fronteira!r} (esperada uma de {DECISION_BOUNDARIES})")
    if not acao or not acao.strip():
        raise ValueError("acao obrigatória")
    if not motivo or not motivo.strip():
        raise ValueError("motivo obrigatório — escalonamento sem explicação não serve pra um humano decidir")

    return {
        "acao": acao,
        "fronteira": fronteira,
        "motivo": motivo,
        "urgencia": URGENCIA_POR_FRONTEIRA.get(fronteira, "⚠️"),
        "contexto": contexto or {},
    }
