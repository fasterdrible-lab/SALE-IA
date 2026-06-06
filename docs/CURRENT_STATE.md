# SALEIA - Estado Atual

Atualizado em: 2026-05-29

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

`V.1.4.5` — registrada no CHANGELOG.md

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

- Deploy da V.1.4.1 na VPS (SFTP + restart do servico).
- Configurar variaveis SMTP no `.env` da VPS para ativar envio real de e-mail de recuperacao.
- Testar Visual Scenario em producao com creditos OpenAI ativos.
- Reinstalar extensao Chrome no navegador (apos deploy) para aplicar correcao do bug de foto.
- Sem tarefas pendentes criticas. Proxima sugestao: reinstalar extensao Chrome com a correcao do bug de foto (V.1.4.1).

## Concluido (T12 - V.1.4.2)

- `GET /relatorios` agora retorna campo `provedor` extraido de `_provedor_ia` dentro de `dados.recapitulacao` (ou `perfil_disc`/`diagnostico_financeiro` como fallback). Funciona tanto para fonte SQLite quanto para arquivos JSON.
- Dashboard: `<select id="filtro-provedor">` adicionado ao toolbar de Reunioes com opcoes DeepSeek, OpenAI, Anthropic, Gemini.
- `filtrarReunioes` filtra por provedor via `r.provedor`.
- `limparFiltrosReunioes` reseta o select de provedor.
- Card de reuniao exibe nome do provedor como label discreta ao lado da data/score.

## Proxima Tarefa Recomendada

Deploy V.1.4.1 via SFTP. Arquivos a enviar:

| Arquivo | Motivo |
|---|---|
| `api/main.py` | recuperar-senha real, /reset, /redefinir-senha |
| `agent/sessao_manager.py` | migrar_colunas_usuarios() |
| `agent/email_service.py` | **novo arquivo** — deve ser criado na VPS |
| `.env.example` | referencia para vars SMTP |
| `chrome-extension/background.js` | correcao do bug de foto |
| `chrome-extension/manifest.json` | versao atualizada |
| `chrome-extension/popup.html` | versao atualizada |
| `chrome-extension/popup.js` | versao dinamica |

Apos upload: `pip install -r requirements.txt && systemctl restart saleia && curl https://api.saleia.com.br/health`

Tambem adicionar ao `.env` da VPS:
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASS=...
EMAIL_FROM=noreply@saleia.com.br
APP_BASE_URL=https://api.saleia.com.br
```

### Transcricao de Audio (V.1.4.5)

- SDK oficial `groq>=0.9.0` instalado na VPS; modelo `whisper-large-v3`
- Endpoint `POST /admin/transcricao/config` aceita `apenas_salvar: true` para salvar chave sem mudar provedor
- Dashboard: botao 👁 para mostrar/ocultar chave Groq; `salvarChaveGroq` usa `fetchJsonWithFallback`
- Extensao Chrome exibe erros de transcricao na barra de status da sidebar

## Problemas Conhecidos

Nenhum problema critico pendente.

## Cuidados

- Nunca expor `.env`, tokens ou chaves em logs, frontend ou documentacao.
- Nao analisar a arvore duplicada fora de `SALEIA/` sem pedido explicito.
- Preservar compatibilidade com o fluxo atual da extensao Chrome.
- Alterar somente arquivos da tarefa em andamento.
