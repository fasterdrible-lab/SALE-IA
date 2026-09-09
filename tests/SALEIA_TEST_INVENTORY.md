# SALEIA — Inventário Funcional e de Testes

> Gerado por auditoria manual do código real (grep + leitura de arquivos), cruzado com os 37 arquivos em `tests/*.py` (409+ funções de teste). Não reflete `CLAUDE.md`/`CHANGELOG.md` sem confirmação direta no código — onde a documentação e o código divergiram, o código venceu.
>
> Versão auditada: backend V.1.4.66 / extensão Chrome V.1.4.8 (08/09/2026).
>
> **Nota sobre duplicatas no disco**: existem cópias inteiras e obsoletas do projeto em `SALEIA/SALEIA/` e `SALEIA/SALEIA/SALEIA/` dentro do próprio repo (versões antigas de `api/main.py`, `agent/*`, etc., algumas com nomes de domínio antigos como `api.saleia.com.br`). Este inventário cobre **apenas** o código na raiz do repo (`api/`, `agent/`, `services/`, `frontend/`, `chrome-extension/`, `tests/`), que é o que roda em produção.
>
> Legenda "Possui teste?": **Sim** (existe teste que exercita a lógica real, não mock total) · **Parcial** (só uma parte do fluxo, ou só a integração é mockada) · **Não** (zero teste direto).

## 1. Endpoints HTTP (`api/main.py`, salvo indicação contrária)

