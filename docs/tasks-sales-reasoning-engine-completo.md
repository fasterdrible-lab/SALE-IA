# Tasks: SalesReasoningEngine plenamente funcional

## Contexto

O `agent/sales_reasoning_engine.py::raciocinar_async()` (Fase 7 do
"PROMPT MESTRE - SALE-IA V2", V.1.4.85) espera 11 campos de entrada
(`meeting_memory`, `opportunity_memory`, `opportunity_graph`,
`spin_state`, `meddpicc_state`, `buyer_motivation`, `objections`,
`behavioral_signals`, `rag_context`, `seller_context`,
`historical_patterns`), mas hoje (Fase 23/24, V.1.4.119-120) só 2
tem dado real no ciclo de `/tempo-real`: `meeting_memory` (parcial) e
`rag_context`. Os outros 9 campos ficam sempre vazios porque os
motores que os calculam (Fases 3, 4, 5, 6, 13, 15) sao funcoes puras
ja prontas, mas nenhuma delas e alimentada com fato extraido de
transcricao real.

Objetivo deste plano: fechar esses 9 gaps, um de cada vez, sempre
testando antes de avancar. Cada tarefa exige confirmacao explicita do
usuario antes de comecar - mesma disciplina de toda fase anterior do
roadmap (ver CLAUDE.md).

Ordem recomendada: Bloco 1 -> Bloco 2 -> Bloco 3 -> (decisao de custo)
-> Bloco 4 -> Bloco 5 -> Bloco 6.

---

## Bloco 1 - Ganho rapido (reaproveitar dado ja calculado, sem IA nova)

### Tarefa 1.1 - Traduzir maturity_score (Closer) em fatos parciais de MEDDPICC

**BLOQUEADA (20/09/2026)**: investigacao antes de codar confirmou que
`agent/prompt_templates/multiagente_closer.txt` so pede numeros
(`budget_identificado: 0-15` etc.), nunca a citacao literal que
justificou o numero. `meddpicc_rules.py` exige `evidence_quote` real
pra qualquer fato sair de UNKNOWN - sem citacao real disponivel, geral
o fato seria fabricar evidencia. Usuario confirmou pular esta tarefa
por agora (nao mudar o prompt do Closer, que roda em producao real,
sem decisao separada pra isso) e comecar pela Tarefa 1.2, que tem
evidencia real disponivel. Reabrir esta tarefa exige decidir antes:
mudar o prompt do Closer pra capturar citacao, ou aceitar outro
formato de evidencia.


O `agent/multiagente/closer_agent.py` ja calcula a cada ciclo:
`dor_identificada`, `impacto_quantificado`, `urgencia_identificada`,
`budget_identificado`, `decisores_mapeados`,
`valor_verbalizado_cliente`, `proximo_passo_claro` -
`resultado["maturity_score"]` em `agent/multiagente/orquestrador.py`.
Isso e um MEDDPICC parcial calculado de graca, sem chamada de IA
extra.

Arquivos:
- Criar `agent/maturity_para_meddpicc_rules.py` (funcao pura)
- Modificar `agent/multiagente/orquestrador.py` (passar o resultado
  como `meddpicc_state` na entrada do piloto/shadow mode)

Reutilizacao:
- Reaproveitar `agent/meddpicc_rules.py::calcular_qualificacao_meddpicc()`
  (Fase 4.1) - a traducao so monta os fatos de entrada, nunca
  reimplementa a logica de agregacao.
- Reaproveitar `resultado["maturity_score"]` ja calculado pelo Closer,
  sem tocar no agente.

Dependencias:
- Nenhuma nova.

Cenarios (testes):
- `maturity_score` com `budget_identificado=1` gera fato MEDDPICC
  `metrics`/`economic_buyer` (conforme mapeamento definido) com status
  avancado.
- `maturity_score` zerado nao gera nenhum fato (nunca inventa
  confianca sem sinal real).
- Sem `evidence_quote` real disponivel (maturity_score nao carrega
  texto da fala), decidir explicitamente: ou usar um texto padrao
  neutro documentado como limitacao, ou nao gerar o fato - decisao a
  tomar no inicio da tarefa, nao no meio.
- Teste de integracao: `montar_registro_shadow()`/`_aplicar_piloto_
  sales_reasoning()` recebem o `meddpicc_state` preenchido sem
  quebrar.

### Tarefa 1.2 - Traduzir objecao_detectada (Finance) em fato de objecao [CONCLUIDA - 20/09/2026]

