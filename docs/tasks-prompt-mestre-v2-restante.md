# Tasks: o que falta do "PROMPT MESTRE — SALE-IA V2"

> Criado em 24/09/2026 (produção em V.1.4.141). Fonte: `# PROMPT MESTRE —
> SALE-IA V2-03_09_26.txt` (raiz do repo) cruzado com CHANGELOG.md,
> CURRENT_STATE.md e `docs/tasks-sales-reasoning-engine-completo.md`.
> Sempre consulte este arquivo antes de assumir o que já foi feito.

## Diagnóstico em uma frase

As Fases 0-24 existem no código, mas a maior parte existe só como
**contrato/regra pura**. O que falta é o **dado real fluindo**: nada em
produção escreve `SalesEvent`/`SalesEvidence`/`OpportunityMemory`/
`OpportunityGraph`, MEDDPICC está bloqueado, os sinais de Deal Risk não
são calculados e o resultado da venda (avançou/ganhou) quase não é
capturado. Sem isso, Sales Science e Learning Loop giram em vazio, e a
Fase 25 (critérios do Digital Twin) não tem como ser atingida.

## Status atual por tema

| Tema | Pronto e em produção | Só contrato/regra (sem dado real) | Não existe |
|---|---|---|---|
| **Sales Intelligence** | SPIN, sinais comportamentais, motivação, objeção + causa raiz (extratores IA no ciclo); vínculo meeting↔opportunity; SalesReasoningEngine com 9/11 campos (Shadow Mode ligado) | SalesEvent, SalesEvidence, OpportunityMemory/Graph (sem escritor), MEDDPICC, Deal Risk, Conversation Metrics | Challenger Engine (está no diagrama da arquitetura, nunca construído) |
| **Sales Science** | Win/Loss, Seasonality, Conversion Drivers no dashboard (sobre `Opportunity`) | Seller Benchmark, Strategy Effectiveness, Objection Trends, Experiment Engine (sem persistência) | Pipeline analítico assíncrono (ETL), Data Quality (seção 33) |
| **Learning Loop** | RecommendationEvent + classificação de uso (embeddings) | `stage_advanced`/`opportunity_result` nunca capturados; Seller DNA com kill-switch desligado | Retroalimentação de insights no raciocínio além de `historical_patterns` por estágio |
| **Digital Twin readiness** | AutonomyPolicy, escalonamento humano, audit trail (100%), policy_violation (0), Piloto (desligado) | 9 critérios da Fase 25: vários com número, poucos batendo o alvo | 10 cenários E2E (seção 30), load test (32), contract repair de LLM (29), versionamento completo (34), 6 docs obrigatórios (35) |

### Fase 25 — onde cada critério está

| Critério | Alvo | Hoje | Bloqueio principal |
|---|---|---|---|
| transcription reliability | WER ≤ 10% | groq 7,3% ✅, whisper_local 11,0%, whisper sem saldo | Saldo OpenAI |
| event precision | ≥ 90% | **sem medição** | Não existe extrator de SalesEvent |
| objection classification | ≥ 90% | 75% | Qualidade do classificador |
| critical hallucination | ≈ 0 | 14,44% (todas, não só críticas) | "Crítica" nunca foi definida |
| policy violation | 0 | 0 ✅ | — |
| recommendation quality | a definir | 52,8% uso (subestimado, fix V.1.4.140) | Reuniões novas; alvo nunca definido |
| E2E success | ≥ 99% | 85,5% (proxy) | Saldo DeepSeek/OpenAI + E2E real inexistente |
| audit coverage | 100% | 100% ✅ | — |
| human escalation functional | 100% | mecanismo pronto, nunca disparado | Nada autônomo roda ainda |

---

## Pré-requisitos fora do código (bloqueiam medição, não implementação)

- **P1 — Saldo DeepSeek/OpenAI**: derruba E2E success e bloqueia o
  benchmark do whisper. Decisão financeira.
- **P2 — Volume de reuniões reais**: não há nenhuma chamada de IA desde
  23/09 14:12 UTC. Learning Loop e Sales Science dependem disso.
- **P3 — Oportunidades com resultado**: Sales Science precisa de
  `Opportunity` marcadas won/lost (hoje só manualmente pelo dashboard).

---

## Bloco A — Sales Intelligence: fazer o dado estruturado existir

Ordem pensada: primeiro o que reaproveita dado já extraído (zero IA
nova), depois extratores novos.

### A1 — Investigar as linhas duplicadas entre falantes [CONCLUÍDA — 24/09/2026, V.1.4.142 + ext. V.1.4.17]
- **Por quê primeiro**: tudo abaixo consome a transcrição. Achado da
  V.1.4.140: linhas quase iguais alternando 2 rótulos de falante
  ("Felipe:"/"Paulo:"). Se for bug de captura (legenda + Whisper
  sobrepostos), contamina extratores, talk ratio e Seller DNA.
