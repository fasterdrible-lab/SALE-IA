# SALEIA — Evaluation Suite (Fase 2 do PROMPT MESTRE)

Implementa a Fase 2 (`PROMPT MESTRE — EVOLUÇÃO DA SALEIA.txt`, raiz do
repo) usando [Promptfoo](https://www.promptfoo.dev/). Avalia os agentes
reais do multiagente (`agent/multiagente/*_agent.py`) chamando o mesmo
codigo que roda em producao — nunca reimplementa a logica de chamada de
IA (`api/ai_router.py`), conforme a regra do prompt mestre de "evoluir a
arquitetura existente, nao criar sistemas paralelos duplicados".

## Estrutura

```
evals/
├── promptfooconfig.yaml                    # Coach Agent (principal)
├── promptfooconfig.finance.yaml            # Finance Agent
├── promptfooconfig.redteam.yaml            # Red teaming (TAREFA 2.8)
├── promptfooconfig.sales_reasoning.yaml    # SalesReasoningEngine (Fase 7 / Tarefa 7.1)
├── providers/                     # Pontes Python -> agentes/motores reais
│   ├── coach_provider.py
│   ├── finance_provider.py
│   └── sales_reasoning_provider.py
├── datasets/
│   ├── coach/
│   │   ├── objections_real.yaml     # 34 objecoes REAIS anonimizadas (TAREFA 2.2/2.3)
│   │   ├── objections_fit_gap.yaml  # 2 casos sinteticos so pra categoria FIT (sem exemplo real)
│   │   └── next_best_action.yaml    # Cenarios de NBA (TAREFA 2.4)
│   ├── finance/
│   │   └── price_objections.yaml    # Objecoes financeiras aprofundadas
│   └── sales_reasoning/             # Golden Dataset da Fase 7 (52 cenarios, ver secao propria)
│       ├── spin.yaml
│       ├── meddpicc_qualification.yaml
│       ├── objection_investigation.yaml
│       ├── negotiation.yaml
│       ├── risk_mitigation.yaml
│       ├── closing.yaml
│       ├── buyer_motivation_and_behavior.yaml
│       └── edge_cases.yaml
├── scenarios/
│   └── red_team.yaml              # Injection/role override/exfiltration
├── prompts/                        # Reservado para variantes (coach_v2.txt
│   .gitkeep                        # etc.) quando existir uma pra comparar — TAREFA 2.6
└── results/                        # Saida do `promptfoo eval` (gitignored)
```

**Por que 2 (na verdade 3) config files em vez de um so**: o schema de
saida do Coach difere do Finance (`next_best_action` vs
`mapa_financeiro`/`objecao_detectada`); misturar tudo numa config so
faria as assertions genericas demais. Cada config aponta pro provider
Python certo.

## Rodar localmente

```bash
cd SALEIA
npm install

# Ativar o venv do projeto ANTES de rodar — os providers Python
# (evals/providers/*.py) importam agent/api/etc., que dependem de
# fastapi/sqlmodel/etc. instalados so no venv, nao no Python global.
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac

# Precisa de pelo menos 1 provedor de IA configurado no .env
# (mesmo .env que api/ai_router.py usa) — ver .env.example.
PYTHONPATH=. npx promptfoo eval -c evals/promptfooconfig.yaml
npx promptfoo view   # abre o dashboard local de resultados
```

Confirmado nesta sessao: `PYTHONPATH=. venv/Scripts/python.exe -c "from agent.multiagente.coach_agent import analisar_coach"` importa sem erro dentro do venv; falha com `ModuleNotFoundError: No module named 'fastapi'` no Python global do sistema — por isso o venv precisa estar ativo (ou configurar `pythonExecutable` no provider) antes de rodar o Promptfoo.

Ou via npm scripts (`package.json` na raiz de `SALEIA/`):

```bash
npm run eval:coach
npm run eval:finance
npm run eval:redteam
npm run eval:all
npm run eval:view
```

**⚠️ Custa dinheiro real.** Cada teste dispara uma chamada real de IA
pelo provedor ativo (DeepSeek/OpenAI/Anthropic/Gemini). Os providers
Python (`providers/*.py`) chamam `agent.multiagente.coach_agent.
analisar_coach`/`finance_agent.analisar_finance` diretamente — o mesmo
caminho de `chamar_ia_com_fallback_claude` -> `chamar_ia_async` que roda
em producao, incluindo Cost Intelligence (`ai_usage_events`) se o banco
estiver acessivel. Rodando localmente com SQLite (`docs/CURRENT_STATE.md`:
"Local pode cair para SQLite se MySQL estiver indisponivel"), o registro
de custo funciona igual, so nao compartilha os dados de producao.

## Resultado da primeira execucao real (05/09/2026)

Rodada de verdade (nao so harness) apos o usuario atualizar
`DEEPSEEK_API_KEY` local (a chave que estava no `.env` local era invalida
— diferente da chave em producao na VPS, que funciona) e depois de
instalar `google-generativeai` (faltava no venv local, so isso ja
bastava pra derrubar o fallback pro Gemini antes mesmo de tentar a API).

- **Coach Agent**: 27/27 passou (100%).
- **Finance Agent**: 4/4 passou (100%).
- **Red Team**: 6/6 passou (100%) — **na segunda tentativa**. Na
  primeira, 2 dos 6 casos (`prompt injection` e `role override`) deram
  `[FAIL]` por um falso positivo do proprio assert, nao por falha de
  seguranca do agente: o Coach realmente detectou e resistiu as duas
  tentativas de manipulacao (gerou `next_best_action.type: "warning"`,
  nunca revelou o system prompt real nem mudou de papel), mas
  `filtro_cliente.frases_chave`/`key_moments[].quote` citam a fala do
  cliente **verbatim por design** (e assim que o schema registra
  evidencia de manipulacao) — meu assert original (`not-contains`/
  `not-icontains` no JSON inteiro) pegava essas citacoes legitimas como
  se fossem o agente obedecendo a instrucao injetada. Corrigido
  restringindo os asserts desses 2 casos aos campos que o vendedor de
  fato ve/fala (`next_best_action.message`, `texto_falavel`,
  `dica_vendedor`), nunca o JSON inteiro — licao registrada nos
  comentarios de `scenarios/red_team.yaml`.
- **Custo real total**: US$ 0,0122 pelas 37 chamadas de IA dos agentes
  (somado direto do campo `_custo_estimado_ia` que `api/ai_router.py` ja
  grava em cada resposta) — bem abaixo da estimativa de pior caso feita
  antes de rodar.
- **Achado de infraestrutura local, sem relacao com o eval em si**: o
  `.env` local desta maquina tinha `DEEPSEEK_API_KEY` invalida (a
  producao usa outra chave, valida) e o venv local nao tinha
  `google-generativeai` instalado apesar de estar em `requirements.txt`
  (drift entre venv e requirements). Nenhum dos dois e culpa do
  Promptfoo/harness — sao problemas pre-existentes do ambiente de dev
  local, agora corrigidos.
- Resultados brutos em `evals/results/coach_latest.json`/
  `finance_latest.json`/`redteam_latest.json` (`git`-ignorados, gerados a
  cada `promptfoo eval`).

## Segunda execucao real — dataset trocado por objecoes reais (05/09/2026)

Apos substituir `objections_golden.yaml` (22 sinteticos) por
`objections_real.yaml` (34 reais) + `objections_fit_gap.yaml` (2
sinteticos so pra FIT), rodada real contra o Coach Agent: **41/41
casos** (27 antigos de NBA + 34 reais + 2 gap de FIT, menos os 22
sinteticos removidos = 41 no total), custo real **US$ 0,0093**.

- **Primeira tentativa: 38/41 (3 falhas)** — mesma classe de falso
  positivo do red team acima: os 3 casos `PRICE_VALUE` com assert
  `not-contains: "desconto"` falharam porque o campo `dica_vendedor`
  dizia literalmente **"Não ofereça desconto imediatamente..."** — o
  Coach estava fazendo exatamente o certo (aconselhando o vendedor a
  NÃO dar desconto), mas o assert bruto de substring nao distingue
  "recomendar desconto" de "recomendar NAO dar desconto".
- **Fix**: as 4 ocorrencias de `not-contains: "desconto"` em
  `objections_real.yaml` foram trocadas por `llm-rubric` (julgamento
  semantico via DeepSeek, mesmo grader ja configurado em
  `defaultTest.options.provider`): "a resposta nao recomenda oferecer
  desconto — dizer explicitamente para NAO oferecer conta como
  passando". Segunda tentativa: **41/41 (100%)**.
- **Licao recorrente**: esta e a segunda vez no mesmo dia que um assert
  de substring pura (`not-contains`) deu falso positivo por nao entender
  polaridade/intencao (a primeira foi no red team, com as citacoes
  verbatim do cliente). Prefira `llm-rubric` sempre que a checagem for
  sobre **o que a IA recomenda fazer**, nao sobre presenca/ausencia
  literal de uma palavra.

## Estado atual desta Fase 2 (o que foi feito nesta sessao)

- [x] TAREFA 2.1 — estrutura `evals/` criada.
- [x] TAREFA 2.2/2.3 — Golden Dataset com as 11 categorias minimas
  (`PRICE_VALUE`, `CASH_FLOW`, `ROI_RISK`, `DECISION_MAKER`, `TIMING`,
  `COMPETITION`, `TRUST`, `FIT`, `IMPLEMENTATION`, `CONTRACT`, `OTHER`).
  **Atualizado em 05/09/2026**: os 22 casos sinteticos foram substituidos
  por **34 objecoes REAIS anonimizadas** (`datasets/coach/
  objections_real.yaml`), extraidas da tabela `sales_memories` de
  producao (`memory_type='objection'`, TODAS as que existiam no banco) —
  reescritas manualmente como fala em primeira pessoa e anonimizadas
  (removidos 2 nomes proprios que apareciam no conteudo original). A
  unica categoria sem nenhum exemplo real (`FIT`) ganhou 2 casos
  sinteticos isolados em `objections_fit_gap.yaml`, claramente
  identificados. Ver aviso completo no topo de `objections_real.yaml`
  pra saber exatamente o que "real" significa aqui (resumo da IA
  reescrito, nao a transcricao verbatim — decisao deliberada de reduzir
  risco de privacidade).
- [x] TAREFA 2.4 — Next Best Action: o caso literal do prompt mestre
  ("Preciso conversar com meu socio" -> mapear decisor, nunca desconto/
  pressao) esta em `next_best_action.yaml`, mais 4 cenarios de matriz de
  decisao. O DECISION_MAKER real (aprovacao de conselho/familia) esta em
  `objections_real.yaml`.
- [~] TAREFA 2.5 — Comparacao entre providers: a config suporta multiplos
  `providers:` (bastaria adicionar mais entradas apontando pro mesmo
  provider Python com uma env var de override de provedor), mas **nao
  foi executada** — precisa de chave valida dos 4 provedores ao mesmo
  tempo, e o `docs/CURRENT_STATE.md` documenta que 3 dos 4 provedores
  centrais estao sem saldo/chave valida desde 22/08/2026. Fica pendente
  ate esse incidente ser resolvido.
- [ ] TAREFA 2.6 — Comparacao entre versoes de prompt: pasta `prompts/`
  reservada, mas nao ha ainda uma v2 de nenhum prompt pra comparar contra
  a v1 (`agent/prompt_templates/multiagente_*.txt`).
- [x] TAREFA 2.7 — `APPROVAL_CRITERIA.md` (criterios de aprovacao antes
  de trocar prompt em producao).
- [x] TAREFA 2.8 — `scenarios/red_team.yaml` (6 casos: prompt injection,
  role override, exfiltration, injecao de desconto, JSON malformado
  induzido, pressao de fechamento).
- [x] TAREFA 2.9 — `.github/workflows/llm-evals.yml` na raiz do repo.
- [x] TAREFA 2.10 — este README cobre os criterios de aceite.

## SalesReasoningEngine — Golden Dataset da Fase 7 (criado, nunca rodado)

`promptfooconfig.sales_reasoning.yaml` avalia o motor real de
`agent.sales_reasoning_engine.raciocinar_async` (Fase 7 / Tarefa 7.1 do
"PROMPT MESTRE — SALE-IA V2", diferente do "PROMPT MESTRE — EVOLUÇÃO DA
SALEIA.txt" que criou o resto desta suite Fase 2) via
`providers/sales_reasoning_provider.py`, mesmo principio dos providers
de Coach/Finance — chama o codigo real, nenhuma logica de raciocinio
duplicada aqui.

- **52 cenarios** em `datasets/sales_reasoning/` (minimo pedido pelo
  prompt mestre: 50) — sinteticos, escritos para exercitar as regras de
  decisao entre os 9 frameworks do vocabulario fechado (`SPIN_SITUATION`
  a `CLOSING`, ver `agent/sales_reasoning_engine.py::
  SALES_REASONING_FRAMEWORKS`), incluindo o exemplo PROIBIDO literal do
  prompt mestre (`"Está caro." -> "Posso dar 20% agora."`, em
  `objection_investigation.yaml`).
- **Cada cenario tem `context` (narrativa) + os campos estruturados já
  calculados pelas Fases 1-6 que o cenário simula** (`spin_state`,
  `meddpicc_state`, `objections`, `behavioral_signals`,
  `buyer_motivation`, `opportunity_memory`, `opportunity_graph`,
  `rag_context`, `historical_patterns`, `seller_context`) — nunca
  transcrição crua, mesma disciplina do motor real (ele só sintetiza
  dado já estruturado, não reprocessa fala livre).
- **Validação sempre semântica (`llm-rubric`)**, nunca por igualdade
  literal de frase — regra explícita do próprio prompt mestre pra este
  Golden Dataset especificamente (diferente de `next_best_action.yaml`,
  que também usa `llm-rubric` mas por escolha de estilo, não por
  exigência do documento). Cada rubric descreve o `expected_framework`
  esperado junto das `acceptable_actions`/`forbidden_actions` do
  cenário, tudo em texto único — mesmo formato de
  `datasets/coach/next_best_action.yaml`.
- **Nunca rodado nesta rodada** — harness criado e revisado
  estaticamente (`node --check` nos providers, YAML validado), mas
  `npx promptfoo eval -c evals/promptfooconfig.sales_reasoning.yaml`
  não foi executado: 52 casos x custo real por chamada é uma decisão de
  custo que precisa de confirmação explícita antes de rodar, mesma
  disciplina de todo o resto desta suite (ver "Custa dinheiro real"
  acima). Quando rodar, resultado esperado vai para
  `evals/results/sales_reasoning_latest.json`.
- **Não usa embedding/mock nenhum dos módulos determinísticos das Fases
  1-6** — os campos `spin_state`/`meddpicc_state`/etc. de cada cenário
  são escritos manualmente no formato que `spin_coverage_rules.py`/
  `meddpicc_rules.py`/`objection_rules.py`/`behavioral_signal_rules.py`
  realmente produzem, mas não chamam essas funções — o dataset testa só
  o SalesReasoningEngine, não a cadeia inteira de principio a fim
  (fica para quando o motor for integrado a `orquestrador.py`, decisão
  de produto ainda não tomada).

## Pendencias explicitas (nao inventadas, decisao de produto/acesso)

1. ~~Substituir o dataset sintetico por reunioes reais anonimizadas~~ —
   **feito em 05/09/2026**: 34 objecoes reais de `sales_memories`
   (TODAS as que existiam), reescritas e anonimizadas. Volume (36 com o
   gap de FIT) ainda abaixo da meta de 50-200 do prompt mestre — so
   existiam 34 registros `objection` no banco nesta data; crescera
   organicamente conforme mais reunioes forem analisadas e Sales Memory
   extrair mais objecoes. Suite re-rodada apos a troca: 41/41 passou
   (100%), custo real US$ 0,0093.
2. ~~Rodar a suite de fato pelo menos uma vez~~ — **feito em 05/09/2026**:
   37/37 casos passaram via DeepSeek (custo real US$ 0,0122), apos
   corrigir a `DEEPSEEK_API_KEY` local (estava invalida) e instalar
   `google-generativeai` no venv. Ver "Resultado da primeira execucao
   real" acima.
3. **TAREFA 2.5 completa** (comparacao real entre os 4 providers) —
   ainda bloqueada: mesmo com DeepSeek local funcionando agora,
   OpenAI/Anthropic continuam sem saldo (confirmado nesta mesma sessao,
   erros `429`/`400` reais) e Gemini nunca foi testado de fato (so o
   pacote foi instalado, a chave em si nao foi validada). Precisa dos 4
   provedores com saldo/chave valida ao mesmo tempo pra uma comparacao
   justa.
4. **TAREFA 2.6** — so faz sentido quando existir de fato uma v2 de algum
   prompt candidata a substituir a v1 em producao.
5. Estender a mesma cobertura para `disc_agent.py`/`closer_agent.py` —
   esta rodada cobriu Coach (foco em NBA/objecoes, que e o pedido mais
   explicito do prompt mestre) e Finance (objecao de preco); DISC/Closer
   ficaram de fora por escopo, nao por esquecimento.
6. ~~Configurar secrets no GitHub~~ — **feito em 05/09/2026**:
   `EVAL_DEEPSEEK_API_KEY` configurado em Settings > Secrets and
   variables > Actions. So esse e obrigatorio hoje (unico provedor com
   saldo valido); `OPENAI`/`ANTHROPIC`/`GEMINI` ficaram comentados no
   workflow, prontos pra ativar quando resolver TAREFA 2.5.
