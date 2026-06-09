# CHANGELOG — SALEIA
> Registro de todas as implementações, correções e melhorias por versão.

---

## V.1.4.18 — Fix compatibilidade openai + httpx
> Data: 09/06/2026 | Bug fix

### BUG FIX

- `openai==1.35.7` usava parâmetro `proxies` removido no `httpx>=0.28.0` — causava erro `AsyncClient.__init__() got an unexpected keyword argument 'proxies'` ao testar conexão com DeepSeek/OpenAI no dashboard
- `requirements.txt`: `openai==1.35.7` → `openai>=1.52.0` (compatível com httpx 0.28+)

### ARQUIVOS ALTERADOS
- `requirements.txt`
- `api/main.py` (versão `1.4.17` → `1.4.18`)

---

## V.1.4.17 — Migração para VPS Dedicada + Novo Domínio
> Data: 09/06/2026 | Operação de infraestrutura

### INFRAESTRUTURA

- **Nova VPS dedicada**: Hetzner CPX32 — 4 vCPU AMD, 8GB RAM, 160GB SSD, Helsinki (`37.27.214.33`)
- **MySQL local**: banco migrado de servidor remoto compartilhado (`177.104.186.227`, 676ms) para instância local na própria VPS (`127.0.0.1`, ~2ms) — redução de 338x na latência
- **Novo domínio**: `saleia.app.br` criado no Registro.br e delegado ao Cloudflare (proxy ativo); subdomínio `api.saleia.app.br` configurado
- **Deploy**: `git clone` do GitHub + venv Python 3.14 + systemd `TimeoutStopSec=30` (previne SIGKILL em restart)
- **nginx**: configurado para `api.saleia.app.br` com proxy reverso para `127.0.0.1:8000`
- **Dados migrados**: `mysqldump` do banco compartilhado → import na nova instância; tabelas de outros projetos removidas; 5 tabelas SALEIA preservadas (`admin_route_rules`, `alertas_automaticos`, `api_integrations`, `audit_logs`, `base_conhecimento` com 49 docs RAG)

### BUG FIX — Versão no health endpoint

- `/health` e `/monitor/metricas` tinham versão hardcoded defasada (`1.4.14` e `1.4.15`); corrigidos para `1.4.17`

### ARQUIVOS ALTERADOS
- `api/main.py` (versões `1.4.14`/`1.4.15`/`1.4.16` → `1.4.17`)
- `docs/CURRENT_STATE.md`
- `docs/TASKS.md`
- `CHANGELOG.md`

### DEPLOY
Nova VPS ativa em `37.27.214.33`. Domínio `api.saleia.app.br` aguardando propagação DNS (~2h). VPS antiga (`204.168.180.25`) aguarda descomissionamento.

---

## V.1.4.16 — Próxima Melhor Pergunta (next_best_question)
> Data: 09/06/2026 | Desenvolvido com Claude Sonnet 4.6

### BACKEND — Prompt da IA (`agent/prompt_templates/agente_tempo_real.txt`)

- Seção **LOGICA DA PROXIMA MELHOR PERGUNTA** adicionada ao prompt de tempo real
- 9 categorias de pergunta definidas com lógica de prioridade explícita: `descoberta_dor`, `amplificacao_dor`, `impacto_financeiro`, `urgencia`, `prioridade`, `autoridade`, `objecao`, `fechamento`, `recapitulacao`
- Adaptação por perfil DISC: D (resultado/números), I (visão/cenário), S (segurança/processo), C (dados/critérios)
- Campo `next_best_question` adicionado ao schema JSON de resposta com 7 subcampos: `question`, `category`, `objective`, `reason`, `expected_score_impact`, `urgency_level`, `follow_up_question`
- Fallback neutro para contexto insuficiente (< 50 palavras do cliente)

### BACKEND — Processador tempo real (`api/processador_tempo_real.py`)

- `_FALLBACK_NBQ_QUESTION` e `_fallback_next_best_question()` adicionados ao módulo
- `_normalizar_resposta_realtime`: preenche `next_best_question` com fallback se ausente, não-dict ou question vazia
- `_extrair_ultima_analise_memoria`: propaga `next_best_question` do cache persistido
- `analyzeRealtimeMeeting`: acumula cada `next_best_question` real (não-fallback) como `key_moment` com `type="next_best_question"` — aparecem no relatório pós-reunião em `/historico/uso/{meeting_id}`

### BACKEND — Banco de dados (`api/database.py`)

- `registrar_analise_meeting`: `diagnostico_atual` inclui `next_best_question` — persiste junto ao `current_diagnosis` do `MeetingMemory`

### EXTENSÃO CHROME — Sidebar (`chrome-extension/content.js`, `sidebar.css`)

- Seção `#saleia-proxima-fala` substituída por `#saleia-nbq` com bloco estruturado:
  - Badge de categoria + badge de urgência colorido (vermelho/amarelo/cinza)
  - Label "Objetivo:" em 3–5 palavras
  - Pergunta em destaque dourado entre aspas
  - Motivo (por que perguntar agora) em itálico
  - Impacto esperado no score
  - Botão "📋 Copiar pergunta" (usa `navigator.clipboard`)
- Fallback: se `next_best_question` ausente, exibe `proxima_pergunta` / `proxima_fala` / `texto_falavel` sem badges
- Função `renderizarNBQ(dados)` com mapa de labels por categoria e cores por urgência
- CSS: `.saleia-nbq-box`, `.saleia-nbq-badge`, `.saleia-nbq-urgency`, `.saleia-nbq-objetivo`, `.saleia-nbq-pergunta`, `.saleia-nbq-motivo`, `.saleia-nbq-impacto`

### TESTES (`tests/test_next_best_question.py`)

- 20 testes em 4 suítes: `TestNBQFallback`, `TestNBQNormalizacao`, `TestNBQCenariosNegocio`, `TestNBQPersistencia`
- 8 cenários de negócio: sem dor, dor operacional, objeção de preço, urgência alta, score baixo, score alto, DISC C analítico, decisor ausente
- Resultado: **20/20 OK** em 0.2s — sem chamadas reais de IA ou banco

### ARQUIVOS ALTERADOS
- `agent/prompt_templates/agente_tempo_real.txt`
- `api/processador_tempo_real.py`
- `api/database.py`
- `api/main.py` (versão `1.4.15` → `1.4.16`)
- `chrome-extension/content.js`
- `chrome-extension/sidebar.css`
- `tests/test_next_best_question.py` (novo)
- `docs/CURRENT_STATE.md`
- `docs/TASKS.md`
- `CHANGELOG.md`

### DEPLOY
Não deployado — apenas local + GitHub (produção programada).

---

## V.1.4.15 — Monitor: gastos USD, status real, Dev Manual
> Data: 08/06/2026 | Desenvolvido com Claude Sonnet 4.6

### BACKEND — Cache de resultado de teste por provedor (`api/main.py`)

- `_ultimo_teste: dict` — cache em memória que armazena `{ok, ts, detalhe}` por provedor após cada "Testar conexão"
- `POST /admin/api/teste` salva o resultado no cache após cada chamada
- `GET /monitor/metricas` expõe `ultimo_teste` para o frontend
- `admin_testar_provedor`: modelo Gemini corrigido — usa `os.environ.get("GEMINI_MODEL")` em vez de `"gemini-2.0-flash"` hardcoded
- `GET /monitor/metricas` inclui `provedores_status` (circuit breaker + chave) em resposta ao endpoint

### BACKEND — Monitoramento de gastos (`api/ai_router.py`)

- `_counters` ampliado com `custo_total_usd` (global) e `custo_usd` por provedor
- `chamar_ia()` acumula custo estimado USD a cada chamada bem-sucedida
- `snapshot_metricas()` expõe `custo_total_usd` e `custo_usd` por provedor com arredondamento 6 casas

### FRONTEND — Monitor atualizado (`frontend/dashboard.html`)

- Card **💰 Gasto (USD)** com total acumulado desde o último restart
- Coluna **Custo (USD)** na tabela de provedores (valores em dourado)
- Coluna **STATUS ATUAL** usa `ultimo_teste` como fonte principal:
  - ✅ Online / ❌ Offline com tempo decorrido ("agora", "5min atrás")
  - Fallback para status do circuit breaker se nenhum teste foi realizado
- `Sem chave` / `cooldown` / `degradado` exibidos com cores distintas

### FRONTEND — Dev Manual (`frontend/manual_tecnico.html`)

- Reescrito com tema gold/black do sistema
- Seções: Arquitetura, VPS/Infra, Deploy, Variáveis de Ambiente, Estrutura de Arquivos, Endpoints, Roteador de IA, Banco de Dados, Monitor, Segurança, Troubleshoot
- Comandos prontos para copiar (SSH, SCP, diagnóstico)
- Link **🛠️ Dev Manual** adicionado na sidebar do dashboard
- Acessível em `/manual-tecnico` (rota já existia em `main.py`)

### VALIDAÇÕES

- Gasto USD acumulando corretamente por provedor ✅
- STATUS ATUAL reflete resultado do último teste real ✅
- Dev Manual acessível em produção ✅
- Modelo Gemini no teste usa variável de ambiente ✅

### ARQUIVOS ALTERADOS
- `api/main.py`
- `api/ai_router.py`
- `frontend/dashboard.html`
- `frontend/manual_tecnico.html`
- `docs/CURRENT_STATE.md`
- `CHANGELOG.md`

### DEPLOY
- Todos os arquivos deployados via SCP para `/opt/saleia/`
- `systemctl restart saleia` executado

---

