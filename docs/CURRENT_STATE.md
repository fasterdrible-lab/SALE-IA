# SALEIA - Estado Atual

Atualizado em: 2026-08-21 (V.1.4.44)

## Ambiente

- Pasta canonica local: `C:\Users\phpos\OneDrive\SALE-IA\SALEIA`
- Dominio de producao: `https://api.saleia.app.br` (DNS propagando ~2h apos 09/06/2026 16h UTC)
- Dominio antigo (deprecado): `https://api.saleia.com.br` (VPS antiga ainda ativa)
- Dashboard: `https://api.saleia.app.br/dashboard`
- Backend de producao: FastAPI via `saleia.service`
- Porta interna na VPS: `127.0.0.1:8000`
- Proxy publico: nginx em `80/443` + Cloudflare proxy (nuvem laranja)
- Banco em producao: MySQL local (127.0.0.1) — latencia ~2ms

## Deploy

- VPS nova (dedicada): `37.27.214.33` — CPX32, 4 vCPU, 8GB RAM, 160GB SSD, Helsinki
- VPS antiga (deprecada): `204.168.180.25` — aguarda descomissionamento
- App na VPS: `/opt/saleia`
- Servico: `saleia.service`
- Health: `curl http://127.0.0.1:8000/health` ou `https://api.saleia.app.br/health`
- Deploy via: `git pull` + `systemctl restart saleia`
- Nao sobrescrever em deploy: `.env`, `venv`, `data`, `logs`

## Versao Atual

`V.1.4.45` — piloto Claude Account tambem disponivel na tela de Analisar Transcricao (texto colado), alem do detalhe de sessao gravada. V.1.4.44 confirmada deployada e ativa na VPS nova em 22/08/2026 (ver "Deploy V.1.4.44 Confirmado") | extensao Chrome `V.1.4.3` | VPS antiga (`204.168.180.25`) deprecada

## Funcionalidades Entregues

### Core (V.1.3.x)
- `MeetingMemory` persistida no banco por `meeting_id`.
- Transcricao completa, buffer recente, resumo acumulado, diagnostico atual, historico de score, momentos-chave e eventos.
- Coach em tempo real com envio de contexto reduzido para IA.
- Eventos estruturados e key moments.
- Trigger de recapitulacao por deixa verbal com cooldown.
- Recapitulacao viva com mapa mental para sidebar.
- Diagnostico final pos-reuniao.
- Estimativa de custo das chamadas de IA.
- Roteamento de IA com fallback (DeepSeek → OpenAI → Anthropic → Gemini).
- Dashboard publico carregando em `/dashboard`, `/dashboard/` e `/dashboard.`.
- DeepSeek configurado em producao como provedor preferido.
- Configuracoes em accordion no dashboard (usuarios, APIs, base).
- Conducao ligada aos prompts da apresentacao.
- RAG ajustado para o fluxo atual.

### Autenticacao e Administracao (V.1.4.0)
- Auth JWT: `POST /auth/login`, `POST /auth/cadastro`, `POST /auth/recuperar-senha`.
- Tabela `usuarios` criada automaticamente no startup (MySQL).
- Helper `_req_auth` (qualquer usuario autenticado) e `_req_admin` (apenas admin).
- Admin de usuarios: `GET/PATCH/DELETE /admin/usuarios/*` — perfil, plano, status, reset senha.
- Admin de APIs: `GET/POST/PATCH /admin/api/*` — provedores, chaves, teste, principal.
- `POST /cenario/{meeting_id}/conducao` agora exige JWT valido.