| ID | Funcionalidade | Arquivos | Endpoint | Dependências | Possui teste? | Cobertura |
|----|----------------|----------|----------|---------------|----------------|-----------|
| EP-01 | Health check | `api/main.py` | `GET /health` | `api/database.py`, `api/ai_router.py` (circuit breaker) | Sim | `test_smoke.py` (`test_health_status_200`, `test_health_payload_shape`) — cobre status 200 e shape do payload. |
| EP-02 | Monitor de métricas em tempo real e histórico | `api/main.py`, `api/metricas_historico.py` | `GET /monitor/metricas`, `GET /monitor/historico` | `api/metricas_historico.py` (SQLite rolling 24h) | Não | Nenhum teste direto de `api/metricas_historico.py` nem destes 2 endpoints. |
| EP-03 | Controle manual de provedor de IA (próximo/preferido) | `api/main.py` | `POST /ai/provedor/proximo`, `POST /ai/provedor/preferido` | `api/ai_router.py` (circuit breaker, estado em memória) | Não | `test_ai_router.py` (33 testes) cobre o circuit breaker internamente, mas não os 2 endpoints HTTP que o manipulam. |
| EP-04 | **Núcleo tempo real** — ciclo de análise por fragmento de transcrição | `api/main.py`, `api/processador_tempo_real.py`, `agent/multiagente/orquestrador.py` | `POST /tempo-real` | Os 4 agentes (Coach/DISC/Finance/Closer), RAG (`base_conhecimento`, `sales_memory`, Knowledge Compiler), `skill_resolver`, `claude_fallback`, `otimizacao`, `cost_router`, `observability` | Parcial | `test_realtime_memory.py` (1 teste — só o caminho "skip" por texto insuficiente), `test_tempo_real_auth.py` (3 — resolução de `usuario_id` via JWT), `test_next_best_question.py` (20 — normalização de `next_best_action`/fallback), `test_propensao_rules.py`. Nenhum teste exercita o ciclo completo de `analisar_fragmento_multi` fim-a-fim com os 4 agentes reais. |
| EP-05 | Webhook Tactiq (pós-reunião: diagnóstico completo) | `api/main.py`, `api/webhook_tactiq.py` | `POST /webhook/tactiq` | `agent/diagnostico.py`, `agent/perfil_disc.py`, `agent/recapitulacao.py`, `agent/diagnostico_final.py`, `api/notificador.py` | Parcial | `test_final_diagnosis.py` (2 testes): 1 testa `generateFinalDiagnosis` com lógica real de normalização; 1 testa `processar_webhook_tactiq` mas com todas as 6 dependências mockadas — só valida orquestração/soma de custo, não a lógica interna de cada sub-agente. |
| EP-06 | Diagnóstico financeiro / Perfil DISC (relatório avulso) | `api/main.py`, `agent/diagnostico.py`, `agent/perfil_disc.py` | `POST /diagnostico-financeiro`, `POST /perfil-disc` | `api/ai_router.py` | Não | Nenhum teste importa `agent.diagnostico` ou `agent.perfil_disc` diretamente; só aparecem mockados em `test_final_diagnosis.py`. |
| EP-07 | Recapitulação (completa/viva/manual) | `api/main.py`, `agent/recapitulacao.py` | `POST /recapitulacao-completa`, `POST /recapitulacao-viva`, `POST /recapitulacao-manual` | `api/ai_router.py` | Parcial | `test_smoke.py` cobre só `/recapitulacao-manual` (status 200, shape, rejeição de transcrição vazia) via mock da chamada de IA. `/recapitulacao-completa` e `/recapitulacao-viva` sem teste. |
| EP-08 | Relatório HTML de reunião (view) | `api/main.py` | `GET /relatorio` | `agent/sessao_manager.py` | Não | — |
| EP-09 | Status de reunião (ganha/perdida/aberta) | `api/main.py`, `agent/playbook_generator.py` | `PATCH/GET /relatorios/{meeting_id}/status` | `agent/playbook_generator.py::atualizar_status_reuniao/obter_status_reuniao` | Não | `test_sales_memory.py` mocka a função-irmã `listar_status_reunioes`, mas não os endpoints nem `atualizar_status_reuniao`/`obter_status_reuniao`. |
| EP-10 | CRUD de Playbooks + geração a partir de reunião | `api/main.py`, `agent/playbook_generator.py` | `GET/PATCH/DELETE /playbooks`, `GET /playbooks/{id}`, `POST /playbooks/gerar/{meeting_id}` | `api/ai_router.py`, `agent/sessao_manager.py` | Não | `test_knowledge_compiler_integracao.py` testa só `gerar_playbook_de_fonte`/`mapear_knowledge_items_para_playbook` (fluxo da Biblioteca de Inteligência); `gerar_e_salvar_playbook` (a partir de reunião) e o CRUD não têm teste. |
| EP-11 | CRUD de Clientes + timeline + vínculo com reuniões | `api/main.py`, `agent/client_intelligence.py` | `GET/POST/PATCH/DELETE /clientes`, `/clientes/{id}`, `POST/DELETE /clientes/{id}/reunioes/...`, `GET /clientes/por-reuniao/{meeting_id}` | MySQL raw (`client_profiles`, `client_meetings`) | Não | Nenhum teste importa `agent.client_intelligence`. |
| EP-12 | CRUD de Skills + geração | `api/main.py`, `agent/skill_resolver.py` | `GET /skills`, `POST /skills/gerar`, `PATCH/DELETE /skills/{id}` | MySQL raw (`skills`) | Parcial | `test_skill_resolver.py` (18 testes) cobre a **resolução** (`resolver_melhor_skill`/`resolver_skills_relevantes`) sempre com `listar_skills` mockado — o CRUD real (`gerar_e_salvar_skill`, `atualizar_skill`, `deletar_skill`, `criar_tabela_skills`) não é exercitado. |
| EP-13 | Sales Memory (listar/buscar/stats) | `api/main.py`, `agent/sales_memory.py` | `GET /sales-memories`, `GET /sales-memories/buscar`, `GET /sales-memories/stats` | MySQL raw (`sales_memories`), embeddings | Parcial | `test_sales_memory.py` (13 testes) cobre só o ajuste de ranking por outcome (`_ajustar_similaridade_por_outcome`, `_status_reunioes_origem`, `buscar_memorias_semantico`) — `salvar_memoria`, `listar_memorias`, `contar_por_tipo`, `criar_tabela_sales_memories` sem teste direto. |
| EP-14 | Listagem de relatórios (dashboard) | `api/main.py` | `GET /relatorios` | `agent/sessao_manager.py`, `agent/client_intelligence.py`, `agent/playbook_generator.py::listar_status_reunioes` | Não | — |
| EP-15 | Follow-ups (gerar/listar/CRUD) | `api/main.py`, `agent/followup_generator.py` | `POST /relatorios/{id}/followups/gerar`, `GET .../followups`, `PATCH/DELETE /followups/{fid}` | `api/ai_router.py`, MySQL raw (`followups`) | Não | Nenhum teste importa `agent.followup_generator`. |
| EP-16 | Histórico de uso de IA por reunião | `api/main.py` | `GET /historico/uso`, `GET /historico/uso/{meeting_id}` | `api/database.py::AiUsageEvent` | Parcial | Coberto indiretamente por `test_cost_aggregation.py`/`test_ai_usage_events.py` (funções de agregação), mas não os 2 endpoints HTTP especificamente. |
| EP-17 | Páginas estáticas servidas (login/dashboard/manual/manual-tecnico/reset) | `api/main.py` | `GET /login`, `GET /`, `GET /dashboard`, `GET /dashboard/`, `GET /dashboard.`, `GET /manual`, `GET /manual-tecnico`, `GET /reset` | `frontend/*.html` | Parcial | `test_smoke.py` cobre só `/dashboard` (status 200, content-type, contém "SALEIA"). Os outros 6 sem teste. |
| EP-18 | Sessões (histórico de análises tempo real) | `api/main.py`, `agent/sessao_manager.py` | `GET/DELETE /sessoes`, `GET /sessoes/{id}`, `POST /iniciar-sessao`, `POST /sessoes/{id}/exportar-base` | MySQL raw (`sessoes`) | Não | `agent.sessao_manager` nunca é importado em nenhum teste. |
| EP-19 | Base de Conhecimento (RAG manual: CRUD, download, OCR) | `api/main.py`, `agent/sessao_manager.py`, `agent/base_conhecimento.py` | `GET/POST/DELETE /base`, `GET /base/{id}/download`, `POST /base/ocr` | Extração de texto (PDF/DOCX/OCR) | Parcial | `test_base_download.py` (7 testes) cobre **só** o download: auth, token inválido, content-type/nome preservado, documento sem arquivo, arquivo removido do disco. Upload (`POST /base`), listagem/deleção e `POST /base/ocr` sem teste. `agent/base_conhecimento.py::buscar_contexto_similar` (a busca RAG em si, usada em toda análise de tempo real) **sem nenhum teste direto**. |
| EP-20 | Biblioteca de Inteligência / Knowledge Compiler (upload, extração, compilação, itens, gerar skill/playbook) | `api/main.py`, `services/knowledge_compiler/` | `POST/GET /biblioteca/fontes`, `POST .../extrair`, `GET .../estimar-custo`, `POST .../compilar`, `GET .../itens`, `PATCH /biblioteca/itens/{id}`, `POST .../gerar-skill`, `POST .../gerar-playbook` | `KNOWLEDGE_COMPILER_ENABLED` (flag), extractors PDF/DOCX/HTML/TXT, embeddings | Sim | `test_knowledge_compiler_extraction.py` (18), `test_knowledge_compiler_compilation.py` (18), `test_knowledge_compiler_integracao.py` (14) — cobertura ampla de extração, compilação com IA, dedup por embedding e integração com Skill/Playbook. Endpoints HTTP em si (auth/404 quando flag off) não testados diretamente, só a lógica de negócio subjacente. |
| EP-21 | Cenário (visão do vendedor + condução por IA) | `api/main.py` | `GET /cenario/{id}`, `GET /api/cenario/{id}`, `POST /cenario/{id}/conducao` | `agent/sessao_manager.py` | Não | — |
| EP-22 | Transcrição de áudio (dispatcher OpenAI/Groq/Whisper Local) | `api/main.py::/audio-transcricao` | `POST /audio-transcricao` | `agent/whisper_local.py`, chaves OpenAI/Groq | Sim | `test_transcricao_config.py::test_audio_transcricao_dispatches_to_whisper_local` cobre o dispatch para Whisper Local; `test_whisper_local.py` (6 testes) cobre o módulo em si. Caminhos OpenAI/Groq do dispatcher sem teste direto. |
| EP-23 | Cenário Visual (geração e listagem) | `api/main.py`, `agent/visual_scenario.py` | `POST /generate-visual-scenario`, `GET /visual-scenarios/{id}`, `GET /visual-scenario` | `agent/visual_scenario.py::ScenarioComposer`, OpenAI | Não | `criar_tabela_visual_scenarios` só é mockado (no-op) em `setUp` de outros testes para evitar tocar DB real — nenhum teste exercita `ScenarioComposer` ou os endpoints. |
| EP-24 | Autenticação (login/cadastro/recuperação/redefinição de senha) | `api/main.py` | `POST /auth/login`, `POST /auth/cadastro`, `POST /auth/recuperar-senha`, `POST /auth/redefinir-senha` | JWT (PyJWT), bcrypt, `agent/email_service.py` | Parcial | `test_tempo_real_auth.py` cobre só a leitura do JWT em `/tempo-real`, não os endpoints de auth em si nem `agent/email_service.py` (zero teste). |
| EP-25 | Admin — gestão de usuários | `api/main.py` | `GET /admin/usuarios`, `PATCH .../inativar\|reativar\|resetar-senha\|perfil\|plano\|status`, `DELETE /admin/usuarios/{uid}` | `agent/sessao_manager.py` | Não | — |
| EP-26 | Claude Account Mode (piloto — conectar/status/analisar) | `api/main.py`, `agent/claude_account.py` | `GET /claude-account/status`, `POST /connect\|disconnect\|analisar`, `GET /analises/{id}`, `POST .../feedback`, `GET /admin/claude-account/metricas` | `CLAUDE_ACCOUNT_PILOT` (flag), `claude_agent_sdk` | Parcial | `test_claude_account.py` (26 testes) — todos mockam `_executar_query`/`claude_agent_sdk.query`; o próprio `CLAUDE.md` documenta que nenhum teste exercita a configuração real do `ClaudeAgentOptions` contra o SDK/CLI real (3 bugs de produção só apareceram em uso real). |
| EP-27 | Cost Intelligence — Admin Costs (resumo/por-usuário/reuniões/export) | `api/main.py` | `GET /admin/costs/resumo\|por-usuario\|reunioes\|reunioes/{id}\|export` | `api/database.py` (agregações) | Sim | `test_admin_costs_endpoints.py` (12 testes): auth (401/403), formato, export JSON/CSV, filtro de data inválida, limite respeitado. |
| EP-28 | Cost Intelligence — Budget Guard (orçamento/margem/auditoria) | `api/main.py`, `api/fx_rates.py` | `GET/PATCH /admin/costs/orcamento`, `GET /projecao`, `GET/PATCH /margem`, `.../planos/{p}/preco`, `GET /auditoria` | `OrcamentoIA`, `PlanoPreco`, `AuditoriaFinanceira` | Sim | `test_admin_costs_orcamento_endpoints.py` (8) + `test_budget_and_margin.py` (11) + `test_fx_rates.py` (5) — auth, definição de orçamento/preço, projeção, margem, auditoria. |
| EP-29 | Cost Intelligence — Cost Router (recomendação de modelo) | `api/main.py`, `api/cost_router.py` | `GET /admin/costs/router`, `GET /router/config` | `COST_ROUTER_ATIVO` (flag), `RouterDecisao` | Sim | `test_admin_costs_router_endpoints.py` (7) + `test_cost_router.py` (23) — kill-switch via env, formato, ausência de decisões, classificação de complexidade. |
| EP-30 | Cost Intelligence — Otimização (cache/contexto/loop) + anomalias | `api/main.py`, `api/otimizacao.py` | `GET /admin/costs/otimizacao`, `/anomalias`, `/analise`, `/metricas` | `OTIMIZACAO_{CACHE,CONTEXTO,LOOP}_ATIVO` (flags) | Sim | `test_admin_costs_otimizacao_endpoints.py` (11) + `test_otimizacao.py` (20) + `test_anomalias_e_analise.py` (9) — cache/TTL/LRU, corte de contexto, loop caro (429), kill-switches, anomalias. |
| EP-31 | Admin — API/Provedores de IA (chaves, teste, principal) | `api/main.py` | `GET /admin/api/provedores`, `POST .../chave`, `POST /admin/api/teste`, `PATCH .../status`, `POST /admin/api/principal` | `api/ai_router.py`, `api/metricas_historico.py` | Não | — |
| EP-32 | Admin — Embeddings (status do provedor) | `api/main.py` | `GET /admin/embeddings/status` | `services/embeddings/factory.py` | Não | O serviço em si tem teste (SVC-01), não este endpoint. |
| EP-33 | Admin — Transcrição (config/teste) | `api/main.py` | `GET/POST /admin/transcricao/config`, `POST /admin/transcricao/teste` | `agent/whisper_local.py::health_check`, chaves Groq/OpenAI | Sim | `test_transcricao_config.py` (5 testes) cobre listagem sem exigir chave para Whisper Local, ativação, bloqueio do Groq sem chave, chamada de `health_check`. |