## V.1.4.14 — Fix monitor provedores + inativar API + ordem DeepSeek + RAG restaurado
> Data: 08/06/2026 | Desenvolvido com Claude Sonnet 4.6

### BACKEND — Monitor: contador de provedores sem chave (`api/ai_router.py`)

- Provedores pulados por `missing_api_key` agora incrementam `_counters["por_provedor"][name]["falha"]`
- Antes: provedor sem chave aparecia como 0/0 no Monitor (invisível, sem diagnóstico)
- Após: exibe falha no Monitor com log `WARNING: Skipping {name}: API key not configured`

### BACKEND — Fix botão "Inativar" na gestão de APIs (`api/main.py`)

- `admin_listar_provedores`: campo `ativo` agora lê `os.environ.get(env_key)` (estado em runtime) em vez de `_ler_env().get(env_key)` (arquivo .env)
- Causa do bug: ao inativar, o backend zerova `os.environ[env_key]` em memória, mas ao recarregar a lista o endpoint lia o arquivo .env (que ainda tinha a chave) e devolvia `ativo: true` — o botão revertia imediatamente
- Separação: `tem_chave` continua lendo do arquivo (indica se existe chave salva); `ativo` reflete o estado de execução

### VPS — Ordem dos provedores corrigida

- `data/ai_provider_order.json` ajustado para `deepseek → openai → anthropic → gemini`
- Estava `anthropic → openai → gemini → deepseek` — Anthropic resolvia tudo, DeepSeek nunca era chamado
- Monitor agora exibe contadores corretos por provedor

### VPS — Modelo Gemini atualizado

- `GEMINI_MODEL` atualizado de `gemini-2.0-flash` (retornava 404 — modelo descontinuado) para `gemini-2.5-flash`

### VPS — RAG restaurado (OpenAI embeddings)

- Chave `OPENAI_API_KEY` renovada via painel admin
- Embedding `text-embedding-3-small` testado: 1536 dimensões ✅
- Base de conhecimento com 49 transcrições indexadas

### VALIDAÇÕES

- DeepSeek: ✅ Online, PRINCIPAL — primeiro na cadeia
- OpenAI: ✅ Online — fallback + RAG/embeddings funcionando
- Embedding test: `OK dimensoes: 1536` ✅
- Botão "Inativar" atualiza corretamente o estado visual após click ✅

### ARQUIVOS ALTERADOS
- `api/ai_router.py`
- `api/main.py`
- `docs/CURRENT_STATE.md`
- `CHANGELOG.md`

### DEPLOY
- `api/ai_router.py` e `api/main.py` deployados via SCP para `/opt/saleia/`
- `data/ai_provider_order.json` corrigido diretamente na VPS
- `GEMINI_MODEL` atualizado no `.env` da VPS via `sed`
- `systemctl restart saleia` executado

---

## V.1.4.13 — Observabilidade: OTel fix + Grafana Cloud Tempo ativo + Monitor auth
> Data: 07/06/2026 | Desenvolvido com Claude Sonnet 4.6

### BACKEND — Fix instrumentação OpenTelemetry (`api/main.py`)

- `_configurar_opentelemetry()` movida do `on_startup` para o **nível do módulo** (chamada imediatamente após o setup de middlewares)
- Causa do bug: `FastAPIInstrumentor.instrument_app(app)` chamado dentro do `on_startup` era tarde demais — o Starlette já havia finalizado o middleware stack antes da primeira requisição, impedindo a geração de spans para rotas HTTP
- Resultado: traces de todas as rotas FastAPI (`GET /health`, `POST /tempo-real`, etc.) agora chegam ao **Grafana Cloud Tempo** em tempo real
- Versão bumped para `1.4.13`

### FRONTEND — Auth interceptor global (`frontend/dashboard.html`)

- Adicionado interceptor de `window.fetch` no topo do script principal
- Injeta automaticamente `Authorization: Bearer <token>` em todas as requisições para `api.saleia.com.br` ou rotas relativas (`/...`) quando `saleia_token` existe no localStorage
- Elimina a necessidade de passar headers de auth manualmente em cada chamada `fetchJsonWithFallback()`
- Corrige o erro `HTTP 401` na aba Monitor (endpoints `/monitor/metricas` e `/monitor/historico`)

### VALIDAÇÕES

- Grafana Cloud Tempo: query `{}` retorna múltiplos traces `saleia` — `GET /health`, `GET /monitor/metricas`, etc. ✅
- OTel startup log: `"OpenTelemetry ativo → https://otlp-gateway-prod-sa-east-1.grafana.net/otlp"` (2 workers) ✅
- Serviço ativo após deploy: `systemctl is-active saleia` → `active` ✅

### ARQUIVOS ALTERADOS
- `api/main.py`
- `frontend/dashboard.html`
- `docs/CURRENT_STATE.md`
- `CHANGELOG.md`

### DEPLOY
- Arquivos deployados via SCP para `/opt/saleia/`
- `systemctl restart saleia` executado
- `GET /health` → `versao: 1.4.13`, `status: online` ✅

---

## V.1.4.12 — Fase 3 Observabilidade: Histórico SQLite + Alertas threshold + Sparklines
> Data: 07/06/2026 | Desenvolvido com Claude Sonnet 4.6

### BACKEND — Histórico de métricas SQLite (`api/metricas_historico.py` — novo)

- Tabela `metricas_historico` em `data/metricas.db` (SQLite)
- Colunas: `ts`, `banco_latencia`, `banco_modo`, `reunioes_ativas`, `reunioes_hoje`, `chamadas_ia`, `falhas_ia`
- `criar_tabela_metricas()` — cria tabela + índice em ts
- `registrar(banco, ativas, hoje, chamadas, falhas)` — deduplicação por DB: ignora se já existe linha nos últimos 55s (safe com 2 workers uvicorn)
- `obter(horas=6)` — retorna lista ordenada das últimas N horas (máx 24h)
- Limpeza automática: deleta linhas com mais de 25h a cada inserção

### BACKEND — Background task e endpoint historico (`api/main.py`)

- `on_startup` convertido de `def` → `async def` para suportar `asyncio.create_task`
- `_loop_metricas()` async: loop com `asyncio.sleep(60)`, startup delay de 15s
  - Coleta: `db_health()`, `contar_reunioes_ativas()`, `contar_reunioes_hoje()`, `snapshot_metricas()`
  - Grava snapshot via `metricas_historico.registrar()`
  - Chama `alertas.verificar_thresholds(ia_snap, banco)`
  - Tolerante a erros: nunca derruba o loop
- `GET /monitor/historico?horas=N` (requer JWT): retorna série temporal das últimas N horas

### BACKEND — Alertas por threshold (`agent/alertas.py`)

- `_last_alerta: dict` e `_COOLDOWN_S = 3600` — cooldown de 1h por tipo
- `_pode_alertar(chave)` — controla cooldown
- `verificar_thresholds(metricas_ia, banco)` — verifica:
  - Banco offline (erro não nulo)
  - Banco lento (latência > 1500 ms)
  - Taxa de erro IA > 30% (mínimo 10 chamadas)
  - Fallback rate > 50% das chamadas com sucesso

### FRONTEND — Sparklines no Monitor tab (`frontend/dashboard.html`)

- Seção "Histórico — últimas 6h" adicionada no Monitor tab
- `_carregarHistoricoMonitor()` — chama `GET /monitor/historico?horas=6`
- `_sparklineSVG(values, color, unit)` — SVG polyline com gradient fill, dot no valor atual, label de valor
- `_renderHistorico(pontos)` — renderiza 4 sparklines:
  - Latência banco (ms) — amarelo
  - Reuniões ativas — azul
  - Chamadas IA (acumulado) — roxo
  - Reuniões hoje — verde
- Auto-refresh de 60s (alinhado com o background task) enquanto o Monitor tab está aberto

### INFRA — Templates Grafana Cloud (`infra/`)

- `infra/grafana-alloy.alloy` — config pronta para Grafana Alloy com placeholders GRAFANA_CLOUD_URL / USER / API_KEY
- `infra/grafana-setup.sh` — script de instalação do Grafana Alloy na VPS
- Comentários completos com instruções passo a passo

### ARQUIVOS ALTERADOS
- `api/metricas_historico.py` (novo)
- `api/main.py`
- `agent/alertas.py`
- `frontend/dashboard.html`
- `infra/grafana-alloy.alloy` (novo)
- `infra/grafana-setup.sh` (novo)
- `docs/CURRENT_STATE.md`
- `CHANGELOG.md`

### DEPLOY
- 4 arquivos deployados via SCP para `/opt/saleia/`
- `systemctl restart saleia` executado
- Validação: `GET /health` → `versao: 1.4.12`, `status: online`
- Validação: `GET /monitor/historico` → 401 sem token ✅
- Validação: `data/metricas.db` criado (16K), 1° snapshot com latência 678ms (MySQL) ✅

---

## V.1.4.11 — Fase 2 Observabilidade: Métricas IA + aba Monitor
> Data: 07/06/2026 | Desenvolvido com Claude Sonnet 4.6

### BACKEND — Contadores de uso da IA em memória (`api/ai_router.py`)

- `import threading` adicionado
- `_counters_lock = threading.Lock()` + `_counters` dict criados após `_breakers`
- Contadores: `chamadas_total`, `chamadas_sucesso`, `chamadas_falha`, `fallbacks`, `circuit_breaker_aberturas`, `por_provedor[name]{sucesso, falha, total_ms}`
- `chamar_ia()` instrumentado: incrementa contadores no início, em cada sucesso/falha de provedor e no 503 final
- `fallbacks` incrementado quando há ao menos 1 falha antes do sucesso
- `CircuitBreaker.register_failure()` incrementa `circuit_breaker_aberturas` ao abrir
- `snapshot_metricas() → dict` exporta cópia thread-safe com `uptime_segundos` e `latencia_media_ms` por provedor

