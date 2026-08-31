# Auditoria — Arquitetura de Chamadas de IA e Custo

> Levantamento somente-leitura da arquitetura atual, feito como Tarefa 1 do
> prompt de desenvolvimento "Cost Intelligence, Cost Router e Controle de
> Gastos com APIs" (31/08/2026). Nenhum comportamento foi alterado nesta
> etapa. Base para o roadmap faseado em `docs/cost-intelligence-roadmap.md`.

Todos os caminhos são relativos à raiz do repositório.

---

## 1. `api/ai_router.py` — Router central

### Assinaturas
- `chamar_ia(system_prompt: str, user_content: str) -> dict` (linha 462) — síncrono.
- `chamar_ia_async(system_prompt: str, user_content: str) -> dict` (linha 610) — `await asyncio.to_thread(chamar_ia, ...)`.

**Nenhuma das duas aceita parâmetro de feature/agente/meeting_id/usuario_id** — a única informação de contexto é o texto do prompt.

### Ordem de provedores e decisão
- `DEFAULT_PROVIDER_ORDER = ("deepseek", "openai", "anthropic", "gemini")` (linha 32).
- `_provider_order()` (linha 352): 1º tenta `STATE_FILE` (`data/ai_provider_order.json`), senão env `AI_PROVIDER_ORDER`, senão o default.
- Circuit breaker por provedor: `CircuitBreaker` (linha 88-129), `FAILURES_TO_OPEN=3`, `COOLDOWN_SECONDS=60` (ambos configuráveis via env). `available` (linha 94-100) reabre após cooldown por tempo, não reseta falhas até sucesso.
- Loop principal em `chamar_ia` (linha 474-546): tenta cada provedor na ordem, pulando os com circuit breaker aberto ou sem chave; retorna no primeiro sucesso; `HTTPException(503)` (linha 551) se todos falharem.

### Chamadas por provedor (`PROVIDERS`, linha 298-327)

| Provedor | Função | SDK | Modelo padrão | API retorna uso real? | É capturado hoje? |
|---|---|---|---|---|---|
| deepseek | `_call_deepseek` (241) | `openai.OpenAI` (compatível, `base_url` custom) | `deepseek-chat` | Sim (`response.usage.prompt_tokens/completion_tokens`) | **Não** |
| openai | `_call_openai` (221) | `openai.OpenAI` | `gpt-4o` | Sim (`response.usage`) | **Não** |
| anthropic | `_call_anthropic` (258) | `anthropic.Anthropic` | `claude-sonnet-4-20250514` | Sim (`response.usage.input_tokens/output_tokens`, + cache) | **Não** |
| gemini | `_call_gemini` (279) | `google.generativeai` | `gemini-2.0-flash` | Sim (`response.usage_metadata.*`) | **Não** |

Em nenhum dos 4 provedores o token count real da API é lido — o objeto de resposta com `usage`/`usage_metadata` é descartado assim que a função extrai o texto.

### Estimativa de custo atual (linhas 65-76, 389-410)
```python
ESTIMATED_COST_INPUT_PER_MILLION = {"deepseek": 0.14, "openai": 5.0, "anthropic": 3.0, "gemini": 0.35}
ESTIMATED_COST_OUTPUT_PER_MILLION = {"deepseek": 0.28, "openai": 15.0, "anthropic": 15.0, "gemini": 1.05}

def _estimate_token_count(text):
    return max(1, int(round(len(text) / 4)))  # heurística chars/4

def _estimate_call_cost(provider_name, system_prompt, user_content, result):
    input_tokens = _estimate_token_count(f"{system_prompt}\n{user_content}")
    output_tokens = _estimate_token_count(json.dumps(result))
    return ((input_tokens * input_rate) + (output_tokens * output_rate)) / 1_000_000
```
Preços têm default hardcoded mas são sobrescrevíveis por env (`DEEPSEEK_INPUT_COST_PER_MILLION` etc.) — porém a chave é o **provedor**, não o **modelo** (ex.: `claude-sonnet-4-20250514` usa a mesma taxa genérica de "anthropic" que qualquer outro modelo Anthropic teria). Toda contagem de token é estimativa de caracteres, nunca a contagem real do SDK.

