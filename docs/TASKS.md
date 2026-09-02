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
- **Pendente**: `KNOWLEDGE_COMPILER_ENABLED=true` ainda nao foi setado no `.env` da VPS — a feature continua invisivel (`404`) ate alguem pedir pra ativar. Fases 4-6 do Knowledge Compiler ainda nao iniciadas.

## Pendente

- [ ] Testar Visual Cenario AI em producao (DALL-E 3 + OpenAI).
- [ ] Recarregar extensao Chrome: `chrome://extensions` → 🔄 recarregar SALEIA (aplica migracao de URL e V.1.4.3).
- [ ] Descomissionar VPS antiga `204.168.180.25` apos validacao.
- [ ] Alterar senha do admin `phpos35@gmail.com` via dashboard.
- [ ] **Reindex de embeddings pos-deploy**: `python -m scripts.reindex_embeddings --dry-run --table all` (conferir) e depois sem `--dry-run` (embeddings atuais sao da OpenAI, incompativeis com Ollama). Ainda nao executado.
- [ ] **Corrigir a chave SSH `saleia_vps`** (`Permission denied (publickey,password)`, checado em 01/09/2026 — acesso restabelecido só por senha root fornecida pelo usuario) — checar `authorized_keys` na VPS nova ou gerar/cadastrar chave nova.
- [ ] **Validar end-to-end a transcricao de audio (Groq)** apos o restart confirmado do V.1.4.50/1.4.51 — chave `GROQ_API_KEY` foi atualizada em 31/08/2026, presente no `.env`, mas nunca testada ponta a ponta (sem trafego real de `/audio-transcricao` desde o restart).
- [ ] **Migracao de reunioes historicas (Drive) — 23/74 restantes**: `scripts/migrar_reunioes_historico.py` processou 51/74 reunioes exportadas do Google Drive (Gemini Notes) direto contra producao — cada uma virou um relatorio completo + entrada de Sales Memory. As 23 restantes falharam consistentemente com 503 mesmo apos retry com backoff, mesmo com DeepSeek/OpenAI/Anthropic parcialmente recuperados — parece timeout de infraestrutura em reunioes grandes (media 127k chars nas que falham vs 99k nas que deram certo, sem corte limpo) combinado com degradacao dos provedores no momento. Para retomar (idempotente — pula as 51 ja feitas):
  ```bash
  # extrair o zip baixado do Drive de novo se a pasta de trabalho nao existir mais:
  # unzip "C:\Users\phpos\Downloads\drive-download-20260820T182045Z-1-001.zip" -d <pasta>
  python -m scripts.migrar_reunioes_historico --pasta <pasta_com_os_docx> \
    --base-url https://api.saleia.app.br \
    --estado-file data/migracao_reunioes_estado.json
  ```
  Zip original ainda em `C:\Users\phpos\Downloads\drive-download-20260820T182045Z-1-001.zip` (74 `.docx` + 5 `.txt` de chat — os `.txt` de chat foram propositalmente excluidos desta migracao).

## Concluido (Ollama na VPS — 17/08/2026)

- [x] Ollama instalado na VPS nova (`37.27.214.33`) via script oficial — `ollama.service` active + enabled.
- [x] Modelo `embeddinggemma` baixado e testado — dimensao real confirmada: 768.
- [x] Confirmado que a instalacao nao afetou `saleia.service` (continuou active durante todo o processo).

Projeto em V.1.4.39 local + GitHub (pendente deploy VPS) | Ollama ja instalado na VPS nova | VPS antiga (deprecada).
