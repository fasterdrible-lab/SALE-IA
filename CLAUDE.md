# SALEIA — Instruções para Claude Code

## Leia sempre ao iniciar uma conversa

1. **[CHANGELOG.md](CHANGELOG.md)** — Registro completo de tudo implementado
2. **[docs/CURRENT_STATE.md](docs/CURRENT_STATE.md)** — Estado atual, infraestrutura, pendências

## Contexto do projeto

**SALEIA** é um assistente de vendas com IA para Google Meet.
- Backend: FastAPI + Python 3.14, porta 8000
- Frontend: HTML/JS vanilla (login.html, dashboard.html, cenario.html, manual.html, visual-scenario.html)
- Banco: MySQL local na VPS (`127.0.0.1`, ~2ms)
- VPS: `37.27.214.33` (Hetzner CPX32, Helsinki) — serviço `saleia.service` (systemd)
- Domínio: `api.saleia.app.br`
- Repo: `https://github.com/fasterdrible-lab/SALE-IA.git` branch `main`
- Versão atual: **V.1.4.84** (backend, local — ainda não deployada; produção confirmada em V.1.4.75) · extensão Chrome **V.1.4.14** (`chrome-extension/manifest.json`, versionada separadamente)
- Usuário admin: `phpos35@gmail.com`

## Deploy

```bash
cd /opt/saleia && git pull origin main && systemctl restart saleia
```

Não sobrescrever em deploy: `.env`, `venv/`, `data/`, `logs/`

## Regras importantes

- Nunca commitar `.env`, `data/saleia.db`, `data/metricas.db` ou PDFs com nomes de clientes
- Nunca expor chaves de API no frontend
- Frontend usa `fetchJsonWithFallback(path, init)` que retorna um `Response` — sempre chamar `.json()` depois
- Extensão Chrome: após qualquer mudança em `chrome-extension/`, precisa ser reinstalada manualmente no browser
- Extensão Chrome (desde V.1.4.40): sidebar/popup só mostram o que ajuda o vendedor durante a reunião — nada de URL do backend, nome/modelo de provedor de IA ou score numérico; isso fica só no Dashboard

## Stack técnica

| Camada | Tecnologia |
|---|---|
| API | FastAPI + Uvicorn (Python 3.14) |
| Auth | JWT (PyJWT) + bcrypt |
| IA | DeepSeek → OpenAI → Anthropic → Gemini (fallback chain) |
| RAG | NumPy cosine similarity + provedor pluggable (`services/embeddings/` — Ollama/`embeddinggemma` local por padrão, OpenAI `text-embedding-3-small` opcional) |
| Banco | MySQL local (PyMySQL) |
| Frontend | HTML/CSS/JS vanilla, sem framework |
| Deploy | Hetzner VPS + Nginx + Certbot SSL + Cloudflare |
| Observabilidade | SQLite rolling 24h + OpenTelemetry → Grafana Cloud Tempo |

## Arquitetura do Motor de Análise (V.1.4.28, propensão desde V.1.4.40)

O endpoint `POST /tempo-real` retorna:
- `next_best_action` — ação consultiva recomendada (tipo: question/insight/warning/next_step)
- `conversation_stage` — estágio SPIN atual (abertura → compromisso)
- `kare_type` — classificação da conta (keep/attain/recapture/expand)
- `maturity_score` — maturidade da oportunidade (0-100, 7 critérios)
- `score_compra` — score de compra interno (0-100) — usado para diagnóstico e persistido, mas **não é mais exibido na extensão** (ver `propensao`)
- `propensao` — `{nivel}` alta/media/baixa/nao_determinada, derivado deterministicamente de `score_compra.valor` via `agent/propensao_rules.py` (sem chamada de IA extra); é o campo que a sidebar da extensão exibe
- `next_best_question` — alias de backward compat para extensões antigas

O detalhamento da propensão (fatores, evidências, o que falta para avançar) é gerado uma única vez por `PROMPT_RECAPITULACAO` (`api/main.py`) ao final da reunião — não em tempo real — e consumido pelo Dashboard.

## Piloto Claude Account Mode (V.1.4.44+)

Cada vendedor conecta a própria assinatura Claude via `claude setup-token` (dashboard → Configurações → card "Claude (piloto)"). Ponto único de execução: `agent/claude_account.py::ClaudeAccountExecutor`.

- **Isolamento de credencial**: o `claude_agent_sdk` monta o ambiente do subprocesso CLI herdando *todo* o `os.environ` do `saleia.service` — sem limpar `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` explicitamente em `options.env`, o piloto cobraria da conta central (Claude Code prioriza essas variáveis sobre `CLAUDE_CODE_OAUTH_TOKEN`).
- **Sem ferramentas de verdade**: usar `tools=[]`, não `allowed_tools=[]` — este último só remove pré-aprovação, não torna as ferramentas indisponíveis (doc do SDK). Só `allowed_tools=[]` faz o modelo tentar usar o conjunto padrão, cair em permissão negada e esgotar `max_turns`.
- **Sem expiração programada por tempo**: `agent/claude_account.py::_levantar_erro_classificado` distingue por conteúdo da mensagem de erro, não por timer — `RateLimitEvent`/padrão de limite → `USAGE_LIMIT_REACHED` (conexão continua `ativo`, só a janela de uso da assinatura esgotou, como em qualquer outro projeto Claude Code); padrão de auth (`401`/`expired`/`invalid token`/etc.) → `AUTH_REQUIRED` (marca `expirado`, exige reconectar).
- **Token colado deve ser sanitizado de whitespace em qualquer posição** (`re.sub(r"\s+", "", ...)`, não só `.strip()`) — copiar um token longo de um terminal com quebra de linha pode inserir um espaço no meio, que corrompe o token silenciosamente (conecta com 200 OK, só a análise revela o problema).
- Todos os 26 testes de `tests/test_claude_account.py` mockam `_executar_query`/`claude_agent_sdk.query` — nenhum exercita a configuração real do `ClaudeAgentOptions` contra o SDK/CLI de verdade. Os 3 bugs acima só apareceram no primeiro uso real de produção (22/08/2026).

### Fallback no tempo real (V.1.4.49)

A extensão Chrome pode opcionalmente logar (`/auth/login`, mesmo endpoint do Dashboard) — login é sempre opcional, quem não loga continua 100% anônimo como antes. Quando logado, `POST /tempo-real` resolve `usuario_id` via JWT e o repassa por toda a cadeia (`processador_tempo_real.py` → `orquestrador.py` → os 4 agentes). Se os 4 provedores centrais se esgotarem (`HTTPException(503)` de `api/ai_router.py`), `agent/multiagente/claude_fallback.py::chamar_ia_com_fallback_claude` tenta a conta Claude pessoal do usuário antes de desistir — só como fallback, nunca substitui os 4 centrais no caminho normal (evita drenar a janela de uso de 5h da assinatura a cada ciclo de 60s). Se o fallback também falhar, relança a exceção original, preservando a degradação graciosa já existente (`orquestrador.py::_safe()`).

**Limitação conhecida (achado em incidente real, 31/08/2026)**: o servidor não consegue distinguir "vendedor com extensão desatualizada" de "vendedor com extensão atualizada mas sem login" — a única pista era a ausência do header `Authorization`, que ocorre nos dois casos. Ver `X-Extensao-Versao` (V.1.4.50) abaixo.

### Versão da extensão nos logs (V.1.4.50)

Toda chamada da extensão ao backend (`fetchBackend`, `/audio-transcricao`, heartbeat de `/health`) envia `X-Extensao-Versao: <manifest.version>`. `api/main.py::_CorrelationMiddleware` lê esse header em qualquer rota (não só `/tempo-real`) e expõe via `_ext_ver_var` (`ContextVar`, mesmo padrão do `cid` de correlação) — todo log JSON estruturado (`_JsonFormatter`) ganha o campo `ext_ver`. Durante um incidente, `journalctl -u saleia | grep ext_ver` mostra imediatamente se a extensão do vendedor está desatualizada, sem precisar perguntar a ele.

## Cost Intelligence (Fases 1-6, V.1.4.51-1.4.60 — roadmap completo)

Sistema de custo de IA de ponta a ponta: captura → visibilidade →
controle financeiro → roteamento observacional → otimização (ativa) →
polimento final. Roadmap original de 60 tarefas (nunca salvo em arquivo
— só o resumo por fase em `~/.claude/plans/misty-yawning-unicorn.md`,
que já foi todo implementado). Auditoria inicial read-only em
`docs/cost-intelligence-audit.md` (Fase 1, hoje só valor histórico — o
estado real está neste documento).

**Onde cada fase mora:**

| Fase | O que faz | Arquivos principais |
|---|---|---|
| 1 — Fundação | Captura custo real por chamada | `api/pricing_catalog.py`, `api/cost_engine.py`, `api/database.py::AiUsageEvent`, `api/ai_features.py` |
| 2 — Agregações | Dashboard de custos | `api/database.py::custos_resumo`/`custos_por_usuario`/`custos_reunioes_mais_caras`, endpoints `GET /admin/costs/*` |
| 3 — Budget Guard | Orçamento, FX, margem, auditoria | `api/fx_rates.py`, `api/database.py::OrcamentoIA`/`PlanoPreco`/`AuditoriaFinanceira`, `agent/alertas.py::verificar_orcamento` |
| 4 — Cost Router | Recomendação de modelo (**ATIVA desde V.1.4.61**) | `api/cost_router.py`, `api/database.py::RouterDecisao` |
| 5 — Otimização | Cache/contexto/loop (**ATIVA desde V.1.4.60**) | `api/otimizacao.py`, `api/database.py::OtimizacaoDecisao`, `detectar_anomalias_custo` |
| 6 — Observabilidade | Polimento final | `GET /admin/costs/metricas`, logger `saleia.financeiro` |

Tudo isso vive atrás de `/admin/costs/*` (`_req_admin`) e na aba
**Custos** do Dashboard, com um accordion **"Orçamento de IA"** em
Configurações pra editar limite/preços de plano.

### Fundação (Fase 1)
- **`api/pricing_catalog.py::obter_preco(provider, model)`** — preço por
  *modelo*, com fallback e override por env (`PRICE_<PROVIDER>_
  <MODELO>_<CAMPO>_PER_MILLION`).
- **`api/cost_engine.py::calcular_custo(...)`** — cálculo puro;
  `estimar_usage(...)` é o fallback char/4 usado só quando o provedor
  não devolve tokens reais.
- **`api/ai_router.py::chamar_ia`/`chamar_ia_async`** — `feature`/
  `meeting_id`/`usuario_id` keyword-only, leem o `usage` real de cada
  SDK. **Este é o único choke-point** por onde passa ~100% do custo de
  IA do sistema — é onde as Fases 4 e 5 penduram seus hooks de shadow
  mode (ver abaixo).
- **`api/database.py::AiUsageEvent`** (`ai_usage_events`) — um registro
  por chamada. Gravação é sempre melhor esforço.
- **Limitação conhecida**: nomes de campo de cache do DeepSeek/Gemini
  não validados contra resposta real (degradam pra `0`); Claude Account
  fallback não expõe contagem de tokens, só custo agregado.

### Budget Guard, FX e margem (Fase 3)
- Orçamento mensal (`OrcamentoIA`) e preço por plano (`PlanoPreco`)
  começam **sempre `null`/desativado** — nunca um valor inventado; o
  admin configura pelo Dashboard.
- `api/fx_rates.py::usd_para_brl` — taxa fixa (`FX_USD_BRL_RATE`, default
  5.40), **sem** API de câmbio externa (decisão deliberada — o projeto
  não tem nenhuma outra dependência de rede opcional desse tipo).
- Toda mudança de orçamento/preço grava em `AuditoriaFinanceira` E loga
  em `saleia.financeiro` (ver Fase 6).

