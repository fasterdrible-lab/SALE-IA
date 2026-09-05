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
- Versão atual: **V.1.4.62** (backend) · extensão Chrome **V.1.4.5** (`chrome-extension/manifest.json`, versionada separadamente)
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
SALEIA — esta é a Fase 1 (Langfuse/Observabilidade), a única concluída
além da Fase 4 (que já existia como "Biblioteca de Inteligência" abaixo).
Fases 2 (Promptfoo), 3 (captura/transcrição local), 5 (Skill Resolver
V2), 6 (Retrieval V2 híbrido), 7 (Agent Router por evento) e a maior
parte da 8 (Pilot Analytics completo) **não foram iniciadas** — antes de
assumir que uma peça desse roadmap existe, grepe o código, não confie só
nesta nota.

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
