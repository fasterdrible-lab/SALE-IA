# SALEIA - Estado Atual

Atualizado em: 2026-09-20 — Backend **V.1.4.122** (local + GitHub,
aguardando deploy na VPS): Tarefas 3.1 (vínculo automático
meeting↔opportunity) + 2.1 (historical_patterns via Sales Science).
Investigação prévia confirmou que 2.1 dependia de 3.1, nunca
resolvida (`vincular_meeting_opportunity()` existia mas nunca era
chamada) — usuário confirmou fazer as duas juntas, 3.1 primeiro.
Regra de vínculo: só automático quando exatamente 1 oportunidade
aberta do cliente (0 ou 2+ ficam sem vínculo, ambiguidade não é
resolvida sozinha); nunca sobrescreve vínculo existente. `agent/
opportunity_link_rules.py` (novo) + `agent/historical_pattern_
rules.py` (novo, filtra só por `stage` — `product`/`competitor` só
nascem no fechamento, reaproveita `win_loss_rules`/`sales_science_
engine` sem recalcular estatística inteira a cada ciclo). Wiring em
`orquestrador.py`. **4 dos 11 campos do SalesReasoningEngine agora
têm dado real** (`meeting_memory`, `rag_context`, `objections`,
`historical_patterns`). 46 testes novos, suite completa: **1303
testes, 0 falhas**, 1 skip pré-existente. Detalhe completo em
CHANGELOG.md. **Bloco 4 (extração real via IA) não começa sem nova
confirmação explícita do usuário.**

Backend **V.1.4.121** (local + GitHub +
**produção confirmada**, `/health` = `versao 1.4.121`): usuário pediu
plano pra fechar os 9 campos
vazios do `SalesReasoningEngine`, documentado em `docs/
tasks-sales-reasoning-engine-completo.md` (6 blocos). Tarefa 1.1
(MEDDPICC via `maturity_score`) **bloqueada** — sem citação real
disponível hoje, mudar exigiria tocar o prompt do Closer em produção,
usuário preferiu pular. Tarefa 1.2 (objeção do Finance) **concluída**
— achou o mesmo problema estrutural (sem categoria classificada), mas
resolvido com 1 chamada de IA nova e barata (`agent/objection_
category_classifier.py`). `entrada["objections"]` agora tem dado real
no ciclo de `/tempo-real` — **3 dos 11 campos do SalesReasoningEngine
preenchidos** (antes: 2). 33 testes novos, suite completa: **1285
testes, 0 falhas**, 1 skip pré-existente. **Deploy confirmado
(20/09/2026, ~21h09 UTC)**: commit `d5b59e9`, `reunioes_ativas: 0`
checado antes do `git pull`/restart — `/health` = `versao 1.4.121`,
`status online`; `/dashboard` = `200`. Detalhe completo em
CHANGELOG.md. **Tarefa 2.1 (historical_patterns via Sales Science) não
começa sem nova confirmação explícita do usuário.**

Backend **V.1.4.120** (local + GitHub +
**produção confirmada**, `/health` = `versao 1.4.120`): **Fase 24
(Piloto)** do "PROMPT MESTRE —
SALE-IA V2" — infraestrutura de rollout gradual (1 vendedor → 5% → 20%
→ 50% → 100%, feature flag `PILOT_MODE`, rollback sem deploy) +
adaptador que converte a saída do `SalesReasoningEngine` pro schema
que a extensão já renderiza. **Achado crítico antes de codar**: a
Fase 23 (Shadow Mode) terminava com "só liberar após avaliação", mas
`SHADOW_MODE_ENABLED` seguia `false` em produção — zero dado real
coletado. Usuário confirmou construir a Fase 24 (desligada por padrão,
`PILOT_MODE=off`) **e** ligar `SHADOW_MODE_ENABLED=true` em produção
nesta mesma rodada, já que é a única forma de a avaliação começar a
existir. `agent/pilot_rollout_rules.py` (novo) — bucket determinístico
por vendedor (sha256, sempre superconjunto ao subir percentual),
`mapear_para_next_best_action()` nunca traduz `category` inventando
mapeamento, mesmo princípio de honestidade da Fase 23. Wiring em
`agent/multiagente/orquestrador.py`: piloto sempre `await`ado (soma
latência real só pra quem está dentro do rollout), fail-open, mutuamente
exclusivo com Shadow Mode. `ShadowModeComparison` ganha coluna `origem`
(`shadow`/`piloto`). 32+4 testes novos. Suite completa: **1267 testes,
0 falhas**, 1 skip pré-existente. **Deploy confirmado (20/09/2026,
~19h23 UTC)**: commit `1c8663a`, `reunioes_ativas: 0` checado 3x —
`ALTER TABLE` (coluna `origem`) confirmado via `DESCRIBE` +
`SHADOW_MODE_ENABLED=true` adicionado ao `.env` da VPS + restart —
`/health` = `versao 1.4.120`, `status online`; `/dashboard` = `200`.
**Shadow Mode agora coletando dado real em produção.** `PILOT_MODE`
continua `off` — nenhum vendedor real entra no rollout ainda; ativar
é decisão separada, só depois de avaliar dado real de Shadow Mode.
Detalhe completo em CHANGELOG.md.

Backend **V.1.4.119** (local + GitHub +
**produção confirmada**, `/health` = `versao 1.4.119`): **Fase 23
(Teste em Shadow Mode)** do
"PROMPT MESTRE — SALE-IA V2". Investigação prévia achou que só 2 dos 11
campos de entrada do `SalesReasoningEngine` (Fase 7) têm dado real hoje
no ciclo de `/tempo-real` (`meeting_memory` parcial + `rag_context`) —
os outros 9 têm o mesmo gap de extração já documentado nas
investigações da Fase 22. Usuário confirmou a ordem: **contrato de
comparação primeiro, wiring real no ciclo em seguida**, aceitando
`quality` limitado. `agent/shadow_mode_rules.py` (novo) — único sinal
de concordância calculável sem IA extra é estrutural (os dois modelos
recomendam uma pergunta agora, ou não?), nunca inventa tradução de
`category`↔`recommended_framework`. `api/database.py::
ShadowModeComparison` (tabela nova) + wiring fire-and-forget em
`agent/multiagente/orquestrador.py` (kill-switch `SHADOW_MODE_ENABLED`,
**default `false`** — liga soma 1 chamada real de IA por ciclo, opt-in
explícito) + `GET /admin/shadow-mode/resumo` (admin-only). 34 testes
novos. **Deploy confirmado (20/09/2026, ~18h17 UTC)**: commit
`4d8a5dc`, `reunioes_ativas: 0` checado antes do `git pull`/restart —
corrida de DDL conhecida entre os 2 workers ao criar
`shadow_mode_comparisons` (mesmo padrão desde V.1.4.108) desta vez
tratada sem derrubar o processo; `/health` = `versao 1.4.119`, `status
online`; `/dashboard` = `200`. `SHADOW_MODE_ENABLED` continua `false`
— nenhuma comparação real coletada ainda, ligar em produção é decisão
separada não tomada nesta rodada. **Fecha o contrato + wiring da Fase
23**; a Fase 24 (Piloto) não começa sem nova confirmação explícita do
usuário. Detalhe completo em CHANGELOG.md.

Backend **V.1.4.118** (local + GitHub +
**produção confirmada**, `/health` = `versao 1.4.118`): Seller Coaching
(Fase 22 / bloco 4) — **fecha
a Fase 22 (Frontend) por completo**. Investigação prévia (mesmo padrão
das fases anteriores) achou que, diferente de Opportunity Intelligence
(9/12 campos reais) e Sales Science (3/7 campos reais), **nenhum dos 8
campos literais (Talk Ratio, Question Quality, SPIN Coverage,
Qualification, Objection Handling, Negotiation, Next Step Discipline,
Trend) tem dado real hoje** — Talk Ratio/Question Quality/Next Step
Discipline exigem transcrição estruturada por turno (speaker/start/end,
nunca capturada); SPIN Coverage/Qualification exigem fatos classificados
com evidence_quote (mesmo gap do bloco 2); Objection Handling/
Negotiation exigem objeção classificada em produção (nunca roda); Trend
exigiria histórico de Seller Scorecard persistido (nunca salvo em
tabela nenhuma). Usuário confirmou **só o contrato — os 8 como gap
explícito**, mesma disciplina de honestidade do resto do roadmap.
`agent/seller_coaching_rules.py` (novo) + `GET /seller-coaching/
{seller_id}` (novo, JWT + ownership via `_verificar_dono_ou_admin`) +
aba "🎓 Seller Coaching" no Dashboard. 12 testes novos. **Fase 22
(Frontend) completa**: bloco 1 (sidebar) → bloco 2 (Opportunity
Intelligence) → bloco 3 (Sales Science) → bloco 4 (Seller Coaching).
Fix, fora do escopo original mas confirmado pelo usuário: teste
pré-existente com `close_date` hardcoded que expirava após 10h do dia
— corrigido para data relativa a agora. Suite completa: **1201 testes,
0 falhas**, 1 skip pré-existente. **Deploy confirmado (20/09/2026,
~17h27 UTC)**: commit `0d2196e`, `reunioes_ativas: 0` checado antes do
`git pull`/restart — `/health` = `versao 1.4.118`, `status online`, 4
provedores `ok`; `/dashboard` = `200`; `GET /seller-coaching/x`
responde `401` sem token. Detalhe completo em CHANGELOG.md. **Nenhuma
fase seguinte do "PROMPT MESTRE — SALE-IA V2" começa sem nova
confirmação explícita do usuário.**

Backend **V.1.4.117** (local + GitHub +
**produção confirmada**, `/health` = `versao 1.4.117`): Sales Science
(Fase 22 / bloco 3). Só
Win/Loss, Seasonality e Conversion Drivers dão pra alimentar com dado
real hoje (via `Opportunity.stage`/`product`/`competitor`/
`close_date`/`created_at`) — Seller Benchmark, Best Strategies/
Recommendation Effectiveness e Objection Trends ficam como gap
explícito porque **nenhuma função no sistema gera o dado bruto que
exigem** (não é questão de volume/amostra). Experiments (Fase 14)
fora desta rodada. `agent/sales_science_insights_rules.py` (novo)
orquestra motores já prontos das Fases 8/9/13 via
`sales_science_engine.py::montar_insight()`. `GET /sales-science/
insights` (novo, admin-only, visão agregada de toda a organização) +
aba "🔬 Sales Science" no Dashboard. 14 testes novos. **Testado de
ponta a ponta com dado real**: 200 oportunidades reais com taxa de
conversão propositalmente diferente por estágio confirmaram o sinal
estatístico detectado corretamente via Chromium real. Detalhe
completo em CHANGELOG.md e CLAUDE.md. **Seller Coaching (último
bloco de Dashboard da Fase 22) não começa sem nova confirmação
explícita do usuário.**

Backend **V.1.4.116** (local + GitHub +
**produção confirmada**, `/health` = `versao 1.4.116`): `PATCH
/opportunities/{id}` fecha o CRUD
básico de `Opportunity` — `stage`/`status` independentes no mesmo
body; won/lost exigem os mesmos dados de sempre (`value`/`product`/
`loss_reason`, `agent/outcome_rules.py`, sem duplicação). Dashboard:
`<select>` de status + botão de estágio na ficha, prompts pra won/
lost, ficha sempre recarregada do banco após qualquer mudança. 10
testes novos. **Testado de ponta a ponta com dado real**: mudança de
estágio e transição pra "Ganha" confirmadas via clique/seleção reais
no Chromium. Detalhe completo em CHANGELOG.md e CLAUDE.md. **Sales
Science, Seller Coaching não começam sem nova confirmação explícita
do usuário.**

Backend **V.1.4.115** (local + GitHub +
**produção confirmada**, `/health` = `versao 1.4.115`): `GET`/`POST
/opportunities` (lista/criação),
pré-requisito real que faltava pra Opportunity Intelligence virar
utilizável (sem isso, a ficha só funcionava com ID digitado a mão e
nada criava uma `Opportunity` de verdade). `seller_id` sempre do
token; não-admin só vê as próprias (`Opportunity.seller_id` é
`NOT NULL` desde a criação, sem caso de "sem dono"). Dashboard: aba
"Oportunidades" ganhou lista real (cards clicáveis) + "+ Nova
Oportunidade" (busca cliente por nome via `/clientes`, nunca ID cru).
8 testes novos. **Testado de ponta a ponta com dado real**: 2
oportunidades reais criadas via API, confirmadas na lista, detalhe
aberto via clique real no Chromium (inclusive caso de oportunidade
sem nenhum insight ainda), fluxo de "novo" confirmado terminando num
alerta claro quando não acha cliente (ambiente de teste sem MySQL
local — achado: `agent/client_intelligence.py` não tem fallback
SQLite, diferente do resto do sistema). Inclui também o bump da
versão hardcoded em `/health`/`/monitor/metricas` pra `1.4.115`.
Detalhe completo em CHANGELOG.md e CLAUDE.md. **Sales Science, Seller
Coaching não começam sem nova confirmação explícita do usuário.**

Dashboard: tela **"Oportunidades"**
(Opportunity Intelligence) nova em `frontend/dashboard.html` — consome
`GET /opportunities/{id}/intelligence` (backend já existia desde
V.1.4.114). Sem lista/criação de oportunidades ainda (não existe em
lugar nenhum do Dashboard) — usuário escolheu aba com campo de ID
manual + botão "Ver", mais enxuto. Renderiza Opportunity Health (dado
real de `Opportunity`), os 3 gaps explícitos (SPIN Coverage/MEDDPICC/
riscos calculados) e os 9 campos de dado real de `OpportunityMemory`
(Pain/Impact/Champion/Economic Buyer/Decision Process/Objections/
Competitors/Risks relatados/Next Steps), reaproveitando classes CSS já
existentes (`.info-card`, `.metric`, `.badge-alta`). **Testado de
ponta a ponta com dado real**: backend local forçado pra SQLite (nunca
tocou a produção — achado: `.env` local tem `DB_HOST` apontando pra
VPS de produção; qualquer `DB_*` vazio força o fallback SQLite),
oportunidade + 9 insights reais criados via `api.database` direto,
Chromium real via Playwright confirmando as 12 seções renderizadas
sem erro. Sem bump de versão de backend (só `frontend/dashboard.html`
mudou). Detalhe completo em CHANGELOG.md. **Sales Science e Seller
Coaching (os outros 2 blocos de Dashboard da Fase 22) e lista/criação
de oportunidades não começam sem nova confirmação explícita do
usuário.**

Extensão Chrome **V.1.4.16**: usuário
reportou via DevTools que a captura de áudio da aba (V.1.4.7) nunca
funcionava de verdade — `chrome.tabCapture` recusava com "Extension
has not been invoked for the current page (see activeTab permission)"
porque o botão que a iniciava ficava dentro da sidebar (injetada pela
própria página), e isso nunca satisfaz o gesto que o Chrome exige
(ícone da barra de ferramentas). Corrigido movendo o início da
captura pro `popup.html` — abrir o popup já é o gesto válido. Sidebar
continua controlando o microfone e, ao parar, também encerra a
captura da aba. `1.4.15` → `1.4.16`. Detalhe completo no CHANGELOG.md.
**Confirmado pelo usuário numa reunião real (19/09/2026)** — funcionou
após reinstalação manual da extensão.

Backend **V.1.4.114** (local + GitHub +
**produção confirmada** na VPS, `/health` = `versao 1.4.114`): Fase 22
(Frontend) / bloco 2
("Opportunity Intelligence" no Dashboard). Usuário confirmou avançar
para este bloco após o bloco 1 (sidebar, extensão V.1.4.15, abaixo).
Investigação prévia achou o problema central: `OpportunityMemory`
(Fase 2) guarda insights genéricos por categoria de negócio
(`pain_points`/`champion`/etc.), mas SPIN Coverage e MEDDPICC exigem
formatos de fato completamente diferentes (vocabulário SPIN/status
UNKNOWN-PARTIAL-CONFIRMED) que nenhuma função no código traduz ainda
— mesmo problema para os riscos *calculados* de `deal_risk_rules.py`
(sinais não computados em lugar nenhum). Usuário escolheu **só expor
dado real; documentar os 3 como gap explícito**, mesma disciplina de
`RAG_LATENCY_NAO_CAPTURADA` (Fase 19). Novo
`agent/opportunity_intelligence_rules.py` (função pura,
`montar_opportunity_intelligence`) + `GET /opportunities/{id}/
intelligence` (novo endpoint, JWT + ownership via
`_verificar_dono_ou_admin`, mesmo padrão de `GET /clientes/{id}`) — 9
dos 12 campos literais são pass-through direto de `OpportunityMemory`,
Opportunity Health é composto de campos reais de `Opportunity`, 3
ficam como gap (`spin_coverage`/`meddpicc`/`risks_calculados`). 16
testes novos (9 módulo puro + 7 endpoint). **Suite completa: 1156
testes, 0 falhas**, 1 skip pré-existente — sem regressão. Sem UI no
Dashboard ainda (só o endpoint agregador). Detalhe completo em
CHANGELOG.md e CLAUDE.md. **Sales Science e Seller Coaching (os
outros 2 blocos de Dashboard da Fase 22) e a tela HTML/JS do
Opportunity Intelligence não começam sem nova confirmação explícita
do usuário.**

## Bloco 1 — sidebar simplificada (extensão V.1.4.15)

Extensão Chrome **V.1.4.15** (sidebar
simplificada, Fase 22 / bloco 1 do "PROMPT MESTRE — SALE-IA V2"):
usuário confirmou avançar para a Fase 22 (Frontend); texto literal
pede sidebar mínima ao vivo (`ALERTA/PRÓXIMA AÇÃO/PRÓXIMA
PERGUNTA/POR QUÊ/EVITE`) + 3 blocos de Dashboard (Opportunity
Intelligence, Sales Science, Seller Coaching) que dependem de ~10
endpoints agregadores ainda não construídos pelas Fases 3-13.
Escopo confirmado com o usuário: **só o bloco 1 (sidebar) nesta
rodada** — autocontido em `chrome-extension/`, sem tocar em
backend. `chrome-extension/content.js` removeu as 7 seções de
leitura analítica passiva da tela ao vivo (DISC, Temperatura,
Estágio/KARE, Maturidade, Objeção Detectada, Dado Esquecido,
Propensão) — o backend continua calculando/persistindo tudo
normalmente, só o *render* ao vivo mudou. Caixa única remanescente
("🎯 PRÓXIMA AÇÃO / PERGUNTA") ganhou o bloco **EVITE**, ligado a
`next_best_action.evite` — campo que nenhum agente em produção
preenche hoje (só definido no contrato de `next_best_action_v2_rules.py`,
Fase 16, não integrado ao orquestrador), então fica sempre oculto
até essa integração futura — nunca inventado no cliente. Limpeza de
3 funções JS + constantes + seletores CSS que ficaram 100% órfãos.
Validado com `node --check` (sintaxe), **não testado ao vivo numa
reunião real ainda**. **Achado + fix nesta mesma rodada**:
`chrome-extension/content.css` nunca é injetado em produção
(`manifest.json` só carrega `sidebar.css`) — o bloco de estilos
`.saleia-nbq-evite`/`-risco`/`-followup`/`-type` estava lá e nunca era
aplicado na sidebar real; movido para `sidebar.css`. `content.css`
continua no repo, mas hoje é 100% código morto — decisão de remover
o arquivo por completo não foi tomada, fica para o usuário decidir.
Extensão `1.4.14` → `1.4.15`
(`chrome-extension/manifest.json`); backend inalterado, `V.1.4.113`
continua a versão de produção. Detalhe completo em CHANGELOG.md.
**Os 3 blocos de Dashboard da Fase 22 (Opportunity Intelligence,
Sales Science, Seller Coaching) não começam sem nova confirmação
explícita do usuário** — cada um exige antes decidir o contrato de
vários endpoints agregadores novos.

V.1.4.113 é a **Fase 21 (Testes de Adversarial Sales) do "SALE-IA V2"**.
V.1.4.113 é a **Fase 21 (Testes de Adversarial Sales) do "SALE-IA V2"**.
Investigação prévia: dos 4 casos literais (falar mal do concorrente,
desconto "que o chefe não precisa saber", garantir 200% de retorno,
"ignore suas regras"), o 4º já estava 100% coberto pela Tarefa 18.2. O
1º e o 3º não tinham guarda nenhuma; o 2º tinha cobertura parcial via
`agent/autonomy_policy_rules.py::avaliar_desconto()` (Fase 17, nunca
conectada a fluxo real). Usuário escolheu **guarda real no
choke-point de IA (mesmo padrão arquitetural da Tarefa 18.2) + os 4
cenários como testes Promptfoo**. `agent/adversarial_sales_rules.py`
(novo): `ADVERSARIAL_SALES_GUARD_TEXT` cobrindo os 3 casos sem guarda
prévia, anexado em `api/ai_router.py::chamar_ia` (junto de
`FORBIDDEN_TRIGGER_RULE`/`PROMPT_INJECTION_GUARD_TEXT`) e no caminho
manual do fallback pra Conta Claude (`agent/multiagente/
claude_fallback.py`) — cobre ~100% do tráfego de IA sem editar
templates. `evals/scenarios/red_team.yaml` ganhou os 4 cenários
literais (agora 10 no total), nunca rodados nesta rodada (custo real
de IA). 13 testes novos (2 módulo puro + 2 choke-point + 1 fallback +
4 estrutura YAML + os que já existiam ajustados). Ver seção "Testes de
Adversarial Sales — Fase 21" no CLAUDE.md e CHANGELOG.md V.1.4.113.
**Deploy confirmado (18/09/2026)**: commit `a0d1daf`, `reunioes_ativas:
0` checado antes do `git pull` e do restart — `/health` = `versao
1.4.113`, `status online`, 4 provedores `ok`; `/dashboard` = `200`;
journal sem erros. **Fase 22 (Frontend) ou qualquer outra tarefa
pendente do "SALE-IA V2" não começa sem nova confirmação explícita do
usuário.**

