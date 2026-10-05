# SALEIA — Arquitetura do Sales Brain

> Seção 35 do "PROMPT MESTRE — SALE-IA V2" (Tarefa D9). Descreve o que
> o código faz em **V.1.4.164** (05/10/2026). Visão geral do sistema
> (extensão, API, deploy) fica em [ARCHITECTURE.md](ARCHITECTURE.md).

## 1. Princípios

1. **Regra separada de IA.** Toda decisão que pode ser determinística
   mora em `agent/*_rules.py`: função pura, sem IA e sem banco, testável
   com dado sintético. A IA só entra para **extrair** fatos da conversa
   ou **raciocinar** sobre fatos já estruturados.
2. **Evidência antes de interpretação.** Todo fato extraído por IA
   carrega `evidence_quote`, checada literalmente contra a conversa
   (substring). Citação inventada descarta o fato.
3. **Vocabulário fechado.** A IA nunca inventa categoria: SPIN (6
   campos), MEDDPICC, 12 motivadores, 6 sinais comportamentais, 13 tipos
   de objeção, 14 tipos de SalesEvent, 9 frameworks recomendáveis.
4. **Vazio é informação.** Campo sem dado chega ao motor como `null`,
   nunca preenchido com suposição.
5. **Melhor esforço fora do caminho do vendedor.** Extração,
   persistência e Shadow Mode nunca derrubam o `/tempo-real`. Toda etapa
   tem kill-switch no `.env`.
6. **Associação, nunca causa** (ver [SALES_SCIENCE.md](SALES_SCIENCE.md)).

## 2. Ciclo de tempo real (`POST /tempo-real`, a cada ~60s)

```
extensão Chrome ──► api/main.py /tempo-real
                     │  dedup de transcrição (agent/transcript_dedup_rules.py)
                     │  api/processador_tempo_real.py (corta contexto p/ 6.000 chars)
                     ▼
        agent/multiagente/orquestrador.py::analisar_fragmento_multi()
          asyncio.gather ─► Coach │ DISC │ Finance │ Closer │ BigFive*
                     ▼
          _mesclar() ─► next_best_action, propensão, score, eventos
                     ▼
          contract guard (agent/contract_repair_rules.py) ─► sidebar
                     │
                     ├─► _rastrear_recomendacao() ─► RecommendationEvent
                     └─► Shadow Mode (create_task, fora do caminho) ou Piloto (await)
```

\* BigFive atrás de `BIGFIVE_AGENT_ENABLED`.

O vendedor vê sempre a saída do **modelo atual** (4-5 agentes),
exceto quando está no **Piloto** (Fase 24), em que vê a do
`SalesReasoningEngine` traduzida por
`pilot_rollout_rules.mapear_para_next_best_action()`.

## 3. Pipeline do SalesReasoningEngine (Shadow/Piloto)

`orquestrador._rodar_shadow_mode()` / `_aplicar_piloto_sales_reasoning()`
montam os **11 campos** de entrada e chamam
`agent/sales_reasoning_engine.py::raciocinar_async()`:

| Campo | Fonte | IA? |
|---|---|---|
| `meeting_memory` | estado ao vivo da reunião | não |
| `rag_context` | RAG + Sales Memory + Knowledge Compiler (mesmo dos agentes) | embeddings |
| `objections` | `objecao_detectada` do Finance → `objection_category_classifier` + `objection_root_cause_extractor` | sim |
| `historical_patterns` | `historical_pattern_rules` (Win/Loss do estágio da oportunidade) | não |
| `opportunity_memory` | `OpportunityMemory` da oportunidade vinculada | não |
| `opportunity_graph` | `OpportunityGraphEdge` da oportunidade | não |
| `spin_state` | `spin_extractor` → `spin_coverage_rules` | sim |
| `behavioral_signals` | `behavioral_signal_extractor` → `behavioral_signal_rules` | sim |
| `buyer_motivation` | `buyer_motivation_extractor` → `buyer_motivation_rules` | sim |
| `meddpicc_state` | `meddpicc_extractor` (citação checada) | sim |
| `seller_context` | `seller_context_rules` (SellerDNA agregado, mín. 10 reuniões) | não |

No mesmo ciclo, os **escritores** gravam o que foi extraído:

- `sales_evidence_persist_rules` → `SalesEvidence` (dedup por tipo + citação);
- `opportunity_memory_writer_rules` → `OpportunityMemory` (append-only,
  contradição registrada, nunca sobrescrita);
