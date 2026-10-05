# SALEIA — Dicionário de Dados

> Seção 35 do "PROMPT MESTRE — SALE-IA V2" (Tarefa D9). Tabelas em
> **V.1.4.164** (05/10/2026). Produção: MySQL local na VPS. Local/testes:
> SQLite.
>
> - **SQLModel**: definidas em `api/database.py`, criadas por
>   `create_all()` no startup (serializado entre workers por `GET_LOCK`).
> - **SQL direto**: `CREATE TABLE IF NOT EXISTS` no módulo indicado.
>
> Classificação (C = CONFIDENTIAL, P = contém PII) segue
> [SECURITY_MODEL.md](SECURITY_MODEL.md).

## 1. Reunião e transcrição

| Tabela | Origem | Chave | Conteúdo | Classe |
|---|---|---|---|---|
| `meeting_memory` | SQLModel | `meeting_id` (único) | transcrição completa e buffer, resumo acumulado, diagnóstico atual, histórico de score, key moments, eventos (JSON, LONGTEXT), `usuario_id` (dono), `opportunity_id`, custo estimado | C, P |
| `sessoes` | `agent/sessao_manager.py` | `id` | transcrição acumulada, última análise (JSON), DISC, nº de análises | C |
| `relatorio` | SQLModel | `id` | relatório final completo em `dados_json` (recapitulação, DISC, diagnóstico financeiro) | C, P |
| `meeting_status` | `agent/playbook_generator.py` | `meeting_id` | open/closed | — |
| `visual_scenarios` | `agent/visual_scenario.py` | — | imagens do Visual Cenário (data URI) | C |

## 2. Cliente e oportunidade

| Tabela | Origem | Conteúdo | Classe |
|---|---|---|---|
| `client_profiles` | `agent/client_intelligence.py` | nome, empresa, e-mail, telefone, DISC, objeções/dores recorrentes, scores, status, dia/mês de nascimento | P |
| `client_meetings` | idem | vínculo cliente × reunião (score, data) | — |
| `opportunities` | SQLModel | `client_id`, `seller_id`, `stage` (livre), `status` (open/won/lost/abandoned), valor estimado, desfecho (valor, produto, data, ciclo, concorrente, motivo de perda) | C |
| `opportunity_stage_history` | SQLModel | append-only: cada estágio assumido e quando (B2) | — |
| `opportunity_memories` | SQLModel | 1 por oportunidade; 13 listas JSON append-only de insights (`pain_points`, `business_impact`, `goals`, `objections`, `competitors`, `decision_process`, `stakeholders`, `champion`, `economic_buyer`, `metrics`, `next_steps`, `risks`, `unknowns`), cada insight com evidência, confiança e `contradiz` | C |
| `opportunity_graph_edges` | SQLModel | aresta `from_type/from_id → to_type/to_id`, `relation`, evidência obrigatória, confiança | C |
| `followups` | `agent/followup_generator.py` | follow-up gerado (canal, mensagem, agendamento, status) | C |

## 3. Modelo canônico da venda (Fase 1)

| Tabela | Conteúdo | Observação |
|---|---|---|
| `sales_events` | `event_type` (14 tipos), `evidence_quote`, `confidence`, `source`, `speaker`, `meeting_id`, `opportunity_id`, `seller_id` | escritor ligado; desligado de 04 a 05/10/2026 durante a A7b |
| `sales_evidences` | `type` (ex.: `SPIN_PROBLEM:main_pain`, `OBJECTION:`, `MEDDPICC:<item>`), `quote`, `confidence` | dedup por tipo + citação normalizada |

## 4. Recomendação, aprendizado e vendedor

| Tabela | Conteúdo |
|---|---|
| `recommendation_events` | recomendação mostrada (`strategy`, `recommendation`, `reason`, `shown_at`), uso (`used_at`, `seller_action`), versões da inteligência (`reasoning_engine_/policy_/knowledge_/model_version`) |
| `shadow_mode_comparisons` | modelo atual × SalesReasoningEngine por ciclo: concordância, latência, custo, erro, `origem` (shadow/piloto) |
| `seller_dna_observacoes` | observação de estilo do vendedor (12 campos fechados) com citação real |
| `sales_memories` | memória comercial do Sales Brain (tipo, conteúdo, confiança, status) |
| `playbooks`, `skills` | gerados a partir de reuniões; status `approved`/`pending` |
| `graph_edges` | grafo do Sales Brain entre entidades persistidas (cliente, reunião, memória, playbook, skill) — diferente do grafo da oportunidade |

## 5. Conhecimento e RAG

| Tabela | Conteúdo |
|---|---|
| `knowledge_sources` | fonte da Biblioteca (livro/manual): arquivo, hash, texto extraído, seções |
| `knowledge_items` | item estruturado (framework, objeção, script), nasce DRAFT, só vale APPROVED; embedding + provedor/modelo/dimensão |
| `base_conhecimento` | RAG legado: transcrições/documentos + embedding |
| `semantic_index` | busca semântica de relatórios e transcrições |

Vetores só são comparados com vetores do mesmo `embedding_provider`/
`embedding_model`/`embedding_dim`.

## 6. IA, custo e qualidade

| Tabela | Conteúdo |
|---|---|
| `ai_usage_events` | 1 por chamada de IA: `feature`, provedor, modelo, tokens, custo USD, latência, sucesso, fallback (coluna de data: `criado_em`) |
| `orcamento_ia`, `planos_preco`, `auditoria_financeira` | orçamento mensal, preço por plano e auditoria das mudanças |
| `router_decisoes`, `otimizacao_decisoes` | shadow do Cost Router e das otimizações de custo (nunca influenciam a chamada real) |
| `audit_trail_entries` | auditoria: ator, ação, motivo, dados usados, modelo, versões (coluna de data: `created_at`) |
| `policy_violation_events` | detecções de prompt injection |
| `readiness_medicoes` | append-only: cada medição em lote de um critério da Fase 25 |
| `claude_connections`, `claude_meeting_analyses` | piloto da conta Claude pessoal por usuário |

## 7. Usuários

| Tabela | Conteúdo | Classe |
|---|---|---|
| `usuarios` | nome, e-mail (único), `senha_hash` (bcrypt), perfil, plano, status, token de reset + expiração | P, SENSITIVE (hash) |

## 8. Fora do MySQL

| Onde | Conteúdo |
|---|---|
| `data/metricas.db` (SQLite) | `metricas_historico` (snapshot a cada 60s, janela de 24h) e `teste_provedores` (último teste de cada provedor, compartilhado entre os 2 workers) |
| `data/base_arquivos/`, `data/biblioteca_arquivos/` | arquivos originais enviados à Base/Biblioteca |
| `data/relatorios/*.json` | cópia em disco dos relatórios |

`data/` nunca vai para o git nem é sobrescrito em deploy.