V.1.4.112 é a **Fase 20 (Golden Sales Dataset) do "SALE-IA V2"**.
Usuário confirmou o escopo (pergunta direta): só o dataset em
`evals/datasets/golden_sales_dataset/` (10 categorias literais ×
4 cenários = 40 no total), schema literal do prompt mestre (`INPUT`/
`EXPECTED FACTS`/`EXPECTED EVENTS`/`EXPECTED FRAMEWORK`/
`ACCEPTABLE ACTIONS`/`FORBIDDEN ACTIONS`), **sem conectar a nenhum
runner/Promptfoo nesta rodada** — mesma disciplina "contrato primeiro"
do resto do roadmap. Todos os cenários são sintéticos (nenhum dado
pessoal real). `expected_events` usa só o vocabulário fechado de
`SALES_EVENT_TYPES` (Fase 1); `expected_framework` usa só
`SALES_REASONING_FRAMEWORKS` (Fase 7) ou `null`. 12 testes novos
(`tests/test_golden_sales_dataset.py`) validam estrutura/taxonomias
via `yaml.safe_load` — nunca chamam IA. `PyYAML` adicionado ao
`requirements.txt` (pinado explicitamente, antes só dependência
transitiva). Ver seção "Golden Sales Dataset — Fase 20" no CLAUDE.md e
CHANGELOG.md V.1.4.112. **Deploy confirmado (18/09/2026)**: commit
`d4cff17`, `reunioes_ativas: 0` checado antes do `git pull`/`pip
install` e antes do restart — `/health` = `versao 1.4.112`, `status
online`, 4 provedores `ok`; `/dashboard` = `200`; journal sem erros.
**Qualquer fase seguinte do "SALE-IA V2" (Fase 21 — Testes de
Adversarial Sales, ou voltar à Tarefa 19.1 com dado real) não começa
sem nova confirmação explícita do usuário.**

V.1.4.111 é a **Tarefa 19.1 (Quality Monitoring) do "SALE-IA V2"**.
Investigação prévia (antes de perguntar escopo): as 6 métricas
literais (event_precision, objection_precision, framework_accuracy,
recommendation_relevance, hallucination_rate, evidence_coverage)
exigem comparar a saída da IA contra um gabarito rotulado — exatamente
o que a Fase 20 ("Golden Sales Dataset"), ainda não construída,
deveria fornecer. Sem gabarito real, nenhuma pode gerar número
verdadeiro hoje. Usuário escolheu **só as fórmulas corretas, sem dado
real** — mesma disciplina de honestidade dos 2 gaps da Fase 19.
`agent/quality_monitoring_rules.py` (novo, função pura): 6 funções
nomeadas pelas métricas literais (`calcular_event_precision`/
`calcular_objection_precision`/`calcular_framework_accuracy`/
`calcular_recommendation_relevance`/`calcular_hallucination_rate`/
`calcular_evidence_coverage`), reaproveitando `calcular_taxa()` (Fase
19) pra aritmética comum, + `QUALITY_METRIC_SEM_GABARITO` (dict
explícito documentando o gap). **Sem endpoint HTTP** (decisão
deliberada desta rodada — as 6 métricas retornariam só o gap hoje).
16 testes novos. Ver seção "Quality Monitoring — Tarefa 19.1" no
CLAUDE.md e CHANGELOG.md V.1.4.111. **Deploy confirmado (18/09/2026)**:
commit `c1f5cf2`, `reunioes_ativas: 0` checado antes do `git pull` e
do restart — `/health` = `versao 1.4.111`, `status online`, 4
provedores `ok`; `/dashboard` = `200`; journal sem erros. **Fase 20
(Golden Sales Dataset) e qualquer fase seguinte do "SALE-IA V2" não
começam sem
nova confirmação explícita do usuário.**

V.1.4.110 é um **fix de bug ativo em produção**, achado incidental
durante a checagem pós-deploy da Fase 19 (não faz parte do roadmap
"SALE-IA V2"): `MeetingMemory.score_history_json`/`key_moments_json`/
`events_json` continuavam `Column(Text, ...)` puro (limite 64KB do
MySQL) — mesma classe de bug já corrigida 2x antes (V.1.4.54,
V.1.4.100), mas essas 3 colunas nunca tinham recebido o fix. 30+
ocorrências reais de `pymysql.err.DataError (1406, "Data too long for
column 'key_moments_json'")` no journal de 18/09/2026 numa reunião
longa. Corrigido pra `_LongText` (MEDIUMTEXT), mesmo padrão de sempre.
1 teste novo (`tests/test_meeting_memory_mediumtext.py`) confirmando
as 7 colunas (4 já corrigidas + 3 novas) compilam pra MEDIUMTEXT. Ver
CLAUDE.md/CHANGELOG.md V.1.4.110. **Deploy confirmado (18/09/2026)**:
commit `1d2cdeb`. `reunioes_ativas: 0` checado antes do `ALTER TABLE`
(`DESCRIBE meeting_memory` confirmou as 3 colunas em `mediumtext`) e
de novo antes do restart — `/health` = `versao 1.4.110`, `status
online`, 4 provedores `ok`; `/dashboard` = `200`; journal sem erros.

V.1.4.109 é a **Fase 19 (Observabilidade) do "SALE-IA V2"**. Usuário
confirmou o escopo (pergunta direta, investigação prévia): das 10
métricas literais da fase (AI latency, recommendation latency, RAG
latency, cost per meeting, cost per opportunity, tokens, fallback
rate, error rate, recommendation acceptance rate, recommendation
effectiveness), a maior parte já tinha dado bruto capturado desde o
Cost Intelligence (Fase 1-2) e a Recommendation Fase 10 — só faltava
agregação. **RAG latency** não tem nenhuma cronometragem hoje (fica
documentada como gap — `agent/observability_metrics_rules.py::
RAG_LATENCY_NAO_CAPTURADA`); **recommendation effectiveness** tem a
fórmula pronta (Fase 10.3) mas nenhum dado real classificado
alimentando-a (gap também documentado); **recommendation acceptance
rate** é exposta como proxy barato (taxa de resposta do vendedor, não
a classificação semântica real da Fase 10.2). Novo endpoint `GET
/admin/observabilidade/metricas` (admin) consolida as 8 métricas reais
+ os 2 gaps explícitos. `agent/observability_metrics_rules.py` (novo,
função pura) + 4 funções novas em `api/database.py`
(`latencia_por_feature`/`custo_medio_por_reuniao`/
`custo_medio_por_opportunity`/`taxa_resposta_recomendacoes`) —
reaproveitam `ai_usage_events`/`recommendation_events` já existentes,
sem tabela/coluna nova. 22 testes novos. Ver seção "Observabilidade —
Fase 19" no CLAUDE.md e CHANGELOG.md V.1.4.109. **Deploy confirmado
(18/09/2026)**: commit `dfcbffd`; o restart manual ficou bloqueado por
~2h20min de reuniões reais consecutivas, mas o restart diário
automático do systemd (`RuntimeMaxSec=86400`) aplicou o deploy sozinho
às 06:40:57 UTC — `/health` = `versao 1.4.109`, `GET /admin/
observabilidade/metricas` responde `401` sem token (rota existe).
**Tarefa 19.1 (Quality Monitoring) e qualquer fase seguinte do
"SALE-IA V2" não começam sem nova confirmação explícita do usuário.**

V.1.4.108 é a **Fase 18 / Tarefa 18.4 (Audit Trail) do "SALE-IA V2"** —
**fecha a Fase 18 (Segurança) completa** (Tarefas 18.1-18.4). Usuário
confirmou o escopo (pergunta direta): só schema + CRUD do
`AuditTrailEntry`, sem integração automática com nenhum fluxo real
ainda (mesma disciplina "contrato primeiro" da maioria das Fases
1-17) — texto literal do prompt mestre diz que é "especialmente para
recomendações autônomas futuras", e a `AutonomyPolicy` da Fase 17
continua dormente (nenhum nível de autonomia ativo em produção).
`agent/audit_trail_rules.py` (novo): `validar_audit_trail_entry()`
exige `actor`/`action`/`reason`/`result` (os 4 campos que dão sentido a
uma entrada de auditoria); `meeting_id`/`opportunity_id`/`data_used`/
`model`/`prompt_version`/`rule_version` são opcionais (nem toda ação
auditada envolve IA ou está ligada a uma reunião específica).
`api/database.py::AuditTrailEntry` (tabela `audit_trail_entries`, nova)
+ `criar_audit_trail_entry()`/`obter_audit_trail_entry()`/
`listar_audit_trail_entries()` — dado de domínio, propaga `ValueError`
em dado inválido, mesma disciplina de `SalesEvent`/`RecommendationEvent`
(Fases 1/10). 11 testes novos. Ver seção "Audit Trail — Fase 18" no
CLAUDE.md e CHANGELOG.md V.1.4.108. **Deploy confirmado (17/09/2026)**:
commit `029ea73`. **Incidente real durante o restart** — corrida de
DDL entre os 2 workers do uvicorn criando `audit_trail_entries`
simultaneamente derrubou um worker (`pymysql.err.OperationalError
1684`), `systemd` reiniciou automaticamente (~12s de indisponibilidade
real, 18:05:00–18:05:12 UTC); na 2ª tentativa a tabela já existia, sem
disputa. Ver detalhe completo e risco pra futuros deploys com tabela
nova em "Audit Trail — Fase 18" no CLAUDE.md. Pós-recuperação:
`/health` = `versao 1.4.108`, `status online`, 4 provedores `ok`;
`/dashboard` = `200`; tráfego real servido sem erro novo desde então.
**Fase 19 (Observabilidade) e qualquer fase seguinte do "SALE-IA V2"
não começam sem nova confirmação explícita do usuário.**

V.1.4.107 é a **Fase 18 / Tarefa 18.3 (PII — Classificação de Dados +
Redação de Segredos) do "SALE-IA V2"**. Usuário confirmou o escopo
(pergunta direta de escopo): classificação (5 níveis literais) +
redação real conectada ao logger de produção; retenção fica só como
contrato de referência (prazos sugeridos, não vinculantes — decisão de
produto/jurídica sobre prazo real fica pendente, sem job de expiração
automática). `agent/data_classification_rules.py` (novo):
`DATA_CLASSIFICATION_LEVELS` (`PUBLIC`/`INTERNAL`/`CONFIDENTIAL`/`PII`/
`SENSITIVE`) + `CLASSIFICACAO_CAMPOS_PADRAO` (tabela de referência,
não exaustiva) + `redigir_segredos()`/`redigir_dict()` (nunca logar
senha/token/Authorization header/API key — nunca bloqueia, só mascara).
Conectado de verdade ao logger de produção: `api/main.py::
_JsonFormatter` agora redige toda mensagem/exceção antes de virar log,
e `_configurar_logging()` passou a anexar o mesmo formatter também no
logger root (não só em `"saleia.*"`) — sem isso, módulos que usam
`logging.getLogger(__name__)` (ex.: `agent/multiagente/
claude_fallback.py`) caíam no handler de último recurso do Python,
sem JSON e sem redação nenhuma. 20 testes novos. Ver seção "PII —
Classificação de Dados + Redação de Segredos — Fase 18" no CLAUDE.md
e CHANGELOG.md V.1.4.107. **Deploy confirmado (17/09/2026)**: commit
`a16f0a5`. Reunião real bloqueou o restart por ~2h20min
(`reunioes_ativas: 1`) — `git pull` já aplicado com segurança antes
(só arquivos em disco); `systemctl restart saleia` executado assim
que `reunioes_ativas` voltou a `0`. `/health` = `versao 1.4.107`,
`status online`, 4 provedores `ok`; `/dashboard` = `200`; journal sem
erros de aplicação. Tarefa 18.4 (Audit Trail) não começa sem nova
confirmação explícita do usuário.

V.1.4.106 é a **Fase 18 / Tarefa 18.2 (Prompt Injection Hardening) do
"SALE-IA V2"** — documentos e transcrições são sempre dado, nunca
instrução. `agent/prompt_injection_rules.py` (novo): detector por regex
(generaliza o que já existia só para upload de documento no Knowledge
Compiler, Fase 1) + `PROMPT_INJECTION_GUARD_TEXT`, anexado a todo
`system_prompt` no único choke-point de IA (`api/ai_router.py::
chamar_ia`) e no caminho manual do fallback pra Conta Claude pessoal
(`agent/multiagente/claude_fallback.py`) — cobre ~100% do tráfego sem
editar os ~20 templates de prompt individualmente. Detecção nunca
bloqueia, só loga para auditoria futura (Tarefa 18.4). 15 testes novos.
Ver seção "Prompt Injection Hardening — Fase 18" no CLAUDE.md e
CHANGELOG.md V.1.4.106. **Deploy confirmado (17/09/2026)**: commit
`1289b0b`, `reunioes_ativas: 0` checado antes do `git pull` e do
restart (deploy só de código), `systemctl restart saleia` — `/health`
= `versao 1.4.106`, `status online`, `/dashboard` = `200`, journal sem
erros. Tarefas 18.3 (PII) e 18.4 (Audit Trail) não
começam sem nova confirmação explícita do usuário.

V.1.4.105 é a **Fase 18 / Tarefa 18.1 (Tenant/User Isolation) do
"SALE-IA V2"** — fix crítico de segurança real (não módulo isolado
como as Fases 14-17): `POST /recapitulacao-viva` não tinha
autenticação alguma (achado já documentado desde a Fase 0,
V.1.4.72); auditoria revelou que nenhuma tabela principal tinha
coluna de dono. `MeetingMemory.usuario_id` e `client_profiles.
usuario_id` (novos) + `_verificar_dono_ou_admin()` aplicado em ~15
endpoints. Dado sem dono continua aberto a qualquer autenticado
(decisão confirmada); `/cenario/*` continua público por design.
20 testes novos (`tests/test_tenant_isolation.py`) + 3 testes
pré-existentes corrigidos (2 assumiam o comportamento antigo sem
auth, 1 não isolava o engine em SQLite de memória e caiu no schema
desatualizado do `data/saleia.db` local). Ver seção "Tenant/User
Isolation — Fase 18" no CLAUDE.md e CHANGELOG.md V.1.4.105.
**Deploy confirmado em produção (17/09/2026)**: commit `ecfd028`,
`ALTER TABLE meeting_memory ADD COLUMN usuario_id VARCHAR(36) NULL`
aplicado com `reunioes_ativas: 0` confirmado antes, `systemctl
restart saleia` — `/health` = `versao 1.4.105`, `/dashboard` = `200`,
journal sem erros. `client_profiles.usuario_id` self-migrating
confirmado no mesmo restart.

V.1.4.104 **fecha a Fase 17 (Preparação para Autonomia)
do "SALE-IA V2"** — `agent/autonomy_policy_rules.py` (conceito `AutonomyPolicy`
com os 6 níveis literais + Decision Boundaries da Tarefa 17.1, com a
garantia estrutural "nenhum LLM pode contornar políticas" —
FORBIDDEN/HUMAN_REQUIRED/HUMAN_APPROVAL bloqueados em qualquer nível
de autonomia, inclusive o máximo). Regra explícita da própria fase
("ainda não colocar agente para vender sozinho") — nenhum nível é de
fato ativado, sem integração com `orquestrador.py`. Ver seção
"Preparação para Autonomia — Fase 17" no CLAUDE.md e CHANGELOG.md
V.1.4.104. Sem endpoint HTTP novo, sem tabela/coluna nova.

V.1.4.103 **fecha a Fase 16 (Next Best Action V2) do "SALE-IA V2"** —
`agent/next_best_action_v2_rules.py` (contrato + validações
estruturais das 4 consistências literais — fatos, estágio, políticas,
conhecimento disponível — reusando `spin_coverage_rules`/
`meddpicc_rules`/`sales_science_engine` já prontos; sem motor de IA
por decisão de escopo, mesma disciplina das Fases 8-15). Ver seção
"Next Best Action V2 — Fase 16" no CLAUDE.md e CHANGELOG.md V.1.4.103.
Sem endpoint HTTP novo, sem integração com `orquestrador.py`, sem
tabela/coluna nova.

V.1.4.102 **fecha a Fase 15 (Seller DNA) do "SALE-IA V2"** —
`agent/seller_dna_rules.py` (Tarefas 15.1 perfil do vendedor nos 12
campos literais, com guarda de amostra mínima, e 15.2 guarda
estrutural "comportamento vs. eficácia" — SellerDNA nunca alega que um
comportamento observado funciona, só o Sales Science Engine, Fase 13,
mede eficácia). Ver seção "Seller DNA — Fase 15" no CLAUDE.md e
CHANGELOG.md V.1.4.102. Sem endpoint HTTP novo, sem integração com
`orquestrador.py`, sem tabela/coluna nova.

V.1.4.101 **fecha a Fase 14 (Experiment Engine) do "SALE-IA V2"** —
`agent/experiment_engine_rules.py` (Tarefas 14.1 hipótese→teste e
14.2 A/B controlado + guarda de segurança fail-closed dos 5 itens do
prompt mestre). Ver seção "Experiment Engine — Fase 14" no CLAUDE.md
e CHANGELOG.md V.1.4.101. Sem endpoint HTTP novo, sem integração com
`orquestrador.py`, sem tabela/coluna nova — deploy foi só `git pull` +
`systemctl restart saleia` (`reunioes_ativas: 0` confirmado
antes/depois), `/health` = `versao 1.4.101`, journal sem erros.

V.1.4.100 **fecha o bug ativo do incidente 15-16/09/2026**:
`MeetingMemory.transcript_full`/`transcript_buffer`/
`accumulated_summary`/`current_diagnosis` trocados de `Text` puro
(64KB no MySQL) para `_LongText`/`MEDIUMTEXT` (até 16MB) — mesmo
padrão já usado em `KnowledgeSource` desde a V.1.4.54. `ALTER TABLE`
manual aplicado na VPS com `reunioes_ativas: 0` confirmado (`DESCRIBE
meeting_memory` confirmou as 4 colunas em `mediumtext`) +
`systemctl restart saleia` — `/health` = `versao 1.4.100`, `status
online`, journal sem erros.

V.1.4.99 **fecha a Fase 13 (Sales Science Engine) por completo** do
"SALE-IA V2" — os 2 submódulos que faltavam,
`agent/objection_trend_analyzer.py` (tendência de categoria de
objeção ao longo do tempo) e `agent/conversion_driver_analyzer.py`
(ranking do que mais impulsiona conversão), com seus wrappers em
`agent/sales_science_engine.py`. Ver seção "Sales Science Engine —
Fase 13 (fecho)" abaixo e CHANGELOG.md V.1.4.99. Sem endpoint HTTP
novo, sem integração com `orquestrador.py`. V.1.4.91-98 (Fases 10, 11
e 12 completas + Fase 13 parcial) foram deployadas na VPS em
15-16/09/2026 (`/health` confirmou `versao 1.4.98`, `reunioes_ativas:
0` checado antes do restart — o restart de V.1.4.98 ficou bloqueado
por reuniões reais em andamento por ~100min e foi concluído
automaticamente assim que a última terminou, journal sem erros —
ver também "Incidente ao vivo" abaixo, achado durante essa espera).
V.1.4.99 foi deployada em seguida (commit `ea6e4bc`, `reunioes_ativas:
0` confirmado, `/health` = `versao 1.4.99`).

## Incidente ao vivo — 15-16/09/2026 (reunião longa: saldo esgotado + coluna de transcrição estourada)

Durante a espera pela janela segura de restart do V.1.4.98 (reunião
real bloqueando o deploy), monitoramento do `/health` mostrou os 4
provedores centrais de IA degradados/em cooldown com centenas de
falhas consecutivas. Investigação via `journalctl` (só leitura, sem
nenhuma ação na reunião ativa) encontrou **dois problemas reais
simultâneos**, o segundo deles **novo, nunca documentado antes**:

1. **DeepSeek `402 Insufficient Balance`** desde `21:32:52` (15/09,
   ~3h+ contínuas até o momento desta nota) — **1.740 ocorrências**
   no log em 3h. Mesmo padrão já visto no incidente de 31/08/2026:
   saldo da conta esgotado faz todo ciclo de `/tempo-real` cair em
   cascata pelos 4 provedores (`openai`/`anthropic`/`gemini` também em
   cooldown). **Fallback para Conta Claude pessoal do vendedor
   (`agent/multiagente/claude_fallback.py`, V.1.4.49) não disparou**
   nesta reunião — nenhuma linha de `claude_fallback`/`claude_account`
   no journal das últimas 90min, mesmo achado de "vendedor sem login
   na extensão" do incidente anterior.
2. **NOVO — `MeetingMemory.transcript_full`: `pymysql.err.DataError
   (1406, "Data too long for column 'transcript_full'")`** desde
   `22:58:44` (15/09) — **380 ocorrências** desde então, toda tentativa
   de salvar um novo fragmento de transcrição falhando. **Causa raiz
   confirmada no código**: `api/database.py::MeetingMemory.
   transcript_full`/`transcript_buffer`/`accumulated_summary`/
   `current_diagnosis` continuam `Column(Text, ...)` — limite de 64KB
   do MySQL `TEXT` puro — **nunca receberam o mesmo fix de
   `Text().with_variant(MEDIUMTEXT, "mysql")`** já aplicado em
   `KnowledgeSource.texto_extraido`/`sections_json` (V.1.4.54, mesma
   classe de bug). Uma reunião comum nunca gerava transcrição longa o
   bastante pra estourar 64KB — esta é (pelo menos) a primeira vez
   registrada que isso acontece de verdade em produção. **Efeito
   prático**: a partir de `22:58:44`, `transcript_full`/
   `transcript_buffer` dessa reunião ficaram congelados no MySQL —
   tudo que foi falado depois disso nunca foi persistido (a análise em
   tempo real na sidebar do vendedor pode continuar funcionando via
   memória do processo, mas o relatório final/recapitulação gerados a
   partir do banco vão refletir só a transcrição até esse instante).