- **Entrega**: causa confirmada com amostra real + fix ou documentação.
- **Teste**: reunião de amostra sem duplicação após o fix.

### A2 — Persistir SalesEvidence a partir dos extratores existentes [CONCLUÍDA — 30/09/2026, V.1.4.148]
- Os extratores de SPIN/sinais/motivação/causa raiz já produzem
  `evidence_quote` validada literalmente contra a conversa, e hoje ela
  é descartada após o ciclo. Gravar como `SalesEvidence`
  (`criar_sales_evidence()`, Fase 1.2, nunca chamada).
- **Cuidado**: deduplicar entre ciclos (a mesma fala reaparece a cada 60s).
- **Kill-switch**: `SALES_EVIDENCE_PERSIST_ENABLED`.
- **Teste**: reunião de 3 ciclos → N evidências únicas, sem duplicata.

### A3 — Escritor de OpportunityMemory [CONCLUÍDA — 30/09/2026, V.1.4.149]
- Quando a reunião tem `opportunity_id` (Tarefa 3.1), gravar os fatos
  do ciclo nas categorias de `OpportunityMemory` (`pain_points`,
  `objections`, `champion`…), com append-only + contradição (Fase 2.1).
- **Efeito**: `opportunity_memory` deixa de vir vazio no
  SalesReasoningEngine.
- **Teste**: 2 reuniões na mesma oportunidade → memória acumulada;
  valor divergente → `contradiz` preenchido, nada apagado.

### A4 — Escritor de OpportunityGraph [CONCLUÍDA — 30/09/2026, V.1.4.150]
- Arestas `PAIN → causa → IMPACT` etc. derivadas dos insights gravados
  em A3 (regras fixas por categoria, nunca IA).
- **Teste**: exemplo literal da Fase 2.2 reproduzido com dado do ciclo.

### A5 — Extrator de MEDDPICC [CONCLUÍDA — 30/09/2026, V.1.4.151]
- Mesmo padrão de `spin_extractor.py`: vocabulário fechado dos 8 itens,
  `evidence_quote` obrigatória e checada por substring. **Não mexe no
  prompt do Closer** (a razão do bloqueio original).
- **Efeito**: `meddpicc_state` real → **10/11 campos**.
- **Teste**: guarda contra citação fabricada; custo por chamada medido.

### A6 — Sinais reais para Deal Risk [CONCLUÍDA — 01/10/2026, V.1.4.153]
- `NO_NEXT_STEP` (próximo passo registrado na recapitulação),
  `HIGH_PRICE_RESISTANCE` (contagem de objeções PRICE já classificadas),
  `STALE_OPPORTUNITY` (dias desde a última reunião vinculada). Só
  `COMPETITOR_ADVANTAGE` não tem fonte e segue como gap explícito.
- **Efeito**: `risks_calculados` do Opportunity Intelligence deixa de
  ser gap.

### A7 — Extrator de SalesEvent [CONCLUÍDA no código — 01/10/2026, V.1.4.159; medição real pendente]
- Classifica trechos nas 14 categorias de `SALES_EVENT_TYPES`, com
  evidência. Pode reaproveitar saídas de A2/A5 para parte dos tipos.
- **Teste**: rodar contra `expected_events` do Golden Dataset (Fase 20)
  → primeiro número real de `event_precision`.

### A8 — Turnos temporizados por falante [extensão + backend] [CONCLUÍDA — 17/10/2026, V.1.4.187 + ext 1.4.37; validada pelo usuário em reunião real, indicador ao vivo aprovado]
- Pré-requisito de Conversation Metrics/Seller Coaching (talk ratio,
  perguntas, monólogos). Depende de A1.
- **Teste**: transcrição conhecida → métricas batendo o cálculo manual.
- **Feito**: extensão grava início/fim de cada fala da legenda e manda em
  `turnos_novos`; tabela `turnos_fala`; `agent/turnos_rules.py` (papel
  pelo "quem é quem"); card "🗣️ Conversa" na sessão; Seller Coaching com
  Talk Ratio e Question Quality reais (30 dias); indicador ao vivo na
  sidebar (pedido do usuário, em avaliação). `tests/test_turnos.py` bate a
  conta manual. Tempo vem da legenda (aproximado).

### A9 — Challenger Engine [decisão de produto]
- Está no diagrama da seção 3, mas nenhuma fase o detalha. Decidir:
  construir (mesmo padrão de `negotiation_rules.py`) ou registrar como
  fora de escopo.

---

## Bloco B — Sales Science: dados confiáveis e pipeline analítico