### Cost Router — **ATIVA em produção desde V.1.4.61** (Fase 4)
**Decisão confirmada explicitamente pelo usuário em 04/09/2026**, depois
de rodar em shadow mode desde a Fase 4 original (V.1.4.57) com 20
decisões registradas mostrando 100% de concordância — não porque o
router "acerta sempre", mas porque **todo o tráfego real hoje passa só
pelo DeepSeek**, que não tem variante *economy* configurada
(`MODELOS_ECONOMY` só tem `openai`/`anthropic`). **Ativar é hoje
efetivamente inerte** na prática — só passa a ter efeito real quando o
saldo central de OpenAI/Anthropic voltar (ver incidente de saldo/chave
inválida documentado no CHANGELOG desde 31/08/2026).
- `api/cost_router.py::modelo_a_usar` — substitui de verdade o modelo
  usado dentro do provedor que já venceu a chamada real (nunca mexe em
  ordem/escolha de provedor, circuit breaker ou fallback), recomendando
  por complexidade da tarefa (`classificar_complexidade`) × modo
  `normal`/`economy`/`critical` (derivado do % de orçamento gasto).
- **Kill-switch**: `COST_ROUTER_ATIVO` (env, default `true`) — `false`
  no `.env` da VPS + `systemctl restart saleia` volta ao modelo padrão
  configurado, sem reverter deploy.
- Hook em `chamar_ia`, dentro de `try/except Exception: pass` — uma
  falha aqui é invisível pra chamada de IA real, caindo pro modelo
  padrão de sempre.
- `api/cost_router.py::registrar_decisao` grava a comparação real ×
  recomendado em `RouterDecisao` pra auditoria — como o router agora
  aplica a própria recomendação, `model_real` já nasce igual a
  `model_recomendado` na maioria das linhas (`concordou≈true`,
  `economia_estimada_usd≈0` por linha — esperado, não é bug). A
  pergunta real de negócio ("quanto o router está economizando") já é
  respondida sem código novo pela quebra `por_model` que `custos_resumo`
  (Fase 2) expõe, assim que tráfego real começar a usar
  `gpt-4o-mini`/`claude-3-5-haiku`.

### Otimização — **ATIVA em produção desde V.1.4.60** (Fase 5)
**Decisão confirmada explicitamente pelo usuário em 04/09/2026**, depois
de rodar em shadow mode desde V.1.4.58 (mesmo sem nenhuma decisão
registrada no shadow ainda — o usuário pediu a ativação mesmo assim).
Diferente de todo o resto do Cost Intelligence, **este módulo muda o
resultado real de chamadas de IA**:
- `api/otimizacao.py::buscar_no_cache`/`guardar_no_cache` — cache de
  resposta (`OrderedDict` em memória, chave sha256 de `feature+prompt+
  conteúdo`, TTL 10min, LRU 500 entradas). Hit → `chamar_ia` devolve o
  resultado cacheado (`_cache_hit_ia: true`) **sem chamar nenhum
  provedor**.
- `api/otimizacao.py::aplicar_corte_contexto` — corta só `user_content`
  (nunca `system_prompt` — cortar instruções quebraria formato de
  saída), tail-slice até `OTIMIZACAO_CONTEXTO_MAX_CHARS` (default
  20000).
- `api/otimizacao.py::verificar_loop_caro` — levanta `HTTPException(429)`
  (**nunca 503** — `agent/multiagente/claude_fallback.py` só aciona o
  fallback pra Conta Claude pessoal em 503 especificamente; 429 bloqueia
  de verdade sem drenar a assinatura pessoal do vendedor) quando
  `OTIMIZACAO_LOOP_MAX_CUSTO_USD` (**sem default — desligado até
  configurar**) e o custo acumulado da reunião já passou do limite.
- **Kill-switch por mecanismo**: `OTIMIZACAO_{CACHE,CONTEXTO,LOOP}_ATIVO`
  (env, default `true` cada) — qualquer um vira `false` no `.env` da VPS
  + `systemctl restart saleia` pra desligar sem reverter deploy.
  `GET /admin/costs/otimizacao` expõe o estado atual dos 3.
- Todos os hooks em `chamar_ia` isolam falhas *inesperadas* em
  `try/except Exception: pass` (nunca podem quebrar uma chamada real) —
  **exceto** o `HTTPException(429)` de `verificar_loop_caro`, que é o
  próprio mecanismo funcionando e precisa propagar.
- **Achado durante a ativação**: `chamar_ia.resetar_estado_ia_para_
  testes()` precisou passar a limpar o cache de `api/otimizacao.py`
  também — sem isso, testes que reusam `system_prompt`/`user_content`
  genéricos (comum em `tests/test_ai_router.py`) vazavam resultado
  cacheado de um teste pro outro, já que o cache agora é real e ativo
  por padrão.
- `detectar_anomalias_custo` (Fase 5) compara custo médio por `feature`
  entre janelas de 7 dias; `agent/alertas.py::verificar_anomalia` avisa
  no Telegram (cooldown 1h por feature) — isso continua puramente
  analítico, não muda comportamento.

### Observabilidade final (Fase 6)
- `GET /admin/costs/metricas` — contrato único consolidando resumo/
  router/otimização/anomalias, pensado pra apontar uma ferramenta
  externa (painel Grafana via JSON, script) sem bater em 4 endpoints.
- `logging.getLogger("saleia.financeiro")` (em `api/database.py` e
  `agent/alertas.py`) — filho de `"saleia"`, herda o `_JsonFormatter` de
  graça. `journalctl -u saleia | grep saleia.financeiro` mostra toda
  mudança de orçamento/preço de plano e todo alerta de orçamento/
  anomalia, sem precisar de acesso ao MySQL.

### Runbook rápido
- **Configurar orçamento/preço de plano**: Dashboard → Configurações →
  "💰 Orçamento de IA".
- **Alerta de orçamento/anomalia no Telegram**: checar `GET /admin/
  costs/orcamento` (`pct_usado`) ou `GET /admin/costs/anomalias`; o
  `journalctl | grep saleia.financeiro` tem o mesmo dado sem precisar de
  login.
- **Ver o que o Cost Router está fazendo de verdade** (Fase 4, ativa):
  `GET /admin/costs/router` (ou o card correspondente na aba Custos) —
  `ativo` mostra o kill-switch, `economia_potencial_usd` continua
  estimativa (não dinheiro realmente economizado, ver nota acima sobre
  `concordou`/`economia` ficarem quase tautológicos uma vez ativo).
- **Ver o que a Otimização *já fez* de verdade** (Fase 5, ativa): `GET
  /admin/costs/otimizacao` — `ativo` mostra os 3 kill-switches,
  `economia_potencial_total_usd` é economia real (cache/loop) ou
  estimada com precisão (corte de contexto, via `cost_engine`).
- **Desligar o Cost Router (Fase 4) em emergência**: `COST_ROUTER_
  ATIVO=false` no `.env` da VPS + `systemctl restart saleia`.
- **Desligar uma otimização da Fase 5 em emergência**: `OTIMIZACAO_
  CACHE_ATIVO=false` (ou `_CONTEXTO_`/`_LOOP_`) no `.env` da VPS +
  `systemctl restart saleia` — não precisa reverter o deploy.

## Observabilidade — Langfuse (Fase 1 do PROMPT MESTRE, V.1.4.62)

Camada de tracing/debugging **paralela** ao Cost Intelligence acima —
nunca calcula custo, só visualiza (em trace/span) o que
`api/cost_engine.py`/`api/ai_router.py` já calcularam. Existe porque
`PROMPT MESTRE — EVOLUÇÃO DA SALEIA.txt` (arquivo solto na raiz do repo,
fora de `SALEIA/`) descreve um roadmap de 10 fases de evolução da
SALEIA. Status em 05/09/2026: **Fase 1** (Langfuse/Observabilidade) e
**Fase 4** (Biblioteca de Inteligência, já existia antes com outro nome)
concluídas; **Fase 2** (Promptfoo, `evals/`) tem harness completo e uma
execução real validada (ver seção própria abaixo); **Fase 3** (Meetily —
captura/transcrição local) tem o Whisper Local self-hosted e a captura
de áudio da aba implementados (V.1.4.63/extensão V.1.4.7), mas **sem**
as abstrações formais `MeetingCaptureProvider`/`TranscriptionProvider`
do roadmap original (decisão deliberada, ver seções próprias). **Fase 5**
(Skill Resolver V2) tem `resolver_skills_relevantes()` implementada e
testada (V.1.4.65), mas **não plugada em produção** ainda (ver seção
própria). **Fase 6** (Retrieval V2 híbrido) tem a TAREFA 6.4 (outcome
won/lost no ranking de Sales Memory) implementada e ativa em produção
desde V.1.4.66 (ver seção própria) — resto da fase (client_profiles/
client_meetings) segue bloqueado por falta de dado real. **Fase 7**
(Agent Router por evento) e a maior parte da **Fase 8** (Pilot Analytics
completo) **não foram iniciadas** — antes de assumir que uma peça desse
roadmap existe, grepe o código, não confie só nesta nota.

- **`services/observability/`**: `ObservabilityProvider` (interface:
  `start_trace`/`end_trace`/`start_span`/`end_span`/`record_generation`/
  `record_retrieval`/`record_score`), `LangfuseObservabilityProvider`
  (só backend suportado hoje), `NoOpObservabilityProvider` (padrão —
  `OBSERVABILITY_ENABLED=false`, zero import de `langfuse`, zero chamada
  de rede). `get_observability_provider()` (`factory.py`) é o único
  ponto que módulos de negócio devem chamar — nunca instanciar os
  providers diretamente. Chamadores nunca cacheiam a instância (chamam
  inline dentro do próprio `try/except Exception: pass`).
- **ContextVar, não parâmetro explícito**: `_current_observation`
  (`provider.py`) carrega "qual trace/span está ativo agora" através de
  fronteiras `asyncio.gather`/`asyncio.to_thread` sem precisar mudar a
  assinatura de `chamar_ia`/`analisar_fragmento_multi` — cada um cria
  automaticamente uma cópia de contexto por Task/thread, isolando os 4
  agentes (Coach/DISC/Finance/Closer) entre si. **Cuidado em teste**: um
  `start_trace`/`start_span` sem o `end_*` correspondente vaza pro
  próximo teste da mesma classe (achado real, corrigido na V.1.4.62 —
  ver `tests/test_observability.py::setUp` resetando incondicionalmente
  via `self.addCleanup(_current_observation.set, None)`).
- **Onde cada instrumentação mora**: trace por ciclo de `/tempo-real`
  (`api/main.py`), generation por chamada de IA — sucesso/cache hit/
  falha total (`api/ai_router.py::chamar_ia`, único choke-point,
  ~100% do tráfego de IA passa por aqui inclusive `chamar_ia_async`),
  span por agente + retrieval de RAG/Sales Memory/Knowledge Compiler
  (`agent/multiagente/orquestrador.py::analisar_fragmento_multi`), span
  de skill resolvida (`agent/skill_resolver.py::resolver_skill_context`
  — candidatos considerados, selecionada, prioridade, DISC, score,
  estágio), generation do fallback pra Conta Claude pessoal
  (`agent/multiagente/claude_fallback.py` — só esse ramo respondeu de
  verdade quando os 4 provedores centrais falharam, por isso também
  precisa aparecer como generation, não só como `AiUsageEvent`).
- **`OBSERVABILITY_CAPTURE_TRANSCRIPT`** (`.env`, default `false`): quem
  decide incluir a transcrição bruta no trace é o chamador
  (`api/main.py`), não o provider — por padrão só o tamanho em
  caracteres vai pro Langfuse, nunca a conversa real do cliente sem
  decisão explícita.
- **Dashboard mínimo — decisão de reuso, sem UI nova**: "custo por
  agente" e "agente mais caro" já existem sem código novo — as 4
  features `realtime.coach`/`realtime.disc`/`realtime.finance`/
  `realtime.closer` (`api/ai_features.py`) já aparecem na tabela "Por
  Feature" da aba Custos (`custo_por_reuniao`/`custos_resumo`, Cost
  Intelligence Fases 1-2); reuniões/latência/chamadas/fallbacks/erros/
  provider já estão na aba Monitor. Construir um card de observabilidade
  paralelo duplicaria dado já servido.