## 2. Agentes de IA (`agent/multiagente/*.py`)

| ID | Funcionalidade | Arquivos | Endpoint | Dependências | Possui teste? | Cobertura |
|----|----------------|----------|----------|---------------|----------------|-----------|
| AGT-01 | Orquestrador (paraleliza os 4 agentes, mescla resultado, RAG compartilhado, custo do ciclo) | `agent/multiagente/orquestrador.py` | via `POST /tempo-real` | Coach/DISC/Finance/Closer, `base_conhecimento`, `sales_memory`, Knowledge Compiler RAG, `observability` | Não | Nenhum teste importa `agent.multiagente.orquestrador` diretamente — `_mesclar`, `_safe`, `_nba_para_nbq` e o `asyncio.gather` dos 4 agentes com spans de observabilidade não têm teste direto (só indiretamente via `test_realtime_memory.py`, que mocka o módulo inteiro antes de bater no caminho "skip"). |
| AGT-02 | Coach Agent (condução, rapport, próxima ação, estágio) | `agent/multiagente/coach_agent.py`, `agent/prompt_templates/multiagente_coach.txt` | via `/tempo-real` | `claude_fallback.py`, `ai_features.REALTIME_COACH` | Parcial | Só via `evals/` (Promptfoo, dev tool com custo real de IA, não roda em CI) — `evals/datasets/coach/objections_real.yaml` (34 casos reais) e `objections_fit_gap.yaml`. Nenhum teste unitário em `tests/*.py`. |
| AGT-03 | DISC Agent (perfil comportamental, KARE, temperatura) | `agent/multiagente/disc_agent.py` | via `/tempo-real` | `claude_fallback.py` | Não | Sem teste unitário nem eval dedicado (`evals/` só cobre Coach e Finance). |
| AGT-04 | Finance Agent (capacidade financeira, objeção de preço) | `agent/multiagente/finance_agent.py` | via `/tempo-real` | `claude_fallback.py` | Parcial | Só via `evals/promptfooconfig.finance.yaml` (dev tool, sem execução real registrada ainda). |
| AGT-05 | Closer Agent (score, maturidade, próximos passos) | `agent/multiagente/closer_agent.py` | via `/tempo-real` | `claude_fallback.py` | Não | Sem teste nem eval. |
| AGT-06 | Fallback para Conta Claude pessoal do vendedor | `agent/multiagente/claude_fallback.py` | via `/tempo-real` (quando os 4 provedores centrais retornam 503) | `api/ai_router.py`, `agent/claude_account.py` | Sim | `test_multiagente_claude_fallback.py` (8 testes) — acionamento em 503, não acionamento em 429, propagação de erro se fallback também falhar. |