### B1 — Data Quality (seção 33) [CONCLUÍDA — 24/09/2026, V.1.4.143]
- Validações: `seller_id`/`opportunity_id` ausente, valor negativo,
  timestamp inválido, evento duplicado, reunião órfã, desfecho
  desconhecido. Endpoint admin + relatório.
- **Por quê cedo**: "sem dados confiáveis não existe Sales Science
  confiável".

### B2 — Capturar `stage_advanced` e `opportunity_result` [CONCLUÍDA — 01/10/2026, V.1.4.154]
- `stage_advanced`: mudança de `Opportunity.stage` entre a reunião da
  recomendação e a seguinte. `opportunity_result`: status final
  won/lost da oportunidade vinculada.
- **Efeito**: `taxa_avanco`/`taxa_desfecho_positivo` (Fase 10.3) deixam
  de ser `None`. Fecha o elo "resultado é registrado" do Learning Loop.

### B3 — Pipeline analítico assíncrono (seção 31) [infra]
- Job agendado fora do hot path (respeitando
  `pode_executar_analise_pesada()`, Fase 9.1) que monta o dataset
  analítico e pré-calcula Win/Loss/Seasonality/Drivers/Trends.
- **Teste**: o ciclo de `/tempo-real` não muda de latência com o job
  rodando.

### B4 — Objection Trends com dado real [depende de A2/A3]
- Alimentar `objection_trend_analyzer.py` com as objeções classificadas
  persistidas.

### B5 — Seller Benchmark com `seller_tier` real [depende de P2/P3]
- Definir o tier por taxa real de conversão por vendedor (amostra
  mínima) e ligar `benchmark_controlado()`.

### B6 — Persistir experimentos e analisar resultado [Fase 14]
- Tabela de experimentos + atribuição pilot/control + análise via
  `pattern_discovery_rules.descobrir_padrao()`. Só faz sentido com B2.

---

## Bloco C — Learning Loop: fechar o ciclo

### C1 — Remedir recommendation_quality (ids > 236) [CONCLUÍDA — 29/09/2026]
- Resultado: 45,6% depois do fix (52,8% antes), `USED` 1,7%. Fix
  confirmado estruturalmente, hipótese de subestimação refutada.
  Detalhe no CHANGELOG.

### C8 — Calibrar recommendation_quality com rótulos humanos [FEITA a rotulagem — 05/10/2026; calibração impossível]
- 0/49 usados na rotulagem humana; embeddings erram 16/49. Métrica atual
  não confiável. Ver CHANGELOG (C8) e a investigação da V.1.4.166.

### A10 — Falante correto na transcrição [FEITA no código — 08/10/2026, extensão V.1.4.20; validar no Meet real]
- 86-100% das linhas vêm com o mesmo rótulo ("João"). Corrigir a leitura
  do nome na legenda do Meet atual e nunca rotular fala desconhecida com
  o nome de um cliente salvo. Maior impacto esperado na "alucinação".
- Feito: "Não identificado" no lugar do cliente salvo; nome pela
  estrutura da legenda (bloco com 1 foto); clientes só valem na reunião
  em que foram cadastrados; `[SALEIA-FALANTE]` no console quando não
  achar. Testado em DOM simulado; falta a 1ª reunião real.

### A12 — Precisão da transcrição [passo 2 feito no código — 09/10/2026, V.1.4.169 + ext. V.1.4.21]
- Passo 1 (usuário): extensão nova em todos + legenda do Meet em Português.
- Passo 2 (feito): filtro de texto de tela no backend (22,6% das linhas
  eram tela), vocabulário no Whisper com descarte de alucinação, extensão
  só na área de legendas, áudio da aba em arquivos completos.
- Passo 3 (pendente): 10 min de reunião real corrigidos à mão → WER e
  acerto de falante da legenda × Whisper; decidir a fonte principal (o
  áudio separa vendedor/cliente por canal, sem depender do DOM do Meet).

### A11 — Reduzir o atraso da sugestão [EM PRODUÇÃO — 07/10/2026, V.1.4.167; extensão V.1.4.19 aguarda reinstalação]
- Ciclo 60s → 20s (intervalo agora vem do servidor), trava 35s → 15s,
  Shadow limitado a 1/min. Esperado: ~35-40s → ~15-20s. Custo ~US$ 0,37
  → ~0,85 por hora de reunião. Medir o atraso real depois da
  reinstalação.

Pedido original da C8:
- Rotular ~50 pares (recomendação, fala nova) como usado/parcial/
  ignorado e ajustar os limiares (hoje 0,55/0,35, nunca calibrados) —
  e avaliar comparar só com falas do vendedor. Sem isso,
  `recommendation_quality` não serve como critério da Fase 25.