`agent/multiagente/finance_agent.py` ja detecta objecao a cada ciclo
(`resultado["objecao_detectada"]`), com a citacao real
(`objecao_detectada.objecao`, "transcricao da objecao").

**Achado durante a investigacao (antes de codar)**: a citacao real
existe, mas o Finance **nunca classifica a categoria** (PRICE/VALUE/
BUDGET/etc.) - sem categoria, `objection_rules.py` recusa o fato (mesmo
problema estrutural da Tarefa 1.1, em outro campo). Diferente da 1.1,
aqui o usuario confirmou resolver com **1 chamada de IA nova, pequena
e barata** (so escolhe 1 de 13 categorias fechadas) - sai do escopo
original "zero IA nova" do Bloco 1, mas ainda e bem mais barato que os
extratores completos do Bloco 4.

Arquivos:
- Criado `agent/objection_category_classifier.py` (IA, so a
  classificacao de categoria)
- Criado `agent/objecao_detectada_para_objection_rules.py` (funcao
  pura `montar_objection_spoken()` + orquestracao
  `extrair_objecao_do_ciclo()`)
- Criado `agent/prompt_templates/objecao_categoria_classificacao.txt`
- Modificado `api/ai_features.py` (`OBJECTION_CATEGORIA_
  CLASSIFICACAO`)
- Modificado `agent/multiagente/orquestrador.py` (`_aplicar_piloto_
  sales_reasoning()`/`_rodar_shadow_mode()`/`_agendar_shadow_mode()`
  passam a montar `entrada["objections"]`)

Reutilizacao:
- Reaproveitado `agent/objection_rules.py::OBJECTION_TIPOS`/
  `registrar_objecao()` (Fase 6.1) - so a parte `objection_spoken`,
  nunca a investigacao de causa raiz (isso fica pra Tarefa 4.4).
- Reaproveitado o mesmo caminho de IA de producao
  (`chamar_ia_com_fallback_claude`).

Dependencias:
- Nenhuma nova (mesmos 4 provedores de sempre).

Cenarios (testes) - 33 testes novos, todos passando:
- Objecao detectada com categoria classificada com sucesso vira
  registro `objection_spoken` valido (`tests/test_objecao_detectada_
  para_objection_rules.py`).
- Objecao com categoria fora do vocabulario fechado, ou sem
  classificacao (`category: null` da IA) - nunca quebra, vira `None`
  (gap, nunca um valor forcado) (`tests/test_objection_category_
  classifier.py`).
- Sem objecao detectada no ciclo, `objections` fica `None` (nunca
  chama a IA de classificacao a toa).
- Falha real de IA na classificacao (4 provedores + fallback
  esgotados) propaga, mas o chamador (`orquestrador.py`) trata como
  melhor esforco - nunca derruba o ciclo real.
- Testes de integracao em `tests/test_orquestrador_shadow_mode.py`/
  `tests/test_orquestrador_piloto.py` confirmando que `entrada
  ["objections"]` chega preenchido no `raciocinar_async()` real quando
  o Finance detecta objecao.

---

## Bloco 2 - Conectar o que ja esta pronto e so falta ligar

### Tarefa 2.1 - Alimentar historical_patterns via Sales Science Engine

`agent/sales_science_engine.py` (Fase 13) ja consolida os 7
submodulos estatisticos. So falta buscar os insights relevantes pra
oportunidade atual (por estagio/produto) e passar como entrada do
SalesReasoningEngine.

Arquivos:
- Modificar `agent/multiagente/orquestrador.py` (buscar insight
  relevante quando ha `opportunity_id` vinculado)

Reutilizacao:
- Reaproveitar `agent/sales_science_insights_rules.py::
  montar_sales_science_insights()` (Fase 22/bloco 3) - nunca
  recalcular estatistica aqui.

Dependencias:
- Requer que a reuniao tenha `opportunity_id` vinculado (ver Bloco 3)
  para saber qual estagio/produto filtrar - sem isso, `historical_
  patterns` continua vazio mesmo com a Tarefa 2.1 pronta.

Cenarios (testes):
- Com `opportunity_id` vinculado e amostra estatistica suficiente,
  `historical_patterns` vem preenchido com o insight real.
- Sem amostra suficiente (`amostra_suficiente=False`), vem `None` -
  nunca fabrica sinal.
- Sem `opportunity_id` vinculado, vem `None` direto, sem tentar
  buscar nada.

---

## Bloco 3 - Ligar reuniao a Oportunidade automaticamente

### Tarefa 3.1 - Vinculo automatico meeting<->opportunity