### BACKEND — Endpoint de métricas (`api/main.py`)

- `snapshot_metricas` importado de `ai_router`
- `GET /monitor/metricas` adicionado após `/health`
  - Requer JWT (`_req_auth`)
  - Retorna: `ia` (snapshot_metricas), `banco` (modo/latencia/erro), `reunioes_ativas`, `reunioes_hoje`, `versao`, `timestamp`
- Versão atualizada para `1.4.11`

### FRONTEND — Aba Monitor (`frontend/dashboard.html`)

- Nav item "📡 Monitor" adicionado antes de "Visual Cenário"
- `<div id="page-monitor">` adicionado antes de `page-configuracoes`
  - Cards: Uptime, Chamadas, Sucesso, Falha, Fallbacks, Circuit Breaks, Reuniões Ativas, Reuniões Hoje
  - Tabela de provedores: Sucesso / Falha / Latência Média / Taxa de Sucesso %
  - Card de banco: modo, latência, status
- `mostrarPagina()` atualizado: `_iniciarMonitor()` ao entrar, `_pararMonitor()` ao sair
- `_iniciarMonitor()` / `_pararMonitor()`: controla `setInterval` de 15 s
- `carregarMonitor()`: chama `GET /monitor/metricas`, renderiza via `_renderMonitor()`
- Contadores zerados ficam com cor `var(--muted)` para indicar inatividade

### ARQUIVOS ALTERADOS
- `api/ai_router.py`
- `api/main.py`
- `frontend/dashboard.html`
- `docs/CURRENT_STATE.md`
- `CHANGELOG.md`

### DEPLOY
- 3 arquivos deployados via SCP para `/opt/saleia/`
- `systemctl restart saleia` executado
- Validação: `GET /health` → `versao: 1.4.11`, `status: online`
- Validação: `GET /monitor/metricas` sem token → 401 ✅; módulo `snapshot_metricas()` testado diretamente → retorna estrutura correta ✅

---

## V.1.4.10 — Toggle de chave API e badge de status persistente
> Data: 07/06/2026 | Desenvolvido com Claude Sonnet 4.6

### DASHBOARD — Botão 👁 nos campos de chave de API (`frontend/dashboard.html`)

**Problema:** Os campos de chave dos provedores (DeepSeek, OpenAI, Anthropic, Gemini) usavam `type="password"` sem toggle de visibilidade. O Chrome tratava o campo como senha e preenchia automaticamente com a última senha salva no gerenciador, sobrepondo a chave real.

**Solução:**
- `autocomplete="new-password"` substituiu `autocomplete="off"` — instrução efetiva para o Chrome não sugerir senhas salvas nesses campos
- Botão 👁 adicionado entre o campo de chave e o botão "Salvar" em cada card de provedor
- Função `toggleVerChave(pid, btn)` adicionada — alterna `input.type` entre `password` e `text`; ícone muda para 🙈 quando visível
- Mesma lógica já existente no campo Groq (V.1.4.5) aplicada aos 4 provedores principais

### DASHBOARD — Badge de status persistente após teste de conexão (`frontend/dashboard.html`)

**Problema:** O botão "Testar conexão" mostrava "✅ Conectado" no span de feedback mas limpava o texto após 4 segundos via `setTimeout`. Não havia forma de confirmar visualmente que a API estava online após o teste.

**Solução:**
- `<span id="status-teste-${p.id}">` adicionado na linha de badges de cada card (ao lado de "Ativo/Inativo" e "Principal")
- `testarProvedor(id)` reescrito:
  - **Sucesso:** badge `✅ Online` (dourado, estilo gold do tema) inserido permanentemente no `status-teste-${id}`; feedback de texto limpo imediatamente
  - **Falha / sem resposta:** badge `❌ Offline` inserido no mesmo slot; mensagem de erro no span de feedback desaparece após 4 s
- O badge persiste até o usuário fechar e reabrir o accordion (quando os cards são re-renderizados)

### ARQUIVOS ALTERADOS

| Arquivo | Tipo |
|---|---|
| `frontend/dashboard.html` | feat: toggle 👁 + `autocomplete="new-password"` + badge `status-teste` permanente + `testarProvedor` reescrito |

---

## T18 — Deploy V.1.4.3–V.1.4.9 na VPS
> Data: 07/06/2026 | Desenvolvido com Claude Sonnet 4.6

### DEPLOY — VPS `204.168.180.25` (`/opt/saleia/`)

17 arquivos enviados via SCP com chave `saleia_vps`:

| Arquivo | Versão |
|---|---|
| `api/main.py` | V.1.4.3+ |
| `agent/sessao_manager.py` | V.1.4.3 |
| `requirements.txt` | V.1.4.5 |
| `frontend/dashboard.html` | V.1.4.8 |
| `frontend/visual-scenario.html` | V.1.4.8 |
| `frontend/cenario.html` | V.1.4.8 |
| `frontend/login.html` | V.1.4.6 |
| `frontend/logo-saleia.png` | V.1.4.6 (novo) |
| `frontend/manual.html` | V.1.4.9 |
| `chrome-extension/background.js` | V.1.4.1 |
| `chrome-extension/manifest.json` | V.1.4.8 |
| `chrome-extension/popup.html` | V.1.4.8 |
| `chrome-extension/popup.js` | V.1.4.1 |
| `chrome-extension/popup.css` | V.1.4.8 |
| `chrome-extension/sidebar.css` | V.1.4.8 |
| `chrome-extension/content.css` | V.1.4.8 |
| `chrome-extension/content.js` | V.1.4.8 |

**Resultado:**
- `pip install -r requirements.txt` — OK (groq instalado)
- `systemctl restart saleia` — `active`
- `GET /health` — `online`, 4 provedores ok (anthropic/openai/gemini/deepseek)
- `GET /dashboard` — 200
- `GET /logo-saleia.png` — 200

**Pendente após deploy:**
- Reinstalar extensão Chrome no navegador (tema gold/black + multi-clientes)

---

## V.1.4.9 — Manual de instruções atualizado para V.1.4.8
> Data: 06/06/2026 | Desenvolvido com Claude Sonnet 4.6

### DOCS — Reescrita completa do manual (`frontend/manual.html`)

Manual atualizado de V.1.4.5 para V.1.4.8 com todas as funcionalidades documentadas:

- **Versão** atualizada para 1.4.8 no badge do cabeçalho e rodapé
- **Nova seção 7 — Cenário do Cliente:** slides interativos, botões de condução (DISC, Recapitulação, Diagnóstico, Fechamento), uso em segundo monitor
- **Nova seção 8 — Visual Cenário AI:** as três colunas (Cliente / Cenário Atual / Cenário Futuro), como vincular à reunião (link completo ou só o código), passo a passo de uso, tabela de botões, fullscreen e comparação, histórico, aviso DALL-E 3
- **Seção 3 — Extensão Chrome:** documentado suporte a múltiplos clientes no modal Participantes (botão **+ Adicionar**, botão ✕, persistência via `chrome.storage.local`)
- **Seção 10 — Relatório:** documentado campo multi-clientes na análise manual (Dashboard → Relatórios) com explicação de por que informar vários nomes melhora a precisão
- **Seção 11 — Dashboard:** adicionados links para Cenário do Cliente e Visual Cenário AI
- **Seção 14 — FAQ:** novas entradas para multi-clientes, botão Início do Visual Cenário, Visual Cenário sem meeting_id, análise de reuniões já encerradas
- **Nav sticky:** link "Visual Cenário" adicionado na barra de navegação
- **Bloco de ações rápidas** no rodapé: botões diretos para Dashboard, Visual Cenário AI, Status e Login

**Arquivo alterado:**
- `frontend/manual.html` — reescrita completa, V.1.4.5 → V.1.4.8

---

## V.1.4.8 — Multi-clientes, correções de navegação e redesign extensão
> Data: 06/06/2026 | Desenvolvido com Claude Sonnet 4.6

### FRONTEND — Múltiplos clientes na análise (`dashboard.html`)
- Campo "Cliente" substituído por lista dinâmica de clientes
- Botão **+ Cliente** permite adicionar quantos clientes forem necessários
- Botão ✕ remove clientes extras (mínimo 1 sempre presente)
- `analisar()` coleta array `clientes[]` de `_clientesLista`
- `detectarFalas()` atualizado: recebe `nomes.clientes[]` e identifica fala de qualquer cliente pelo nome
- Speaker das falas preserva nome original (não colapsa tudo em um "Cliente" único)

### FRONTEND — Correção botão "Início" (`visual-scenario.html`)
- Botão "← Início" corrigido: volta para `/cenario/{meeting_id}` em vez de `/` (que deslogava)
- Fallback para `/dashboard` quando não há meeting ID
- Extrai só o código da reunião mesmo que o `meetingId` seja a URL completa do Google Meet (`https://meet.google.com/xxx` → `xxx`)

### FRONTEND — Paleta gold/black na tela Cenário do Cliente (`cenario.html`)
- Variáveis CSS: `--bg #0A0A0A`, `--card #111111`, `--card2 #000000`, `--borda rgba(212,175,55,0.18)`
- `--verde/#azul/#roxo` → `#D4AF37`/`#F5C542` (dourado)
- Header, dropdowns, overlay, painéis, chips e botões atualizados

