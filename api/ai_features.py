"""
Identificadores de feature para atribuicao de custo (Cost Intelligence Fase 1).

String livre, nao Enum — o valor vira uma coluna de texto em ai_usage_events
(api/database.py); manter aqui como constantes so para evitar erro de
digitacao nos varios pontos de chamada.
"""

REALTIME_COACH = "realtime.coach"
REALTIME_DISC = "realtime.disc"
REALTIME_FINANCE = "realtime.finance"
REALTIME_CLOSER = "realtime.closer"
REALTIME_BIGFIVE = "realtime.bigfive"
REALTIME_RECAP_VIVA = "realtime.recap_viva"
REALTIME_CLAUDE_ACCOUNT_FALLBACK = "realtime.claude_account_fallback"

SALES_REASONING_RACIOCINIO = "sales_reasoning.raciocinio"
OBJECTION_CATEGORIA_CLASSIFICACAO = "objection.categoria_classificacao"
OBJECTION_CAUSA_RAIZ_INVESTIGACAO = "objection.causa_raiz_investigacao"
SPIN_EXTRACAO_FATOS = "spin.extracao_fatos"
BEHAVIORAL_SIGNAL_EXTRACAO = "behavioral_signal.extracao"
BUYER_MOTIVATION_EXTRACAO = "buyer_motivation.extracao"

REPORT_DIAGNOSTICO_FINANCEIRO = "report.diagnostico_financeiro"
REPORT_PERFIL_DISC = "report.perfil_disc"
REPORT_RECAPITULACAO = "report.recapitulacao"

TACTIQ_RECAPITULACAO = "tactiq.recapitulacao"
TACTIQ_DIAGNOSTICO_FINANCEIRO = "tactiq.diagnostico_financeiro"
TACTIQ_PERFIL_DISC = "tactiq.perfil_disc"

PLAYBOOK_GERACAO = "playbook.geracao"
FOLLOWUP_GERACAO = "followup.geracao"
SKILL_GERACAO = "skill.geracao"
KNOWLEDGE_EXTRACAO_MEMORIAS = "knowledge.extracao_memorias"
KNOWLEDGE_COMPILER_EXTRACAO = "knowledge_compiler.extracao"
CENARIO_CONDUCAO = "cenario.conducao"

CLAUDE_ACCOUNT_ANALISE_SOB_DEMANDA = "claude_account.analise_sob_demanda"

UNSPECIFIED = "unspecified"  # default de chamar_ia — nao deve aparecer em producao apos a Fase 1 completa