Hoje `api/database.py::vincular_meeting_opportunity()` existe mas
nunca e chamada automaticamente (Fase 18.1: "sem endpoint").

Arquivos:
- Modificar `api/processador_tempo_real.py` (ou local a definir) para
  disparar o vinculo automatico

Reutilizacao:
- Reaproveitar `vincular_meeting_opportunity()` ja existente, sem
  reescrever.
- Reaproveitar `api/database.py::listar_opportunities(client_id=...,
  status="open")` pra achar candidatos.

Dependencias:
- Precisa do `client_id` da reuniao ja identificado (ja existe hoje
  via `client_intelligence.py`).

Cenarios (testes):
- Reuniao com exatamente 1 oportunidade aberta do mesmo cliente ->
  vincula sozinha.
- Reuniao com 2+ oportunidades abertas do mesmo cliente -> nao
  vincula automaticamente (ambiguidade), fica registrado como
  pendente de vinculo manual.
- Reuniao sem oportunidade nenhuma pro cliente -> nao quebra, segue
  sem vinculo.
- Reuniao ja vinculada anteriormente -> nunca sobrescreve o vinculo
  existente.

---

## Bloco 4 - Extracao real por IA (a parte mais cara)

Cada tarefa abaixo e independente das outras - podem ser priorizadas
em qualquer ordem dentro do bloco. Todas seguem o mesmo formato: 1
chamada de IA nova (a decidir se cada uma e uma chamada separada ou
se da pra consolidar mais de uma no mesmo prompt, por custo) que le a
conversa e produz fatos estruturados com evidencia real.

### Tarefa 4.1 - Extrator de SPIN

Arquivos:
- Criar `agent/spin_extractor.py` (chamada de IA) +
  `agent/prompt_templates/spin_extractor.txt`
- Modificar `agent/multiagente/orquestrador.py`

Reutilizacao:
- Reaproveitar `agent/spin_coverage_rules.py::calcular_cobertura_
  spin()`/`SPIN_CHECKLIST_PADRAO` (Fase 3) - o extrator so produz os
  fatos de entrada, a cobertura continua calculada pela regra pura ja
  existente.
- Reaproveitar o mesmo caminho de IA de producao
  (`chamar_ia_com_fallback_claude`).

Dependencias:
- Nenhuma nova (usa os mesmos 4 provedores de sempre).

Cenarios (testes):
- Exemplos "golden" (trecho de conversa conhecido -> fato SPIN
  esperado), pelo menos 1 por estagio (situation/problem/implication/
  need_payoff).
- Conversa sem nenhum sinal SPIN claro -> extrator nao inventa fato
  nenhum.
- Guarda automatica: toda `evidence_quote` produzida precisa ser um
  trecho que realmente existe na transcricao recebida (checagem
  literal de substring, nunca so "parece plausivel").
- Teste de custo: medir tokens/custo real por chamada antes de decidir
  ativar em producao.

### Tarefa 4.2 - Extrator de sinais comportamentais

Arquivos:
- Criar `agent/behavioral_signal_extractor.py` +
  `agent/prompt_templates/behavioral_signal_extractor.txt`

Reutilizacao:
- Reaproveitar `agent/behavioral_signal_rules.py::detectar_sinais()`
  (Fase 5.2) - vocabulario fechado de 6 sinais ja definido.

Dependencias:
- Nenhuma nova.

Cenarios (testes):
- Mesmo padrao golden examples + guarda de evidence_quote da Tarefa
  4.1.
- Guarda contra alegacao pseudocientifica ja existente em
  `behavioral_signal_rules.py` continua validando a saida do extrator
  tambem (reaproveitada, nao duplicada).

### Tarefa 4.3 - Extrator de motivacao do comprador

Arquivos:
- Criar `agent/buyer_motivation_extractor.py` +
  `agent/prompt_templates/buyer_motivation_extractor.txt`

Reutilizacao:
- Reaproveitar `agent/buyer_motivation_rules.py::validar_hipoteses_
  motivacao()`/`motivacao_dominante()` (Fase 5.1).

Dependencias:
- Nenhuma nova.

Cenarios (testes):
- Golden examples + guarda de evidence_quote.
- Guarda arquitetural ja existente (DISC nunca e tratado como
  motivacao) continua valendo pro extrator tambem.

### Tarefa 4.4 - Investigacao de causa raiz de objecao (completa a 1.2)

Arquivos:
- Modificar `agent/objecao_detectada_para_objection_rules.py`
  (Tarefa 1.2) ou criar extrator separado pra causa raiz