## 3. Serviços (`services/`)

| ID | Funcionalidade | Arquivos | Endpoint | Dependências | Possui teste? | Cobertura |
|----|----------------|----------|----------|---------------|----------------|-----------|
| SVC-01 | Embeddings pluggable (Ollama/OpenAI, fallback) | `services/embeddings/` (`factory.py`, `provider.py`, `ollama_provider.py`, `openai_provider.py`) | `GET /admin/embeddings/status` | `EMBEDDING_PROVIDER`, `EMBEDDING_FALLBACK_PROVIDER` (env) | Sim | `test_embeddings.py` (26 testes) + `test_embeddings_semantic_ranking.py` (1, requer Ollama local rodando — não roda em CI puro). Boa cobertura de factory/fallback/batch. |
| SVC-02 | Observabilidade (Langfuse / NoOp) | `services/observability/` (`factory.py`, `provider.py`, `langfuse_provider.py`, `noop_provider.py`) | integrado em `/tempo-real`, `/webhook/tactiq` | `OBSERVABILITY_ENABLED`, `LANGFUSE_*` (env) | Sim | `test_observability.py` (15 testes) — trace/span/generation/retrieval/score, isolamento de `ContextVar` entre testes. |
| SVC-03 | Knowledge Compiler (extractors PDF/DOCX/HTML/TXT, sanitizer, compiler) | `services/knowledge_compiler/` (`compiler.py`, `sanitizer.py`, `schemas.py`, `extractors/*.py`) | via EP-20 | `KNOWLEDGE_COMPILER_ENABLED` (flag) | Sim | Ver EP-20 — cobertura ampla (50 testes somados entre os 3 arquivos). |

## 4. Módulos de domínio (`agent/*.py`, fora de `multiagente/`)

| ID | Funcionalidade | Arquivos | Endpoint | Dependências | Possui teste? | Cobertura |
|----|----------------|----------|----------|---------------|----------------|-----------|
| MOD-01 | `sessao_manager.py` — CRUD de sessões, usuários, base de conhecimento (tabelas raw-pymysql) | `agent/sessao_manager.py` | EP-08, EP-14, EP-18, EP-19, EP-25 | MySQL raw (`sessoes`, `usuarios`, `base_conhecimento`) | Não | Nunca importado em nenhum teste. |
| MOD-02 | `base_conhecimento.py` — busca RAG por similaridade de cosseno (cache de embeddings) | `agent/base_conhecimento.py` | usado dentro de EP-04/AGT-01 | `services/embeddings/` | Não | `buscar_contexto_similar`/`invalidar_cache` sem teste direto — é o 1º dos 3 blocos de RAG do orquestrador e não tem nenhuma cobertura. |
| MOD-03 | `client_intelligence.py` — CRUD de clientes, timeline, vínculo com reuniões, enriquecimento de perfil | `agent/client_intelligence.py` | EP-11 | MySQL raw (`client_profiles`, `client_meetings`) | Não | Zero referência em `tests/`. |
| MOD-04 | `playbook_generator.py` — geração de playbook a partir de reunião de sucesso, status ganha/perdida | `agent/playbook_generator.py` | EP-09, EP-10 | MySQL raw (`meeting_status`, `playbooks`) | Parcial | Só a fatia "Knowledge Compiler → Playbook" (`gerar_playbook_de_fonte`) é testada (`test_knowledge_compiler_integracao.py`); `gerar_e_salvar_playbook`, `_eh_reuniao_de_sucesso`, `atualizar_status_reuniao`, CRUD, sem teste. |
| MOD-05 | `skill_resolver.py` — CRUD de skills + resolução (V1 e V2) | `agent/skill_resolver.py` | EP-12, AGT-01 | MySQL raw (`skills`) | Parcial | Ver EP-12: resolução bem testada, persistência não. |
| MOD-06 | `sales_memory.py` — extração/persistência/busca de memórias comerciais | `agent/sales_memory.py` | EP-13, AGT-01 | MySQL raw (`sales_memories`) | Parcial | Ver EP-13: só o ajuste de ranking por outcome é testado. |
| MOD-07 | `followup_generator.py` — agenda inteligente + geração de follow-ups | `agent/followup_generator.py` | EP-15 | MySQL raw (`followups`), `api/ai_router.py` | Não | Zero referência em `tests/`. |
| MOD-08 | `knowledge_extractor.py` — extração de memórias ao fim da reunião | `agent/knowledge_extractor.py` | usado em EP-04 (fim de reunião) e EP-05 | `agent/sales_memory.py` | Não | Zero referência em `tests/`. |
| MOD-09 | `visual_scenario.py` — composição de cenário visual (SVG/imagem) | `agent/visual_scenario.py` | EP-23 | OpenAI | Não | `criar_tabela_visual_scenarios` só é mockado como no-op em `setUp` de outros testes (evitar tocar DB real), nunca exercitado de fato. |
| MOD-10 | `recapitulacao.py` — mapa mental de recapitulação ao vivo | `agent/recapitulacao.py` | EP-04 (trigger periódico), EP-07 | `api/ai_router.py` | Não | Zero referência direta em `tests/`. |
| MOD-11 | `email_service.py` — envio de e-mail (recuperação de senha) | `agent/email_service.py` | EP-24 | SMTP (env) | Não | Zero referência em `tests/`. |
| MOD-12 | `notificador.py` (`api/notificador.py`) — notificação pós-reunião (WhatsApp/Z-API, e-mail) | `api/notificador.py` | EP-05 | Z-API, SMTP (env) | Não | `notificar_vendedor` só aparece **mockado** em `test_final_diagnosis.py`, nunca testado de fato. |
| MOD-13 | `alertas.py` — alertas de orçamento/anomalia via Telegram | `agent/alertas.py` | usado por Cost Intelligence Fases 3/5 | Telegram Bot API | Sim | `test_alertas.py` (8 testes) — `verificar_orcamento`/`verificar_anomalia`/thresholds. |
| MOD-14 | `claude_account.py` — piloto Claude Account Mode (conectar, executar, classificar erro) | `agent/claude_account.py` | EP-26 | `claude_agent_sdk`, `CLAUDE_TOKEN_ENC_KEY` (env) | Parcial | Ver EP-26 — 26 testes, mas todos mockando o SDK. |
| MOD-15 | `propensao_rules.py` — classificação determinística de propensão de compra | `agent/propensao_rules.py` | usado em AGT-01 | nenhuma (puro) | Sim | `test_propensao_rules.py` (7 testes) — cobertura completa incluindo limiares configuráveis via env. |
| MOD-16 | `whisper_local.py` — transcrição self-hosted via `faster-whisper` | `agent/whisper_local.py` | EP-22, EP-33 | `faster-whisper` (modelo local) | Sim | `test_whisper_local.py` (6 testes). |
| MOD-17 | `diagnostico.py` — diagnóstico financeiro (legado, ainda ativo via Tactiq) | `agent/diagnostico.py` | EP-05, EP-06 | `api/ai_router.py` | Não | Só mockado em `test_final_diagnosis.py`. |
| MOD-18 | `diagnostico_financeiro.py` — arquivo separado com nome parecido a `diagnostico.py` | `agent/diagnostico_financeiro.py` | não referenciado em `api/main.py` atual | — | Não | **Achado**: existe tanto `agent/diagnostico.py` (com `diagnostico_financeiro()`, usado de fato por `webhook_tactiq.py`) quanto `agent/diagnostico_financeiro.py` (arquivo próprio) — checar se o segundo é código morto/duplicata antes de qualquer refatoração assumir que são a mesma coisa. |
| MOD-19 | `diagnostico_final.py` — diagnóstico final consolidado da reunião | `agent/diagnostico_final.py` | EP-05 | `api/ai_router.py` | Sim | `test_final_diagnosis.py::test_generate_final_diagnosis_normalizes_ai_response` testa a lógica real de normalização. |
| MOD-20 | `perfil_disc.py` — perfil DISC avulso (legado, ainda ativo via Tactiq) | `agent/perfil_disc.py` | EP-05, EP-06 | `api/ai_router.py` | Não | Só mockado em `test_final_diagnosis.py`. |
| MOD-21 | **[CÓDIGO MORTO]** `agente_tempo_real.py` — motor de análise single-agent, substituído pelo orquestrador multiagente | `agent/agente_tempo_real.py` | nenhum — `api/processador_tempo_real.py` real não o importa (confirmado por grep; só a cópia obsoleta em `SALEIA/api/processador_tempo_real.py` ainda o importa) | — | N/A | `test_realtime_memory.py` referencia o nome do módulo só para criar um `types.ModuleType` fake via `sys.modules` — nunca importa/executa o código real. |
| MOD-22 | **[CÓDIGO MORTO]** `suporte_venda.py` — geração de suporte de venda | `agent/suporte_venda.py` | nenhum — não importado em nenhum lugar de `api/` atual | — | N/A | Zero referência fora do próprio arquivo. |
| MOD-23 | **[CÓDIGO MORTO]** `api/llm_router.py` | `api/llm_router.py` | nenhum — não importado por `api/main.py` nem qualquer outro módulo ativo | — | N/A | Só existe (em uso) nas cópias obsoletas `SALEIA/api/llm_router.py`/`SALEIA/SALEIA/api/llm_router.py`. |
| MOD-24 | `ai_router.py` — roteador central de chamadas de IA (choke-point de custo/observabilidade) | `api/ai_router.py` | usado por EP-04 a EP-33 (praticamente tudo) | DeepSeek/OpenAI/Anthropic/Gemini, circuit breaker | Sim | `test_ai_router.py` (33 testes) — fallback entre provedores, circuit breaker, timeout, cálculo/registro de uso. |
| MOD-25 | `cost_engine.py` / `pricing_catalog.py` — cálculo puro de custo por chamada | `api/cost_engine.py`, `api/pricing_catalog.py` | usado por `ai_router` | — | Sim | `test_cost_engine.py` (9) + `test_pricing_catalog.py` (10). |
| MOD-26 | `fx_rates.py` — taxa de câmbio fixa USD→BRL | `api/fx_rates.py` | usado em EP-28 | `FX_USD_BRL_RATE` (env) | Sim | `test_fx_rates.py` (5 testes). |
| MOD-27 | `metricas_historico.py` — métricas rolling 24h + histórico de teste de provedores | `api/metricas_historico.py` | EP-02, EP-31 | SQLite | Não | Nenhum teste dedicado. |
| MOD-28 | `webhook_tactiq.py` — orquestração do fluxo pós-reunião Tactiq | `api/webhook_tactiq.py` | EP-05 | Tactiq API, MOD-12, MOD-17, MOD-19, MOD-20 | Parcial | Ver EP-05. |

