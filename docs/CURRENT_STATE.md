# SALEIA - Estado Atual

Atualizado em: 2026-05-28

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

`V.1.4.0` — registrada no CHANGELOG.md

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

- Smoke tests: 8/8 OK em 1.1s (`python -m unittest tests.test_smoke -v`).
- `/health` publico respondeu `online`.
- `/dashboard` publico respondeu `200`.
- `/recapitulacao-manual` retornou `200` em producao apos correcoes de fallback.

## O Que Falta

- Deploy da V.1.4.0 na VPS (SFTP dos arquivos alterados + restart do servico).
- Testar Visual Scenario em producao com creditos OpenAI ativos.
- `/auth/recuperar-senha` e stub — envio de email nao implementado (requer SMTP).
- Filtro por provedor em Reunioes (campo ausente no response de `/relatorios`; requer ajuste de backend).

## Proxima Tarefa Recomendada

- Deploy V.1.4.0 via SFTP para a VPS.
- Apos deploy, testar Visual Scenario ao vivo em uma reuniao real.

## Problemas Conhecidos

- `PATCH /admin/api/provedores/{pid}/status` com `ativo=False` nao propaga desativacao ao `ai_router` (design atual).
- `base_conhecimento` usa coluna `conteudo` na criacao inline mas `texto` nas queries do `/base` — inconsistencia de schema a corrigir.

## Cuidados

- Nunca expor `.env`, tokens ou chaves em logs, frontend ou documentacao.
- Nao analisar a arvore duplicada fora de `SALEIA/` sem pedido explicito.
- Preservar compatibilidade com o fluxo atual da extensao Chrome.
- Alterar somente arquivos da tarefa em andamento.