### Métricas em memória (`snapshot_metricas`/`snapshot_provedores`/`status_provedores`)
- Contadores globais **em memória** (`_counters`, linha 337-349, `threading.Lock`): `chamadas_total/sucesso/falha`, `fallbacks`, `circuit_breaker_aberturas`, `custo_total_usd`, `por_provedor[nome] = {sucesso, falha, total_ms, custo_usd}`, `inicio`.
- **Resetam a zero a cada restart** e são **por-worker** (uvicorn com múltiplos workers — sem agregação entre processos).
- Nenhuma das três funções persiste em SQLite/MySQL — é só estado de processo.

---

## 2. `api/main.py` — Endpoints que chegam (ou não) ao AI Router

`chamar_gpt()` (linha 518-520) é wrapper fino de `chamar_ia` (nome legado da era mono-provedor).

| Endpoint | Cadeia até IA |
|---|---|
| `POST /tempo-real` (621) | `processar_fragmento_tempo_real` → `orquestrador.analisar_fragmento_multi` → 4x `chamar_ia_com_fallback_claude` (coach/disc/finance/closer, paralelo) → `chamar_ia_async` → `chamar_ia`. Se `recap_trigger`: +1 chamada via `agent/recapitulacao.py::generateLiveRecapMindMap`. |
| `POST /webhook/tactiq` (677) | Background: 3x `chamar_gpt` (recapitulação, financeiro, DISC). |
| `POST /diagnostico-financeiro` (748) | `chamar_gpt` direto. |
| `POST /perfil-disc` (760) | `chamar_gpt` direto. |
| `POST /recapitulacao-completa` (772) | 3x `chamar_gpt` + background `extrair_e_salvar_memorias`/`gerar_e_salvar_playbook` (ambos `chamar_ia`). |
| `POST /recapitulacao-viva` (813) | `generateLiveRecapMindMap` → `chamar_ia_async`. |
| `POST /recapitulacao-manual` (1640) | Idêntico a `/recapitulacao-completa`. |
| `POST /cenario/{meeting_id}/conducao` (2057) | `chamar_ia_async` direto. |
| `POST /audio-transcricao` (2141) | **Fora do AI Router** — `openai.OpenAI().audio.transcriptions.create` ou `groq.Groq().audio.transcriptions.create` direto. Sem circuit breaker, sem contador, sem custo (Whisper/Groq cobram por minuto de áudio, modelo de custo diferente). |
| `POST /generate-visual-scenario` (2229) | `PainExtractor.extract` (via AI Router, custo descartado) + 2x `ImageGenerator.generate` (DALL-E 3, **fora do AI Router**, zero custo capturado). |
| `POST /base/ocr` (2590) | **Fora do AI Router** — `anthropic.AsyncAnthropic` direto com fallback manual para `openai.AsyncOpenAI`. Sem contador, sem custo. |
| `POST /claude-account/analisar` (2939) | **Fora do AI Router** — Claude Agent SDK via subprocess CLI, cobra da assinatura pessoal do vendedor. |
| `POST /admin/api/teste` (3116) | Pings diretos aos 4 SDKs, fora do router (custo real irrisório, mas zero captura). |
| `POST /playbooks/gerar/{meeting_id}` (1044) | `playbook_generator.gerar_playbook` → `chamar_ia`. |
| `POST /skills/gerar` (1232) | `skill_resolver.gerar_skill` → `chamar_ia`. |
| `POST /relatorios/{meeting_id}/followups/gerar` (1403) | `followup_generator.gerar_followups` → `chamar_ia`. |

**Achado central**: 3 famílias de chamada com custo real não passam pelo `ai_router.py` — transcrição de áudio, OCR e Claude Account Mode — nenhuma alimenta `_counters`, nenhuma tem estimativa de custo (nem char/4).

---

## 3. Tempo real e os 4 agentes multiagente

### Fluxo (`processador_tempo_real.py::analyzeRealtimeMeeting`, 442-669)
1. Carrega `MeetingMemory`; decide se pode chamar IA (`_pode_chamar_ia`, rate-limit).
2. Resolve `skill_context`/`client_context` — lookups de DB, **não chamam IA**.
3. `orquestrador.analisar_fragmento_multi`: busca RAG + Sales Memory (cada uma gera 1 embedding de consulta) e roda os 4 agentes em paralelo.
4. Se `detectRecapTrigger`: +1 chamada (`generateLiveRecapMindMap`).