## 5. Modelos de banco de dados

### SQLModel (`api/database.py`, MySQL via SQLAlchemy)

| ID | Tabela / Classe | Domínio | Possui teste? | Cobertura |
|----|------------------|---------|----------------|-----------|
| DB-01 | `Relatorio` | relatórios de reunião | Não | — |
| DB-02 | `ClaudeConnection` | Claude Account Mode — conexão do vendedor | Parcial | Via `test_claude_account.py` (mockado). |
| DB-03 | `ClaudeMeetingAnalysis` | Claude Account Mode — análise sob demanda | Parcial | Idem DB-02. |
| DB-04 | `MeetingMemory` | memória de contexto acumulado por reunião (tempo real) | Sim | `test_meeting_memory.py` (4 testes). |
| DB-05 | `AiUsageEvent` | evento de custo por chamada de IA (Cost Intelligence Fase 1) | Sim | `test_ai_usage_events.py` (4) + `test_cost_aggregation.py` (12). |
| DB-06 | `OrcamentoIA` | orçamento mensal de IA | Sim | `test_budget_and_margin.py`. |
| DB-07 | `PlanoPreco` | preço por plano (margem) | Sim | `test_budget_and_margin.py`. |
| DB-08 | `AuditoriaFinanceira` | log de auditoria de mudanças financeiras | Sim | `test_admin_costs_orcamento_endpoints.py::test_auditoria_lista_mudancas`. |
| DB-09 | `RouterDecisao` | decisão do Cost Router (real × recomendado) | Sim | `test_cost_router.py`. |
| DB-10 | `OtimizacaoDecisao` | decisão de cache/contexto/loop (Fase 5) | Sim | `test_otimizacao.py`. |
| DB-11 | `KnowledgeSource` | fonte de documento da Biblioteca de Inteligência | Sim | `test_knowledge_compiler_extraction.py`. |
| DB-12 | `KnowledgeItem` | item de conhecimento extraído (FRAMEWORK/OBJECTION/etc.) | Sim | `test_knowledge_compiler_compilation.py`. |

### Raw-pymysql (`CREATE TABLE IF NOT EXISTS`, sem ORM)