### EXTENSÃO CHROME — Paleta gold/black
**`popup.css`:** Background `#0A0A0A`, header gradiente preto, teal `#14B8A6` → `#D4AF37`, laranja → dourado, toggle/inputs/botões/links em ouro

**`sidebar.css`:** Fundo `rgba(0,0,0,0.97)`, bordas douradas, seções/recap/badges/temperatura/modal em ouro, dot pulsante dourado

**`content.css`:** Background, header, cards, hover — padrão preto/dourado

### EXTENSÃO CHROME — Multi-clientes no modal Participantes (`content.js`)
- Modal "Participantes": campo "Nome do cliente" → lista dinâmica **"Clientes"** com botão **"+ Adicionar"**
- Botão ✕ por linha remove cliente (mínimo 1)
- Event delegation via `container.onclick`/`container.oninput` com `data-ri`/`data-ci` (fix: inline `onclick` não funciona no mundo isolado do content script)
- `salvarParticipantes()`: lê inputs diretamente via `querySelectorAll('[data-ci]')` para garantir valores corretos
- `rotuloParticipante()`: identifica fala contra todos os clientes do array
- `atualizarResumoParticipantes()`: exibe `Vendedor -> Cliente1, Cliente2`
- Migração automática de dados antigos: `{ cliente: "X" }` → `{ clientes: ["X"] }`
- `estado.participantes.clientes` persiste via `chrome.storage.local`

**Arquivos alterados:**
- `frontend/dashboard.html` — multi-clientes + menu "Visual Cenário"
- `frontend/visual-scenario.html` — botão Início corrigido + paleta gold
- `frontend/cenario.html` — paleta gold/black completa
- `chrome-extension/popup.css` — paleta gold/black
- `chrome-extension/sidebar.css` — paleta gold/black
- `chrome-extension/content.css` — paleta gold/black
- `chrome-extension/content.js` — multi-clientes com event delegation

---

## V.1.4.7 — Visual Cenário: paleta gold/black + correção de nomenclatura
> Data: 06/06/2026 | Desenvolvido com Claude Sonnet 4.6

### FRONTEND — Padronização visual da tela Visual Cenário

**`frontend/visual-scenario.html` — redesign de cores:**
- Paleta CSS atualizada para o padrão gold/black do dashboard:
  - `--bg: #0A0A0A`, `--card: #111111`, `--field: #1A1A1A`
  - `--border: rgba(212,175,55,0.18)`, `--primary: #D4AF37`, `--secondary: #F5C542`
  - `--muted: #888`, `--gold: #D4AF37`
- Header: fundo `#000000` (era `#201E30` roxo)
- Action bar: fundo `rgba(0,0,0,.4)` (era roxo semi-transparente)
- Botão primário: gradiente `#A67C00 → #D4AF37 → #F5C542`, texto preto (era teal)
- Ícones de painel: dourado sutil (era azul/teal)
- Chips de contexto (`chip-disc`, `chip-maturity`): ouro (era azul/teal)
- Toast de sucesso: dourado (era teal)
- Loading overlay: `rgba(0,0,0,.92)` (era roxo escuro)
- Spinner border: `rgba(212,175,55,.2)` (era teal)
- Modal fullscreen: fundo `#000000` (era `#0A0914`)
- Modal crop: fundo `#000000` + botão confirmar em gradiente dourado
- Hover dos painéis: borda dourada `rgba(212,175,55,.35)`
- Título `<title>` e `<h1>`: "Visual **Cenário** AI" (era "Visual Scenario AI")

**`frontend/dashboard.html` — correção de nomenclatura:**
- Item do menu lateral: "Visual Scenario" → "Visual Cenário"

---

## V.1.4.6 — Redesign Visual Premium (Gold/Black Theme)
> Data: 06/06/2026 | Desenvolvido com Claude Sonnet 4.6

### FRONTEND — Redesign completo da identidade visual

Aplicada nova paleta de cores premium em toda a plataforma, sem alteração de funcionalidades.

**Paleta adotada:**
- Dourado metálico: `#D4AF37` (nova cor primária — substituiu teal `#14B8A6`)
- Dourado brilhante: `#F5C542` (secundária — substituiu azul `#38BDF8`)
- Preto absoluto: `#000000` (sidebar)
- Preto premium: `#0A0A0A` (fundo geral)
- Cinza grafite: `#111111` (cards)
- Cinza tecnológico: `#1A1A1A` (inputs/fields)

**`dashboard.html` — mudanças visuais:**
- Todas as variáveis CSS atualizadas (`--bg`, `--card`, `--field`, `--border`, `--primary`, `--secondary`)
- Sidebar: fundo `#000000` (antes roxo `#201E30`)
- Nav itens ativos/hover: dourado `rgba(212,175,55,...)` (antes laranja `rgba(249,115,22,...)`)
- Botão principal: gradiente dourado `#A67C00 → #D4AF37 → #F5C542` (antes laranja/vermelho)
- Badges e indicadores: dourado (antes teal/azul)
- Accordion aberto: borda dourada `rgba(212,175,55,.35)`
- Ícones de accordion: fundo dourado discreto
- Background tecnológico: grid de linhas douradas sutis + glow radial no topo
- Tipografia: `Inter` + `Sora` via Google Fonts (antes Segoe UI)
- Focus inputs: glow dourado `rgba(212,175,55,.12)`

**`login.html` — mudanças visuais:**
- Logo SALEIA original (PNG premium 3D dourado) integrado via Nginx static location
- Imagem exibida com `object-fit: cover` + `object-position: top` mostrando S + SALEIA + tagline
- Removidos: badge de versão, taglines duplicadas, espaçamentos excessivos
- Padding do body reduzido para melhor fit em mobile

**Nginx (`/etc/nginx/sites-enabled/saleia`) — nova location:**
```nginx
location = /logo-saleia.png {
    alias /opt/saleia/frontend/logo-saleia.png;
    add_header Cache-Control "public, max-age=2592000";
}
```

**Arquivos alterados:**
- `frontend/dashboard.html` — redesign CSS completo
- `frontend/login.html` — logo + layout compacto
- `frontend/logo-saleia.png` — logo PNG premium adicionado (novo)

---

## V.1.4.5 — SDK Groq Oficial, Toggle de Chave e Separação de Ações
> Data: 06/06/2026 | Desenvolvido com Claude Sonnet 4.6

### BACKEND — SDK oficial Groq

Substituído o workaround `OpenAI(base_url="https://api.groq.com/openai/v1")` pelo SDK oficial `groq>=0.9.0`:

- Pacote `groq>=0.9.0` adicionado ao `requirements.txt`
- Modelo atualizado de `whisper-large-v3-turbo` para `whisper-large-v3` (maior qualidade)
- Arquivo passado como tupla `(caminho, bytes)` conforme documentação oficial Groq
- Flag `temperature=0` e `response_format="verbose_json"` adicionados

### BACKEND — Flag `apenas_salvar` no endpoint de transcrição

`POST /admin/transcricao/config` aceita novo campo `apenas_salvar: bool`:

- `apenas_salvar: true` → salva a chave Groq no `.env` **sem** mudar o provedor ativo
- `apenas_salvar: false` (padrão) → comportamento anterior: salva chave e ativa o provedor
- Validação de tamanho mínimo da chave removida (qualquer string não vazia é aceita)

### DASHBOARD — Botão 👁 mostrar/ocultar chave Groq

- Botão 👁 ao lado do campo de senha: alterna entre `type="password"` e `type="text"`
- Ícone muda para 🙈 quando a chave está visível
- Função `toggleVerChaveGroq()` adicionada

### DASHBOARD — Correção crítica em `salvarChaveGroq`

- Substituído `fetch(API + '/admin/...')` por `fetchJsonWithFallback('/admin/...')` — corrige falha silenciosa quando `API` aponta para URL incorreta
- `apenas_salvar: true` enviado: salvar chave não muda mais o provedor ativo
- Após salvo com sucesso, recarrega o accordion automaticamente via `carregarTranscricaoConfig()`
- Mensagem de erro agora inclui o status HTTP (`Erro 401`, `Erro 400`, etc.)

### EXTENSÃO CHROME — Visibilidade de erros de transcrição

`enviarChunkWhisper` em `content.js` agora exibe erros do backend na barra de status da sidebar:

- `data.ok === false` ou `data.error` → `setAudioStatus('⚠️ ' + msgErro, '#ff9900')`
- Antes: erros apenas no `console.warn`, invisíveis ao usuário

### ARQUIVOS ALTERADOS

| Arquivo | Tipo |
|---|---|
| `requirements.txt` | feat: `groq>=0.9.0` |
| `api/main.py` | feat: SDK Groq oficial; flag `apenas_salvar`; validação de chave relaxada |
| `frontend/dashboard.html` | feat: toggle 👁; fix `fetchJsonWithFallback`; `apenas_salvar: true` |
| `chrome-extension/content.js` | fix: erros de transcrição exibidos na sidebar |

---

## V.1.4.4 — Transcrição de Áudio com Whisper e Groq
> Data: 06/06/2026 | Desenvolvido com Claude Sonnet 4.6

### BACKEND — Roteamento de provedor em `/audio-transcricao`

O endpoint `/audio-transcricao` agora lê `TRANSCRICAO_PROVEDOR` do `.env` para decidir qual API usar:

| Valor | Provedor | Modelo | Chave necessária |
|---|---|---|---|
| `whisper` (padrão) | OpenAI Whisper | `whisper-1` | `OPENAI_API_KEY` |
| `groq` | Groq | `whisper-large-v3-turbo` | `GROQ_API_KEY` |