3. **Nenhuma ação corretiva tomada nesta rodada** — nem no saldo
   (decisão de produto/financeira, fora do escopo técnico), nem no
   schema `MeetingMemory` (mudar coluna em produção com reunião ativa
   é uma decisão de deploy separada, precisa de confirmação explícita
   e da mesma disciplina seguinda em V.1.4.54: `ALTER TABLE` manual +
   `reunioes_ativas: 0` antes de aplicar). Achado registrado aqui para
   a próxima sessão não perder o contexto.
- **Recomendação para quando for corrigir**: mesmo padrão já usado em
  V.1.4.54 — `ALTER TABLE meeting_memory MODIFY transcript_full
  MEDIUMTEXT, MODIFY transcript_buffer MEDIUMTEXT, MODIFY
  accumulated_summary MEDIUMTEXT, MODIFY current_diagnosis MEDIUMTEXT`
  na VPS (com `reunioes_ativas: 0` confirmado antes) + atualizar
  `api/database.py` pra `Text().with_variant(MEDIUMTEXT, "mysql")` nas
  4 colunas, igual ao que já foi feito para `KnowledgeSource`.
- **Atualização (16/09/2026, ~01:13 UTC, pós-deploy V.1.4.98)**: o
  restart do `saleia.service` para aplicar V.1.4.98 zerou os
  contadores de falha em memória (mesmo efeito colateral já
  documentado em deploys anteriores — não resolve o saldo de
  verdade), mas **em menos de 10min uma nova reunião real
  (`reunioes_ativas: 1`) já reacumulava falhas nos 4 provedores**
  (`/health` = `status: "degradado"`, não mais `"online"`). Journal
  confirma um **segundo provedor com crédito esgotado de verdade**:
  `openai` — `429 insufficient_quota`, `"You have no credits
  remaining"` — além do `402 Insufficient Balance` já confirmado do
  `deepseek`. Isso muda o quadro: **2 dos 4 provedores centrais têm
  problema de cobrança confirmado**, não só 1 (o achado original desta
  seção citava só DeepSeek). Segue sem nenhuma ação corretiva tomada
  — decisão financeira/de produto, fora do escopo técnico.
- **Checagem final (16/09/2026, ~02:04 UTC)**: `reunioes_ativas: 0`
  (nenhuma reunião ativa no momento) e **zero ocorrências novas** de
  `"Data too long for column"`/`"Insufficient Balance"`/
  `"insufficient_quota"` no journal desde o restart do V.1.4.99
  (`01:47:12` UTC) — os erros vistos minutos antes eram resíduo da
  reunião longa que acabou de terminar, não um problema novo
  acontecendo agora. **Isso não fecha o incidente**: saldo de
  DeepSeek/OpenAI continua esgotado (só não há chamada de IA
  acontecendo pra expor isso sem reunião ativa) e a coluna
  `transcript_full` continua sem o fix `MEDIUMTEXT` — ambos voltam a
  se manifestar assim que a próxima reunião de IA rodar/for longa o
  bastante.

O corpo deste documento nao acompanhou o
CHANGELOG.md entre V.1.4.54 e V.1.4.66; a fonte de verdade sempre mais
atualizada e o CHANGELOG e o `/health` de producao. Cost Intelligence
Fases 1-6, Observabilidade Fase 1 e Whisper Local seguem concluidas e
confirmadas em producao — ver CHANGELOG.md V.1.4.55-V.1.4.63 e
CLAUDE.md).

## Ambiente

- Pasta canonica local: `C:\Users\phpos\OneDrive\SALE-IA\SALEIA`
- Dominio de producao: `https://api.saleia.app.br` (DNS propagando ~2h apos 09/06/2026 16h UTC)
- Dominio antigo (deprecado): `https://api.saleia.com.br` (VPS antiga ainda ativa)
- Dashboard: `https://api.saleia.app.br/dashboard`
- Backend de producao: FastAPI via `saleia.service`
- Porta interna na VPS: `127.0.0.1:8000`
- Proxy publico: nginx em `80/443` + Cloudflare proxy (nuvem laranja)
- Banco em producao: MySQL local (127.0.0.1) — latencia ~2ms

## Deploy

- VPS nova (dedicada): `37.27.214.33` — CPX32, 4 vCPU, 8GB RAM, 160GB SSD, Helsinki
- VPS antiga (deprecada): `204.168.180.25` — aguarda descomissionamento
- App na VPS: `/opt/saleia`
- Servico: `saleia.service`
- Health: `curl http://127.0.0.1:8000/health` ou `https://api.saleia.app.br/health`
- Deploy via: `git pull` + `systemctl restart saleia`
- Nao sobrescrever em deploy: `.env`, `venv`, `data`, `logs`

## Versao Atual

`V.1.4.54` (local + GitHub + **VPS confirmada em produção**) —
**Biblioteca de Inteligência / Knowledge Compiler Fases 1-3** completas:
extração determinística, compilação com IA em `KnowledgeItem`s
revisáveis, e integração (RAG automático + Skill/Playbook manuais).
**Ativa em produção e validada de ponta a ponta com um arquivo real**
(upload >1MB + extração, após os 2 fixes abaixo). Linha do tempo do
deploy (todos os passos em 01-02/09/2026, madrugada UTC):

1. **Deploy do código** (~00h00 UTC): `git pull` (fast-forward
   `41dedd5` → `ab35a6f`) + `pip install` + `systemctl restart saleia`
   (`reunioes_ativas: 0` checado antes) — `/health` confirmou
   `versao: 1.4.54`, `/dashboard` = `200`, sem erros no journal. Bônus:
   o restart limpou os circuit breakers em memória dos 4 provedores de
   IA centrais (voltaram a `status: ok` — não confirma que o saldo/chave
   deles foi resolvido de verdade, só zera o contador, ver "O Que Falta").
2. **Feature flag ativada** (~00h10 UTC): `KNOWLEDGE_COMPILER_ENABLED=true`
   adicionado ao `.env` da VPS + `systemctl restart saleia` de novo
   (`reunioes_ativas: 0` checado de novo) — confirmado lendo o valor com
   o mesmo `python-dotenv`/`os.getenv` que `api/main.py` usa, direto no
   Python da VPS. Endpoints `/biblioteca/*` passam a responder para
   usuários autenticados.
3. **Fix nginx** (~00h20 UTC): primeiro upload real do usuário (PDF de
   livro) retornou `HTTP 413` genérico — o **nginx**, não o FastAPI,
   estava rejeitando antes de chegar no backend.
   `/etc/nginx/sites-available/saleia` não tinha `client_max_body_size`
   (default do nginx = 1 MB, bem abaixo do limite de 20 MB já validado
   no backend desde a Fase 1). Corrigido com `client_max_body_size 20m;`
   no nível do `server{}` (backup do config original salvo antes),
   `nginx -t` + `systemctl reload nginx` (gracioso, não derruba
   conexões/reuniões ativas). Como o limite ficou no nível do server
   (não numa `location` específica), o fix vale pra todas as rotas —
   `POST /base` (Base de Conhecimento) provavelmente tinha o mesmo
   problema silencioso, corrigido de graça como efeito colateral (não
   validado manualmente ainda com arquivo real >1MB lá).
4. **Fix de schema MEDIUMTEXT** (~00h40 UTC): com o nginx corrigido, o
   mesmo PDF subiu certo, mas `POST .../extrair` quebrou com
   `pymysql.err.DataError (1406, "Data too long for column
   'texto_extraido'")` — `KnowledgeSource.texto_extraido`/`sections_json`
   e `KnowledgeItem.content`/`metadata_json`/`embedding_json` usavam
   `Text` (64KB no MySQL), insuficiente pro texto de um livro inteiro.
   Corrigido no código (`api/database.py`, commit `d444c48`) com
   `Text().with_variant(MEDIUMTEXT, "mysql")` — mesmo padrão que
   `base_conhecimento.texto` já usava. `create_all()` não migra colunas
   existentes, então aplicado `ALTER TABLE ... MODIFY ... MEDIUMTEXT`
   manual nas 5 colunas direto no MySQL de produção (confirmado via
   `DESCRIBE`), `git pull` (`ab35a6f` → `d444c48`), a fonte travada em
   `EXTRACTING` (id=1) resetada para `UPLOADED`, `systemctl restart
   saleia` (`reunioes_ativas: 0` checado antes).
5. **Confirmado pelo usuário**: reextração da fonte id=1 funcionou após
   o fix de `MEDIUMTEXT` — upload + extração validados de ponta a ponta
   em produção real. Compilação (Fase 2) e integração RAG/Skill/Playbook
   (Fase 3) ainda sem teste manual do usuário.

**Fix de regressão** (achado durante a Fase 3, antes de qualquer deploy):
o primeiro edit da Fase 1 havia apagado sem querer o decorator
`@app.get("/cenario/{meeting_id}")` — rota parou de existir
silenciosamente (nenhum teste cobre isso). Corrigido antes do commit da
Fase 2, nunca chegou a afetar produção.

Resumo da versão anterior confirmada em produção:

`V.1.4.51` (local + GitHub, commit `dde7987`) — **confirmado na VPS via SSH**
(01/09/2026, acesso por senha — a chave `saleia_vps` continua nao
autenticando): `git log -1` na VPS confirma commit exato `dde7987`;
`systemctl is-active saleia` = `active`, rodando desde `2026-09-01
06:38:15 UTC`; `/health` local (`127.0.0.1:8000`) responde `versao: 1.4.51`
e `reunioes_ativas: 0`. `GROQ_API_KEY` presente no `.env` (chave nova de
31/08/2026), mas sem chamadas recentes de `/audio-transcricao` no journal —
teste end-to-end da transcricao de audio ainda nao confirmado (ver
"O Que Falta").

Resumo das ultimas versoes:
- **V.1.4.51** — Cost Intelligence Fase 1: fundacao de dados reais de custo de IA (catalogo de precos por modelo, captura de uso real dos 4 provedores, tabela `ai_usage_events`, fix do bug que zerava o custo do tempo real). Ver `docs/cost-intelligence-audit.md` para a auditoria completa e o roadmap das Fases 2-6 (agregacoes/dashboard, Budget Guard, Cost Router inteligente, otimizacao, observabilidade).
- **V.1.4.50** — extensao Chrome passa a informar sua propria versao (`X-Extensao-Versao`) em toda chamada ao backend, exposta como `ext_ver` em todo log estruturado (mesmo padrao do `cid` de correlacao) — motivado pelo incidente de 31/08/2026 (ver abaixo), onde nao foi possivel diferenciar remotamente "extensao desatualizada" de "extensao atualizada mas sem login".
- **V.1.4.49** — login opcional na extensao + fallback do tempo real pra conta Claude do vendedor quando os 4 provedores centrais se esgotarem. **Validado end-to-end em producao real em 31/08/2026** (ver secao "Fallback Claude Account validado" abaixo) — pendencia da propria V.1.4.49 fechada.
- V.1.4.48 (fix allowed_tools/tools), V.1.4.47 (token corrompido por espaco), V.1.4.46 (ANTHROPIC_API_KEY herdada), V.1.4.45 (piloto em Analisar Transcricao) e V.1.4.44 (piloto Claude Account) confirmadas deployadas.

Extensao Chrome: `V.1.4.5` local/GitHub — deploy pendente, precisa reinstalar no navegador do vendedor. VPS antiga (`204.168.180.25`) deprecada.

## Whisper Local — parte da Fase 3 do PROMPT MESTRE (V.1.4.63, 05/09/2026 — DEPLOYADO)

Terceiro provedor de `TRANSCRICAO_PROVEDOR` (junto de `whisper`/`groq`):
`whisper_local`, self-hosted via `faster-whisper` (CPU, sem `torch`),
implementado em `agent/whisper_local.py`. Reaproveita a estrutura
existente de `/audio-transcricao` (refatorada em 3 funcoes despachadas
por dict) em vez de criar a abstracao `services/transcription/` do
prompt mestre original — decisao explicita do usuario. Nao exige chave
de API.

**Deploy confirmado na VPS (05/09/2026 ~19h47 UTC)**: `git pull`
fast-forward `e6eefa4`→`48538a4` (trouxe tambem a V.1.4.62/Langfuse,
nunca deployada antes), `pip install`+`pip check` limpo, `systemctl
restart saleia` ativo, `/health` = `versao 1.4.63`. **Validado com
transcricao real direto na VPS** (processo separado, sem mexer no
servico rodando): modelo `small` baixado do Hugging Face + transcricao
de teste rodaram em 4,4s no total — bem abaixo de qualquer
`proxy_read_timeout` default de nginx, risco descartado.

**Falta**: captura de audio do sistema/aba (hoje so o microfone do
vendedor e capturado, `chrome-extension/offscreen.js`); ativar de fato
`TRANSCRICAO_PROVEDOR=whisper_local` em producao pelo Dashboard (decisao
de produto separada, continua `whisper`/`groq` por enquanto). Detalhe
completo em CHANGELOG.md (V.1.4.63).

## Promptfoo / Evaluation Suite — Fase 2 do PROMPT MESTRE (harness criado, 05/09/2026, sem bump de versao)

`evals/` (raiz do repo `SALEIA/`): suite de avaliacao automatizada dos
agentes reais (Coach/Finance) via Promptfoo, chamando
`agent.multiagente.coach_agent.analisar_coach`/`finance_agent.
analisar_finance` diretamente (sem duplicar `api/ai_router.py`). Inclui
Golden Dataset das 11 categorias de objecao (**22 casos sinteticos**,
nao reunioes reais — sem acesso a producao nesta sessao), cenarios de
Next Best Action, red teaming (injection/role override/exfiltration),
criterios de aprovacao de troca de prompt (`evals/APPROVAL_CRITERIA.md`)
e CI (`.github/workflows/llm-evals.yml`).

**Primeira execucao real confirmada no mesmo dia**: 37/37 casos passaram
via DeepSeek (custo real US$ 0,0122), apos 2 achados de ambiente local
corrigidos (chave DeepSeek local invalida — diferente da chave de
producao na VPS, que funciona; `google-generativeai` faltando no venv
local) e 2 falsos positivos de assert no red team corrigidos (o Coach
resistiu corretamente as manipulacoes, o assert que checava errado).
TAREFA 2.5 (comparar os 4 providers) segue bloqueada — OpenAI/Anthropic
confirmados sem saldo nesta mesma sessao. Detalhe completo em
`evals/README.md` e CHANGELOG.md.

## Observabilidade (Langfuse) — Fase 1 do PROMPT MESTRE concluida (V.1.4.62, 04/09/2026)

`PROMPT MESTRE — EVOLUÇÃO DA SALEIA.txt` (arquivo solto na raiz do
repo, fora de `SALEIA/`) descreve um roadmap de 10 fases de evolucao.
Investigacao do codigo real (nao so da documentacao) encontrou
`services/observability/` ja criado e ja integrado numa sessao anterior
do mesmo dia (`api/ai_router.py`, `api/main.py`,
`api/processador_tempo_real.py`, `agent/multiagente/orquestrador.py`) —
mas nunca commitado, nunca documentado, com 1 teste falhando por
vazamento de ContextVar entre testes. Esta versao fechou a Fase 1
completa: trace por reuniao/ciclo, span por agente (Coach/DISC/Finance/
Closer), retrieval rastreado (RAG/Sales Memory/Knowledge Compiler),
custo+latencia por chamada de IA, skill resolvida rastreada (adicionado
nesta versao), fallback pra Conta Claude pessoal rastreado (adicionado
nesta versao) — atras de `OBSERVABILITY_ENABLED` (`false` por padrao,
`NoOpObservabilityProvider`, zero dependencia de rede quando desligado).
Detalhe completo em CHANGELOG.md (V.1.4.62) e CLAUDE.md.

**Confirmado na mesma auditoria**: a Fase 4 do roadmap (Book-to-Skill)
ja estava ~90% pronta e em producao — e a "Biblioteca de Inteligencia"
ja documentada abaixo (V.1.4.52-54).

**Atualizado em 05/09/2026**: Fase 2 (Promptfoo) ganhou harness completo
e uma execucao real validada (`evals/`, ver secao propria abaixo). Fase
3 (captura/transcricao local estilo Meetily) ganhou o Whisper Local
self-hosted (V.1.4.63) e a captura de audio da aba via `chrome.tabCapture`
(extensao V.1.4.7) — sem as abstracoes formais `MeetingCaptureProvider`/
`TranscriptionProvider` do roadmap original, por decisao deliberada (ver
secoes proprias). Fase 5 (Skill Resolver V2) ganhou `resolver_skills_
relevantes()` (V.1.4.65) com 4 dos 11 triggers novos (os unicos com sinal
estruturado real hoje) — **nao plugada em producao ainda**, so uma
capacidade nova testada e pronta. Fases 6 (Retrieval V2 hibrido), 7
(Agent Router por evento) e a maior parte da 8 (Pilot Analytics completo)
**continuam nao iniciadas**.

**Pendente**: `OBSERVABILITY_ENABLED` continua `false` — ninguem gerou
uma conta Langfuse nem decidiu ativar de fato em producao ainda (decisao
de produto separada, nao tecnica). Deploy na VPS ainda nao feito.

## Incidente ao vivo — 31/08/2026 (reuniao real sem IA por mais de 1h)

Durante checagem de rotina (deploy V.1.4.49 ja confirmado em producao, commit
`12a23d8`), encontrada reuniao real em andamento com o coach 100% fora do ar:
- Os 4 provedores centrais falhando de verdade a cada ciclo de 60s desde
  pelo menos 11:08 (>1h): DeepSeek `402 Insufficient Balance`, OpenAI
  `429 insufficient_quota`, Anthropic `400 credit balance too low`, Gemini
  `400 API_KEY_INVALID` (esse ultimo e novo — antes era faturamento
  suspenso, agora e chave invalida).
- Transcricao de audio (Groq) tambem quebrada: `401 Invalid API Key` em
  todo `POST /audio-transcricao`. **Corrigido pelo usuario durante a sessao**
  (chave Groq atualizada no `.env` da VPS, 31/08/2026) — nao validado
  end-to-end ainda (reuniao ao vivo continuava rodando, sem reiniciar o
  servico pra nao derrubar a sessao).
- O fallback da V.1.4.49 (Claude Account) **nao disparou** para essa
  reuniao: existe 1 conexao `claude_connections` ativa no banco (de testes
  anteriores), mas o `/tempo-real` dessa sessao especifica chegava sempre
  sem `Authorization` — vendedor anonimo, extensao sem login. Nao da pra
  saber pelo servidor se a extensao dele e a 1.4.3/1.4.4 antiga (sem bloco
  de login) ou se e mais nova mas ele nao logou — motivou o fix da V.1.4.50
  acima.
- Nao foi reiniciado o `saleia.service` em nenhum momento desta
  investigacao (`reunioes_ativas: 1` confirmado antes de qualquer comando).

## Fallback Claude Account validado em producao real (31/08/2026, ~20h)