| ID | Tabela | Módulo dono | Possui teste? | Cobertura |
|----|--------|-------------|----------------|-----------|
| DB-13 | `client_profiles` | `agent/client_intelligence.py` | Não | 0 linhas em produção até 05/09/2026 (CHANGELOG). |
| DB-14 | `client_meetings` | `agent/client_intelligence.py` | Não | Idem. |
| DB-15 | `meeting_status` | `agent/playbook_generator.py` | Parcial | Só via mock de `listar_status_reunioes` em `test_sales_memory.py`. 0 linhas em produção até 05/09/2026. |
| DB-16 | `playbooks` | `agent/playbook_generator.py` | Não | — |
| DB-17 | `followups` | `agent/followup_generator.py` | Não | — |
| DB-18 | `skills` | `agent/skill_resolver.py` | Não (persistência) | Ver MOD-05. |
| DB-19 | `visual_scenarios` | `agent/visual_scenario.py` | Não | — |
| DB-20 | `sessoes` | `agent/sessao_manager.py` | Não | — |
| DB-21 | `base_conhecimento` | `agent/sessao_manager.py` | Não | — |
| DB-22 | `usuarios` | `agent/sessao_manager.py` | Não | Só cruzado indiretamente (auth JWT testado, não a tabela). |
| DB-23 | `sales_memories` | `agent/sales_memory.py` | Parcial | Ver MOD-06. |
| DB-24 | `metricas_historico`, `teste_provedores` | `api/metricas_historico.py` | Não | — |

## 6. Jobs / tarefas em background

> **Não há fila persistente nem scheduler (sem Celery/RQ/APScheduler/cron) no código atual.** "Background" aqui significa `fastapi.BackgroundTasks` (roda após a resposta HTTP, no mesmo processo, sem retry nem persistência de fila) ou scripts de manutenção disparados manualmente.

| ID | Job | Arquivos | Disparado por | Possui teste? | Cobertura |
|----|-----|----------|----------------|----------------|-----------|
| JOB-01 | Processamento do webhook Tactiq | `api/main.py::receber_webhook_tactiq` | `BackgroundTasks` em `POST /webhook/tactiq` | Parcial | A função-alvo (`processar_webhook_tactiq`) é testada diretamente em `test_final_diagnosis.py`, mas não o disparo via `BackgroundTasks` em si. |
| JOB-02 | Envio de recapitulação completa | `api/main.py::recapitulacao_completa` | `BackgroundTasks` em `POST /recapitulacao-completa` | Não | — |
| JOB-03 | Geração de playbook (via reunião) | `api/main.py` (~linha 1114) | `BackgroundTasks` em `POST /playbooks/gerar/{id}` | Não | — |
| JOB-04 | Geração de skill | `api/main.py` (~linha 1302) | `BackgroundTasks` em `POST /skills/gerar` | Não | — |
| JOB-05 | Recapitulação manual | `api/main.py::recapitulacao_manual` | `BackgroundTasks` em `POST /recapitulacao-manual` | Parcial | Ver EP-07. |
| JOB-06 | E-mail de recuperação de senha | `api/main.py::auth_recuperar_senha` | `BackgroundTasks` em `POST /auth/recuperar-senha` | Não | `agent/email_service.py` sem teste (MOD-11). |
| JOB-07 | Reindexação de embeddings (manutenção) | `scripts/reindex_embeddings.py` | manual (CLI) | Não | Script de operação, roda sob demanda pelo operador. |
| JOB-08 | Migração de histórico de reuniões (manutenção, one-off) | `scripts/migrar_reunioes_historico.py` | manual (CLI) | Não | Script one-off de migração. |
| JOB-09 | Verificação de configuração Cloudflare (diagnóstico de infra) | `deploy/verificar_cloudflare.py` | manual (CLI) | Não | Aparenta estar desatualizado — referencia domínio antigo (`api.saleia.com.br`) e topologia de 2 VPS, divergente do `CLAUDE.md` atual (1 VPS, `api.saleia.app.br`). |
| JOB-10 | Alerta de orçamento/anomalia (síncrono, inline no ciclo de custo — não é job separado de fato) | `agent/alertas.py` | chamado inline por `verificar_orcamento`/`detectar_anomalias_custo` | Sim | `test_alertas.py`. Listado aqui porque funciona como monitoramento contínuo, mas não há scheduler — dispara a cada gravação de custo real. |

## 7. Frontend (`frontend/*.html`)

| ID | Página | Arquivo | Servida em | Possui teste? | Cobertura |
|----|--------|---------|------------|----------------|-----------|
| FE-01 | Login | `frontend/login.html` | `GET /login` | Não | — |
| FE-02 | Dashboard (principal — custos, relatórios, config, admin) | `frontend/dashboard.html` (6100 linhas) | `GET /dashboard` | Parcial | Só `test_smoke.py` (status 200, content-type, contém "SALEIA") — nenhuma lógica JS do dashboard é testada (não há teste de frontend/JS no repo). |
| FE-03 | Cenário (visão do vendedor durante a reunião) | `frontend/cenario.html` | `GET /cenario/{id}` | Não | — |
| FE-04 | Manual do usuário | `frontend/manual.html` | `GET /manual` | Não | — |
| FE-05 | Manual técnico | `frontend/manual_tecnico.html` | `GET /manual-tecnico` | Não | — |
| FE-06 | Cenário Visual | `frontend/visual-scenario.html` | `GET /visual-scenario` | Não | — |
| FE-07 | **[possível órfão]** `painel.html` | `frontend/painel.html` | **nenhuma rota em `api/main.py` a serve** (grep não encontrou `painel.html` referenciado no roteador) | N/A | Confirmar se é resquício de versão anterior antes de assumir que está em uso ou de removê-lo. |

## 8. Chrome Extension (`chrome-extension/`)

| ID | Componente | Arquivo | Função | Possui teste? | Cobertura |
|----|------------|---------|--------|----------------|-----------|
| EXT-01 | Manifest (V3) | `manifest.json` | Permissões: `activeTab`, `storage`, `alarms`, `offscreen`, `tabs`, `tabCapture`; content script só em `meet.google.com` | N/A | Sem framework de teste JS no repo; validação só via `node --check` (sintaxe), documentado no CHANGELOG. |
| EXT-02 | Content script (captura de legendas/áudio mic, sidebar, envio para `/tempo-real`) | `content.js` (1429 linhas) | Roda na página do Meet | Não | Nenhum teste automatizado (JS não coberto por `tests/*.py`). |
| EXT-03 | Background / service worker (mensageria, `chrome.tabCapture`) | `background.js` (380 linhas) | Handler `iniciarCaptura`/`pararCaptura`, resolve `getMediaStreamId` | Não | — |
| EXT-04 | Offscreen document (captura de áudio da aba) | `offscreen.js` (110 linhas), `offscreen.html` | `chromeMediaSource: 'tab'` + reconexão via `AudioContext` | Não | CHANGELOG registra explicitamente "não testado ao vivo ainda" (V.1.4.7). |
| EXT-05 | Popup | `popup.js` (270 linhas), `popup.html` | UI de status/configuração rápida | Não | — |
| EXT-06 | Estilos (sidebar/popup/content) | `sidebar.css`, `popup.css`, `content.css` | — | N/A | — |