- **Kill-switch**: `OBSERVABILITY_ENABLED=false` no `.env` (padrão) volta
  pro `NoOpObservabilityProvider` sem reverter deploy — mesmo padrão dos
  kill-switches do Cost Intelligence Fases 4-5.
- **Ainda não ativado em produção**: ninguém criou uma conta Langfuse
  nem decidiu ligar `OBSERVABILITY_ENABLED=true` de fato — decisão de
  produto separada da conclusão técnica da Fase 1.

## Skill Resolver V2 — início da Fase 5 do PROMPT MESTRE (`agent/skill_resolver.py`, V.1.4.65)

`resolver_skills_relevantes()` (novo) — substitui o conceito de "1
skill vencedora" por 3 grupos: `{"primary", "supporting" (max 2),
"cases" (max 1)}`. **Não plugado em produção** — `resolver_melhor_skill()`/
`resolver_skill_context()` continuam sendo o único caminho ativo em
`api/processador_tempo_real.py`, sem nenhuma mudança de comportamento
real ainda.

- **Só 4 dos 11 triggers novos do roadmap foram implementados**
  (`buying_signal`, `budget_status`, `decision_maker_status`, `urgency`)
  — são os únicos com sinal estruturado real hoje
  (`key_moments`/`eventos` com `type="buying_signal"`; Closer::
  `maturity_score.budget_identificado`/`.decisores_mapeados`/
  `.urgencia_identificada`). Os outros 7 (`objection_type`, `pain_type`,
  `product`, `segment`, `competitor`, `meeting_type`, `risk`) não são
  classificados por nenhum agente hoje — antes de adicioná-los como
  trigger, alguém precisa construir a extração desse sinal primeiro
  (provavelmente um novo agente ou campo no Closer/Finance).
- **Backward-compatible por design**: os triggers novos são chaves
  opcionais (`requires_buying_signal` etc.) em `triggers` — skill que não
  declara a chave não tem restrição nenhuma. As 5 skills builtin/
  customizadas de hoje não usam nenhuma delas, então continuam batendo
  exatamente igual a antes (confirmado sem mock, `primary` bateu 100% com
  `resolver_melhor_skill()` em 3 cenários reais).
- **"cases"** são skills geradas a partir de `KnowledgeItem` tipo `CASE`
  (Biblioteca de Inteligência) — reconhecidas pelo prefixo `"[CASE]"` que
  `mapear_knowledge_item_para_skill()` já grava no `system_injection`,
  não por uma coluna nova.
- **Por que não foi plugado**: injetar múltiplas skills no prompt do
  Coach muda tamanho/custo de contexto em produção real — mesmo
  princípio de "confirmar com o usuário antes de ativar" já usado no
  Cost Router e na Otimização (Cost Intelligence Fases 4/5). Diferente
  daquelas, esta rodada nem criou o hook de shadow mode ainda — é decisão
  de produto em aberto.

## Outcome no Retrieval de Sales Memory — TAREFA 6.4 da Fase 6 do PROMPT MESTRE (`agent/sales_memory.py`, V.1.4.66)

`buscar_memorias_semantico()` agora ajusta o ranking por cosseno usando
o outcome (`won`/`lost`) da reunião que originou cada memória —
**ativo em produção**, diferente do Skill Resolver V2 acima.

- **Por que só `sales_memories` e não `base_conhecimento`/
  `knowledge_items`**: só `sales_memories.source_meeting_id` tem link
  direto e confiável com `meeting_status.meeting_id`.
  `base_conhecimento` não tem nenhuma coluna de meeting-id no schema;
  `knowledge_items` é conteúdo curado manualmente da Biblioteca de
  Inteligência, sem conceito de "reunião de origem" ganha/perdida.
  Investigação confirmou isso antes de escrever qualquer código —
  não estender o ajuste a essas duas tabelas foi decisão deliberada,
  não lacuna esquecida.
- **Nunca faça `JOIN` direto entre `sales_memories` e `meeting_status`**
  — `source_meeting_id` (utf8mb4_unicode_ci) e `meeting_id`
  (utf8mb4_0900_ai_ci) têm collations diferentes nesta base; um `JOIN`/
  `WHERE ... =` cruzando as duas colunas lança
  `pymysql.err.OperationalError: (1267, "Illegal mix of
  collations...")`. Use sempre `agent.playbook_generator.
  listar_status_reunioes(ids)` (lookup por `IN (...)` numa tabela só,
  cruzamento feito em Python) — mesmo padrão já usado por
  `GET /relatorios` pra enriquecer a listagem com `status`.
- **Ajuste é neutro por padrão**: `_ajustar_similaridade_por_outcome()`
  só altera a similaridade quando existe uma linha em `meeting_status`
  para aquela reunião de origem (`won` → `+0.05`, `lost` → `-0.10`,
  capado em `[0, 1]`). Memória sem `source_meeting_id` ou de reunião
  nunca marcada — **100% das memórias em produção até 05/09/2026,
  já que `meeting_status` estava com 0 linhas** — não muda de posição.
  Efeito real só aparece conforme os novos botões "Ganha"/"Perdida" do
  Dashboard (`frontend/dashboard.html::statusReuniaoBotoesHTML()`,
  mesma versão) forem usados.
- **Campo novo aditivo**: cada resultado de `buscar_memorias_semantico()`
  ganha `"outcome"` (`"won"|"lost"|"open"|None`) — não remove nem
  renomeia nenhum campo existente, então `buscar_contexto_para_reuniao()`
  e `GET /sales-memories/buscar` continuam funcionando sem mudança.
- **Achado que motivou esta rodada**: o botão de marcar reunião como
  ganha já existia desde antes (`marcarComoGanha()` no dashboard,
  chamando `PATCH /relatorios/{id}/status`) — o problema nunca foi
  ausência de UI, foi visibilidade (0.7rem, sem opção "Perdida",
  escondido no card). Antes de assumir "feature não existe", confirme
  com grep amplo (`marcarComoGanha`, `status.*lost`, não só o nome do
  endpoint documentado) — uma busca por `marcar-ganha` (slug antigo já
  renomeado) deu falso negativo nesta mesma investigação.

## Sales Operating System — Fase 7 do EPIC Sales Brain (V.1.4.67-1.4.70, local)

Usuário colou o EPIC "SALEIA SALES BRAIN" (7 fases) e perguntou se já
estava implementado. Fases 1-6 já existiam em produção desde V.1.4.31-37
(Sales Memory, Playbook Engine, Sales Skills, Client Intelligence,
Multiagent System, Follow-up — ver seção própria acima). Esta rodada
fechou 3 lacunas das Fases 1-6 e construiu a Fase 7 (que não existia).
**Ainda não deployada na VPS** — produção continua em V.1.4.63.

### Gaps das Fases 1-6 fechados (V.1.4.67)
- **Busca semântica de relatórios/transcrições** (`agent/
  semantic_search.py`, tabela própria `semantic_index`): indexa cada
  reunião via `background_tasks` no mesmo hook onde `extrair_e_salvar_
  memorias()` já roda. **Só para busca humana** (`GET /busca-semantica`,
  usado no Workspace) — **nunca** injetado de volta no prompt de IA em
  tempo real, mesmo princípio já usado pra não mapear `KnowledgeItem →
  sales_memory` (evitaria duplicar contexto).
- **Resumo do Cliente**: card na tela de detalhe da reunião do Dashboard
  (`GET /clientes/resumo-reuniao/{meeting_id}`), **nunca em
  `cenario.html`** — essa tela é mostrada/compartilhada com o próprio
  CLIENTE ("📋 Seu Perfil", segunda pessoa); colocar ali objeções/dores
  internas vazaria dado sensível de volta pro cliente.
- Skills como pastas de arquivo (pedido literal do EPIC): **decisão
  deliberada de não implementar** — regressão funcional frente ao que já
  existe (skills em MySQL, editáveis pelo dashboard, integradas ao
  `skill_resolver`).

### Aprendizado Contínuo com aprovação — Fase 7.3 (V.1.4.68)
O EPIC pedia pipeline 100% automático, sem intervenção manual. Decisão
confirmada com o usuário: **automático com aprovação** — roda sozinho
após cada reunião, mas todo artefato gerado por IA nasce `status=
'pending'` e só entra em uso real depois de 1 clique. Mesma rede de
segurança do Knowledge Compiler (`DRAFT`/`APPROVED`).

- Extração de memória e geração de playbook **já eram automáticas**
  desde V.1.4.31/32 (`background_tasks` em `/recapitulacao-completa` e
  `/recapitulacao-manual`, gated por `agent.playbook_generator.
  _eh_reuniao_de_sucesso()`) — o gap real era só o *gate* de aprovação,
  não a automação. Geração de skill a partir de um playbook (antes só
  via botão manual "🧠 Skill") passou a **auto-disparar** também, logo
  após o playbook nascer.
- `sales_memories`/`playbooks`/`skills` ganharam coluna `status`
  (`approved` por padrão — dado existente não muda de comportamento).
  Para playbook/skill, `status='pending'` implica `is_active=0`, então
  o gate reusa o filtro `is_active` que `listar_playbooks(apenas_
  ativos=True)`/`resolver_melhor_skill()` já tinham — nenhuma query nova
  precisou ser escrita para "esconder" o pendente do caminho real de
  produção. Para memória, `buscar_memorias_semantico()` (o RAG de
  verdade) passou a filtrar `status='approved'` direto na query.
- Aprovação reusa os `PATCH /playbooks/{id}` e `PATCH /skills/{id}` **já
  existentes** — só `"status"` entrou na whitelist editável de cada um.
  Memória ganhou endpoint novo (`PATCH /sales-memories/{id}/status`,
  não existia nenhum antes).
- **Kill-switch único**: `SALES_BRAIN_AUTOPILOT_ENABLED` (env, default
  `true`) — `false` no `.env` + restart volta ao comportamento de sempre
  (playbook/skill nascem ativos direto), sem reverter deploy. Mesmo
  padrão dos kill-switches do Cost Intelligence.
- `gerar_skill_de_knowledge_item()` (Knowledge Compiler) **não** passa
  por esse gate — continua nascendo aprovada, porque o `KnowledgeItem`
  de origem já foi revisado por humano antes (fase anterior do próprio
  Knowledge Compiler).

### Knowledge Graph — Fase 7.2 (V.1.4.69)
`agent/knowledge_graph.py`: tabela `graph_edges` (arestas simples
`from_type/from_id/to_type/to_id/relacao`, sem lib de grafo nova) —
relaciona cliente↔reunião↔memória↔playbook↔skill. `registrar_aresta()`
é chamada best-effort (`try/except: pass`) nos 4 pontos de criação de
entidade (`client_intelligence.vincular_reuniao`, `knowledge_extractor.
extrair_e_salvar_memorias`, `playbook_generator.gerar_e_salvar_playbook`,
`skill_resolver.gerar_e_salvar_skill`) — nunca pode quebrar o fluxo
principal se falhar. `GET /grafo/conexoes/{tipo}/{id}` resolve rótulo
legível de cada nó conectado. `scripts/backfill_knowledge_graph.py
--dry-run` popula arestas pra dado histórico (sem isso o grafo nasceria
vazio pra tudo que já existia).

### Workspace Comercial — Fase 7.1 (V.1.4.70)
Nova aba no Dashboard (`GET /workspace/resumo`, `GET /workspace/
pendencias`) — visão única com contadores (clientes/playbooks/skills/
memórias/follow-ups) + fila de aprovação (memória/playbook/skill
pendentes, com Aprovar/Rejeitar inline) + busca semântica, sem precisar
visitar 5 abas separadas. Botão "🔗 Conexões" plugado na página Clientes
(`verConexoesWorkspace()`) — estender aos cards de Playbooks/Skills é
follow-up trivial, mesma função.

### Runbook rápido
- **Ver o que está pendente de aprovação**: aba Workspace Comercial, ou
  `GET /workspace/pendencias`.
- **Desligar o autopilot em emergência**: `SALES_BRAIN_AUTOPILOT_
  ENABLED=false` no `.env` da VPS + `systemctl restart saleia`.
- **Buscar em relatórios/transcrições/memórias**: `GET /busca-semantica
  ?q=...` (ou a barra de busca na aba Workspace).
- **Ver como duas entidades se conectam**: `GET /grafo/conexoes/{tipo}
  /{id}` (`tipo` em `cliente|reuniao|memoria|playbook|skill`).

## Big Five + Astrologia opcional (V.1.4.71, local)

Extensão do motor multiagente — **não** o produto de autoconhecimento do
vendedor que um spec de 60 tarefas colado pelo usuário originalmente
descrevia. Escopo real, confirmado com o usuário: entender melhor *por
que o cliente* respondeu de determinada forma ou fez uma objeção numa
call de vendas.

- **`agent/multiagente/bigfive_agent.py`** (5º agente em tempo real,
  mesmo padrão de `disc_agent.py`): infere as 5 dimensões do Big Five
  **do cliente**, a partir do comportamento na conversa — nunca
  questionário, nunca recebe astrologia como entrada. Atrás do
  kill-switch `BIGFIVE_AGENT_ENABLED` (env, default `true`) —
  `agent/multiagente/orquestrador.py::bigfive_agent_ativo()` controla
  se a coroutine é criada; quando `false`, o agente nem é instanciado
  (zero custo de IA extra, não só resultado descartado). `+1 chamada de
  IA por ciclo de tempo real (~+25%)` quando ativo — pese isso antes de
  reativar em produção se o custo dos 4 provedores centrais voltar a
  ser um problema.
- **`perfil_bigfive` persiste em `MeetingMemory.current_diagnosis`**
  (reuso do campo JSON existente — `api/database.py::
  registrar_analise_meeting()`, sem coluna nova) — como
  `{diagnostico_atual}` já é lido pelos prompts de Coach e Closer, o
  Big Five realimenta o raciocínio deles automaticamente no ciclo
  seguinte, sem nenhum plumbing extra.
- **Astrologia — só signo solar, nunca mapa natal**: `agent/
  signo_solar_rules.py` (função pura, mesmo padrão de
  `propensao_rules.py` — zero IA, zero rede, zero biblioteca de
  efemérides). O dia/mês de nascimento **nunca é perguntado** — só
  usado quando o cliente menciona espontaneamente (ex.: papo de
  aniversário no rapport), extraído **uma vez por reunião** dentro da
  mesma chamada de `PROMPT_RECAPITULACAO` (campo
  `data_nascimento_mencionada`, sem chamada de IA extra). `client_
  profiles` ganha `data_nascimento_dia`/`_mes` (nullable) —
  `salvar_nascimento_cliente()` só grava se a coluna ainda for `NULL`
  (nunca sobrescreve). `obter_cliente()` anexa `perfil_astrologico`
  automaticamente, então já aparece de graça no card "Resumo do
  Cliente" (V.1.4.67) sem tocar naquele endpoint.
- **Garantia por construção, não só por instrução de prompt**: nenhum
  dos prompts `multiagente_disc.txt`/`multiagente_bigfive.txt` tem um
  placeholder de substituição trazendo signo/astrologia como entrada —
  astrologia só é processada depois, no relatório final, por um módulo
  que não importa nada de IA. `tests/test_signo_solar_rules.py::
  GuardaArquiteturalTest` confirma isso estaticamente (grep nos prompts
  + inspeção de imports) — nunca confie só no texto do prompt pedindo
  pra IA ignorar astrologia.
- **`objecoes_com_motivo`/`sintese_comportamental`**: campos aditivos no
  `PROMPT_RECAPITULACAO`, cruzando DISC+Big Five para explicar a causa
  de cada objeção. **`recapitulacao_estrategica.objecoes_levantadas`
  (lista de strings) nunca mudou de tipo** — renderiza em pelo menos 4
  lugares de `dashboard.html`; trocar pra lista de objetos ali
  repetiria a classe de bug "[object Object]" já corrigida antes no
  projeto (V.1.3.x). Se precisar estender a causa de uma objeção no
  futuro, sempre em campo novo, nunca mudando o tipo de um existente.
- Astrologia na síntese comportamental é sempre comentário narrativo
  complementar (regra explícita no prompt: "na interpretação
  astrológica...") — nunca evidência de peso igual a DISC/Big Five, e
  `sintese_comportamental.usa_astrologia` fica `false` quando não há
  dado de nascimento.

## Fase 0 do "SALE-IA V2" — baseline de confiabilidade (V.1.4.72, local)

Usuário colou um novo "PROMPT MESTRE — SALE-IA V2": 25 fases pra evoluir
o SALEIA de "IA escuta → IA sugere" pra um cérebro comercial completo
(SalesEvent, Opportunity, SPIN 2.0, MEDDPICC, Sales Science, Seller DNA,
Autonomy Policy) — **iniciativa de meses**, com Clean Architecture e uma
"regra de bloqueio" (não avançar com teste quebrado) explícita no
próprio documento. **Só a Fase 0 foi executada** — baseline de testes +
E2E de reunião completa. **Fases 1+ (SalesEvent em diante) não
começaram** — não presuma que existe nenhum `SalesEvent`/`Opportunity`/
domain layer no código só porque este prompt mestre foi discutido;
confirme sempre lendo `docs/BASELINE_REPORT_FASE0.md` e o CHANGELOG antes
de assumir progresso em qualquer fase além da 0.

- Baseline real: **512 testes, 0 falhas** (`python -m unittest discover
  tests`) — nunca reporte um número de baseline sem rodar de verdade,
  mesmo achado já valeu a pena aqui (a doc antiga citava "8 falhas
  pré-existentes" que já não existem mais).
- `docs/BASELINE_REPORT_FASE0.md` tem os 3 achados documentados
  (ownership de `meeting_id` ausente, degradação silenciosa dos 4
  provedores, extensão Chrome sem teste) — nenhum foi corrigido nesta
  rodada, são decisões de produto/priorização separadas.
- `tests/test_e2e_meeting_lifecycle.py` é o padrão a seguir pra testar o
  ciclo de vida de uma reunião: mocka só
  `agent.multiagente.claude_fallback.chamar_ia_async` (os 5 agentes do
  orquestrador) e `agent.recapitulacao.chamar_ia_async` (recapitulação
  viva, caminho de IA separado) — nunca a lógica de persistência real.
  `api.database.engine` trocado por SQLite em memória
  (`StaticPool`+`check_same_thread=False`, mesmo padrão de
  `tests/test_admin_costs_endpoints.py`).
- **Achado útil pra escrever testes de `/tempo-real` no futuro**: existe
  um gate de "texto novo mínimo" antes de qualquer chamada de IA
  (`api/processador_tempo_real.py::_pode_chamar_ia`, 120 chars OU 18
  palavras no fragmento novo, env `SALEIA_REALTIME_MIN_NEW_CHARS`/
  `_MIN_NEW_WORDS`) — um fragmento de teste curto demais retorna
  `analysis_status: "skipped"` sem nunca chamar a IA, silenciosamente.
  Sempre usar falas realistas (parágrafo, não frase curta) em testes que
  esperam `analysis_status: "updated"`.

## SalesEvent — início da Fase 1 do "PROMPT MESTRE — SALE-IA V2" (V.1.4.73)

Roadmap **diferente** do `PROMPT MESTRE — EVOLUÇÃO DA SALEIA.txt` (10
fases, seções acima) — este é o `# PROMPT MESTRE — SALE-IA V2-03_09_26.txt`
(25 fases, arquivo solto na raiz do repo), que evolui o SALEIA de "IA
escuta → IA sugere" para um cérebro comercial completo (SalesEvent,
Opportunity, SPIN 2.0, MEDDPICC, Sales Science, Seller DNA, Autonomy
Policy). Fase 0 (baseline, V.1.4.72) documentou que Fase 1+ não
começaria sem confirmação explícita do usuário — **confirmada nesta
versão**. Escopo desta rodada: **só a Tarefa 1.1** (criar o `SalesEvent`)
— Tarefa 1.2 (`SalesEvidence`) e qualquer fase seguinte não começaram.