### C2 — Ligar Seller DNA [CONCLUÍDA no código — 30/09/2026, V.1.4.152; flag em produção pendente do deploy]
- `SELLER_DNA_OBSERVACAO_ENABLED=true` em produção + agregação ligada
  em `seller_context` → **11/11 campos** (junto com A5).
### C3 — Avaliar o Shadow Mode (Tarefa 6.2) [RODADA — 08/10/2026: Piloto NÃO pode começar; erro 61% (billing), quality sem medição; remedir com saldo + extensão 1.4.20]
- Relatório agreement/latency/errors/cost por origem, com o contexto
  completo. Define se o Piloto pode começar.
- **2ª rodada 17/10/2026** (`/tmp/c3_20261017.json` na VPS, dados pós-reset
  de 11/10): 1.575 comparações (1.191 comparáveis), 39 reuniões, agreement
  91,8%, latência p95 6,6 s, error_rate 24,4% — **todo erro em 12-14/10**
  (IA fora por saldo/cota); **0% desde 15/10**. Custo do caminho Shadow
  US$ 11,30 (53% do tempo real). Piloto: **NÃO** — falta `quality`
  (C4) e a amostra é quase toda de reuniões de TESTE do usuário (música,
  "testando"), não de venda real; agreement aqui não mede valor.
  `recommended_framework` sem vocabulário fechado ("SPIN" em ~40 grafias).
  Próximo: C4 usando reuniões reais (ex.: as do Paulo) como referência.
### C4 — Definir o alvo de recommendation quality e a métrica de qualidade
- O prompt deixa o alvo "a definir". Decidir o número e se `quality`
  do Shadow Mode usa LLM-judge (custo real por comparação).
### C5 — Retroalimentar insights no raciocínio
- Hoje só `historical_patterns` filtrado por estágio chega ao motor.
  Incluir estratégias com efetividade comprovada (B2) quando houver
  amostra suficiente, sempre como associação, nunca como causa.
### C6 — Piloto com 1 vendedor (Tarefa 6.3 / Fase 24) [decisão, depende de C3]

---

## Bloco D — Prontidão para o Digital Sales Twin (Fase 25 + seções 26-36)

### D1 — Painel único de prontidão [CONCLUÍDA — 01/10/2026, V.1.4.155]
- `GET /admin/readiness` com os 9 critérios, o valor atual, o alvo e a
  origem do número (real, proxy ou gap). Substitui medições manuais.
### D2 — Definir "hallucination crítica" e atacar os casos [CONCLUÍDA no código — 02/10/2026, V.1.4.160; medição real pendente]
- Separar as críticas (inventar preço, promessa ou dado do cliente) das
  demais; medir as críticas isoladamente contra ≈ 0.
### D3 — Objection classification 75% → 90% [CONCLUÍDA no código — 02/10/2026, V.1.4.161; remedição pendente]
- Analisar os erros no Golden Dataset e ajustar o prompt/regra; remedir.
### D4 — Suíte E2E dos 10 cenários (seção 30) [CONCLUÍDA — 01/10/2026, V.1.4.156]
- Hoje existe 1 arquivo de ciclo de vida. Cobrir: ganha, perdida por
  preço, perdida por concorrente, várias reuniões, troca de decisor,
  objeção falsa de preço, indeciso, provider fora, RAG fora, prompt
  injection. Mock de IA, persistência real.
### D5 — Contract tests com reparo controlado (seção 29) [CONCLUÍDA — 01/10/2026, V.1.4.158]
- Resposta inválida de LLM: rejeitar → reparar → registrar → fallback
  seguro. Garantir que JSON quebrado nunca chegue à sidebar.
### D6 — Versionamento completo da inteligência (seção 34) [CONCLUÍDA — 01/10/2026, V.1.4.157]
- Hoje só `prompt_version`/`rule_version`. Adicionar
  `reasoning_engine_version`, `policy_version`, `knowledge_version`,
  `model_version` em RecommendationEvent + AuditTrailEntry.
### D7 — Load test 10/50/100 reuniões (seção 32) + hot path × analytics
### D8 — Corrigir a corrida de DDL entre workers [CONCLUÍDA — 29/09/2026, V.1.4.147]
- `GET_LOCK` nomeado em volta de todo o DDL do startup + tratamento do
  erro 1684 + 2ª tentativa do `create_all`. Validado no MySQL real.
- Serializar `create_all()` antes do fork (achado de V.1.4.108/119).
  Pré-requisito de confiabilidade para E2E ≥ 99%.
### D12 — Restart diário terminando em timeout [CONCLUÍDA — 04/10/2026, V.1.4.163; 1º disparo do timer em 05/10 06:00 UTC]
- Resultado: o "timeout" era cosmético (resultado padrão do
  `RuntimeMaxSec`, paradas de 0-8s). O risco real era o horário andar a
  cada deploy. Timer às 03:00 BRT só sem reunião ativa, `RuntimeMaxSec`
  48h como rede de segurança e `--timeout-graceful-shutdown 25`.
  Detalhe no CHANGELOG.