A Groq usa a mesma interface da OpenAI SDK com `base_url="https://api.groq.com/openai/v1"` — nenhuma dependência nova. O rótulo salvo na transcrição bruta passou de `[Whisper]` para `[Whisper]` ou `[Groq]` conforme o provedor ativo. O response agora inclui `provedor`.

### BACKEND — Novos endpoints de configuração

| Endpoint | Método | Descrição |
|---|---|---|
| `/admin/transcricao/config` | GET | Retorna provedores disponíveis, provedor ativo, modelo e se a chave existe |
| `/admin/transcricao/config` | POST | Define o provedor ativo; aceita `groq_api_key` opcional para salvar a chave Groq |

Ambos exigem JWT admin.

### DASHBOARD — Novo accordion "Transcrição de Áudio"

Adicionado entre "Configuração de APIs" e "Base de Conhecimento" na página Configurações:

- Cards para Whisper (OpenAI) e Groq com nome, modelo e nota informativa
- Card do Groq exibe campo de senha para colar a `GROQ_API_KEY`
- Botão "Usar este provedor" envia chave (se preenchida) e ativa o provedor
- Feedback inline de sucesso/erro; recarrega após ativação para refletir novo estado

### ARQUIVOS ALTERADOS

| Arquivo | Tipo |
|---|---|
| `api/main.py` | feat: `_TRANSCRICAO_PROVEDORES`, `GET/POST /admin/transcricao/config`, roteamento em `/audio-transcricao` |
| `frontend/dashboard.html` | feat: accordion `acc-transcricao`, funções `carregarTranscricaoConfig`, `renderizarTranscricaoConfig`, `ativarTranscricaoProvedor` |
| `.env.example` | docs: `GROQ_API_KEY` e `TRANSCRICAO_PROVEDOR` |

---

## V.1.4.3 — Correção de Bugs e Refatoração
> Data: 06/06/2026 | Desenvolvido com Claude Sonnet 4.6

### BUGS CORRIGIDOS

| # | Arquivo | Problema | Solução |
|---|---|---|---|
| 1 | `agent/sessao_manager.py` | `exportar_para_base_conhecimento` usava coluna `conteudo` no CREATE TABLE e INSERT — a coluna real é `texto`; toda exportação de sessão para a Base de IA falhava silenciosamente | Renomeado `conteudo` → `texto` na DDL e no INSERT |
| 2 | `agent/sessao_manager.py` | Invalidação do cache RAG após exportação chamava `_cache.clear()` — isso limpa o dict em memória mas deixa `_cache is not None`, fazendo `_carregar_cache()` retornar `{}` sem recarregar e causando `KeyError` na próxima consulta | Substituído por `invalidar_cache()` (que seta `_cache = None`) |
| 3 | `api/main.py` | `PATCH /admin/api/provedores/{pid}/status` com `ativo=False` não propagava a desativação ao `os.environ` — provedor continuava sendo usado pelo `ai_router` | Adicionado `os.environ[env_key] = ""` quando `ativo=False` e `os.environ[env_key] = chave` quando `ativo=True` |
| 4 | `api/main.py` | Importação de `db_salvar`, `db_listar`, `db_ultimo` duplicada nas linhas 33 e 67 | Removida a segunda importação (linha 67) |
| 5 | `api/main.py` | `admin_definir_principal` setava `os.environ["PROVEDOR_PREFERIDO"]` manualmente logo após chamar `_salvar_env_key` que já faz isso internamente | Removida linha redundante |

### ARQUIVOS ALTERADOS

| Arquivo | Tipo |
|---|---|
| `agent/sessao_manager.py` | fix: `conteudo` → `texto` em `exportar_para_base_conhecimento`; `invalidar_cache()` correto |
| `api/main.py` | fix: propagação de status do provedor; remoção de import duplicado e `os.environ` redundante |

---

## V.1.4.2 — Filtro por Provedor de IA em Reuniões
> Data: 06/06/2026 | Desenvolvido com Claude Sonnet 4.6

### BACKEND — `GET /relatorios` com campo `provedor`

O endpoint `/relatorios` agora inclui o campo `provedor` em cada item da lista.

**Origem do valor:** extraído de `_provedor_ia` armazenado dentro de `dados.recapitulacao` (ou `dados.perfil_disc` / `dados.diagnostico_financeiro` como fallback). Funciona tanto para a fonte SQLite quanto para o fallback de arquivos JSON.

**Valores possíveis:** `deepseek`, `openai`, `anthropic`, `gemini` ou `""` (vazio para relatórios anteriores que não tinham o campo).

### FRONTEND — Filtro de provedor no toolbar de Reuniões (`frontend/dashboard.html`)

- `<select id="filtro-provedor">` adicionado ao toolbar após o filtro de propensão, com opções: Todos os provedores / DeepSeek / OpenAI / Anthropic / Gemini.
- `filtrarReunioes()` atualizada para incluir o filtro por `r.provedor`.
- `limparFiltrosReunioes()` atualizada para resetar o select de provedor.
- `cardReuniaoHTML()` exibe o nome do provedor como label discreta (`var(--muted)`) ao lado da data/score no card de cada reunião.

### ARQUIVOS ALTERADOS

| Arquivo | Tipo de alteração |
|---|---|
| `api/main.py` | feat: campo `provedor` no response de `GET /relatorios` (SQLite + fallback JSON) |
| `frontend/dashboard.html` | feat: select filtro-provedor, filtrarReunioes, limparFiltrosReunioes, cardReuniaoHTML |

---

## V.1.4.1 — Recuperação de Senha por E-mail + Correção de Bug Crítico na Extensão Chrome
> Data: 29/05/2026 | Desenvolvido com Claude Sonnet 4.6

---

### RECUPERAÇÃO DE SENHA — IMPLEMENTAÇÃO REAL (`api/main.py`, `agent/sessao_manager.py`, `agent/email_service.py`)

**Problema anterior:** `POST /auth/recuperar-senha` era um stub que apenas confirmava recebimento sem enviar e-mail.

**Solução completa:**

**Novo módulo `agent/email_service.py`:**
- Envio de e-mail HTML via `smtplib` (stdlib — nenhuma dependência nova)
- Configurado por variáveis de ambiente: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM`, `APP_BASE_URL`
- Link formatado com botão estilizado no tema SALEIA (dark)
- Retorna `True`/`False` para controle do caller; falha não derruba o endpoint

**Migração de banco — `agent/sessao_manager.py`:**
- `migrar_colunas_usuarios()` — adiciona `reset_token VARCHAR(128)` e `reset_token_exp DATETIME` via `ALTER TABLE` idempotente (ignora erro se coluna já existe)
- Chamada no startup junto com `criar_tabela_usuarios()`

**`api/main.py` — 3 novos endpoints + 1 substituição:**

| Endpoint | Método | Descrição |
|---|---|---|
| `/auth/recuperar-senha` | POST | **Substituído**: gera token seguro (`secrets.token_urlsafe(32)`), expira em 1h, salva no banco, envia e-mail em `BackgroundTask`. Resposta sempre neutra. |
| `/reset` | GET | Serve página HTML inline com formulário de nova senha. Retorna 400 se token ausente. |
| `/auth/redefinir-senha` | POST | Valida token + expiração, aplica `bcrypt`, limpa `reset_token` e `reset_token_exp`. |

**Novo model Pydantic:**
```python
class AuthRedefinirSenhaRequest(BaseModel):
    token: str
    nova_senha: str
```

**Fluxo completo:**
1. Usuário clica "Recuperar senha" no `login.html`
2. `POST /auth/recuperar-senha { email }` → gera token, salva no banco, envia e-mail em background
3. Usuário recebe e-mail com link `https://api.saleia.com.br/reset?token=<token>`
4. `GET /reset?token=...` → página HTML com formulário de nova senha
5. `POST /auth/redefinir-senha { token, nova_senha }` → valida, aplica hash bcrypt, limpa token
6. Usuário volta ao login

**`.env.example` atualizado:**
```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=seu-email@gmail.com
SMTP_PASS=sua-senha-de-app-google
EMAIL_FROM=noreply@saleia.com.br
APP_BASE_URL=https://api.saleia.com.br
```

---

### EXTENSÃO CHROME — CORREÇÃO DE BUG CRÍTICO (`chrome-extension/background.js`)

**Problema:** O handler `abrirCenarioComFoto` no `background.js` lia `msg.foto` que sempre era `undefined`. O `content.js` grava a foto em `chrome.storage.local['saleia_foto_pendente']` e **não a inclui na mensagem**. Resultado: `_aplicarDataUrl()` era chamado com `undefined` e a foto do cliente nunca aparecia no Visual Scenario.

**Correção:** O handler agora lê a foto de `chrome.storage.local` após o tab carregar:
```js
chrome.storage.local.get(['saleia_foto_pendente'], function (result) {
    var fotoData = result.saleia_foto_pendente ? result.saleia_foto_pendente.foto : null;
    if (!fotoData) return;
    chrome.scripting.executeScript({ ..., args: [fotoData] });
});
```

---

### EXTENSÃO CHROME — ATUALIZAÇÕES MENORES

| Arquivo | Alteração |
|---|---|
| `chrome-extension/manifest.json` | Versão atualizada: `1.2.0` → `1.4.1` |
| `chrome-extension/popup.html` | Versão no rodapé atualizada de `v1.0.0` para `v1.4.1` |
| `chrome-extension/popup.js` | Versão passa a ser lida dinamicamente via `chrome.runtime.getManifest().version` (nunca mais precisa de atualização manual) |

---

### DOCUMENTAÇÃO — CONTEXTO MÍNIMO CRIADO

