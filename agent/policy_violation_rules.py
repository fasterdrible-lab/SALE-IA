# -*- coding: utf-8 -*-
"""
agent/policy_violation_rules.py

Fase 25 do "PROMPT MESTRE — SALE-IA V2" (Critério para iniciar o
Digital Sales Twin) — alimenta o critério literal
`policy violation = 0`. Função pura, mesmo padrão de
`audit_trail_rules.py`/`sales_event_rules.py` — zero IA/banco.

Escopo confirmado com o usuário antes de codar: só o único tipo de
violação com detector determinístico real hoje — tentativa de prompt
injection (`agent/prompt_injection_rules.py::
detectar_tentativas_injection()`, Tarefa 18.2), já ligada no único
choke-point de IA (`api/ai_router.py::chamar_ia`), mas até esta rodada
só gerava `logger.warning`, nunca persistia nada — não dava pra medir
`policy_violation` de verdade, só assumir "0" sem lastro nenhum.

Os outros 2 tipos potenciais de violação **não têm detector nenhum**
hoje — documentados como gap, não fabricados:
- Tentativa adversarial (Fase 21, `agent/adversarial_sales_rules.py`)
  — só tem texto de guarda no prompt (`ADVERSARIAL_SALES_GUARD_TEXT`),
  nunca um detector determinístico do lado de entrada.
- Ação `FORBIDDEN` do AutonomyPolicy (Fase 17) — a `AutonomyPolicy`
  segue dormente, nenhuma ação autônoma roda em produção hoje, então
  não há nada pra violar ainda.
"""

POLICY_VIOLATION_TIPOS = ("PROMPT_INJECTION",)


def validar_policy_violation_event(dados: dict) -> None:
    """Levanta ValueError se `tipo` não estiver no vocabulário fechado
    ou se `trechos_detectados` estiver ausente/vazio — um evento de
    violação sem nenhum trecho real detectado não serve pra auditoria
    nenhuma (mesma disciplina de evidência obrigatória de
    `SalesEvent`/`AuditTrailEntry`)."""
    tipo = dados.get("tipo")
    if tipo not in POLICY_VIOLATION_TIPOS:
        raise ValueError(f"tipo inválido: {tipo!r} (esperado um de {POLICY_VIOLATION_TIPOS})")
    if not dados.get("trechos_detectados"):
        raise ValueError("trechos_detectados é obrigatório e não pode ser vazio")