- O reinício automático (`RuntimeMaxSec=86400`) das 19:00 UTC de
  28/09 terminou em `Failed with result 'timeout'` (`TimeoutStopSec=30`)
  com chamadas de IA em andamento — pode cortar requisições de reunião
  ao vivo. Avaliar: agendar o restart para madrugada (fora de horário de
  reunião, mesmo sinal de `reunioes_ativas`), aumentar o timeout de
  parada, ou graceful shutdown que espere o ciclo em curso.

### D13 — Alertas do Telegram não chegam [CONCLUÍDA — 05/10/2026, V.1.4.164; teste real 5/5 entregues]
- Causa: IPv6 intermitente VPS → Telegram + alerta de circuit breaker
  síncrono sem cooldown (travava `/tempo-real`). Fix: IPv4, thread de
  fundo, resposta conferida, 1 alerta de breaker/provedor/hora. Detalhe
  no CHANGELOG.

Achado original:
- O journal da VPS mostra `Falha ao enviar alerta Telegram: The read
  operation timed out` várias vezes por hora (ex.: 02/10 23:46-00:05
  UTC). Nenhum alerta de produção chega, inclusive o escalonamento
  humano da Fase 25 (`escalar_para_humano()`, sem cooldown). Investigar
  conectividade VPS → `api.telegram.org`, token/chat do bot e o timeout
  do cliente em `agent/alertas.py`.

### A7b — Precisão do extrator de SalesEvent [CONCLUÍDA — 05/10/2026, V.1.4.165; extrator religado em produção]
- Golden Dataset v1.2.0 (gabarito exaustivo, regras no README) + prompt
  com "conta / não conta" por tipo + limite de confiança 0,5. Golden
  completo em produção: event_precision **100%**, recall 84,6%. Detalhe
  no CHANGELOG.

Histórico da tarefa:
- `event_precision` 48,9% / recall 74,2% no Golden Dataset real (alvo
  ≥ 90%): o extrator aponta eventos demais. Ajustar o prompt
  (`sales_event_extractor.txt`) com os erros por cenário e remedir.
  Religar `SALES_EVENT_EXTRACTOR_ENABLED` na VPS (desligado em 04/10) só
  quando passar no alvo.
- **Diagnóstico feito (05/10/2026), tarefa PAUSADA aguardando decisão**:
  `scripts/sales_event_diagnostico.py --real` (40 chamadas, só o
  extrator) reproduziu 46,9% / 74,2% (23 VP, 26 FP, 8 FN). Dos 26 FP:
  - ~19-21 são **gabarito incompleto**: `expected_events` lista só o
    evento principal, mas a métrica o trata como exaustivo (ex.:
    PRICE_DISCUSSION em won-deal-01 "R$ 4.500/mês" e negotiation-02
    "pagar em 60 dias"; COMPETITOR_MENTIONED em lost-deal-01; BUYING_SIGNAL
    em negotiation-04 "topo fechar");
  - 2 são **gabarito errado**: objections-04 e pricing-04 esperam
    OBJECTION_RESOLVED, mas a conversa só revela a causa real;
  - ~5-7 são **erro real da IA**: DEAL_STALLED para hesitação
    (closing-04, good-seller-03), NEXT_STEP_AGREED só com proposta do
    vendedor (good-seller-03), CHAMPION para indicação de terceiro
    (won-deal-04), DEAL_LOST não marcado em "não temos verba esse ano"
    (lost-deal-03), PRICE_DISCUSSION citando "não é o preço"
    (bad-seller-04).
  Com gabarito completo a precisão atual seria ~85-88%. **Plano proposto**
  (não executado): gabarito v1.2.0 exaustivo nos 40 cenários com regras
  escritas no README e revisão humana das mudanças + regras no prompt
  para os 5 erros reais + nova rodada do diagnóstico.

### D9 — 6 documentos obrigatórios (seção 35) [CONCLUÍDA — 05/10/2026]
- Criados em `docs/`: SALES_BRAIN_ARCHITECTURE, SALES_SCIENCE,
  AUTONOMY_POLICY, TEST_STRATEGY, SECURITY_MODEL, DATA_DICTIONARY.
  Descrevem o código em V.1.4.164, com as lacunas conhecidas (retenção
  de dados sem job, reuniões anônimas sem dono, `/tempo-real` sem rate
  limit por IP, acesso à VPS por senha). ARCHITECTURE.md aponta para
  eles.