- **`api/database.py::SalesEvent`** (tabela `sales_events`, aditiva):
  schema literal do prompt mestre — `meeting_id`, `opportunity_id`
  (sem FK; `Opportunity` só nasce na Fase 2, ainda não implementada),
  `client_id`, `seller_id`, `event_type`, `timestamp`, `speaker`,
  `evidence_quote`, `source`, `confidence`, `metadata`, `created_at`.
- **`agent/sales_event_rules.py`** (novo, função pura — mesmo padrão de
  `propensao_rules.py`/`signo_solar_rules.py`, zero IA/DB):
  `SALES_EVENT_TYPES` (as 14 categorias mínimas, `PAIN_DETECTED` a
  `DEAL_LOST`) e `validar_sales_event()`.
- **SalesEvent é dado de domínio, não telemetria — decisão deliberada**:
  diferente de `AiUsageEvent`/`KnowledgeItem` (escrita "melhor esforço",
  nunca lança), `api/database.py::criar_sales_event()` propaga
  `ValueError` do chamador em 3 casos: `event_type` fora das 14
  categorias, `confidence` fora de `[0, 1]`, ou `evidence_quote` ausente
  quando `source="conversation"` — regra explícita do prompt mestre
  ("nenhum evento pode existir sem evidência quando sua origem é uma
  conversa"). Nada é persistido quando a validação falha.
- **Sem endpoint HTTP** — a Tarefa 1.1 pede "criar o SalesEvent", não
  expô-lo via API; só `criar_sales_event()`/`obter_sales_event()`/
  `listar_sales_events()` em `api/database.py`.
- **Escopo do teste de integração, decisão deliberada**: o exemplo do
  prompt mestre (transcrição "Achei caro." → `OBJECTION_RAISED`,
  `category=PRICE`, `evidence="Achei caro"`) é reproduzido chamando
  `criar_sales_event()` diretamente com esses valores já classificados
  — prova o schema/validação de ponta a ponta via persistência real.
  **Nenhuma extração automática de eventos a partir de transcrição
  livre foi construída** — não está no enunciado da Tarefa 1.1 (que é
  só "criar o SalesEvent"), exigiria uma classificação nova (regra
  determinística ou IA) fora do escopo desta rodada, e fica para tarefa
  futura do roadmap.
- 12 testes novos (`tests/test_sales_event.py`). Suite completa: 524
  testes (512 da Fase 0 + 12 novos), 0 falhas, 1 skip pré-existente —
  sem regressão.
- **Pendente**: push + deploy na VPS (aditivo — 1 tabela nova, criada
  automaticamente via `create_all()` no startup, sem `.env`/flag novos).
  **Tarefa 1.2 (`SalesEvidence`) e Fase 2+ do roadmap não começam sem
  nova confirmação explícita do usuário.**

## SalesEvidence — Tarefa 1.2 da Fase 1 do "PROMPT MESTRE — SALE-IA V2" (V.1.4.74)

Sequência direta do `SalesEvent` acima — usuário confirmou avançar para
a Tarefa 1.2. Objetivo do prompt mestre: separar **interpretação** de
**evidência**. Nunca salvar só "cliente está inseguro" (hipótese solta,
sem lastro); sempre `type=ADOPTION_RISK` + `quote="Tenho medo da minha
equipe não usar"` (hipótese apontando para a fala real que a sustenta).

- **`api/database.py::SalesEvidence`** (tabela `sales_evidences`,
  aditiva): schema literal do prompt mestre — `id`, `meeting_id`,
  `type`, `quote`, `speaker`, `timestamp`, `confidence`, `source`,
  `created_at`. Sem FK para `SalesEvent` de propósito — mesma
  disciplina de escopo da Tarefa 1.1 (só o schema pedido).
- **`agent/sales_evidence_rules.py`** (novo, função pura — mesmo padrão
  de `sales_event_rules.py`): `validar_sales_evidence()` levanta
  `ValueError` em `type` vazio, `quote` vazia/ausente, ou `confidence`
  fora de `[0, 1]`.
- **A regra central da tarefa** ("hipóteses geradas por IA sempre
  apontem para ao menos uma evidência") é imposta no schema/validação
  tornando `quote` obrigatória e não-vazia — uma hipótese sem a fala que
  a sustenta nunca vira um `SalesEvidence` válido. `criar_sales_evidence()`
  propaga o `ValueError`, mesma convenção "dado de domínio" da Tarefa
  1.1 (nunca falha silenciosa como `AiUsageEvent`/`KnowledgeItem`).
- **Sem endpoint HTTP** — mesma decisão da Tarefa 1.1, a tarefa pede
  "criar o SalesEvidence", não expô-lo via API.
- 10 testes novos (`tests/test_sales_evidence.py`), incluindo o teste
  literal do exemplo do prompt mestre. Suite completa: 534 testes (524
  da Tarefa 1.1 + 10 novos), 0 falhas, 1 skip pré-existente — sem
  regressão.
- **Pendente**: push + deploy na VPS (aditivo — 1 tabela nova via
  `create_all()`). **Fase 2 (Opportunity Memory) do roadmap não começa
  sem nova confirmação explícita do usuário.**

## Opportunity Memory + Opportunity Graph — Fase 2 completa do "PROMPT MESTRE — SALE-IA V2" (V.1.4.75)

Usuário confirmou avançar para a Fase 2 (Tarefa 2.1) e, em seguida,
para a Tarefa 2.2 — as duas concluídas nesta rodada.

### Tarefa 2.1 — Opportunity + OpportunityMemory
- **`api/database.py::Opportunity`** (tabela `opportunities`): schema
  literal do prompt mestre — `client_id`, `seller_id`, `stage` (string
  livre, sem enum — o prompt mestre não define vocabulário fechado de
  pipeline aqui, diferente do `conversation_stage` SPIN já existente
  por-reunião), `status` (`open`/`won`/`lost`, validado),
  `estimated_value`, `won_at`/`lost_at`/`loss_reason`.
- **`api/database.py::OpportunityMemory`** (tabela
  `opportunity_memories`, 1:1 com `opportunity_id`): as 13 categorias
  do prompt mestre (`pain_points` a `unknowns`), cada uma uma lista
  JSON **append-only** de insights (`{id, meeting_id, campo, valor,
  evidence, confidence, timestamp, contradiz}`).
- **Regra central — "informações históricas não desaparecem;
  contradições são registradas e não silenciosamente sobrescritas"**:
  `agent/opportunity_memory_rules.py::adicionar_insight()` nunca
  remove/edita uma entrada existente. Quando um novo valor para o
  mesmo `campo` (aspecto opcional dentro da categoria, ex.:
  `"orcamento_mensal"` dentro de `metrics`) diverge do valor mais
  recente já registrado, a entrada nova aponta `contradiz` para o `id`
  da entrada anterior — ambas ficam na lista, nada é apagado.
- **`MeetingMemory` ganha coluna `opportunity_id`** (nullable,
  aditiva) — liga reuniões a uma oportunidade sem tocar em nenhum
  campo existente; `MeetingMemory` continua isolada (transcrição/
  diagnóstico/eventos próprios nunca se misturam entre reuniões).
- `api/database.py`: CRUD completo (`criar_opportunity`,
  `obter_opportunity`, `listar_opportunities`,
  `atualizar_status_opportunity` — grava `won_at`/`lost_at` só na
  primeira transição, nunca sobrescreve —, `vincular_meeting_opportunity`,
  `listar_meetings_da_opportunity`, `obter_opportunity_memory`,
  `registrar_conhecimento_opportunity` — dado de domínio, propaga
  `ValueError` em categoria inválida, mesma convenção da Fase 1). Sem
  endpoint HTTP novo (não pedido pela Tarefa 2.1).
- 22 testes novos (`tests/test_opportunity_memory.py`), incluindo o
  teste literal do prompt mestre (oportunidade com 3 reuniões,
  confirma isolamento + agregação + contradição sem perda de dado).

### Tarefa 2.2 — Opportunity Graph
- **`api/database.py::OpportunityGraphEdge`** (tabela
  `opportunity_graph_edges`): relaciona nós `CLIENT`/`PAIN`/`IMPACT`/
  `GOAL`/`OBJECTION`/`STAKEHOLDER`/`COMPETITOR`/`DECISION`/`NEXT_STEP`
  dentro de uma `opportunity_id`. Nós `PAIN`/`IMPACT`/... referenciam
  o `id` do insight já registrado em `OpportunityMemory` (Tarefa 2.1)
  — nunca duplica dado; só `CLIENT` referencia `client_id` direto.
- **Decisão deliberada — grafo novo, separado do
  `agent/knowledge_graph.py` já existente** (Sales Brain Fase 7.2,
  V.1.4.69): aquele conecta entidades de CRUD (cliente/reunião/
  memória/playbook/skill) por `relacao`+`created_at`, sem evidência
  nem confiança por aresta, e é raw-pymysql (não testável com
  SQLite). Este é um grafo qualitativo diferente, escopado por
  oportunidade, com `source`/`evidence`/`confidence`/`timestamp`
  obrigatórios por aresta — schema literal da Tarefa 2.2.
- **`evidence` sempre obrigatória** (`agent/opportunity_graph_rules.py::
  validar_aresta()`) — regra central do prompt mestre ("cada relação
  deve conter source/evidence/confidence/timestamp... sem perder a
  origem"), mesma disciplina de `SalesEvidence`/Tarefa 1.2.
- `api/database.py`: `criar_aresta_opportunity_graph()` (propaga
  `ValueError`), `listar_arestas_opportunity()` (filtro opcional por
  nó específico, qualquer direção). Sem endpoint HTTP novo.
- 15 testes novos (`tests/test_opportunity_graph.py`), incluindo o
  exemplo literal do prompt mestre: reunião 1 identifica
  `dor=leads esquecidos`, reunião 2 identifica `impacto=R$20.000/mês`,
  o grafo relaciona `PAIN → causa → IMPACT` sem perder a origem de
  nenhum dos dois insights.

### Comum às duas tarefas
- Suite completa: **571 testes** (556 da Fase 1 + 37 novos), **0
  falhas**, 1 skip pré-existente — sem regressão.
- **Pendente**: push + deploy na VPS. `opportunities`/
  `opportunity_memories`/`opportunity_graph_edges` são tabelas novas
  (aditivas via `create_all()`), mas a coluna `opportunity_id` em
  `MeetingMemory` (tabela já existente) **exige `ALTER TABLE
  meeting_memory ADD COLUMN opportunity_id INTEGER` manual na VPS** —
  `create_all()` não migra colunas em tabelas já existentes (mesmo
  problema do fix `MEDIUMTEXT` da V.1.4.54). **Fase 3 (SPIN 2.0) do
  roadmap não começa sem nova confirmação explícita do usuário.**

## SPIN Coverage Engine — Fase 3 / Tarefa 3.1 do "PROMPT MESTRE — SALE-IA V2" (V.1.4.76)

Usuário confirmou avançar para a Fase 3 (SPIN 2.0) do "PROMPT MESTRE —
SALE-IA V2" (roadmap diferente do "PROMPT MESTRE — EVOLUÇÃO DA
SALEIA.txt" mencionado na próxima seção — os dois têm uma "Fase 3", mas
são documentos e roadmaps distintos). Escopo desta rodada: só a
**Tarefa 3.1** (SPIN Coverage Engine) — Tarefa 3.2 (Question Gap
Engine, prioridades critical/high/medium/low) não começou.

- **`agent/spin_coverage_rules.py`** (novo, função pura — mesmo padrão
  de `sales_event_rules.py`/`opportunity_memory_rules.py`, zero IA/DB):
  `calcular_cobertura_spin(fatos_conhecidos, checklist=None)` computa
  `known[]`/`missing[]` por estágio SPIN (`situation`/`problem`/
  `implication`/`need_payoff`) a partir de fatos já estruturados e
  evidenciados.
- **Regra do prompt mestre — "não permitir que a IA invente informação
  faltante"**: imposta recusando (`ValueError`) qualquer fato sem
  `evidence_quote` — nenhum "known" existe sem lastro real na
  conversa, mesma disciplina de `SalesEvent`/`SalesEvidence` (Fase 1).
- **`SPIN_CHECKLIST_PADRAO`**: vocabulário default por estágio,
  inferido do exemplo literal do prompt mestre (`situation`:
  `team_size`/`crm_tool`; `problem`: `main_pain`; `implication`:
  `financial_impact`/`conversion_impact`; `need_payoff`:
  `solution_value`) — sobrescrevível por chamada (`checklist=`), não é
  um vocabulário fechado do domínio.
- **`estagio_atual()`**: primeiro estágio SPIN (em ordem) ainda com
  pendência. **`sugerir_proxima_pergunta()`**: usa
  `SPIN_PERGUNTAS_PADRAO` (fallback genérico pra campos fora do dict)
  — bate **exatamente** com o exemplo literal do prompt mestre
  (`financial_impact` → `"Quanto esse problema custa atualmente?"`).
- **Decisão deliberada de escopo**: extração automática de fatos a
  partir de transcrição livre via IA (interpretar "nosso follow-up é
  lento" → `problem.main_pain`) **não foi construída** — não está no
  enunciado da Tarefa 3.1 ("criar cobertura real" a partir de fatos já
  estruturados), fica para tarefa futura. Sem integração com
  `orquestrador.py` ainda — mesma disciplina das Fases 1-2 (schema/
  regra primeiro, integração é decisão separada).
- 13 testes novos (`tests/test_spin_coverage_rules.py`), incluindo o
  exemplo literal do prompt mestre reproduzido exatamente.
- Suite completa: **584 testes** (571 da Fase 2 + 13 novos), **0
  falhas**, 1 skip pré-existente — sem regressão.
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova — módulo
  puro em memória). **Tarefa 3.2 (Question Gap Engine) e qualquer fase
  seguinte não começam sem nova confirmação explícita do usuário.**

## Question Gap Engine — Fase 3 / Tarefa 3.2 do "PROMPT MESTRE — SALE-IA V2" (V.1.4.77)

Usuário confirmou avançar para a Tarefa 3.2. Constrói diretamente sobre
o `SPINState` (known[]/missing[] por estágio) da Tarefa 3.1 — objetivo
do prompt mestre: "descobrir qual pergunta ainda precisa ser feita".

- **`agent/question_gap_rules.py`** (novo, função pura, mesmo padrão de
  `spin_coverage_rules.py` — zero IA/banco): `calcular_gaps_priorizados(
  cobertura, prioridade_por_stage=None)` recebe a cobertura já calculada
  por `calcular_cobertura_spin()` (Tarefa 3.1) e devolve a lista de gaps
  (`missing`) com `{"stage", "campo", "priority", "pergunta"}`, ordenada
  por prioridade (`critical` > `high` > `medium` > `low`, as 4 do prompt
  mestre) e, dentro da mesma prioridade, pela ordem SPIN.
- **`proximo_gap(gaps_priorizados)`**: primeiro item da lista já
  priorizada, ou `None` — resposta direta a "qual pergunta ainda precisa
  ser feita".
- **Pergunta sempre reaproveitada de `SPIN_PERGUNTAS_PADRAO`** (Tarefa
  3.1), nunca reinventada — regra de teste do prompt mestre ("pergunta
  recomendada precisa estar relacionada ao gap detectado") garantida por
  construção, já que o campo do gap indexa diretamente o dicionário de
  perguntas.
- **`STAGE_PRIORIDADE_PADRAO`**: mapeamento default por estágio SPIN
  (`implication=critical`, `need_payoff=high`, `problem=medium`,
  `situation=low`) — não está explícito no prompt mestre (que só define
  o vocabulário de prioridades, não a regra de atribuição), decisão
  desta rodada seguindo a própria lógica do SPIN: Implication expõe o
  custo/urgência do problema (gap mais crítico de não perguntar),
  Need Payoff sustenta o valor da solução, Situation/Problem são
  fundação. Sobrescrevível por chamada (`prioridade_por_stage=`), mesmo
  padrão de `checklist=` em `calcular_cobertura_spin()`.
- 10 testes novos (`tests/test_question_gap_rules.py`), incluindo o
  exemplo literal do prompt mestre (`financial_impact` → "Quanto esse
  problema custa atualmente?").
- **Decisão deliberada de escopo**: sem integração com
  `orquestrador.py`/`processador_tempo_real.py` ainda — mesma disciplina
  das Fases 1-3 (schema/regra primeiro, integração é decisão de produto
  separada). Sem endpoint HTTP novo.
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova — módulo
  puro em memória). **Fase 4 (MEDDPICC) e qualquer tarefa seguinte não
  começam sem nova confirmação explícita do usuário.**

## Opportunity Qualification Engine — Fase 4 / Tarefa 4.1 do "PROMPT MESTRE — SALE-IA V2" (V.1.4.78)

Usuário confirmou avançar para a Fase 4 (MEDDPICC). Escopo desta rodada:
só a Tarefa 4.1 (motor de qualificação) — Tarefa 4.2 (Deal Risk) não
começou.

- **`agent/meddpicc_rules.py`** (novo, função pura, mesmo padrão de
  `spin_coverage_rules.py`/`question_gap_rules.py` — zero IA/DB):
  `calcular_qualificacao_meddpicc(fatos_conhecidos)` recebe fatos já
  estruturados e evidenciados (`{"item", "status", "confidence",
  "evidence_quote"}`) e devolve o estado dos 8 itens MEDDPICC
  (`metrics`, `economic_buyer`, `decision_criteria`, `decision_process`,
  `paper_process`, `identify_pain`, `champion`, `competition`) — cada um
  `{"status", "confidence", "evidence": [...]}`.
- **Agregação quando há múltiplos fatos sobre o mesmo item** (decisão
  desta rodada, mesmo espírito de "informação não desaparece" já usado
  em `opportunity_memory_rules.py`): `status` nunca regride (usa o mais
  avançado já visto, `UNKNOWN → PARTIAL → CONFIRMED`), `confidence` usa
  o maior valor já visto, `evidence` acumula todas as quotes na ordem
  recebida — nunca descarta.
- **Regra de evidência estendida por decisão deliberada**: o prompt
  mestre não repete a frase "não invente informação faltante" na Tarefa
  4.1, mas o schema pedido (status/confidence/evidence[] por item) só
  faz sentido com a mesma disciplina de `SalesEvent`/`SalesEvidence`/SPIN
  — `calcular_qualificacao_meddpicc()` recusa (`ValueError`) qualquer
  item que tente sair de `UNKNOWN` sem `evidence_quote`.
- **`resumo_qualificacao(estado)`**: contagem de itens por status +
  `nivel` geral (`fraca`/`intermediaria`/`avancada`) por contagem de
  itens `CONFIRMED` (limiares `>=6`=avancada, `>=3`=intermediaria —
  decisão desta rodada, o prompt mestre não define o número exato, só
  pede os 3 cenários de teste). **`itens_pendentes(estado)`**: itens
  ainda não `CONFIRMED`, na ordem literal do prompt mestre.
- 14 testes novos (`tests/test_meddpicc_rules.py`), incluindo os 3
  cenários pedidos pelo prompt mestre com resultado esperado definido
  antes da execução (oportunidade mal qualificada → `fraca`;
  intermediária → `intermediaria`; enterprise avançada, 8/8 itens
  `CONFIRMED` → `avancada`).
- **Decisão deliberada de escopo**: sem integração com
  `orquestrador.py`/`processador_tempo_real.py`, sem persistência nova
  (nenhuma tabela `MeddpiccState`) e sem endpoint HTTP — mesma
  disciplina de schema/regra primeiro das Fases 1-3.
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova — módulo
  puro em memória). **Tarefa 4.2 (Deal Risk) e qualquer fase seguinte
  não começam sem nova confirmação explícita do usuário.**

## Deal Risk Engine — Fase 4 / Tarefa 4.2 do "PROMPT MESTRE — SALE-IA V2" (V.1.4.79)

Usuário confirmou avançar para a Tarefa 4.2. Fecha a Fase 4 (MEDDPICC)
completa — constrói diretamente sobre o estado MEDDPICC da Tarefa 4.1.

- **`agent/deal_risk_rules.py`** (novo, função pura, mesmo padrão de
  `meddpicc_rules.py`/`spin_coverage_rules.py`/`question_gap_rules.py`
  — zero IA/banco, regra explícita do prompt mestre "não usar LLM para
  calcular regras simples"): `calcular_riscos(estado_meddpicc=None,
  tem_proximo_passo=True, total_objecoes_preco=0,
  competidor_em_vantagem=False, dias_desde_ultima_atividade=0, ...)`
  devolve a lista de códigos de risco detectados (subconjunto de
  `DEAL_RISK_TIPOS`, sempre na ordem fixa `NO_ECONOMIC_BUYER →
  NO_CHAMPION → NO_NEXT_STEP → NO_METRICS → HIGH_PRICE_RESISTANCE →
  COMPETITOR_ADVANTAGE → STALE_OPPORTUNITY`, os 7 exemplos literais do
  prompt mestre).
- **`NO_ECONOMIC_BUYER`/`NO_CHAMPION`/`NO_METRICS`** derivam direto do
  `estado_meddpicc` (Tarefa 4.1) — item não `CONFIRMED` dispara o risco.
  Os outros 4 (`NO_NEXT_STEP`, `HIGH_PRICE_RESISTANCE`,
  `COMPETITOR_ADVANTAGE`, `STALE_OPPORTUNITY`) recebem sinal explícito
  do chamador (booleano/contagem/dias) — **de onde vem cada sinal em
  produção real (ex.: contar `SalesEvent.event_type ==
  "PRICE_DISCUSSION"`) é integração futura**, fora do escopo desta
  tarefa.
- **`COMPETITOR_ADVANTAGE` é sinal explícito, não deriva do item
  `competition` do MEDDPICC** — aquele item só indica se o cenário
  competitivo foi mapeado (CONFIRMED/PARTIAL/UNKNOWN), não quem está na
  frente; misturar os dois inflaria falso-positivo toda vez que a
  competição fosse simplesmente conhecida, mesmo sem desvantagem real.
- **Limiares** (`LIMIAR_OBJECOES_PRECO_PADRAO=3`,
  `LIMIAR_DIAS_STALE_PADRAO=21`) — decisão desta rodada, o prompt mestre
  não define os números exatos, só pede "riscos determinísticos sempre
  que possível". Sobrescrevíveis por chamada, mesmo padrão de
  `STAGE_PRIORIDADE_PADRAO`/`NIVEL_MINIMO_AVANCADA` das tarefas
  anteriores.
- 13 testes novos (`tests/test_deal_risk_rules.py`), incluindo o
  exemplo literal do prompt mestre (dor forte + sem decisor + sem
  próxima reunião → pelo menos `NO_ECONOMIC_BUYER` e `NO_NEXT_STEP`).
- **Decisão deliberada de escopo**: sem integração com
  `orquestrador.py`/`processador_tempo_real.py`, sem persistência nova
  e sem endpoint HTTP — mesma disciplina das Fases 1-4.
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova — módulo
  puro em memória). **Fase 5 (Motivação e Comportamento) e qualquer
  tarefa seguinte não começam sem nova confirmação explícita do
  usuário.**

## Buyer Motivation Engine — Fase 5 / Tarefa 5.1 do "PROMPT MESTRE — SALE-IA V2" (V.1.4.80)

Usuário confirmou avançar para a Fase 5 (Motivação e Comportamento).
Escopo desta rodada: só a Tarefa 5.1 (motor de motivação) — Tarefa 5.2
(Behavioral Signal Engine) não começou.

- **`agent/buyer_motivation_rules.py`** (novo, função pura, mesmo padrão
  de `meddpicc_rules.py`/`sales_event_rules.py` — zero IA/DB):
  `MOTIVATION_TIPOS` (os 12 motivadores literais do prompt mestre —
  `GROWTH`, `SECURITY`, `CONTROL`, `STATUS`, `CONVENIENCE`, `SPEED`,
  `COST_REDUCTION`, `REVENUE_GAIN`, `RISK_REDUCTION`, `PRODUCTIVITY`,
  `RECOGNITION`, `SIMPLICITY`) — taxonomia controlada, não texto livre.
- **`validar_hipoteses_motivacao(hipoteses)`**: cada hipótese
  (`{"motivation", "confidence", "evidence"}`) validada — `motivation`
  precisa estar na taxonomia, `confidence` em `[0,1]`, `evidence`
  precisa ser uma lista não-vazia com pelo menos 1 quote real (mesma
  disciplina de evidência de `SalesEvent`/`SPIN`/`MEDDPICC`).
  **`motivacao_dominante(hipoteses)`**: valida e retorna a hipótese de
  maior `confidence` (leitura corrente da motivação predominante), ou
  `None` se a lista estiver vazia.
- **Regra do prompt mestre — "DISC nunca deverá ser tratado como
  motivação" — garantida por construção, não só por convenção**: o
  módulo não importa nem lê nenhum campo relacionado a DISC.
  `tests/test_buyer_motivation_rules.py::GuardaArquiteturalTest`
  confirma isso via grep no arquivo-fonte, mesmo padrão de
  `agent/signo_solar_rules.py` (astrologia vs. DISC/Big Five, V.1.4.71).
- **Teste do prompt mestre reproduzido** ("diálogos onde DISC permanece
  igual; motivação muda; sistema deve diferenciar corretamente"):
  simula 3 turnos com DISC externo constante (`"D"`) e hipóteses de
  motivação diferentes por turno — confirma que `motivacao_dominante()`
  muda a cada turno, nunca herda o valor anterior nem se acopla ao DISC.
- 14 testes novos (`tests/test_buyer_motivation_rules.py`).
- **Decisão deliberada de escopo**: sem integração com
  `orquestrador.py`/`processador_tempo_real.py`, sem persistência nova
  e sem endpoint HTTP — mesma disciplina das Fases 1-4. Extração
  automática de hipóteses a partir de transcrição livre via IA não foi
  construída (fora do enunciado da Tarefa 5.1).
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova — módulo
  puro em memória). **Tarefa 5.2 (Behavioral Signal Engine) e qualquer
  fase seguinte não começam sem nova confirmação explícita do
  usuário.**

## Behavioral Signal Engine — Fase 5 / Tarefa 5.2 do "PROMPT MESTRE — SALE-IA V2" (V.1.4.81)

Usuário confirmou avançar para a Tarefa 5.2. Fecha a Fase 5 (Motivação
e Comportamento) completa.

- **`agent/behavioral_signal_rules.py`** (novo, função pura, mesmo
  padrão de `buyer_motivation_rules.py` — zero IA/DB):
  `BEHAVIORAL_SIGNAL_TIPOS` (os 6 sinais literais do prompt mestre —
  `LOSS_AVERSION`, `STATUS_QUO_BIAS`, `SOCIAL_PROOF_REQUEST`,
  `AUTHORITY_REQUEST`, `PRICE_ANCHOR`, `RISK_AVERSION`).
- **`validar_sinais_comportamentais(sinais)`**: cada sinal
  (`{"signal", "evidence_quote"}`) validado — `signal` precisa estar na
  taxonomia, `evidence_quote` obrigatória e não-vazia (regra literal do
  prompt mestre: "cada sinal precisa apresentar trecho da conversa que
  o sustenta").
- **`detectar_sinais(sinais_observados)`**: valida e enriquece cada
  sinal com uma descrição canônica sóbria do tipo (`DESCRICOES_
  SINAIS`), nunca um texto livre/gerado — garante por construção a
  regra "evitar alegações como 'o cérebro reptiliano foi ativado'"
  (`GuardaContraAlegacoesPseudocientificasTest` confirma via grep que
  nenhuma descrição menciona mecanismo neurológico/evolutivo
  especulativo). **`contagem_por_sinal(sinais_observados)`**: contagem
  por tipo, útil pra saber quais vieses mais apareceram numa reunião.
- 15 testes novos (`tests/test_behavioral_signal_rules.py`).
- **Decisão deliberada de escopo**: sem integração com
  `orquestrador.py`/`processador_tempo_real.py`, sem persistência nova
  e sem endpoint HTTP — mesma disciplina das Fases 1-5. Extração
  automática de sinais a partir de transcrição livre via IA não foi
  construída (fora do enunciado da Tarefa 5.2).
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova — módulo
  puro em memória). **Fase 6 (Objection Intelligence) e qualquer tarefa
  seguinte não começam sem nova confirmação explícita do usuário.**

## Taxonomia de Objeções — Fase 6 / Tarefa 6.1 do "PROMPT MESTRE — SALE-IA V2" (V.1.4.82)

Usuário confirmou avançar para a Fase 6 (Objection Intelligence).
Escopo desta rodada: só a Tarefa 6.1 (taxonomia + separação spoken/root
cause) — Tarefa 6.2 (Negotiation Engine) não começou.

- **`agent/objection_rules.py`** (novo, função pura, mesmo padrão de
  `behavioral_signal_rules.py`/`meddpicc_rules.py` — zero IA/DB):
  `OBJECTION_TIPOS` (as 13 categorias literais do prompt mestre —
  `PRICE`, `VALUE`, `BUDGET`, `TIMING`, `TRUST`, `ADOPTION`,
  `COMPETITOR`, `AUTHORITY`, `PRIORITY`, `IMPLEMENTATION`, `LEGAL`,
  `PROCUREMENT`, `SECURITY`) — vocabulário fechado só pra
  `objection_spoken` (o que o cliente literalmente falou).
- **`objection_spoken` e `root_cause_hypothesis` são sempre campos
  separados, nunca fundidos**: `root_cause_hypothesis.hypothesis` usa
  vocabulário livre (o exemplo do prompt mestre usa `ADOPTION_RISK`,
  que nem está nas 13 categorias de `objection_spoken`) — só exige
  `confidence` em `[0,1]` e `evidence_quote` própria.
- **Regra central — "'Está caro.' não pode resultar automaticamente em
  root_cause = PRICE, confidence 100%; sistema deve primeiro recomendar
  investigação"** — imposta estruturalmente por
  `precisa_investigar(objection_spoken, root_cause_hypothesis=None)`:
  retorna `True` sempre que (a) nenhuma hipótese foi levantada ainda,
  (b) `confidence < LIMIAR_CONFIANCA_MINIMA_ROOT_CAUSE` (`0.7`, decisão
  desta rodada), ou (c) a hipótese só repete a categoria falada
  (`hypothesis == objection_spoken.category`) reaproveitando a MESMA
  `evidence_quote` do spoken — o padrão exato de "espelhamento sem
  investigação real" que o prompt mestre proíbe.
- **`registrar_objecao(objection_spoken, root_cause_hypothesis=None)`**:
  monta o registro completo (`{"objection_spoken", "root_cause_
  hypothesis", "precisa_investigar"}`), sempre com os dois campos
  visivelmente separados.
- 16 testes novos (`tests/test_objection_rules.py`), incluindo o
  exemplo literal proibido (`PRICE`/"Está caro."/confidence 100% +
  mesma evidência → `precisa_investigar=True`) e o exemplo literal bom
  do prompt mestre (`spoken=PRICE`, `root=ADOPTION_RISK` com evidência
  própria → `precisa_investigar=False`).
- **Decisão deliberada de escopo**: sem integração com
  `orquestrador.py`/`processador_tempo_real.py`, sem persistência nova
  e sem endpoint HTTP — mesma disciplina das Fases 1-5. Extração
  automática de objeções a partir de transcrição livre via IA não foi
  construída (fora do enunciado da Tarefa 6.1).
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova — módulo
  puro em memória). **Tarefa 6.2 (Negotiation Engine) e qualquer fase
  seguinte não começam sem nova confirmação explícita do usuário.**

## Negotiation Engine — Fase 6 / Tarefa 6.2 do "PROMPT MESTRE — SALE-IA V2" (V.1.4.83)

Usuário confirmou avançar para a Tarefa 6.2. Fecha a Fase 6 (Objection
Intelligence) completa — constrói diretamente sobre
`objection_rules.precisa_investigar()` (Tarefa 6.1).

- **`agent/negotiation_rules.py`** (novo, função pura, mesmo padrão de
  `objection_rules.py`/`behavioral_signal_rules.py` — zero IA/DB):
  `NEGOTIATION_TIPOS` — as 7 estratégias consultivas literais do prompt
  mestre (`LABEL`, `MIRROR`, `CALIBRATED_QUESTION`, `SUMMARIZE`,
  `CLARIFY`, `VALUE_REFRAME`, `RISK_REDUCTION`), divididas em
  `ESTRATEGIAS_INVESTIGATIVAS` (4) e `ESTRATEGIAS_POS_INVESTIGACAO` (3)
  — união cobre a taxonomia inteira, sem sobreposição.
- **Regra explícita do prompt mestre — "nunca permitir: ameaça,
  mentira, escassez falsa, manipulação, informações inventadas" —
  garantida por construção**: o vocabulário é fechado nas 7 estratégias
  consultivas; nenhuma tática manipulativa (desconto arbitrário,
  ameaça, urgência falsa) é sequer representável — não existe campo de
  texto livre na API pública. `GuardaContraTaticasManipulativasTest`
  confirma via grep que nenhuma das 7 descrições canônicas
  (`DESCRICOES_ESTRATEGIAS`) menciona essas táticas.
- **Teste específico do prompt mestre reproduzido literalmente**:
  cliente diz "Está caro." → resultado proibido "Posso dar 20% agora."
  → resultado esperado: estratégia de investigação.
  `recomendar_estrategia(objection_spoken, root_cause_hypothesis=None,
  estrategia_desejada=None)` reaproveita `precisa_investigar()` (Tarefa
  6.1): enquanto a objeção não foi investigada, só estratégias de
  `ESTRATEGIAS_INVESTIGATIVAS` são permitidas — qualquer tentativa de
  passar `estrategia_desejada` fora desse subconjunto (inclusive
  `VALUE_REFRAME`, o caminho mais próximo de "oferecer algo" nesse
  vocabulário) é recusada (`ValueError`), mesmo se um chamador/IA
  futura tentar pular a investigação.
- **Decisão deliberada de escopo**: sem integração com
  `orquestrador.py`/`processador_tempo_real.py`, sem persistência nova
  e sem endpoint HTTP — mesma disciplina das Fases 1-6.
- 13 testes novos (`tests/test_negotiation_rules.py`), incluindo o
  exemplo literal "Está caro." e a guarda contra táticas manipulativas.
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova — módulo
  puro em memória). **Fase 7 (Sales Reasoning Engine) e qualquer tarefa
  seguinte não começam sem nova confirmação explícita do usuário.**

## SalesReasoningEngine — Fase 7 / Tarefa 7.1 do "PROMPT MESTRE — SALE-IA V2" (V.1.4.84, só contrato)

Usuário confirmou avançar para a Fase 7 ("o cérebro central" que
consolida SPINState/MEDDPICCState/BuyerMotivation/Objections/
BehavioralSignals das Fases 1-6 + MeetingMemory/OpportunityMemory/
OpportunityGraph/RAGContext/SellerContext/HistoricalPatterns).

- **Decisão explícita do usuário sobre escopo, via pergunta direta
  antes de implementar**: só o CONTRATO de entrada/saída nesta rodada,
  sem nenhuma chamada de IA e sem o Golden Dataset de 50+ cenários que
  o prompt mestre pede para a Tarefa 7.1 — o motor de raciocínio real
  (novo prompt/agente) e a suíte semântica ficam para quando o usuário
  decidir avançar. Motivo: diferente das Fases 1-6 (regras
  determinísticas puras), o próprio prompt mestre exige validação
  **semântica** ("o teste não deve depender de igualdade literal de
  frase") — só faz sentido com raciocínio real via IA, um salto de
  escopo/custo que merecia confirmação explícita antes de começar.
- **`agent/sales_reasoning_engine.py`** (novo — nome de arquivo foge do
  padrão `*_rules.py` de propósito, o prompt mestre chama isso de
  "novo serviço"): `SALES_REASONING_INPUT_CAMPOS` (os 11 campos
  literais de entrada — `meeting_memory`, `opportunity_memory`,
  `opportunity_graph`, `spin_state`, `meddpicc_state`,
  `buyer_motivation`, `objections`, `behavioral_signals`,
  `rag_context`, `seller_context`, `historical_patterns`) e
  `SALES_REASONING_OUTPUT_CAMPOS` (os 10 campos literais de saída —
  `current_state`, `hypotheses`, `evidence`, `missing_information`,
  `recommended_framework`, `next_best_action`, `next_best_question`,
  `avoid`, `reason`, `confidence`).
- **`construir_input_vazio()`/`validar_input_raciocinio(entrada)`**:
  todos os 11 campos de entrada são opcionais (numa reunião real, nem
  todos existem em qualquer ponto da conversa) — a validação só barra
  chave desconhecida/erro de digitação, nunca exige preenchimento.
- **`montar_saida_raciocinio(...)`/`validar_output_raciocinio(saida)`**:
  `current_state`/`recommended_framework`/`next_best_action`/`reason`
  obrigatórios e não-vazios; `hypotheses`/`evidence`/`missing_
  information`/`avoid` sempre lista (default `[]`, nunca `None`);
  `next_best_question` é o único texto opcional (`None` permitido —
  nem toda recomendação é uma pergunta); `confidence` em `[0,1]`.
- 14 testes novos (`tests/test_sales_reasoning_engine.py`), incluindo o
  exemplo literal de saída do prompt mestre (`current_state` sobre dor
  sem impacto econômico claro → `recommended_framework=SPIN_
  IMPLICATION` → `next_best_action="aprofundar impacto"` →
  `confidence=0.86`).
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova — módulo
  puro em memória, zero custo de IA nesta rodada). **O motor de
  raciocínio real (chamada de IA) e o Golden Dataset de 50+ cenários da
  Tarefa 7.1, além de qualquer fase seguinte, não começam sem nova
  confirmação explícita do usuário.**

## Captura de áudio da aba (participantes) — Fase 3 do PROMPT MESTRE (extensão V.1.4.7)

Complementa o Whisper Local: até V.1.4.6, o pipeline de áudio só
capturava o **microfone do vendedor**; agora também captura o **áudio da
aba** (vozes dos participantes) via `chrome.tabCapture`.

- **Achado**: existiam 2 mecanismos de captura de áudio na extensão — um
  preparado desde abril/2026 (`background.js::handleIniciarCaptura` +
  `offscreen.js`, pensado pra `chrome.tabCapture`) que **nenhum botão da
  UI jamais chamava**, e o mecanismo real usado pelo botão
  ("🎤 Capturar áudio (Whisper)"): `getUserMedia` direto em `content.js`,
  só microfone. Antes de escrever qualquer código, confirme qual caminho
  está de fato conectado à UI — grep pela mensagem (`iniciarCaptura`,
  `whisperChunk`, etc.) no arquivo que dispara o botão, não só onde o
  handler está definido.
- **Por que o microfone continua em `content.js` e não foi movido pro
  offscreen document**: documentos offscreen não têm UI visível para o
  prompt de permissão do Chrome aparecer — pedir `getUserMedia({audio:
  true})` lá dentro tende a falhar silenciosamente. `content.js` roda na
  própria página do Meet, onde o prompt já funciona. `offscreen.js`
  captura só o áudio da aba (`chromeMediaSource: 'tab'`), que **não**
  exige prompt em tempo de execução — só a permissão `tabCapture` no
  manifest.
- **`chrome.tabCapture.getMediaStreamId({ targetTabId })`** só pode ser
  chamado do contexto do service worker (`background.js`) — content
  scripts não têm acesso a `chrome.tabCapture`. Por isso o streamId é
  resolvido em `handleIniciarCaptura` e repassado ao offscreen document
  via mensagem.
- **Capturar áudio da aba intercepta a saída de som** — sem reconectar
  via `AudioContext` (`fonte.connect(audioContext.destination)` em
  `offscreen.js`), o vendedor pararia de ouvir a reunião inteira enquanto
  a captura estivesse ativa.
- **Mesclagem por texto, não por áudio**: mic e aba são gravados e
  transcritos **separadamente** (dois `MediaRecorder`/duas chamadas de
  `/audio-transcricao`), cada um rotulado (`Vendedor`/`Cliente`) e
  commitado no mesmo transcript via `commitarFrase()` — evita toda a
  complexidade de compartilhar `MediaStream` entre `content.js` (página)
  e `offscreen.js` (contexto separado da extensão).
- **Best-effort, nunca bloqueia o que já funcionava**: se `tabCapture`
  falhar (permissão, política do Chrome, etc.), o microfone continua
  gravando normalmente — só a voz do cliente fica sem cobertura extra do
  Whisper (ainda coberta pelas legendas do Google, se o CC estiver
  ligado).
- **Não testado ao vivo ainda** — só validado estaticamente
  (`node --check` nos 3 arquivos). `chrome.tabCapture` e permissões de
  offscreen document só se confirmam de verdade numa reunião real.

## Whisper Local — parte da Fase 3 do PROMPT MESTRE (`agent/whisper_local.py`, V.1.4.63)

Terceira opção de `TRANSCRICAO_PROVEDOR` (junto de `whisper`/`groq`),
self-hosted via `faster-whisper` — roda no próprio servidor, sem enviar
áudio a nenhuma API externa e sem custo por chamada.

- **Escopo desta rodada, confirmado com o usuário**: só a parte
  "self-hosted na VPS" da Fase 3 (Meetily) do prompt mestre — não o
  conceito completo de app rodando na máquina do vendedor. Reaproveita a
  estrutura existente (`TRANSCRICAO_PROVEDOR`) em vez de criar a
  abstração `services/transcription/` sugerida no roadmap original.
- **Já existia antes desta rodada**: captura de áudio do microfone
  (`chrome-extension/offscreen.js`, `getUserMedia`+`MediaRecorder`, 15s
  por chunk) e transcrição em nuvem via Groq/OpenAI
  (`POST /audio-transcricao`). Esta rodada só adicionou o terceiro
  provedor — não mexeu na captura.
- **`agent/whisper_local.py`**: modelo `faster-whisper` carregado como
  singleton por processo (`_get_model()`), recarregado só se
  `WHISPER_LOCAL_MODEL`/`_DEVICE`/`_COMPUTE_TYPE` mudar — mesmo padrão
  de `services/embeddings/factory.py`. `transcrever()` nunca cai
  silenciosamente para um provedor pago em falha (propaga a exceção).
- **`api/main.py::/audio-transcricao`**: refatorado em 3 funções
  (`_transcrever_via_openai`/`_transcrever_via_groq`/
  `_transcrever_via_whisper_local`) despachadas por
  `_TRANSCRICAO_FUNCOES` (dict) — adicionar um provedor novo é 1 função
  + 1 entrada no dict + 1 entrada em `_TRANSCRICAO_PROVEDORES`.
- **Sem chave de API**: `_TRANSCRICAO_PROVEDORES["whisper_local"]["env_key"]
  is None` — `admin_get_transcricao`/`admin_set_transcricao` tratam esse
  caso (nunca bloqueia por "chave não configurada", único provedor onde
  isso não se aplica). `POST /admin/transcricao/teste` chama
  `agent.whisper_local.health_check()` em vez de validar chave.
- **Validado com transcrição real** (não só mockada): modelo `small`
  baixado do Hugging Face e testado contra um WAV real antes do commit
  (~15,8s na primeira ativação, incluindo download).
- **Risco não verificado**: se o `proxy_read_timeout` do nginx da VPS for
  menor que o tempo de download do modelo na primeira ativação, o
  primeiro "Testar conexão"/"Usar este provedor" no dashboard pode
  expirar. Não testado contra o nginx real da VPS ainda.
- **Fora do escopo** (roadmap da Fase 3 continua aberto): captura de
  áudio do sistema/aba (hoje só o microfone do vendedor é capturado —
  falta a voz do cliente via Meet), abstrações formais
  `MeetingCaptureProvider`/`TranscriptionProvider`, Parakeet (opcional no
  prompt mestre), benchmark de WER/latência.

## Promptfoo / Evaluation Suite — Fase 2 do PROMPT MESTRE (`evals/`)

Suite de avaliacao automatizada dos prompts dos agentes, criada
05/09/2026 (harness apenas — nunca rodada de fato ainda, custo real de
IA por execucao). Vive em `evals/` na raiz do repo, com `package.json`
proprio (`promptfoo` como devDependency) — **nao introduz Node.js em
runtime de producao**, e uma ferramenta de dev/CI.

- **Nunca duplica a chamada de IA**: `evals/providers/coach_provider.py`/
  `finance_provider.py` importam e chamam
  `agent.multiagente.coach_agent.analisar_coach`/`finance_agent.
  analisar_finance` diretamente — o provider Python do Promptfoo e so
  uma ponte, roda o mesmo caminho de producao
  (`chamar_ia_com_fallback_claude` -> `api/ai_router.py::chamar_ia_async`).
- **3 configs separadas** (`evals/promptfooconfig.yaml` Coach,
  `promptfooconfig.finance.yaml` Finance, `promptfooconfig.redteam.yaml`
  red team) porque os schemas de saida dos agentes diferem — misturar
  tudo numa config so deixaria as assertions genericas demais.
- **Dataset e sintetico, nao real**: `evals/datasets/coach/
  objections_golden.yaml` tem 22 casos escritos a mao (2 por categoria
  das 11 minimas do prompt mestre) — a tarefa original pede "reunioes
  reais anonimizadas", mas nenhuma sessao ate agora teve acesso ao MySQL
  de producao para extrair/anonimizar transcricoes de verdade. Ver aviso
  no topo do arquivo antes de tratar os resultados como sinal real de
  qualidade do prompt.
- **Rodar exige o venv ativo**: os providers Python importam `agent`/
  `api`, que dependem de `fastapi`/`sqlmodel`/etc. — no Python global do
  sistema (fora do venv) a import falha com `ModuleNotFoundError:
  No module named 'fastapi'`. Ativar `venv\Scripts\activate` antes de
  `npx promptfoo eval`.
- **Custa dinheiro real**: cada teste do dataset dispara uma chamada real
  de IA no provedor configurado no `.env`. Nunca rodar em CI ou
  localmente sem confirmar o custo esperado — nenhuma execucao real foi
  feita ainda.
- `evals/APPROVAL_CRITERIA.md` — criterios formais antes de trocar
  qualquer prompt de `agent/prompt_templates/*.txt` em producao.
- `.github/workflows/llm-evals.yml` roda em PRs que tocam
  `agent/prompt_templates/**`/`agent/multiagente/**`/`api/ai_router.py`/
  RAG/Skills — precisa dos secrets `EVAL_*_API_KEY` configurados no
  GitHub (ainda nao configurados).
- Detalhe completo, decisoes e pendencias explicitas em `evals/README.md`.

## Biblioteca de Inteligência / Knowledge Compiler (Fase 1, V.1.4.52)

Feature grande (roadmap de 6 fases) que transforma documentos comerciais (livros, playbooks, treinamentos, manuais) em conhecimento estruturado reutilizável pelo RAG/Sales Memory/Playbook/Skill. **Esta fase só cobre upload + extração determinística de texto — sem IA ainda.** Atrás de `KNOWLEDGE_COMPILER_ENABLED` (`false` por padrão, endpoints somem via `404`, mesmo padrão do `CLAUDE_ACCOUNT_PILOT`).

- **`services/knowledge_compiler/`**: `get_extractor(mime_type, filename)` despacha para o extractor certo (PDF via pypdf com fallback pdfplumber, DOCX via python-docx, TXT/MD, HTML via BeautifulSoup4). Chunking é por seção real (heading, ou tamanho de fonte detectado no PDF), nunca por corte fixo de caracteres — o LLM nunca abre o arquivo bruto diretamente, sempre recebe texto já extraído deterministicamente.
- **`sanitizer.py::sanitize_document_text()`**: o texto de um documento é dado, nunca instrução — remove só ruído técnico inequívoco (unicode de controle/formatação invisível) e **sinaliza sem remover** trechos que parecem prompt injection (`potential_instruction_injection`). Fases futuras devem bloquear texto sinalizado de virar `system_injection` de uma Skill sem revisão humana.
- **`api/database.py::KnowledgeSource`**: tabela SQLModel (`knowledge_sources`), sem `organization_id` — decisão deliberada (mesma linha da V.1.4.40: SALEIA é uso interno de uma única empresa, multi-tenancy não se aplica hoje).
- **Deduplicação por hash**: `POST /biblioteca/fontes` calcula `content_hash` (sha256) do arquivo — reenviar o mesmo arquivo reaproveita o registro existente em vez de reprocessar.
- **Extração é um passo manual separado** (`POST /biblioteca/fontes/{id}/extrair`), nunca automática no upload — controle de custo/processamento deliberado desde a Fase 1, mesmo sem custo de IA ainda (vale para quando a Fase 2 adicionar compilação com IA).
- **Fase 2 (V.1.4.53) — compilação com IA**: `services/knowledge_compiler/compiler.py::compilar_fonte()` — 1 chamada de IA por seção (não por tipo), extrai `KnowledgeItem`s de 7 tipos (`FRAMEWORK`, `OBJECTION`, `DISCOVERY_QUESTION`, `SCRIPT`, `ANTI_PATTERN`, `DECISION_RULE`, `CASE`). Seções sinalizadas `potential_instruction_injection` (Fase 1) são puladas, não só marcadas. `api/database.py::KnowledgeItem` é **SQLModel** (não raw-pymysql como `sales_memories`/`skills`) — decisão deliberada pra manter testável, já que os módulos raw-pymysql equivalentes não têm nenhum teste hoje. Dedup por embedding (`buscar_knowledge_item_similar`, threshold 0.92) nunca bloqueia nem faz merge automático, só marca `possivel_duplicado_de` — revisão humana decide. Todo item nasce `DRAFT`; só `APPROVED` deve entrar em qualquer fase futura de RAG. Estimativa de custo pré-voo (`estimar_custo_compilacao`, sem IA) reaproveita `api/cost_engine.py`/`api/pricing_catalog.py`, mostrada ao usuário antes de qualquer gasto real.
- **Fase 3 (V.1.4.54) — integração RAG/Skill/Playbook**: `api/database.py::buscar_conhecimento_compilado_similar()` — 3º bloco de RAG em `agent/multiagente/orquestrador.py::analisar_fragmento_multi` (junto de base_conhecimento e Sales Memory), busca só `KnowledgeItem`s `APPROVED`, `top_k=2`. Skill (`agent/skill_resolver.py::gerar_skill_de_knowledge_item`) e Playbook (`agent/playbook_generator.py::gerar_playbook_de_fonte`) são **manuais**, disparados pelo usuário por item/fonte — nunca automáticos, e sem custo de IA (reshape de dados já estruturados). Skill nova entra com triggers amplos (qualquer DISC/estágio/score) e prioridade 60 — `resolver_melhor_skill()` só elege 1 vencedora por prioridade (não é RAG), então competir sem revisão humana antes seria arriscado. **Decisão deliberada**: `KnowledgeItem` NÃO é mapeado para `sales_memory` — duplicaria conteúdo no contexto da IA já que a busca direta em `knowledge_items` cobre isso.
- **Roadmap não iniciado**: Fase 4 (progressive disclosure / context builder com ranking além de cosseno puro), Fase 5 (governança/versionamento/segurança avançada), Fase 6 (UI final + métricas de uso + feedback). Detalhe completo no CHANGELOG (V.1.4.52-1.4.54).