Enquanto a reuniao do incidente acima continuava ativa, o vendedor conectou
a conta Claude pelo Dashboard e depois logou no bloco "Conta" da extensao
(email/senha da conta SALEIA — `POST /auth/login` = `200 OK` as 20:15:45,
apos uma tentativa com credencial errada as 20:14:12 = `401`). No ciclo de
`/tempo-real` seguinte (20:16:31), com os 4 provedores centrais falhando
como no resto do incidente, `agent/multiagente/claude_fallback.py` disparou
pela primeira vez em uso real de producao: **4 analises concluidas com
sucesso** (coach/disc/finance/closer) via `agent/claude_account.py`, custo
real logado pelo proprio SDK — `US$ 0.0296`, `0.0368`, `0.0387`, `0.0585`.
Fecha a pendencia que a V.1.4.49 tinha deixado em aberto ("validar o
fallback disparando de verdade").

**Achado**: conectar a conta Claude no Dashboard e logar na extensao sao
dois passos independentes — so o segundo resolve o `usuario_id` que aciona
o fallback no tempo real. Ter so o primeiro (como estava documentado acima,
"existe 1 conexao claude_connections ativa... mas vendedor anonimo") nao e
suficiente.

## Deploy V.1.4.50/1.4.51 confirmado (01/09/2026) + fix do PAT do GitHub na VPS

- O PAT configurado no `git remote origin` da VPS expirou/foi revogado de
  novo (mesmo tipo de problema corrigido em 16/08/2026, ver V.1.4.38) —
  `git pull` falhava com `Invalid username or token`. Usuario gerou um PAT
  novo no GitHub; `git remote set-url origin` corrigido, `git fetch`/`git
  pull` testados e funcionando.
- `git pull origin main` executado na VPS (fast-forward para `dde7987` =
  V.1.4.50+V.1.4.51) em 31/08/2026 — seguro com reuniao ativa, so atualiza
  arquivos em disco, nao afeta o processo `uvicorn` ja em memoria.
- **`systemctl restart saleia` confirmado aplicado**, verificado via SSH em
  01/09/2026 (`ActiveEnterTimestamp = 2026-09-01 06:38:15 UTC`) — restart
  feito fora desta sessao de doc, na madrugada/manha de 01/09. `git log -1`
  na VPS confirma commit exato `dde7987`.
- **Ainda nao validado**: se a chave nova do `GROQ_API_KEY` (atualizada no
  `.env` em 31/08/2026, presente e confirmada via SSH) resolveu de fato o
  `401 Invalid API Key` na transcricao de audio — o journal nao tem
  nenhuma chamada recente de `/audio-transcricao` para confirmar (sem
  trafego desde o restart). Precisa de um teste real (upload de audio em
  uma reuniao) para fechar essa pendencia.

## Biblioteca de Inteligência / Knowledge Compiler (Fases 1-3 — V.1.4.52-1.4.54)

Feature grande (roadmap de 6 fases) que transforma documentos comerciais
(livros, playbooks, treinamentos, manuais) em conhecimento estruturado
reutilizável pelo RAG/Sales Memory/Playbook/Skill durante reuniões.

**Fase 1 (V.1.4.52)** — upload + extração determinística, sem IA:
- `services/knowledge_compiler/`: extratores de PDF (pypdf + fallback
  pdfplumber), DOCX (python-docx), TXT/MD e HTML — chunking por seção
  real (heading/tamanho de fonte), não por corte fixo de caracteres.
  `sanitize_document_text()` remove unicode invisível e sinaliza (sem
  remover) trechos que parecem prompt injection.
- Tabela `knowledge_sources` (SQLModel, aditiva) + endpoints de upload
  (`POST /biblioteca/fontes`), extração (`POST .../extrair`) e listagem
  (`GET /biblioteca/fontes[/{id}]`).

**Fase 2 (V.1.4.53)** — compilação com IA em `KnowledgeItem`s:
- `services/knowledge_compiler/compiler.py`: 1 chamada de IA por seção
  não sinalizada (seções `potential_instruction_injection` da Fase 1 são
  puladas, não só marcadas), extrai 7 tipos (`FRAMEWORK`, `OBJECTION`,
  `DISCOVERY_QUESTION`, `SCRIPT`, `ANTI_PATTERN`, `DECISION_RULE`,
  `CASE`). Estimativa de custo pré-voo (sem IA) antes de compilar de
  verdade — reaproveita `api/cost_engine.py`/`api/pricing_catalog.py`.
- Tabela `knowledge_items` (SQLModel) — todo item nasce `DRAFT`; dedup
  por similaridade de embedding (threshold 0.92) sinaliza
  `possivel_duplicado_de` sem nunca bloquear ou fazer merge automático;
  revisão humana aprova/rejeita/arquiva. 4 endpoints novos
  (`GET estimar-custo`, `POST compilar`, `GET itens`,
  `PATCH itens/{id}`).
- Fix de regressão nesta versão: decorator de `/cenario/{meeting_id}`
  apagado sem querer no primeiro edit da Fase 1, corrigido antes do
  commit da Fase 2 (ver `CHANGELOG.md`).
- Dashboard: card de cada fonte ganha "💰 Compilar" (mostra estimativa,
  pede confirmação, só então gasta IA) e "📋 Ver itens" (lista agrupada
  por tipo com aprovar/rejeitar e badge de possível duplicata).

**Fase 3 (V.1.4.54)** — integração com RAG/Skill/Playbook:
- `api/database.py::buscar_conhecimento_compilado_similar()` — 3º bloco
  de RAG em `orquestrador.py::analisar_fragmento_multi` (junto de base de
  conhecimento e Sales Memory), só itens `APPROVED`, `top_k=2`.
- Skill (`agent/skill_resolver.py::gerar_skill_de_knowledge_item`) e
  Playbook (`agent/playbook_generator.py::gerar_playbook_de_fonte`) são
  **manuais** (botão por item/fonte no dashboard), sem custo de IA.
- Deliberadamente sem mapeamento `KnowledgeItem` → `sales_memory`
  (duplicaria conteúdo no contexto da IA).

**Comum às três fases**:
- Atrás de `KNOWLEDGE_COMPILER_ENABLED` (`false` por padrão — endpoints
  somem, `404`, mesmo padrão do `CLAUDE_ACCOUNT_PILOT`).
- Sem multi-tenant (`organization_id`) — decisão deliberada, mantém a
  mesma linha da V.1.4.40.
- **Deploy + ativação confirmados na VPS (01/09/2026, ~00h UTC)**:
  `git pull` (fast-forward `41dedd5` → `ab35a6f`) + `pip install` +
  `systemctl restart saleia`, depois `KNOWLEDGE_COMPILER_ENABLED=true`
  adicionado ao `.env` + segundo restart. `/health` = `versao 1.4.54`,
  `/dashboard` = `200`, flag confirmada `true` no Python real da VPS, sem
  erros no journal em nenhum dos dois restarts. Endpoints
  `/biblioteca/*` estão de fato acessíveis agora (para usuário
  autenticado) — ainda não testado manualmente no navegador pelo usuário.
- Fases 4-6 (context builder/ranking, governança, UI final) documentadas
  no CHANGELOG mas não iniciadas.

## Funcionalidades Entregues

### Core (V.1.3.x)
- `MeetingMemory` persistida no banco por `meeting_id`.
- Transcricao completa, buffer recente, resumo acumulado, diagnostico atual, historico de score, momentos-chave e eventos.
- Coach em tempo real com envio de contexto reduzido para IA.
- Eventos estruturados e key moments.
- Trigger de recapitulacao por deixa verbal com cooldown.
- Recapitulacao viva com mapa mental para sidebar.
- Diagnostico final pos-reuniao.
- Estimativa de custo das chamadas de IA.
- Roteamento de IA com fallback (DeepSeek → OpenAI → Anthropic → Gemini).
- Dashboard publico carregando em `/dashboard`, `/dashboard/` e `/dashboard.`.
- DeepSeek configurado em producao como provedor preferido.
- Configuracoes em accordion no dashboard (usuarios, APIs, base).
- Conducao ligada aos prompts da apresentacao.
- RAG ajustado para o fluxo atual.

### Autenticacao e Administracao (V.1.4.0)
- Auth JWT: `POST /auth/login`, `POST /auth/cadastro`, `POST /auth/recuperar-senha`.
- Tabela `usuarios` criada automaticamente no startup (MySQL).
- Helper `_req_auth` (qualquer usuario autenticado) e `_req_admin` (apenas admin).
- Admin de usuarios: `GET/PATCH/DELETE /admin/usuarios/*` — perfil, plano, status, reset senha.
- Admin de APIs: `GET/POST/PATCH /admin/api/*` — provedores, chaves, teste, principal.
- `POST /cenario/{meeting_id}/conducao` agora exige JWT valido.

### Recuperacao de Senha (V.1.4.1)
- `agent/email_service.py` — envio real de e-mail SMTP (smtplib stdlib).
- `migrar_colunas_usuarios()` — adiciona `reset_token` e `reset_token_exp` na tabela `usuarios`.
- `POST /auth/recuperar-senha` — gera token seguro (expira 1h), envia e-mail em background, resposta sempre neutra.
- `GET /reset?token=...` — serve pagina HTML inline com formulario de nova senha.
- `POST /auth/redefinir-senha` — valida token, aplica bcrypt, limpa token do banco.
- Variaveis SMTP necessarias no `.env`: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM`, `APP_BASE_URL`.

### Extensao Chrome (V.1.4.1)
- Bug critico corrigido: `background.js::abrirCenarioComFoto` agora le a foto de `chrome.storage.local['saleia_foto_pendente']` em vez de `msg.foto` (que era sempre undefined).
- `manifest.json` versao atualizada para `1.4.1`.
- `popup.js` versao exibida dinamicamente via `chrome.runtime.getManifest().version`.

### Historico de Uso (V.1.4.0)
- `GET /historico/uso` — lista reunioes com custo, score final, DISC, num_analises.
- `GET /historico/uso/{meeting_id}` — detalhe com score_history, key_moments, eventos.
- Pagina Historico no dashboard: grafico de barras de evolucao do score, momentos-chave e eventos.

### Melhorias de Filtros (V.1.4.0)
- Filtros de Reunioes: data De/Ate + botao Limpar + contador de resultados.
- `input[type=date]` com estilo dark no dashboard.

### Testes (V.1.4.0)
- `tests/test_smoke.py`: 8 testes automatizados para `/health`, `/dashboard`, `/recapitulacao-manual`.
- Dependencias `bcrypt` e `PyJWT` adicionadas ao `requirements.txt`.

### Visual Scenario AI (V.1.4.0)
- `POST /generate-visual-scenario`: extrai contexto via IA, gera 2 imagens (atual/futuro) com DALL-E 3.
- `ImageGenerator` usa `response_format=b64_json` — data URI armazenado no banco, sem expiracao.
- `frontend/visual-scenario.html`: webcam do cliente, paineis Atual/Futuro, fullscreen, comparacao, historico.
- `cenario.html` tem botao `Gerar Cenarios` que abre a pagina com o meeting_id da reuniao ativa.

## Estado dos Provedores

Ordem ativa:

1. `deepseek`
2. `openai`
3. `anthropic`
4. `gemini`

Modelos padrao:

- DeepSeek: `deepseek-chat`
- OpenAI: `gpt-4o`
- Anthropic: `claude-sonnet-4-6`
- Gemini: `gemini-2.0-flash`

## Validacoes Recentes

- Visual Scenario fix: webcam espelhada (scaleX -1) + canvas flip + botao Capturar Tela via getDisplayMedia para capturar o cliente do Google Meet.
- Smoke tests: 8/8 OK em 1.1s (`python -m unittest tests.test_smoke -v`).
- `/health` publico respondeu `online`.
- `/dashboard` publico respondeu `200`.
- `/recapitulacao-manual` retornou `200` em producao apos correcoes de fallback.

## Funcionalidades Novas (V.1.4.27–V.1.4.28)

### Fix: 502 Bad Gateway + Estabilidade VPS (V.1.4.27)
- Workers uvicorn entravam em estado zumbi após ~2,5 dias: `systemctl restart saleia` corrigiu
- `RuntimeMaxSec=86400` adicionado ao `/etc/systemd/system/saleia.service` — reinício automático diário
- Logo quebrada no login: `frontend/login.html` src corrigido para `/static/logo-saleia.png`
- `frontend/static/logo-saleia.png` adicionado ao nginx static path

### Motor de Próxima Melhor Ação (V.1.4.28)
- `next_best_action`: tipo (question|insight|warning|next_step), título, mensagem, motivo, risco, follow-up, confidence
- `conversation_stage`: 8 estágios SPIN (abertura → compromisso)
- `kare_type`: keep | attain | recapture | expand
- `maturity_score`: 7 critérios independentes, 0-100
- Matriz de decisão com 10 regras em ordem de prioridade
- Insight Desafiador como tipo formal (Sandler + Venda Desafiadora)
- DISC expandido por perfil em cada regra da matriz
- Sidebar Chrome: badges Stage+KARE, bloco Próxima Melhor Ação com risco/follow-up, grid Maturity Score

### Sales Brain — Inteligência Comercial Acumulativa (V.1.4.31–V.1.4.37)

#### Fase 1 — Memórias de Vendas (V.1.4.31)
- `agent/sales_memory.py`: extrai DISC, objeções, dores, próximos passos, score final e lições após cada reunião.
- Tabela MySQL `sales_memories`: gerada automaticamente no startup.
- Endpoints: `GET /relatorios/{mid}/memoria`, `POST /relatorios/{mid}/gerar-memoria`.

#### Fase 2 — Playbooks (V.1.4.32)
- `agent/playbook_generator.py`: gera roteiro de vendas a partir de reuniões marcadas como ganhas.
- Tabela MySQL `playbooks`: id, meeting_id, titulo, conteudo, disc_profile, stage, score_origem.
- Endpoints: `POST /relatorios/{mid}/marcar-ganha`, `GET /playbooks`, `GET /playbooks/{pid}`, `DELETE /playbooks/{pid}`.
- Dashboard: aba "Playbooks" no menu lateral.

#### Fase 3 — Skills Especializadas (V.1.4.33)
- `agent/skill_resolver.py`: seleciona skill com base em DISC + score + estágio da conversa.
- 5 skills: fechamento, objecao_preco, prospecting, negociacao, reativacao.
- Tabela MySQL `skills`: id, nome, conteudo_instrucao, condicoes_json.
- Integrado ao `processador_tempo_real.py` como `skill_context` injetado em cada fragmento.

#### Fase 4 — Perfil de Clientes / Client Intelligence (V.1.4.34)
- `agent/client_intelligence.py`: CRUD de clientes e vínculo cliente↔reunião.
- Tabelas: `client_profiles` (id, user_id, nome, empresa, cargo, email, whatsapp, notas, status) e `client_meetings` (client_id, meeting_id, score_reuniao, vinculado_em).
- Endpoints: `GET/POST /clientes`, `GET/PATCH/DELETE /clientes/{cid}`, `POST/DELETE /clientes/{cid}/reunioes/{mid}`.
- Dashboard: aba "Clientes" — cards com score médio, total reuniões, último contato, status (ativo/ganho/em_pausa/perdido).
- Relatório: botão "🔗 Vincular ao Cliente".
- Métricas agregadas via JOIN + AVG na query de listagem.

#### Fase 5 — Sistema Multiagente (V.1.4.36)
- `agent/multiagente/orquestrador.py`: dispara 4 agentes em paralelo com `asyncio.gather(return_exceptions=True)`.
- Agentes: Coach (estágio SPIN, NBA, alerta, texto falável), DISC (perfil D/I/S/C, KARE, temperatura), Finance (mapa financeiro, objeções preço), Closer (score, maturity, próxima pergunta).
- RAG buscado uma única vez no orquestrador e compartilhado entre todos os agentes.
- `_safe()` converte Exception em `{}` — se um agente falhar, os outros 3 continuam.
- `_nba_para_nbq()` mantém backward compat com extensões Chrome antigas.
- `processador_tempo_real.py::analyzeRealtimeMeeting` agora chama `analisar_fragmento_multi()` em vez do agente legado.
- skill_context e client_context resolvidos antes do orquestrador nessa função.

#### Fase 6 — Follow-up Inteligente (V.1.4.37)
- `agent/followup_generator.py`: IA gera mensagens para WhatsApp, Email e LinkedIn adaptadas por DISC.
- `agenda_inteligente(score)`: timing server-side (score ≥65 → hot; 35–64 → warm; <35 → cold).
- Tabela MySQL `followups`: id, meeting_id, client_id, canal, assunto, mensagem, call_to_action, tom, disc_profile, score, dias_apos, agendado_para, status (pendente/enviado/descartado).
- Endpoints: `POST /relatorios/{mid}/followups/gerar`, `GET /relatorios/{mid}/followups`, `PATCH /followups/{fid}`, `DELETE /followups/{fid}`.
- Dashboard/Relatório: botão "📩 Follow-up" — seção expandível com cards por canal, botão copiar e marcar enviado.

#### Fase 7 — Sales Operating System (V.1.4.67-1.4.70, 09/09/2026)

Última fase do EPIC "SALEIA SALES BRAIN" — transforma as Fases 1-6 acima
(já isoladas) numa plataforma única com aprendizado contínuo e visão
consolidada. Investigação prévia corrigiu 3 lacunas das Fases 1-6 (busca
semântica de relatórios/transcrições, Resumo do Cliente visual, gate de
aprovação) antes de construir a Fase 7 propriamente dita.

- **V.1.4.67 — Gaps**: `agent/semantic_search.py` (tabela `semantic_index`
  própria, `GET /busca-semantica`) indexa relatório+transcrição de cada
  reunião — **só para busca humana**, nunca injetado de volta no prompt
  de IA em tempo real (evitaria duplicar contexto, mesmo princípio já
  usado pra não mapear `KnowledgeItem → sales_memory`). `GET /clientes/
  resumo-reuniao/{meeting_id}` + card no Dashboard (`verDetalhe()`) —
  **nunca em `cenario.html`**, que é a tela do próprio cliente (achado
  de segurança de dado durante a implementação). Coluna `status`
  (default `'approved'`) preparada em `sales_memories`/`playbooks`/
  `skills` para a rodada seguinte.
- **V.1.4.68 — Aprendizado Contínuo com aprovação (Fase 7.3 do EPIC)**:
  memória/playbook/skill gerados por IA nascem `pending` — só entram em
  uso real (`buscar_memorias_semantico()`, `listar_playbooks(apenas_
  ativos=True)`, `resolver_melhor_skill()`) depois de 1 aprovação
  (`PATCH .../status`), mesma rede de segurança do Knowledge Compiler
  (`DRAFT`/`APPROVED`). Achado: extração de memória e geração de
  playbook **já eram automáticas** desde V.1.4.31/32 — só faltava o
  *gate*, e a geração de skill a partir de playbook (antes só manual)
  passou a auto-disparar também. Kill-switch `SALES_BRAIN_AUTOPILOT_
  ENABLED` (default `true`).
- **V.1.4.69 — Knowledge Graph (Fase 7.2)**: `agent/knowledge_graph.py`
  (tabela `graph_edges`, arestas simples `from_type/from_id/to_type/
  to_id/relacao`, sem lib de grafo) relaciona cliente↔reunião↔memória↔
  playbook↔skill via hooks best-effort nos 4 pontos de criação.
  `GET /grafo/conexoes/{tipo}/{id}` + backfill `scripts/
  backfill_knowledge_graph.py --dry-run` para dado histórico.
- **V.1.4.70 — Workspace Comercial (Fase 7.1)**: nova aba no Dashboard
  (`GET /workspace/resumo`, `GET /workspace/pendencias`) — visão única
  com contadores, fila de aprovação (memória/playbook/skill pendentes)
  e busca semântica, sem precisar visitar 5 abas separadas.
- **Decisão deliberada, não implementada**: skills como pastas de
  arquivo (pedido literal do EPIC) — seria regressão funcional frente ao
  que já existe (skills em MySQL, editáveis pelo dashboard, integradas
  ao `skill_resolver`).
- 48 testes novos no total (9+18+9+8 + 4 do Resumo do Cliente). Suite
  completa sem regressão em cada rodada.
- **Pendente**: deploy das 4 rodadas juntas na VPS — aditivo (2 tabelas
  novas, 1 coluna nova em 3 tabelas, tudo com `DEFAULT` seguro, zero
  mudança de comportamento pra dado já existente até o backfill do grafo
  rodar). Detalhe completo por rodada no `CHANGELOG.md`.

#### Big Five + Astrologia opcional (V.1.4.71, 09/09/2026)

Extensão do motor multiagente — não um produto novo. Objetivo: entender
melhor *por que o cliente* respondeu de determinada forma ou fez uma
objeção, cruzando DISC (já existia) com uma nova camada de Big Five
(inferida da conversa) e, opcionalmente, astrologia (signo solar, só
quando dia/mês de nascimento surgem naturalmente na conversa — nunca
perguntado, nunca inventado).

- **5º agente em tempo real**: `agent/multiagente/bigfive_agent.py`
  (mesmo padrão de `disc_agent.py`), atrás do kill-switch
  `BIGFIVE_AGENT_ENABLED` (default `true` — quando `false`, a coroutine
  nem é criada, zero custo extra). `perfil_bigfive` persiste em
  `MeetingMemory.current_diagnosis` (reuso do campo JSON existente) e
  realimenta Coach/Closer automaticamente no ciclo seguinte, já que
  `{diagnostico_atual}` é lido pelos dois.
- **Astrologia — signo solar, nunca mapa natal**: `agent/signo_solar_
  rules.py` (função pura, sem IA, sem efemérides). Dia/mês só é
  extraído quando mencionado, uma vez, por `PROMPT_RECAPITULACAO`
  (mesma chamada de IA, sem custo novo) — `client_profiles` ganha
  `data_nascimento_dia`/`_mes` (nullable, nunca sobrescrito). **Garantia
  por construção**: nenhum prompt de DISC/Big Five tem canal de entrada
  para dado de signo — astrologia nunca pode ajustar esses scores,
  confirmado por teste de guarda arquitetural (grep + inspeção de
  imports), não só por instrução no prompt.
- **"Por que essa objeção aconteceu"**: `objecoes_com_motivo` +
  `sintese_comportamental` — campos aditivos no relatório final
  (`objecoes_levantadas`, lista de strings usada em 4+ lugares do
  dashboard, nunca mudou de tipo — evita repetir a classe de bug
  "[object Object]" já corrigida antes no projeto).
- Dashboard: 4 cards novos (`verDetalhe()`), astrologia sempre com
  disclaimer visível quando presente.
- 34 testes novos, suite completa sem regressão.
- **Pendente**: deploy na VPS (aditivo — 2 colunas nullable, sem
  migração em `MeetingMemory`); validação real com uma reunião onde o
  cliente menciona o próprio aniversário.

## Fase 0 — "SALE-IA V2": baseline de confiabilidade (V.1.4.72, 09/09/2026)

Usuário colou o "PROMPT MESTRE — SALE-IA V2": iniciativa de 25 fases,
meses de trabalho (SalesEvent, Opportunity, SPIN 2.0, MEDDPICC, Sales
Science, Seller DNA, Autonomy Policy, Clean Architecture). **Só a Fase 0
foi executada nesta rodada** — baseline de testes + E2E de reunião
completa, 100% aditivo, zero mudança de comportamento. Fases 1+
(SalesEvent em diante) **não começaram** — aguardando confirmação
explícita antes de qualquer código de domínio novo.

- Baseline real (não estimado): **512 testes, 0 falhas, 1 skip
  pré-existente**, categorizado em `docs/BASELINE_REPORT_FASE0.md` (9
  categorias pedidas + uma 10ª "Sales Brain/Multiagente" necessária).
- `tests/test_smoke.py` (9→14) e `tests/test_e2e_meeting_lifecycle.py`
  (novo, 6 testes) fecham os gaps de smoke/E2E pedidos pela Tarefa
  0.1/0.2 — detalhe completo no CHANGELOG.md (V.1.4.72).
- **3 achados documentados, não corrigidos**: (1) 🔴 `meeting_id` sem
  controle de ownership — qualquer um que souber o id lê a recapitulação
  viva de outra reunião (`/recapitulacao-viva` sem auth nenhuma); (2) 🔵
  degradação total dos 4 provedores é silenciosa (`analysis_status`
  continua `"updated"` com fallback genérico, sem sinal de falha); (3) 🟡
  extensão Chrome 100% sem teste automatizado. Ver
  `docs/BASELINE_REPORT_FASE0.md` para detalhe e recomendação de cada um.

## SalesEvent — Fase 1 / Tarefa 1.1 do "SALE-IA V2" (V.1.4.73, 10/09/2026)

Usuário confirmou explicitamente o início da Fase 1 (modelo canônico da
venda) do prompt mestre. **Só a Tarefa 1.1 foi executada** — criar o
schema/validação do `SalesEvent`. Tarefa 1.2 (`SalesEvidence`) e
qualquer fase seguinte **não começaram** — aguardando nova confirmação
explícita.

- `api/database.py::SalesEvent` (tabela `sales_events`, aditiva) + regra
  de validação pura em `agent/sales_event_rules.py` (14 `event_type`
  válidos, `confidence` em `[0,1]`, `evidence_quote` obrigatória quando
  `source="conversation"`) — diferente de `AiUsageEvent`/`KnowledgeItem`
  (escrita "melhor esforço"), `criar_sales_event()` propaga `ValueError`
  em dado inválido, por ser dado de domínio.
- **Decisão deliberada**: nenhuma extração automática de eventos a
  partir de transcrição livre foi construída — o teste de integração do
  exemplo do prompt mestre ("Achei caro" → `OBJECTION_RAISED`) chama
  `criar_sales_event()` diretamente com os valores já classificados,
  provando o schema/validação de ponta a ponta. Extração automática
  (por regra determinística ou por IA) fica para tarefa futura.
- 12 testes novos (`tests/test_sales_event.py`). Suite completa: 524
  testes, 0 falhas, 1 skip pré-existente — sem regressão. Detalhe
  completo no CHANGELOG.md (V.1.4.73).
- **Pendente**: push + deploy na VPS (aditivo, 1 tabela nova via
  `create_all()`).

## SalesEvidence — Fase 1 / Tarefa 1.2 do "SALE-IA V2" (V.1.4.74, 10/09/2026)

Sequência direta da Tarefa 1.1. Objetivo do prompt mestre: separar
**interpretação** de **evidência** — nunca salvar só "cliente está
inseguro" (hipótese solta); sempre `type=ADOPTION_RISK` +
`quote="Tenho medo da minha equipe não usar"`.

- `api/database.py::SalesEvidence` (tabela `sales_evidences`, aditiva) +
  regra de validação pura em `agent/sales_evidence_rules.py` — `quote`
  obrigatória e não-vazia (regra central da tarefa: hipótese sem a fala
  que a sustenta nunca é um `SalesEvidence` válido), `type` obrigatório,
  `confidence` em `[0,1]`.
- 10 testes novos (`tests/test_sales_evidence.py`). Suite completa: 534
  testes, 0 falhas, 1 skip pré-existente — sem regressão. Detalhe
  completo no CHANGELOG.md (V.1.4.74).
- **Push + deploy confirmados (10/09/2026)**: commit `6b9a0ab` no
  GitHub. Na VPS, `reunioes_ativas: 1` (reunião real em andamento)
  bloqueou o restart por ~55min — `git pull`/`pip install` feitos antes
  com segurança (só arquivos em disco); `systemctl restart saleia`
  executado assim que `reunioes_ativas` chegou a `0`. Pós-restart:
  `/health` = `versao 1.4.74`, `status online`, sem erros no journal;
  `/dashboard` e `/health` públicos responderam `200`.
- Fase 2 (Opportunity Memory) do roadmap não começa sem nova confirmação
  explícita do usuário.

## Opportunity Memory + Opportunity Graph — Fase 2 completa do "SALE-IA V2" (V.1.4.75, 10/09/2026)

Usuário confirmou a Fase 2 (Tarefa 2.1) e, em seguida, a Tarefa 2.2 —
as duas concluídas nesta rodada.

- **Tarefa 2.1**: `api/database.py::Opportunity`/`OpportunityMemory` —
  entidade superior a `MeetingMemory` (que ganhou coluna
  `opportunity_id`, nullable, aditiva). As 13 categorias do prompt
  mestre são listas JSON **append-only** de insights — regra central
  em `agent/opportunity_memory_rules.py::adicionar_insight()`: nunca
  sobrescreve/remove uma entrada anterior; quando o mesmo `campo`
  recebe um valor diferente entre reuniões, a entrada nova aponta
  `contradiz` para a anterior, e ambas ficam visíveis.
- **Tarefa 2.2**: `api/database.py::OpportunityGraphEdge` — grafo novo
  e deliberadamente separado do `agent/knowledge_graph.py` já
  existente (Sales Brain Fase 7.2, entidades de CRUD, sem evidência
  por aresta); este relaciona nós `CLIENT`/`PAIN`/`IMPACT`/`GOAL`/
  `OBJECTION`/`STAKEHOLDER`/`COMPETITOR`/`DECISION`/`NEXT_STEP` dentro
  de uma oportunidade, com `source`/`evidence`/`confidence`/
  `timestamp` obrigatórios por aresta (`evidence` nunca vazia).
- 37 testes novos (22 + 15). Suite completa: 571 testes, 0 falhas, 1
  skip pré-existente — sem regressão. Detalhe completo no CHANGELOG.md
  (V.1.4.75).
- **Push + deploy confirmados (10/09/2026)**: commit `451beae` no
  GitHub. Na VPS, `reunioes_ativas: 0` (sem reunião ativa desta vez) —
  `git pull`/`pip install` limpos, `ALTER TABLE meeting_memory ADD
  COLUMN opportunity_id INTEGER` + índice aplicados via script
  idempotente (checou a coluna antes de alterar), `systemctl restart
  saleia` executado na sequência. Pós-restart: `/health` = `versao
  1.4.75`, `status online`, 4 provedores de IA `ok`; `/dashboard` e
  `/health` públicos responderam `200`.
- Fase 3 (SPIN 2.0) do roadmap não começa sem nova confirmação
  explícita do usuário.

## SPIN Coverage Engine — Fase 3 / Tarefa 3.1 do "SALE-IA V2" (V.1.4.76, 10/09/2026)

Usuário confirmou avançar para a Fase 3. Só a Tarefa 3.1 (motor de
cobertura) foi feita — Tarefa 3.2 (Question Gap Engine, prioridades
critical/high/medium/low) não começou.

- `agent/spin_coverage_rules.py` (novo, função pura, sem IA/banco):
  `calcular_cobertura_spin()` computa `known[]`/`missing[]` por
  estágio SPIN (`situation`/`problem`/`implication`/`need_payoff`) a
  partir de fatos já estruturados e evidenciados — recusa
  (`ValueError`) qualquer fato sem `evidence_quote` (regra do prompt
  mestre: "não permitir que a IA invente informação faltante").
- `estagio_atual()` + `sugerir_proxima_pergunta()` — reproduz
  exatamente o exemplo literal do prompt mestre (pergunta sugerida
  para `financial_impact` = `"Quanto esse problema custa
  atualmente?"`).
- **Decisão deliberada**: extração automática de fatos a partir de
  transcrição livre via IA não foi construída (fora do enunciado da
  Tarefa 3.1); sem integração com `orquestrador.py` ainda.
- 13 testes novos. Suite completa: 584 testes, 0 falhas, 1 skip
  pré-existente — sem regressão. Detalhe completo no CHANGELOG.md
  (V.1.4.76).
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova). Tarefa
  3.2 e qualquer fase seguinte não começam sem nova confirmação
  explícita do usuário.