- `opportunity_graph_writer_rules` → arestas PAIN→IMPACT, PAIN→GOAL,
  CLIENT→PAIN, CLIENT→OBJECTION;
- `sales_event_extractor` → `SalesEvent` (14 tipos, descarta confiança
  < 0,5; precisão 100% no Golden Dataset v1.2.0 desde a V.1.4.165).

Saída do motor: `current_state`, `recommended_framework` (1 de 9),
`next_best_action`, `next_best_question`, `reason`, `confidence`,
`hypotheses`, `evidence`, `missing_information`, `avoid`.

Guardas sobre a saída:

- **alucinação crítica** (`critical_hallucination_rules`): número/preço,
  promessa ou dado do cliente fora da entrada. No Piloto, bloqueia a
  recomendação e mantém a do modelo atual;
- **contrato** (`contract_repair_rules`): JSON quase válido é reparado
  sem inventar conteúdo; inválido cai no fallback seguro;
- **auditoria**: cada chamada grava `AuditTrailEntry` com as versões da
  inteligência (`intelligence_version_rules`: hash do prompt, das
  guardas e do conhecimento aprovado).

## 4. Choke-point de IA

Todo tráfego de IA passa por `api/ai_router.py::chamar_ia` (exceto o
fallback para a conta Claude pessoal, `agent/multiagente/claude_fallback.py`,
que replica as guardas manualmente):

- ordem DeepSeek → OpenAI → Anthropic → Gemini, circuit breaker por provedor;
- anexa `FORBIDDEN_TRIGGER_RULE`, `PROMPT_INJECTION_GUARD_TEXT` e
  `ADVERSARIAL_SALES_GUARD_TEXT` a todo system prompt;
- registra `AiUsageEvent` (custo/tokens por `feature`) e
  `PolicyViolationEvent`;
- reparo sintático de JSON (`_extract_json`).

## 5. Memória e conhecimento

| Estrutura | Escopo | Onde |
|---|---|---|
| `MeetingMemory` | 1 por reunião | `api/database.py` |
| `Opportunity` + `OpportunityStageHistory` | venda (várias reuniões) | `api/database.py` |
| `OpportunityMemory` (13 categorias) | 1 por oportunidade | `opportunity_memory_rules.py` |
| `OpportunityGraphEdge` | grafo da oportunidade | `opportunity_graph_rules.py` |
| `sales_memories`, `playbooks`, `skills` | Sales Brain (aprendizado entre reuniões) | `sales_memory.py`, `playbook_generator.py`, `skill_resolver.py` |
| `knowledge_sources` / `knowledge_items` | Biblioteca (livros/manuais), item só vale após `APPROVED` | `services/knowledge_compiler/` |
| `base_conhecimento` | RAG legado (transcrições) | `base_conhecimento.py` |

Oportunidade e cliente nascem automaticamente da recapitulação
(`auto_opportunity_rules`, B7) e a reunião é vinculada por
`opportunity_link_rules` quando há exatamente uma oportunidade aberta.

## 6. Kill-switches (`.env`)

| Variável | Padrão | Produção (05/10/2026) |
|---|---|---|
| `SHADOW_MODE_ENABLED` | false | **true** |
| `PILOT_MODE` (`off`/`pilot_user`/`5pct`…`100pct`) | off | **off** |
| `SALES_EVENT_EXTRACTOR_ENABLED` | true | true (religado em 05/10/2026) |
| `SELLER_DNA_OBSERVACAO_ENABLED` | false | **true** |
| `MEDDPICC_EXTRACTOR_ENABLED`, `SALES_EVIDENCE_PERSIST_ENABLED`, `OPPORTUNITY_MEMORY_WRITE_ENABLED`, `OPPORTUNITY_GRAPH_WRITE_ENABLED`, `SELLER_CONTEXT_ENABLED`, `AUTO_OPPORTUNITY_ENABLED`, `RECOMMENDATION_TRACKING_ENABLED`, `BIGFIVE_AGENT_ENABLED`, `SALES_BRAIN_AUTOPILOT_ENABLED` | true | padrão |
| `KNOWLEDGE_COMPILER_ENABLED` | false | não verificado |

Mudar um flag exige restart do `saleia` (ler `reunioes_ativas` antes).

## 7. Prontidão para o Digital Sales Twin

`GET /admin/readiness` (`readiness_rules.py`) mostra os 9 critérios da
Fase 25 com valor, alvo e origem (`real`/`proxy`/`gap`). Estado e
números atuais: [CURRENT_STATE.md](CURRENT_STATE.md).