### Os 4 agentes — padrão idêntico
Todos chamam `chamar_ia_com_fallback_claude(system_prompt, prompt, usuario_id)` (`agent/multiagente/claude_fallback.py:20`). `usuario_id` é o único identificador estrutural propagado hoje, e só decide o fallback Claude pessoal — não serve para atribuição de custo. **Nenhuma chamada carrega um identificador de "feature"/"agente"** até o AI Router.

**Ponto de extensão natural**: a assinatura de `chamar_ia_com_fallback_claude` já recebe um parâmetro extra (`usuario_id`) além de `(system_prompt, user_content)` — um `feature: str` poderia seguir o mesmo caminho.

### Bug estrutural — custo do tempo real sempre zerado
Cada resposta de agente chega do AI Router com `_provedor_ia`, `_modelo_ia`, `_custo_estimado_ia`, `_tokens_entrada_ia`, `_tokens_saida_ia` (`ai_router.py:524-530`). A função `orquestrador.py::_mesclar()` (68-120) monta o dict final campo a campo e **nunca copia essas chaves `_*_ia`**. O mesmo vale para `generateLiveRecapMindMap` → `_normalizar_recapitulacao_viva()`.

**Consequência**: `registrar_analise_meeting()` (`database.py:451-560`) chama `_extrair_custo_estimado(analise)` sobre o `resultado` já processado — que nunca tem as chaves candidatas — e **sempre recebe 0.0**. Isso é a única chamada a `registrar_analise_meeting` no código-fonte inteiro, e alimenta `MeetingMemory.provider_cost_estimate`, que por sua vez alimenta:
- `GET /historico/uso` — `custo_total_usd` sempre `0.0` na prática.
- `GET /historico/uso/{meeting_id}` — `custo_estimado_usd` individual sempre `0.0`.

Em contraste, os relatórios pós-reunião (`chamar_gpt` direto, sem passar por `_mesclar()`) preservam `_custo_estimado_ia` — por isso `renderUsoIa()` no dashboard mostra custo/tokens só para os 3 blocos de relatório, nunca para o tempo real.

---

## 4. Módulos de custo de IA fora do tempo real

| Módulo | Chamada de IA | Registra custo/uso hoje? |
|---|---|---|
| `agent/sales_memory.py` | `gerar_embedding()` a cada `buscar_memorias_semantico()` (inclusive dentro do loop de tempo real) + `gerar_e_salvar_embeddings_em_lote()` pós-reunião. | **Não** — `EmbeddingResult` não carrega custo/tokens. |
| `agent/playbook_generator.py` | `gerar_playbook()` → `chamar_ia`. | Soma no contador global do router; custo não persiste vinculado ao playbook. |
| `agent/followup_generator.py` | `gerar_followups()` → `chamar_ia`. | Idem. |
| `agent/skill_resolver.py` | `gerar_skill()` → `chamar_ia` (só ao criar skill). | Idem. |
| `agent/client_intelligence.py` | Nenhuma — só lookup de DB. | N/A. |
| `agent/knowledge_extractor.py` | `extrair_memorias()` → `chamar_ia`, + 1 embedding por memória extraída. | Custo do `chamar_ia` some no contador global; embeddings em lote não rastreados. |
| `services/embeddings/` | `OllamaEmbeddingProvider` (padrão) / `OpenAIEmbeddingProvider`. A resposta da OpenAI **tem** `resp.usage.total_tokens`, nunca lido. | **Não** — contrato `EmbeddingProvider` não tem conceito de custo/uso. |
| `agent/visual_scenario.py` | `PainExtractor.extract` (via router, custo descartado — filtro explícito remove chaves `_*`) + `ImageGenerator.generate` (DALL-E 3, **fora do router**, ~US$0,08–0,12/imagem, zero captura). | Não. |
| `agent/claude_account.py` | `ClaudeAccountExecutor._executar_query()` — **único ponto do sistema onde a API retorna custo REAL**: `ResultMessage.total_cost_usd`. Só é logado (`logger.info`), **nunca persistido** — nem em `ClaudeConnection` nem em `ClaudeMeetingAnalysis`. | Descartado após o log. |

