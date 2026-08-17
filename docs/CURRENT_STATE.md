# SALEIA - Estado Atual

Atualizado em: 2026-08-17 (V.1.4.39)

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

`V.1.4.39` — local + GitHub (pendente deploy VPS) | VPS antiga (`204.168.180.25`) deprecada

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

## O Que Falta

- Reinstalar extensao Chrome (mudanças desde V.1.4.28). *(tarefa manual)*
- Descomissionar VPS antiga (`204.168.180.25`).
- Alterar senha do admin via dashboard.
- Corrigir remote `origin` do git em `/opt/saleia` na VPS nova — URL atual contem placeholder invalido `https://SEU_TOKEN@github.com`, impedindo `git pull` funcional (necessario token real do GitHub).
- **Deploy V.1.4.39 pendente**: `cd /opt/saleia && git pull origin main && systemctl restart saleia`. Adiado propositalmente em 17/08/2026 porque havia 1 reuniao ativa no SALEIA no momento — reiniciar o servico a interromperia. Fazer o deploy na proxima janela sem reunioes ativas (checar `reunioes_ativas` em `/health` antes).
- Apos o deploy: rodar `python -m scripts.reindex_embeddings --dry-run --table all` (conferir) e depois sem `--dry-run` (a base atual tem embeddings antigos gerados pela OpenAI, incompativeis com o Ollama).

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
