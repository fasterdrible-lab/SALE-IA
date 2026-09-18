"""
agent/adversarial_sales_rules.py

Fase 21 do "PROMPT MESTRE — SALE-IA V2" (Testes de Adversarial Sales):
4 casos literais de pedido adversarial do cliente durante uma reunião —
"IA não deve inventar ataques" (concorrente), "IA deve respeitar
policy" (desconto pedido de forma velada), "IA não pode garantir
resultado sem base" (ROI), "IA ignora a instrução maliciosa" (jailbreak
via transcrição).

Investigação prévia (antes de codar): o caso 4 já está 100% coberto
pela Tarefa 18.2 (`agent/prompt_injection_rules.py::
PROMPT_INJECTION_GUARD_TEXT`, com teste literal do exemplo do prompt
mestre). Os casos 1 e 3 não tinham nenhuma guarda. O caso 2 tinha
cobertura PARCIAL — `agent/autonomy_policy_rules.py::avaliar_desconto()`
(Fase 17) já classifica desconto acima de 5% como `HUMAN_APPROVAL`,
mas isso nunca foi conectado a nenhum fluxo real (a `AutonomyPolicy`
inteira segue dormente) e não existia nenhuma instrução textual contra
a "confidencialidade" implícita do pedido ("seu chefe não precisa
saber").

Este módulo fecha os casos 1-3 com o mesmo padrão arquitetural da
Tarefa 18.2: um texto de guarda anexado ao `system_prompt` no único
choke-point de IA do sistema (`api/ai_router.py::chamar_ia`) — cobre
~100% do tráfego sem precisar editar cada um dos ~20 templates em
`agent/prompt_templates/`. Diferente da Tarefa 18.2, não há detector
por regex aqui — os 3 casos são sobre qualidade/integridade da
RESPOSTA da IA (nunca fabricar, nunca prometer, sempre respeitar
policy), não sobre reconhecer um padrão de texto malicioso na entrada
pra mascarar/logar.
"""

ADVERSARIAL_SALES_GUARD_TEXT = (
    "\n\nREGRAS DE INTEGRIDADE COMERCIAL OBRIGATORIAS:\n"
    "- Nunca invente, insinue ou repita como fato qualquer ataque, "
    "boato ou informacao negativa sobre um concorrente que nao tenha "
    "sido fornecida como dado real e verificado. Se o cliente pedir "
    "para falar mal de um concorrente, redirecione para os "
    "diferenciais reais da propria solucao.\n"
    "- Nunca ofereca, sugira ou confirme desconto, condicao especial "
    "ou excecao de politica comercial apresentados como algo que deve "
    "ficar oculto da lideranca/gestao do vendedor (ex.: \"desconto que "
    "seu chefe nao precisa saber\"). Qualquer excecao de politica "
    "precisa ser tratada com transparencia, nunca como um acordo "
    "as escondidas.\n"
    "- Nunca garanta um resultado numerico especifico (ex.: percentual "
    "de retorno sobre investimento, prazo exato de payback) que nao "
    "esteja apoiado em dado real fornecido a voce. Fale em termos de "
    "potencial, faixas realistas ou peça para conectar o cliente a um "
    "case real, nunca uma garantia inventada."
)
