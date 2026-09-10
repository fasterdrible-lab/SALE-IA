# SALE-IA V2 — Baseline Report (Fase 0)

> Gerado em 09/09/2026, como parte da Tarefa 0.1/0.2 do "PROMPT MESTRE —
> SALE-IA V2". Antes de qualquer código de domínio novo (SalesEvent,
> Opportunity, SPIN 2.0, etc.), esta é a fotografia da confiabilidade
> atual do sistema. Números medidos rodando `python -m unittest discover
> tests` de verdade — nunca estimados a partir de documentação antiga.

## Resumo geral

| Métrica | Valor |
|---|---|
| TOTAL | 512 |
| PASS | 511 |
| FAIL | 0 |
| SKIP | 1 |
| DURAÇÃO | ~800s (~13min) |

O "SKIP" é pré-existente e não relacionado a esta rodada (não investigado
nesta Fase 0 — não bloqueia).

## Baseline por categoria

O prompt mestre pediu 9 categorias. Uma 10ª categoria ("Sales Brain /
Multiagente") foi necessária — ~14 arquivos (28% da suíte) não cabem em
nenhuma das 9 originais, cobrindo funcionalidade que não existia quando
essas categorias foram definidas (Sales Memory, Playbooks, Skills,
Client Intelligence, Big Five, Astrologia, Observabilidade).

| Categoria | Arquivos (exemplos) |
|---|---|
| API | `test_smoke.py`, `test_base_download.py`, `test_tempo_real_auth.py`, `test_transcricao_config.py`, `test_extensao_versao_log.py`, `test_e2e_meeting_lifecycle.py` (novo) |
| MeetingMemory | `test_meeting_memory.py`, `test_realtime_memory.py`, `test_final_diagnosis.py` |
| AIRouter | `test_ai_router.py`, `test_ai_usage_events.py` |
| Embeddings | `test_embeddings.py`, `test_embeddings_semantic_ranking.py`, `test_semantic_search.py`, `test_knowledge_graph.py` |
| KnowledgeCompiler | `test_knowledge_compiler_compilation.py`, `_extraction.py`, `_integracao.py` |
| ClaudeFallback | `test_multiagente_claude_fallback.py`, `test_claude_account.py`, `test_integracao_fallback_budget.py` |
| CostIntelligence | `test_admin_costs_*.py` (4), `test_cost_aggregation.py`, `test_cost_engine.py`, `test_cost_router.py`, `test_pricing_catalog.py`, `test_fx_rates.py`, `test_budget_and_margin.py`, `test_alertas.py`, `test_otimizacao.py`, `test_anomalias_e_analise.py` |
| Extensão (Chrome) | Só cobertura server-side (`test_extensao_versao_log.py` — header `X-Extensao-Versao`). **`chrome-extension/*.js` continua 100% sem teste** — ver Achado 2. |
| Banco | Sem arquivo dedicado — comportamento testado inline (fixtures SQLite) dentro de MeetingMemory/CostIntelligence/E2E. |
| **Sales Brain / Multiagente** (10ª, não pedida mas necessária) | `test_bigfive_agent.py`, `test_orquestrador_bigfive.py`, `test_signo_solar_rules.py`, `test_sales_brain_approval.py`, `test_sales_memory.py`, `test_skill_resolver.py`, `test_next_best_question.py`, `test_propensao_rules.py`, `test_observability.py`, `test_client_intelligence_nascimento.py`, `test_perfil_astrologico_helper.py`, `test_resumo_cliente_endpoint.py`, `test_workspace_endpoints.py` |

## Smoke tests (Tarefa 0.1) — cobertura antes/depois desta rodada

| Endpoint | Antes | Depois |
|---|---|---|
| `GET /health` | ✅ | ✅ |
| `GET /dashboard` | ✅ | ✅ |
| `POST /recapitulacao-manual` | ✅ | ✅ |
| `POST /auth/login` | ❌ | ✅ (caminho de erro — sem fixture de usuário real) |
| `POST /iniciar-sessao` | ❌ | ✅ |
| Biblioteca (upload + extração) | ❌ (só funções internas) | ✅ via `TestClient` |
| `GET /busca-semantica` (RAG) | ❌ (só função interna) | ✅ via `TestClient` |
| `POST /tempo-real` | ✅ (`test_tempo_real_auth.py`) | ✅ |

## E2E de reunião completa (Tarefa 0.2)

Novo arquivo `tests/test_e2e_meeting_lifecycle.py` (6 testes) simula:
início → 3 ciclos de `/tempo-real` (um com objeção de preço) →
`MeetingMemory` acumulando corretamente (score_history/key_moments/
events crescem, transcrição sem duplicar) → `/recapitulacao-viva` lendo
a memória real da reunião → isolamento entre duas reuniões diferentes.

## Achados (por prioridade)

### 🔴 Alta — Sem controle de ownership em `meeting_id`
`MeetingMemory` não tem coluna `usuario_id`; `POST /recapitulacao-viva`
não exige autenticação nenhuma; nenhum endpoint verifica se o
`meeting_id` pertence ao usuário autenticado. **Qualquer pessoa que
souber/adivinhar o `meeting_id` de outra reunião consegue ler a
recapitulação viva daquela reunião.** Confirmado e documentado (não
corrigido) em `tests/test_e2e_meeting_lifecycle.py::
test_ACHADO_recapitulacao_viva_sem_auth_nem_ownership` — esse teste
falha (de propósito) no dia em que alguém corrigir isso, servindo de
lembrete pra atualizar este relatório.

**Risco real**: baixo-médio hoje (uso interno, uma empresa, vendedores
confiáveis) — mas `meeting_id` circula em URLs/logs e não é
criptograficamente aleatório em todos os casos. Recomendação: tratar
como tarefa própria antes de qualquer exposição multi-tenant futura.

### 🟡 Média — Extensão Chrome 100% sem teste automatizado
Zero Jest/Mocha/Playwright configurado no repo. Toda a lógica de
`chrome-extension/*.js` (captura de áudio, offscreen, sidebar) depende
só de validação manual. Não resolvido nesta rodada — criar harness de
teste JS do zero é investimento de tooling desproporcional ao resto da
Fase 0 (que é 100% Python). Fica registrado como dívida técnica.

### 🔵 Observação — Degradação de "todos os provedores fora do ar" é silenciosa
Quando os 4 provedores de IA centrais falham simultaneamente, o sistema
**não propaga erro nenhum** até o endpoint `/tempo-real` — cada um dos 5
agentes falha isoladamente dentro de `analisar_fragmento_multi`
(capturado por `_safe()`/`asyncio.gather(return_exceptions=True)`), e
`_mesclar()` monta um resultado normal com fallbacks genéricos
(`next_best_action` = "Descoberta Inicial" fixo, `maturity_score` zerado
etc.). O endpoint responde `200` com `analysis_status: "updated"` — o
vendedor recebe conteúdo genérico sem nenhum sinal de que a IA falhou.
Não é um bug (o sistema não quebra, que era o objetivo original da
degradação graciosa) — é uma lacuna de **observabilidade**: hoje não há
como o vendedor (ou um dashboard) distinguir "IA funcionou mas achou
pouco relevante dizer algo diferente" de "os 4 provedores estavam fora
do ar". Fica registrado para decisão de produto futura (ex.: um campo
`ia_degradada: bool` explícito).

## Fora de escopo desta rodada
Ver `docs/TASKS.md` (seção Fase 0) e o plano aprovado — nenhum código de
domínio (SalesEvent, Opportunity, etc.), nenhuma correção dos achados
acima, nenhuma decisão de Clean Architecture.