| Arquivo | Conteúdo |
|---|---|
| `docs/CURRENT_STATE.md` | Estado completo do projeto: ambiente, deploy, funcionalidades, provedores, pendências |
| `docs/TASKS.md` | Fila operacional: T01–T10 concluídas, T11 concluída, T12–T13 pendentes |
| `docs/ARCHITECTURE.md` | Atualizado com todos os endpoints da V.1.4.0/V.1.4.1 (auth, admin, histórico, cenário, base) |

---

### ARQUIVOS ALTERADOS NESTA VERSÃO

| Arquivo | Tipo de alteração |
|---|---|
| `agent/email_service.py` | **novo** — módulo SMTP para recuperação de senha |
| `agent/sessao_manager.py` | feat: `migrar_colunas_usuarios()` — colunas `reset_token` e `reset_token_exp` |
| `api/main.py` | feat: `POST /auth/recuperar-senha` real, `GET /reset`, `POST /auth/redefinir-senha`, `AuthRedefinirSenhaRequest`; startup chama `migrar_colunas_usuarios()` |
| `.env.example` | feat: vars SMTP adicionadas |
| `chrome-extension/background.js` | fix: `abrirCenarioComFoto` lê foto de `chrome.storage.local` em vez de `msg.foto` |
| `chrome-extension/manifest.json` | chore: versão `1.2.0` → `1.4.1` |
| `chrome-extension/popup.html` | chore: versão `v1.0.0` → `v1.4.1` |
| `chrome-extension/popup.js` | chore: versão dinâmica via `getManifest()` |
| `docs/CURRENT_STATE.md` | docs: atualizado para V.1.4.1 |
| `docs/TASKS.md` | docs: T11 concluída, T12–T13 adicionadas |
| `docs/ARCHITECTURE.md` | docs: endpoints V.1.4.0/V.1.4.1 documentados |

---

## V.1.4.0 — Auth, Admin, Histórico de Uso, Filtros, Smoke Tests, Visual Scenario DALL-E 3
> Data: 28/05/2026 | Desenvolvido com Claude Sonnet 4.6

---

### AUTENTICAÇÃO (`api/main.py`, `agent/sessao_manager.py`)

**Endpoints implementados e validados:**
- `POST /auth/login` — verifica senha (bcrypt), gera JWT 72h, atualiza `ultimo_acesso`
- `POST /auth/cadastro` — valida dados, hash bcrypt, primeiro usuário vira admin/ativo, demais operador/pendente
- `POST /auth/recuperar-senha` — stub seguro (não vaza se e-mail existe ou não)

**Tabela `usuarios` criada automaticamente no startup** via `criar_tabela_usuarios()` adicionada a `agent/sessao_manager.py` e chamada em `on_startup`. Schema: `id UUID`, `nome`, `email UNIQUE`, `senha_hash`, `perfil`, `plano`, `status`, `data_cadastro`, `ultimo_acesso`.

**Dependências adicionadas a `requirements.txt`:** `bcrypt>=4.0.0`, `PyJWT>=2.8.0`.

**Helpers de autorização:**
- `_req_auth(authorization)` — verifica JWT, aceita qualquer perfil autenticado
- `_req_admin(authorization)` — verifica JWT e exige `perfil == "admin"`

---

### CONDUÇÃO — AUTENTICAÇÃO ADICIONADA (`api/main.py`)

**Problema anterior:** `POST /cenario/{meeting_id}/conducao` não exigia autenticação e tinha bug silencioso de `_get_conn` não importado em `_buscar_conteudo_programa`.

**Correções:**
- Adicionado `Header` ao import FastAPI no topo do arquivo
- Endpoint recebe `authorization: str | None = Header(default=None)` e chama `_req_auth` como primeira linha
- Validação de `meeting_id` adicionada (padrão `xxx-xxxx-xxx`)
- `_get_conn` importado localmente em `_buscar_conteudo_programa` (bug: caía no `except` e retornava sempre placeholder)

---

### ADMIN — GERENCIAMENTO DE USUÁRIOS E APIs (`api/main.py`)

**Endpoints de usuários** (todos com `_req_admin`):
| Endpoint | Ação |
|---|---|
| `GET /admin/usuarios` | Lista todos com perfil, plano, status, datas |
| `PATCH /admin/usuarios/{uid}/perfil` | Altera perfil (admin/gerente/operador/usuario) |
| `PATCH /admin/usuarios/{uid}/plano` | Altera plano (free/pro/enterprise) |
| `PATCH /admin/usuarios/{uid}/status` | Altera status (ativo/inativo/pendente) |
| `PATCH /admin/usuarios/{uid}/inativar` | Atalho: status → inativo |
| `PATCH /admin/usuarios/{uid}/reativar` | Atalho: status → ativo |
| `PATCH /admin/usuarios/{uid}/resetar-senha` | Reset para "Saleia@2025" |
| `DELETE /admin/usuarios/{uid}` | Remove permanentemente |

**Endpoints de APIs** (todos com `_req_admin`):
| Endpoint | Ação |
|---|---|
| `GET /admin/api/provedores` | Lista provedores com status de chave (sem expor a chave) |
| `POST /admin/api/provedores/{pid}/chave` | Salva chave no `.env` + `os.environ` |
| `POST /admin/api/teste` | Testa conectividade real com o SDK do provedor |
| `PATCH /admin/api/provedores/{pid}/status` | Ativa/inativa provedor |
| `POST /admin/api/principal` | Define provedor preferido (persiste em `.env`) |

---

### HISTÓRICO DE USO (`api/main.py`)

**Novos endpoints:**
- `GET /historico/uso` — lista últimas 100 reuniões com `custo_estimado_usd`, `score_final`, `disc_identificado`, `num_analises`, `num_key_moments`, `num_eventos`. Requer JWT. Cruza `MeetingMemory` (SQLModel) com `sessoes` (MySQL raw). Retorna `custo_total_usd` acumulado.
- `GET /historico/uso/{meeting_id}` — detalhe de uma reunião: `score_history[]` completo, `key_moments[]`, `eventos[]`, infos da sessão. Valida formato do `meeting_id`.

---

### PÁGINA HISTÓRICO NO DASHBOARD (`frontend/dashboard.html`)

**Nav item:** `📈 Histórico` adicionado à sidebar entre Analisar e Base de IA.

**Página `page-historico`:**
- Métricas resumidas: total de reuniões, custo total estimado (U$), score médio
- Lista de cards com meeting_id, data, número de análises, custo, score e DISC

**Página `page-historico-detalhe`** (ao clicar em uma reunião):
- Card de metadados (meeting_id, custo, score, análises, DISC, iniciada_em)
- Gráfico de barras da evolução do score ao longo da reunião
- Momentos-chave com tipo, fala, importância e timestamp
- Eventos com ícones por tipo (💰 pricing, 🛡️ objeção, ⚠️ alerta, 🔔 recap)

---

### FILTROS DE REUNIÕES — MELHORIAS (`frontend/dashboard.html`)

**Adicionado ao toolbar de Reuniões:**
- `input[type=date]` "De" e "Até" — filtro por intervalo de data (`r.data` ou `r.criado_em`)
- Botão `✕ Limpar` — zera todos os filtros de uma vez
- Contador `"X de Y reuniões"` aparece quando qualquer filtro está ativo

**CSS:** `input[type=date]` incluído nas regras dark (`color-scheme: dark` para o calendário do sistema).

**Nota:** filtro por provedor não implementado — campo ausente no response de `/relatorios`.

---

### SMOKE TESTS (`tests/test_smoke.py`)

**8 testes automatizados**, sem dependências externas (DB e IA mockados):

| Endpoint | Testes |
|---|---|
| `GET /health` | status 200, shape `{status, servico, versao, timestamp}`, status ∈ `{online, degradado}` |
| `GET /dashboard` | status 200, `content-type: text/html`, HTML contém `SALEIA` |
| `POST /recapitulacao-manual` | status 200, chaves `{recapitulacao, perfil_disc, diagnostico_financeiro, gerado_em}`, rejeita `transcricao: ""` com 400 |

**Resultado:** 8/8 OK em 1.1s.

**Como rodar:** `.\venv\Scripts\python.exe -m unittest tests.test_smoke -v`

---

### VISUAL SCENARIO AI — PERSISTÊNCIA (`agent/visual_scenario.py`)

**Problema anterior:** `ImageGenerator` retornava URLs do CDN da OpenAI que expiram após 1 hora. O botão `🕒 Histórico` em `visual-scenario.html` quebrava na segunda visita.

**Solução:** `response_format="b64_json"` — a imagem retorna como base64 e é armazenada como `data:image/png;base64,...` diretamente nas colunas `current_url`/`future_url` (`LONGTEXT`) do MySQL. Imagens persistem indefinidamente.

Timeout aumentado de 60s para 90s (DALL-E 3 pode levar 30–60s por imagem).

**Fluxo completo:**
1. `PainExtractor.extract()` — extrai segmento, dores, DISC, maturidade, urgência, descrições de ambiente via IA de texto
2. `PromptBuilder.build_current/future()` — monta prompts cinematográficos personalizados
3. `ImageGenerator.generate()` × 2 em paralelo (`asyncio.gather`) via DALL-E 3
4. `_salvar_cenario()` — persiste no MySQL
5. Retorna URLs (data URIs) + contexto + pain points

**Acesso:** `cenario.html` → botão `🎬 Visual` → `visual-scenario.html?meeting=<id>`

---

## V.1.3.6 — Configurações Accordion + Condução Conectada aos Prompts + RAG Corrigido
> Data: 27/05/2026 | Desenvolvido com Claude Sonnet 4.6