Pedido original:
- `SALES_BRAIN_ARCHITECTURE`, `SALES_SCIENCE`, `AUTONOMY_POLICY`,
  `TEST_STRATEGY`, `SECURITY_MODEL`, `DATA_DICTIONARY`. Nenhum existe.
### D10 — Camada `domain/`/`application/` (seção 4) [decisão]
- O prompt pede uma migração gradual; hoje tudo vive em `agent/*_rules.py`.
  Decidir se vale mover (risco de regressão alto) ou registrar que
  `agent/*_rules.py` cumpre o papel de domínio.

---

## Ordem recomendada

1. **A1** (transcrição limpa), **B1** (qualidade de dados), **D8** (DDL)
   — base de confiabilidade.
2. **A2 → A3 → A4** — dado estruturado passa a existir, zero IA nova.
3. **A5** (MEDDPICC) + **C2** (Seller DNA) → 11/11 campos.
4. **A6**, **B2** — risco e resultado reais; o Learning Loop fecha.
5. **D1** (painel de prontidão), **D4/D5** (E2E e contratos), **D6**.
6. **A7** (SalesEvent → event_precision), **D2/D3** (qualidade da IA).
7. Com volume real: **C1, C3, B4, B5, C5** → **C6** (Piloto).
8. **B3, B6, D7, D9**; **A8**; decisões **A9/D10**.

Critério de entrada no Digital Twin: os 9 critérios de D1 no alvo,
com número real (não proxy). Nenhuma tarefa começa sem confirmação
explícita, uma de cada vez — mesma disciplina de todo o roadmap.

## Registro de progresso

- **A1 — CONCLUÍDA (24/09/2026)**, V.1.4.142 + extensão V.1.4.17: 3
  causas (reenvio de delta, 2 fontes legenda/Whisper, ruído de UI/CSS),
  21,9% das linhas de 12 reuniões reais eram duplicata. Fix no backend
  (append idempotente + gate de IA pelo texto aceito) e na extensão
  (trava de envio, dedup por similaridade, filtros). Rótulo do Whisper
  do microfone continua sempre "vendedor" (eco do alto-falante pode
  atribuir fala do cliente ao vendedor quando não há legenda) —
  limitação conhecida, só resolvível com diarização (fora do escopo).
- **B1 — CONCLUÍDA (24/09/2026)**, V.1.4.143: `GET /admin/data-quality`.
  1º relatório real mudou prioridades: **0 `Opportunity` em produção**
  (P3 é o bloqueio nº 1 de Sales Science/Learning Loop — nenhuma
  oportunidade é criada automaticamente, só pelo dashboard), 98,7% das
  reuniões sem vendedor (sem login na extensão → Seller DNA/benchmark
  sem dado). Novas tarefas candidatas: **B7 — criar Opportunity
  automaticamente** (ex.: ao vincular cliente a uma reunião) e **B8 —
  incentivar/forçar login na extensão**; **C7 — estagnação de
  recomendação** (Coach repetiu a mesma pergunta de Situação por 30+
  min numa reunião real).
- **B7 — CONCLUÍDA (24/09/2026)**, V.1.4.144: `cliente_identificado` no
  PROMPT_RECAPITULACAO + `agent/auto_opportunity_rules.py` (casa/cria
  cliente, vincula reunião, reaproveita/cria oportunidade só com dono
  real). Achado: 0 clientes em produção e
  `enriquecer_perfil_apos_relatorio()` nunca chamada. Efeito real
  depende de recapitulações novas — medir com `GET /admin/data-quality`
  (`opportunities` deve deixar de ser 0/0).
- **B8 — CONCLUÍDA (28/09/2026)**, V.1.4.146 + extensão V.1.4.18:
  sessão deslizante + `auth_status` em `/tempo-real` + aviso/logout na
  extensão. O "98,7% sem vendedor" era histórico (desde 22/09: 4/4 com
  dono); o risco real era o token de 72h expirar em silêncio.
  Deploy confirmado 28/09 (~20:29 UTC). Nas 5 reuniões do dia, todos
  ainda na extensão V.1.4.15 e sem vendedor — o efeito depende da
  reinstalação da V.1.4.18. 180 recomendações novas (id > 236) já
  permitem executar a C1.
- **A2 — CONCLUÍDA (30/09/2026)**, V.1.4.148:
  `agent/sales_evidence_persist_rules.py` + wiring em Shadow/Piloto.
  Tipos `SPIN_<STAGE>:<campo>`, `BEHAVIOR:`, `MOTIVATION:`,
  `OBJECTION:`, `ROOT_CAUSE:`; dedup `(type, citação normalizada)`.
  O dado só nasce onde os extratores rodam (Shadow Mode ligado em
  produção). `speaker=None` (rótulos não confiáveis, A1). A A3 pode ler
  daqui ou direto dos extratores do ciclo.