## Question Gap Engine — Fase 3 / Tarefa 3.2 do "SALE-IA V2" (V.1.4.77, 11/09/2026)

Usuário confirmou avançar para a Tarefa 3.2. Constrói sobre o
`SPINState` da Tarefa 3.1 — Fase 4 (MEDDPICC) não começou.

- `agent/question_gap_rules.py` (novo, função pura, sem IA/banco):
  `calcular_gaps_priorizados(cobertura, prioridade_por_stage=None)`
  recebe a cobertura da Tarefa 3.1 e devolve os gaps (`missing`) com
  `{"stage", "campo", "priority", "pergunta"}`, ordenados por
  prioridade (`critical` > `high` > `medium` > `low`).
  `proximo_gap()` retorna o primeiro (ou `None`).
- Pergunta sempre reaproveitada de `SPIN_PERGUNTAS_PADRAO` (Tarefa
  3.1) — reproduz o exemplo literal do prompt mestre (`financial_
  impact` → `"Quanto esse problema custa atualmente?"`).
- **Decisão desta rodada** (prompt mestre não define a regra de
  atribuição, só o vocabulário de prioridades): `STAGE_PRIORIDADE_
  PADRAO` marca `implication=critical`, `need_payoff=high`,
  `problem=medium`, `situation=low` — sobrescrevível por chamada.
- 10 testes novos. Suite completa: 594 testes (584 + 10), 0 falhas, 1
  skip pré-existente — sem regressão. Detalhe completo no CHANGELOG.md
  (V.1.4.77).
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova). Fase 4
  (MEDDPICC) e qualquer tarefa seguinte não começam sem nova
  confirmação explícita do usuário.

## Opportunity Qualification Engine — Fase 4 / Tarefa 4.1 do "SALE-IA V2" (V.1.4.78, 11/09/2026)

Usuário confirmou avançar para a Fase 4 (MEDDPICC). Só a Tarefa 4.1
(motor de qualificação) foi feita — Tarefa 4.2 (Deal Risk) não começou.

- `agent/meddpicc_rules.py` (novo, função pura, sem IA/banco):
  `calcular_qualificacao_meddpicc()` computa o estado dos 8 itens
  MEDDPICC (`metrics`/`economic_buyer`/`decision_criteria`/`decision_
  process`/`paper_process`/`identify_pain`/`champion`/`competition`) —
  cada um `{status, confidence, evidence[]}` — a partir de fatos já
  estruturados e evidenciados. Recusa (`ValueError`) item saindo de
  `UNKNOWN` sem `evidence_quote` (regra estendida por decisão desta
  rodada, mesma disciplina de SalesEvent/SPIN).
- `resumo_qualificacao()` — nível geral (`fraca`/`intermediaria`/
  `avancada`) por contagem de itens `CONFIRMED` (limiares `>=6`/`>=3`,
  decisão desta rodada). `itens_pendentes()` — itens ainda não
  `CONFIRMED`.
- 14 testes novos, incluindo os 3 cenários pedidos pelo prompt mestre
  (mal qualificada/intermediária/enterprise avançada) com resultado
  esperado definido antes da execução. Suite completa: 608 testes
  (594 + 14), 0 falhas, 1 skip pré-existente — sem regressão. Detalhe
  completo no CHANGELOG.md (V.1.4.78).
- **Decisão deliberada**: sem integração com `orquestrador.py`, sem
  tabela nova, sem endpoint HTTP — mesma disciplina das Fases 1-3.
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova). Tarefa
  4.2 (Deal Risk) e qualquer fase seguinte não começam sem nova
  confirmação explícita do usuário.

## Deal Risk Engine — Fase 4 / Tarefa 4.2 do "SALE-IA V2" (V.1.4.79, 11/09/2026)

Usuário confirmou avançar para a Tarefa 4.2 — fecha a Fase 4 (MEDDPICC)
completa. Constrói sobre o estado MEDDPICC da Tarefa 4.1.

- `agent/deal_risk_rules.py` (novo, função pura, sem IA/banco — "não
  usar LLM para calcular regras simples"): `calcular_riscos()` devolve
  os riscos detectados (subconjunto de `DEAL_RISK_TIPOS`, os 7 exemplos
  literais do prompt mestre: `NO_ECONOMIC_BUYER`, `NO_CHAMPION`,
  `NO_NEXT_STEP`, `NO_METRICS`, `HIGH_PRICE_RESISTANCE`,
  `COMPETITOR_ADVANTAGE`, `STALE_OPPORTUNITY`).
- `NO_ECONOMIC_BUYER`/`NO_CHAMPION`/`NO_METRICS` derivam do estado
  MEDDPICC (Tarefa 4.1); os outros 4 recebem sinal explícito do
  chamador (de onde vem cada sinal em produção real é integração
  futura). `COMPETITOR_ADVANTAGE` é sinal explícito, não deriva do item
  `competition` do MEDDPICC (aquele só indica se o cenário competitivo
  foi mapeado, não quem está na frente).
- Limiares (`LIMIAR_OBJECOES_PRECO_PADRAO=3`, `LIMIAR_DIAS_STALE_
  PADRAO=21`) — decisão desta rodada, sobrescrevíveis por chamada.
- 13 testes novos, incluindo o exemplo literal do prompt mestre (dor
  forte + sem decisor + sem próxima reunião → pelo menos
  `NO_ECONOMIC_BUYER`/`NO_NEXT_STEP`). Suite completa: 621 testes
  (608 + 13), 0 falhas, 1 skip pré-existente — sem regressão. Detalhe
  completo no CHANGELOG.md (V.1.4.79).
- **Decisão deliberada**: sem integração com `orquestrador.py`, sem
  tabela nova, sem endpoint HTTP — mesma disciplina das Fases 1-4.
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova). Fase 5
  (Motivação e Comportamento) e qualquer tarefa seguinte não começam
  sem nova confirmação explícita do usuário.

## Buyer Motivation Engine — Fase 5 / Tarefa 5.1 do "SALE-IA V2" (V.1.4.80, 11/09/2026)

Usuário confirmou avançar para a Fase 5. Só a Tarefa 5.1 (motor de
motivação) foi feita — Tarefa 5.2 (Behavioral Signal Engine) não
começou.

- `agent/buyer_motivation_rules.py` (novo, função pura, sem IA/banco):
  `MOTIVATION_TIPOS` (12 motivadores literais do prompt mestre),
  `validar_hipoteses_motivacao()` (cada hipótese `{motivation,
  confidence, evidence[]}`, evidência obrigatória) e
  `motivacao_dominante()` (hipótese de maior confidence, ou `None`).
- **DISC nunca é motivação — garantido por construção**: módulo não
  importa/lê nada relacionado a DISC, confirmado por teste de guarda
  arquitetural (grep). Teste do prompt mestre reproduzido: DISC externo
  constante em 3 turnos, motivação mudando turno a turno.
- 14 testes novos. Suite completa: 635 testes (621 + 14), 0 falhas, 1
  skip pré-existente — sem regressão. Detalhe completo no CHANGELOG.md
  (V.1.4.80).
- **Decisão deliberada**: sem integração com `orquestrador.py`, sem
  tabela nova, sem endpoint HTTP — mesma disciplina das Fases 1-4.
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova). Tarefa
  5.2 (Behavioral Signal Engine) e qualquer fase seguinte não começam
  sem nova confirmação explícita do usuário.

## Behavioral Signal Engine — Fase 5 / Tarefa 5.2 do "SALE-IA V2" (V.1.4.81, 11/09/2026)

Usuário confirmou avançar para a Tarefa 5.2 — fecha a Fase 5 completa.

- `agent/behavioral_signal_rules.py` (novo, função pura, sem IA/banco):
  `BEHAVIORAL_SIGNAL_TIPOS` (6 sinais literais do prompt mestre:
  LOSS_AVERSION/STATUS_QUO_BIAS/SOCIAL_PROOF_REQUEST/AUTHORITY_REQUEST/
  PRICE_ANCHOR/RISK_AVERSION). `validar_sinais_comportamentais()` exige
  `evidence_quote` por sinal. `detectar_sinais()` enriquece cada sinal
  com descrição canônica sóbria (nunca texto livre — evita alegação
  pseudocientífica tipo "cérebro reptiliano"). `contagem_por_sinal()`.
- 15 testes novos, incluindo guarda contra linguagem pseudocientífica
  nas descrições. Suite completa: 650 testes (635 + 15), 0 falhas, 1
  skip pré-existente — sem regressão. Detalhe completo no CHANGELOG.md
  (V.1.4.81).
- **Decisão deliberada**: sem integração com `orquestrador.py`, sem
  tabela nova, sem endpoint HTTP — mesma disciplina das Fases 1-5.
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova). Fase 6
  (Objection Intelligence) e qualquer tarefa seguinte não começam sem
  nova confirmação explícita do usuário.

## Taxonomia de Objeções — Fase 6 / Tarefa 6.1 do "SALE-IA V2" (V.1.4.82, 11/09/2026)

Usuário confirmou avançar para a Fase 6. Só a Tarefa 6.1 (taxonomia +
separação spoken/root cause) foi feita — Tarefa 6.2 (Negotiation
Engine) não começou.

- `agent/objection_rules.py` (novo, função pura, sem IA/banco):
  `OBJECTION_TIPOS` (13 categorias literais do prompt mestre) para
  `objection_spoken`; `root_cause_hypothesis` usa vocabulário livre
  (ex.: `ADOPTION_RISK`), sempre com `confidence`/`evidence_quote`
  próprios — os dois campos nunca são fundidos.
- `precisa_investigar()` — regra central: "'Está caro.' não pode virar
  root_cause=PRICE @ 100% automaticamente" imposta estruturalmente
  (sem hipótese, confidence baixa, ou hipótese que só espelha a
  categoria+evidência do spoken → sempre recomenda investigação).
  `registrar_objecao()` monta o registro completo.
- 16 testes novos, incluindo os 2 exemplos literais do prompt mestre
  (proibido e o "bom", spoken=PRICE/root=ADOPTION_RISK). Suite completa:
  666 testes (650 + 16), 0 falhas, 1 skip pré-existente — sem
  regressão. Detalhe completo no CHANGELOG.md (V.1.4.82).
- **Decisão deliberada**: sem integração com `orquestrador.py`, sem
  tabela nova, sem endpoint HTTP — mesma disciplina das Fases 1-5.
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova). Tarefa
  6.2 (Negotiation Engine) e qualquer fase seguinte não começam sem
  nova confirmação explícita do usuário.

## Negotiation Engine — Fase 6 / Tarefa 6.2 do "SALE-IA V2" (V.1.4.83, 11/09/2026)

Usuário confirmou avançar para a Tarefa 6.2 — fecha a Fase 6 completa.
Constrói sobre `objection_rules.precisa_investigar()` da Tarefa 6.1.

- `agent/negotiation_rules.py` (novo, função pura, sem IA/banco):
  `NEGOTIATION_TIPOS` (7 estratégias consultivas literais do prompt
  mestre: LABEL/MIRROR/CALIBRATED_QUESTION/SUMMARIZE/CLARIFY/
  VALUE_REFRAME/RISK_REDUCTION), divididas em investigativas (4) e
  pós-investigação (3). `recomendar_estrategia()` reaproveita
  `precisa_investigar()` — enquanto a objeção não foi investigada, só
  estratégias investigativas são permitidas.
- "Nunca permitir ameaça/mentira/escassez falsa/manipulação/informação
  inventada" garantido por construção: vocabulário fechado, sem campo
  de texto livre. Teste literal do prompt mestre reproduzido: "Está
  caro." → nunca "posso dar 20% agora" → sempre estratégia de
  investigação.
- 13 testes novos, incluindo guarda contra táticas manipulativas nas
  descrições. Suite completa: 679 testes (666 + 13), 0 falhas, 1 skip
  pré-existente — sem regressão. Detalhe completo no CHANGELOG.md
  (V.1.4.83).
- **Decisão deliberada**: sem integração com `orquestrador.py`, sem
  tabela nova, sem endpoint HTTP — mesma disciplina das Fases 1-6.
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova). Fase 7
  (Sales Reasoning Engine) e qualquer tarefa seguinte não começam sem
  nova confirmação explícita do usuário.

## SalesReasoningEngine — Fase 7 / Tarefa 7.1 do "SALE-IA V2" (V.1.4.85, 13/09/2026, motor real + Golden Dataset)

Sequência de V.1.4.84 (contrato). Usuário confirmou explicitamente
avançar para o motor real — a parte que ficou pendente por decisão
deliberada de escopo na rodada anterior.

- `agent/sales_reasoning_engine.py` — contrato (V.1.4.84, inalterado) +
  **`raciocinar_async()`** (novo): sintetiza os 11 inputs numa
  recomendação via IA, usando o mesmo caminho de produção dos 5 agentes
  de `agent/multiagente/` (`chamar_ia_com_fallback_claude`). Resposta
  da IA validada contra o contrato de saída já existente
  (`montar_saida_raciocinio()`); entrada parcial nunca levanta, chave
  desconhecida sempre levanta (mesmo contrato da V.1.4.84).
  `SALES_REASONING_FRAMEWORKS` (novo) — vocabulário fechado de 9
  valores para `recommended_framework` (4 estágios SPIN +
  `MEDDPICC_QUALIFICATION`/`OBJECTION_INVESTIGATION`/`NEGOTIATION`/
  `RISK_MITIGATION`/`CLOSING`).
- `agent/prompt_templates/sales_reasoning_engine.txt` (novo) — regra
  central herdada da Fase 6.1: objeção com `precisa_investigar=true`
  bloqueia `NEGOTIATION`/`CLOSING` até `OBJECTION_INVESTIGATION`
  acontecer primeiro.
- `api/ai_features.py::SALES_REASONING_RACIOCINIO` (nova feature de
  custo).
- **Não integrado a `orquestrador.py`/`processador_tempo_real.py`
  ainda** — decisão de produto separada (mudaria custo/latência do
  ciclo de tempo real), não tomada nesta rodada.
- 7 testes novos (`RaciocinarAsyncTest`, mock de
  `chamar_ia_com_fallback_claude`). Suite completa: **700 testes, 0
  falhas, 1 skip pré-existente** — sem regressão.
- **Golden Dataset — 57 cenários** (mínimo pedido: 50) em
  `evals/datasets/sales_reasoning/` + `evals/providers/
  sales_reasoning_provider.py` + `evals/promptfooconfig.
  sales_reasoning.yaml` — mesmo harness Promptfoo do Coach/Finance
  (Fase 2), validação sempre via `llm-rubric` (semântica, nunca
  igualdade literal — regra explícita do prompt mestre). Inclui o
  exemplo PROIBIDO literal ("Está caro." → "Posso dar 20% agora.").
  **Nunca executado** — custa dinheiro real por cenário, mesma
  disciplina do resto da suíte (decisão de rodar é separada da decisão
  de construir).
- Detalhe completo no CHANGELOG.md (V.1.4.85).
- **Push + deploy confirmados (14/09/2026)**: commit `96bd3ea` no
  GitHub. Na VPS, `reunioes_ativas: 0` checado antes de cada etapa —
  `git pull` (fast-forward `451beae` → `96bd3ea`, aditivo, sem
  tabela/coluna nova) + `pip install`/`pip check` limpos, `systemctl
  restart saleia` — `active`, journal sem erros. Pós-restart: `/health`
  = `versao 1.4.85`, `status online`, `reunioes_ativas 0`, 4 provedores
  de IA `ok` (restart zerou os circuit breakers em memória — não
  confirma saldo/chave de verdade, mesma ressalva de sempre).
- **Pendente**: rodar o Golden Dataset de verdade. **Integrar ao
  orquestrador não começa sem nova confirmação explícita do usuário.**