---

### CONFIGURAÇÕES — REDESIGN EM ACCORDION (`frontend/dashboard.html`)

**Problema anterior:** Página Configurações exibia todos os cards abertos e expandidos simultaneamente, ocupando muito espaço e carregando dados desnecessariamente.

**Solução:** Substituição dos cards planos por acordeão colapsável.

**Novo comportamento:**
- 3 seções colapsáveis com ícone + título + subtítulo + chevron (▾)
- Clique no cabeçalho abre/fecha — chevron rotaciona
- **Lazy-load:** cada seção carrega os dados apenas na primeira abertura (não dispara requisições desnecessárias)
- Ao re-navegar para Configurações: todas as seções fecham e o cache de load é resetado (dados sempre frescos)
- Rodapé fixo: status do backend (dot online/offline) + endpoint + versão + copyright

**Seções:**
| Ícone | Seção | Badge | Conteúdo ao abrir |
|---|---|---|---|
| 👥 (laranja) | Gerenciamento de Usuários | Admin | Tabela de usuários com selects inline |
| 🔑 (azul) | Configuração de APIs | Admin | Cards dos provedores de IA |
| 📚 (teal) | Base de Conhecimento | — | Contagem de documentos + botão ir à Base de IA |

**Novos CSS:** `.acc-wrap`, `.acc-item`, `.acc-item.open`, `.acc-header`, `.acc-icon`, `.acc-icon.orange`, `.acc-icon.blue`, `.acc-label`, `.acc-chevron`, `.acc-body`, `.acc-divider`, `.cfg-status-footer`

**Novas funções JS:**
```javascript
toggleAcc(id)          // abre/fecha seção + lazy-load na primeira abertura
carregarResumoBase()   // busca total de documentos via GET /base
```

---

### CONDUÇÃO — ENDPOINT CRIADO (`api/main.py`)

**Problema anterior:** `cenario.html` chamava `POST /cenario/{meeting_id}/conducao` mas o endpoint **não existia** — retornava erro e o overlay fechava com "❌ Não foi possível gerar o conteúdo". Os 4 arquivos de prompt template existiam mas nunca eram usados.

**Solução:** Endpoint implementado do zero.

| Endpoint | Método | Descrição |
|---|---|---|
| `/cenario/{meeting_id}/conducao` | POST | Gera script de condução ao vivo baseado no tipo e dados do cliente |

**Modelo Pydantic:**
```python
class ConducaoRequest(BaseModel):
    tipo: str        # recapitulacao | programa-aceleracao | performance | fechamento
    dados: Optional[dict] = None  # objeto completo de análise do cenário
```

**Roteamento por tipo:**
| `tipo` recebido | Template carregado |
|---|---|
| `recapitulacao` | `conducao_recapitulacao.txt` |
| `programa-aceleracao` | `conducao_programa_aceleracao.txt` |
| `performance` | `conducao_performance.txt` |
| `fechamento` | `conducao_fechamento.txt` |

**Variáveis extraídas do objeto `dados`:**
| Placeholder | Origem em `dados` |
|---|---|
| `{perfil_disc_tipo}` | `dados.perfil_disc.tipo` |
| `{perfil_disc_descricao}` | `dados.perfil_disc.descricao` ou `.evidencia` |
| `{faturamento}` | `dados.mapa_financeiro.faturamento_mensal` ou `.renda_clt` |
| `{capacidade_investimento}` | `dados.mapa_financeiro.capacidade_investimento` |
| `{produto_nome}` | `dados.mapa_financeiro.produto_indicado.nome` |
| `{produto_justificativa}` | `dados.mapa_financeiro.produto_indicado.justificativa` |
| `{score}` | `dados.score_compra.valor` |
| `{temperatura}` | `dados.temperatura.nivel` |
| `{conteudo_programa}` | Documentos da Base de IA (ver seção abaixo) |

**Compatibilidade com `chamar_ia_async` (que espera JSON):**
```python
system_prompt = (
    'Você é um assistente de vendas. '
    'Responda APENAS com um JSON válido sem markdown, no formato: '
    '{"conteudo": "script do vendedor aqui"}'
)
resultado = await chamar_ia_async(system_prompt, prompt_preenchido)
conteudo = resultado.get("conteudo") or ...
```

---

### CONDUÇÃO — INJEÇÃO DE DOCUMENTOS DA BASE DE IA (`api/main.py`)

**Problema:** Os prompts de Apresentação (Programa de Aceleração e Performance) geravam scripts genéricos porque a IA não sabia o que são esses programas na empresa.

**Solução:** O endpoint busca automaticamente documentos da `base_conhecimento` pelo `tipo` correspondente e injeta o conteúdo no prompt como `{conteudo_programa}`.

**Função adicionada:**
```python
def _buscar_conteudo_programa(tipo_base: str) -> str:
    # Query: SELECT titulo, texto FROM base_conhecimento WHERE tipo = %s ORDER BY created_at
    # Concatena todos os documentos do tipo com separador ### Titulo
```

**Mapeamento tipo condução → tipo Base de IA:**
```python
_CONDUCAO_TIPO_BASE = {
    "programa-aceleracao": "programa_aceleracao",
    "performance":         "performance",
}
```

**Como usar — fluxo completo:**
1. No Dashboard → Base de IA → adicionar documento
2. Selecionar tipo: **🚀 Programa de Aceleração** ou **📈 Programa Performance**
3. Escrever o conteúdo completo do programa (metodologia, benefícios, resultados, investimento...)
4. Salvar — entra em vigor imediatamente na próxima chamada de Condução
5. Múltiplos documentos do mesmo tipo são concatenados automaticamente

---

### PROMPT TEMPLATES ATUALIZADOS

Ambos os templates de Apresentação receberam bloco `INFORMAÇÕES DO PROGRAMA` com `{conteudo_programa}`:

**`conducao_programa_aceleracao.txt`** — adicionado:
```
INFORMAÇÕES DO PROGRAMA DE ACELERAÇÃO:
{conteudo_programa}
```
Instrução atualizada: *"Use as informações do programa acima para embasar a fala com detalhes reais."*

**`conducao_performance.txt`** — adicionado:
```
INFORMAÇÕES DO PROGRAMA PERFORMANCE:
{conteudo_programa}
```
Instrução atualizada: *"Use as informações reais do programa acima para mostrar o que muda na vida ou no negócio do cliente."*

---

### BASE DE IA — NOVO TIPO `performance` (`frontend/dashboard.html`)

**Adicionado:**
- Option `📈 Programa Performance` no `<select>` de tipo do formulário
- `_TIPOS_BASE` map: `performance: '📈 Prog. Performance'`

**Tipos disponíveis agora:**
```
instrucao, script_venda, programa_aceleracao, performance,
diagnostico, consultoria, reuniao_1_1, reuniao, outro
```

---

### CORREÇÕES DE BUGS

| # | Arquivo | Problema | Solução |
|---|---|---|---|
| 1 | `agent/base_conhecimento.py` | RAG buscava coluna `tipo_reuniao` (inexistente) | Corrigido para `tipo` (nome real da coluna adicionada em V.1.3.5) |
| 2 | `api/main.py` | `POST /cenario/{id}/conducao` retornava 404/405 | Endpoint criado do zero |
| 3 | `frontend/dashboard.html` | Configurações carregava todos os dados simultaneamente ao abrir | Lazy-load com accordion resolve |

---

### ARQUIVOS ALTERADOS NESTA VERSÃO

| Arquivo | Tipo de alteração |
|---|---|
| `api/main.py` | feat: `ConducaoRequest`, endpoint `/cenario/{id}/conducao`, `_buscar_conteudo_programa` |
| `frontend/dashboard.html` | feat: accordion Configurações, tipo `performance` na Base de IA |
| `agent/base_conhecimento.py` | fix: `tipo_reuniao` → `tipo` |
| `agent/prompt_templates/conducao_programa_aceleracao.txt` | feat: bloco `{conteudo_programa}` |
| `agent/prompt_templates/conducao_performance.txt` | feat: bloco `{conteudo_programa}` |

---

## V.1.3.5 — Deploy VPS + Auth + Admin + Base de IA Avançada
> Data: 27/05/2026 | Desenvolvido com Claude Sonnet 4.6

---

### DEPLOY EM PRODUÇÃO

| Item | Detalhe |
|---|---|
| Servidor | VPS Hetzner — `204.168.180.25` |
| Domínio | `api.saleia.com.br` (Nginx + Certbot SSL) |
| Serviço | `saleia.service` (systemd, reinicia automaticamente) |
| Processo | `uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 2` |
| Banco | MySQL remoto `177.104.186.227` — base `fast5342_AV3D` |
| Deploy | SFTP direto (repo VPS apontava para `SALEIA.git` errado; migrado para `SALE-IA.git`) |

---

### AUTENTICAÇÃO (`/auth/*`)

**Problema anterior:** login.html chamava endpoints que não existiam → "Not Found".

| Endpoint | Método | Descrição |
|---|---|---|
| `/auth/login` | POST | Verifica email + senha bcrypt, retorna JWT (72h) |
| `/auth/cadastro` | POST | Cria usuário; primeiro usuário vira admin automaticamente |
| `/auth/recuperar-senha` | POST | Stub (confirma recebimento; envio de e-mail pendente) |