- **A3 — CONCLUÍDA (30/09/2026)**, V.1.4.149:
  `agent/opportunity_memory_writer_rules.py` + wiring em Shadow/Piloto.
  Lê direto dos extratores do ciclo (precisa do `valor`, que a
  SalesEvidence não guarda). Categorias preenchidas: `pain_points`,
  `business_impact`, `goals`, `objections`. As outras 9 continuam sem
  escritor (sem extrator; A5 destrava champion/economic_buyer/
  decision_process/metrics). Para a A4: arestas só podem sair dessas 4
  categorias hoje (ex.: `PAIN → causa → IMPACT` entre `pain_points` e
  `business_impact`).
- **A4 — CONCLUÍDA (30/09/2026)**, V.1.4.150:
  `agent/opportunity_graph_writer_rules.py` + wiring após a A3. Regras:
  PAIN→causa→IMPACT, PAIN→motiva→GOAL, CLIENT→sente→PAIN,
  CLIENT→levanta→OBJECTION; `source="regra_memoria"`. Causa raiz e
  OBJECTION↔PAIN ficaram fora (sem vínculo na memória / sem regra
  determinística). Passo 2 da ordem recomendada fechado; a A5 destrava
  STAKEHOLDER/DECISION.
- **A5 — CONCLUÍDA (30/09/2026)**, V.1.4.151: `agent/meddpicc_extractor.py`
  (IA, feature `meddpicc.extracao`, kill-switch
  `MEDDPICC_EXTRACTOR_ENABLED`) → `meddpicc_state` real (10/11 campos).
  Liga na A2 (`MEDDPICC:<item>`) e na A3 (metrics/economic_buyer/
  champion/decision_process/competitors). **Pendentes que surgiram**:
  medir o custo real por chamada após o deploy; nós STAKEHOLDER/
  DECISION/COMPETITOR no grafo (A4) ainda não criados (ids por
  categoria ficariam ambíguos num nó STAKEHOLDER). Próximo do passo 3:
  **C2** (Seller DNA → `seller_context`, 11/11).
- **C2 — CONCLUÍDA no código (30/09/2026)**, V.1.4.152:
  `agent/seller_context_rules.py` + wiring em Shadow/Piloto + regra no
  prompt do motor (estilo, nunca eficácia). **11/11 campos ligados.**
  Falta a parte operacional: `SELLER_DNA_OBSERVACAO_ENABLED=true` no
  `.env` da VPS (no deploy). Dado real só depois de 10 reuniões do
  mesmo vendedor logado. Passo 3 fechado; próximo: passo 4 (**A6**,
  **B2**).
- **A6 — CONCLUÍDA (01/10/2026)**, V.1.4.153:
  `agent/deal_risk_signals_rules.py` + `status` MEDDPICC nos insights
  da memória + próximos passos da recapitulação em `next_steps` +
  `risks_calculados` real no Opportunity Intelligence (endpoint e
  dashboard). `COMPETITOR_ADVANTAGE` segue sem fonte (`nao_avaliados`).
  Achado: o card MEDDPICC do Opportunity Intelligence já poderia sair
  do gap (`estado_meddpicc_da_memoria()`), passo pequeno não feito.
  Próximo: **B2**.
- **B2 — CONCLUÍDA (01/10/2026)**, V.1.4.154: tabela
  `opportunity_stage_history` (o estágio não tinha histórico) +
  `agent/recommendation_outcome_rules.py` + script de qualidade de
  recomendação preenchendo os 2 sinais. Estado de uso continua não
  persistido (só em lote pelo script), então o gap de
  `recommendation_effectiveness` no endpoint de observabilidade segue.
  Passo 4 fechado; próximo: passo 5 (**D1**, D4/D5, D6).
- **D1 — CONCLUÍDA (01/10/2026)**, V.1.4.155: `GET /admin/readiness` +
  `agent/readiness_rules.py` + tabela `readiness_medicoes` + os 3
  scripts de lote registrando no `--real`. `pronto_para_digital_twin`
  exige os 9 no alvo com origem `real`. Pendente operacional: rodar os
  3 scripts após o deploy (o painel nasce com os critérios de lote
  `sem_numero`). Sem card no dashboard ainda.
- **D4 — CONCLUÍDA (01/10/2026)**, V.1.4.156:
  `tests/test_e2e_cenarios_venda.py`, com os 10 cenários. Achou um bug
  da D1 (audit coverage > 100%), já corrigido. Fica pendente para o
  critério E2E success: os testes provam o fluxo, mas o número da Fase
  25 continua o proxy de produção (1 − taxa de erro de IA). Um E2E real
  em produção exigiria monitorar reuniões completas. Próximo: **D5**,
  **D6**.
