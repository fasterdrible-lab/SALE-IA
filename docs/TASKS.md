# SALEIA - Tarefas

Use este arquivo como fila operacional. Execute apenas a primeira tarefa pendente.

## Concluido

- [x] Criar `MeetingMemory` persistida no banco.
- [x] Integrar `MeetingMemory` ao fluxo de tempo real.
- [x] Implementar coach em tempo real com controle de custo/contexto.
- [x] Criar eventos estruturados e key moments.
- [x] Detectar deixas verbais para recapitulacao.
- [x] Gerar recapitulacao viva com mapa mental.
- [x] Exibir recapitulacao viva na sidebar.
- [x] Gerar diagnostico final pos-reuniao.
- [x] Implementar fallback de IA.
- [x] Colocar DeepSeek como primeiro provedor.
- [x] Adicionar configuracao manual de provedor na UI.
- [x] Deploy em `https://api.saleia.com.br`.
- [x] Corrigir `/dashboard.` retornando `404`.
- [x] Corrigir erro `[object Object]` na analise manual.
- [x] Configurar DeepSeek em producao.
- [x] Registrar em docs o estado atual do projeto e a frente Runware para o cenario do Nilton.

## Concluido (V.1.3.6 - ultimo registro)

- [x] Reorganizar Configuracoes em accordion no dashboard.
- [x] Ligar Conducao aos prompts da apresentacao.
- [x] Corrigir o RAG do fluxo atual.

## Concluido (V.1.3.3 - frontend)

- [x] T01 - Exibir metadados da IA no resultado da analise manual (`renderUsoIa` com tokens, moeda e custo total).
- [x] Criar `frontend/login.html` com tabs Login / Cadastro / Recuperar senha, show/hide password, loading states, auto-detect API.
- [x] Config dashboard: remover seletor Local/Producao da UI; adicionar Gerenciamento de Usuarios (tabela com perfil, plano, status, acoes) e Configuracao de APIs (provedores com chave mascarada, testar, ativar/inativar, definir principal).
- [x] `cenario.html`: renomear slide-3 para "Conducao"; adicionar menu dropdown (Recapitulacao, Apresentacao -> submenu, Fechamento) com overlay de resultado e botao Copiar.
- [x] Criar `frontend/apresentacao/programa-aceleracao.md` e `frontend/apresentacao/performance.md` com prompts estruturados.

## Proxima Tarefa

### T02 - Criar endpoints backend para Conducao

Objetivo:

Implementar `POST /cenario/{meeting_id}/conducao` no backend para suportar o menu Conducao do `cenario.html`.

Escopo permitido:

- `backend/src/` (rotas e servico)

Nao alterar:

- Frontend (ja implementado)
- Banco de dados (usar MeetingMemory existente)
- Extensao Chrome

Comportamento esperado:

- Receber `{ tipo, dados }` onde `tipo` e um de: `recapitulacao`, `programa-aceleracao`, `performance`, `fechamento`.
- Usar o prompt correto de `frontend/apresentacao/` para os tipos de Apresentacao.
- Retornar `{ conteudo: "..." }` com o texto gerado.
- Autenticacao obrigatoria.
- Nunca expor chaves de API no retorno.

## Concluido (T02)

- [x] T02 - Criar endpoint backend para Conducao (`POST /cenario/{meeting_id}/conducao`) — autenticacao JWT obrigatoria, bug `_get_conn` corrigido, validacao de meeting_id adicionada.

## Concluido (T03)

- [x] T03 - Endpoints de autenticacao existentes e validados; `criar_tabela_usuarios()` adicionada ao sessao_manager e chamada no startup — tabela `usuarios` agora criada automaticamente na VPS.

## Concluido (T04)

- [x] T04 - Endpoints de gerenciamento de usuarios existentes e validados (GET/PATCH x6/DELETE, todos protegidos com `_req_admin`). Tabela criada no startup via T03.

## Concluido (T05)

- [x] T05 - Endpoints de configuracao de APIs existentes e validados (5 endpoints, todos com `_req_admin`). Chaves salvas em .env + os.environ; nunca expostas nas respostas.

## Concluido (T06)

- [x] T06 - `GET /historico/uso` (lista reunioes com custo, score final, DISC, num_analises) e `GET /historico/uso/{meeting_id}` (detalhe com score_history, key_moments, eventos). Requer JWT. Fonte: MeetingMemory + sessoes.

## Concluido (T07)

- [x] T07 - Pagina Historico adicionada ao dashboard: nav item, lista de reunioes com score/custo/DISC, grafico de barras da evolucao do score, momentos-chave e eventos por reuniao. Consome GET /historico/uso e GET /historico/uso/{meeting_id}.

## Concluido (T08)

- [x] T08 - Filtros de Reunioes melhorados: data De/Ate adicionados, botao Limpar, contador "X de Y reunioes" exibido ao filtrar. Filtro por provedor nao implementado (campo ausente no response de /relatorios; requer alteracao de backend futura).

## Concluido (T09)

- [x] T09 - `tests/test_smoke.py` criado com 8 testes (2 por endpoint + rejeicao de input invalido). Nao requer servicos externos. Dependencias `bcrypt` e `PyJWT` adicionadas ao `requirements.txt`. Resultado: 8/8 OK em 1.1s.

## Concluido (T10)

- [x] T10 - Visual Scenario com DALL-E 3 (OpenAI) ja implementado. Runware descartado. Corrigido bug de expiracao de URL: `ImageGenerator` agora usa `response_format="b64_json"` e armazena data URI no banco — imagens persistem indefinidamente. Timeout aumentado para 90s.

---

## Concluido (T11)

- [x] T11 - Implementar envio de e-mail para recuperacao de senha — `agent/email_service.py` criado (SMTP via smtplib); `agent/sessao_manager.py` recebeu `migrar_colunas_usuarios()` que adiciona `reset_token` e `reset_token_exp`; `api/main.py` substituiu o stub por implementacao real com token seguro (secrets.token_urlsafe), expiracao 1h, envio em background_task, endpoint `GET /reset` servindo pagina HTML inline, endpoint `POST /auth/redefinir-senha` com validacao de token e hash bcrypt. `.env.example` atualizado com vars SMTP. Nenhuma dependencia nova (smtplib e stdlib).

## Concluido (T11-Ext)

- [x] T11-Ext - Analise e correcao da extensao Chrome: bug critico `abrirCenarioComFoto` corrigido (handler lia `msg.foto` undefined; corrigido para ler de `chrome.storage.local['saleia_foto_pendente']`); manifest versao `1.2.0` → `1.4.1`; popup.js versao dinamica via `chrome.runtime.getManifest()`.

---

## Proxima Tarefa

### T12 - Filtro por provedor em Reunioes

Objetivo:

Substituir o stub atual de `POST /auth/recuperar-senha` por uma implementacao real que envia e-mail com link/token de redefinicao.

Escopo permitido:

- `api/main.py` — endpoint `/auth/recuperar-senha` e novo endpoint `/auth/redefinir-senha`
- `agent/email_service.py` — novo modulo de envio de e-mail via SMTP
- `requirements.txt` — adicionar dependencia se necessario
- `frontend/login.html` — formulario de nova senha (se necessario)

Nao alterar:

- Fluxo de login e cadastro
- Tabela de usuarios (apenas adicionar coluna `reset_token` e `reset_token_exp` se necessario)
- Extensao Chrome
- Outros endpoints

Comportamento esperado:

1. `POST /auth/recuperar-senha` com `{ "email": "..." }`:
   - Gera token seguro (UUID ou secrets.token_urlsafe)
   - Salva token + expiracao (1h) na tabela `usuarios`
   - Envia e-mail com link `https://api.saleia.com.br/reset?token=...`
   - Sempre retorna `200` com mensagem neutra (nao vaza se e-mail existe)
2. `GET /reset?token=...` — serve pagina HTML com formulario de nova senha
3. `POST /auth/redefinir-senha` com `{ "token": "...", "nova_senha": "..." }`:
   - Valida token e expiracao
   - Aplica hash bcrypt na nova senha
   - Limpa token e expiracao
   - Retorna `200`

Variaveis de ambiente necessarias:

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASS=...
EMAIL_FROM=noreply@saleia.com.br
```

## Concluido (T12)

- [x] T12 - Campo `provedor` adicionado ao response de `GET /relatorios` (extraido de `_provedor_ia` dentro de `dados.recapitulacao`, `dados.perfil_disc` ou `dados.diagnostico_financeiro`). Select de provedor adicionado ao toolbar de Reunioes. `filtrarReunioes` e `limparFiltrosReunioes` atualizados. Provedor exibido como label discreta no card de cada reuniao.

---

## Concluido (T13)

- [x] T13 - Deploy V.1.4.2 na VPS (06/06/2026). Arquivos enviados via SCP com chave `saleia_vps`: `api/main.py`, `requirements.txt`, `agent/sessao_manager.py`, `agent/visual_scenario.py`, `agent/base_conhecimento.py`, `agent/email_service.py` (novo), `agent/prompt_templates/conducao_programa_aceleracao.txt`, `agent/prompt_templates/conducao_performance.txt`, `frontend/dashboard.html`, `frontend/visual-scenario.html`, `tests/test_smoke.py`. pip install OK, `saleia.service` ativo. `/health` = online, `/dashboard` = 200, `/login` = 200, `/relatorios` = 200.

---

## Proxima Tarefa

## Concluido (T14)

- [x] T14 - Variaveis SMTP adicionadas ao `.env` da VPS (06/06/2026). Gmail App Password configurada. `POST /auth/recuperar-senha` testado em producao — retornou resposta neutra correta. E-mail de recuperacao ativo.

## Concluido (T15)

- [x] T15 - Refatoracao e correcao de bugs (06/06/2026): (1) `exportar_para_base_conhecimento` em `sessao_manager.py` corrigido — coluna `conteudo` renomeada para `texto` no CREATE TABLE e INSERT (toda exportacao de sessao para Base de IA falhava); (2) invalidacao de cache RAG substituida por `invalidar_cache()` (a chamada anterior deixava `_cache = {}` causando `KeyError` na proxima busca); (3) `PATCH /admin/api/provedores/{pid}/status` agora propaga ativacao/desativacao ao `os.environ`; (4) import duplicado e `os.environ` redundante removidos de `main.py`.

## Concluido (T17)

- [x] T17 - SDK Groq oficial, toggle 👁 e correcao de `salvarChaveGroq` (06/06/2026): (1) `groq>=0.9.0` adicionado ao `requirements.txt`; `/audio-transcricao` agora usa `from groq import Groq` com `whisper-large-v3`; (2) `POST /admin/transcricao/config` recebe flag `apenas_salvar: bool` — salva chave sem mudar provedor ativo; (3) Dashboard: botao 👁 mostra/oculta a chave Groq; `salvarChaveGroq` corrigido para usar `fetchJsonWithFallback` e enviar `apenas_salvar: true`; (4) `content.js` exibe erros de transcricao na sidebar (antes apenas `console.warn`).

## Concluido (T16)

- [x] T16 - Suporte a dois provedores de transcricao de audio: Whisper (OpenAI) e Groq (06/06/2026). `/audio-transcricao` roteia pelo valor de `TRANSCRICAO_PROVEDOR` no `.env` — `whisper` usa `whisper-1` via OpenAI SDK; `groq` usa `whisper-large-v3-turbo` via OpenAI SDK apontado para `https://api.groq.com/openai/v1`. Novos endpoints `GET/POST /admin/transcricao/config` (requer JWT admin). Dashboard: accordion "Transcricao de Audio" em Configuracoes com cards para cada provedor, campo de senha para GROQ_API_KEY e botao de ativacao. `.env.example` atualizado com `GROQ_API_KEY` e `TRANSCRICAO_PROVEDOR`. (06/06/2026): (1) `exportar_para_base_conhecimento` em `sessao_manager.py` corrigido — coluna `conteudo` renomeada para `texto` no CREATE TABLE e INSERT (toda exportacao de sessao para Base de IA falhava); (2) invalidacao de cache RAG substituida por `invalidar_cache()` (a chamada anterior deixava `_cache = {}` causando `KeyError` na proxima busca); (3) `PATCH /admin/api/provedores/{pid}/status` agora propaga ativacao/desativacao ao `os.environ`; (4) import duplicado e `os.environ` redundante removidos de `main.py`.

---

## Concluido (V.1.4.6 a V.1.4.9 — Redesign Visual e Manual)

- [x] V.1.4.6 - Redesign visual gold/black completo: `dashboard.html` (variaveis CSS, sidebar preta, botoes dourados, tipografia Inter+Sora), `login.html` (logo PNG premium, layout compacto), `frontend/logo-saleia.png` (novo arquivo), Nginx: `location = /logo-saleia.png`.
- [x] V.1.4.7 - `visual-scenario.html` paleta gold/black; titulo renomeado para "Visual Cenario AI"; item de menu "Visual Cenario" corrigido em `dashboard.html`.
- [x] V.1.4.8 - Multi-clientes em analise manual (`dashboard.html`: lista dinamica + `/Adicionar`); botao "← Inicio" em `visual-scenario.html` corrigido; `cenario.html` paleta gold/black; extensao Chrome (popup.css, sidebar.css, content.css) redesenhada em ouro/preto; `content.js` multi-clientes com event delegation e migracao de dados antigos.
- [x] V.1.4.9 - Manual (`frontend/manual.html`) reescrito de V.1.4.5 para V.1.4.8 com secoes 7 (Cenario), 8 (Visual Cenario AI), nav sticky, FAQ atualizado e botoes de acoes rapidas.

---

## Concluido (T18)

- [x] T18 - Deploy V.1.4.3–V.1.4.9 na VPS (07/06/2026). 17 arquivos enviados via SCP com chave `saleia_vps`: api/main.py, agent/sessao_manager.py, requirements.txt, 5 frontend HTML, logo-saleia.png, manual.html, 8 chrome-extension (background.js, manifest.json, popup.html/js/css, sidebar.css, content.css/js). pip install OK, `saleia.service` ativo. `/health` = online (4 provedores ok), `/dashboard` = 200, `/logo-saleia.png` = 200.

---

## Proxima Tarefa

## Concluido (T19)

- [x] T19 - UX de chaves API e badge de status persistente (07/06/2026): (1) `autocomplete="new-password"` nos campos de chave dos 4 provedores — bloqueia preenchimento automático do gerenciador de senhas do Chrome; botão 👁 adicionado em cada card com função `toggleVerChave(pid, btn)` para alternar visibilidade; (2) badge `✅ Online` / `❌ Offline` adicionado no cabeçalho do card — persiste após clicar em "Testar conexão"; `testarProvedor` reescrito para popular `status-teste-${id}` permanentemente no sucesso e com timeout apenas no texto de erro.

---

## Concluido (V.1.4.11)

- [x] V.1.4.11 - Monitor de observabilidade Fase 2: contadores de uso IA em memória com lock thread-safe (`api/ai_router.py`); endpoint `GET /monitor/metricas` (requer JWT); aba Monitor no dashboard com cards de uptime, chamadas, sucesso, falha, fallbacks, circuit breaks, reuniões ativas/hoje e tabela de provedores com latência média.

## Concluido (V.1.4.12)

- [x] V.1.4.12 - Observabilidade Fase 3: histórico SQLite rolling 24h em `data/metricas.db` (`api/metricas_historico.py` novo); background task `_loop_metricas()` a cada 60s; `GET /monitor/historico?horas=N`; alertas Telegram por threshold (`agent/alertas.py`); sparklines SVG 6h no Monitor tab; templates Grafana Alloy em `infra/`.

## Concluido (V.1.4.13)

- [x] V.1.4.13 - Fix OpenTelemetry: `_configurar_opentelemetry()` movida para nível do módulo (era chamada dentro do `on_startup` — tarde demais para instrumentar rotas); traces chegando ao Grafana Cloud Tempo em tempo real. Global fetch interceptor no `dashboard.html` injeta JWT automaticamente em todas as requisições — corrige 401 no Monitor.

## Concluido (V.1.4.14)

- [x] V.1.4.14 - Fix monitor provedores: provedores sem chave incrementam contador de falha (antes apareciam como 0/0). Fix botão "Inativar" API: `admin_listar_provedores` passa a ler `ativo` de `os.environ` (runtime) e `tem_chave` do arquivo .env. VPS: ordem dos provedores corrigida para `deepseek → openai → anthropic → gemini`; modelo Gemini atualizado para `gemini-2.5-flash`; RAG restaurado (OpenAI embeddings, 49 transcrições).

## Concluido (V.1.4.15)

- [x] V.1.4.15 - Monitor: card "💰 Gasto (USD)" e coluna Custo por provedor; coluna "STATUS ATUAL" usa cache `_ultimo_teste` como fonte principal com tempo decorrido; modelo Gemini no teste usa `GEMINI_MODEL` do `.env`. Dev Manual (`frontend/manual_tecnico.html`) reescrito com tema gold/black; link "🛠️ Dev Manual" na sidebar. Deploy realizado na VPS.

---

## Concluido (V.1.4.16)

- [x] V.1.4.16 - Funcionalidade "Próxima Melhor Pergunta" (next_best_question): prompt atualizado com 9 categorias + lógica DISC; fallback seguro no processador; persistência como key_moment no banco; sidebar Chrome substituída por bloco estruturado (categoria, objetivo, pergunta, motivo, impacto, botão copiar); 20 testes em 4 suítes (8 cenários de negócio). Apenas local + GitHub; deploy programado.

---

## Concluido (V.1.4.17)

- [x] V.1.4.17 - Migracao para VPS dedicada Hetzner CPX32 (`37.27.214.33`, Helsinki): MySQL movido de servidor remoto compartilhado (676ms) para instancia local (2ms, reducao 338x); novo dominio `api.saleia.app.br` (Cloudflare proxy); deploy via git clone + Python 3.14 venv + systemd `TimeoutStopSec=30`; bug de versao hardcoded no `/health` corrigido (1.4.14 -> 1.4.17). Dados migrados: 5 tabelas SALEIA preservadas incluindo base_conhecimento (49 docs RAG).

## Concluido (V.1.4.18)

- [x] V.1.4.18 - Fix compatibilidade openai + httpx (09/06/2026): `openai==1.35.7` incompativel com `httpx>=0.28.0` causava `AsyncClient.__init__() got an unexpected keyword argument 'proxies'` ao testar conexao no dashboard. Corrigido com `openai>=1.52.0` em `requirements.txt`.

## Concluido (V.1.4.19)

- [x] V.1.4.19 - Monitor melhorado (09/06/2026): (1) Tabela de provedores sempre exibe os 4 provedores (DeepSeek/OpenAI/Anthropic/Gemini) mesmo sem chamadas registradas; (2) Card "Transcricao de Audio" adicionado ao Monitor com status de Groq e OpenAI Whisper; (3) Backend: campo `transcricao` adicionado ao endpoint `/monitor/metricas`. (4) Auto-refresh do Monitor: timer `60s` → `15s`.

## Concluido (V.1.4.20)

- [x] V.1.4.20 - Config APIs: status automatico real ao abrir accordion (09/06/2026): `_autoTestarProvedores()` dispara `testarProvedor()` em background para cada provedor ao carregar a aba — mostra Online/Offline/Sem chave sem precisar clicar em "Testar conexao". Substituiu abordagem anterior que usava circuit breaker (mostrava todos como Online incorretamente).

## Concluido (V.1.4.21)

- [x] V.1.4.21 - Config APIs: pre-teste em background + badge de carregamento (09/06/2026): `_preTestarProvedores()` e `_testePendente` adicionados — testes disparam ao navegar para Configuracoes, antes do accordion abrir; quando accordion abre, badges mostram resultado instantaneo via `_aplicarTesteStatus`. Badge "⏳ Testando..." exibido se accordion abrir antes do teste concluir. Sem chamadas duplicadas.

## Concluido (V.1.4.22)

- [x] V.1.4.22 - Refatoracao profunda (09/06/2026): 6 bugs corrigidos — (1) padrao TRANSCRICAO_PROVEDOR alinhado para "whisper" em ambos endpoints; (2) double-reload transcricao corrigido com `_trReloadTimer`; (3) `delete _accLoaded['transcricao']` incorreto removido; (4) `toggleProvedor` agora limpa status cacheado e aguarda reload; (5) `_autoTestarProvedores` exibe badge de loading para testes pendentes; (6) `_iniciarMonitor` sempre chama `_pararMonitor()` antes de iniciar.

## Concluido (V.1.4.23)

- [x] V.1.4.23 - Fix critico: status de provedores oscilando no Monitor (09/06/2026). Causa: `_ultimo_teste` in-memory por worker com `--workers 2` — requests alternavam entre Worker A (com resultado) e Worker B (sem resultado), fazendo status flutuar entre Online e Offline a cada clique em "Atualizar". Correcao: `_ultimo_teste` agora persistido em tabela SQLite `teste_provedores` em `metricas.db` (compartilhado entre todos os workers). `_ler_testes_compartilhados()` mescla DB + in-memory (mais recente vence). Startup cria tabela automaticamente. `salvar_teste_provedor()` chamado em todo `POST /admin/api/teste`. Arquivos: `api/metricas_historico.py` (3 novas funcoes) + `api/main.py`.

---

## Concluido — Infraestrutura Nova VPS

- [x] DNS `api.saleia.app.br` propagado (09/06/2026).
- [x] Certbot SSL configurado — cert valido ate 2026-09-07.
- [x] Admin `phpos@gmail.com` criado e ativado na nova VPS.
- [x] App validado em `https://api.saleia.app.br` (health, dashboard, login, APIs online).
- [x] Frontend: todos os URLs `api.saleia.com.br` → `api.saleia.app.br` atualizados.

---

## Concluido (V.1.4.24 a V.1.4.26 + fixes)

- [x] V.1.4.24 - Botao "Testar conexao" na secao Transcricao de Audio (09/06/2026): endpoint `POST /admin/transcricao/teste` valida chave Groq ou OpenAI Whisper; badge Online/Offline por card; funcao `testarTranscricao(pid)` no frontend.
- [x] V.1.4.25 - Teste de transcricao via `models.list()` (09/06/2026): substituiu envio de WAV minimo que retornava erro 400 "Audio file is too small" em ambas as APIs.
- [x] V.1.4.26 - Campo de chave OPENAI_API_KEY no card OpenAI Whisper (09/06/2026): campo password + botao salvar + toggle 👁 identicos ao card Groq; backend aceita `openai_api_key` em `TranscricaoConfigRequest`.
- [x] Fix UX - Timestamps UTC convertidos para horario local (UTC-3) nas Sessoes ao Vivo via `_fmtLocal()`.
- [x] Fix UX - `autocomplete="new-password"` no campo Groq API Key bloqueia prompt "Salvar senha?" do Chrome.
- [x] Fix Ext - `background.js` migra `saleiaBackendUrl` de `saleia.com.br` para `saleia.app.br` automaticamente no storage.

## Concluido (Deploy V.1.4.38)

