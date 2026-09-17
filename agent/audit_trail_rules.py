"""
agent/audit_trail_rules.py

Tarefa 18.4 do "PROMPT MESTRE — SALE-IA V2" (fecha a Fase 18 —
Segurança): validação do AuditTrailEntry — schema literal do prompt
mestre (quem/quando/ação/motivo/dados usados/modelo/versão do
prompt/versão da regra/resultado), "especialmente para recomendações
autônomas futuras" (a AutonomyPolicy da Fase 17 continua dormente —
nenhum nível de autonomia ativo em produção; este módulo só prepara o
schema/validação pra quando isso mudar).

Mesmo padrão de `sales_event_rules.py`/`recommendation_rules.py` —
função pura, zero IA/banco. Persistência real em
`api/database.py::AuditTrailEntry`/`criar_audit_trail_entry()`.
"""

AUDIT_TRAIL_CAMPOS_OBRIGATORIOS = ("actor", "action", "reason", "result")


def validar_audit_trail_entry(dados: dict) -> None:
    """Levanta ValueError se `actor` ("quem"), `action` ("ação"),
    `reason` ("motivo") ou `result` ("resultado") estiverem ausentes ou
    vazios — sem esses 4 campos, a entrada não serve pra auditoria
    nenhuma. `model`/`prompt_version`/`rule_version`/`data_used`/
    `meeting_id`/`opportunity_id` são opcionais (nem toda ação
    auditada envolve IA ou está ligada a uma reunião/oportunidade
    específica)."""
    for campo in AUDIT_TRAIL_CAMPOS_OBRIGATORIOS:
        valor = dados.get(campo)
        if not valor or not str(valor).strip():
            raise ValueError(f"AuditTrailEntry.{campo} é obrigatório e não pode ser vazio")