- **D6 — CONCLUÍDA (01/10/2026)**, V.1.4.157:
  `agent/intelligence_version_rules.py` + 4 colunas em
  `recommendation_events`/`audit_trail_entries` (migração automática no
  startup). Versões derivadas do conteúdo. Fora:
  `base_conhecimento` (RAG legado) não entra na `knowledge_version`.
  Passo 5 resta só a **D5**.
- **D5 — CONCLUÍDA (01/10/2026)**, V.1.4.158:
  `agent/contract_repair_rules.py`. Reparo sintático em
  `ai_router._extract_json` e contrato da sidebar no fim do
  `/tempo-real` + dentro da normalização. Registro em log, contador
  `json_reparado` e `AuditTrailEntry` `contract_guard`. Bug corrigido:
  `confidence` em texto derrubava `_nba_para_nbq`. **Passo 5 fechado.**
  Próximo: passo 6 (**A7**, **D2**, **D3**).
- **A7 — CONCLUÍDA no código (01/10/2026)**, V.1.4.159:
  `agent/sales_event_extractor.py` (14 tipos, citação literal), gravação
  em Shadow/Piloto e `event_precision` real no runner do Golden Dataset
  e no `/admin/readiness`. Decisão: uma IA para os 14 tipos, sem
  derivar das saídas A2/A5 (ver CHANGELOG). **Pendente**: rodar o Golden
  Dataset com `--real` para o 1º número (custo de IA). Próximo:
  **D2**, **D3**.
- **D2 — CONCLUÍDA no código (02/10/2026)**, V.1.4.160:
  `agent/critical_hallucination_rules.py` (número/preço, promessa, dado
  do cliente fora da entrada). Medida por cenário no Golden Dataset e
  no readiness como `real`. Atacada no prompt do motor e por guarda no
  Piloto, que bloqueia e mantém o modelo atual.
- **D3 — CONCLUÍDA no código (02/10/2026)**, V.1.4.161: o erro dos 75%
  era de gabarito (`objections-04`), corrigido no Golden Dataset
  v1.1.0. Conjunto de 30 casos (13 tipos), `objecoes_erradas` no
  relatório e desempate no prompt do classificador. **Passo 6 fechado
  no código**; pendente rodar o Golden Dataset `--real` (até 234
  chamadas) para remedir A7/D2/D3. Próximo na ordem: passo 7 (com
  volume real: C1, C3, B4, B5, C5 → C6).
- **Deploy das V.1.4.150-161 (03/10/2026)**: commit `5efcd3d` em
  produção, `SELLER_DNA_OBSERVACAO_ENABLED=true` na VPS. Todas as
  tarefas "concluídas no código" acima passam a rodar em produção. PAT
  do remote da VPS inválido (deploy via `git bundle`).
- **Golden Dataset `--real` (03/10/2026)**, após V.1.4.162 (fix de
  falsos positivos da D2): objection_classification 100% (D3 bate o
  alvo), critical_hallucination 2,5% (1 falso positivo, real 0%),
  event_precision 48,9% / recall 74,2% (A7 abaixo do alvo de 90%).
  Nova candidata: **A7b — precisão do extrator de SalesEvent**.
- **04/10/2026**: extrator de SalesEvent desligado em produção
  (`SALES_EVENT_EXTRACTOR_ENABLED=false`) até a A7b. Religar faz parte
  da A7b.
- **Análise de 16/10/2026** (pedido do usuário: "o que falta da parte de
  inteligência"): dados de produção desde o reset de 11/10 — 33 reuniões,
  **0 relatórios, 0 clientes, 0 oportunidades**, memória/grafo da
  oportunidade 0, Seller DNA 0 observações, 530 PolicyViolationEvent
  (todos alarme falso "você agora é"). Readiness: 3/9 no alvo. Ordem
  combinada: corrigir os problemas e depois **A8**.
  - **V.1.4.184** (no GitHub, aguardando deploy): detector de prompt
    injection só conta troca de persona de IA; 1 registro por (reunião,
    trechos); readiness reavalia os registros antigos.
  - **V.1.4.185** (no GitHub, aguardando deploy): relatório pós-reunião
    automático ao fim da reunião → destrava B7 (cliente/oportunidade),
    memórias, playbook, indexação e Seller DNA (C2 passa a ter dado).
    Efeito esperado: `client_profiles`/`opportunities`/
    `opportunity_memories`/`seller_dna_observacoes` deixam de ser 0 nas
    reuniões novas — conferir em `/admin/data-quality` depois do deploy.
  - **Próxima: A8** (turnos temporizados por falante) — depende de o nome
    do falante na legenda estar certo (ext 1.4.34; validação real com 2
    participantes pendente, ver CURRENT_STATE de 16/10 noite).