- [x] Deploy V.1.4.38 confirmado na VPS nova (16/08/2026, via SSH): `/opt/saleia` ja estava no commit `555b990` (igual a `origin/main`); `systemctl restart saleia` executado, servico `active`; `/health` retornou `versao: 1.4.38`; `/dashboard` retornou `200`.
- Achado: remote `origin` do git em `/opt/saleia` tinha URL com placeholder invalido (`https://SEU_TOKEN@github.com`), entao `git pull` falhava com erro de autenticacao. Nao bloqueou o deploy porque o commit ja estava atualizado.
- [x] Corrigido (16/08/2026): `git remote set-url origin` atualizado com PAT valido do GitHub (`fasterdrible-lab`). `git pull origin main` testado e retornou "Already up to date".

## Concluido (V.1.4.39 — Embeddings desacoplados)

- [x] Auditoria dos 4 pontos que geravam embeddings (2 nao documentados no pedido original: `POST /base` em `api/main.py` e `agent/sessao_manager.py::exportar_para_base_conhecimento`).
- [x] Criado `services/embeddings/` — interface `EmbeddingProvider`, `OllamaEmbeddingProvider` (local, padrao), `OpenAIEmbeddingProvider` (opcional), `factory.get_embedding_provider()`.
- [x] Refatorados `agent/base_conhecimento.py`, `agent/sales_memory.py`, `agent/sessao_manager.py`, `api/main.py` para usar `services.embeddings` — nenhum modulo de negocio instancia mais um cliente OpenAI diretamente.
- [x] Mecanismo de seguranca de dimensao: colunas `embedding_provider`/`embedding_model`/`embedding_dim` + `is_dimension_compatible()` — fecha bug pre-existente de `ValueError` ao comparar vetores de dimensoes diferentes.
- [x] `scripts/reindex_embeddings.py` (idempotente, `--dry-run`, nunca deleta antes de validar).
- [x] `GET /admin/embeddings/status` (diagnostico, JWT admin).
- [x] `docs/EMBEDDINGS_LOCAL.md` (guia Windows/Linux).
- [x] `tests/test_embeddings.py` (32/32 OK) + `tests/test_embeddings_semantic_ranking.py` (auto-skip sem Ollama local). `tests/test_smoke.py` (8/8 OK, sem regressao — confirmado via `git stash` isolando as mudancas).
- Achado corrigido: `agent/sessao_manager.py::_get_conn()` nao tinha `connect_timeout` (diferente das outras 3 conexoes do projeto) — adicionado `connect_timeout=10`.
- Versao: `1.4.38` → `1.4.39`.

## Concluido (Deploy V.1.4.39 — 19/08/2026)

- [x] Deploy V.1.4.39 na VPS nova (`37.27.214.33`, via SSH com chave `saleia_vps`): `reunioes_ativas: 0` confirmado em `/health` antes de agir; `git pull origin main` (fast-forward `670ad5a..85dd554`); `systemctl restart saleia` — servico `active`.
- Commit adicional trazido pelo pull (nao documentado antes do deploy): `85dd554` — fix `_call_anthropic` em `api/ai_router.py` para nao assumir que `content[0]` e sempre bloco de texto (claude-sonnet-5 pode antepor bloco `thinking`); resolveu os 138 `falhas_consecutivas` do provedor Anthropic vistos em producao antes do restart.
- Pos-deploy: `/health` retornou `versao: 1.4.39`, 4 provedores (`deepseek`/`openai`/`anthropic`/`gemini`) com `status: ok` e `falhas_consecutivas: 0`; `/dashboard` retornou `200`.

## Concluido (V.1.4.40 — Simplificacao extensao + download Base + busca Sessoes + Propensao)

- [x] Extensao: auditoria e gate completo do toggle "API ativa/desligada" em todos os pontos de rede (incl. heartbeat) + bug de persistencia do estado no service worker corrigido.
- [x] Extensao: removidos Visual Cenario, Mapa Financeiro (card), Score de Compra (numero), Cenario do Cliente (botao) e "Backend online + URL" do popup/sidebar. Backend mantido intocado onde outros agentes ainda dependem do dado.
- [x] Base de Conhecimento: novas colunas de arquivo original + `POST /base` multipart + `GET /base/{id}/download` (JWT) + botao Baixar no dashboard.
- [x] Sessoes ao Vivo: busca por cliente/link/data/hora, filtros e ordenacao (client-side, mesmo padrao de Filtros de Reunioes); `listar_sessoes` enriquecida com cliente vinculado via `client_meetings`.
- [x] Propensao de Compra: `agent/propensao_rules.py` (classificacao deterministica no tempo real, sem custo de IA extra) + `propensao` estruturado no prompt de recapitulacao (fatores/evidencias/como_avancar) + UI atualizada (extensao mostra so o rotulo; dashboard tem Detalhamento expansivel).
- Achado nao corrigido (fora do escopo): 8 falhas pre-existentes em `tests/test_next_best_question.py` e `tests/test_realtime_memory.py`, nao relacionadas a esta rodada (arquivos `api/processador_tempo_real.py`/`api/database.py` nao tocados).
- Pendente pos-deploy: validar manualmente upload/download da Base contra o MySQL de producao (nao foi possivel testar localmente — sem MySQL acessivel desta maquina).

## Concluido (V.1.4.50 — Extensao informa a propria versao)

- [x] Incidente ao vivo (31/08/2026): reuniao real com os 4 provedores centrais falhando de verdade por mais de 1h e o fallback Claude Account (V.1.4.49) nao disparando para essa sessao. Investigacao mostrou que o servidor nao tinha como diferenciar "extensao desatualizada" de "extensao atualizada mas sem login" — so via a ausencia do header `Authorization`, ambigua nos dois casos.
- [x] `chrome-extension/background.js`: header `X-Extensao-Versao` adicionado em toda chamada ao backend (`fetchBackend`, `whisperChunk`/`audioChunk` → `/audio-transcricao`, heartbeat de `/health`). `manifest.json` `1.4.4` → `1.4.5`.
- [x] `api/main.py`: `_ext_ver_var` (ContextVar, mesmo padrao do `cid`) exposto em todo log JSON estruturado via `_CorrelationMiddleware`/`_JsonFormatter` — funciona em qualquer rota, nao so `/tempo-real`.
- [x] `tests/test_extensao_versao_log.py` (5 testes, novo) + suite completa `tests.test_smoke` (8) sem regressao — 13/13 OK.
- Versao: backend `1.4.49` → `1.4.50`; extensao Chrome `1.4.4` → `1.4.5`.
- **Pendente pos-implementacao**: deploy do backend na VPS (checar `reunioes_ativas` antes) + reinstalar a extensao nos navegadores dos vendedores — sem isso o `ext_ver` continua aparecendo como `"-"` nos logs.

## Concluido (V.1.4.51 — Cost Intelligence Fase 1)

- [x] Auditoria read-only da arquitetura de custo de IA (`docs/cost-intelligence-audit.md`) — achado critico: custo do tempo real sempre zerado (bug de propagacao em `orquestrador.py::_mesclar`).
- [x] `api/pricing_catalog.py` (catalogo por provider+model) + `api/cost_engine.py` (calculo puro) — novos.
- [x] Captura de uso real de tokens dos 4 provedores em `api/ai_router.py` (antes 100% estimativa char/4).
- [x] Tabela `ai_usage_events` (aditiva) + `registrar_evento_uso_ia`/`custo_por_reuniao` em `api/database.py`.
- [x] Fix do bug de propagacao: `_custo_ciclo_ia_usd` somado antes do merge em `orquestrador.py`/`processador_tempo_real.py`.
- [x] `api/ai_features.py` (novo) + threading de `feature`/`meeting_id` pelos ~15 pontos de chamada de IA (tempo real, relatorios, playbook, followup, skill, knowledge extractor, cenario/conducao).
- [x] `agent/claude_account.py`: custo real do SDK (`total_cost_usd`) deixa de ser descartado apos o log.
- [x] Suite completa: 168 testes, 8 falhas pre-existentes e nao relacionadas (`test_next_best_question.py`/`test_realtime_memory.py`, ja documentadas desde V.1.4.36) — sem regressao.
- **Pendente**: deploy na VPS + validacao manual dos nomes de campo de cache do DeepSeek/Gemini contra chamada real (ver `docs/CURRENT_STATE.md`). Fases 2-6 do roadmap (dashboard de custos, Budget Guard, Cost Router inteligente) ainda nao iniciadas.

## Concluido (31/08/2026 — Fallback Claude Account validado + fix PAT GitHub)

- [x] PAT do GitHub no `git remote` da VPS expirado/revogado — corrigido com PAT novo gerado pelo usuario (`git remote set-url origin`).
- [x] `git pull origin main` executado na VPS (fast-forward para `dde7987` = V.1.4.50+V.1.4.51) — codigo em disco, `systemctl restart` ainda pendente (aguardando `reunioes_ativas: 0`).
- [x] **Fallback Claude Account (V.1.4.49) validado end-to-end em producao real pela primeira vez**: vendedor conectou conta Claude no Dashboard + logou na extensao (email/senha) durante reuniao ao vivo com os 4 provedores centrais fora do ar; 4 analises concluidas com sucesso (coach/disc/finance/closer) via conta Claude pessoal, custo real ~US$0,03-0,06 cada. Pendencia da V.1.4.49 fechada. Detalhes em `docs/CURRENT_STATE.md` e `CHANGELOG.md`.

## Concluido (Deploy V.1.4.50/1.4.51 confirmado — 01/09/2026)

- [x] `systemctl restart saleia` confirmado aplicado e verificado via SSH (acesso por senha root, fornecida pelo usuario — chave `saleia_vps` continua nao autenticando): commit exato `dde7987` na VPS, servico `active` desde `2026-09-01 06:38:15 UTC`, `/health` local = `versao 1.4.51` / `reunioes_ativas 0`, `GROQ_API_KEY` presente no `.env`.
- **Pendente**: validar end-to-end se `GROQ_API_KEY` novo resolveu a transcricao de audio (journal sem chamadas recentes de `/audio-transcricao` para confirmar — precisa de trafego real); restabelecer a chave SSH `saleia_vps` (fallback por senha funciona, mas nao e sustentavel a longo prazo).

## Concluido (V.1.4.52 — Biblioteca de Inteligencia / Knowledge Compiler Fase 1)

- [x] `services/knowledge_compiler/`: extratores deterministicos de PDF/DOCX/TXT/MD/HTML (sem IA) + sanitizacao contra prompt injection (sinaliza, nunca remove).
- [x] Tabela `knowledge_sources` (SQLModel) + 4 endpoints (`POST /biblioteca/fontes`, `POST .../extrair`, `GET /biblioteca/fontes[/{id}]`) atras de `KNOWLEDGE_COMPILER_ENABLED` (desligada por padrao).
- [x] Dashboard: pagina "Biblioteca de Inteligencia" (upload + lista + extrair).
- [x] 18 testes novos (`tests/test_knowledge_compiler_extraction.py`) + verificacao end-to-end manual via TestClient. Suite `test_smoke`+`test_knowledge_compiler_extraction`+`test_base_download`: 33/33 OK, sem regressao.
- Decisao confirmada com o usuario: sem multi-tenant (`organization_id`), mantendo a decisao da V.1.4.40.
- Plano completo (Fases 1-6) salvo em `C:\Users\phpos\.claude\plans\twinkly-floating-emerson.md`.
- **Pendente**: deploy na VPS (`git pull` + `systemctl restart saleia` — a feature fica invisivel/`404` ate `KNOWLEDGE_COMPILER_ENABLED=true` ser setado no `.env` da VPS). Fases 2-6 ainda nao iniciadas — roadmap no CHANGELOG (V.1.4.52).

## Concluido (V.1.4.53 — Biblioteca de Inteligencia / Knowledge Compiler Fase 2)

- [x] Fix de regressao: decorator `@app.get("/cenario/{meeting_id}")` apagado sem querer no primeiro edit da Fase 1 — corrigido e verificado (nao chegou a afetar producao, restart da Fase 1 ainda pendente).
- [x] `agent/prompt_templates/knowledge_compiler_extracao.txt` (novo) + `api/ai_features.py::KNOWLEDGE_COMPILER_EXTRACAO`.
- [x] Tabela `knowledge_items` (SQLModel, deliberadamente testavel — nao raw-pymysql) + `services/knowledge_compiler/compiler.py` (`estimar_custo_compilacao` sem IA, `compilar_fonte` com 1 chamada de IA por secao + dedup por embedding, nunca bloqueia so sinaliza).
- [x] 4 endpoints novos (`GET estimar-custo`, `POST compilar`, `GET itens`, `PATCH itens/{id}`).
- [x] Dashboard: botoes "Compilar" (com estimativa+confirmacao) e "Ver itens" (aprovar/rejeitar) no card de cada fonte.
- [x] 18 testes novos (`tests/test_knowledge_compiler_compilation.py`) + verificacao end-to-end manual via TestClient (incluindo regressao do `/cenario`). Suite `test_smoke`+`test_knowledge_compiler_extraction`+`test_knowledge_compiler_compilation`+`test_base_download`: 51/51 OK, sem regressao.
- [x] Commitado localmente (`406d8a6`).
- **Pendente**: push + deploy na VPS (restart segue bloqueado por reuniao ativa). Fases 3-6 ainda nao iniciadas — roadmap no CHANGELOG (V.1.4.53).

## Concluido (V.1.4.54 — Biblioteca de Inteligencia / Knowledge Compiler Fase 3)

- [x] `api/database.py::buscar_conhecimento_compilado_similar()` — busca por texto livre entre KnowledgeItems `APPROVED`, formato pronto pra prompt.
- [x] 3º bloco de RAG em `orquestrador.py::analisar_fragmento_multi` (junto de base de conhecimento e Sales Memory), mesmo padrao try/except isolado.
- [x] `agent/skill_resolver.py::gerar_skill_de_knowledge_item` + `agent/playbook_generator.py::gerar_playbook_de_fonte` — mapeamentos puros e testaveis, sem custo de IA, disparados manualmente (nunca automatico).
- [x] 2 endpoints novos (`POST itens/{id}/gerar-skill`, `POST fontes/{id}/gerar-playbook`).
- [x] Dashboard: botoes "Gerar Skill" (item aprovado) e "Gerar Playbook" (fonte compilada).
- [x] Decisao documentada: sem mapeamento KnowledgeItem -> sales_memory (duplicaria contexto).
- [x] 14 testes novos (`tests/test_knowledge_compiler_integracao.py`) + verificacao end-to-end manual via TestClient. Suite `test_smoke`+3 arquivos knowledge_compiler+`test_base_download`: 65/65 OK, sem regressao. Suite completa (`discover tests`) rodando em background para confirmacao final.
- [x] Commitado localmente.
- **Pendente**: push + deploy na VPS. Fases 4-6 ainda nao iniciadas — roadmap no CHANGELOG (V.1.4.54).

## Concluido (Deploy V.1.4.52-1.4.54 confirmado — 01/09/2026 ~00h UTC)

- [x] Push dos 3 commits (`41dedd5`, `406d8a6`, `ab35a6f`) para o GitHub.
- [x] `git pull` na VPS (fast-forward `41dedd5` -> `ab35a6f`, Fases 1-3 de uma vez) — `reunioes_ativas: 0` checado antes e de novo logo antes do restart (evita corrida).
- [x] `pip install -r requirements.txt` + `pip check` limpo.
- [x] `systemctl restart saleia` — `active`, sem erros/excecoes no journal.
- [x] Pos-deploy: `/health` = `versao 1.4.54`; `/dashboard` = `200`.
- Achado: restart zerou os contadores de falha dos 4 provedores de IA (`status: ok` no `/health`) — **isso nao confirma que o saldo/chave foi resolvido**, e so o restart limpando o circuit breaker em memoria (comportamento ja documentado em 22/08/2026). Nenhuma chamada real de teste foi feita para confirmar.
- [x] `KNOWLEDGE_COMPILER_ENABLED=true` adicionado ao `.env` da VPS + `systemctl restart saleia` de novo (`reunioes_ativas: 0` checado antes e logo antes do restart) — confirmado direto no Python da VPS (`os.getenv` via mesmo `python-dotenv` que `api/main.py` usa) que a flag esta `true`. Endpoints `/biblioteca/*` acessiveis para usuario autenticado.
- [x] Fix pos-ativacao: usuario testou upload real de PDF, recebeu `HTTP 413` generico (nginx, nao FastAPI) — `client_max_body_size` faltava no nginx (default 1MB, backend ja aceitava ate 20MB desde a Fase 1). Corrigido em `/etc/nginx/sites-available/saleia` (`client_max_body_size 20m;` no nivel do server, vale tambem pra `/base`), `nginx -t` + `systemctl reload nginx` (gracioso, sem derrubar reunioes ativas). Backup do config original salvo antes do sed.
- [x] **Bug real encontrado no primeiro upload de verdade**: PDF de ~1.7MB subiu certo (fix do nginx funcionou), mas `POST /biblioteca/fontes/1/extrair` quebrou com `pymysql.err.DataError (1406, "Data too long for column 'texto_extraido'")` — `KnowledgeSource.texto_extraido`/`sections_json` e `KnowledgeItem.content`/`metadata_json`/`embedding_json` usavam `Text` (64KB no MySQL), insuficiente pra texto de livro inteiro. Corrigido com `Text().with_variant(MEDIUMTEXT, "mysql")` (ate 16MB, mesmo padrao ja usado em `base_conhecimento.texto`).
- [x] Aplicado em producao: `ALTER TABLE` manual nas 5 colunas (create_all nao migra colunas existentes), `git pull` (`ab35a6f` -> `d444c48`), fonte travada (id=1) resetada para `UPLOADED` (usuario pode clicar Extrair de novo sem reenviar o arquivo), `systemctl restart saleia` (`reunioes_ativas: 0` checado antes). Colunas confirmadas `mediumtext` via `DESCRIBE` em producao.
- [x] **Confirmado pelo usuario**: reextracao da fonte id=1 funcionou apos o fix de `MEDIUMTEXT` — upload + extracao validados de ponta a ponta em producao real.
- **Pendente**: testar manualmente a compilacao com IA (Fase 2) e a integracao RAG/Skill/Playbook (Fase 3) — so tem cobertura automatizada ate agora; validar `POST /base` tambem aceita arquivo >1MB. Fases 4-6 do Knowledge Compiler ainda nao iniciadas.

## Concluido (V.1.4.55 — Cost Intelligence Fase 2: Agregacoes e Dashboard de Custos)

- [x] `api/database.py`: 5 funcoes de agregacao SQLModel (`custos_resumo`, `custos_por_usuario`, `custos_reunioes_mais_caras`, `eventos_de_reuniao`, `exportar_eventos_uso_ia`) + helper `_com_filtro_data` para date_from/date_to opcionais.
- [x] `agent/sessao_manager.py`: 2 helpers de enriquecimento (`obter_nomes_usuarios`, `obter_clientes_por_reunioes`), mesma tecnica de subquery de `listar_sessoes`.
- [x] `api/main.py`: 5 endpoints novos atras de `_req_admin` (`GET /admin/costs/resumo|por-usuario|reunioes|reunioes/{meeting_id}|export`). Export CSV/JSON e o primeiro do backend inteiro (zero precedente antes).
- [x] Dashboard: aba "💰 Custos" nova, espelhando a estrutura da aba Monitor — cards de resumo, 3 tabelas de breakdown, "reunioes mais caras" clicavel com painel de detalhe/timeline, exportar CSV/JSON.
- [x] 24 testes novos (`tests/test_cost_aggregation.py` + `tests/test_admin_costs_endpoints.py`). Achado durante a escrita: SQLite `:memory:` isola por thread — `TestClient` roda o endpoint numa thread diferente do teste, corrigido com `StaticPool`+`check_same_thread=False` no engine de teste.
- [x] Suite completa (`discover tests`): 242 testes, 8 falhas pre-existentes e nao relacionadas (mesmas de sempre), sem regressao.
- [x] Commitado localmente e enviado ao GitHub (`push`).
- **Pendente**: deploy na VPS (`git pull` + `systemctl restart saleia` — checar `reunioes_ativas: 0` antes; aditivo, nenhuma tabela/`.env`/flag nova). Fases 3-6 do roadmap ainda nao iniciadas — ver CHANGELOG (V.1.4.55).

## Concluido (V.1.4.56 — Cost Intelligence Fase 3: Budget Guard, Alertas, Projecao, FX, Margem, Auditoria)

- [x] Investigacao previa: `admin_route_rules`/`alertas_automaticos`/`audit_logs` confirmadas vestigiais (zero codigo referencia); `agent/alertas.py` ja roda no loop de 60s, canal certo pro Budget Guard; sem cotacao USD->BRL nem preco por plano em lugar nenhum.
- [x] Decisoes confirmadas com o usuario: taxa de cambio fixa/configuravel (sem API externa); preco por plano sem valor inventado (comeca null); orcamento comeca desativado.
- [x] `api/fx_rates.py` (novo): `taxa_usd_brl`/`usd_para_brl`, default 5.40, override via `FX_USD_BRL_RATE`.
- [x] `api/database.py`: 3 tabelas novas (`OrcamentoIA`, `PlanoPreco`, `AuditoriaFinanceira`) + 7 funcoes (orcamento, precos de plano, auditoria, `gasto_mes_usd`, `projecao_mensal_custo`).
- [x] `agent/sessao_manager.py`: `obter_nomes_usuarios` ganha `plano`; novo `obter_usuarios_ativos_por_plano`.
- [x] `agent/alertas.py`: `verificar_orcamento` (aviso 80%, critico 100%+, mesmo cooldown de 1h).
- [x] `api/main.py`: Budget Guard no `_loop_metricas()` (a cada ~5min) + 6 endpoints `/admin/costs/orcamento|projecao|margem|planos/{p}/preco|auditoria`.
- [x] Dashboard: 3 cards novos na aba Custos (Orcamento Mensal, Margem por Plano, Auditoria Financeira) + accordion "Orcamento de IA" em Configuracoes.
- [x] 30 testes novos (`test_fx_rates`, `test_alertas` novo arquivo, `test_budget_and_margin`, `test_admin_costs_orcamento_endpoints`). Suite completa: 272 testes, 8 falhas pre-existentes e nao relacionadas, sem regressao.
- [x] Commitado localmente e enviado ao GitHub.
- **Pendente**: deploy na VPS (`git pull` + `systemctl restart saleia` — checar `reunioes_ativas: 0` antes; aditivo, 3 tabelas novas criadas automaticamente no startup). Fases 4-6 do roadmap ainda nao iniciadas — ver CHANGELOG (V.1.4.56).

## Concluido (V.1.4.57 — Cost Intelligence Fase 4: Cost Router em Shadow Mode)