---

## 5. Banco de dados

| Tabela | Campos de meeting/user/client | Campo de custo |
|---|---|---|
| `Relatorio` (`relatorio`) | `meeting_id` | — |
| `ClaudeConnection` (`claude_connections`) | `usuario_id` | — (apesar do SDK retornar `total_cost_usd`) |
| `ClaudeMeetingAnalysis` (`claude_meeting_analyses`) | `meeting_id`, `usuario_id`, `transcript_hash` | — |
| `MeetingMemory` (`meeting_memory`) | `meeting_id` — **sem `usuario_id`/`client_id`** | `provider_cost_estimate: float` — existe, mas sempre 0.0 (ver seção 3) |
| `sessoes` | `meeting_id` — sem `usuario_id`/`client_id` | — |
| `usuarios` | `id`, `plano`, `perfil` | — |
| `client_profiles` | `id` — sem dono/`usuario_id` | — |
| `client_meetings` | `client_id` + `meeting_id` | — (só `score`) |
| `sales_memories` | `source_meeting_id`, `organization_id` | — |
| `visual_scenarios` | `meeting_id` | — |

**Não existe** hoje nenhuma tabela `ai_usage_events` (confirmado por busca textual — 0 ocorrências).

---

## 6. Observabilidade existente

- **`api/metricas_historico.py`** — SQLite (`data/metricas.db`), tabela `metricas_historico`: `ts, banco_latencia, banco_modo, reunioes_ativas, reunioes_hoje, chamadas_ia, falhas_ia`. Rolling 24h, 1 snapshot/min. **Não guarda custo nem breakdown por provedor.**
- Tabela `teste_provedores` — resultado do botão "testar" do admin, sem custo.
- **OpenTelemetry** — só tracing HTTP genérico do FastAPI; nenhum span/atributo/métrica customizada de custo, tokens ou provedor de IA.
- **`GET /monitor/metricas`** — expõe `snapshot_metricas()` (`custo_total_usd`, `por_provedor[*].custo_usd`). É a **única fonte viva de custo agregado**, mas em memória, por-worker, sem filtro por período/feature/meeting/cliente.
- **Dashboard "💰 Gasto (USD)"** — lê `custo_total_usd` direto de `/monitor/metricas`. Contador cumulativo desde o restart, sem quebra por dimensão.
- **`renderUsoIa()`** — mostra custo/tokens só para os 3 blocos de relatório pós-reunião (não tempo real, pelo bug da seção 3).

---

## 7. Preços de modelo hardcoded — todas as ocorrências

Única localização no repositório inteiro: `api/ai_router.py`, linhas 65-76 (bloco `ESTIMATED_COST_INPUT_PER_MILLION`/`ESTIMATED_COST_OUTPUT_PER_MILLION`, reproduzido na seção 1). Chave é o **provedor**, nunca o **modelo** — dois modelos do mesmo provedor com preços reais diferentes usam a mesma taxa hoje.

DALL-E 3 e Whisper/Groq **não têm nenhuma tabela de preço** no código (nem hardcoded, nem via env) — não passam pela função de estimativa do router.

---

## Resumo dos achados que mais importam para o roadmap

1. **O maior volume de chamadas do sistema (tempo real) tem custo sempre zerado** — não é falta de instrumentação, é um bug de propagação já existente (`_mesclar()` descarta os metadados de custo).
2. **Nenhum provedor lê o `usage` real da própria API** — hoje 100% do custo é estimativa char/4, mesmo quando o dado real está disponível na resposta do SDK.
3. **3 vias de custo real (áudio, OCR, imagem, Claude Account) não passam pelo AI Router** e têm zero captura — inclusive uma delas (Claude Account) já recebe o custo real exato da API e o descarta após logar.
4. **Preço é por provedor, não por modelo** — impossível hoje saber quanto custa `gpt-4o` vs. um futuro modelo mais barato do mesmo provedor.
5. **Não existe nenhuma tabela de eventos de uso** — toda métrica hoje é agregado em memória, perdido a cada restart, sem correlação com `meeting_id`/`usuario_id`/`client_id`/feature.
