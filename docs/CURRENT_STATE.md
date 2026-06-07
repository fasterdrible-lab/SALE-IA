# SALEIA - Estado Atual

Atualizado em: 2026-06-07

## Ambiente

- Pasta canonica local: `C:\Users\phpos\OneDrive\SALE-IA\SALEIA`
- Dominio de producao: `https://api.saleia.com.br`
- Dashboard: `https://api.saleia.com.br/dashboard`
- Backend de producao: FastAPI via `saleia.service`
- Porta interna na VPS: `127.0.0.1:8000`
- Proxy publico: nginx em `80/443`
- Banco em producao: MySQL

## Deploy

- VPS: `204.168.180.25`
- App na VPS: `/opt/saleia`
- Servico: `saleia.service`
- Health publico validado: `https://api.saleia.com.br/health`
- Nao sobrescrever em deploy: `.env`, `venv`, `data`, `logs`
- Apos deploy: reiniciar com `systemctl restart saleia`

## Versao Atual

`V.1.4.13` — registrada no CHANGELOG.md

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

## O Que Falta

- Reinstalar extensao Chrome no navegador (novo tema gold/black + multi-clientes — V.1.4.8).
- Testar Visual Cenario AI em producao com creditos OpenAI ativos.
- Sem tarefas criticas pendentes.

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

## Proxima Tarefa Recomendada

**T18 — Deploy V.1.4.3–V.1.4.9 na VPS** via SCP com chave `saleia_vps`.

Arquivos a enviar:

| Arquivo | Versao | Motivo |
|---|---|---|
| `api/main.py` | V.1.4.3+ | correcoes de bugs e endpoints novos |
| `agent/sessao_manager.py` | V.1.4.3 | fix exportar_para_base_conhecimento |
| `requirements.txt` | V.1.4.5 | groq>=0.9.0 |
| `frontend/dashboard.html` | V.1.4.8 | multi-clientes + redesign gold |
| `frontend/visual-scenario.html` | V.1.4.8 | botao Inicio corrigido + paleta gold |
| `frontend/cenario.html` | V.1.4.8 | paleta gold/black |
| `frontend/login.html` | V.1.4.6 | logo integrado |
| `frontend/logo-saleia.png` | V.1.4.6 | **novo arquivo** |
| `frontend/manual.html` | V.1.4.9 | manual V.1.4.8 completo |
| `chrome-extension/background.js` | V.1.4.1 | bug de foto corrigido |
| `chrome-extension/manifest.json` | V.1.4.8 | versao atualizada |
| `chrome-extension/popup.html` | V.1.4.8 | redesign gold |
| `chrome-extension/popup.js` | V.1.4.1 | versao dinamica |
| `chrome-extension/popup.css` | V.1.4.8 | paleta gold/black |
| `chrome-extension/sidebar.css` | V.1.4.8 | paleta gold/black |
| `chrome-extension/content.css` | V.1.4.8 | paleta gold/black |
| `chrome-extension/content.js` | V.1.4.8 | multi-clientes |

Apos upload:
```bash
pip install -r requirements.txt && systemctl restart saleia && curl https://api.saleia.com.br/health
```

Adicionar ao Nginx (`/etc/nginx/sites-enabled/saleia`):
```nginx
location = /logo-saleia.png {
    alias /opt/saleia/frontend/logo-saleia.png;
    add_header Cache-Control "public, max-age=2592000";
}
```

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

Nenhum problema critico pendente.

## Cuidados

- Nunca expor `.env`, tokens ou chaves em logs, frontend ou documentacao.
- Nao analisar a arvore duplicada fora de `SALEIA/` sem pedido explicito.
- Preservar compatibilidade com o fluxo atual da extensao Chrome.
- Alterar somente arquivos da tarefa em andamento.
