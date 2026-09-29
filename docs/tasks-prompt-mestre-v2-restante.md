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

### A2 — Persistir SalesEvidence a partir dos extratores existentes [zero IA nova]
- Os extratores de SPIN/sinais/motivação/causa raiz já produzem
  `evidence_quote` validada literalmente contra a conversa, e hoje ela
  é descartada após o ciclo. Gravar como `SalesEvidence`
  (`criar_sales_evidence()`, Fase 1.2, nunca chamada).
- **Cuidado**: deduplicar entre ciclos (a mesma fala reaparece a cada 60s).
- **Kill-switch**: `SALES_EVIDENCE_PERSIST_ENABLED`.
- **Teste**: reunião de 3 ciclos → N evidências únicas, sem duplicata.

### A3 — Escritor de OpportunityMemory [zero IA nova, depende de A2]
- Quando a reunião tem `opportunity_id` (Tarefa 3.1), gravar os fatos
  do ciclo nas categorias de `OpportunityMemory` (`pain_points`,
  `objections`, `champion`…), com append-only + contradição (Fase 2.1).
- **Efeito**: `opportunity_memory` deixa de vir vazio no
  SalesReasoningEngine.
- **Teste**: 2 reuniões na mesma oportunidade → memória acumulada;
  valor divergente → `contradiz` preenchido, nada apagado.

### A4 — Escritor de OpportunityGraph [determinístico, depende de A3]
- Arestas `PAIN → causa → IMPACT` etc. derivadas dos insights gravados
  em A3 (regras fixas por categoria, nunca IA).
- **Teste**: exemplo literal da Fase 2.2 reproduzido com dado do ciclo.

### A5 — Extrator de MEDDPICC [IA nova, desbloqueia a Tarefa 1.1]
- Mesmo padrão de `spin_extractor.py`: vocabulário fechado dos 8 itens,
  `evidence_quote` obrigatória e checada por substring. **Não mexe no
  prompt do Closer** (a razão do bloqueio original).
- **Efeito**: `meddpicc_state` real → **10/11 campos**.
- **Teste**: guarda contra citação fabricada; custo por chamada medido.

### A6 — Sinais reais para Deal Risk [determinístico, depende de A3/A5]
- `NO_NEXT_STEP` (próximo passo registrado na recapitulação),
  `HIGH_PRICE_RESISTANCE` (contagem de objeções PRICE já classificadas),
  `STALE_OPPORTUNITY` (dias desde a última reunião vinculada). Só
  `COMPETITOR_ADVANTAGE` não tem fonte e segue como gap explícito.
- **Efeito**: `risks_calculados` do Opportunity Intelligence deixa de
  ser gap.

### A7 — Extrator de SalesEvent [IA nova, desbloqueia event_precision]
- Classifica trechos nas 14 categorias de `SALES_EVENT_TYPES`, com
  evidência. Pode reaproveitar saídas de A2/A5 para parte dos tipos.
- **Teste**: rodar contra `expected_events` do Golden Dataset (Fase 20)
  → primeiro número real de `event_precision`.

### A8 — Turnos temporizados por falante [extensão + backend]
- Pré-requisito de Conversation Metrics/Seller Coaching (talk ratio,
  perguntas, monólogos). Depende de A1.
- **Teste**: transcrição conhecida → métricas batendo o cálculo manual.

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

### B2 — Capturar `stage_advanced` e `opportunity_result` [determinístico, depende de P3]
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

### C8 — Calibrar recommendation_quality com rótulos humanos [novo, 29/09/2026]
- Rotular ~50 pares (recomendação, fala nova) como usado/parcial/
  ignorado e ajustar os limiares (hoje 0,55/0,35, nunca calibrados) —
  e avaliar comparar só com falas do vendedor. Sem isso,
  `recommendation_quality` não serve como critério da Fase 25.
### C2 — Ligar Seller DNA [flag + wiring, Tarefa 5.1 → 6.1]
- `SELLER_DNA_OBSERVACAO_ENABLED=true` em produção + agregação ligada
  em `seller_context` → **11/11 campos** (junto com A5).
### C3 — Avaliar o Shadow Mode (Tarefa 6.2) [leitura, depende de P2]
- Relatório agreement/latency/errors/cost por origem, com o contexto
  completo. Define se o Piloto pode começar.
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

### D1 — Painel único de prontidão [determinístico]
- `GET /admin/readiness` com os 9 critérios, o valor atual, o alvo e a
  origem do número (real, proxy ou gap). Substitui medições manuais.
### D2 — Definir "hallucination crítica" e atacar os casos
- Separar as críticas (inventar preço, promessa ou dado do cliente) das
  demais; medir as críticas isoladamente contra ≈ 0.
### D3 — Objection classification 75% → 90%
- Analisar os erros no Golden Dataset e ajustar o prompt/regra; remedir.
### D4 — Suíte E2E dos 10 cenários (seção 30)
- Hoje existe 1 arquivo de ciclo de vida. Cobrir: ganha, perdida por
  preço, perdida por concorrente, várias reuniões, troca de decisor,
  objeção falsa de preço, indeciso, provider fora, RAG fora, prompt
  injection. Mock de IA, persistência real.
### D5 — Contract tests com reparo controlado (seção 29)
- Resposta inválida de LLM: rejeitar → reparar → registrar → fallback
  seguro. Garantir que JSON quebrado nunca chegue à sidebar.
### D6 — Versionamento completo da inteligência (seção 34)
- Hoje só `prompt_version`/`rule_version`. Adicionar
  `reasoning_engine_version`, `policy_version`, `knowledge_version`,
  `model_version` em RecommendationEvent + AuditTrailEntry.
### D7 — Load test 10/50/100 reuniões (seção 32) + hot path × analytics
### D8 — Corrigir a corrida de DDL entre workers [CONCLUÍDA — 29/09/2026, V.1.4.147]
- `GET_LOCK` nomeado em volta de todo o DDL do startup + tratamento do
  erro 1684 + 2ª tentativa do `create_all`. Validado no MySQL real.
- Serializar `create_all()` antes do fork (achado de V.1.4.108/119).
  Pré-requisito de confiabilidade para E2E ≥ 99%.
### D12 — Restart diário terminando em timeout [infra, achado 28/09/2026]
- O reinício automático (`RuntimeMaxSec=86400`) das 19:00 UTC de
  28/09 terminou em `Failed with result 'timeout'` (`TimeoutStopSec=30`)
  com chamadas de IA em andamento — pode cortar requisições de reunião
  ao vivo. Avaliar: agendar o restart para madrugada (fora de horário de
  reunião, mesmo sinal de `reunioes_ativas`), aumentar o timeout de
  parada, ou graceful shutdown que espere o ciclo em curso.

### D9 — 6 documentos obrigatórios (seção 35)
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