**Detalhes técnicos:**
- Hash: `bcrypt` (instalado no venv do VPS)
- Token: `PyJWT` HS256, expiração 72h
- JWT secret: variável `JWT_SECRET` no `.env` (fallback padrão se não definida)
- Tabela: `usuarios` (MySQL) — campos: `id`, `nome`, `email`, `senha_hash`, `perfil`, `plano`, `status`, `data_cadastro`, `ultimo_acesso`
- Coluna `plano` adicionada via `ALTER TABLE` (padrão `free`)

---

### ADMIN — GERENCIAMENTO DE USUÁRIOS (`/admin/usuarios/*`)

Todos os endpoints exigem JWT Bearer com `perfil = admin`.

| Endpoint | Método | Descrição |
|---|---|---|
| `/admin/usuarios` | GET | Lista todos os usuários |
| `/admin/usuarios/{id}/inativar` | PATCH | Define `status = inativo` |
| `/admin/usuarios/{id}/reativar` | PATCH | Define `status = ativo` |
| `/admin/usuarios/{id}/status` | PATCH | Define status arbitrário (`ativo`, `pendente`, `inativo`) |
| `/admin/usuarios/{id}/resetar-senha` | PATCH | Redefine senha para `Saleia@2025`, retorna nova senha |
| `/admin/usuarios/{id}/perfil` | PATCH | Altera perfil (`admin`, `gerente`, `operador`, `usuario`) |
| `/admin/usuarios/{id}/plano` | PATCH | Altera plano (`free`, `pro`, `enterprise`) |
| `/admin/usuarios/{id}` | DELETE | Exclui usuário permanentemente |

**UI — Tabela com menus suspensos inline:**
- **Perfil**: `<select>` direto na linha — salva ao trocar
- **Plano**: `<select>` direto na linha — salva ao trocar
- **Status**: `<select>` direto na linha — salva ao trocar
- **⋮ Ações**: dropdown com → 🔑 Reset senha / 🗑 Excluir
- Dropdown fecha ao clicar fora da tabela

---

### ADMIN — CONFIGURAÇÃO DE APIs (`/admin/api/*`)

| Endpoint | Método | Descrição |
|---|---|---|
| `/admin/api/provedores` | GET | Lista os 4 provedores com status atual baseado no `.env` |
| `/admin/api/provedores/{id}/chave` | POST | Salva chave no `.env` e recarrega em tempo real |
| `/admin/api/teste` | POST | Testa conectividade do provedor (chamada real de 1 token) |
| `/admin/api/provedores/{id}/status` | PATCH | Ativa/inativa provedor |
| `/admin/api/principal` | POST | Define provedor preferido (`PROVEDOR_PREFERIDO` no `.env`) |

**Provedores suportados:** DeepSeek · OpenAI · Anthropic · Gemini

---

### BASE DE CONHECIMENTO — CRUD (`/base/*`)

**Problema anterior:** endpoint usava coluna `conteudo` mas a tabela tem `texto`.

| Endpoint | Método | Descrição |
|---|---|---|
| `/base` | GET | Lista documentos (id, título, tipo, chars, data) |
| `/base` | POST | Adiciona documento; gera embedding via `text-embedding-3-small` |
| `/base/{id}` | DELETE | Remove documento e invalida cache RAG |
| `/base/ocr` | POST | OCR de imagem via AI Vision (Claude → GPT-4o fallback) |

**Fallback de embedding:** quando a quota OpenAI está esgotada, documento é salvo com `embedding = NULL` e o usuário recebe aviso laranja em vez de erro 502.

**Migração de banco:**
```sql
ALTER TABLE base_conhecimento ADD COLUMN tipo VARCHAR(100) DEFAULT 'outro' AFTER titulo;
```

---

### UPLOAD DE ARQUIVOS — DRAG & DROP

**Localização:** Dashboard → Base de Conhecimento

**Formatos suportados:**

| Formato | Método de extração |
|---|---|
| `.txt` `.md` `.csv` | FileReader nativo (browser) |
| `.pdf` | PDF.js 3.11 via CDN (extração página a página) |
| `.docx` `.doc` | Mammoth.js 1.6 via CDN (texto limpo) |
| `.jpg` `.jpeg` `.png` `.webp` `.gif` | OCR via AI Vision (`/base/ocr`) — Claude ou GPT-4o |

**Comportamento:**
- Arrastar arquivo para a zona **ou** clicar para selecionar
- Nome do arquivo vira sugestão de título automaticamente
- Exibe quantidade de caracteres extraídos
- Erros de extração exibidos em vermelho na própria zona

**Correções de bugs no drag-drop:**
- `_dropzoneInited` flag → evita listeners duplicados ao alternar páginas
- `dragenter` + `dragleave` com `relatedTarget` → fix do flicker em elementos filhos
- `.base-dropzone * { pointer-events: none }` → filhos não interceptam eventos de drag
- `document.dragover/drop` com `preventDefault` → evita browser abrir o arquivo

---

### ROTAS HTML ADICIONADAS

| Rota | Arquivo servido |
|---|---|
| `GET /` | `frontend/login.html` |
| `GET /login` | `frontend/login.html` |

**Problema anterior:** botão "Sair" redirecionava para `/login` que retornava 404 (FastAPI não tinha essa rota).

---

### CORREÇÕES DE BUGS

| # | Problema | Solução |
|---|---|---|
| 1 | POST `/base` retornava 500 — coluna `conteudo` não existe | Corrigido para `texto` (nome real no banco) |
| 2 | GET `/base` retornava 500 — `tipo` não existia na tabela | `ALTER TABLE` adicionou coluna `tipo` |
| 3 | Botão Sair → `/login` → 404 | Adicionado `GET /login` no FastAPI |
| 4 | POST `/base` retornava 502 quando quota OpenAI esgotada | Fallback: salva sem embedding + aviso ao usuário |
| 5 | Botão "🗑 Excluir" invisível na Base de IA | CSS `.cfg-btn-acao.danger` estava sem definição |
| 6 | Drag-drop não funcionava | 3 bugs corrigidos (ver seção acima) |
| 7 | Git remoto VPS apontava para repo errado (`SALEIA` vs `SALE-IA`) | Atualizado via `git remote set-url` + SFTP deploy |

---

## V.1.3.4 — Recapitulação com Mapa Mental + Base de IA + Logout
> Data: 27/05/2026

### FUNCIONALIDADES

**Cenário → Condução → Recapitulação:**
- Painel alargado (`min(760px, 100vw - 32px)`) ao abrir Recapitulação
- Exibe texto gerado pela IA + Mapa Mental inline com 6 cards:
  - DISC (tipo + cor), Score de compra, Temperatura, Faturamento/Renda, Capacidade de investimento, Produto indicado
- Mapa Mental usa cores DISC: D=`#EF4444` I=`#F97316` S=`#14B8A6` C=`#38BDF8`

**Dashboard — Página "Base de IA":**
- Formulário: Título, Tipo (7 categorias), Conteúdo
- Tabela de documentos com botão Excluir
- Tipos: instrucao, script_venda, programa_aceleracao, diagnostico, consultoria, reuniao_1_1, outro

**Botão Sair:**
- Localização: rodapé da sidebar
- Ação: remove `saleia_token` do localStorage → redireciona para `/login`

**Arquivos alterados:** `api/main.py`, `frontend/dashboard.html`, `frontend/cenario.html`, `frontend/login.html`, `agent/base_conhecimento.py`, `agent/prompt_templates/*.txt`

---

## INFRAESTRUTURA

### Banco de dados (MySQL `fast5342_AV3D`)

**Tabelas relevantes:**

| Tabela | Uso |
|---|---|
| `usuarios` | Autenticação e gerenciamento de usuários |
| `base_conhecimento` | Documentos para RAG (embeddings OpenAI) |
| `sessoes` | Sessões de reunião |
| `meeting_memory` | Memória por meeting_id |

**Colunas adicionadas nesta versão:**
```sql
ALTER TABLE usuarios ADD COLUMN plano VARCHAR(30) NOT NULL DEFAULT 'free';
ALTER TABLE base_conhecimento ADD COLUMN tipo VARCHAR(100) DEFAULT 'outro' AFTER titulo;
```

### VPS — Pacotes instalados no venv

```bash
pip install PyJWT bcrypt
```

### Variáveis de ambiente (`.env`)

```env
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GEMINI_API_KEY=...
DEEPSEEK_API_KEY=...
DEEPSEEK_MODEL=deepseek-chat
DB_HOST=177.104.186.227
DB_PORT=3306
DB_USER=fast5342_AV3D
DB_PASS=...
DB_NAME=fast5342_AV3D
JWT_SECRET=...              # novo — segredo para JWT
PROVEDOR_PREFERIDO=deepseek # novo — provedor ativo principal
```

---

## COMMITS DESTA SESSÃO

```
9a49917  fix: botão Excluir visível e funcional na Base de IA
0382369  fix: corrigir drag-and-drop na Base de IA
7582bc3  feat: OCR de imagens (JPEG/PNG/WEBP) via AI Vision na Base de IA
e5f065d  feat: drag-and-drop de arquivos na Base de IA (PDF, DOCX, TXT, MD)
a7656f2  fix: salvar documento na base mesmo sem embedding (fallback gracioso)
c2f617c  feat: implementar endpoints /admin/usuarios e /admin/api/provedores
14e9d38  feat: implementar endpoints /auth/login, /auth/cadastro e /auth/recuperar-senha
d413ae2  fix: adicionar rota /login e / para servir login.html
f89e984  fix: usar coluna 'texto' em vez de 'conteudo' nos endpoints /base
53f2b0d  feat: V.1.3.4 — Recapitulação com Mapa Mental integrado + versão atualizada
```

---

*Documento gerado em 27/05/2026 — SALEIA / HEXAGON TECNOLOGIA*