- [x] Usuario confirmou: Fase 4 entra so em shadow mode (calcula recomendacao e registra, nunca troca o modelo real usado).
- [x] `api/pricing_catalog.py`: 2 entradas novas (`gpt-4o-mini`, `claude-3-5-haiku-20241022`) para o router estimar economia de verdade.
- [x] `api/cost_router.py` (novo): `classificar_complexidade` (simples/padrao/complexa), `modo_atual` (normal/economy/critical a partir do orcamento da Fase 3, cacheado 5min), `recomendar_modelo` (so troca modelo, nunca provedor), `avaliar_shadow` (melhor esforco, nunca lanca).
- [x] `api/database.py`: tabela `RouterDecisao` + `registrar_decisao_router`/`resumo_router_shadow`.
- [x] `api/ai_router.py::chamar_ia`: 1 hook depois do resultado real ja decidido, `try/except: pass` — zero mudanca de comportamento real.
- [x] `api/main.py`: `GET /admin/costs/router/shadow|config` (config e so leitura, sem endpoint de ativacao).
- [x] Dashboard: card "Cost Router (shadow mode)" na aba Custos.
- [x] 29 testes novos (`test_cost_router` novo arquivo + extensoes de `test_pricing_catalog`/`test_ai_router` + `test_admin_costs_router_endpoints` novo). Suite completa: 301 testes, 8 falhas pre-existentes e nao relacionadas, sem regressao.
- [x] Commitado localmente e enviado ao GitHub.
- **Pendente**: deploy na VPS (`git pull` + `systemctl restart saleia` — checar `reunioes_ativas: 0` antes; aditivo, 1 tabela nova). Fases 5-6 do roadmap ainda nao iniciadas — ver CHANGELOG (V.1.4.57). Ativar o roteamento de fato (sair do shadow mode) e decisao futura separada, so depois de revisar os dados coletados.

## Concluido (V.1.4.58 — Cost Intelligence Fase 5: Otimizacao em Shadow Mode)

- [x] Usuario confirmou: partes que mudam comportamento (cache, bloqueio de loop, corte de contexto) tambem entram so em shadow mode.
- [x] Investigacao previa: rate-limit do tempo real ja cobre ciclos rapidos (gap real e custo acumulado por reuniao); corte de contexto so existe pra transcricao/historico do tempo real; cache de resposta e 100% novo; versionamento de prompt e problema de 3 formas (escopo reduzido a hash tag).
- [x] `api/otimizacao_shadow.py` (novo): cache de resposta shadow (TTL 10min, LRU 500), corte de contexto shadow (economia calculada via cost_engine), loop caro por reuniao shadow (desligado por padrao, cache 60s).
- [x] `api/database.py`: tabela `OtimizacaoDecisao` + `registrar_decisao_otimizacao`/`resumo_otimizacao_shadow` + `detectar_anomalias_custo` + `analise_custo_latencia_qualidade`.
- [x] `agent/alertas.py`: `verificar_anomalia` (cooldown 1h por feature).
- [x] `api/main.py`: checagem de anomalias no loop (~1h) + `GET /admin/costs/otimizacao/shadow|anomalias|analise`.
- [x] Dashboard: card "Otimizacao (shadow mode)" na aba Custos.
- [x] 37 testes novos. Suite completa: 336 testes, 8 falhas pre-existentes e nao relacionadas, sem regressao.
- [x] Commitado localmente e enviado ao GitHub.
- **Pendente**: deploy na VPS (`git pull` + `systemctl restart saleia` — checar `reunioes_ativas: 0` antes; aditivo, 1 tabela nova). Fase 6 do roadmap ainda nao iniciada — ver CHANGELOG (V.1.4.58). Ativar qualquer otimizacao de fato (sair do shadow mode) e decisao futura separada.

## Concluido (V.1.4.59 — Cost Intelligence Fase 6: Observabilidade Final — ROADMAP DE 6 FASES FECHADO)

- [x] Achados previos: CLAUDE.md congelado na Fase 1 (nunca atualizado); testes de fallback existentes mockavam a escrita, nada provava a integracao real com a agregacao.
- [x] `GET /admin/costs/metricas` (novo): contrato consolidado resumo+router+otimizacao+anomalias, sem introduzir OpenTelemetry Metrics (fora de escopo/desproporcional).
- [x] Logs financeiros estruturados: `logging.getLogger("saleia.financeiro")` em `api/database.py`/`agent/alertas.py`, herda o JSON formatter existente de graca.
- [x] `tests/test_integracao_fallback_budget.py` (novo, 5 testes): grava de verdade e le pela agregacao real (fallback Claude Account, todos provedores falhando, orcamento cruzando 100%, anomalia real) + 2 testes do endpoint novo.
- [x] Suite completa: 343 testes, 8 falhas pre-existentes e nao relacionadas, sem regressao.
- [x] `CLAUDE.md`: secao Cost Intelligence reescrita cobrindo as 6 fases (tabela de arquivos por fase, env vars de shadow mode, runbook operacional).
- [x] Commitado localmente e enviado ao GitHub.
- **Pendente**: deploy na VPS (`git pull` + `systemctl restart saleia` — checar `reunioes_ativas: 0` antes; aditivo, zero tabela nova). **Roadmap de Cost Intelligence (60 tarefas, 6 fases) concluido** — decisao em aberto e separada: ativar de fato o Cost Router (Fase 4) e/ou Otimizacao (Fase 5), hoje so shadow mode.

## Concluido (V.1.4.60 — Cost Intelligence Fase 5 sai do Shadow Mode — ATIVA em producao)

- [x] Usuario confirmou explicitamente (duas vezes): ativar de verdade as 3 otimizacoes da Fase 5 (cache, corte de contexto, loop caro), mesmo com 0 decisoes shadow registradas ate entao.
- [x] Decisao de design confirmada contra o codigo real: bloqueio de loop caro usa HTTP 429 (nao 503) pra nao acionar o fallback Conta Claude pessoal.
- [x] `api/otimizacao_shadow.py` renomeado pra `api/otimizacao.py` (deliberado — nome antigo virava armadilha, ja que o modulo age de verdade agora); endpoint `/admin/costs/otimizacao/shadow` -> `/admin/costs/otimizacao`.
- [x] `api/otimizacao.py`: cache guarda resultado completo (nao so custo), corte so em user_content (nunca system_prompt), loop caro com kill-switch `OTIMIZACAO_LOOP_ATIVO`.
- [x] `api/ai_router.py::chamar_ia` reordenado: loop caro -> cache -> corte de contexto -> loop de provedores normal.
- [x] Achado durante os testes: cache real vazava entre testes que reusavam prompts genericos — corrigido estendendo `resetar_estado_ia_para_testes()`.
- [x] `GET /admin/costs/otimizacao` ganha bloco `ativo` (cache/contexto/loop) + `loop_limite_usd`.
- [x] Dashboard: card com 3 badges de status (✅/⛔).
- [x] Testes reescritos: `test_otimizacao.py` (20), `test_ai_router.py` (9 novos/reescritos), `test_multiagente_claude_fallback.py` (+1, trava a decisao do 429), `test_admin_costs_otimizacao_endpoints.py` atualizado. Suite completa: 356 testes, 8 falhas pre-existentes e nao relacionadas, sem regressao.
- [x] `CLAUDE.md`: Fase 5 vira secao propria "ATIVA em producao", Fase 4 continua "shadow mode" separada.
- [x] Commitado localmente e enviado ao GitHub.
- **Pendente**: deploy na VPS (`git pull` + `systemctl restart saleia` — checar `reunioes_ativas: 0` antes; muda comportamento real, rollback rapido via `OTIMIZACAO_*_ATIVO=false` no `.env` se necessario, sem reverter deploy).

## Concluido (V.1.4.61 — Cost Intelligence Fase 4: Cost Router sai do Shadow Mode — ATIVA em producao)

- [x] Usuario confirmou explicitamente ("Sim, ativar de verdade agora") apos eu avisar que os 20 registros de shadow mostram 100% concordancia/0% economia por causa de todo o trafego real hoje passar so pelo DeepSeek (sem variante economy configurada) — ativacao e hoje efetivamente inerte na pratica ate o saldo central de OpenAI/Anthropic voltar.
- [x] Decisao de design: `RouterDecisao`/schema nao muda — `concordou`/`economia_estimada_usd` por linha ficam quase tautologicos uma vez ativo (esperado, nao bug); a pergunta real de economia ja e respondida sem codigo novo pela quebra `por_model` de `custos_resumo` (Fase 2).
- [x] `api/cost_router.py`: `router_ativo()` (renomeia `_shadow_habilitado`, env `COST_ROUTER_ATIVO`), `modelo_a_usar()` (novo, substitui o modelo de verdade quando ativo), `registrar_decisao` (renomeia `avaliar_shadow`), `config_router()` com chave `ativo`.
- [x] `api/ai_router.py::chamar_ia`: loop de provedores usa `modelo_a_usar(provider.name, model_padrao, feature)` no lugar do modelo padrao direto; `resetar_estado_ia_para_testes()` ganha reset de `cost_router._modo_cache` (mesma classe de bug de vazamento entre testes ja corrigida na Fase 5).
- [x] `GET /admin/costs/router/shadow` -> `GET /admin/costs/router` (ganha `ativo`); `GET /admin/costs/router/config` mantem path, chave `ativo`; `GET /admin/costs/metricas` chave `router_shadow` -> `router`.
- [x] Dashboard: card Cost Router com badge de status ✅/⛔.
- [x] Testes reescritos: `test_cost_router.py`, `test_ai_router.py::CostRouterAtivoTest` (substitui `CostRouterShadowHookTest`), `test_admin_costs_router_endpoints.py`, `test_admin_costs_otimizacao_endpoints.py` (chave `router`). Suite completa sem regressao (mesmas 8 falhas pre-existentes e nao relacionadas).
- [x] `CLAUDE.md`: Fase 4 vira secao propria "ATIVA em producao", junto da Fase 5.
- [x] Commitado localmente e enviado ao GitHub.
- [x] Deploy na VPS confirmado (`reunioes_ativas: 0` antes e depois do pull, `systemctl restart saleia`, `/health` -> `versao: 1.4.61`, logs limpos). `GET /admin/costs/router` em producao confirma `ativo: true`, 20 decisoes herdadas do shadow mode (100% concordancia / 0% economia, esperado — trafego real so passa por DeepSeek hoje).

## Concluido (V.1.4.62 — Observabilidade Langfuse: Fase 1 do PROMPT MESTRE)

- [x] Ao ser perguntado se `PROMPT MESTRE — EVOLUÇÃO DA SALEIA.txt` (raiz do repo) estava finalizado, auditoria do codigo real encontrou `services/observability/` (Langfuse) ja criado e integrado numa sessao anterior do mesmo dia, mas nunca commitado/documentado, com 1 teste falhando.
- [x] Corrigido vazamento de ContextVar entre testes (`tests/test_observability.py` — teste que abria trace sem fechar contaminava o teste seguinte): 15/15 testes passando.
- [x] TAREFA 1.7 (instrumentar Skill Resolver): `agent/skill_resolver.py::resolver_skill_context` ganha span `skill_resolver` com candidatos considerados/skill selecionada/score/DISC/estagio/prioridade. 10 testes novos (`tests/test_skill_resolver.py`).
- [x] Fallback rastreado tambem para a Conta Claude pessoal (`agent/multiagente/claude_fallback.py`) — antes so virava `AiUsageEvent` (Cost Intelligence), agora tambem gera `record_generation` no Langfuse.
- [x] TAREFA 1.8/1.9 (custo por agente, dashboard minimo) resolvidas por reuso, sem UI nova: `custo_por_reuniao()` (Cost Intelligence Fase 1) ja agrega por `feature`, e `realtime.coach/disc/finance/closer` ja sao os 4 agentes — ja visivel na aba Custos ("Por Feature"); Monitor ja cobre reunioes/latencia/chamadas/fallbacks/erros/provider.
- [x] `.env.example` documentado (`OBSERVABILITY_ENABLED`/`OBSERVABILITY_PROVIDER`/`LANGFUSE_*`/`OBSERVABILITY_CAPTURE_TRANSCRIPT`) — faltava desde a sessao anterior.
- [x] Suite completa (`discover tests`): 389 testes, 8 falhas pre-existentes e nao relacionadas (mesmas de sempre, `test_next_best_question.py`/`test_realtime_memory.py`), sem regressao.
- **Confirmado na mesma auditoria**: Fase 4 do PROMPT MESTRE (Book-to-Skill) ja estava ~90% pronta em producao (= Biblioteca de Inteligencia, V.1.4.52-54). Fases 2, 3, 5, 6, 7 e a maior parte da 8 do roadmap **nao foram iniciadas**.
- **Pendente**: commit/push ainda nao feitos (aguardando confirmacao do usuario); deploy na VPS pendente; `OBSERVABILITY_ENABLED` continua `false` (decisao de ativar de fato em producao e separada — precisa de conta Langfuse configurada).

## Concluido (Fase 2 do PROMPT MESTRE — Promptfoo / Evaluation Suite, harness criado)

- [x] `evals/` criado (TAREFA 2.1): `promptfooconfig.yaml` (Coach), `promptfooconfig.finance.yaml` (Finance), `promptfooconfig.redteam.yaml` (red team) — 3 configs separadas porque os schemas de saida dos agentes diferem.
- [x] `evals/providers/coach_provider.py`/`finance_provider.py`: bridges Python que chamam os agentes reais (`agent.multiagente.coach_agent.analisar_coach`/`finance_agent.analisar_finance`) diretamente — sem duplicar a logica de chamada de IA (`api/ai_router.py`).
- [x] Golden Dataset (TAREFA 2.2/2.3): 22 casos **sinteticos** (2 por categoria) cobrindo as 11 categorias minimas em `datasets/coach/objections_golden.yaml` — nao sao reunioes reais anonimizadas (sem acesso a MySQL de producao nesta sessao); aviso explicito no topo do arquivo.
- [x] Next Best Action (TAREFA 2.4): `datasets/coach/next_best_action.yaml`, incluindo o exemplo literal do prompt mestre (mapear decisor, nunca desconto/pressao).
- [x] Finance Agent: `datasets/finance/price_objections.yaml` (preco, caixa, ROI, checagem de nao-alucinacao de valores).
- [x] Red teaming (TAREFA 2.8): `scenarios/red_team.yaml` (6 casos — injection, role override, exfiltracao, injecao de desconto, JSON malformado, pressao de fechamento).
- [x] Criterios de aprovacao (TAREFA 2.7): `evals/APPROVAL_CRITERIA.md`.
- [x] CI (TAREFA 2.9): `.github/workflows/llm-evals.yml`, roda em PRs que tocam prompts/AI Router/RAG/Skills/Agents.
- [x] `evals/README.md` (TAREFA 2.10) documentando tudo + pendencias explicitas.
- [x] `package.json` na raiz de `SALEIA/` (devDependency `promptfoo@0.122.2`, so pra rodar o eval — backend continua 100% Python).
- [x] Validado sem rodar eval real (custaria dinheiro): YAMLs parseiam (`yaml.safe_load`), providers compilam (`py_compile`), imports dos agentes reais funcionam dentro do venv do projeto (falham no Python global por falta de `fastapi` — documentado).
- **Pendente**: substituir dataset sintetico por reunioes reais anonimizadas (TAREFA 2.2, precisa acesso a producao); TAREFA 2.5 (comparacao entre os 4 providers) bloqueada pelo incidente de saldo/chave ja documentado; TAREFA 2.6 (comparacao de versoes de prompt) sem objeto ainda; configurar secrets `EVAL_*_API_KEY` no GitHub; estender cobertura para DISC/Closer agents.

## Concluido (Fase 2 Promptfoo — primeira execucao real, 05/09/2026)

- [x] Rodada real confirmada pelo usuario (custo estimado ~US$0,01-0,35 aceito antes de rodar): Coach 27/27, Finance 4/4, Red Team 6/6 (apos corrigir 2 falsos positivos de assert) — **37/37 passou no total**, custo real US$ 0,0122.
- [x] Achado corrigido: `DEEPSEEK_API_KEY` no `.env` local estava invalida (diferente da chave de producao na VPS, que funciona) — usuario forneceu chave de teste nova, aplicada diretamente no `.env` local.
- [x] Achado corrigido: venv local sem `google-generativeai` (pinado em `requirements.txt`, nunca instalado nesta maquina) — instalado, sem regressao (`test_smoke` 8/8 OK).
- [x] Achado registrado (fora do escopo, nao corrigido agora): pacote `google.generativeai` totalmente descontinuado pelo Google (avisa pra migrar pra `google.genai`); modelo `claude-sonnet-4-20250514` deprecado com EOL 15/06/2026.
- [x] Achado corrigido: 2 dos 6 casos de red team davam falso `[FAIL]` porque o assert checava o JSON inteiro, incluindo campos que citam a fala do cliente verbatim por design (`filtro_cliente.frases_chave`/`key_moments[].quote`) — corrigido restringindo aos campos falados/exibidos ao vendedor.
- [x] Fix de path: `outputPath` das 3 configs apontava pra fora de `evals/` (resolvia relativo ao CWD, nao ao config) — corrigido.
- [x] Secret `EVAL_DEEPSEEK_API_KEY` configurado no GitHub (Settings > Secrets and variables > Actions) — unico obrigatorio hoje, ja que e o unico provedor com saldo valido; `.github/workflows/llm-evals.yml` atualizado pra deixar OPENAI/ANTHROPIC/GEMINI comentados (opcionais, prontos pra ativar quando TAREFA 2.5 avancar).
- **Pendente**: TAREFA 2.5 (comparacao real entre os 4 providers) ainda bloqueada — OpenAI/Anthropic confirmados sem saldo nesta mesma sessao, Gemini nunca teve a chave testada de fato (so o pacote foi instalado).

## Concluido (V.1.4.63 — Whisper Local, parte da Fase 3 do PROMPT MESTRE)

- [x] Investigacao previa: `chrome-extension/offscreen.js` ja captura audio do microfone (getUserMedia+MediaRecorder, chunks 15s) e `POST /audio-transcricao` ja transcreve via Groq/OpenAI — so faltava um provedor self-hosted, nao a captura em si.
- [x] Escopo confirmado com o usuario: Whisper self-hosted na VPS (nao app local na maquina do vendedor), reaproveitando a estrutura existente (`TRANSCRICAO_PROVEDOR`) em vez de criar `services/transcription/` — "mantenha a estrutura original... usar uma funcao pra alternar".
- [x] `agent/whisper_local.py` (novo): `faster-whisper` (CPU, sem torch), singleton por processo, nunca cai silenciosamente pra provedor pago em falha.
- [x] `api/main.py`: `/audio-transcricao` refatorado em 3 funcoes (`_transcrever_via_openai`/`_transcrever_via_groq`/`_transcrever_via_whisper_local`) despachadas por dict; `_TRANSCRICAO_PROVEDORES["whisper_local"]` com `env_key: None` (nao exige chave); endpoints admin tratam esse caso.
- [x] `requirements.txt` (`faster-whisper>=1.0.0`), `.env.example` (`WHISPER_LOCAL_MODEL`/`_DEVICE`/`_COMPUTE_TYPE`), `frontend/dashboard.html` (card sem campo de chave).
- [x] 13 testes novos (`test_whisper_local.py` 8 + `test_transcricao_config.py` 5, todos mockados — nunca escrevem no `.env` real nem baixam modelo real).
- [x] **Validacao real de ponta a ponta** (sem mock): instalado `faster-whisper` de verdade, modelo `small` baixado do Hugging Face (~15,8s), transcricao de WAV de silencio retornou vazio corretamente.
- [x] Suite completa: 402 testes, mesmas 4 falhas pre-existentes e nao relacionadas de sempre, sem regressao.
- [x] Versao: `1.4.62` → `1.4.63`.
- [x] **Deploy na VPS confirmado (05/09/2026 ~19h47 UTC)**: `reunioes_ativas: 0` checado antes/depois; `git pull` fast-forward `e6eefa4`->`48538a4` (trouxe tambem V.1.4.62/Langfuse, nunca deployada); `pip install`+`pip check` limpo; `systemctl restart saleia` ativo, journal sem excecoes; `/health` = `versao 1.4.63`.
- [x] **Validado o risco do timeout do nginx**: rodado um processo Python separado na propria VPS (sem mexer no servico rodando) baixando o modelo `small` e transcrevendo um audio de teste — 4,4s no total, bem abaixo de qualquer `proxy_read_timeout` default. Risco baixo, nao e mais pendencia.
- **Pendente**: captura de audio do sistema/aba (so microfone hoje); abstracoes formais MeetingCaptureProvider/TranscriptionProvider (TAREFA 3.1/3.2/3.4) deliberadamente nao criadas; Parakeet (TAREFA 3.6, opcional no prompt mestre); benchmark WER real (TAREFA 3.12); ativar `TRANSCRICAO_PROVEDOR=whisper_local` de fato em producao (decisao de produto separada).

## Concluido (Extensao Chrome V.1.4.6 — fix transcricao poluida por outra extensao)

- [x] Usuario testou reuniao real com Whisper Local ja ativo em producao, mas nada aparecia no dashboard — investigacao nos logs da VPS confirmou zero chamadas de `/tempo-real`/`/audio-transcricao` chegando ao servidor (problema era 100% client-side).
- [x] Diagnostico via Console do DevTools na aba do Meet: `content.js` capturava "Nenhuma reuniao ativa" (texto do painel flutuante do EasySub, outra extensao do usuario na mesma aba) como se fosse fala real.
- [x] Causa raiz: `iniciarObservadorLegendas()` observa `document.body` inteiro (nao so o Meet), so exclui `#saleia-sidebar`; a lista `CAPTION_SELECTORS` existe no arquivo mas nunca e usada pra restringir.
- [x] Fix minimo: 3 novas regras em `eRuidoUI()` excluindo os textos exatos conhecidos do EasySub ("Nenhuma reuniao ativa", "Finalizar captura", "Capturar audio (Whisper)") — mesmo padrao heuristico ja usado no arquivo.
- [x] Versao da extensao: `1.4.5` -> `1.4.6`.
- [x] **Causa raiz real do "nada aparece no dashboard" identificada e resolvida**: nao era so ruido de UI — era o content script ficando **orfao** apos multiplos reloads da extensao durante a sessao de debug (aba do Meet aberta antes de um reload da extensao perde a conexao com o novo service worker; `chrome.tabs.sendMessage`/`chrome.runtime.sendMessage` falham silenciosamente). Confirmado removendo e adicionando a extensao do zero + abrindo aba nova — `/iniciar-sessao`, `/audio-transcricao` e `/tempo-real` passaram a responder 200 OK imediatamente, com `ext_ver: "1.4.6"` confirmado nos logs.
- [x] Usuario cobrou verificacao antes de assumir regressao: confirmado via logs da VPS que `/iniciar-sessao` nunca tinha sido chamado com sucesso em NENHUM teste do dia (nem antes de qualquer mudanca de codigo) — nao foi uma mudanca desta sessao que quebrou o registro em "Sessoes ao Vivo", era o mesmo problema de conexao desde o inicio.
- **Pendente**: fix mais robusto no filtro de ruido (escopar o observer a um container real do Meet, ou excluir o container do EasySub explicitamente) — precisaria inspecionar o codigo do EasySub pra achar um seletor confiavel; hoje e so whack-a-mole por texto exato.

## Concluido (V.1.4.64 — fix Sales Memory sem contexto no tempo real)