## Outcome Tracking — Fase 8 / Tarefa 8.1 do "SALE-IA V2" (V.1.4.86, 14/09/2026)

Usuário confirmou avançar para a Fase 8 (Resultado da Venda). Só a
Tarefa 8.1 (Outcome Tracking) foi feita — Tarefa 8.2 (Win/Loss
Intelligence) não começou.

- `agent/opportunity_memory_rules.py::OPPORTUNITY_STATUSES` ganha
  `"abandoned"` (4º estado, junto de `open`/`won`/`lost` da Fase 2).
- `agent/outcome_rules.py` (novo, função pura, sem IA/banco):
  `calcular_cycle_days()` (sempre derivado das datas reais, nunca
  aceito como input), `validar_dados_won({value, product, close_date})`,
  `validar_dados_lost({reason, competitor})` (`competitor` opcional),
  `esta_fechada(status)`, `resumo_por_status(opportunities)` — atende
  a regra de teste literal da Tarefa 8.1: "uma oportunidade encerrada
  precisa deixar de entrar como aberta em estatísticas".
- `api/database.py::Opportunity` ganha 5 colunas aditivas
  (`outcome_value`/`product`/`close_date`/`cycle_days` para WON,
  `competitor` para LOST) — `reason`/`stage`/`lost_at` do schema do
  prompt mestre reaproveitam `loss_reason`/`stage`/`lost_at` já
  existentes, nunca duplicados.
- `atualizar_status_opportunity()`: transição para `"won"` agora exige
  `value`/`product`/`close_date`; `"lost"` exige `loss_reason`
  (`competitor` opcional); `"abandoned"` não exige dado extra.
- **Achado**: 2 testes pré-existentes da Fase 2 chamavam a transição
  para `"won"` sem esses dados — corrigidos para passar
  `value`/`product`/`close_date`, sem mudar o que cada teste verifica.
- 25 testes novos (19 + 6). Suite completa: 725 testes, 0 falhas, 1
  skip pré-existente — sem regressão. Detalhe completo no
  CHANGELOG.md (V.1.4.86).
- **Decisão deliberada**: sem endpoint HTTP novo, sem integração com
  `orquestrador.py`/`processador_tempo_real.py` — mesma disciplina das
  Fases 1-7.
- **Push + deploy confirmados (14/09/2026)**: commit `12aa93a` no
  GitHub. Na VPS, `reunioes_ativas: 0` checado antes de cada etapa —
  `git pull` fast-forward `96bd3ea` → `12aa93a` + `pip install`/`pip
  check` limpos. `ALTER TABLE opportunities ADD COLUMN` aplicado via
  script idempotente (checou `INFORMATION_SCHEMA.COLUMNS` antes — as 5
  colunas não existiam, todas adicionadas nullable). `systemctl
  restart saleia` — `active`, journal sem erros. Pós-restart: `/health`
  = `versao 1.4.86`, `status online`, `reunioes_ativas 0`.
- **Pendente**: nada — Tarefa 8.2 (abaixo) fecha a Fase 8.

## Win/Loss Intelligence — Fase 8 / Tarefa 8.2 do "SALE-IA V2" (V.1.4.87, 14/09/2026)

Usuário confirmou avançar para a Tarefa 8.2, fechando a Fase 8
completa.

- `agent/win_loss_rules.py` (novo, função pura, zero IA/banco e **zero
  numpy/scipy** — estatística em Python puro): `WIN_LOSS_VARIAVEIS`
  documenta as 15 variáveis do prompt mestre (funções genéricas sobre
  qualquer campo do dict, não travadas a esses nomes).
- Regra científica "nunca causa, sempre associação" garantida por
  construção: só 3 templates fixos geram texto
  (`TEMPLATE_AFIRMACAO_ASSOCIACAO`/`TEMPLATE_AMOSTRA_INSUFICIENTE`/
  `TEMPLATE_SIMPSONS_PARADOX`), guardados por
  `GuardaContraCausalidadeTest`.
- `comparar_por_variavel_categorica()` — taxa de conversão + IC de
  Wilson + afirmação por grupo categórico; `sem_dado` nunca vira grupo
  "None".
- `amostra_suficiente(n, minimo=30)`, `intervalo_confianca_wilson()`
  (Wilson score, sem scipy), `calcular_limites_iqr`/
  `detectar_outliers_iqr`/`resumir_variavel_numerica` (método IQR pra
  ticket/cycle/talk_ratio).
- `detectar_simpsons_paradox()` — testado com o dataset sintético
  clássico (2 estratégias × porte do negócio: A vence em cada segmento
  mas B vence agregado) — atende literalmente "Simpson's paradox em
  dataset sintético" da Tarefa 8.2.
- **Decisão deliberada**: sem integração com `Opportunity`/
  `orquestrador.py`, sem endpoint HTTP — motor estatístico genérico,
  não a extração de cada uma das 15 variáveis reais.
- 24 testes novos. Suite completa: 749 testes, 0 falhas, 1 skip
  pré-existente — sem regressão. Detalhe completo no CHANGELOG.md
  (V.1.4.87).
- **Push + deploy confirmados (14/09/2026)** junto com V.1.4.88/89/90
  — ver detalhe no fim da seção V.1.4.90 abaixo.

## Data Warehouse comercial mínimo — Fase 9 / Tarefa 9.1 do "SALE-IA V2" (V.1.4.88, 14/09/2026)

Usuário confirmou avançar para a Fase 9 (Seasonality Engine). Só a
Tarefa 9.1 (Data Warehouse comercial mínimo) foi feita — Tarefas 9.2
(Sazonalidade temporal) e 9.3 (Sazonalidade contextual) não começaram.

- `agent/data_warehouse_rules.py` (novo, função pura, sem IA/banco):
  `DIMENSOES_DATASET` documenta as 16 dimensões literais do prompt
  mestre (calendário + negócio).
- `derivar_dimensoes_calendario(data)` — as 6 dimensões de calendário
  sempre calculadas a partir de uma data real, nunca aceitas como
  input.
- `construir_linha_analitica(opportunity, campo_data="close_date",
  **dimensoes_extra)` — 1 linha do dataset a partir do formato de
  `listar_opportunities()`; cai pra `created_at` sem `close_date`;
  `ticket` usa `outcome_value` (Fase 8) senão `estimated_value`;
  `won`/`lost` viram flags booleanos. Dimensões não rastreadas ainda
  (`team`/`lead_source`/`objection_type`/`sales_strategy`) via
  `**dimensoes_extra`.
- `construir_dataset_analitico(opportunities, **kwargs)` — oportunidade
  sem data válida é pulada, nunca derruba o dataset inteiro.
- `pode_executar_analise_pesada(reunioes_ativas)` — implementa "nunca
  analisar pesado em horário de reunião" reaproveitando o mesmo sinal
  `reunioes_ativas` que já governa todo deploy seguro do projeto.
- **Decisão deliberada**: sem endpoint HTTP, sem integração com
  `orquestrador.py`/scheduler.
- 19 testes novos. Suite completa: 768 testes, 0 falhas, 1 skip
  pré-existente — sem regressão. Detalhe completo no CHANGELOG.md
  (V.1.4.88).
- **Push + deploy confirmados (14/09/2026)** junto com V.1.4.87/89/90
  — ver detalhe no fim da seção V.1.4.90 abaixo.

## Sazonalidade Temporal — Fase 9 / Tarefa 9.2 do "SALE-IA V2" (V.1.4.89, 14/09/2026)

Usuário confirmou avançar para a Tarefa 9.2. Constrói sobre o dataset
analítico da Tarefa 9.1 e reaproveita as primitivas estatísticas de
`win_loss_rules.py` (Fase 8). Tarefa 9.3 (Sazonalidade contextual) não
começou.

- `agent/seasonality_rules.py` (novo, função pura, zero IA/banco/numpy/
  scipy): `DIMENSOES_TEMPORAIS` (month/quarter/week/weekday/hour —
  `date` fica de fora de propósito, granularidade única por linha).
- Critério de significância (sem scipy): amostra suficiente + baseline
  geral fora do intervalo de confiança de Wilson do período.
- `taxa_conversao_por_periodo()`/`detectar_sazonalidade()` — agrupam
  linhas do dataset analítico pela dimensão temporal.
- Regra "nunca causa, sempre associação" herdada da Fase 8, guardada
  por `GuardaContraCausalidadeTest`.
- Testado com o exemplo literal do prompt mestre (março-maio +18pp) e
  com 2 datasets sem sinal real (taxa idêntica por construção; e
  aleatório com seed fixa, tolerando no máximo 1 falso-positivo em 12
  meses — taxa esperada de um IC de 95%, documentada no teste).
- **Decisão deliberada**: sem integração com `orquestrador.py`, sem
  endpoint HTTP. Segmento/produto/origem é a Tarefa 9.3.
- 12 testes novos. Suite completa: 780 testes, 0 falhas, 1 skip
  pré-existente — sem regressão. Detalhe completo no CHANGELOG.md
  (V.1.4.89).
- **Push + deploy confirmados (14/09/2026)** junto com V.1.4.87/88/90
  — ver detalhe no fim da seção V.1.4.90 abaixo.

## Sazonalidade Contextual — Fase 9 / Tarefa 9.3 do "SALE-IA V2" (V.1.4.90, 14/09/2026, fecha a Fase 9)

Usuário confirmou avançar para a Tarefa 9.3, fechando a Fase 9
completa.

- `agent/contextual_seasonality_rules.py` (novo, função pura, zero
  IA/banco/numpy/scipy): `DIMENSOES_CONTEXTO` (7 campos literais:
  segment/product/origin/ticket/client_type/objection_type/
  opportunity_stage — reaproveita nomes da Tarefa 9.1 onde já existem).
- `detectar_sazonalidade_contextual()` — combina período temporal
  (Tarefa 9.2) + dimensão de contexto, compara contra o mesmo baseline
  geral da Tarefa 9.2. Cada descoberta usa exatamente os 6 campos
  literais do prompt mestre (`sample_size`/`baseline`/`observed`/
  `difference`/`confidence`/`period`), lista ordenada por magnitude.
- **Decisão deliberada**: o exemplo do prompt mestre mistura
  divergência de taxa (implementada) com "categoria dominante por
  frequência" (mode-finder, fora do Critério de 6 campos — não
  construído nesta rodada).
- Regra "nunca causa, sempre associação" herdada da Fase 8.
- 12 testes novos, incluindo o exemplo adaptado (Q4 × SaaS) e 2
  datasets sem sinal real. Suite completa: 792 testes, 0 falhas, 1
  skip pré-existente — sem regressão. Detalhe completo no
  CHANGELOG.md (V.1.4.90).
- **Decisão deliberada**: sem integração com `orquestrador.py`, sem
  endpoint HTTP.
- **Push + deploy confirmados (14/09/2026)**: commit `8c8490e` no
  GitHub (4 commits, V.1.4.87→90, empurrados juntos). Na VPS,
  `reunioes_ativas: 1` bloqueou o restart por um tempo curto — `git
  pull`/`pip install`/`pip check` feitos antes com segurança (só
  arquivos em disco, aditivo, sem tabela/coluna nova nas 4 versões);
  `systemctl restart saleia` executado assim que `reunioes_ativas`
  voltou a `0`. Pós-restart: `/health` = `versao 1.4.90`, `status
  online`, journal sem erros.

## RecommendationEvent — Fase 10 / Tarefa 10.1 do "SALE-IA V2" (V.1.4.91, 14/09/2026)

Usuário confirmou avançar para a Fase 10 (Strategy Effectiveness). Só
a Tarefa 10.1 (criar o `RecommendationEvent`) foi feita — Tarefas 10.2
(detectar uso) e 10.3 (efetividade) não começaram.

- `api/database.py::RecommendationEvent` (tabela
  `recommendation_events`, aditiva): schema literal do prompt mestre —
  `meeting_id`, `opportunity_id` (sem FK), `strategy`, `recommendation`,
  `reason`, `shown_at`, `used_at`, `seller_action`, `outcome_window`.
- `agent/recommendation_rules.py` (novo, função pura, sem IA/banco):
  `validar_recommendation_event()` exige `meeting_id`/`strategy`/
  `recommendation`/`reason` não vazios.
- RecommendationEvent é dado de domínio — `criar_recommendation_event()`
  propaga `ValueError` em dado inválido, mesma disciplina de
  `SalesEvent`/`SalesEvidence` (Fase 1).
- `registrar_uso_recommendation_event(id, seller_action, used_at=None)`
  — persistência mecânica, não decide USED/PARTIALLY_USED/IGNORED
  (Tarefa 10.2); nunca sobrescreve `used_at` já gravado.
- **Decisão deliberada**: sem vocabulário fechado para `strategy`, sem
  endpoint HTTP.
- 12 testes novos. Suite completa: 804 testes, 0 falhas, 1 skip
  pré-existente — sem regressão. Detalhe completo no CHANGELOG.md
  (V.1.4.91).
- **Pendente**: push + deploy na VPS (aditivo — 1 tabela nova via
  `create_all()`; segue junto do V.1.4.92 abaixo).

## Detectar Uso da Recomendação — Fase 10 / Tarefa 10.2 do "SALE-IA V2" (V.1.4.92, 14/09/2026)

Usuário confirmou avançar para a Tarefa 10.2 e escolheu embeddings
(não IA nem só contrato) para a detecção — regra central "não exigir
correspondência literal".

- `agent/recommendation_usage_rules.py` (novo): `RECOMMENDATION_USAGE_STATES`
  (USED/PARTIALLY_USED/IGNORED/UNKNOWN), `cosine_similarity()`,
  `classificar_uso_por_similaridade()` (função pura, limiares 0.55/0.35
  — decisão desta rodada), `detectar_uso_recomendacao()` (motor real,
  `async`, usa `services.embeddings.get_embedding_provider()`, mesmo
  provedor do RAG).
- Estado nunca é coluna nova em `RecommendationEvent` — sempre derivado
  de `recommendation`/`seller_action` já persistidos.
- Sem wrapper async em `api/database.py` (inteiramente síncrono hoje) —
  compor busca + classificação fica a cargo do chamador.
- Testado com o exemplo literal do prompt mestre (embeddings mockados
  simulando vetores próximos) — classificado como `USED`. Falha de
  embedding vira `UNKNOWN`, nunca `IGNORED`.
- 15 testes novos. Suite completa: 819 testes, 0 falhas, 1 skip
  pré-existente — sem regressão. Detalhe completo no CHANGELOG.md
  (V.1.4.92).
- **Decisão deliberada**: sem integração com `orquestrador.py`, sem
  endpoint HTTP.
- **Push + deploy confirmados (15/09/2026)**: commit `6d5c9ce` no
  GitHub (junto com V.1.4.91, `672644a`). Na VPS, `reunioes_ativas: 0`
  checado antes de cada etapa — `git pull` (fast-forward `06e4fc3` →
  `6d5c9ce`) + `pip install`/`pip check` limpos. `systemctl restart
  saleia` — `active`, journal sem erros. Pós-restart: `/health` =
  `versao 1.4.92`, `status online`, `reunioes_ativas 0`, 4 provedores
  `ok`; `/dashboard` = `200`.

## Recommendation Effectiveness — Fase 10 / Tarefa 10.3 do "SALE-IA V2" (V.1.4.93, fecha a Fase 10, 15/09/2026)

Usuário confirmou avançar para a Tarefa 10.3. **Achado**: o módulo e os
testes já existiam no working tree local, não commitados, de uma
sessão anterior — revisados por completo (imports conferidos contra
`recommendation_usage_rules.py`/`win_loss_rules.py`, suite completa
rodada do zero) antes de aceitar o código; nenhuma linha nova escrita
além do bump de versão e da documentação.

- `agent/recommendation_effectiveness_rules.py` (novo):
  `calcular_efetividade_por_estrategia(eventos, minimo_amostra=
  AMOSTRA_MINIMA_PADRAO)` agrupa eventos por `strategy` e mede
  efetividade a partir de sinais já classificados (`state` da Tarefa
  10.2, `stage_advanced`, `opportunity_result`) — não extrai nada de
  transcrição real.
- **Regra central — nunca confundir "avanço imediato" com "causa da
  venda"**: `taxa_avanco` e `taxa_desfecho_positivo` são sempre
  calculadas e reportadas separadamente, nunca combinadas numa métrica
  única — mesma disciplina de `win_loss_rules.py`/`seasonality_rules.py`
  (Fases 8-9). Dado ausente (`None`) nunca conta no denominador (nunca
  vira "não avançou"/"não converteu" por omissão).
- `ESTADOS_CONTADOS_COMO_USO = {USED, PARTIALLY_USED}` — decisão desta
  rodada; `amostra_avanco_suficiente`/`amostra_desfecho_suficiente`
  reaproveitam `win_loss_rules.amostra_suficiente` (Fase 8).