Reutilizacao:
- Reaproveitar `agent/objection_rules.py::precisa_investigar()`/
  `registrar_objecao()` (Fase 6.1) - a regra que proibe "Esta caro" ->
  desconto automatico continua sendo a mesma, sem duplicar.

Dependencias:
- Depende da Tarefa 1.2 ja estar funcionando (objection_spoken real).

Cenarios (testes):
- Reproduzir o exemplo proibido do prompt mestre ("Esta caro." com
  confianca 100% e mesma evidencia do spoken) - extrator real nunca
  pode cair nesse padrao proibido.
- Objecao com hipotese de causa raiz distinta e evidencia propria ->
  aceita.

---

## Bloco 5 - Perfil do vendedor (SellerDNA)

### Tarefa 5.1 - Persistir observacoes por vendedor ao longo do tempo

Arquivos:
- Criar tabela `SellerDnaObservacao` (ou similar) em `api/database.py`
- Modificar fluxo pos-reuniao (mesmo ponto onde Sales Memory e
  extraida automaticamente) para acumular observacoes por vendedor

Reutilizacao:
- Reaproveitar `agent/seller_dna_rules.py::construir_seller_dna()`
  (Fase 15.1), incluindo a exigencia de amostra minima (10 reunioes)
  ja implementada.

Dependencias:
- Precisa de varias reunioes do mesmo vendedor acumuladas - nao da
  pra testar em producao com 1 reuniao so.

Cenarios (testes):
- Com menos de 10 reunioes do vendedor, perfil nao e gerado (gap
  explicito, sem clonar personalidade de poucas conversas).
- Com 10+ reunioes, perfil reflete padroes agregados reais.
- Guarda contra alegacao de eficacia (Tarefa 15.2, ja existente)
  continua validando as observacoes novas tambem.

---

## Bloco 6 - Reconectar tudo e revalidar

### Tarefa 6.1 - Wiring completo dos 11 campos

Arquivos:
- Modificar `agent/multiagente/orquestrador.py::_agendar_shadow_
  mode()`/`_aplicar_piloto_sales_reasoning()` pra montar a entrada
  completa usando os Blocos 1-5.

Reutilizacao:
- Reaproveitar toda a infraestrutura de Shadow Mode (Fase 23) e
  Piloto (Fase 24) ja construida - so a montagem da `entrada` muda.

Dependencias:
- Blocos 1-5 completos (ou pelo menos os que forem priorizados).

Cenarios (testes):
- Teste de integracao confirmando que os 11 campos chegam preenchidos
  (ou `None` explicito quando de fato nao ha dado) na chamada de
  `raciocinar_async()`.
- Nenhuma regressao nos testes existentes de Shadow Mode/Piloto
  (mocks precisam ser atualizados pra nova assinatura de entrada).

### Tarefa 6.2 - Rodar o Shadow Mode de novo com contexto completo

Sem codigo novo - e observacao. Deixar `SHADOW_MODE_ENABLED=true`
rodando por um periodo com o contexto completo e comparar `agreement_
rate`/`latency_ms_media`/`cost_usd_total` antes e depois do Bloco 6.1
(usando o campo `origem` e a data de deploy pra separar as duas
janelas).

Cenarios (validacao, nao teste automatizado):
- Comparar amostra manual de recomendacoes antes/depois do wiring
  completo - confirmar que ficaram mais especificas, nao so
  estatisticamente "concordantes".

### Tarefa 6.3 - Reavaliar o Piloto

Decisao de produto, nao tarefa tecnica. So comeca com nova
confirmacao explicita do usuario, depois de revisar o resultado da
Tarefa 6.2.

---

## Registro de progresso

- **Tarefa 1.1 (MEDDPICC via maturity_score)**: BLOQUEADA (20/09/2026)
  - sem citacao real disponivel no maturity_score do Closer. Ver nota
  na propria tarefa acima.
- **Tarefa 1.2 (objecao via Finance)**: CONCLUIDA (20/09/2026) - com
  ajuste de escopo confirmado (1 chamada de IA nova pra classificar
  categoria). `entrada["objections"]` agora tem dado real no ciclo de
  tempo real, junto de `meeting_memory`/`rag_context` - 3 dos 11 campos
  do SalesReasoningEngine preenchidos.

Atualizar esta secao (e o CHANGELOG.md/CLAUDE.md/docs/
CURRENT_STATE.md, mesmo padrao do resto do projeto) a cada tarefa
concluida.