- [x] Achado durante a validacao ao vivo acima: toda chamada de `/tempo-real` gerava `ERROR [Ollama] embed() sincrono chamado dentro de um event loop ativo` + `WARNING [SalesMemory] Falha ao gerar embedding via ollama` — a busca de Sales Memory ficava sempre desativada, silenciosamente, sem afetar a analise (degradava com seguranca, so sem contexto extra).
- [x] Causa raiz: `agent/multiagente/orquestrador.py` chama `sales_memory.buscar_contexto_para_reuniao()` sem `await` (decisao de design documentada, mesmo padrao de `api/database.py::buscar_conhecimento_compilado_similar`) — mas `OllamaEmbeddingProvider.embed()` usa `asyncio.run()` internamente, que quebra dentro de um loop ja ativo. Como `EMBEDDING_PROVIDER=ollama` e o padrao desde a V.1.4.39, isso acontecia em toda chamada real.
- [x] Fix em `services/embeddings/ollama_provider.py::embed()`: detecta proativamente loop ativo (`asyncio.get_running_loop()`) e roda `embed_async()` numa thread separada com loop isolado quando necessario — sem mudar a decisao de design de chamar sem `await`, so conserta a camada do provider.
- [x] 2 testes novos reproduzindo o bug real dentro de `IsolatedAsyncioTestCase`. Suite de embeddings: 34/34 OK.
- [x] Validado com Ollama real (nao mockado): passou pela ponte de thread corretamente, degradou por "conexao recusada" (esperado, sem Ollama local) em vez do erro de loop.
- [x] Versao: `1.4.63` -> `1.4.64`.
- **Pendente**: deploy na VPS + validar que o Sales Memory volta a aparecer no contexto de `/tempo-real` em producao real.

## Concluido (V.1.4.65 — Skill Resolver V2, inicio da Fase 5)

- [x] Investigacao previa: dos 11 sinais novos pedidos pelo prompt mestre, so 4 tem sinal estruturado real hoje (buying_signal via key_moments/eventos; budget_status/decision_maker_status/urgency via Closer::maturity_score). Os outros 7 (objection_type, pain_type, product, segment, competitor, meeting_type, risk) nao sao classificados por nenhum agente hoje — nao implementados, pra nao filtrar sobre dado inexistente.
- [x] `agent/skill_resolver.py`: `resolver_skills_relevantes()` (TAREFA 5.2/5.3) retorna `{primary, supporting (max 2), cases (max 1)}` em vez de 1 unica vencedora; `_sinal_bool_match()` + `_candidatos_aplicaveis_v2()` adicionam os 4 triggers novos como opcionais (skill que nao declara continua batendo igual — zero regressao nas 5 skills builtin/custom existentes).
- [x] "cases" reconhecidos pelo prefixo `[CASE]` que `mapear_knowledge_item_para_skill()` ja grava no `system_injection` (reaproveita dado existente).
- [x] 8 testes novos + validado sem mock contra as 5 skills builtin reais: `primary` bateu 100% com `resolver_melhor_skill()` em 3 cenarios, `supporting` trouxe skill extra aplicavel num deles.
- [x] Versao: `1.4.64` -> `1.4.65`.
- **Deliberadamente NAO feito**: `resolver_skills_relevantes()` nao foi plugada em `api/processador_tempo_real.py` — `resolver_melhor_skill()`/`resolver_skill_context()` continuam sendo o unico caminho ativo em producao. Integrar (mesmo que em shadow mode primeiro, como Cost Router/Otimizacao) e decisao de produto separada.

## Concluido (V.1.4.66 — Marcar reuniao ganha/perdida (UI) + outcome no retrieval, TAREFA 6.4 da Fase 6)

- [x] Investigacao previa confirmou `meeting_status`, `client_profiles` e `client_meetings` com 0 linhas em producao. Causa raiz: botao de marcar reuniao como ganha ja existia (`marcarComoGanha()`, `PATCH /relatorios/{id}/status`), mas era pouco visivel (0.7rem, sem opcao "Perdida") — ninguem usava de fato. Correcao de uma afirmacao errada feita antes na mesma investigacao (uma busca por `marcar-ganha`, slug antigo ja renomeado, deu falso negativo).
- [x] `frontend/dashboard.html`: `marcarComoGanha()` substituida por `statusReuniaoBotoesHTML()`/`marcarStatusReuniao()` — botoes "Ganha"/"Perdida" lado a lado (ou badge quando ja decidido), em 2 contextos (`card` discreto na lista, `detalhe` destacado num card proprio "Resultado desta reuniao" na tela de detalhe). Mesmo endpoint de sempre, sem mudanca de backend pra isso.
- [x] `agent/sales_memory.py`: `buscar_memorias_semantico()` agora ajusta o ranking por cosseno usando o outcome da reuniao de origem — `won` +0.05, `lost` -0.10 (capado em [0,1]), sem status = neutro (100% das memorias hoje). Resolve status via `agent.playbook_generator.listar_status_reunioes()` (IN-clause numa tabela so) — nunca JOIN direto entre `sales_memories` e `meeting_status`, que quebra por incompatibilidade real de collation entre as duas colunas (achado durante a investigacao). Escopo restrito a `sales_memories` (unica fonte com link direto e confiavel via `source_meeting_id`) — `base_conhecimento` (sem coluna de meeting-id) e `knowledge_items` (curadoria manual) ficam de fora, deliberadamente.
- [x] Campo novo `"outcome"` em cada resultado de `buscar_memorias_semantico()` — aditivo, nao quebra `buscar_contexto_para_reuniao()` nem `GET /sales-memories/buscar`.
- [x] 13 testes novos em `tests/test_sales_memory.py` (ajuste puro, resolucao de status, fluxo completo de ranking incluindo reordenacao e top_k).
- [x] Versao: `1.4.65` -> `1.4.66`.
- **Pendente**: deploy na VPS (mudanca de `agent/sales_memory.py` exige `git pull` + `systemctl restart saleia`; `dashboard.html` e estatico, nao exige restart). Efeito real do ajuste de ranking so aparece conforme reunioes forem marcadas pelos novos botoes — base ainda vazia no momento do commit.

## Concluido (V.1.4.67-1.4.70 — EPIC SALES BRAIN: gaps + Fase 7 Sales Operating System)

Usuario colou o EPIC "SALEIA SALES BRAIN" completo (Fases 1-7) e perguntou se ja estava implementado. Investigacao confirmou Fases 1-6 ja em producao desde V.1.4.31-37; 3 lacunas encontradas + Fase 7 (nao existia) foram tratadas nesta sessao, em 4 rodadas de versao. Detalhe completo por rodada no CHANGELOG.md.

- [x] V.1.4.67 — Busca semantica de relatorios/transcricoes (`agent/semantic_search.py`, novo, tabela `semantic_index`, `GET /busca-semantica`) — so para busca humana, nunca injetada no prompt de IA em tempo real (evita duplicar contexto). Card "Resumo do Cliente" (`GET /clientes/resumo-reuniao/{meeting_id}`) na tela de detalhe da reuniao no Dashboard — achado importante: `cenario.html` e a tela do proprio CLIENTE, colocar o resumo la vazaria objecoes/dores internas de volta pro cliente. Coluna `status` (default `approved`) preparada em `sales_memories`/`playbooks`/`skills` para a rodada seguinte. 13 testes novos.
- [x] V.1.4.68 — Pipeline automatico-com-aprovacao (Fase 7.3): memoria/playbook/skill gerados por IA nascem `pending`, so entram em RAG/producao apos aprovacao (`PATCH /sales-memories/{id}/status` novo; `PATCH /playbooks|skills/{id}` reusados, so ganharam `status` na whitelist editavel). Playbook auto-gerado agora auto-dispara geracao de skill (lacuna real do EPIC — antes so o botao manual existia). Kill-switch `SALES_BRAIN_AUTOPILOT_ENABLED`. 18 testes novos.
- [x] V.1.4.69 — Knowledge Graph (Fase 7.2): `agent/knowledge_graph.py` (tabela `graph_edges`, arestas simples, sem lib de grafo), hooks best-effort nos 4 pontos de criacao (cliente-reuniao, reuniao-memoria, reuniao-playbook, playbook-skill), `GET /grafo/conexoes/{tipo}/{id}`, backfill `scripts/backfill_knowledge_graph.py --dry-run`. 9 testes novos.
- [x] V.1.4.70 — Workspace Comercial (Fase 7.1): nova aba no Dashboard agregando contadores + fila de pendencias de aprovacao + busca semantica + painel de conexoes (`GET /workspace/resumo`, `GET /workspace/pendencias`). 8 testes novos.
- [x] Decisao deliberada, nao implementada: skills como pastas de arquivo (pedido literal do EPIC) — regressao funcional frente ao que ja existe (skills em MySQL, editaveis pelo dashboard, integradas ao skill_resolver).
- **Pendente**: deploy das 4 rodadas juntas na VPS (`git pull` + `systemctl restart saleia` — 2 tabelas novas aditivas `semantic_index`/`graph_edges` + coluna `status` nova em 3 tabelas, tudo com DEFAULT seguro); estender botao "Conexoes" aos cards de Playbooks/Skills (hoje so na pagina Clientes); backfill real do Knowledge Graph (`scripts/backfill_knowledge_graph.py`, sem `--dry-run`) apos deploy.

## Concluido (V.1.4.71 — Big Five + Astrologia opcional)

Usuario colou um spec de 60 tarefas pra um modulo de autoconhecimento do vendedor (Big Five/DISC via questionario + astrologia com mapa natal). Escopo real, depois de discussao: entender melhor *por que o cliente* respondeu daquela forma/fez aquela objecao — nao um produto novo, extensao do motor multiagente ja existente.

- [x] 5o agente em tempo real `agent/multiagente/bigfive_agent.py` (infere Big Five do CLIENTE a partir da conversa, sem questionario, mesmo padrao do disc_agent.py) — atras do kill-switch `BIGFIVE_AGENT_ENABLED` (default true, zero custo quando desligado). `perfil_bigfive` persiste em `MeetingMemory.current_diagnosis` (reuso, sem coluna nova) e realimenta Coach/Closer no ciclo seguinte automaticamente.
- [x] `agent/signo_solar_rules.py` (novo) — signo solar puro (dia+mes, sem mapa natal/efemerides), 12 signos estruturados. So usado quando o cliente menciona o proprio aniversario espontaneamente na conversa (nunca perguntado) — extraido 1x por `PROMPT_RECAPITULACAO` (mesma chamada de IA, sem custo novo).
- [x] `client_profiles` ganha `data_nascimento_dia`/`data_nascimento_mes` (nullable) — `salvar_nascimento_cliente()` nunca sobrescreve. `obter_cliente()` anexa `perfil_astrologico` automaticamente (aparece de graca no card Resumo do Cliente, V.1.4.67).
- [x] `objecoes_com_motivo` + `sintese_comportamental` (campos aditivos no `PROMPT_RECAPITULACAO`, cruzando DISC+Big Five) — `objecoes_levantadas` (lista de strings) nunca mudou de tipo, pra nao repetir a classe de bug "[object Object]" ja corrigida antes (renderiza em 4+ lugares do dashboard).
- [x] Garantia por construcao (nao so por instrucao de prompt): nenhum prompt de DISC/Big Five tem placeholder de entrada pra dado de signo/astrologia — teste de guarda arquitetural confirma isso via grep + inspecao de imports.
- [x] Dashboard: 4 cards novos (Big Five, Por que essas objecoes aconteceram, Sintese Comportamental, Perfil Astrologico com disclaimer sempre visivel).
- [x] 34 testes novos (`test_signo_solar_rules.py`, `test_bigfive_agent.py`, `test_orquestrador_bigfive.py`, `test_client_intelligence_nascimento.py`, `test_perfil_astrologico_helper.py`). Suite completa sem regressao.
- **Fora de escopo deliberado**: questionario de autoavaliacao do vendedor, mapa natal/efemerides, exibicao em tempo real na extensao Chrome, motor de compatibilidade entre pessoas.
- **Pendente**: deploy na VPS (aditivo — 2 colunas nullable em `client_profiles`, sem migracao em `MeetingMemory`); validar em producao com uma reuniao real onde o cliente menciona o proprio aniversario.

## Concluido (Fase 0 do "SALE-IA V2" — baseline de confiabilidade)

Usuario colou o "PROMPT MESTRE — SALE-IA V2" (25 fases, meses de trabalho: SalesEvent, Opportunity, SPIN 2.0, MEDDPICC, Sales Science, Seller DNA, Autonomy Policy). Esta rodada cobre so a Fase 0 (Tarefas 0.1/0.2) — baseline de testes + E2E de reuniao completa, 100% aditivo, zero mudanca de comportamento da aplicacao. Fases 1+ (SalesEvent em diante) ainda NAO comecaram.

- [x] Baseline real medido (nao estimado de doc antiga): `python -m unittest discover tests` = 512 testes, 0 falhas, 1 skip pre-existente, ~800s. Relatorio completo em `docs/BASELINE_REPORT_FASE0.md` (10 categorias — as 9 pedidas pelo prompt mestre + uma 10a "Sales Brain/Multiagente" que a investigacao mostrou ser necessaria).
- [x] `tests/test_smoke.py` estendido (9 -> 14 testes): `/auth/login`, `POST /iniciar-sessao`, Biblioteca (upload+extracao via TestClient real, nao so as funcoes internas), `/busca-semantica` (RAG via TestClient).
- [x] `tests/test_e2e_meeting_lifecycle.py` (novo, 6 testes): reuniao completa (iniciar-sessao -> 3 ciclos de /tempo-real com objecao de preco -> MeetingMemory acumulando corretamente, sem duplicar transcricao -> /recapitulacao-viva lendo a memoria real) + isolamento entre 2 reunioes + 2 testes de degradacao (todos os provedores falhando, JSON invalido de 1 provedor).
- [x] **Achado de seguranca real (documentado, nao corrigido)**: `MeetingMemory` nao tem `usuario_id`, `/recapitulacao-viva` nao exige auth nenhuma — qualquer pessoa que souber um `meeting_id` consegue ler a recapitulacao viva de outra reuniao. Teste `test_ACHADO_recapitulacao_viva_sem_auth_nem_ownership` documenta o comportamento atual de proposito (falha quando alguem corrigir, nao esconde atras de skip/xfail).
- [x] **Achado real sobre degradacao**: quando os 4 provedores centrais falham, o sistema NAO retorna erro — cada agente falha isolado dentro do orquestrador (`_safe()`/`asyncio.gather`), resultado final vem com `analysis_status: "updated"` e fallbacks genericos, sem nenhum sinal visivel de falha. Nao e bug (o sistema nao quebra), e lacuna de observabilidade — registrado para decisao de produto futura.
- [x] **Achado registrado, nao resolvido**: extensao Chrome (`chrome-extension/*.js`) continua 100% sem teste automatizado — criar Jest do zero seria tooling desproporcional ao resto da Fase 0 (so Python). Fica como divida tecnica.
- **Fora de escopo desta rodada**: qualquer codigo de dominio (SalesEvent, Opportunity, SPIN 2.0, MEDDPICC, etc.), decisao de Clean Architecture (nao ha codigo de dominio ainda pra decidir onde morar), correcao dos achados acima.
- **Proximo passo, se o usuario confirmar**: Fase 1 (Tarefa 1.1 — SalesEvent) e a proxima na ordem definida pelo prompt mestre — nao comecar sem essa confirmacao explicita, dado o tamanho da mudanca arquitetural envolvida.

## Concluido (V.1.4.73 — SalesEvent, Tarefa 1.1 da Fase 1 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou explicitamente o inicio da Fase 1. Escopo desta rodada: so a Tarefa 1.1 (criar o schema/validacao do SalesEvent) — Tarefa 1.2 (SalesEvidence) nao comecou.

- [x] `api/database.py::SalesEvent` (SQLModel, tabela `sales_events`) — schema completo do prompt mestre (meeting_id, opportunity_id sem FK ainda/client_id/seller_id/event_type/timestamp/speaker/evidence_quote/source/confidence/metadata/created_at).
- [x] `agent/sales_event_rules.py` (novo, funcao pura, mesmo padrao de propensao_rules.py/signo_solar_rules.py): `SALES_EVENT_TYPES` (14 categorias) + `validar_sales_event()` (ValueError em event_type invalido, confidence fora de [0,1], evidencia ausente quando source="conversation").
- [x] `criar_sales_event()`/`obter_sales_event()`/`listar_sales_events()` em `api/database.py` — SalesEvent e dado de dominio (decisao deliberada: propaga ValueError, diferente do padrao "melhor esforco" de AiUsageEvent/KnowledgeItem). Sem endpoint HTTP novo (fora do enunciado da Tarefa 1.1).
- [x] Decisao deliberada: teste de integracao reproduz o exemplo do prompt mestre ("Achei caro" -> OBJECTION_RAISED/category=PRICE) chamando `criar_sales_event()` direto com esses valores — sem construir extracao automatica de eventos a partir de transcricao livre (fora do enunciado da Tarefa 1.1, fica para tarefa futura).
- [x] 12 testes novos (`tests/test_sales_event.py`). Suite completa: 524 testes (512 + 12), 0 falhas, 1 skip pre-existente — sem regressao.
- [x] Versao: `1.4.72` -> `1.4.73`.
- **Pendente**: push + deploy na VPS (aditivo, 1 tabela nova via create_all()). **Tarefa 1.2 (SalesEvidence) e qualquer fase seguinte nao comecam sem nova confirmacao explicita do usuario.**

## Concluido (V.1.4.74 — SalesEvidence, Tarefa 1.2 da Fase 1 do "PROMPT MESTRE — SALE-IA V2")

Sequencia direta da Tarefa 1.1. Objetivo: separar interpretacao de evidencia — nunca salvar so "cliente esta inseguro", sempre type=ADOPTION_RISK + quote="Tenho medo da minha equipe nao usar".

- [x] `api/database.py::SalesEvidence` (SQLModel, tabela `sales_evidences`) — schema literal do prompt mestre (id/meeting_id/type/quote/speaker/timestamp/confidence/source/created_at), sem FK para SalesEvent de proposito.
- [x] `agent/sales_evidence_rules.py` (novo, funcao pura): `validar_sales_evidence()` — ValueError em type vazio, quote vazia/ausente, confidence fora de [0,1]. Regra central da tarefa: quote obrigatoria e nao-vazia (hipotese sem evidencia nunca persiste).
- [x] `criar_sales_evidence()`/`obter_sales_evidence()`/`listar_sales_evidences()` em `api/database.py` — mesma convencao "dado de dominio" da Tarefa 1.1, sem endpoint HTTP novo.
- [x] 10 testes novos (`tests/test_sales_evidence.py`), incluindo o exemplo literal do prompt mestre. Suite completa: 534 testes (524 + 10), 0 falhas, 1 skip pre-existente — sem regressao.
- [x] Versao: `1.4.73` -> `1.4.74`.
- [x] Push para o GitHub (commit `6b9a0ab`, bundlando Fase 0 + Tarefa 1.1 + Tarefa 1.2).
- [x] **Deploy confirmado na VPS (10/09/2026, ~19h05 UTC)**: `reunioes_ativas: 1` bloqueou o restart por ~55min (reuniao real em andamento) — `git pull` (fast-forward `615864e` -> `6b9a0ab`) + `pip install`/`pip check` feitos antes, sem risco (so atualiza arquivos em disco). Assim que `reunioes_ativas` chegou a `0`, `systemctl restart saleia` executado — `active`, sem erros/tracebacks no journal. Pos-restart: `/health` local = `versao 1.4.74`, `status online`, `reunioes_ativas 0`; `/dashboard` e `/health` publicos (`api.saleia.app.br`) responderam `200`.
- **Fase 2 (Opportunity Memory) do roadmap nao comeca sem nova confirmacao explicita do usuario.**

## Concluido (V.1.4.75 — Opportunity Memory + Opportunity Graph, Fase 2 completa do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para a Fase 2 (Tarefa 2.1) e depois para a Tarefa 2.2, sem esperar o resultado da suite intermediaria. As duas tarefas ficaram prontas.

- [x] Tarefa 2.1 — `api/database.py::Opportunity`/`OpportunityMemory` (13 categorias, listas JSON append-only de insights) + `agent/opportunity_memory_rules.py` (`adicionar_insight()` — nunca sobrescreve, registra contradicao quando o mesmo campo recebe valor diferente). `MeetingMemory` ganha coluna `opportunity_id` (nullable, aditiva). CRUD completo em `api/database.py` (criar/obter/listar Opportunity, atualizar status, vincular/listar meetings, registrar/obter conhecimento). 22 testes novos (`tests/test_opportunity_memory.py`), incluindo o teste literal de "oportunidade com 3 reunioes".
- [x] Tarefa 2.2 — `api/database.py::OpportunityGraphEdge` (grafo novo e deliberadamente separado do `agent/knowledge_graph.py` ja existente do Sales Brain) + `agent/opportunity_graph_rules.py` (9 NODE_TYPES, `evidence` sempre obrigatoria). `criar_aresta_opportunity_graph()`/`listar_arestas_opportunity()`. 15 testes novos (`tests/test_opportunity_graph.py`), incluindo o exemplo literal "dor -> causa -> impacto".
- [x] Suite completa: 571 testes (556 + 15), 0 falhas, 1 skip pre-existente — sem regressao.
- [x] Versao: `1.4.74` -> `1.4.75`.
- [x] Push para o GitHub (commit `451beae`).
- [x] **Deploy confirmado na VPS (10/09/2026, ~20h13 UTC)**: `reunioes_ativas: 0` (sem reuniao ativa desta vez) — `git pull` (fast-forward `6b9a0ab` -> `451beae`) + `pip install`/`pip check` limpos. `ALTER TABLE meeting_memory ADD COLUMN opportunity_id INTEGER` + `CREATE INDEX` aplicados via script idempotente (checou coluna ausente antes de alterar). `systemctl restart saleia` — `active`, journal sem erros. Pos-restart: `/health` = `versao 1.4.75`, `status online`, `reunioes_ativas 0`, 4 provedores de IA `ok`; `/dashboard` e `/health` publicos responderam `200`.
- **Fase 3 (SPIN 2.0) do roadmap nao comeca sem nova confirmacao explicita do usuario.**

## Concluido (V.1.4.76 — SPIN Coverage Engine, Tarefa 3.1, inicio da Fase 3 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar pra Fase 3. Escopo desta rodada: so a Tarefa 3.1 (motor de cobertura) — Tarefa 3.2 (Question Gap Engine, prioridades critical/high/medium/low) nao comecou.

- [x] `agent/spin_coverage_rules.py` (novo, funcao pura, sem IA/banco): `calcular_cobertura_spin()` computa known[]/missing[] por estagio SPIN (situation/problem/implication/need_payoff) a partir de fatos ja estruturados e evidenciados. Regra "nao inventar informacao faltante" imposta recusando (ValueError) fato sem evidence_quote.
- [x] `SPIN_CHECKLIST_PADRAO` (vocabulario default inferido do exemplo literal do prompt mestre, sobrescrevivel por chamada) + `estagio_atual()` + `sugerir_proxima_pergunta()` (bate exatamente com o exemplo do prompt mestre: "Quanto esse problema custa atualmente?").
- [x] Decisao deliberada: extracao automatica de fatos a partir de transcricao livre via IA nao foi construida (fora do enunciado da Tarefa 3.1). Sem integracao com orquestrador.py ainda.
- [x] 13 testes novos (`tests/test_spin_coverage_rules.py`), incluindo o exemplo literal do prompt mestre reproduzido exatamente. Suite completa: 584 testes (571 + 13), 0 falhas, 1 skip pre-existente — sem regressao.
- [x] Versao: `1.4.75` -> `1.4.76`.
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova — modulo puro em memoria). **Tarefa 3.2 (Question Gap Engine) e qualquer fase seguinte nao comecam sem nova confirmacao explicita do usuario.**