- Testado com o exemplo literal do prompt mestre ("SPIN Implication —
  187 usos — 61% avanço", "Case Similar — 153 usos — 66% avanço").
- 10 testes novos. Suite completa: 829 testes, 0 falhas, 1 skip
  pré-existente — sem regressão. Detalhe completo no CHANGELOG.md
  (V.1.4.93).
- **Decisão deliberada**: sem integração com `orquestrador.py`, sem
  endpoint HTTP, sem persistência nova.
- **Fecha a Fase 10 (Strategy Effectiveness)** completa: Tarefa 10.1
  (RecommendationEvent) → 10.2 (Detectar Uso) → 10.3 (Effectiveness).
- **Push + deploy confirmados (15/09/2026)**: commit `36c7585` no
  GitHub. Na VPS, `reunioes_ativas: 0` checado antes/depois — `git
  pull` (fast-forward `6d5c9ce` → `36c7585`) + `systemctl restart
  saleia` — `active`, journal sem erros. Pós-restart: `/health` =
  `versao 1.4.93`, `status online`, `reunioes_ativas 0`.

## Conversation Metrics — Fase 11 / Tarefa 11.1 do "SALE-IA V2" (V.1.4.94, início da Fase 11, 15/09/2026)

Usuário confirmou avançar para a Fase 11 (Seller Coaching) — nova fase
do roadmap, confirmação explícita pedida separadamente da confirmação
de tarefa dentro de uma fase já em andamento (mesma disciplina desde
a Fase 0).

- `agent/conversation_metrics_rules.py` (novo):
  `calcular_metricas_conversa(turns, objections=None, next_step_
  proposto=None, ...)` calcula as 11 métricas literais da Tarefa 11.1
  a partir de uma transcrição temporizada estruturada (`speaker`/
  `start`/`end`/`text` por turno).
- **Separação estrutural × classificação de negócio**: talk ratio/
  interrupções/monólogos e contagem de perguntas (aberta/fechada) são
  calculados de sinais estruturais do próprio turno (timing + `"?"`);
  `price_timing`/`presentation_timing`/`objection_exploration_rate`/
  `next_step_rate` sempre recebem o sinal já classificado do chamador
  (flags por turno / lista de objeções / booleano) — nunca inferidos
  por keyword matching de negócio dentro do módulo, mesmo princípio de
  `deal_risk_rules.py` (Fase 4.2).
- Falante não identificado nunca conta nos ratios/interrupções; dado
  ausente nunca vira 0/False por omissão (mesma disciplina de
  `recommendation_effectiveness_rules.py`, Fase 10). Perguntas
  contadas só do vendedor. Turnos consecutivos do mesmo falante são
  mesclados antes de checar o limiar de monólogo. Função ordena os
  turnos internamente por `start`.
- Testado com uma transcrição temporizada conhecida (11 turnos, 302s)
  com valores calculados à mão — literal da instrução da Tarefa 11.1.
- 22 testes novos. Suite completa: 851 testes, 0 falhas, 1 skip
  pré-existente — sem regressão. Detalhe completo no CHANGELOG.md
  (V.1.4.94).
- **Decisão deliberada**: sem integração com `orquestrador.py`, sem
  endpoint HTTP, sem persistência nova.
- **Push + deploy confirmados (15/09/2026)**: commit `33dd12a` no
  GitHub. Na VPS, `reunioes_ativas: 0` checado antes/depois — `git
  pull` (fast-forward `36c7585` → `33dd12a`) + `systemctl restart
  saleia` — `active`, journal sem erros. Pós-restart: `/health` =
  `versao 1.4.94`, `status online`, `reunioes_ativas 0`.

## Seller Scorecard — Fase 11 / Tarefa 11.2 do "SALE-IA V2" (V.1.4.95, fecha a Fase 11, 15/09/2026)

Usuário confirmou avançar para a Tarefa 11.2, fechando a Fase 11
(Seller Coaching) completa.

- `agent/seller_scorecard_rules.py` (novo): `SCORECARD_DIMENSOES` — as
  7 dimensões literais do prompt mestre (Discovery, Listening,
  Qualification, Value Building, Negotiation, Closing, Next Step
  Discipline). `calcular_scorecard(evidencias_por_dimensao)` genérica
  sobre evidências já classificadas pelo chamador (de
  `conversation_metrics_rules.py`, `spin_coverage_rules.py`,
  `meddpicc_rules.py`, `objection_rules.py`/`negotiation_rules.py`
  etc.) — nunca decide sozinha o que conta como evidência.
- **Regra literal "Não criar score arbitrário", imposta
  estruturalmente**: cada dimensão é `criterios_atendidos /
  total_criterios` sobre a lista de evidências — nunca peso/fórmula
  inventada, e **nunca combinada com as outras 6 numa nota geral
  única** (nenhuma chave `score_geral` existe na API, guardado por
  `GuardaContraScoreArbitrarioTest`).
- "Cada score precisa apontar evidências": resultado de cada dimensão
  sempre inclui a lista de evidências (`{"criterio", "atendido",
  "quote"}`) que o compõe. Dimensão sem evidência recebida vem como
  `score: None`, nunca `0` por omissão. `dimensoes_sem_evidencia()`
  helper pro Dashboard sinalizar "dado insuficiente".
- Vocabulário de dimensão fechado (chave fora das 7 literais levanta
  `ValueError`); as 7 dimensões sempre aparecem no retorno.
- 15 testes novos. Suite completa: 866 testes, 0 falhas, 1 skip
  pré-existente — sem regressão. Detalhe completo no CHANGELOG.md
  (V.1.4.95).
- **Decisão deliberada**: sem integração com `orquestrador.py`, sem
  endpoint HTTP, sem persistência nova. Mapear cada dimensão para os
  sinais reais das Fases 3/4/6/11 é integração futura não pedida.
- **Fecha a Fase 11 (Seller Coaching)** completa: Tarefa 11.1
  (Conversation Metrics) → 11.2 (Seller Scorecard).
- **Push + deploy confirmados (15/09/2026)**: commit `3ffce0c` no
  GitHub. Na VPS, `reunioes_ativas: 0` checado antes/depois — `git
  pull` (fast-forward `33dd12a` → `3ffce0c`) + `systemctl restart
  saleia` — `active`, journal sem erros. Pós-restart: `/health` =
  `versao 1.4.95`, `status online`, `reunioes_ativas 0`.

## Benchmark dos Melhores Vendedores — Fase 12 / Tarefa 12.1 do "SALE-IA V2" (V.1.4.96, início da Fase 12, 15/09/2026)

Usuário confirmou avançar para a Fase 12 (Collective Sales
Intelligence) — nova fase do roadmap. Só a Tarefa 12.1 executada —
Tarefa 12.2 (Descoberta de padrões) não começou.

- `agent/seller_benchmark_rules.py` (novo): `PERFORMANCE_TIERS =
  ("top", "median", "low")`, `CONTROL_VARIABLES = ("segment",
  "lead_source", "ticket", "product")`. `comparar_tiers(opportunities)`
  reaproveita `win_loss_rules.comparar_por_variavel_categorica()`
  sobre `seller_tier` (taxa bruta por tier).
- **Regra central "não concluir que um vendedor é melhor só porque
  recebe leads melhores", imposta reaproveitando o paradoxo de Simpson
  da Fase 8** (nenhum cálculo novo): `benchmark_controlado(
  opportunities, tier_a="top", tier_b="low", campos_controle=
  CONTROL_VARIABLES)` chama `win_loss_rules.detectar_simpsons_
  paradox()` uma vez por variável de controle — vantagem bruta só é
  confiável quando se mantém dentro de cada estrato; reversão em todos
  os estratos vira sinal de possível confundimento.
- Testado com o dataset sintético clássico já usado na Fase 8
  (análogo ao estudo de cálculo renal), adaptado a `seller_tier`/
  `segment`: `top` parece pior no agregado mas é melhor dentro de
  **cada** segmento — exatamente o cenário que a tarefa pede para
  nunca virar "low é melhor vendedor" sem controlar por segmento.
  Também testado o caso sem confundimento (vantagem real confirmada).
- Quem monta as linhas de entrada: oportunidades no formato de
  `win_loss_rules.py` + `seller_tier` já classificado pelo chamador +
  variáveis de controle já categorizadas (`ticket` pré-bucketizado) —
  módulo nunca decide sozinho quem é top/median/low.
- 9 testes novos. Suite completa: 875 testes, 0 falhas, 1 skip
  pré-existente — sem regressão. Detalhe completo no CHANGELOG.md
  (V.1.4.96).
- **Decisão deliberada**: sem integração com `orquestrador.py`, sem
  endpoint HTTP, sem persistência nova.
- **Push + deploy confirmados (15/09/2026)**: commit `329a47d` no
  GitHub. Na VPS, `reunioes_ativas: 0` checado antes/depois — `git
  pull` (fast-forward `3ffce0c` → `329a47d`) + `systemctl restart
  saleia` — `active`, journal sem erros. Pós-restart: `/health` =
  `versao 1.4.96`, `status online`, `reunioes_ativas 0`.

## Descoberta de Padrões — Fase 12 / Tarefa 12.2 do "SALE-IA V2" (V.1.4.97, fecha a Fase 12, 15/09/2026)

Usuário confirmou avançar para a Tarefa 12.2, fechando a Fase 12
(Collective Sales Intelligence) completa.

- `agent/pattern_discovery_rules.py` (novo): `descobrir_padrao(
  observacoes, hipotese, minimo_amostra=AMOSTRA_MINIMA_PADRAO,
  confianca=0.95)` testa uma hipótese de comportamento (ex.:
  "vendedores de alta conversão exploram implicação antes de
  apresentar solução") comparando a taxa entre `top group` e `control
  group`.
- **Reuso, não reinvenção**: reaproveita `win_loss_rules.comparar_
  por_variavel_categorica()` (Fase 8) direto — "desfecho" vira o
  comportamento (`exhibited`), "categoria" vira o grupo
  (`top`/`control`).
- **Retorno literal do prompt mestre**: `sample`, `top_group`,
  `control_group`, `difference`, `confidence` (+ `diferenca_
  significativa`/`afirmacao`).
- **Significância sem scipy — mesma disciplina honesta de
  `seasonality_rules.py` (Fase 9)**: `diferenca_significativa` só é
  `True` quando os 2 grupos têm amostra suficiente **e** os ICs de
  Wilson não se sobrepõem.
- Regra "nunca causa, sempre associação" herdada das Fases 8-9,
  guardada por `GuardaContraCausalidadeTest`.
- Testado com o exemplo literal do prompt mestre (top 80% vs control
  30%, n=50 cada, ICs não sobrepostos → significativo), caso sem
  sinal real e caso de amostra insuficiente.
- 9 testes novos. Suite completa: 884 testes, 0 falhas, 1 skip
  pré-existente — sem regressão. Detalhe completo no CHANGELOG.md
  (V.1.4.97).
- **Decisão deliberada**: sem integração com `orquestrador.py`, sem
  endpoint HTTP, sem persistência nova.
- **Fecha a Fase 12 (Collective Sales Intelligence)** completa: Tarefa
  12.1 (Benchmark) → 12.2 (Descoberta de Padrões).
- **Push + deploy confirmados (15/09/2026)**: commit `4fb4d93` no
  GitHub. Na VPS, `git pull` foi feito com `reunioes_ativas: 1` (só
  arquivos em disco, seguro) — o restart ficou pendente até a reunião
  real terminar, concluído automaticamente logo em seguida.
  Pós-restart: `/health` = `versao 1.4.97`, `status online`,
  `reunioes_ativas 0`; `/dashboard` = `200`; journal sem erros.

## Sales Science Engine — Fase 13 do "SALE-IA V2" (V.1.4.98, 15/09/2026)

Usuário confirmou avançar para a Fase 13. Pergunta direta sobre
escopo: 2 dos 7 submódulos literais (`ObjectionTrendAnalyzer`,
`ConversionDriverAnalyzer`) não existem ainda — usuário escolheu só o
contrato + wrappers dos 5 que já existem.

- `agent/sales_science_engine.py` (novo): `SALES_SCIENCE_SUBMODULOS`
  (7 literais), `SUBMODULOS_IMPLEMENTADOS` (5)/`SUBMODULOS_PENDENTES`
  (2, explícitos).
- **Regra "saída nunca é só 'descobrimos isso'", imposta
  estruturalmente**: `montar_insight()` exige `insight`+`evidence`+
  `sample`+`possible_confounders`+`recommended_test` sempre
  presentes — `ValueError` se faltar algum. `confidence` é o único
  campo opcional.
- 5 wrappers (`insight_de_win_loss_analyzer`/`_seasonality_engine`/
  `_seller_benchmark`/`_strategy_effectiveness`/`_pattern_discovery`)
  reshapeiam resultados já calculados pelas Fases 8-12 — zero cálculo
  novo. `insight_de_seller_benchmark` é o único que preenche
  `possible_confounders` automaticamente (a variável de controle É o
  confundidor). Cada wrapper retorna `None` (nunca insight forçado)
  quando o submódulo de origem não achou sinal defensável.
- 21 testes novos, chamando os módulos reais das Fases 8-12 (sem
  mock). Suite completa: 905 testes, 0 falhas, 1 skip pré-existente —
  sem regressão. Detalhe completo no CHANGELOG.md (V.1.4.98).
- **Decisão deliberada**: sem integração com `orquestrador.py`, sem
  endpoint HTTP, sem persistência nova.
- **Pendente**: push + deploy na VPS (aditivo — sem tabela/coluna
  nova, módulo puro em memória). **`ObjectionTrendAnalyzer`/
  `ConversionDriverAnalyzer` (fechar a Fase 13) e qualquer fase
  seguinte do "PROMPT MESTRE — SALE-IA V2" não começam sem nova
  confirmação explícita do usuário.**
- **Push + deploy confirmados (16/09/2026)**: commit `d83497e` no
  GitHub. Na VPS, o restart ficou bloqueado por uma reunião real em
  andamento (~100min), concluído automaticamente assim que ela
  terminou. Pós-restart: `/health` = `versao 1.4.98`, `status
  online`, `reunioes_ativas 0`; `/dashboard` = `200`; journal sem
  erros da aplicação (ver "Incidente ao vivo" abaixo para o que foi
  encontrado enquanto se esperava a janela segura).

## Sales Science Engine — Fase 13 (fecho) do "SALE-IA V2" (V.1.4.99, 16/09/2026)

Usuário confirmou "fechar 2 módulos pendentes" — fecha a Fase 13 por
completo, os 7 submódulos literais do prompt mestre implementados.

- `agent/objection_trend_analyzer.py` (novo): `calcular_tendencias(
  eventos, ordem_periodos)` reaproveita `win_loss_rules.amostra_
  suficiente`/`intervalo_confianca_wilson` (Fase 8) pra detectar se a
  participação de uma categoria de objeção cresce/diminui entre a
  primeira e a segunda metade dos períodos — testado com `PRICE`
  crescendo (20%→75%) e `TRUST` caindo (80%→25%) no mesmo dataset.
- `agent/conversion_driver_analyzer.py` (novo): `ranquear_drivers(
  opportunities, campos)` reaproveita `win_loss_rules.calcular_taxa_
  conversao`/`comparar_por_variavel_categorica` (Fase 8) pra ranquear
  `(campo, valor)` pelo maior desvio da taxa de conversão vs. o
  baseline geral — só inclui pares com sinal estatisticamente
  defensável (testado com um campo com sinal real e outro construído
  exatamente no baseline, corretamente excluído do ranking).
- `agent/sales_science_engine.py`: 2 wrappers novos (`insight_de_
  objection_trend_analyzer`/`insight_de_conversion_driver_analyzer`),
  mesmo padrão de reshape puro dos outros 5. `SUBMODULOS_
  IMPLEMENTADOS` agora cobre os 7; `SUBMODULOS_PENDENTES` vira
  `frozenset()`.
- **Achado durante a implementação**: os 2 primeiros templates
  continham a palavra "causa" dentro de uma negação ("não... causa")
  — o guarda de causalidade pegou o falso positivo estrutural, mesma
  lição já registrada em `pattern_discovery_rules.py` (Fase 12.2).
  Corrigido para nunca usar a palavra, nem negada.
- 20 testes novos (9 em `test_objection_trend_analyzer.py`, 8 em
  `test_conversion_driver_analyzer.py`, 3 em
  `test_sales_science_engine.py`). Suite completa: 925 testes, 0
  falhas, 1 skip pré-existente — sem regressão. Detalhe completo no
  CHANGELOG.md (V.1.4.99).
- **Decisão deliberada**: sem integração com `orquestrador.py`, sem
  endpoint HTTP, sem persistência nova.
- **Pendente**: **Fase 14 (Experiment Engine) e qualquer fase
  seguinte do "PROMPT MESTRE — SALE-IA V2" não começam sem nova
  confirmação explícita do usuário.**
- **Push + deploy confirmados (16/09/2026)**: commit `ea6e4bc` no
  GitHub. `reunioes_ativas: 0` confirmado na VPS (sem reunião ativa
  desta vez) — `git pull` (fast-forward `d83497e` → `ea6e4bc`) +
  `systemctl restart saleia` — `active`, journal sem erros.
  Pós-restart: `/health` = `versao 1.4.99`, `status online`, 4
  provedores `ok` (restart zerou os contadores de falha, mesma
  ressalva de sempre — não resolve o saldo de verdade, ver
  "Incidente ao vivo" acima); `/dashboard` = `200`.

### Embeddings Desacoplados — Ollama local + OpenAI opcional (V.1.4.39)
- `services/embeddings/`: interface `EmbeddingProvider` (`embed`, `embed_async`, `embed_batch`, `health_check`), `OllamaEmbeddingProvider` (HTTP local via `httpx`, zero import de SDKs de LLM externos), `OpenAIEmbeddingProvider`, `factory.get_embedding_provider()` (lê `EMBEDDING_PROVIDER`, erro explícito em valor desconhecido).
- `EMBEDDING_PROVIDER=ollama` é o padrão — RAG (`base_conhecimento`) e Sales Memory (`sales_memories`) deixam de depender obrigatoriamente da OpenAI.
- Refatorados os 4 pontos que geravam embedding: `agent/base_conhecimento.py`, `agent/sales_memory.py`, `api/main.py::adicionar_base` (`POST /base`), `agent/sessao_manager.py::exportar_para_base_conhecimento`.
- Novas colunas `embedding_provider`/`embedding_model`/`embedding_dim` em `base_conhecimento` e `sales_memories` — vetores de dimensões diferentes nunca são comparados entre si (bug pré-existente de `ValueError` fechado).
- `GET /admin/embeddings/status` (novo, JWT admin): status do provedor ativo, dimensão, contagem de documentos/memórias indexados.
- `scripts/reindex_embeddings.py`: CLI idempotente para regenerar embeddings sob o provedor configurado (`--dry-run`, `--provider`, `--table`, `--limit`).
- `docs/EMBEDDINGS_LOCAL.md`: guia de instalação do Ollama (Windows/Linux) e configuração.
- Testes: `tests/test_embeddings.py` (32 testes, mockado, sem rede/DB) + `tests/test_embeddings_semantic_ranking.py` (integração real, auto-skip sem Ollama local).

## Funcionalidades Novas (V.1.4.42 — 20/08/2026)

### Visual Cenário — removido da navegação visível
- Item de menu `🎬 Visual Cenário` removido de `frontend/dashboard.html`;
  botão `🎬 Visual` e função `abrirVisualScenario()` removidos de
  `frontend/cenario.html`.
- Backend intocado: `POST /generate-visual-scenario` e
  `frontend/visual-scenario.html` continuam funcionais, acessíveis por URL
  direta (`/visual-scenario?meeting=<id>`) para validação manual pendente.
- Revisão da decisão anterior (V.1.4.41 dizia "aceito como está" para
  manter Visual Cenário visível) — usuário pediu para tirar visualmente do
  front também aqui, mantendo só o backend.

## Funcionalidades Novas (V.1.4.41 — 20/08/2026)

Revisao da V.1.4.40 contra a especificacao original (prompt de desenvolvimento
recebido apos o deploy) encontrou 6 lacunas; 2 foram corrigidas nesta versao
(mecanicas, sem decisao de produto pendente), 4 seguem em aberto de proposito
(exigem decisao de arquitetura/produto — ver "O Que Falta").

### Propensao de Compra — dimensoes nomeadas + limiares configuraveis
- `PROMPT_RECAPITULACAO`: nova regra orienta a IA a avaliar 9 dimensoes de
  venda nomeadas (Dor, Urgencia, Orcamento, Autoridade, Interesse, Intencao,
  Engajamento, Proximo passo, Objecoes) ao montar os fatores do bloco
  `propensao` — so inclui a dimensao que realmente apareceu na conversa.
- `agent/propensao_rules.py`: `LIMIAR_ALTA`/`LIMIAR_MEDIA` deixam de ser
  constantes fixas e passam a ler `PROPENSAO_LIMIAR_ALTA`/`PROPENSAO_LIMIAR_MEDIA`
  do `.env` (fallback 70/45) — continuam sendo o unico lugar do codigo com
  esses limiares, agora ajustaveis sem deploy.

## Funcionalidades Novas (V.1.4.40 — 19/08/2026)

### Extensao Chrome simplificada
- Toggle "API ativa/desligada" com gate completo em todos os pontos de rede (incl. heartbeat) e bug de persistencia no service worker corrigido (estado nao era restaurado do storage fora do `onInstalled`).
- Removidos da UI: Visual Cenario, Mapa Financeiro (card), Score de Compra (numero), Cenario do Cliente (botao), "Backend online + URL" no popup — substituido por indicador simples Conectado/Desconectado/Conectando.
- `manifest.json`: permissao `scripting` removida (ficou orfa); versao `1.4.2` → `1.4.3`.

### Base de Conhecimento — download do documento original
- `base_conhecimento` ganhou colunas `arquivo_nome_original/arquivo_path/arquivo_mime/arquivo_tamanho`; `POST /base` agora multipart (texto + arquivo opcional); novo `GET /base/{id}/download` (JWT); arquivos em `data/base_arquivos/`.

### Sessoes ao Vivo — busca e filtros
- Busca por cliente/empresa/link/data/hora, filtros de status/periodo e ordenacao no dashboard (client-side); `listar_sessoes` enriquecida com cliente vinculado via `client_meetings`+`client_profiles`.

### Propensao de Compra
- `agent/propensao_rules.py`: classificacao deterministica (Alta/Media/Baixa/Nao determinada) a partir do score interno, sem custo de IA extra no tempo real.
- `PROMPT_RECAPITULACAO` ganhou bloco `propensao` estruturado (fatores + evidencias + como avancar) para o Detalhamento no dashboard, gerado uma unica vez por recapitulacao (sem chamada extra ao abrir).

## Funcionalidades Novas (V.1.4.44 — 21/08/2026)

### Piloto Claude Account Mode
Cada vendedor conecta a própria assinatura Claude (Pro/Max) via token de
`claude setup-token` e analisa suas reuniões sob demanda pelo Dashboard, sem
depender de uma conta de IA central da SALEIA. Atrás da feature flag
`CLAUDE_ACCOUNT_PILOT` (desligada por padrão). Detalhe completo no
CHANGELOG (V.1.4.44) — resumo:
- `agent/claude_account.py`: `ClaudeAccountExecutor`, único ponto de chamada
  ao Claude Agent SDK; criptografia do token (Fernet), sanitização de erros,
  classificação `LOGIN_REQUIRED`/`AUTH_REQUIRED`/`USAGE_LIMIT_REACHED`/`GENERIC_ERROR`.
- Tabelas novas `ClaudeConnection`/`ClaudeMeetingAnalysis` (`api/database.py`);
  reusa análise existente se a transcrição não mudou.
- 7 endpoints novos (`/claude-account/*`, `/admin/claude-account/metricas`)
  — conexão sempre resolvida pelo JWT de quem está logado, nunca por id vindo
  do cliente (isolamento por usuário sem precisar de "dono da reunião").
  Não existe hoje na SALEIA — extensão Chrome e tabela `sessoes` continuam
  anônimas, fora do escopo deste piloto.
- Dashboard: card de conexão em Configurações, botão "Analisar com Claude" na
  sessão, feedback 👍/😐/👎, painel de métricas admin no Monitor.
- 19 testes novos em `tests/test_claude_account.py`.

## Deploy V.1.4.44 Confirmado (22/08/2026)

- `reunioes_ativas: 0` checado em `/health` antes de agir (duas vezes: antes do `git pull` e novamente antes do `systemctl restart`).
- SSH root na VPS nova exigia senha (chave `saleia_vps` parou de funcionar) — acesso restabelecido com senha fornecida pelo usuario.
- `git fetch origin main` mostrou que o cache local de `origin/main` na VPS estava atrasado (ainda via `f23b8e0`); `git pull origin main` trouxe o fast-forward para `13f74f4` (bump de versao 1.4.43 -> 1.4.44).
- **Achado durante o `pip install -r requirements.txt`**: o resolvedor bateu em `error: resolution-too-deep` e instalou um ambiente inconsistente — `mcp` (trazido por `claude-agent-sdk`) exige `starlette>=0.48` no Python 3.14 (`sse-starlette` exige `>=0.49.1`), incompativel com o range `starlette<0.38.0,>=0.37.2` exigido por `fastapi==0.111.0`. Pip instalou `starlette 1.6.0` (quebraria o FastAPI, nucleo de toda a API, no proximo restart).
  - Corrigido removendo o pino exato de `fastapi==0.111.0`/`uvicorn[standard]==0.30.1` para `>=0.111.0`/`>=0.30.1` em `requirements.txt` (commit `249fd9a`) — ao rodar `pip install` de novo com o grafo completo (nao isolado), o resolvedor achou uma solucao consistente por conta propria: manteve `fastapi==0.111.0` e baixou `mcp` de `2.0.0` para `1.27.2` (compativel com `starlette==0.37.2`). `pip check`: "No broken requirements found."
  - Validado antes do restart: `import claude_agent_sdk`, `import agent.claude_account` e `import api.main` (com `PYTHONPATH=/opt/saleia`) — todos OK, sem excecao.
- `claude --version` = `2.1.239 (Claude Code)` confirmado funcional (o aviso de `allow-scripts` do npm nao impediu o binario de funcionar).
- `systemctl restart saleia`: servico `active`; `journalctl -u saleia` sem excecoes, todas as tabelas (incluindo as novas `ClaudeConnection`/`ClaudeMeetingAnalysis`) verificadas/criadas no startup.
- Pos-deploy: `/health` retornou `versao: 1.4.44`, 4 provedores `status: ok` com `falhas_consecutivas: 0` (restart tambem liberou os FDs vazados da V.1.4.43 — resolve o "URGENTE" anterior); `/dashboard` = `200`; `GET /claude-account/status` sem JWT retornou `401` (feature flag `CLAUDE_ACCOUNT_PILOT` confirmada ativa — endpoint existe e exige auth, nao `404`).
- Aviso pre-existente e sem relacao com este deploy: `OpenTelemetry não configurado: No module named 'opentelemetry.sdk'` no startup — `opentelemetry-sdk` nunca esteve em `requirements.txt` (instalado manualmente fora do pip na epoca da V.1.4.11-13); tratado como falha graciosa pelo proprio codigo, nao derruba o servico.

### Fix pos-deploy: `CLAUDE_TOKEN_ENC_KEY` invalida (22/08/2026)
- Primeiro teste real do "Analisar com Claude" no dashboard (usuario colou
  o proprio token de `claude setup-token`) retornou `HTTP 500`.
- `journalctl -u saleia` apontou a causa exata: `POST /claude-account/connect`
  → `agent/claude_account.py::criptografar_token` → `ValueError: Fernet key
  must be 32 url-safe base64-encoded bytes` — o valor de `CLAUDE_TOKEN_ENC_KEY`
  gravado no `.env` durante o setup da V.1.4.44 (21/08/2026) nao era uma
  chave Fernet valida.
- Corrigido gerando uma nova chave valida (`Fernet.generate_key()`) e
  substituindo a variavel no `.env` da VPS (backup do arquivo original em
  `/opt/saleia/.env.bak_fernet_fix`); `systemctl restart saleia` aplicado.
  Nenhum dado orfao: como a criptografia falhava antes de qualquer escrita
  no banco, nenhuma `ClaudeConnection` chegou a ser persistida com a chave
  antiga.
- **Pendente**: usuario precisa tentar conectar de novo pelo dashboard para
  confirmar que o fluxo completo funciona ponta a ponta agora.

## O Que Falta

- **Knowledge Compiler (Biblioteca de Inteligência) — pendências pós-ativação**: upload+extração já confirmados de ponta a ponta pelo usuário (fonte id=1, após os fixes de nginx/`MEDIUMTEXT`). Falta: validar `POST /base` também aceita arquivo >1MB (efeito colateral do fix de `client_max_body_size` do nginx); testar manualmente a compilação com IA (Fase 2) e a integração RAG/Skill/Playbook (Fase 3) — só foram testadas automaticamente até agora. Fases 4-6 do roadmap ainda não iniciadas. Detalhe completo na seção "Biblioteca de Inteligência" acima e em `docs/TASKS.md`.
- **Chave SSH `saleia_vps` continua nao autenticando** (`Permission denied (publickey,password)`) — acesso restabelecido só por senha root em 01/09/2026 (mesmo padrao recorrente de 19/08 e 22/08/2026). A chave publica provavelmente nao esta mais em `~/.ssh/authorized_keys` da VPS nova, ou foi rotacionada — nao investigado a fundo, senha continua sendo o fallback funcional.
- **Restart do `saleia.service` confirmado feito** (commit `dde7987` exato, ativo desde `2026-09-01 06:38:15 UTC` — ver secao "Deploy V.1.4.50/1.4.51 confirmado" acima). Falta so: (a) validar end-to-end se o `GROQ_API_KEY` novo resolveu a transcricao de audio (sem trafego real desde o restart para confirmar), (b) a extensao Chrome precisa ser reinstalada (`chrome://extensions`) pra vendedores passarem a enviar `X-Extensao-Versao` — sem isso o incidente de 31/08 (ver secao acima) continua indiferenciavel do lado do servidor.
- **Cost Intelligence — validacao manual pendente (V.1.4.51)**: os nomes exatos de campo de cache do DeepSeek (`prompt_cache_hit_tokens`) e Gemini (`cached_content_token_count`) nao foram confirmados contra uma resposta real de producao — degradam com seguranca para `0` via `getattr`, mas a granularidade de cache pode estar subestimada ate essa validacao. Fazer 1 chamada real por provedor em homologacao/producao logando `response.usage`/`response.usage_metadata` bruto (`api/ai_router.py::_usage_from_*`). Fases 2-6 do roadmap (dashboard de custos, Budget Guard, Cost Router) ainda nao iniciadas — ver `docs/cost-intelligence-audit.md`.
- Descomissionar VPS antiga (`204.168.180.25`).
- Alterar senha do admin via dashboard.
- ~~Reindex de embeddings pendente~~ — **verificado em 04/09/2026, nada a fazer**: dry-run rodado direto na VPS via SSH confirmou `base_conhecimento` (54/54) e `sales_memories` (394/394) 100% ja em `ollama`/`embeddinggemma`, sem nenhum embedding legado da OpenAI restante (confirmado tambem por query direta no MySQL). Reindex real nao precisou rodar.
- **Provedores de IA centrais — status em 31/08/2026** (ver nota de 01/09 abaixo): ainda sem saldo/chave valida (mesmo incidente aberto desde 22/08/2026, agravado). Groq (transcricao) teve a chave corrigida pelo usuario durante a sessao de 31/08, ainda sem validacao end-to-end.
  - **Nota (01/09/2026)**: apos o `systemctl restart` do deploy do Knowledge Compiler, `/health` passou a mostrar os 4 provedores como `status: ok`/`falhas_consecutivas: 0` — **isso e so o restart zerando os contadores em memoria, nao confirma que o saldo/chave foi resolvido** (o proprio achado de 22/08 abaixo ja documentava esse comportamento do `/health`). Nao foi feita nenhuma chamada real de teste contra os 4 provedores nesta sessao para confirmar se voltaram a funcionar de fato.
  - `deepseek`: `APIStatusError 402 Insufficient Balance`.
  - `openai`: `RateLimitError 429 insufficient_quota` — "You have no credits remaining".
  - `anthropic`: `BadRequestError 400` — "Your credit balance is too low to access the Anthropic API".
  - `gemini`: **mudou de causa** — em 22/08 era `403` de faturamento suspenso no Google Cloud; em 31/08 passou a ser `400 API_KEY_INVALID` (chave de API rejeitada, nao mais faturamento). Verificar se a chave em uso ainda e valida/nao expirou.
  - Resolver adicionando credito/saldo nos paineis do DeepSeek, OpenAI e Anthropic, e gerando/validando uma chave Gemini nova. Ate isso ser feito, nenhuma analise de reuniao (recapitulacao manual, tempo real, ou piloto Claude Account) funciona pelos provedores centrais — so pelo fallback Claude Account, e so para vendedores logados na extensao (ver incidente acima).
  - Achado (22/08/2026, ainda nao investigado): `/health` pode reportar os 4 provedores como `status: ok` / `falhas_consecutivas: 0` mesmo com falha real recente — o contador de falhas do `/health` nem sempre e incrementado pelo caminho de `/recapitulacao-manual`; `/health` sozinho nao e sinal confiavel de saldo. Em 31/08 o `/health` já refletia corretamente o estado degradado (`status: "degradado"`, `falhas_consecutivas` alto em todos), entao esse achado pode ja estar resolvido ou ser intermitente — nao confirmado.
- Testar Visual Cenario AI em producao (DALL-E 3 + OpenAI) continua pendente — agora so acessivel por URL direta (`/visual-scenario?meeting=<id>`), sem botao/menu (removido na V.1.4.42).
- **Conectar** via `claude setup-token` confirmado funcionando em producao (22/08/2026, `POST /claude-account/connect` = 200 OK).
- **Fix critico (V.1.4.46, 22/08/2026)**: primeiro teste real de `POST /claude-account/analisar` (apos a V.1.4.45 adicionar o botao na tela de Analisar Transcricao) falhou com `GENERIC_ERROR` — `error_message` persistido: "Credit balance is too low", a mesma mensagem do provedor Anthropic central sem saldo. Causa: `claude_agent_sdk` monta o env do subprocesso CLI herdando **todo** o `os.environ` do `saleia.service` (incluindo `ANTHROPIC_API_KEY` central), e o Claude Code prioriza essa variavel sobre `CLAUDE_CODE_OAUTH_TOKEN` quando as duas existem — o piloto estava cobrando da conta compartilhada (sem saldo), nao da assinatura do vendedor. Corrigido em `agent/claude_account.py::_executar_query` limpando `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` no `env` passado ao SDK. Teste novo cobrindo o comportamento. Deploy confirmado (ver Deploy V.1.4.46 abaixo).
- **Fix (V.1.4.47, 22/08/2026)**: apos o fix da V.1.4.46, usuario conectou com sucesso mas a analise continuou falhando — dessa vez com `AUTH_REQUIRED`/"401 OAuth access token is invalid" (nao mais o erro de saldo, confirmando que o fix anterior funcionou). Diagnostico (token decriptografado só para inspecao, nunca exposto): o token salvo tinha **um espaco no meio da string** — artefato de copiar um token longo de um terminal com quebra de linha visual. `POST /claude-account/connect` so fazia `.strip()` (pontas); trocado por `re.sub(r"\s+", "", ...)` que remove whitespace em qualquer posicao. **Vale so para novas conexoes** — quem conectou antes precisa desconectar/reconectar colando o token de novo.
- **Fix (V.1.4.48, 22/08/2026)**: apos reconectar com o token limpo (fix da V.1.4.47), autenticacao funcionou (sem mais 401) mas a analise falhou com `GENERIC_ERROR: error_max_turns`. Causa: `_executar_query` passava `allowed_tools=[]` tentando rodar sem ferramentas, mas esse campo so remove pre-aprovacao — nao torna as ferramentas indisponiveis (doc do SDK: "To restrict which tools are available at all, use `tools`"). O modelo tentava usar o conjunto padrao de ferramentas, caia em permissao negada e esgotava `max_turns=1`. Corrigido com `tools=[]` (o campo certo) + `max_turns` `1` -> `3` como margem.
- **Validado end-to-end (22/08/2026)**: apos o deploy da V.1.4.48, usuario reconectou e disparou uma analise real com sucesso — piloto Claude Account funcionando ponta a ponta pela primeira vez (conectar -> analisar -> 7 blocos). As 3 rodadas de fix (V.1.4.46 credencial herdada, V.1.4.47 token corrompido, V.1.4.48 ferramentas nao desabilitadas) resolveram os 3 bugs reais expostos pelo primeiro uso de producao — nenhum tinha sido pego pelos 26 testes existentes porque todos mockam `_executar_query`/`claude_agent_sdk.query` inteiro, nunca exercitando a configuracao real do `ClaudeAgentOptions` contra o SDK/CLI de verdade.
- **Esclarecimento (22/08/2026) — nao ha expiracao programada por tempo**: usuario perguntou se a SALEIA forca expiracao do token do piloto (comparando com outro projeto seu, NEX-ALS-IDE, onde a conexao nao cai — so para de responder ao esgotar a janela de uso de 5h da assinatura). Confirmado lendo `agent/claude_account.py::_levantar_erro_classificado`: nao existe timer. Dois caminhos distintos:
  - `RateLimitEvent.rate_limit_info.status == "rejected"` (janela de uso da assinatura esgotada, mesmo caso do NEX-ALS-IDE) -> classificado `USAGE_LIMIT_REACHED`, conexao **continua `ativo`**, sem precisar reconectar.
  - Mensagem batendo no regex `_PADROES_AUTH` (`unauthorized`, `invalid...token`, `expired`, `401`, `forbidden`, `403`) -> classificado `AUTH_REQUIRED`, ai sim marca a conexao como `expirado` e exige token novo. Foi esse o caminho acionado pelo bug do token corrompido (V.1.4.47), nao uma expiracao por tempo.
- **Novo (V.1.4.49, 22/08/2026) — login opcional na extensao + fallback no tempo real**: usuario pediu que a extensao Chrome tambem use a conta Claude do vendedor. Extensao ganhou um bloco "Conta" no popup (login opcional via `/auth/login`, mesmo endpoint do Dashboard) — quem nao loga continua 100% anonimo como antes. Quando logado, `POST /tempo-real` resolve `usuario_id` via JWT e o repassa por toda a cadeia (`processador_tempo_real.py` -> `orquestrador.py` -> os 4 agentes); se os 4 provedores centrais se esgotarem, `agent/multiagente/claude_fallback.py` tenta a conta Claude pessoal do vendedor antes de desistir (fallback automatico, nao substitui os 4 centrais no caminho normal — decisao deliberada pra nao drenar a janela de uso de 5h da assinatura a cada ciclo de 60s do tempo real nem sofrer o overhead do CLI subindo a cada fragmento). 10 testes novos (`tests/test_multiagente_claude_fallback.py` + `tests/test_tempo_real_auth.py`); achado durante os testes: `authorization: str | None = _Header(...)` no endpoint `/tempo-real` usava um alias definido bem depois no arquivo, quebrando o import do modulo inteiro — corrigido usando `Header` (ja importado no topo). **Pendente**: deploy na VPS + recarregar a extensao (`chrome://extensions`, manifest `1.4.3` -> `1.4.4`) + validar o fallback disparando de verdade.
- 8 falhas de teste pre-existentes e nao relacionadas encontradas em `tests/test_next_best_question.py`/`tests/test_realtime_memory.py` (nao corrigidas — fora do escopo desta rodada).
- **Decisoes tomadas sobre as 4 lacunas remanescentes da V.1.4.40 (20/08/2026)**:
  - Download da Base sem isolamento por empresa/tenant: **aceito como esta** — SALEIA e uso interno de uma unica empresa, multi-tenancy nao se aplica. `GET /base/{id}/download` continua exigindo so JWT valido.
  - Sessoes ao Vivo so com status "Ao vivo"/"Finalizada": **aceito como esta** — nao inventar "Processando"/"Erro" sem sinal real no banco continua sendo a decisao correta.
  - Codigo morto de Visual Cenario/Mapa Financeiro/Score/Cenario do Cliente: **auditado, nada para remover** — a limpeza da V.1.4.40 ja foi completa (nenhum handler orfao encontrado); o que parecia candidato a remocao (backend de mapa financeiro, score_compra, resumo do cliente, Visual Cenario) esta ativamente em uso por outras partes do sistema.
  - Testes automatizados: **parcialmente feito** — `tests/test_base_download.py` (7 testes) e `tests/test_propensao_rules.py` (7 testes) cobrem download da Base e classificacao de propensao. Testes de UI/JS (toggle da extensao, busca de sessoes, responsividade) ficam de fora por decisao — projeto nao tem infra de teste JS (Jest/jsdom) e o custo de introduzi-la agora nao foi considerado necessario.

## Deploy V.1.4.39 Confirmado (19/08/2026)

- `reunioes_ativas: 0` checado em `/health` antes de agir (deploy havia sido adiado em 17/08/2026 por reuniao ativa).
- `git pull origin main` na VPS nova: fast-forward `670ad5a..85dd554` (trouxe fix nao documentado do Anthropic em `api/ai_router.py`).
- `systemctl restart saleia` — servico `active`; `/health` = `versao 1.4.39`, 4 provedores `status: ok`; `/dashboard` = `200`.
- Achado: o commit trazido pelo pull corrigia `_call_anthropic` para nao assumir `content[0]` como bloco de texto — isso resolveu os 138 `falhas_consecutivas` do provedor Anthropic que estavam visiveis em producao antes do restart.

## Ollama instalado na VPS nova (17/08/2026)

- `ollama.service` — `active` + `enabled` (sobrevive a reboot).
- Modelo `embeddinggemma` baixado (621 MB) e testado — **dimensao real confirmada: 768**.
- Escuta apenas em `127.0.0.1:11434` (nao exposto externamente).
- CPU-only (sem GPU na VPS); ~4.3GB RAM disponivel no momento do teste; 134GB de disco livre.
- Instalado via script oficial (`curl -fsSL https://ollama.com/install.sh | sh`), sem afetar `saleia.service` (servicos independentes).

## Deploy V.1.4.38 Confirmado (16/08/2026)

- Verificado via SSH que `/opt/saleia` ja estava no commit `555b990` (igual ao GitHub `origin/main`) — deploy ja havia ocorrido antes da doc ser atualizada.
- `systemctl restart saleia` executado; servico `active`.
- `curl http://127.0.0.1:8000/health` retornou `"versao":"1.4.38"`, banco MySQL com `banco_latencia_ms: 1`, 4 provedores IA configurados (`ok`).
- `curl http://127.0.0.1:8000/dashboard` retornou `200`.

## Bugs Corrigidos em V.1.4.38 (16/06/2026)

- Connection leak em `enriquecer_perfil_apos_relatorio` (client_intelligence.py)
- Dead code: funcao `processar_fragmento_tempo_real` legada removida (processador_tempo_real.py)
- Sales Memory agora injetada no orquestrador multiagente — memorias comerciais passam a enriquecer analise em tempo real (orquestrador.py)
- `mapa_financeiro` restaurado do banco ao trocar de worker uvicorn (processador_tempo_real.py)
- `AsyncOpenAI` singleton — nao recriado a cada chamada RAG (base_conhecimento.py)
- `MAX(score)` desnecessario removido do SELECT em `_recalcular_stats` (client_intelligence.py)

## Infraestrutura (V.1.4.17 — 09/06/2026)

- VPS dedicada CPX32 provisionada na Hetzner Helsinki (`37.27.214.33`).
- MySQL migrado de servidor remoto compartilhado (`177.104.186.227`, 676ms) para instancia local (`127.0.0.1`, ~2ms) — reducao de 338x na latencia do banco.
- Novo dominio `saleia.app.br` criado no Registro.br + delegado ao Cloudflare (nuvem laranja).
- Deploy via `git clone https://github.com/fasterdrible-lab/SALE-IA.git /opt/saleia` + venv Python 3.14 + systemd com `TimeoutStopSec=30`.
- nginx configurado para `api.saleia.app.br` com proxy reverso para `127.0.0.1:8000`.
- Dados migrados: tabelas `admin_route_rules`, `alertas_automaticos`, `api_integrations`, `audit_logs`, `base_conhecimento` (49 docs RAG) preservadas.
- Tabelas auto-criadas no startup: `relatorio`, `meeting_memory`, `sessoes`, `usuarios`, `visual_scenarios`.

## Concluido (T12 - V.1.4.2)

- `GET /relatorios` agora retorna campo `provedor` extraido de `_provedor_ia` dentro de `dados.recapitulacao` (ou `perfil_disc`/`diagnostico_financeiro` como fallback). Funciona tanto para fonte SQLite quanto para arquivos JSON.
- Dashboard: `<select id="filtro-provedor">` adicionado ao toolbar de Reunioes com opcoes DeepSeek, OpenAI, Anthropic, Gemini.
- `filtrarReunioes` filtra por provedor via `r.provedor`.
- `limparFiltrosReunioes` reseta o select de provedor.
- Card de reuniao exibe nome do provedor como label discreta ao lado da data/score.

## Observabilidade (V.1.4.11–V.1.4.13)

- Contadores IA em memória com lock thread-safe (`api/ai_router.py`)
- Aba Monitor no dashboard com cards de métricas e sparklines 6h
- SQLite rolling 24h em `data/metricas.db` + alertas Telegram por threshold
- OpenTelemetry SDK integrado ao Grafana Cloud Tempo (OTLP/HTTP)
  - Stack Grafana Cloud: `slimturtle2775` — região `sa-east-1`
  - Datasource Tempo: `grafanacloud-slimturtle2775-traces`
  - Traces de todas as rotas FastAPI chegando em tempo real
- Global fetch interceptor no dashboard.html injeta JWT automaticamente

## Estado dos Provedores (V.1.4.15)

Ordem ativa (ai_provider_order.json na VPS):

1. `deepseek` — PRINCIPAL ✅ Online
2. `openai` — ✅ Online (+ RAG embeddings text-embedding-3-small)
3. `anthropic` — ❌ Sem créditos (chave válida, saldo zerado)
4. `gemini` — modelo `gemini-2.5-flash` (atualizado de gemini-2.0-flash)

RAG: 49 transcrições indexadas, embeddings 1536 dimensões funcionando.

### Transcricao de Audio (V.1.4.5)

- SDK oficial `groq>=0.9.0` instalado na VPS; modelo `whisper-large-v3`
- Endpoint `POST /admin/transcricao/config` aceita `apenas_salvar: true` para salvar chave sem mudar provedor
- Dashboard: botao 👁 para mostrar/ocultar chave Groq; `salvarChaveGroq` usa `fetchJsonWithFallback`
- Extensao Chrome exibe erros de transcricao na barra de status da sidebar

### Redesign Visual Gold/Black (V.1.4.6)

- Paleta premium aplicada em toda a plataforma: dourado metalico `#D4AF37`, preto absoluto `#000000`
- `dashboard.html`: variaveis CSS atualizadas, sidebar preta, botoes e badges dourados, tipografia Inter+Sora
- `login.html`: logo SALEIA PNG premium integrado via Nginx static location
- `frontend/logo-saleia.png`: novo arquivo de logo adicionado

### Visual Cenario e Navegacao (V.1.4.7)

- `visual-scenario.html`: paleta gold/black; titulo renomeado para "Visual Cenario AI"
- `dashboard.html`: item de menu "Visual Scenario" → "Visual Cenario"

### Multi-clientes, Botao Inicio e Extensao Chrome (V.1.4.8)

- `dashboard.html`: campo "Cliente" substituido por lista dinamica — botao `+ Cliente`, botao remove (min 1)
- `visual-scenario.html`: botao "← Inicio" volta para `/cenario/{meeting_id}` em vez de `/`
- `cenario.html`: paleta gold/black completa
- Extensao Chrome: popup.css, sidebar.css, content.css redesenhados em ouro/preto
- `content.js`: modal Participantes com lista de clientes dinamica (event delegation), migracao de dados antigos

### Manual Atualizado (V.1.4.9)

- `frontend/manual.html`: reescrito de V.1.4.5 para V.1.4.8 — secoes 7 (Cenario do Cliente), 8 (Visual Cenario AI), nav sticky e botoes de acoes rapidas

### UX do Dashboard — Chaves API e Status de Conexão (V.1.4.10)

- Campos de chave dos 4 provedores: `autocomplete="new-password"` bloqueia preenchimento automático do Chrome; botão 👁 (função `toggleVerChave`) alterna visibilidade
- Botão "Testar conexão": badge `✅ Online` ou `❌ Offline` permanece visível no cabeçalho do card após o teste (não desaparece mais com timeout)

## Problemas Conhecidos

Nenhum problema crítico pendente.

## Cuidados

- Nunca expor `.env`, tokens ou chaves em logs, frontend ou documentacao.
- Nao analisar a arvore duplicada fora de `SALEIA/` sem pedido explicito.
- Preservar compatibilidade com o fluxo atual da extensao Chrome.
- Alterar somente arquivos da tarefa em andamento.