### Recuperacao de Senha (V.1.4.1)
- `agent/email_service.py` — envio real de e-mail SMTP (smtplib stdlib).
- `migrar_colunas_usuarios()` — adiciona `reset_token` e `reset_token_exp` na tabela `usuarios`.
- `POST /auth/recuperar-senha` — gera token seguro (expira 1h), envia e-mail em background, resposta sempre neutra.
- `GET /reset?token=...` — serve pagina HTML inline com formulario de nova senha.
- `POST /auth/redefinir-senha` — valida token, aplica bcrypt, limpa token do banco.
- Variaveis SMTP necessarias no `.env`: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM`, `APP_BASE_URL`.

### Extensao Chrome (V.1.4.1)
- Bug critico corrigido: `background.js::abrirCenarioComFoto` agora le a foto de `chrome.storage.local['saleia_foto_pendente']` em vez de `msg.foto` (que era sempre undefined).
- `manifest.json` versao atualizada para `1.4.1`.
- `popup.js` versao exibida dinamicamente via `chrome.runtime.getManifest().version`.

### Historico de Uso (V.1.4.0)
- `GET /historico/uso` — lista reunioes com custo, score final, DISC, num_analises.
- `GET /historico/uso/{meeting_id}` — detalhe com score_history, key_moments, eventos.
- Pagina Historico no dashboard: grafico de barras de evolucao do score, momentos-chave e eventos.

### Melhorias de Filtros (V.1.4.0)
- Filtros de Reunioes: data De/Ate + botao Limpar + contador de resultados.
- `input[type=date]` com estilo dark no dashboard.

### Testes (V.1.4.0)
- `tests/test_smoke.py`: 8 testes automatizados para `/health`, `/dashboard`, `/recapitulacao-manual`.
- Dependencias `bcrypt` e `PyJWT` adicionadas ao `requirements.txt`.

### Visual Scenario AI (V.1.4.0)
- `POST /generate-visual-scenario`: extrai contexto via IA, gera 2 imagens (atual/futuro) com DALL-E 3.
- `ImageGenerator` usa `response_format=b64_json` — data URI armazenado no banco, sem expiracao.
- `frontend/visual-scenario.html`: webcam do cliente, paineis Atual/Futuro, fullscreen, comparacao, historico.
- `cenario.html` tem botao `Gerar Cenarios` que abre a pagina com o meeting_id da reuniao ativa.

## Estado dos Provedores

Ordem ativa:

1. `deepseek`
2. `openai`
3. `anthropic`
4. `gemini`

Modelos padrao:

- DeepSeek: `deepseek-chat`
- OpenAI: `gpt-4o`
- Anthropic: `claude-sonnet-4-6`
- Gemini: `gemini-2.0-flash`

## Validacoes Recentes

- Visual Scenario fix: webcam espelhada (scaleX -1) + canvas flip + botao Capturar Tela via getDisplayMedia para capturar o cliente do Google Meet.
- Smoke tests: 8/8 OK em 1.1s (`python -m unittest tests.test_smoke -v`).
- `/health` publico respondeu `online`.
- `/dashboard` publico respondeu `200`.
- `/recapitulacao-manual` retornou `200` em producao apos correcoes de fallback.

## Funcionalidades Novas (V.1.4.27–V.1.4.28)

### Fix: 502 Bad Gateway + Estabilidade VPS (V.1.4.27)
- Workers uvicorn entravam em estado zumbi após ~2,5 dias: `systemctl restart saleia` corrigiu
- `RuntimeMaxSec=86400` adicionado ao `/etc/systemd/system/saleia.service` — reinício automático diário
- Logo quebrada no login: `frontend/login.html` src corrigido para `/static/logo-saleia.png`
- `frontend/static/logo-saleia.png` adicionado ao nginx static path

### Motor de Próxima Melhor Ação (V.1.4.28)
- `next_best_action`: tipo (question|insight|warning|next_step), título, mensagem, motivo, risco, follow-up, confidence
- `conversation_stage`: 8 estágios SPIN (abertura → compromisso)
- `kare_type`: keep | attain | recapture | expand
- `maturity_score`: 7 critérios independentes, 0-100
- Matriz de decisão com 10 regras em ordem de prioridade
- Insight Desafiador como tipo formal (Sandler + Venda Desafiadora)
- DISC expandido por perfil em cada regra da matriz
- Sidebar Chrome: badges Stage+KARE, bloco Próxima Melhor Ação com risco/follow-up, grid Maturity Score

### Sales Brain — Inteligência Comercial Acumulativa (V.1.4.31–V.1.4.37)

#### Fase 1 — Memórias de Vendas (V.1.4.31)
- `agent/sales_memory.py`: extrai DISC, objeções, dores, próximos passos, score final e lições após cada reunião.
- Tabela MySQL `sales_memories`: gerada automaticamente no startup.
- Endpoints: `GET /relatorios/{mid}/memoria`, `POST /relatorios/{mid}/gerar-memoria`.

#### Fase 2 — Playbooks (V.1.4.32)
- `agent/playbook_generator.py`: gera roteiro de vendas a partir de reuniões marcadas como ganhas.
- Tabela MySQL `playbooks`: id, meeting_id, titulo, conteudo, disc_profile, stage, score_origem.
- Endpoints: `POST /relatorios/{mid}/marcar-ganha`, `GET /playbooks`, `GET /playbooks/{pid}`, `DELETE /playbooks/{pid}`.
- Dashboard: aba "Playbooks" no menu lateral.

#### Fase 3 — Skills Especializadas (V.1.4.33)
- `agent/skill_resolver.py`: seleciona skill com base em DISC + score + estágio da conversa.
- 5 skills: fechamento, objecao_preco, prospecting, negociacao, reativacao.
- Tabela MySQL `skills`: id, nome, conteudo_instrucao, condicoes_json.
- Integrado ao `processador_tempo_real.py` como `skill_context` injetado em cada fragmento.

#### Fase 4 — Perfil de Clientes / Client Intelligence (V.1.4.34)
- `agent/client_intelligence.py`: CRUD de clientes e vínculo cliente↔reunião.
- Tabelas: `client_profiles` (id, user_id, nome, empresa, cargo, email, whatsapp, notas, status) e `client_meetings` (client_id, meeting_id, score_reuniao, vinculado_em).
- Endpoints: `GET/POST /clientes`, `GET/PATCH/DELETE /clientes/{cid}`, `POST/DELETE /clientes/{cid}/reunioes/{mid}`.
- Dashboard: aba "Clientes" — cards com score médio, total reuniões, último contato, status (ativo/ganho/em_pausa/perdido).
- Relatório: botão "🔗 Vincular ao Cliente".
- Métricas agregadas via JOIN + AVG na query de listagem.

#### Fase 5 — Sistema Multiagente (V.1.4.36)
- `agent/multiagente/orquestrador.py`: dispara 4 agentes em paralelo com `asyncio.gather(return_exceptions=True)`.
- Agentes: Coach (estágio SPIN, NBA, alerta, texto falável), DISC (perfil D/I/S/C, KARE, temperatura), Finance (mapa financeiro, objeções preço), Closer (score, maturity, próxima pergunta).
- RAG buscado uma única vez no orquestrador e compartilhado entre todos os agentes.
- `_safe()` converte Exception em `{}` — se um agente falhar, os outros 3 continuam.
- `_nba_para_nbq()` mantém backward compat com extensões Chrome antigas.
- `processador_tempo_real.py::analyzeRealtimeMeeting` agora chama `analisar_fragmento_multi()` em vez do agente legado.
- skill_context e client_context resolvidos antes do orquestrador nessa função.

#### Fase 6 — Follow-up Inteligente (V.1.4.37)
- `agent/followup_generator.py`: IA gera mensagens para WhatsApp, Email e LinkedIn adaptadas por DISC.
- `agenda_inteligente(score)`: timing server-side (score ≥65 → hot; 35–64 → warm; <35 → cold).
- Tabela MySQL `followups`: id, meeting_id, client_id, canal, assunto, mensagem, call_to_action, tom, disc_profile, score, dias_apos, agendado_para, status (pendente/enviado/descartado).
- Endpoints: `POST /relatorios/{mid}/followups/gerar`, `GET /relatorios/{mid}/followups`, `PATCH /followups/{fid}`, `DELETE /followups/{fid}`.
- Dashboard/Relatório: botão "📩 Follow-up" — seção expandível com cards por canal, botão copiar e marcar enviado.

### Embeddings Desacoplados — Ollama local + OpenAI opcional (V.1.4.39)
- `services/embeddings/`: interface `EmbeddingProvider` (`embed`, `embed_async`, `embed_batch`, `health_check`), `OllamaEmbeddingProvider` (HTTP local via `httpx`, zero import de SDKs de LLM externos), `OpenAIEmbeddingProvider`, `factory.get_embedding_provider()` (lê `EMBEDDING_PROVIDER`, erro explícito em valor desconhecido).
- `EMBEDDING_PROVIDER=ollama` é o padrão — RAG (`base_conhecimento`) e Sales Memory (`sales_memories`) deixam de depender obrigatoriamente da OpenAI.
- Refatorados os 4 pontos que geravam embedding: `agent/base_conhecimento.py`, `agent/sales_memory.py`, `api/main.py::adicionar_base` (`POST /base`), `agent/sessao_manager.py::exportar_para_base_conhecimento`.
- Novas colunas `embedding_provider`/`embedding_model`/`embedding_dim` em `base_conhecimento` e `sales_memories` — vetores de dimensões diferentes nunca são comparados entre si (bug pré-existente de `ValueError` fechado).
- `GET /admin/embeddings/status` (novo, JWT admin): status do provedor ativo, dimensão, contagem de documentos/memórias indexados.
- `scripts/reindex_embeddings.py`: CLI idempotente para regenerar embeddings sob o provedor configurado (`--dry-run`, `--provider`, `--table`, `--limit`).
- `docs/EMBEDDINGS_LOCAL.md`: guia de instalação do Ollama (Windows/Linux) e configuração.
- Testes: `tests/test_embeddings.py` (32 testes, mockado, sem rede/DB) + `tests/test_embeddings_semantic_ranking.py` (integração real, auto-skip sem Ollama local).

## Funcionalidades Novas (V.1.4.42 — 20/08/2026)

### Visual Cenário — removido da navegação visível
- Item de menu `🎬 Visual Cenário` removido de `frontend/dashboard.html`;
  botão `🎬 Visual` e função `abrirVisualScenario()` removidos de
  `frontend/cenario.html`.
- Backend intocado: `POST /generate-visual-scenario` e
  `frontend/visual-scenario.html` continuam funcionais, acessíveis por URL
  direta (`/visual-scenario?meeting=<id>`) para validação manual pendente.
- Revisão da decisão anterior (V.1.4.41 dizia "aceito como está" para
  manter Visual Cenário visível) — usuário pediu para tirar visualmente do
  front também aqui, mantendo só o backend.

## Funcionalidades Novas (V.1.4.41 — 20/08/2026)

Revisao da V.1.4.40 contra a especificacao original (prompt de desenvolvimento
recebido apos o deploy) encontrou 6 lacunas; 2 foram corrigidas nesta versao
(mecanicas, sem decisao de produto pendente), 4 seguem em aberto de proposito
(exigem decisao de arquitetura/produto — ver "O Que Falta").

### Propensao de Compra — dimensoes nomeadas + limiares configuraveis
- `PROMPT_RECAPITULACAO`: nova regra orienta a IA a avaliar 9 dimensoes de
  venda nomeadas (Dor, Urgencia, Orcamento, Autoridade, Interesse, Intencao,
  Engajamento, Proximo passo, Objecoes) ao montar os fatores do bloco
  `propensao` — so inclui a dimensao que realmente apareceu na conversa.
- `agent/propensao_rules.py`: `LIMIAR_ALTA`/`LIMIAR_MEDIA` deixam de ser
  constantes fixas e passam a ler `PROPENSAO_LIMIAR_ALTA`/`PROPENSAO_LIMIAR_MEDIA`
  do `.env` (fallback 70/45) — continuam sendo o unico lugar do codigo com
  esses limiares, agora ajustaveis sem deploy.

## Funcionalidades Novas (V.1.4.40 — 19/08/2026)

### Extensao Chrome simplificada
- Toggle "API ativa/desligada" com gate completo em todos os pontos de rede (incl. heartbeat) e bug de persistencia no service worker corrigido (estado nao era restaurado do storage fora do `onInstalled`).
- Removidos da UI: Visual Cenario, Mapa Financeiro (card), Score de Compra (numero), Cenario do Cliente (botao), "Backend online + URL" no popup — substituido por indicador simples Conectado/Desconectado/Conectando.
- `manifest.json`: permissao `scripting` removida (ficou orfa); versao `1.4.2` → `1.4.3`.

### Base de Conhecimento — download do documento original
- `base_conhecimento` ganhou colunas `arquivo_nome_original/arquivo_path/arquivo_mime/arquivo_tamanho`; `POST /base` agora multipart (texto + arquivo opcional); novo `GET /base/{id}/download` (JWT); arquivos em `data/base_arquivos/`.

### Sessoes ao Vivo — busca e filtros
- Busca por cliente/empresa/link/data/hora, filtros de status/periodo e ordenacao no dashboard (client-side); `listar_sessoes` enriquecida com cliente vinculado via `client_meetings`+`client_profiles`.

### Propensao de Compra
- `agent/propensao_rules.py`: classificacao deterministica (Alta/Media/Baixa/Nao determinada) a partir do score interno, sem custo de IA extra no tempo real.
- `PROMPT_RECAPITULACAO` ganhou bloco `propensao` estruturado (fatores + evidencias + como avancar) para o Detalhamento no dashboard, gerado uma unica vez por recapitulacao (sem chamada extra ao abrir).

## Funcionalidades Novas (V.1.4.44 — 21/08/2026)

### Piloto Claude Account Mode
Cada vendedor conecta a própria assinatura Claude (Pro/Max) via token de
`claude setup-token` e analisa suas reuniões sob demanda pelo Dashboard, sem
depender de uma conta de IA central da SALEIA. Atrás da feature flag
`CLAUDE_ACCOUNT_PILOT` (desligada por padrão). Detalhe completo no
CHANGELOG (V.1.4.44) — resumo:
- `agent/claude_account.py`: `ClaudeAccountExecutor`, único ponto de chamada
  ao Claude Agent SDK; criptografia do token (Fernet), sanitização de erros,
  classificação `LOGIN_REQUIRED`/`AUTH_REQUIRED`/`USAGE_LIMIT_REACHED`/`GENERIC_ERROR`.
- Tabelas novas `ClaudeConnection`/`ClaudeMeetingAnalysis` (`api/database.py`);
  reusa análise existente se a transcrição não mudou.
- 7 endpoints novos (`/claude-account/*`, `/admin/claude-account/metricas`)
  — conexão sempre resolvida pelo JWT de quem está logado, nunca por id vindo
  do cliente (isolamento por usuário sem precisar de "dono da reunião").
  Não existe hoje na SALEIA — extensão Chrome e tabela `sessoes` continuam
  anônimas, fora do escopo deste piloto.
- Dashboard: card de conexão em Configurações, botão "Analisar com Claude" na
  sessão, feedback 👍/😐/👎, painel de métricas admin no Monitor.
- 19 testes novos em `tests/test_claude_account.py`.

## Deploy V.1.4.44 Confirmado (22/08/2026)

- `reunioes_ativas: 0` checado em `/health` antes de agir (duas vezes: antes do `git pull` e novamente antes do `systemctl restart`).
- SSH root na VPS nova exigia senha (chave `saleia_vps` parou de funcionar) — acesso restabelecido com senha fornecida pelo usuario.
- `git fetch origin main` mostrou que o cache local de `origin/main` na VPS estava atrasado (ainda via `f23b8e0`); `git pull origin main` trouxe o fast-forward para `13f74f4` (bump de versao 1.4.43 -> 1.4.44).
- **Achado durante o `pip install -r requirements.txt`**: o resolvedor bateu em `error: resolution-too-deep` e instalou um ambiente inconsistente — `mcp` (trazido por `claude-agent-sdk`) exige `starlette>=0.48` no Python 3.14 (`sse-starlette` exige `>=0.49.1`), incompativel com o range `starlette<0.38.0,>=0.37.2` exigido por `fastapi==0.111.0`. Pip instalou `starlette 1.6.0` (quebraria o FastAPI, nucleo de toda a API, no proximo restart).
  - Corrigido removendo o pino exato de `fastapi==0.111.0`/`uvicorn[standard]==0.30.1` para `>=0.111.0`/`>=0.30.1` em `requirements.txt` (commit `249fd9a`) — ao rodar `pip install` de novo com o grafo completo (nao isolado), o resolvedor achou uma solucao consistente por conta propria: manteve `fastapi==0.111.0` e baixou `mcp` de `2.0.0` para `1.27.2` (compativel com `starlette==0.37.2`). `pip check`: "No broken requirements found."
  - Validado antes do restart: `import claude_agent_sdk`, `import agent.claude_account` e `import api.main` (com `PYTHONPATH=/opt/saleia`) — todos OK, sem excecao.
- `claude --version` = `2.1.239 (Claude Code)` confirmado funcional (o aviso de `allow-scripts` do npm nao impediu o binario de funcionar).
- `systemctl restart saleia`: servico `active`; `journalctl -u saleia` sem excecoes, todas as tabelas (incluindo as novas `ClaudeConnection`/`ClaudeMeetingAnalysis`) verificadas/criadas no startup.
- Pos-deploy: `/health` retornou `versao: 1.4.44`, 4 provedores `status: ok` com `falhas_consecutivas: 0` (restart tambem liberou os FDs vazados da V.1.4.43 — resolve o "URGENTE" anterior); `/dashboard` = `200`; `GET /claude-account/status` sem JWT retornou `401` (feature flag `CLAUDE_ACCOUNT_PILOT` confirmada ativa — endpoint existe e exige auth, nao `404`).
- Aviso pre-existente e sem relacao com este deploy: `OpenTelemetry não configurado: No module named 'opentelemetry.sdk'` no startup — `opentelemetry-sdk` nunca esteve em `requirements.txt` (instalado manualmente fora do pip na epoca da V.1.4.11-13); tratado como falha graciosa pelo proprio codigo, nao derruba o servico.

### Fix pos-deploy: `CLAUDE_TOKEN_ENC_KEY` invalida (22/08/2026)
- Primeiro teste real do "Analisar com Claude" no dashboard (usuario colou
  o proprio token de `claude setup-token`) retornou `HTTP 500`.
- `journalctl -u saleia` apontou a causa exata: `POST /claude-account/connect`
  → `agent/claude_account.py::criptografar_token` → `ValueError: Fernet key
  must be 32 url-safe base64-encoded bytes` — o valor de `CLAUDE_TOKEN_ENC_KEY`
  gravado no `.env` durante o setup da V.1.4.44 (21/08/2026) nao era uma
  chave Fernet valida.
- Corrigido gerando uma nova chave valida (`Fernet.generate_key()`) e
  substituindo a variavel no `.env` da VPS (backup do arquivo original em
  `/opt/saleia/.env.bak_fernet_fix`); `systemctl restart saleia` aplicado.
  Nenhum dado orfao: como a criptografia falhava antes de qualquer escrita
  no banco, nenhuma `ClaudeConnection` chegou a ser persistida com a chave
  antiga.
- **Pendente**: usuario precisa tentar conectar de novo pelo dashboard para
  confirmar que o fluxo completo funciona ponta a ponta agora.

## O Que Falta

- Reinstalar extensao Chrome (mudanças desde V.1.4.40). *(tarefa manual)*
- Descomissionar VPS antiga (`204.168.180.25`).
- Alterar senha do admin via dashboard.
- **Reindex de embeddings pendente**: rodar `python -m scripts.reindex_embeddings --dry-run --table all` (conferir) e depois sem `--dry-run` (a base atual tem embeddings antigos gerados pela OpenAI, incompativeis com o Ollama).
- **URGENTE — Todos os 4 provedores de IA centrais sem saldo (22/08/2026)**: primeiro teste real de `POST /recapitulacao-manual` apos o deploy da V.1.4.44 falhou nos 4 provedores simultaneamente — nao e bug de codigo, e financeiro:
  - `deepseek`: `APIStatusError 402 Insufficient Balance`.
  - `openai`: `RateLimitError 429 insufficient_quota` — "You have no credits remaining".
  - `anthropic`: `BadRequestError 400` — "Your credit balance is too low to access the Anthropic API".
  - `gemini`: `PermissionDenied 403 Lightning dunning decision is deny for project: projects/493614671182` — conta de faturamento do Google Cloud inadimplente/suspensa (mesmo problema ja documentado, ainda nao resolvido).
  - Resolver adicionando credito/saldo nos paineis do DeepSeek, OpenAI e Anthropic, e regularizando o faturamento no Google Cloud Console. Ate isso ser feito, nenhuma analise de reuniao (recapitulacao manual, tempo real, ou piloto Claude Account) funciona.
  - Achado: `/health` continua reportando os 4 provedores como `status: ok` / `falhas_consecutivas: 0` mesmo apos essa falha real — o contador de falhas do `/health` nao esta sendo incrementado pelo caminho de `/recapitulacao-manual` (investigar separadamente, fora do escopo desta rodada; `/health` nao pode ser usado como sinal confiavel de que os provedores tem saldo).
- Testar Visual Cenario AI em producao (DALL-E 3 + OpenAI) continua pendente — agora so acessivel por URL direta (`/visual-scenario?meeting=<id>`), sem botao/menu (removido na V.1.4.42).
- **Conectar** via `claude setup-token` confirmado funcionando em producao (22/08/2026, `POST /claude-account/connect` = 200 OK). **Disparar analise (`POST /claude-account/analisar`) e checar os 7 blocos ainda nao foi validado** ponta a ponta — usuario tentou usar o piloto pela tela errada (Analisar Transcricao, que ainda usa os provedores centrais) antes da V.1.4.45 existir; falta confirmar o fluxo completo agora que ha um botao dedicado nas duas telas (detalhe de sessao E Analisar Transcricao).
- 8 falhas de teste pre-existentes e nao relacionadas encontradas em `tests/test_next_best_question.py`/`tests/test_realtime_memory.py` (nao corrigidas — fora do escopo desta rodada).
- **Decisoes tomadas sobre as 4 lacunas remanescentes da V.1.4.40 (20/08/2026)**:
  - Download da Base sem isolamento por empresa/tenant: **aceito como esta** — SALEIA e uso interno de uma unica empresa, multi-tenancy nao se aplica. `GET /base/{id}/download` continua exigindo so JWT valido.
  - Sessoes ao Vivo so com status "Ao vivo"/"Finalizada": **aceito como esta** — nao inventar "Processando"/"Erro" sem sinal real no banco continua sendo a decisao correta.
  - Codigo morto de Visual Cenario/Mapa Financeiro/Score/Cenario do Cliente: **auditado, nada para remover** — a limpeza da V.1.4.40 ja foi completa (nenhum handler orfao encontrado); o que parecia candidato a remocao (backend de mapa financeiro, score_compra, resumo do cliente, Visual Cenario) esta ativamente em uso por outras partes do sistema.
  - Testes automatizados: **parcialmente feito** — `tests/test_base_download.py` (7 testes) e `tests/test_propensao_rules.py` (7 testes) cobrem download da Base e classificacao de propensao. Testes de UI/JS (toggle da extensao, busca de sessoes, responsividade) ficam de fora por decisao — projeto nao tem infra de teste JS (Jest/jsdom) e o custo de introduzi-la agora nao foi considerado necessario.

## Deploy V.1.4.39 Confirmado (19/08/2026)

- `reunioes_ativas: 0` checado em `/health` antes de agir (deploy havia sido adiado em 17/08/2026 por reuniao ativa).
- `git pull origin main` na VPS nova: fast-forward `670ad5a..85dd554` (trouxe fix nao documentado do Anthropic em `api/ai_router.py`).
- `systemctl restart saleia` — servico `active`; `/health` = `versao 1.4.39`, 4 provedores `status: ok`; `/dashboard` = `200`.
- Achado: o commit trazido pelo pull corrigia `_call_anthropic` para nao assumir `content[0]` como bloco de texto — isso resolveu os 138 `falhas_consecutivas` do provedor Anthropic que estavam visiveis em producao antes do restart.

## Ollama instalado na VPS nova (17/08/2026)

- `ollama.service` — `active` + `enabled` (sobrevive a reboot).
- Modelo `embeddinggemma` baixado (621 MB) e testado — **dimensao real confirmada: 768**.
- Escuta apenas em `127.0.0.1:11434` (nao exposto externamente).
- CPU-only (sem GPU na VPS); ~4.3GB RAM disponivel no momento do teste; 134GB de disco livre.
- Instalado via script oficial (`curl -fsSL https://ollama.com/install.sh | sh`), sem afetar `saleia.service` (servicos independentes).

## Deploy V.1.4.38 Confirmado (16/08/2026)

- Verificado via SSH que `/opt/saleia` ja estava no commit `555b990` (igual ao GitHub `origin/main`) — deploy ja havia ocorrido antes da doc ser atualizada.
- `systemctl restart saleia` executado; servico `active`.
- `curl http://127.0.0.1:8000/health` retornou `"versao":"1.4.38"`, banco MySQL com `banco_latencia_ms: 1`, 4 provedores IA configurados (`ok`).
- `curl http://127.0.0.1:8000/dashboard` retornou `200`.

## Bugs Corrigidos em V.1.4.38 (16/06/2026)

- Connection leak em `enriquecer_perfil_apos_relatorio` (client_intelligence.py)
- Dead code: funcao `processar_fragmento_tempo_real` legada removida (processador_tempo_real.py)
- Sales Memory agora injetada no orquestrador multiagente — memorias comerciais passam a enriquecer analise em tempo real (orquestrador.py)
- `mapa_financeiro` restaurado do banco ao trocar de worker uvicorn (processador_tempo_real.py)
- `AsyncOpenAI` singleton — nao recriado a cada chamada RAG (base_conhecimento.py)
- `MAX(score)` desnecessario removido do SELECT em `_recalcular_stats` (client_intelligence.py)

## Infraestrutura (V.1.4.17 — 09/06/2026)

- VPS dedicada CPX32 provisionada na Hetzner Helsinki (`37.27.214.33`).
- MySQL migrado de servidor remoto compartilhado (`177.104.186.227`, 676ms) para instancia local (`127.0.0.1`, ~2ms) — reducao de 338x na latencia do banco.
- Novo dominio `saleia.app.br` criado no Registro.br + delegado ao Cloudflare (nuvem laranja).
- Deploy via `git clone https://github.com/fasterdrible-lab/SALE-IA.git /opt/saleia` + venv Python 3.14 + systemd com `TimeoutStopSec=30`.
- nginx configurado para `api.saleia.app.br` com proxy reverso para `127.0.0.1:8000`.
- Dados migrados: tabelas `admin_route_rules`, `alertas_automaticos`, `api_integrations`, `audit_logs`, `base_conhecimento` (49 docs RAG) preservadas.
- Tabelas auto-criadas no startup: `relatorio`, `meeting_memory`, `sessoes`, `usuarios`, `visual_scenarios`.

## Concluido (T12 - V.1.4.2)

- `GET /relatorios` agora retorna campo `provedor` extraido de `_provedor_ia` dentro de `dados.recapitulacao` (ou `perfil_disc`/`diagnostico_financeiro` como fallback). Funciona tanto para fonte SQLite quanto para arquivos JSON.
- Dashboard: `<select id="filtro-provedor">` adicionado ao toolbar de Reunioes com opcoes DeepSeek, OpenAI, Anthropic, Gemini.
- `filtrarReunioes` filtra por provedor via `r.provedor`.
- `limparFiltrosReunioes` reseta o select de provedor.
- Card de reuniao exibe nome do provedor como label discreta ao lado da data/score.

## Observabilidade (V.1.4.11–V.1.4.13)

- Contadores IA em memória com lock thread-safe (`api/ai_router.py`)
- Aba Monitor no dashboard com cards de métricas e sparklines 6h
- SQLite rolling 24h em `data/metricas.db` + alertas Telegram por threshold
- OpenTelemetry SDK integrado ao Grafana Cloud Tempo (OTLP/HTTP)
  - Stack Grafana Cloud: `slimturtle2775` — região `sa-east-1`
  - Datasource Tempo: `grafanacloud-slimturtle2775-traces`
  - Traces de todas as rotas FastAPI chegando em tempo real
- Global fetch interceptor no dashboard.html injeta JWT automaticamente

## Estado dos Provedores (V.1.4.15)

Ordem ativa (ai_provider_order.json na VPS):

1. `deepseek` — PRINCIPAL ✅ Online
2. `openai` — ✅ Online (+ RAG embeddings text-embedding-3-small)
3. `anthropic` — ❌ Sem créditos (chave válida, saldo zerado)
4. `gemini` — modelo `gemini-2.5-flash` (atualizado de gemini-2.0-flash)

RAG: 49 transcrições indexadas, embeddings 1536 dimensões funcionando.

### Transcricao de Audio (V.1.4.5)

- SDK oficial `groq>=0.9.0` instalado na VPS; modelo `whisper-large-v3`
- Endpoint `POST /admin/transcricao/config` aceita `apenas_salvar: true` para salvar chave sem mudar provedor
- Dashboard: botao 👁 para mostrar/ocultar chave Groq; `salvarChaveGroq` usa `fetchJsonWithFallback`
- Extensao Chrome exibe erros de transcricao na barra de status da sidebar

### Redesign Visual Gold/Black (V.1.4.6)

- Paleta premium aplicada em toda a plataforma: dourado metalico `#D4AF37`, preto absoluto `#000000`
- `dashboard.html`: variaveis CSS atualizadas, sidebar preta, botoes e badges dourados, tipografia Inter+Sora
- `login.html`: logo SALEIA PNG premium integrado via Nginx static location
- `frontend/logo-saleia.png`: novo arquivo de logo adicionado

### Visual Cenario e Navegacao (V.1.4.7)

- `visual-scenario.html`: paleta gold/black; titulo renomeado para "Visual Cenario AI"
- `dashboard.html`: item de menu "Visual Scenario" → "Visual Cenario"

### Multi-clientes, Botao Inicio e Extensao Chrome (V.1.4.8)

- `dashboard.html`: campo "Cliente" substituido por lista dinamica — botao `+ Cliente`, botao remove (min 1)
- `visual-scenario.html`: botao "← Inicio" volta para `/cenario/{meeting_id}` em vez de `/`
- `cenario.html`: paleta gold/black completa
- Extensao Chrome: popup.css, sidebar.css, content.css redesenhados em ouro/preto
- `content.js`: modal Participantes com lista de clientes dinamica (event delegation), migracao de dados antigos

### Manual Atualizado (V.1.4.9)

- `frontend/manual.html`: reescrito de V.1.4.5 para V.1.4.8 — secoes 7 (Cenario do Cliente), 8 (Visual Cenario AI), nav sticky e botoes de acoes rapidas

### UX do Dashboard — Chaves API e Status de Conexão (V.1.4.10)

- Campos de chave dos 4 provedores: `autocomplete="new-password"` bloqueia preenchimento automático do Chrome; botão 👁 (função `toggleVerChave`) alterna visibilidade
- Botão "Testar conexão": badge `✅ Online` ou `❌ Offline` permanece visível no cabeçalho do card após o teste (não desaparece mais com timeout)

## Problemas Conhecidos

Nenhum problema crítico pendente.

## Cuidados

- Nunca expor `.env`, tokens ou chaves em logs, frontend ou documentacao.
- Nao analisar a arvore duplicada fora de `SALEIA/` sem pedido explicito.
- Preservar compatibilidade com o fluxo atual da extensao Chrome.
- Alterar somente arquivos da tarefa em andamento.