## Concluido (V.1.4.77 — Question Gap Engine, Tarefa 3.2 da Fase 3 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para a Tarefa 3.2. Constroi sobre o SPINState (known[]/missing[] por estagio) da Tarefa 3.1.

- [x] `agent/question_gap_rules.py` (novo, funcao pura, sem IA/banco): `calcular_gaps_priorizados(cobertura, prioridade_por_stage=None)` recebe a cobertura ja calculada por `calcular_cobertura_spin()` (Tarefa 3.1) e devolve os gaps (`missing`) com `{stage, campo, priority, pergunta}`, ordenados por prioridade (critical > high > medium > low, as 4 do prompt mestre) e, dentro da mesma prioridade, pela ordem SPIN. `proximo_gap()` retorna o primeiro gap (ou None).
- [x] Pergunta recomendada sempre reaproveitada de `SPIN_PERGUNTAS_PADRAO` (Tarefa 3.1), nunca reinventada — garante por construcao a regra de teste do prompt mestre ("pergunta recomendada precisa estar relacionada ao gap detectado"). Reproduz o exemplo literal: gap `financial_impact` -> "Quanto esse problema custa atualmente?".
- [x] `STAGE_PRIORIDADE_PADRAO` (decisao desta rodada, prompt mestre so define o vocabulario de prioridades, nao a regra de atribuicao): `implication=critical`, `need_payoff=high`, `problem=medium`, `situation=low` — sobrescrevivel por chamada, mesmo padrao de `checklist=` da Tarefa 3.1.
- [x] 10 testes novos (`tests/test_question_gap_rules.py`), incluindo o exemplo literal do prompt mestre. Suite completa sem regressao.
- [x] Versao: `1.4.76` -> `1.4.77`.
- [x] Decisao deliberada: sem integracao com `orquestrador.py`/`processador_tempo_real.py` ainda; sem endpoint HTTP novo — mesma disciplina das Fases 1-3.
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova — modulo puro em memoria). **Fase 4 (MEDDPICC) e qualquer tarefa seguinte nao comecam sem nova confirmacao explicita do usuario.**

## Concluido (V.1.4.78 — Opportunity Qualification Engine, Tarefa 4.1, inicio da Fase 4 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para a Fase 4 (MEDDPICC). Escopo desta rodada: so a Tarefa 4.1 (motor de qualificacao) — Tarefa 4.2 (Deal Risk) nao comecou.

- [x] `agent/meddpicc_rules.py` (novo, funcao pura, mesmo padrao de `spin_coverage_rules.py`/`question_gap_rules.py`, sem IA/banco): `calcular_qualificacao_meddpicc(fatos_conhecidos)` computa o estado dos 8 itens MEDDPICC (metrics/economic_buyer/decision_criteria/decision_process/paper_process/identify_pain/champion/competition) — cada um `{status, confidence, evidence[]}` — a partir de fatos ja estruturados e evidenciados. Agregacao quando ha multiplos fatos sobre o mesmo item: status nunca regride (UNKNOWN -> PARTIAL -> CONFIRMED), confidence usa o maior valor ja visto, evidence acumula todas as quotes.
- [x] Regra de evidencia estendida por decisao deliberada (prompt mestre nao repete a frase pra Tarefa 4.1, mas o schema pedido so faz sentido com a mesma disciplina de SalesEvent/SPIN): item nao pode sair de UNKNOWN sem evidence_quote.
- [x] `resumo_qualificacao(estado)` — nivel geral (fraca/intermediaria/avancada) por contagem de itens CONFIRMED (limiares >=6/>=3, decisao desta rodada). `itens_pendentes(estado)` — itens ainda nao CONFIRMED.
- [x] 14 testes novos (`tests/test_meddpicc_rules.py`), incluindo os 3 cenarios pedidos pelo prompt mestre (oportunidade mal qualificada, intermediaria, enterprise avancada) com resultado esperado definido antes da execucao. Suite completa sem regressao.
- [x] Versao: `1.4.77` -> `1.4.78`.
- [x] Decisao deliberada: sem integracao com `orquestrador.py`/`processador_tempo_real.py`, sem tabela nova, sem endpoint HTTP — mesma disciplina das Fases 1-3.
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova — modulo puro em memoria). **Tarefa 4.2 (Deal Risk) e qualquer fase seguinte nao comecam sem nova confirmacao explicita do usuario.**

## Concluido (V.1.4.79 — Deal Risk Engine, Tarefa 4.2, fecha a Fase 4 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para a Tarefa 4.2. Constroi sobre o estado MEDDPICC da Tarefa 4.1 — fecha a Fase 4 completa.

- [x] `agent/deal_risk_rules.py` (novo, funcao pura, mesmo padrao de `meddpicc_rules.py`/`spin_coverage_rules.py`/`question_gap_rules.py`, sem IA/banco — regra explicita do prompt mestre "nao usar LLM para calcular regras simples"): `calcular_riscos()` devolve os riscos detectados (subconjunto de `DEAL_RISK_TIPOS`, sempre na mesma ordem fixa), os 7 exemplos literais: NO_ECONOMIC_BUYER, NO_CHAMPION, NO_NEXT_STEP, NO_METRICS, HIGH_PRICE_RESISTANCE, COMPETITOR_ADVANTAGE, STALE_OPPORTUNITY.
- [x] NO_ECONOMIC_BUYER/NO_CHAMPION/NO_METRICS derivam direto do `estado_meddpicc` (Tarefa 4.1) — item nao CONFIRMED dispara o risco. Os outros 4 recebem sinal explicito do chamador (booleano/contagem/dias) — de onde vem cada sinal em producao real e integracao futura, fora do escopo desta tarefa.
- [x] COMPETITOR_ADVANTAGE e sinal explicito, nao deriva do item `competition` do MEDDPICC (aquele so indica se o cenario competitivo foi mapeado, nao quem esta na frente).
- [x] Limiares (LIMIAR_OBJECOES_PRECO_PADRAO=3, LIMIAR_DIAS_STALE_PADRAO=21) — decisao desta rodada, sobrescreviveis por chamada.
- [x] 13 testes novos (`tests/test_deal_risk_rules.py`), incluindo o exemplo literal do prompt mestre (dor forte + sem decisor + sem proxima reuniao -> pelo menos NO_ECONOMIC_BUYER e NO_NEXT_STEP). Suite completa sem regressao.
- [x] Versao: `1.4.78` -> `1.4.79`.
- [x] Decisao deliberada: sem integracao com `orquestrador.py`/`processador_tempo_real.py`, sem tabela nova, sem endpoint HTTP — mesma disciplina das Fases 1-4.
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova — modulo puro em memoria). **Fase 5 (Motivacao e Comportamento) e qualquer tarefa seguinte nao comecam sem nova confirmacao explicita do usuario.**

## Concluido (V.1.4.80 — Buyer Motivation Engine, Tarefa 5.1, inicio da Fase 5 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para a Fase 5 (Motivacao e Comportamento). Escopo desta rodada: so a Tarefa 5.1 (motor de motivacao) — Tarefa 5.2 (Behavioral Signal Engine) nao comecou.

- [x] `agent/buyer_motivation_rules.py` (novo, funcao pura, mesmo padrao de `meddpicc_rules.py`/`sales_event_rules.py`, sem IA/banco): `MOTIVATION_TIPOS` (12 motivadores literais do prompt mestre: GROWTH, SECURITY, CONTROL, STATUS, CONVENIENCE, SPEED, COST_REDUCTION, REVENUE_GAIN, RISK_REDUCTION, PRODUCTIVITY, RECOGNITION, SIMPLICITY) — taxonomia controlada. `validar_hipoteses_motivacao(hipoteses)` valida cada `{motivation, confidence, evidence[]}` (evidencia obrigatoria e nao-vazia). `motivacao_dominante(hipoteses)` retorna a de maior confidence, ou None.
- [x] Regra "DISC nunca deve ser tratado como motivacao" garantida por construcao (nao so por convencao): modulo nao importa/le nada relacionado a DISC — `tests/test_buyer_motivation_rules.py::GuardaArquiteturalTest` confirma via grep, mesmo padrao de `signo_solar_rules.py`.
- [x] Teste do prompt mestre reproduzido: 3 turnos com DISC externo constante ("D"), motivacao mudando turno a turno — sistema diferencia corretamente.
- [x] 14 testes novos (`tests/test_buyer_motivation_rules.py`). Suite completa sem regressao.
- [x] Versao: `1.4.79` -> `1.4.80`.
- [x] Decisao deliberada: sem integracao com `orquestrador.py`/`processador_tempo_real.py`, sem tabela nova, sem endpoint HTTP — mesma disciplina das Fases 1-4.
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova — modulo puro em memoria). **Tarefa 5.2 (Behavioral Signal Engine) e qualquer fase seguinte nao comecam sem nova confirmacao explicita do usuario.**

## Concluido (V.1.4.81 — Behavioral Signal Engine, Tarefa 5.2, fecha a Fase 5 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para a Tarefa 5.2. Fecha a Fase 5 (Motivacao e Comportamento) completa.

- [x] `agent/behavioral_signal_rules.py` (novo, funcao pura, mesmo padrao de `buyer_motivation_rules.py`, sem IA/banco): `BEHAVIORAL_SIGNAL_TIPOS` (6 sinais literais do prompt mestre: LOSS_AVERSION, STATUS_QUO_BIAS, SOCIAL_PROOF_REQUEST, AUTHORITY_REQUEST, PRICE_ANCHOR, RISK_AVERSION). `validar_sinais_comportamentais(sinais)` exige `evidence_quote` por sinal (regra literal: "cada sinal precisa apresentar trecho da conversa que o sustenta").
- [x] `detectar_sinais(sinais_observados)` valida e enriquece cada sinal com descricao canonica sobria do tipo (`DESCRICOES_SINAIS`, nunca texto livre) — garante por construcao a regra "evitar alegacoes como 'o cerebro reptiliano foi ativado'". `contagem_por_sinal(sinais_observados)` — contagem por tipo.
- [x] 15 testes novos (`tests/test_behavioral_signal_rules.py`), incluindo guarda contra linguagem pseudocientifica nas descricoes. Suite completa sem regressao.
- [x] Versao: `1.4.80` -> `1.4.81`.
- [x] Decisao deliberada: sem integracao com `orquestrador.py`/`processador_tempo_real.py`, sem tabela nova, sem endpoint HTTP — mesma disciplina das Fases 1-5.
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova — modulo puro em memoria). **Fase 6 (Objection Intelligence) e qualquer tarefa seguinte nao comecam sem nova confirmacao explicita do usuario.**

## Concluido (V.1.4.82 — Taxonomia de Objecoes, Tarefa 6.1, inicio da Fase 6 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para a Fase 6 (Objection Intelligence). Escopo desta rodada: so a Tarefa 6.1 (taxonomia + separacao spoken/root cause) — Tarefa 6.2 (Negotiation Engine) nao comecou.

- [x] `agent/objection_rules.py` (novo, funcao pura, mesmo padrao de `behavioral_signal_rules.py`/`meddpicc_rules.py`, sem IA/banco): `OBJECTION_TIPOS` (13 categorias literais do prompt mestre: PRICE, VALUE, BUDGET, TIMING, TRUST, ADOPTION, COMPETITOR, AUTHORITY, PRIORITY, IMPLEMENTATION, LEGAL, PROCUREMENT, SECURITY) — vocabulario fechado so pra `objection_spoken`.
- [x] `objection_spoken` e `root_cause_hypothesis` sempre campos separados, nunca fundidos — `root_cause_hypothesis.hypothesis` usa vocabulario livre (exemplo do prompt mestre: ADOPTION_RISK, que nem esta nas 13 categorias de spoken).
- [x] `precisa_investigar(objection_spoken, root_cause_hypothesis=None)` — regra central "'Esta caro.' nao pode virar root_cause=PRICE, confidence 100% automaticamente; sistema deve primeiro recomendar investigacao" imposta estruturalmente: True quando nao ha hipotese ainda, quando confidence < 0.7 (LIMIAR_CONFIANCA_MINIMA_ROOT_CAUSE), ou quando a hipotese so repete categoria+evidencia identicas ao spoken.
- [x] `registrar_objecao(objection_spoken, root_cause_hypothesis=None)` — monta o registro completo `{objection_spoken, root_cause_hypothesis, precisa_investigar}`.
- [x] 16 testes novos (`tests/test_objection_rules.py`), incluindo os 2 exemplos literais do prompt mestre (proibido: PRICE/"Esta caro."/100%/mesma evidencia -> precisa_investigar=True; bom: spoken=PRICE, root=ADOPTION_RISK com evidencia propria -> precisa_investigar=False). Suite completa sem regressao.
- [x] Versao: `1.4.81` -> `1.4.82`.
- [x] Decisao deliberada: sem integracao com `orquestrador.py`/`processador_tempo_real.py`, sem tabela nova, sem endpoint HTTP — mesma disciplina das Fases 1-5.
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova — modulo puro em memoria). **Tarefa 6.2 (Negotiation Engine) e qualquer fase seguinte nao comecam sem nova confirmacao explicita do usuario.**

## Concluido (V.1.4.83 — Negotiation Engine, Tarefa 6.2, fecha a Fase 6 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para a Tarefa 6.2. Fecha a Fase 6 (Objection Intelligence) completa — constroi sobre `objection_rules.precisa_investigar()` da Tarefa 6.1.

- [x] `agent/negotiation_rules.py` (novo, funcao pura, mesmo padrao de `objection_rules.py`/`behavioral_signal_rules.py`, sem IA/banco): `NEGOTIATION_TIPOS` (7 estrategias consultivas literais do prompt mestre: LABEL, MIRROR, CALIBRATED_QUESTION, SUMMARIZE, CLARIFY, VALUE_REFRAME, RISK_REDUCTION), divididas em `ESTRATEGIAS_INVESTIGATIVAS` (4) e `ESTRATEGIAS_POS_INVESTIGACAO` (3) — uniao cobre a taxonomia inteira, sem sobreposicao.
- [x] "Nunca permitir ameaca/mentira/escassez falsa/manipulacao/informacao inventada" garantido por construcao: vocabulario fechado nas 7 estrategias, sem campo de texto livre na API publica. Guarda de teste confirma via grep que nenhuma descricao canonica menciona essas taticas.
- [x] Teste especifico do prompt mestre reproduzido literalmente: cliente diz "Esta caro." -> resultado proibido "Posso dar 20% agora." -> resultado esperado: estrategia de investigacao. `recomendar_estrategia()` reaproveita `precisa_investigar()` (Tarefa 6.1) — enquanto a objecao nao foi investigada, so estrategias investigativas sao permitidas; tentar forcar `VALUE_REFRAME` (ou qualquer pos-investigacao) antes disso levanta ValueError.
- [x] 13 testes novos (`tests/test_negotiation_rules.py`). Suite completa sem regressao.
- [x] Versao: `1.4.82` -> `1.4.83`.
- [x] Decisao deliberada: sem integracao com `orquestrador.py`/`processador_tempo_real.py`, sem tabela nova, sem endpoint HTTP — mesma disciplina das Fases 1-6.
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova — modulo puro em memoria). **Fase 7 (Sales Reasoning Engine) e qualquer tarefa seguinte nao comecam sem nova confirmacao explicita do usuario.**

## Concluido (V.1.4.84 — SalesReasoningEngine, Tarefa 7.1, inicio da Fase 7 do "PROMPT MESTRE — SALE-IA V2", so contrato)

Usuario confirmou avancar para a Fase 7. Antes de implementar, pergunta direta sobre escopo (diferente das Fases 1-6 deterministicas, o prompt mestre pede validacao semantica via Golden Dataset de 50+ cenarios, o que exige IA real) — usuario escolheu: so o contrato de entrada/saida nesta rodada, sem IA.

- [x] `agent/sales_reasoning_engine.py` (novo, nome foge do padrao `*_rules.py` de proposito — prompt mestre chama de "novo servico"): `SALES_REASONING_INPUT_CAMPOS` (11 campos literais: meeting_memory, opportunity_memory, opportunity_graph, spin_state, meddpicc_state, buyer_motivation, objections, behavioral_signals, rag_context, seller_context, historical_patterns) e `SALES_REASONING_OUTPUT_CAMPOS` (10 campos literais: current_state, hypotheses, evidence, missing_information, recommended_framework, next_best_action, next_best_question, avoid, reason, confidence).
- [x] `construir_input_vazio()`/`validar_input_raciocinio(entrada)` — todos os 11 campos de entrada opcionais, validacao so barra chave desconhecida.
- [x] `montar_saida_raciocinio(...)`/`validar_output_raciocinio(saida)` — current_state/recommended_framework/next_best_action/reason obrigatorios; hypotheses/evidence/missing_information/avoid sempre lista (default []); next_best_question e o unico texto opcional (None permitido); confidence em [0,1].
- [x] 14 testes novos (`tests/test_sales_reasoning_engine.py`), incluindo o exemplo literal de saida do prompt mestre (SPIN_IMPLICATION, confidence 0.86). Suite completa sem regressao.
- [x] Versao: `1.4.83` -> `1.4.84`.
- **Pendente**: push + deploy na VPS (sem tabela/coluna nova, zero custo de IA). **O motor de raciocinio real (chamada de IA) e o Golden Dataset de 50+ cenarios da propria Tarefa 7.1, alem de qualquer fase seguinte, nao comecam sem nova confirmacao explicita do usuario.**

## Concluido (V.1.4.85 — SalesReasoningEngine motor real + Golden Dataset, fecha a Tarefa 7.1 da Fase 7 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para o motor real — a parte que a V.1.4.84 deixou pendente por decisao deliberada de escopo.

- [x] `agent/sales_reasoning_engine.py::raciocinar_async()` (novo): sintetiza os 11 inputs do contrato numa recomendacao via IA, mesmo caminho de producao dos 5 agentes de `agent/multiagente/` (`chamar_ia_com_fallback_claude`). Resposta da IA validada contra o contrato de saida ja existente (`montar_saida_raciocinio()`) — dado de dominio, propaga ValueError em resposta malformada.
- [x] `agent/prompt_templates/sales_reasoning_engine.txt` (novo) + `SALES_REASONING_FRAMEWORKS` (vocabulario fechado de 9 frameworks: 4 estagios SPIN + MEDDPICC_QUALIFICATION/OBJECTION_INVESTIGATION/NEGOTIATION/RISK_MITIGATION/CLOSING). Regra herdada da Fase 6.1: objecao com `precisa_investigar=true` bloqueia NEGOTIATION/CLOSING ate OBJECTION_INVESTIGATION acontecer primeiro.
- [x] `api/ai_features.py::SALES_REASONING_RACIOCINIO` (nova feature de custo).
- [x] Decisao deliberada: **nao integrado a `orquestrador.py`/`processador_tempo_real.py` ainda** — decisao de produto separada.
- [x] 7 testes novos (`RaciocinarAsyncTest`, mock de `chamar_ia_com_fallback_claude`). Suite completa: 700 testes, 0 falhas, 1 skip pre-existente — sem regressao.
- [x] Golden Dataset — 57 cenarios (minimo pedido: 50) em `evals/datasets/sales_reasoning/` (8 arquivos por categoria) + `evals/providers/sales_reasoning_provider.py` + `evals/promptfooconfig.sales_reasoning.yaml`, mesmo harness Promptfoo do Coach/Finance. Validacao sempre via `llm-rubric` (semantica, nunca igualdade literal de frase — regra explicita do prompt mestre pra este dataset). Inclui o exemplo PROIBIDO literal ("Esta caro." -> "Posso dar 20% agora."). **Nunca executado nesta rodada** (custa dinheiro real por cenario, mesma disciplina do resto da suite).
- [x] Versao: `1.4.84` -> `1.4.85`.
- [x] Push para o GitHub (commit `96bd3ea`).
- [x] **Deploy confirmado na VPS (14/09/2026)**: `reunioes_ativas: 0` checado antes de cada etapa arriscada — `git pull` (fast-forward `451beae` -> `96bd3ea`, aditivo, sem tabela/coluna nova) + `pip install`/`pip check` limpos. `systemctl restart saleia` — `active`, journal sem erros. Pos-restart: `/health` = `versao 1.4.85`, `status online`, `reunioes_ativas 0`, 4 provedores de IA `ok` (restart zerou os circuit breakers em memoria, mesma ressalva de sempre — nao confirma saldo/chave de verdade).
- **Pendente**: rodar o Golden Dataset de verdade (`npm run eval:sales_reasoning`). **Integrar `raciocinar_async()` ao orquestrador nao comeca sem nova confirmacao explicita do usuario.**

## Concluido (V.1.4.86 — Outcome Tracking, Tarefa 8.1, inicio da Fase 8 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para a Fase 8 (Resultado da Venda). Escopo desta rodada: so a Tarefa 8.1 (Outcome Tracking) — Tarefa 8.2 (Win/Loss Intelligence) nao comecou.

- [x] `agent/opportunity_memory_rules.py::OPPORTUNITY_STATUSES` ganha `"abandoned"` (4o estado, junto de open/won/lost da Fase 2).
- [x] `agent/outcome_rules.py` (novo, funcao pura, sem IA/banco): `calcular_cycle_days()` (sempre derivado das datas reais, nunca aceito como input do chamador), `validar_dados_won({value, product, close_date})`, `validar_dados_lost({reason, competitor})` (competitor opcional — nem toda perda vai pra um concorrente identificado), `esta_fechada(status)` (True pra won/lost/abandoned), `resumo_por_status(opportunities)` — atende a regra de teste literal da Tarefa 8.1: "uma oportunidade encerrada precisa deixar de entrar como aberta em estatisticas".
- [x] `api/database.py::Opportunity` ganha 5 colunas aditivas: `outcome_value`/`product`/`close_date`/`cycle_days` (WON) e `competitor` (LOST). `reason`/`stage`/`lost_at` do schema do prompt mestre reaproveitam `loss_reason`/`stage`/`lost_at` ja existentes desde a Fase 2 — nunca duplicados.
- [x] `atualizar_status_opportunity()`: transicao pra "won" agora exige `value`/`product`/`close_date` (validados, `cycle_days` sempre calculado, nunca aceito do chamador); "lost" exige `loss_reason` (competitor opcional); "abandoned" nao exige dado extra.
- [x] Achado: 2 testes pre-existentes da Fase 2 (`test_atualizar_status_won_grava_won_at_uma_vez`, `test_listar_opportunities_filtra_por_client_e_status`) chamavam a transicao pra "won" sem esses dados — corrigidos pra passar value/product/close_date, sem mudar o que cada teste verifica.
- [x] 19 testes novos (`tests/test_outcome_rules.py`) + 6 testes novos em `tests/test_opportunity_memory.py`, incluindo o teste literal da Tarefa 8.1. Suite completa: 725 testes (700 + 25), 0 falhas, 1 skip pre-existente — sem regressao.
- [x] Decisao deliberada: sem endpoint HTTP novo, sem integracao com `orquestrador.py`/`processador_tempo_real.py` — mesma disciplina das Fases 1-7.
- [x] Versao: `1.4.85` -> `1.4.86`.
- [x] Push para o GitHub (commit `12aa93a`).
- [x] **Deploy confirmado na VPS (14/09/2026)**: `reunioes_ativas: 0` checado antes de cada etapa — `git pull` (fast-forward `96bd3ea` -> `12aa93a`) + `pip install`/`pip check` limpos. `ALTER TABLE opportunities ADD COLUMN` aplicado via script idempotente (checou `INFORMATION_SCHEMA.COLUMNS` antes — as 5 colunas nao existiam, todas adicionadas nullable: outcome_value/product/close_date/cycle_days/competitor). `systemctl restart saleia` — `active`, journal sem erros. Pos-restart: `/health` = `versao 1.4.86`, `status online`, `reunioes_ativas 0`.
- **Pendente**: nada — Tarefa 8.2 (abaixo) fecha a Fase 8.