## 9. Feature flags (kill-switches via env)

| ID | Flag | Default | Controla | Possui teste? | Cobertura |
|----|------|---------|----------|----------------|-----------|
| FLG-01 | `CLAUDE_ACCOUNT_PILOT` | `false` | Piloto Claude Account Mode — endpoints somem via 404 quando off | Sim | `test_claude_account.py`. |
| FLG-02 | `KNOWLEDGE_COMPILER_ENABLED` | `false` | Biblioteca de Inteligência — endpoints `/biblioteca/*` somem via 404 quando off | Não | O 404/flag em si não foi encontrado testado; a lógica de negócio por trás sim (ver EP-20). |
| FLG-03 | `COST_ROUTER_ATIVO` | `true` | Cost Router (Fase 4) — recomendação/troca de modelo dentro do provedor | Sim | `test_admin_costs_router_endpoints.py::test_router_respeita_kill_switch_via_env`. |
| FLG-04 | `OBSERVABILITY_ENABLED` | `false` | Langfuse — troca `LangfuseObservabilityProvider` por `NoOpObservabilityProvider` | Sim | `test_observability.py`. |
| FLG-05 | `OTIMIZACAO_CACHE_ATIVO` | `true` | Cache de resposta de IA (Fase 5) | Sim | `test_otimizacao.py`, `test_admin_costs_otimizacao_endpoints.py`. |
| FLG-06 | `OTIMIZACAO_CONTEXTO_ATIVO` | `true` | Corte de contexto (tail-slice) | Sim | Idem. |
| FLG-07 | `OTIMIZACAO_LOOP_ATIVO` | `true` | Bloqueio de loop caro (429) | Sim | Idem. |
| FLG-08 | `OTIMIZACAO_LOOP_MAX_CUSTO_USD` | sem default (desligado) | Limite de custo acumulado por reunião | Sim | `test_otimizacao.py`. |
| FLG-09 | `OBSERVABILITY_CAPTURE_TRANSCRIPT` | `false` | Se a transcrição bruta vai para o Langfuse (vs. só tamanho) | Não | — |

## 10. Integrações externas

| ID | Integração | Papel | Módulo | Possui teste? | Cobertura |
|----|------------|-------|--------|----------------|-----------|
| INT-01 | DeepSeek | Provedor de IA primário (texto) | `api/ai_router.py` | Sim | `test_ai_router.py`. |
| INT-02 | OpenAI | Fallback de IA, embeddings opcional, transcrição Whisper API, geração de cenário visual | `api/ai_router.py`, `services/embeddings/openai_provider.py`, `api/main.py`, `agent/visual_scenario.py` | Parcial | `test_ai_router.py`, `test_embeddings.py` cobrem o roteador/embeddings; caminho de transcrição Whisper API e cenário visual sem teste. |
| INT-03 | Anthropic (Claude) | Fallback de IA central + Claude Account Mode (piloto, via `claude_agent_sdk`) | `api/ai_router.py`, `agent/claude_account.py` | Parcial | `test_ai_router.py`; `test_claude_account.py` mocka o SDK, nunca exercita o real. |
| INT-04 | Google Gemini | Fallback de IA central | `api/ai_router.py` | Sim | `test_ai_router.py`. |
| INT-05 | Groq | Transcrição de áudio (opção rápida/paga) | `api/main.py::_transcrever_via_groq` | Não | Caminho HTTP direto sem teste. |
| INT-06 | Ollama (`embeddinggemma`) | Provedor de embeddings padrão (RAG local, sem custo por chamada) | `services/embeddings/ollama_provider.py` | Sim | `test_embeddings.py`, `test_embeddings_semantic_ranking.py` (requer instância Ollama local rodando). |
| INT-07 | `faster-whisper` (local) | Transcrição self-hosted (3ª opção, sem API externa) | `agent/whisper_local.py` | Sim | `test_whisper_local.py`. |
| INT-08 | Langfuse | Observabilidade/tracing (paralelo ao Cost Intelligence) | `services/observability/langfuse_provider.py` | Sim | `test_observability.py` (mocka o SDK do Langfuse; nunca ativado em produção real — `OBSERVABILITY_ENABLED=false`). |
| INT-09 | Telegram (Bot API) | Alertas de orçamento/anomalia para o admin | `agent/alertas.py` | Sim | `test_alertas.py`. |
| INT-10 | Tactiq | Webhook de transcrição pós-reunião (fonte externa de dados) | `api/webhook_tactiq.py` | Parcial | Ver EP-05. |
| INT-11 | Z-API (WhatsApp) | Notificação pós-reunião ao vendedor | `api/notificador.py` | Não | `notificar_vendedor` só mockado em `test_final_diagnosis.py`. |
| INT-12 | SMTP (Gmail por padrão) | E-mail de recuperação de senha, notificação pós-reunião | `agent/email_service.py`, `api/notificador.py` | Não | — |
| INT-13 | Cloudflare | Proxy/DNS/SSL de infraestrutura (não é dependência do código Python em runtime) | `deploy/verificar_cloudflare.py` (script de diagnóstico, aparenta desatualizado) | Não | Não é chamada em runtime pela aplicação — só script de operação de infra. |

## 11. Principais variáveis de ambiente (sem valores)

Lista não normativa (config real está em `.env` na VPS, nunca commitado), agrupada por área:

- **IA / roteamento**: `AI_PROVIDER_ORDER`, `AI_PROVIDER_TIMEOUT_SECONDS`, `AI_PROVIDER_FAILURES_TO_OPEN`, `AI_PROVIDER_COOLDOWN_SECONDS`, `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `DEEPSEEK_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`/`GOOGLE_API_KEY`, `GEMINI_MODEL`.
- **Preço/custo (Cost Intelligence)**: `PRICE_<PROVIDER>_<MODELO>_<CAMPO>_PER_MILLION` (override por env), `FX_USD_BRL_RATE`, `COST_ROUTER_ATIVO`, `OTIMIZACAO_CACHE_ATIVO`, `OTIMIZACAO_CONTEXTO_ATIVO`, `OTIMIZACAO_LOOP_ATIVO`, `OTIMIZACAO_CONTEXTO_MAX_CHARS`, `OTIMIZACAO_LOOP_MAX_CUSTO_USD`.
- **Observabilidade**: `OBSERVABILITY_ENABLED`, `OBSERVABILITY_PROVIDER`, `OBSERVABILITY_CAPTURE_TRANSCRIPT`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_SERVICE_NAME`.
- **Embeddings/RAG**: `EMBEDDING_PROVIDER`, `EMBEDDING_FALLBACK_PROVIDER`, `EMBEDDING_TIMEOUT`, `EMBEDDING_BATCH_SIZE`, `OLLAMA_BASE_URL`, `OLLAMA_EMBEDDING_MODEL`, `OPENAI_EMBEDDING_MODEL`.
- **Transcrição de áudio**: `TRANSCRICAO_PROVEDOR`, `GROQ_API_KEY`, `WHISPER_LOCAL_MODEL`, `WHISPER_LOCAL_DEVICE`, `WHISPER_LOCAL_COMPUTE_TYPE`.
- **Claude Account Mode**: `CLAUDE_ACCOUNT_PILOT`, `CLAUDE_TOKEN_ENC_KEY`, `CLAUDE_CLI_PATH`.
- **Banco de dados**: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASS`, `DB_NAME`.
- **Auth/app**: `JWT_SECRET`, `APP_PORT`, `APP_ENV`, `APP_BASE_URL`, `BASE_URL`.
- **Tempo real (thresholds)**: `SALEIA_REALTIME_MIN_NEW_CHARS`, `SALEIA_REALTIME_MIN_NEW_WORDS`, `SALEIA_REALTIME_MIN_INTERVAL_SECONDS`, `SALEIA_REALTIME_MAX_CONTEXT_CHARS`, `SALEIA_MEMORY_BUFFER_MAX_CHARS`, `SALEIA_RECAP_TRIGGER_COOLDOWN_SECONDS`.
- **Notificações**: `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `ZAPI_INSTANCE`, `ZAPI_TOKEN`, `ZAPI_PHONE`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_VENDEDOR`, `EMAIL_FROM`.
- **Knowledge Compiler**: `KNOWLEDGE_COMPILER_ENABLED`.
- **Tactiq**: `TACTIQ_WEBHOOK_SECRET`, `TACTIQ_API_KEY`.
- **Propensão**: limiares configuráveis lidos dinamicamente por `os.environ.get(nome, padrao)` (ver `agent/propensao_rules.py`).

---

## Funcionalidades sem nenhum teste

As lacunas mais críticas — funcionalidades centrais do produto, sem nenhum teste direto (não mockado, exercitando a lógica real):

1. **RAG core (`agent/base_conhecimento.py::buscar_contexto_similar`)** — é o 1º dos 3 blocos de contexto injetados em toda análise de tempo real (junto de Sales Memory e Knowledge Compiler); zero teste. Um bug aqui degrada silenciosamente a qualidade de todas as sugestões da IA sem que nenhum teste pegue a regressão.
2. **Orquestrador multiagente fim-a-fim (`agent/multiagente/orquestrador.py::analisar_fragmento_multi`)** — o coração do produto (`POST /tempo-real`); nenhum teste roda os 4 agentes reais em paralelo e valida `_mesclar`/`_safe`, só sub-partes isoladas ou o módulo inteiro mockado.
3. **CRUD de Clientes (`agent/client_intelligence.py`)** — toda a gestão de clientes/timeline/vínculo de reuniões (`GET/POST/PATCH/DELETE /clientes/*`) sem nenhum teste.
4. **Follow-ups (`agent/followup_generator.py`)** — geração de agenda inteligente e follow-ups pós-reunião, zero teste.
5. **Notificação pós-reunião (`api/notificador.py::notificar_vendedor`)** — canal WhatsApp/e-mail que avisa o vendedor que o diagnóstico ficou pronto; só aparece mockado, nunca exercitado de fato (se quebrar, o vendedor simplesmente não é avisado, silenciosamente).
6. **`sessao_manager.py`** — módulo que hospeda as tabelas core `sessoes`/`usuarios`/`base_conhecimento` (raw-pymysql, sem ORM/migração automática) — zero teste em nenhuma das suas ~17 funções.
7. **Cenário Visual (`agent/visual_scenario.py::ScenarioComposer`)** — feature completa sem nenhum teste (só um mock de no-op de criação de tabela em outros arquivos).
8. **Diagnóstico financeiro / Perfil DISC avulsos (`agent/diagnostico.py`, `agent/perfil_disc.py`)** — usados no fluxo Tactiq pós-reunião; só aparecem mockados em `test_final_diagnosis.py`, nunca com a lógica real exercitada.
9. **E-mail de recuperação de senha (`agent/email_service.py`)** e **autenticação (`/auth/*`)** — fluxo de segurança sem teste de endpoint (só a leitura de JWT em `/tempo-real` é testada, não login/cadastro/recuperação em si).
10. **Chrome Extension inteira** (`content.js`, `background.js`, `offscreen.js`, `popup.js`) — sem qualquer framework de teste JS no repo; validação é só `node --check` (sintaxe). A captura de áudio da aba via `tabCapture` está documentada no próprio CHANGELOG como "não testada ao vivo ainda".

Achados adicionais relevantes para a auditoria (não são "lacuna de teste", mas afetam a confiabilidade deste inventário e merecem limpeza):
- **Código morto identificado**: `agent/agente_tempo_real.py`, `agent/suporte_venda.py` e `api/llm_router.py` não são importados por nenhum caminho ativo de `api/main.py`/`api/processador_tempo_real.py` — candidatos a remoção.
- **Possível frontend órfão**: `frontend/painel.html` não é servido por nenhuma rota encontrada em `api/main.py`.
- **Possível duplicata de módulo**: `agent/diagnostico.py` (com a função `diagnostico_financeiro()`, usada de fato) e `agent/diagnostico_financeiro.py` (arquivo separado, não referenciado em `api/main.py`) — mesmo nome conceitual, merece checagem antes de qualquer refatoração assumir que são a mesma coisa.
- **Cópias obsoletas do repo inteiro** em `SALEIA/SALEIA/` e `SALEIA/SALEIA/SALEIA/` (dentro do próprio diretório do projeto) — não fazem parte do sistema em produção, mas podem confundir buscas/greps futuras se não forem removidas ou pelo menos sinalizadas.