## Concluido (V.1.4.87 — Win/Loss Intelligence, Tarefa 8.2, fecha a Fase 8 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para a Tarefa 8.2, fechando a Fase 8 (Resultado da Venda) completa.

- [x] `agent/win_loss_rules.py` (novo, funcao pura, zero IA/banco e zero numpy/scipy — estatistica em Python puro): `WIN_LOSS_VARIAVEIS` documenta as 15 variaveis literais do prompt mestre (segment/seller/origin/ticket/cycle/pain/objection/decision_maker/champion/strategy/spin_coverage/meddpicc_coverage/talk_ratio/next_step/season) — funcoes genericas sobre qualquer campo do dict, nao travadas a esses nomes.
- [x] Regra cientifica central "nunca causa, sempre associacao" garantida por construcao: so 3 templates fixos geram texto (`TEMPLATE_AFIRMACAO_ASSOCIACAO`/`TEMPLATE_AMOSTRA_INSUFICIENTE`/`TEMPLATE_SIMPSONS_PARADOX`), nunca f-strings ad hoc — guardados por `GuardaContraCausalidadeTest`.
- [x] `comparar_por_variavel_categorica()` — taxa de conversao + IC de Wilson + afirmacao por grupo categorico; oportunidade sem valor no campo vai pra `sem_dado`, nunca vira grupo "None" nem e descartada silenciosamente ("ausencia de dados").
- [x] `amostra_suficiente(n, minimo=30)` ("amostra insuficiente"), `intervalo_confianca_wilson()` (Wilson score interval implementado do zero, sem scipy — "intervalos de confianca quando aplicavel"), `calcular_limites_iqr`/`detectar_outliers_iqr`/`resumir_variavel_numerica` (metodo IQR classico pra ticket/cycle/talk_ratio — "outliers").
- [x] `detectar_simpsons_paradox(opportunities, campo, campo_segmento)` — compara exatamente 2 valores de campo, detecta reversao de tendencia ao segmentar. Testado com dataset sintetico classico (mesma estrutura do estudo de tratamento de calculo renal, adaptado: 2 estrategias de venda x porte do negocio — A vence em cada segmento 93%/87% e 73%/69%, mas B vence agregado 78%/83%) — atende literalmente "Simpson's paradox em dataset sintetico".
- [x] Decisao deliberada: sem integracao com `Opportunity`/`orquestrador.py`, sem endpoint HTTP — motor estatistico generico, nao a extracao de cada uma das 15 variaveis reais.
- [x] 24 testes novos (`tests/test_win_loss_rules.py`), incluindo os 6 testes estatisticos pedidos literalmente pela Tarefa 8.2 (amostra insuficiente, outliers, divisao por segmento, ausencia de dados, Simpson's paradox, intervalos de confianca). Suite completa: 749 testes (725 + 24), 0 falhas, 1 skip pre-existente — sem regressao.
- [x] Versao: `1.4.86` -> `1.4.87`.
- [x] **Push + deploy confirmados (14/09/2026)** junto com V.1.4.88/89/90 — ver detalhe no bloco V.1.4.90 abaixo.

## Concluido (V.1.4.88 — Data Warehouse comercial minimo, Tarefa 9.1, inicio da Fase 9 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para a Fase 9 (Seasonality Engine). Escopo desta rodada: so a Tarefa 9.1 (Data Warehouse comercial minimo) — Tarefas 9.2 (Sazonalidade temporal) e 9.3 (Sazonalidade contextual) nao comecaram.

- [x] `agent/data_warehouse_rules.py` (novo, funcao pura, sem IA/banco, mesmo padrao de `win_loss_rules.py`/`outcome_rules.py`): `DIMENSOES_DATASET` documenta as 16 dimensoes literais do prompt mestre (calendario: date/month/quarter/week/weekday/hour; negocio: seller/team/segment/product/lead_source/opportunity_stage/ticket/objection_type/sales_strategy/won/lost/cycle_days).
- [x] `derivar_dimensoes_calendario(data)` — as 6 dimensoes de calendario sempre calculadas a partir de uma datetime real, nunca aceitas como input separado.
- [x] `construir_linha_analitica(opportunity, campo_data="close_date", **dimensoes_extra)` — 1 linha do dataset a partir do formato de `listar_opportunities()`; cai pra `created_at` quando sem `close_date`; `ticket` usa `outcome_value` (Fase 8) senao `estimated_value`; `won`/`lost` viram flags booleanos independentes (schema literal pede 2 colunas). Dimensoes ainda nao rastreadas (team/lead_source/objection_type/sales_strategy) via `**dimensoes_extra`.
- [x] `construir_dataset_analitico(opportunities, **kwargs)` — oportunidade sem data valida e pulada, nunca derruba o dataset inteiro.
- [x] `pode_executar_analise_pesada(reunioes_ativas)` — implementa "nunca executar analises pesadas em horario de reuniao" reaproveitando o mesmo sinal `reunioes_ativas` que ja governa todo deploy seguro do projeto.
- [x] Decisao deliberada: sem endpoint HTTP, sem integracao com `orquestrador.py`/scheduler.
- [x] 19 testes novos (`tests/test_data_warehouse_rules.py`), incluindo verificacao de que as 16 dimensoes literais do prompt mestre estao todas presentes em cada linha gerada. Suite completa: 768 testes (749 + 19), 0 falhas, 1 skip pre-existente — sem regressao.
- [x] Versao: `1.4.87` -> `1.4.88`.
- [x] **Push + deploy confirmados (14/09/2026)** junto com V.1.4.87/89/90 — ver detalhe no bloco V.1.4.90 abaixo.

## Concluido (V.1.4.89 — Sazonalidade Temporal, Tarefa 9.2 da Fase 9 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para a Tarefa 9.2. Constroi sobre o dataset analitico da Tarefa 9.1 e reaproveita as primitivas estatisticas de `win_loss_rules.py` (Fase 8). Tarefa 9.3 (Sazonalidade contextual) nao comecou.

- [x] `agent/seasonality_rules.py` (novo, funcao pura, zero IA/banco/numpy/scipy, mesmo padrao de `win_loss_rules.py`): `DIMENSOES_TEMPORAIS` documenta as 5 dimensoes literais da Tarefa 9.2 (month/quarter/week/weekday/hour) — `date` (6a dimensao de calendario da Tarefa 9.1) fica de fora de proposito, granularidade unica por linha.
- [x] Criterio de significancia sem scipy: amostra suficiente (reusa `amostra_suficiente`) + baseline geral fora do intervalo de confianca de Wilson do periodo (reusa `intervalo_confianca_wilson`) — nao e teste de hipotese formal, mas forma honesta e auto-calibrada de nao inventar sazonalidade.
- [x] `taxa_conversao_por_periodo()`/`detectar_sazonalidade()` — agrupam linhas do dataset analitico (Tarefa 9.1) pela dimensao temporal; linha sem won/lost nao entra.
- [x] Regra cientifica herdada da Tarefa 8.2 "nunca causa, sempre associacao" — unica string livre vem de `TEMPLATE_SAZONALIDADE`, guardado por `GuardaContraCausalidadeTest`.
- [x] Testado com o exemplo literal do prompt mestre (segmento X, marco-maio, conversion +18%, adaptado sem o recorte de segmento — isso e a Tarefa 9.3): dataset sintetico com meses 3-5 a 68% vs 50% no resto do ano — os 3 meses marcados significativo=True, os outros 9 nao.
- [x] "O motor NAO devera inventar sazonalidade significativa" — 2 testes: dataset com taxa identica em todo periodo (determinstico, sem depender de seed) + dataset aleatorio com seed fixa (random.Random(42), taxa constante 50%, n=200/mes) tolerando no maximo 1 falso-positivo em 12 meses (taxa esperada de IC 95%, documentada no teste).
- [x] Decisao deliberada: sem integracao com `orquestrador.py`, sem endpoint HTTP. Segmento/produto/origem fica pra Tarefa 9.3.
- [x] 12 testes novos (`tests/test_seasonality_rules.py`). Suite completa: 780 testes (768 + 12), 0 falhas, 1 skip pre-existente — sem regressao.
- [x] Versao: `1.4.88` -> `1.4.89`.
- [x] **Push + deploy confirmados (14/09/2026)** junto com V.1.4.87/88/90 — ver detalhe no bloco V.1.4.90 abaixo.

## Concluido (V.1.4.90 — Sazonalidade Contextual, Tarefa 9.3, fecha a Fase 9 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para a Tarefa 9.3, fechando a Fase 9 (Seasonality Engine) completa. Estende a Tarefa 9.2 combinando periodo temporal com dimensao de contexto de negocio.

- [x] `agent/contextual_seasonality_rules.py` (novo, funcao pura, zero IA/banco/numpy/scipy — arquivo proprio mesmo construindo sobre a Tarefa 9.2, mesmo padrao de cada tarefa ganhar seu modulo ja usado em `deal_risk_rules.py` sobre `meddpicc_rules.py` na Fase 4): `DIMENSOES_CONTEXTO` documenta os 7 campos literais do prompt mestre (segment/product/origin/ticket/client_type/objection_type/opportunity_stage) — reaproveita nomes de `data_warehouse_rules.DIMENSOES_DATASET` (Tarefa 9.1) onde ja existem; `client_type` e o unico ainda nao rastreado.
- [x] `detectar_sazonalidade_contextual(linhas_analiticas, dimensao_temporal, dimensao_contexto, ...)` — agrupa por (periodo, contexto) e compara contra o mesmo baseline geral (global) da Tarefa 9.2 (decisao desta rodada, nao o baseline do contexto isolado). Reaproveita `win_loss_rules.amostra_suficiente`/`intervalo_confianca_wilson` (Fase 8).
- [x] Schema de saida literal do prompt mestre: cada descoberta usa exatamente os 6 campos pedidos (sample_size/baseline/observed/difference/confidence/period) — contrato explicito. Retorna lista ja ordenada por magnitude da diferenca.
- [x] Decisao deliberada de escopo: o exemplo do prompt mestre ("Q4, segmento SaaS, objecao dominante = orcamento") mistura divergencia de taxa (implementada) com "categoria dominante por frequencia" (mode-finder, fora do Criterio de 6 campos, todo numerico) — so a divergencia de taxa foi construida.
- [x] Regra cientifica herdada da Tarefa 8.2 — nunca causa, sempre associacao — guardada por `GuardaContraCausalidadeTest`.
- [x] 12 testes novos (`tests/test_contextual_seasonality_rules.py`), incluindo o exemplo adaptado do prompt mestre (Q4 x SaaS com +30pp detectado, outras 7 combinacoes nao), verificacao dos 6 campos literais, ordenacao por magnitude, e 2 datasets sem sinal real (taxa identica; aleatorio com seed fixa random.Random(7), tolerando no maximo 2 falsos-positivos em 12 combinacoes). Suite completa: 792 testes (780 + 12), 0 falhas, 1 skip pre-existente — sem regressao.
- [x] Decisao deliberada: sem integracao com `orquestrador.py`, sem endpoint HTTP.
- [x] Versao: `1.4.89` -> `1.4.90`.
- [x] Push para o GitHub (commit `8c8490e`, 4 commits juntos: V.1.4.87 -> V.1.4.90).
- [x] **Deploy confirmado na VPS (14/09/2026)**: `reunioes_ativas: 1` (reuniao real em andamento) bloqueou o restart por um tempo curto — `git pull`/`pip install`/`pip check` feitos antes com seguranca (so arquivos em disco, aditivo, sem tabela/coluna nova em nenhuma das 4 versoes); `systemctl restart saleia` executado assim que `reunioes_ativas` voltou a `0`. Pos-restart: `/health` = `versao 1.4.90`, `status online`, journal sem erros.
- **Pendente**: nada — Tarefa 10.1 (abaixo) e a proxima.

## Concluido (V.1.4.91 — RecommendationEvent, Tarefa 10.1, inicio da Fase 10 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para a Fase 10 (Strategy Effectiveness). Escopo desta rodada: so a Tarefa 10.1 (criar o RecommendationEvent) — Tarefas 10.2 (detectar se o vendedor usou, estados USED/PARTIALLY_USED/IGNORED/UNKNOWN) e 10.3 (Recommendation Effectiveness) nao comecaram.

- [x] `api/database.py::RecommendationEvent` (tabela `recommendation_events`, aditiva): schema literal do prompt mestre — meeting_id, opportunity_id (sem FK, mesmo padrao de SalesEvent Fase 1), strategy, recommendation, reason, shown_at, used_at, seller_action, outcome_window.
- [x] `agent/recommendation_rules.py` (novo, funcao pura, sem IA/banco, mesmo padrao de `sales_event_rules.py`/`sales_evidence_rules.py`): `validar_recommendation_event()` exige meeting_id/strategy/recommendation/reason nao vazios.
- [x] RecommendationEvent e dado de dominio, nao telemetria — `criar_recommendation_event()` propaga ValueError em dado invalido, mesma disciplina de SalesEvent/SalesEvidence.
- [x] `registrar_uso_recommendation_event(id, seller_action, used_at=None)` — persistencia mecanica de seller_action/used_at, nao decide USED/PARTIALLY_USED/IGNORED (Tarefa 10.2); nunca sobrescreve used_at ja gravado, mesmo padrao de won_at/lost_at (Fase 2/8).
- [x] Decisao deliberada: sem vocabulario fechado pra strategy (prompt mestre nao define taxonomia aqui), sem endpoint HTTP (mesma decisao das Tarefas 1.1/1.2/2.1).
- [x] 12 testes novos (`tests/test_recommendation_event.py`), incluindo a regra "nunca sobrescreve used_at" e validacao de cada campo obrigatorio. Suite completa: 804 testes (792 + 12), 0 falhas, 1 skip pre-existente — sem regressao.
- [x] Versao: `1.4.90` -> `1.4.91`.
- **Pendente**: push + deploy na VPS (aditivo — 1 tabela nova via `create_all()`; segue junto do V.1.4.92 abaixo).

## Concluido (V.1.4.92 — Detectar Uso da Recomendacao, Tarefa 10.2 da Fase 10 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para a Tarefa 10.2 e escolheu embeddings (nao IA nem so contrato) pra deteccao — regra central "nao exigir correspondencia literal": "Pergunte sobre impacto financeiro." precisa ser reconhecida como usada quando o vendedor pergunta "Quanto vocês estimam que isso custa todo mês?", sem nenhuma palavra em comum.

- [x] `agent/recommendation_usage_rules.py` (novo, arquivo proprio mesmo construindo sobre a Tarefa 10.1, mesmo padrao de `deal_risk_rules.py` sobre `meddpicc_rules.py` na Fase 4): `RECOMMENDATION_USAGE_STATES` (USED/PARTIALLY_USED/IGNORED/UNKNOWN, os 4 estados literais do prompt mestre).
- [x] `cosine_similarity(vetor_a, vetor_b)` — helper de par unico (cosine_top_k existente compara 1 vetor contra uma matriz, nao serve direto).
- [x] `classificar_uso_por_similaridade(similaridade, seller_action, limiar_used=0.55, limiar_partially_used=0.35)` — funcao pura, nunca gera embedding sozinha; limiares sao decisao desta rodada. UNKNOWN quando sem seller_action OU quando similaridade e None (embedding falhou) — nunca IGNORED.
- [x] `detectar_uso_recomendacao(recommendation, seller_action, ...)` (motor real, async) — gera os 2 embeddings via `services.embeddings.get_embedding_provider()` (Ollama local por padrao, mesmo provedor do RAG) e classifica por similaridade de cosseno.
- [x] Estado nunca e coluna nova em `RecommendationEvent` — decisao desta rodada: sempre derivado de recommendation/seller_action ja persistidos, calculado sob demanda (mesmo principio de calcular_cycle_days, Fase 8).
- [x] Sem wrapper async novo em `api/database.py` (inteiramente sincrono hoje) — compor busca (sincrona) + classificacao (async) fica a cargo do chamador.
- [x] Testado com o exemplo literal do prompt mestre: embeddings mockados (mesmo padrao de test_embeddings.py, que mocka a camada HTTP em vez de Ollama real) simulando vetores semanticamente proximos — classificado corretamente como USED.
- [x] 15 testes novos (`tests/test_recommendation_usage_rules.py`), incluindo falha de embedding virando UNKNOWN nunca IGNORED. Suite completa: 819 testes (804 + 15), 0 falhas, 1 skip pre-existente — sem regressao.
- [x] Decisao deliberada: sem integracao com `orquestrador.py`/`processador_tempo_real.py`, sem endpoint HTTP.
- [x] Versao: `1.4.91` -> `1.4.92`.
- [x] Push + deploy confirmados (15/09/2026): commit `6d5c9ce` no GitHub (junto com V.1.4.91, `672644a`). `reunioes_ativas: 0` checado antes de cada etapa na VPS — `git pull` (fast-forward `06e4fc3` -> `6d5c9ce`) + `pip install`/`pip check` limpos. `systemctl restart saleia` — `active`, journal sem erros. Pos-restart: `/health` = `versao 1.4.92`, `status online`, `reunioes_ativas 0`, 4 provedores `ok`; `/dashboard` = `200`.

## Concluido (V.1.4.93 — Recommendation Effectiveness, Tarefa 10.3, fecha a Fase 10 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para a Tarefa 10.3, fechando a Fase 10 (Strategy Effectiveness) completa. Achado: o modulo e os testes ja existiam no working tree local, nao commitados, de uma sessao anterior — revisados por completo (imports conferidos contra `recommendation_usage_rules.py`/`win_loss_rules.py`, suite completa rodada do zero) antes de aceitar o codigo; nenhuma linha nova escrita alem do bump de versao e da documentacao.

- [x] `agent/recommendation_effectiveness_rules.py` (novo, funcao pura, sem IA/banco, mesmo padrao de `deal_risk_rules.py` sobre `meddpicc_rules.py`, Fase 4): `calcular_efetividade_por_estrategia(eventos, minimo_amostra=AMOSTRA_MINIMA_PADRAO)` agrupa eventos por `strategy` e mede efetividade a partir de sinais ja classificados (`state` da Tarefa 10.2, `stage_advanced`, `opportunity_result`) — nao extrai nada de transcricao real.
- [x] Regra central "Importante" do prompt mestre, imposta estruturalmente: nunca confundir avanco imediato (`taxa_avanco`) com causa da venda (`taxa_desfecho_positivo`) — sempre dois numeros separados, nunca combinados numa metrica ou afirmacao causal unica. Mesma disciplina "nunca causa, sempre associacao" de `win_loss_rules.py` (Fase 8)/`seasonality_rules.py` (Fase 9), guardada por `GuardaContraConfusaoCausalTest`.
- [x] Dado ausente (`stage_advanced`/`opportunity_result` = `None`) nunca conta no denominador — evento excluido da conta, nunca vira "nao avancou"/"nao converteu" por omissao. `ESTADOS_CONTADOS_COMO_USO = {USED, PARTIALLY_USED}` (decisao desta rodada). Reaproveita `win_loss_rules.amostra_suficiente`/`AMOSTRA_MINIMA_PADRAO` (Fase 8) para `amostra_avanco_suficiente`/`amostra_desfecho_suficiente`.
- [x] Testado com o exemplo literal do prompt mestre: "SPIN Implication — 187 usos — 61% avanco", "Case Similar — 153 usos — 66% avanco".
- [x] 10 testes novos (`tests/test_recommendation_effectiveness_rules.py`). Suite completa: 829 testes (819 da Tarefa 10.2 + 10 novos), 0 falhas, 1 skip pre-existente — sem regressao.
- [x] Decisao deliberada: sem integracao com `orquestrador.py`/`processador_tempo_real.py`, sem endpoint HTTP, sem persistencia nova — mesma disciplina das Fases 1-10.
- [x] **Fecha a Fase 10 (Strategy Effectiveness)** completa: Tarefa 10.1 (RecommendationEvent) -> 10.2 (Detectar Uso) -> 10.3 (Effectiveness).
- [x] Versao: `1.4.92` -> `1.4.93`.
- [x] Push + deploy confirmados (15/09/2026): commit `36c7585` no GitHub. `reunioes_ativas: 0` checado antes/depois na VPS — `git pull` (fast-forward `6d5c9ce` -> `36c7585`) + `systemctl restart saleia` — `active`, journal sem erros. Pos-restart: `/health` = `versao 1.4.93`, `status online`, `reunioes_ativas 0`.

## Concluido (V.1.4.94 — Conversation Metrics, Tarefa 11.1, inicio da Fase 11 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para a Fase 11 (Seller Coaching) — nova fase do roadmap, confirmacao explicita pedida separadamente da confirmacao de tarefa dentro de uma fase ja em andamento (mesma disciplina desde a Fase 0).

- [x] `agent/conversation_metrics_rules.py` (novo, funcao pura, sem IA/banco, mesmo padrao de `deal_risk_rules.py`/`win_loss_rules.py`): `calcular_metricas_conversa(turns, objections=None, next_step_proposto=None, palavras_abertura=PALAVRAS_ABERTURA_PADRAO, limiar_monologo_segundos=90.0)` calcula as 11 metricas literais da Tarefa 11.1 a partir de uma transcricao temporizada estruturada (`speaker`/`start`/`end`/`text` por turno).
- [x] Separacao estrutural x classificacao de negocio (mesma disciplina das Fases 4-10): `seller_talk_ratio`/`customer_talk_ratio`/`interruptions`/`monologues` e contagem de perguntas (aberta/fechada) vem de sinais estruturais do proprio turno (timing + deteccao de "?" + heuristica de palavra de abertura); `price_timing`/`presentation_timing`/`objection_exploration_rate`/`next_step_rate` sempre recebem o sinal ja classificado do chamador (flags por turno / lista de objecoes / booleano) — nunca inferidos por keyword matching de negocio dentro do modulo, mesmo principio de `deal_risk_rules.calcular_riscos()` (Fase 4.2).
- [x] Falante nao identificado ("incerto") nunca conta nos ratios/interrupcoes; dado ausente nunca vira 0/False por omissao (mesma disciplina de `recommendation_effectiveness_rules.py`, Fase 10). Perguntas contadas so do vendedor (decisao desta rodada — feature de Seller Coaching). Turnos consecutivos do mesmo falante sao mesclados antes de checar o limiar de monologo. Funcao ordena os turnos internamente por `start`.
- [x] Testado com uma transcricao temporizada conhecida (11 turnos, 302s totais) com valores esperados calculados a mao — literal da instrucao da Tarefa 11.1 ("Criar transcricoes temporizadas conhecidas. Comparar calculo esperado com calculo real."). Inclui teste de robustez a ordem (transcricao embaralhada produz o mesmo resultado).
- [x] 22 testes novos (`tests/test_conversation_metrics_rules.py`). Suite completa: 851 testes (829 da Tarefa 10.3 + 22 novos), 0 falhas, 1 skip pre-existente — sem regressao.
- [x] Decisao deliberada: sem integracao com `orquestrador.py`/`processador_tempo_real.py`, sem endpoint HTTP, sem persistencia nova — mesma disciplina das Fases 1-10. Extracao automatica de speaker/start/end/flags de negocio a partir de uma reuniao real (diarizacao, deteccao de preco/apresentacao) e integracao futura nao pedida por esta tarefa.
- [x] Versao: `1.4.93` -> `1.4.94`.
- [x] Push + deploy confirmados (15/09/2026): commit `33dd12a` no GitHub. `reunioes_ativas: 0` checado antes/depois na VPS — `git pull` (fast-forward `36c7585` -> `33dd12a`) + `systemctl restart saleia` — `active`, journal sem erros. Pos-restart: `/health` = `versao 1.4.94`, `status online`, `reunioes_ativas 0`.

## Concluido (V.1.4.95 — Seller Scorecard, Tarefa 11.2, fecha a Fase 11 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para a Tarefa 11.2, fechando a Fase 11 (Seller Coaching) completa.

- [x] `agent/seller_scorecard_rules.py` (novo, funcao pura, sem IA/banco, mesmo padrao de `conversation_metrics_rules.py`/`deal_risk_rules.py`): `SCORECARD_DIMENSOES` — as 7 dimensoes literais do prompt mestre (Discovery, Listening, Qualification, Value Building, Negotiation, Closing, Next Step Discipline). `calcular_scorecard(evidencias_por_dimensao)` generica sobre evidencias ja classificadas pelo chamador (de `conversation_metrics_rules.py`/Tarefa 11.1, `spin_coverage_rules.py`/Fase 3, `meddpicc_rules.py`/Fase 4, `objection_rules.py`/`negotiation_rules.py`/Fase 6, etc.) — nunca decide sozinha o que conta como evidencia de cada dimensao.
- [x] Regra literal "Nao criar score arbitrario", imposta estruturalmente: cada dimensao e uma fracao transparente `criterios_atendidos / total_criterios` sobre a lista de evidencias recebida — nunca peso/formula inventada, e nunca combinada com as outras 6 dimensoes numa nota geral unica (essa combinacao nem existe na API do modulo — nenhuma chave `score_geral`/`overall_score` e produzida, guardado por `GuardaContraScoreArbitrarioTest`).
- [x] "Cada score precisa apontar evidencias": o resultado de cada dimensao sempre inclui a lista de evidencias que o compoe (nunca so o numero) — cada evidencia e `{"criterio", "atendido", "quote"}`; `criterio` obrigatorio e nao-vazio, `quote` opcional (nem toda evidencia vem de uma fala literal — ex.: `customer_talk_ratio` da Tarefa 11.1 e sinal estrutural, nao citacao).
- [x] Dimensao sem nenhuma evidencia recebida nunca vira `0` por omissao — vem como `score: None` (mesmo principio de `conversation_metrics_rules.py`/`recommendation_effectiveness_rules.py`, Fases 10-11). `dimensoes_sem_evidencia(scorecard)` helper para o Dashboard sinalizar "dado insuficiente" em vez de esconder a dimensao.
- [x] Vocabulario de dimensao fechado: chave fora das 7 literais levanta `ValueError`. As 7 dimensoes sempre aparecem no retorno, mesmo sem nenhuma evidencia recebida ainda.
- [x] 15 testes novos (`tests/test_seller_scorecard_rules.py`), incluindo a guarda contra score arbitrario (nenhuma chave de score combinado produzida; score sempre recomputavel a partir das proprias evidencias). Suite completa: 866 testes (851 da Tarefa 11.1 + 15 novos), 0 falhas, 1 skip pre-existente — sem regressao.
- [x] Decisao deliberada: sem integracao com `orquestrador.py`/`processador_tempo_real.py`, sem endpoint HTTP, sem persistencia nova — mesma disciplina das Fases 1-11. Mapear cada dimensao para os sinais reais das Fases 3/4/6/11 (ex.: `Qualification` a partir do `meddpicc_state`) e integracao futura nao pedida por esta tarefa.
- [x] **Fecha a Fase 11 (Seller Coaching)** completa: Tarefa 11.1 (Conversation Metrics) -> 11.2 (Seller Scorecard).
- [x] Versao: `1.4.94` -> `1.4.95`.
- [x] Push + deploy confirmados (15/09/2026): commit `3ffce0c` no GitHub. `reunioes_ativas: 0` checado antes/depois na VPS — `git pull` (fast-forward `33dd12a` -> `3ffce0c`) + `systemctl restart saleia` — `active`, journal sem erros. Pos-restart: `/health` = `versao 1.4.95`, `status online`, `reunioes_ativas 0`.

## Concluido (V.1.4.96 — Benchmark dos Melhores Vendedores, Tarefa 12.1, inicio da Fase 12 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para a Fase 12 (Collective Sales Intelligence) — nova fase do roadmap. So a Tarefa 12.1 executada — Tarefa 12.2 (Descoberta de padroes) nao comecou.

- [x] `agent/seller_benchmark_rules.py` (novo, funcao pura, sem IA/banco): `PERFORMANCE_TIERS = ("top", "median", "low")` e `CONTROL_VARIABLES = ("segment", "lead_source", "ticket", "product")` — as 4 variaveis de controle literais do prompt mestre. `comparar_tiers(opportunities)` reaproveita `win_loss_rules.comparar_por_variavel_categorica()` direto sobre `seller_tier` (taxa de conversao bruta por tier).
- [x] Regra central "nao concluir que um vendedor e melhor so porque recebe leads melhores", imposta reaproveitando o paradoxo de Simpson ja construido na Fase 8 (nenhum calculo novo e paralelo): `benchmark_controlado(opportunities, tier_a="top", tier_b="low", campos_controle=CONTROL_VARIABLES)` chama `win_loss_rules.detectar_simpsons_paradox()` uma vez por variavel de controle — a vantagem bruta entre os 2 tiers so e confiavel quando se mantem dentro de cada estrato; quando a direcao se inverte em todos os estratos de uma variavel, o resultado vem sinalizado como possivel confundimento (mesmo template/mecanismo da Fase 8, nunca declara causalidade).
- [x] Testado com o dataset sintetico classico ja usado em `test_win_loss_rules.py` (Fase 8, analogo ao estudo de tratamento de calculo renal), adaptado a `seller_tier`/`segment`: `top` parece pior no agregado (78,0% vs 82,6% do `low`), mas e melhor dentro de cada segmento (93,1%>86,7%; 73,0%>68,75%) — exatamente o cenario que a Tarefa 12.1 pede para nunca virar "low e melhor vendedor" sem controlar por segmento. Tambem testado o caso inverso (vantagem real, sem confundimento — nao deve ser sinalizado como paradoxo).
- [x] Quem monta as linhas de entrada: cada linha e uma oportunidade no formato ja aceito por `win_loss_rules.py` (`status`) + `seller_tier` (ja classificado pelo chamador a partir de alguma metrica de desempenho real — este modulo nunca decide sozinho quem e top/median/low) + um campo por variavel de controle ja categorizada (`ticket` precisa vir pre-bucketizado em faixas pelo chamador) — mesmo principio de "quem extrai/classifica o sinal real e integracao futura" de `deal_risk_rules.py`/Fase 4.2 e `conversation_metrics_rules.py`/Fase 11.1.
- [x] 9 testes novos (`tests/test_seller_benchmark_rules.py`). Suite completa: 875 testes (866 da Tarefa 11.2 + 9 novos), 0 falhas, 1 skip pre-existente — sem regressao.
- [x] Decisao deliberada: sem integracao com `orquestrador.py`/`processador_tempo_real.py`, sem endpoint HTTP, sem persistencia nova — mesma disciplina das Fases 1-11.
- [x] Versao: `1.4.95` -> `1.4.96`.
- [x] Push + deploy confirmados (15/09/2026): commit `329a47d` no GitHub. `reunioes_ativas: 0` checado antes/depois na VPS — `git pull` (fast-forward `3ffce0c` -> `329a47d`) + `systemctl restart saleia` — `active`, journal sem erros. Pos-restart: `/health` = `versao 1.4.96`, `status online`, `reunioes_ativas 0`.

## Concluido (V.1.4.97 — Descoberta de Padroes, Tarefa 12.2, fecha a Fase 12 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para a Tarefa 12.2, fechando a Fase 12 (Collective Sales Intelligence) completa.

- [x] `agent/pattern_discovery_rules.py` (novo, funcao pura, sem IA/banco): `descobrir_padrao(observacoes, hipotese, minimo_amostra=AMOSTRA_MINIMA_PADRAO, confianca=0.95)` testa uma hipotese de comportamento (ex.: "vendedores de alta conversao exploram implicacao antes de apresentar solucao") comparando a taxa do comportamento entre um `top group` e um `control group`.
- [x] Reuso, nao reinvencao: reaproveita `win_loss_rules.comparar_por_variavel_categorica()` (Fase 8) direto — o "desfecho" vira o comportamento observado (`exhibited`) em vez de won/lost, e a "categoria" vira o grupo (`top`/`control`) em vez de segmento/estrategia. Mesma funcao, sem alteracao, mesmo principio de `seller_benchmark_rules.py` (Tarefa 12.1).
- [x] Retorno literal do prompt mestre: `sample`, `top_group`, `control_group`, `difference`, `confidence` — mais `diferenca_significativa`/`afirmacao` (campos adicionais para o Dashboard distinguir sinal real de ruido sem reimplementar a logica).
- [x] Significancia sem scipy — mesma disciplina honesta e auto-calibrada de `seasonality_rules.py` (Fase 9): `diferenca_significativa` so e `True` quando os 2 grupos tem amostra suficiente e os intervalos de confianca de Wilson dos 2 grupos nao se sobrepoem.
- [x] Regra cientifica herdada das Fases 8-9 — nunca causa, sempre associacao: unica string de texto livre vem de `TEMPLATE_PADRAO_DESCOBERTO`/`TEMPLATE_PADRAO_SEM_SINAL` (templates fixos), guardado por `GuardaContraCausalidadeTest`.
- [x] Quem monta as observacoes e o que e "exhibited": cada observacao e `{"group": "top"|"control", "exhibited": bool}` — `group` ja classificado pelo chamador (quem e "alta conversao" e definicao de negocio, nao decidida aqui — mesmo padrao de `seller_tier` da Tarefa 12.1), `exhibited` ja classificado pelo chamador (este modulo nunca extrai comportamento de transcricao livre). `hipotese` (texto) e so uma etiqueta de rastreabilidade no resultado, nunca interpretada pelo modulo.
- [x] Testado com o exemplo literal do prompt mestre (top 40/50=80%, control 15/50=30%, ICs de Wilson nao sobrepostos -> diferenca significativa) e o caso negativo (taxas parecidas -> sem sinal) e o caso de amostra insuficiente (diferenca grande mas n<30 -> nao significativa, mesmo com diferenca calculada e reportada).
- [x] 9 testes novos (`tests/test_pattern_discovery_rules.py`). Suite completa: 884 testes (875 da Tarefa 12.1 + 9 novos), 0 falhas, 1 skip pre-existente — sem regressao.
- [x] Decisao deliberada: sem integracao com `orquestrador.py`/`processador_tempo_real.py`, sem endpoint HTTP, sem persistencia nova — mesma disciplina das Fases 1-12.
- [x] **Fecha a Fase 12 (Collective Sales Intelligence)** completa: Tarefa 12.1 (Benchmark) -> 12.2 (Descoberta de Padroes).
- [x] Versao: `1.4.96` -> `1.4.97`.
- [x] Push + deploy confirmados (15/09/2026): commit `4fb4d93` no GitHub. `git pull` feito na VPS com `reunioes_ativas: 1` (so arquivos em disco, seguro); restart ficou pendente ate a reuniao real terminar, concluido automaticamente logo em seguida. Pos-restart: `/health` = `versao 1.4.97`, `status online`, `reunioes_ativas 0`; `/dashboard` = `200`; journal sem erros.

## Concluido (V.1.4.98 — Sales Science Engine, Fase 13 do "PROMPT MESTRE — SALE-IA V2", contrato + wrappers dos 5 submodulos existentes)

Usuario confirmou avancar para a Fase 13. Pergunta direta sobre escopo (mesma disciplina das Fases 7/10): 2 dos 7 submodulos literais (ObjectionTrendAnalyzer, ConversionDriverAnalyzer) nao foram construidos por nenhuma fase anterior — usuario escolheu so o contrato de saida + wrappers dos 5 submodulos que ja existem.

- [x] `agent/sales_science_engine.py` (novo, funcao pura, sem IA/banco): `SALES_SCIENCE_SUBMODULOS` documenta os 7 submodulos literais; `SUBMODULOS_IMPLEMENTADOS` (5) / `SUBMODULOS_PENDENTES` (objection_trend_analyzer, conversion_driver_analyzer) deixam o gap explicito, nao escondido.
- [x] Regra literal "Saida nunca deve ser apenas 'descobrimos isso'", imposta estruturalmente: `montar_insight()` exige `insight` + `evidence` + `sample` + `possible_confounders` + `recommended_test` sempre presentes e nao vazios — ValueError em qualquer um faltando. `confidence` e o unico campo opcional (None quando o submodulo de origem nao produz um intervalo de confianca formal).
- [x] Cada wrapper so reshape o resultado que o submodulo correspondente ja calculou — zero calculo estatistico novo: `insight_de_win_loss_analyzer()` <- `win_loss_rules.comparar_por_variavel_categorica()` (Fase 8); `insight_de_seasonality_engine()` <- `seasonality_rules.detectar_sazonalidade()` (Fase 9); `insight_de_seller_benchmark()` <- `seller_benchmark_rules.benchmark_controlado()` (Fase 12.1) — unico wrapper onde `possible_confounders` e preenchido automaticamente; `insight_de_strategy_effectiveness()` <- `recommendation_effectiveness_rules.calcular_efetividade_por_estrategia()` (Fase 10.3); `insight_de_pattern_discovery()` <- `pattern_discovery_rules.descobrir_padrao()` (Fase 12.2).
- [x] Cada wrapper retorna None (nunca insight vazio/forcado) quando o submodulo de origem nao encontrou sinal estatisticamente defensavel — amostra insuficiente, periodo nao significativo, diferenca nao significativa, ou nenhum confundimento detectado.
- [x] 21 testes novos (`tests/test_sales_science_engine.py`), chamando os modulos reais das Fases 8-12 (sem mock) para gerar as entradas dos wrappers. Suite completa: 905 testes (884 da Tarefa 12.2 + 21 novos), 0 falhas, 1 skip pre-existente — sem regressao.
- [x] Decisao deliberada: sem integracao com `orquestrador.py`/`processador_tempo_real.py`, sem endpoint HTTP, sem persistencia nova — mesma disciplina das Fases 1-12.
- [x] Versao: `1.4.97` -> `1.4.98`.
- [x] Push + deploy confirmados (16/09/2026): commit `d83497e` no GitHub. Restart na VPS ficou bloqueado por reuniao real em andamento (~100min), concluido automaticamente assim que terminou. Pos-restart: `/health` = `versao 1.4.98`, `status online`, `reunioes_ativas 0`; `/dashboard` = `200`; journal sem erros da aplicacao (ver "Incidente ao vivo" em `docs/CURRENT_STATE.md`).

## Concluido (V.1.4.99 — Sales Science Engine, fecha a Fase 13 do "PROMPT MESTRE — SALE-IA V2", ObjectionTrendAnalyzer + ConversionDriverAnalyzer)

Usuario confirmou "fechar 2 modulos pendentes" — fecha a Fase 13 por completo, os 7 submodulos literais do prompt mestre implementados.

- [x] `agent/objection_trend_analyzer.py` (novo, funcao pura, sem IA/banco, reaproveita `win_loss_rules.amostra_suficiente`/`intervalo_confianca_wilson`, Fase 8): `calcular_tendencias(eventos, ordem_periodos, minimo_amostra=AMOSTRA_MINIMA_PADRAO, confianca=0.95)` detecta se a participacao de uma categoria de objecao (vocabulario livre) vem crescendo ou diminuindo, comparando a primeira metade de `ordem_periodos` (ja ordenada cronologicamente pelo chamador) contra a segunda.
- [x] Significancia sem scipy — mesma disciplina honesta de `seasonality_rules.py` (Fase 9): so marca `significativo` quando ambos os totais (inicio/fim) tem amostra suficiente e os intervalos de confianca de Wilson das duas proporcoes nao se sobrepoem.
- [x] Testado com categoria crescente (PRICE, 20%->75%) e decrescente (TRUST, 80%->25%) no mesmo dataset. 9 testes novos (`tests/test_objection_trend_analyzer.py`).
- [x] `agent/conversion_driver_analyzer.py` (novo, funcao pura, sem IA/banco, reaproveita `win_loss_rules.calcular_taxa_conversao`/`comparar_por_variavel_categorica`, Fase 8): `ranquear_drivers(opportunities, campos, minimo_amostra=AMOSTRA_MINIMA_PADRAO, confianca=0.95)` ranqueia pares `(campo, valor)`, entre varios campos categoricos passados pelo chamador, pelo maior desvio absoluto da taxa de conversao em relacao ao baseline geral da amostra.
- [x] So inclui pares com sinal estatisticamente defensavel: amostra suficiente e intervalo de confianca de Wilson que nao contem o baseline — testado com um campo com sinal real e outro construido exatamente no baseline, corretamente excluido do ranking. 8 testes novos (`tests/test_conversion_driver_analyzer.py`).
- [x] `agent/sales_science_engine.py`: `insight_de_objection_trend_analyzer()` e `insight_de_conversion_driver_analyzer()` (novos) — mesmo padrao dos 5 wrappers ja existentes, reshape puro do resultado ja calculado, sem calculo estatistico proprio. `SUBMODULOS_IMPLEMENTADOS` agora cobre os 7 submodulos literais; `SUBMODULOS_PENDENTES` fica `frozenset()`. 6 testes novos + ajuste do teste de vocabulario para "7 implementados, 0 pendentes".
- [x] Achado durante a implementacao: os 2 primeiros templates (`TEMPLATE_TENDENCIA_OBJECAO`/`TEMPLATE_DRIVER`) continham a palavra "causa" dentro de uma negacao ("nao confirmacao de causa"/"nao causa") — o guarda de causalidade corretamente pegou isso como falso positivo estrutural. Corrigido para "associacao observada nesta amostra, nunca confirmacao de mecanismo" — mesma licao ja registrada em `pattern_discovery_rules.py` (Fase 12.2).
- [x] Suite completa: 925 testes (905 da V.1.4.98 + 20 novos — 9 em test_objection_trend_analyzer.py, 8 em test_conversion_driver_analyzer.py, 3 em test_sales_science_engine.py), 0 falhas, 1 skip pre-existente — sem regressao.
- [x] Decisao deliberada: sem integracao com `orquestrador.py`/`processador_tempo_real.py`, sem endpoint HTTP, sem persistencia nova — mesma disciplina das Fases 1-13.
- [x] **Fecha a Fase 13 (Sales Science Engine)** completa: todos os 7 submodulos literais implementados.
- [x] Versao: `1.4.98` -> `1.4.99`.
- [x] Push + deploy confirmados (16/09/2026): commit `ea6e4bc` no GitHub. `reunioes_ativas: 0` confirmado na VPS (sem reuniao ativa desta vez) — `git pull` (fast-forward `d83497e` -> `ea6e4bc`) + `systemctl restart saleia` — `active`, journal sem erros. Pos-restart: `/health` = `versao 1.4.99`, `status online`, 4 provedores `ok`; `/dashboard` = `200`.

## Concluido (V.1.4.100 — Fix MeetingMemory MEDIUMTEXT)

Usuario confirmou aplicar o fix do bug ativo achado no incidente de 15-16/09/2026.

- [x] `api/database.py::MeetingMemory`: `transcript_full`/`transcript_buffer`/`accumulated_summary`/`current_diagnosis` trocados de `Column(Text, ...)` para `Column(_LongText, ...)` (`Text().with_variant(MEDIUMTEXT, "mysql")`, ja definido no topo do arquivo e ja usado por `KnowledgeSource` desde a V.1.4.54 — mesma classe de bug, mesmo fix, nenhuma constante nova).
- [x] Suite completa: 925 testes, 0 falhas, 1 skip pre-existente — sem regressao (SQLite em dev/teste cai no `Text` comum, sem limite de tamanho).
- [x] Versao: `1.4.99` -> `1.4.100`.
- [x] Push + deploy confirmados (16/09/2026): commit `45e4492` no GitHub. Codigo enviado pra VPS com `git pull` (fast-forward `ea6e4bc` -> `45e4492`) enquanto ainda havia 1 reuniao ativa (seguro, so arquivos em disco). `ALTER TABLE meeting_memory MODIFY transcript_full MEDIUMTEXT, MODIFY transcript_buffer MEDIUMTEXT, MODIFY accumulated_summary MEDIUMTEXT, MODIFY current_diagnosis MEDIUMTEXT;` e `systemctl restart saleia` so executados depois que `reunioes_ativas` confirmou `0` (checado de novo imediatamente antes do ALTER, mesma disciplina de sempre). `DESCRIBE meeting_memory` confirmou as 4 colunas em `mediumtext`. Pos-restart: `/health` = `versao 1.4.100`, `status online`, `reunioes_ativas 0`, 4 provedores `ok` (restart tambem zerou os contadores de falha em memoria dos 4 provedores centrais, mesmo efeito colateral ja documentado em deploys anteriores); journal sem erros.
- [x] **Fecha o bug ativo do incidente de 15-16/09/2026** — proxima reuniao longa nao deve mais estourar o limite de 64KB.

## Concluido (Manuais atualizados — 16/09/2026, fora do fluxo de versao)

Usuario pediu, em paralelo a espera do deploy da V.1.4.100: atualizar `frontend/manual.html` (Manual do Usuario) removendo conteudo tecnico, e atualizar `frontend/manual_tecnico.html` (Dev Manual). Sem bump de versao — sao paginas estaticas servidas direto, nao versionadas no `/health`.

- [x] `frontend/manual.html`: removidas referencias a nomes de variavel de ambiente (`OPENAI_API_KEY`/`GROQ_API_KEY`), nomes de modelo (`whisper-1`, `whisper-large-v3`), custo por minuto, passo a passo de gerar chave em `console.groq.com`, e detalhe de implementacao ("chunks menores que 512 bytes") — secao 5 (Transcricao) e a FAQ correspondente reescritas pra dizer que e configuracao de administrador, sem expor os detalhes de infraestrutura. Badge de versao atualizado para 1.4.100 (estava em 1.4.54, desatualizado ha dezenas de versoes).
- [x] `frontend/manual_tecnico.html`: nova secao "SALE-IA V2 — PROMPT MESTRE (Fases 1-13)" mapeando cada fase do roadmap (V.1.4.73-99) ao(s) modulo(s) `agent/*_rules.py` correspondente(s), sem duplicar o historico de decisoes (aponta para CHANGELOG.md/CLAUDE.md). Tabela de tabelas MySQL ganhou `meeting_memory` (faltava) com nota do fix MEDIUMTEXT, e as 6 tabelas novas do SALE-IA V2. Novo card em Troubleshoot com o comando `ALTER TABLE` do fix MEDIUMTEXT. Badge de versao atualizado 1.4.40 -> 1.4.100.

## Concluido (V.1.4.101 — Experiment Engine, Fase 14 do "PROMPT MESTRE — SALE-IA V2", Tarefas 14.1 + 14.2, fecha a Fase 14)

Usuario confirmou avancar para a Fase 14 e fechar as duas tarefas (14.1 e 14.2) na mesma rodada.

- [x] `agent/experiment_engine_rules.py` (novo, funcao pura, sem IA/banco): Tarefa 14.1 — `montar_experiment_hypothesis(hypothesis, control, treatment, metric)`/`validar_experiment_hypothesis(...)` — os 4 campos literais do exemplo do prompt mestre, todos obrigatorios e nao-vazios. Testado com o exemplo literal ("Quantificar impacto antes de preco melhora avanco." / "fluxo atual" / "pergunta de impacto" / "stage advancement").
- [x] Tarefa 14.2 — `validar_experiment_config(pilot_group, control_group, duration, minimum_sample, safety_attestation)` configura o teste como A/B controlado (os 4 campos literais do prompt mestre), exige grupos distintos.
- [x] Regra de seguranca do prompt mestre ("experimento nao pode envolver: informacao falsa, discriminacao, preco enganoso, escassez falsa, ocultacao de informacao relevante") garantida estruturalmente: `EXPERIMENT_SAFETY_CHECKS` (5 itens literais) exigem atestacao explicita `True` cada — item ausente, `False`, ou valor truthy nao-booleano e recusado (`ValueError`), fail-closed. `montar_experiment_config()` combina 14.1+14.2 num registro so, revalidando a hipotese.
- [x] Decisao deliberada de escopo: sem integracao com `orquestrador.py`/`processador_tempo_real.py`, sem persistencia nova, sem endpoint HTTP. Analise estatistica do resultado (pilot vs control) nao construida — reaproveitar `pattern_discovery_rules.descobrir_padrao()` (Fase 12.2) quando pedido.
- [x] 22 testes novos (`tests/test_experiment_engine_rules.py`). Suite completa sem regressao.
- [x] **Fecha a Fase 14 (Experiment Engine)** completa: Tarefa 14.1 (hipotese -> teste) -> 14.2 (A/B controlado + seguranca).
- [x] Versao: `1.4.100` -> `1.4.101`.
- [x] Push + deploy confirmados (16/09/2026): commit `652781e` no GitHub. `reunioes_ativas: 0` checado antes/depois na VPS — `git pull` (fast-forward `200f19c` -> `652781e`) + `systemctl restart saleia` — `active`, journal sem erros. Pos-restart: `/health` = `versao 1.4.101`, `status online`, `reunioes_ativas 0`, 4 provedores `ok`.

## Concluido (V.1.4.102 — Seller DNA, Fase 15 do "PROMPT MESTRE — SALE-IA V2", Tarefas 15.1 + 15.2, fecha a Fase 15)

Usuario confirmou avancar para a Fase 15.

- [x] `agent/seller_dna_rules.py` (novo, funcao pura, sem IA/banco): Tarefa 15.1 — `SELLER_DNA_CAMPOS`, os 12 campos literais do prompt mestre (communication_style, opening_patterns, discovery_style, question_patterns, storytelling_patterns, negotiation_patterns, objection_patterns, pricing_style, closing_patterns, language_patterns, preferred_phrases, forbidden_phrases). `construir_seller_dna(seller_id, n_reunioes_analisadas, observacoes_por_campo, minimo_amostra=10)` monta o perfil a partir de observacoes ja extraidas pelo chamador.
- [x] Regra literal ("nao clonar personalidade a partir de poucas conversas, exigir amostra minima configuravel") garantida estruturalmente: recusa (`ValueError`) montar perfil com `n_reunioes_analisadas` abaixo do minimo (padrao 10, decisao desta rodada, sempre sobrescrevivel). Campo sem observacao vem `None`, nunca inventado (`campos_sem_observacao()`).
- [x] Tarefa 15.2 — regra central do prompt mestre ("André costuma fazer X" nao significa "X funciona"; SellerDNA registra comportamento, Sales Science mede eficacia, nunca misturar) garantida estruturalmente: `validar_sem_alegacao_de_eficacia(campo, valor)` recusa qualquer valor com linguagem de eficacia/resultado, chamada automaticamente em cada um dos 12 campos.
- [x] 17 testes novos (`tests/test_seller_dna_rules.py`), incluindo os 2 exemplos literais do prompt mestre. Suite completa sem regressao.
- [x] Decisao deliberada de escopo: sem integracao com `orquestrador.py`/`processador_tempo_real.py`, sem persistencia nova, sem endpoint HTTP.
- [x] **Fecha a Fase 15 (Seller DNA)** completa: Tarefa 15.1 (perfil) -> 15.2 (comportamento vs eficacia).
- [x] Versao: `1.4.101` -> `1.4.102`.
- [x] Push + deploy confirmados (16/09/2026): commit `3c993a2` no GitHub. `reunioes_ativas: 0` checado antes/depois na VPS — `git pull` (fast-forward `9cd9529` -> `3c993a2`) + `systemctl restart saleia` — `active`, journal sem erros. Pos-restart: `/health` = `versao 1.4.102`, `status online`, `reunioes_ativas 0`, 4 provedores `ok`.

## Concluido (V.1.4.103 — Next Best Action V2, Fase 16 do "PROMPT MESTRE — SALE-IA V2", fecha a Fase 16)

Usuario confirmou avancar para a Fase 16. Fase sem subtarefas numeradas — pergunta direta sobre escopo (mesma disciplina das Fases 7/10/13/14): usuario escolheu so contrato + validacoes estruturais, sem motor de IA nem integracao com orquestrador.

- [x] `agent/next_best_action_v2_rules.py` (novo, funcao pura, sem IA/banco): `NBA_V2_FONTES_COMBINADAS` — as 8 dimensoes literais do prompt mestre (metodologia/contexto/historico/sazonalidade/cliente/oportunidade/seller_dna/resultado_observado). `montar_next_best_action_v2(...)` monta a recomendacao no formato literal do exemplo (titulo/por_que/spin_gap/meddpicc_gap/historico/confianca/pergunta/evite) — testado reproduzindo o exemplo completo ("Quantifique o impacto financeiro." -> SPIN Implication ausente -> MEDDPICC Metrics ausente -> historico com evidencia -> confianca alta).
- [x] Regra literal ("recomendacao precisa manter consistencia com: fatos; estagio; politicas; conhecimento disponivel") garantida estruturalmente, reusando modulos ja prontos: fatos (spin_gap/meddpicc_gap precisam ser gaps reais de `spin_coverage_rules`/`meddpicc_rules`, Fases 3/4), estagio (spin_gap precisa pertencer ao estagio SPIN atual via `estagio_atual()`), politicas (`bloqueios_politica` precisa vir vazio, fail-closed, mesmo padrao de `EXPERIMENT_SAFETY_CHECKS` da Fase 14), conhecimento disponivel (confianca="alta" exige `historico_insight` real no contrato de `sales_science_engine.montar_insight()`, Fase 13).
- [x] 17 testes novos (`tests/test_next_best_action_v2_rules.py`), incluindo o exemplo literal completo e um caso por consistencia exigida. Suite completa sem regressao.
- [x] Decisao deliberada de escopo: sem integracao com `orquestrador.py`/`processador_tempo_real.py`, sem persistencia nova, sem endpoint HTTP.
- [x] **Fecha a Fase 16 (Next Best Action V2)** completa.
- [x] Versao: `1.4.102` -> `1.4.103`.
- [x] Push + deploy confirmados (16/09/2026): commit `c511902` no GitHub. `reunioes_ativas: 0` checado antes/depois na VPS — `git pull` (fast-forward `c751bc3` -> `c511902`) + `systemctl restart saleia` — `active`, journal sem erros. Pos-restart: `/health` = `versao 1.4.103`, `status online`, `reunioes_ativas 0`, 4 provedores `ok`.

## Concluido (V.1.4.104 — Preparacao para Autonomia / AutonomyPolicy, Fase 17 do "PROMPT MESTRE — SALE-IA V2", Tarefa 17.1, fecha a Fase 17)

Usuario confirmou avancar para a Fase 17. Regra explicita da propria fase ("ainda nao colocar agente para vender sozinho") deixa o escopo claro sem precisar de pergunta de escopo.

- [x] `agent/autonomy_policy_rules.py` (novo, funcao pura, sem IA/banco): `AUTONOMY_LEVELS` — os 6 niveis literais (OBSERVE, RECOMMEND, DRAFT, EXECUTE_LOW_RISK, EXECUTE_HUMAN_APPROVAL, AUTONOMOUS_WITHIN_POLICY), indice = numero literal do nivel (0-5). `DECISION_BOUNDARIES` — as 5 fronteiras literais (AUTONOMOUS, POLICY_DEPENDENT, HUMAN_APPROVAL, HUMAN_REQUIRED, FORBIDDEN).
- [x] `DECISION_BOUNDARIES_PADRAO` reproduz a tabela literal do exemplo (dar_informacao_publica/qualificar/agendar_reuniao/enviar_followup -> AUTONOMOUS; alteracao_juridica -> HUMAN_REQUIRED; promessa_nao_documentada -> FORBIDDEN). `avaliar_desconto(percentual, limite=5.0)` cobre o caso parametrizado (desconto <=5% -> POLICY_DEPENDENT, >5% -> HUMAN_APPROVAL).
- [x] Regra literal ("nenhum LLM pode contornar politicas") garantida estruturalmente: `pode_executar_autonomamente()` e o unico portao — FORBIDDEN/HUMAN_REQUIRED/HUMAN_APPROVAL sempre `False` em qualquer nivel (inclusive o maximo, 5). POLICY_DEPENDENT exige aprovacao explicita + nivel suficiente. AUTONOMOUS so executa em nivel EXECUTE_LOW_RISK (3) ou acima. `avaliar_acao()` fail-closed (ValueError se acao nao mapeada).
- [x] "Testes: criar suite especifica de policy tests" atendido literalmente: `tests/test_autonomy_policy_rules.py`, nucleo `GuardaContraContornoDePoliticaTest` testando fronteira x todos os 6 niveis. 27 testes novos. Suite completa sem regressao.
- [x] Decisao deliberada de escopo: sem integracao com `orquestrador.py`/`processador_tempo_real.py`, sem endpoint HTTP, sem persistencia nova — nenhum nivel de autonomia e de fato ativado.
- [x] **Fecha a Fase 17 (Preparacao para Autonomia)** completa.
- [x] Versao: `1.4.103` -> `1.4.104`.
- [x] Push + deploy confirmados (16/09/2026): commit `6d67db8` no GitHub. `reunioes_ativas: 0` checado antes/depois na VPS — `git pull` (fast-forward `a15781f` -> `6d67db8`) + `systemctl restart saleia` — `active`, journal sem erros. Pos-restart: `/health` = `versao 1.4.104`, `status online`, `reunioes_ativas 0`, 4 provedores `ok`.

## Concluido (V.1.4.105 — Tenant/User Isolation, Fase 18 / Tarefa 18.1 do "PROMPT MESTRE — SALE-IA V2")

Usuario confirmou avancar para a Fase 18 (Seguranca), comecando pela Tarefa 18.1. Auditoria previa confirmou achado ja documentado desde a Fase 0 (V.1.4.72): `POST /recapitulacao-viva` sem autenticacao nenhuma, e revelou que nenhuma tabela do produto principal (MeetingMemory, sessoes, client_profiles) tinha coluna de dono — ~25 endpoints exigiam login mas nenhum verificava ownership.

- [x] Decisoes confirmadas com o usuario: dado sem dono registrado (legado/anonimo) continua acessivel a qualquer autenticado, so dado NOVO fica isolado; `/cenario/{meeting_id}` continua publico por design (tela mostrada ao proprio cliente).
- [x] `api/database.py::MeetingMemory.usuario_id` (nullable) — dono canonico da reuniao, estampado por `registrar_transcricao_meeting()` (nunca sobrescreve). `agent/client_intelligence.py::client_profiles.usuario_id` (self-migrating) — estampado por `criar_cliente()`.
- [x] `api/main.py::_verificar_dono_ou_admin()` — portao unico: sem dono libera qualquer autenticado; com dono so libera o proprio dono ou admin; resto -> 404.
- [x] Fix critico: `POST /recapitulacao-viva` — login continua opcional (extensao anonima e uso legitimo), mas reuniao COM dono exige token do proprio dono/admin.
- [x] Ownership aplicado em ~15 endpoints: relatorios/status, followups (gerar/listar/patch/delete), historico/uso (lista+detalhe), sessoes (get/delete/exportar-base/lista), clientes (get/patch/lista/vincular-reuniao/desvincular/resumo-reuniao/por-reuniao).
- [x] Achado de correcao: 2 endpoints sem `except HTTPException: raise` mascarariam o 404 de ownership como 500 — corrigido.
- [x] Decisao deliberada de escopo (fora desta rodada): /relatorios (webhook Tactiq, sem usuario), /busca-semantica, /grafo/conexoes, /workspace/*, /playbooks*, /skills* (compartilhados por design), /cenario/*/conducao (nao le MeetingMemory), SellerDNA/Opportunity/SalesEvent/RecommendationEvent (sem endpoint HTTP ainda).
- [x] `tests/test_tenant_isolation.py` — 20 testes novos (usuario A cria, usuario B recebe 404, admin acessa tudo, dado sem dono continua aberto). Suite completa sem regressao.
- [x] Versao: `1.4.104` -> `1.4.105`.
- [ ] Push + deploy na VPS pendente — `client_profiles.usuario_id` e self-migrating, mas `meeting_memory.usuario_id` exige `ALTER TABLE meeting_memory ADD COLUMN usuario_id VARCHAR(36) NULL` manual (create_all nao migra coluna em tabela existente, mesmo padrao do opportunity_id/MEDIUMTEXT), com reunioes_ativas:0 confirmado antes. **Tarefas 18.2 (Prompt Injection), 18.3 (PII) e 18.4 (Audit Trail) nao comecam sem nova confirmacao explicita do usuario.**

## Pendente
- [ ] **Incidente de saldo (achado 15-16/09/2026, atualizado apos deploy V.1.4.98)**: DeepSeek `402 Insufficient Balance` desde `21:32:52` (15/09/2026, 1740 ocorrencias em 3h) — mesmo padrao do incidente de 31/08/2026. **Atualizacao ~01:13 UTC (16/09)**: OpenAI tambem confirmado sem credito real (`429 insufficient_quota`, "You have no credits remaining") numa reuniao nova, poucos minutos apos o restart do V.1.4.98 zerar os contadores em memoria. 2 dos 4 provedores centrais com cobranca confirmada esgotada, nao so 1. Fallback para Conta Claude pessoal do vendedor nao disparou (sem login na extensao, mesmo achado de antes). Decisao de saldo/financeira, fora do escopo tecnico desta sessao.
- [ ] **Debito tecnico (achado 05/09/2026, fora de escopo)**: migrar `google.generativeai` (totalmente descontinuado pelo Google) para `google.genai`, e `claude-sonnet-4-20250514` (EOL 15/06/2026) para um modelo Anthropic atual.
- [x] ~~Fase 3 PROMPT MESTRE — deploy do Whisper Local na VPS~~ — **feito em 05/09/2026**: deploy confirmado (`/health` = `versao 1.4.63`) e modelo validado com transcricao real direto na VPS (4,4s, ver `docs/TASKS.md` acima e CHANGELOG). Falta so ativar de fato `whisper_local` como `TRANSCRICAO_PROVEDOR` pelo Dashboard quando o usuario decidir (hoje continua `whisper`/`groq`).
- [x] ~~Fase 3 PROMPT MESTRE — captura de audio do sistema/aba~~ — **implementado em 05/09/2026 (extensao V.1.4.7)**: `chrome-extension/offscreen.js` reescrito pra capturar audio da aba via `chrome.tabCapture` (nao mais tentativa de mic, que nao funcionaria num offscreen document sem UI pro prompt); `background.js::handleIniciarCaptura` resolve o streamId; `content.js` ganhou `iniciarCapturaAba()`/`pararCapturaAba()` (chamadas junto do botao de mic existente) + handler `transcricaoAudio` que commita como fala do "Cliente". Achado importante: existiam 2 mecanismos de captura de audio no codigo — o `iniciarCaptura`/offscreen (preparado desde abril/2026) nunca era chamado por nenhum botao da UI; o botao real usava um caminho totalmente separado (mic direto em content.js). Detalhe completo no CHANGELOG.
  - **Pendente**: validacao ao vivo numa reuniao real — `chrome.tabCapture` e o comportamento do offscreen document so podem ser confirmados de verdade testando (sintaxe e logica verificadas estaticamente, `node --check` limpo nos 3 arquivos).
- [x] ~~Fase 2 Promptfoo — dataset real~~ — **feito em 05/09/2026**: os 22 casos sinteticos foram substituidos por 34 objecoes REAIS anonimizadas, puxadas (SSH, so leitura) de `sales_memories` (`memory_type='objection'`) — TODAS as que existiam no banco nessa data. Reescritas manualmente como fala em primeira pessoa, anonimizadas (2 nomes proprios removidos). Categoria `FIT` (unica sem exemplo real) ganhou 2 casos sinteticos isolados e marcados em `objections_fit_gap.yaml`. Suite re-rodada: 41/41 (100%), custo real US$0,0093 — apos corrigir 4 asserts `not-contains:"desconto"` que davam falso positivo quando o Coach corretamente aconselhava o vendedor a NAO dar desconto (trocados por `llm-rubric`, mesma licao do red team mais cedo no dia). Volume (36) ainda abaixo da meta de 50-200 do prompt mestre — so existiam 34 objecoes reais no banco; cresce organicamente. Detalhe completo no CHANGELOG e `evals/README.md`.
- [ ] Testar Visual Cenario AI em producao (DALL-E 3 + OpenAI).
- [x] ~~Recarregar extensao Chrome~~ — **obsoleto/feito em 05/09/2026**: extensao testada ao vivo em producao real nesta mesma sessao (V.1.4.6), varias vezes, incluindo remocao/reinstalacao completa. Nota original ("migracao de URL e V.1.4.3") ja superada — extensao esta em V.1.4.6 e funcionando (`/iniciar-sessao`, `/tempo-real`, `/audio-transcricao` confirmados 200 OK com `ext_ver: "1.4.6"`).
- [x] ~~Descomissionar VPS antiga `204.168.180.25`~~ — **CANCELADO, achado critico em 05/09/2026**: essa VPS NAO e mais dedicada ao SALEIA — e o servidor de producao ATIVO do projeto MeLembraAI (`melembra-ai-backend.service` rodando, + nginx, MySQL, PostgreSQL, Redis, Next.js na porta 3001, gunicorn e outros processos). O backend do SALEIA (`saleia.service`) ja nao roda mais la (confirmado via `systemctl list-units` por SSH). "Descomissionar" essa maquina destruiria producao do MeLembraAI e possivelmente outros projetos. Este item NUNCA deve ser executado como "desligar/apagar a VPS" — se houver arquivos especificos do SALEIA sobrando em disco nela (ex.: `/opt/saleia` antigo), isso e uma limpeza pontual e segura, bem diferente de decomissionar o servidor inteiro. Nao investigado ainda se ha tais arquivos.
- [ ] Alterar senha do admin `phpos35@gmail.com` via dashboard.
- [x] **Reindex de embeddings pos-deploy — verificado (04/09/2026), nada pendente**: `--dry-run --table all` rodado direto na VPS via SSH (senha root; `reunioes_ativas: 0` confirmado antes) retornou `ja_atual=54/54` (`base_conhecimento`) e `ja_atual=394/394` (`sales_memories`), `sucesso=0 falha=0` — 100% das linhas ja estao em `ollama`/`embeddinggemma`, confirmado tambem por query direta no MySQL (`GROUP BY embedding_provider, embedding_model`). Nao havia mais nenhum embedding legado da OpenAI para migrar; o reindex real (sem `--dry-run`) nao precisou ser executado por nao haver nada a fazer.
- [ ] **Corrigir a chave SSH `saleia_vps`** (`Permission denied (publickey,password)`, checado em 01/09/2026 — acesso restabelecido só por senha root fornecida pelo usuario) — checar `authorized_keys` na VPS nova ou gerar/cadastrar chave nova.
- [ ] **Validar end-to-end a transcricao de audio (Groq)** apos o restart confirmado do V.1.4.50/1.4.51 — chave `GROQ_API_KEY` foi atualizada em 31/08/2026, presente no `.env`, mas nunca testada ponta a ponta (sem trafego real de `/audio-transcricao` desde o restart).
- [x] **Migracao de reunioes historicas (Drive) — 74/74 concluida (04/09/2026)**: as 23 reunioes que falhavam com 503 em 20/08/2026 foram reprocessadas com sucesso (0 falhas) — a degradacao dos provedores de IA que causava o 503 na epoca ja nao estava mais presente. `scripts/migrar_reunioes_historico.py` processou o total das 74 reunioes exportadas do Google Drive (Gemini Notes) contra producao, cada uma virando um relatorio completo + entrada de Sales Memory. Os 5 `.txt` de chat do lote (so trocas de e-mail no chat do Meet, sem sinal de conversa) continuam propositalmente excluidos. Zip original em `C:\Users\phpos\Downloads\drive-download-20260820T182045Z-1-001.zip`; estado final em `data/migracao_reunioes_estado.json`.

## Concluido (Ollama na VPS — 17/08/2026)

- [x] Ollama instalado na VPS nova (`37.27.214.33`) via script oficial — `ollama.service` active + enabled.
- [x] Modelo `embeddinggemma` baixado e testado — dimensao real confirmada: 768.
- [x] Confirmado que a instalacao nao afetou `saleia.service` (continuou active durante todo o processo).

Projeto em V.1.4.39 local + GitHub (pendente deploy VPS) | Ollama ja instalado na VPS nova | VPS antiga (deprecada).
