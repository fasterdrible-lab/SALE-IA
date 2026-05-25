# SALEIA - Arquitetura

## Visao Geral

O SALEIA monitora reunioes de vendas, captura transcricoes, orienta o vendedor em tempo real e gera relatorios de diagnostico e recapitulação. A arquitetura mantém a logica de negocio e as chaves de IA no backend; o frontend apenas envia dados e exibe respostas.

## Componentes

### Chrome Extension

- Captura legendas/transcricao do Google Meet.
- Envia trechos novos para o backend.
- Exibe dicas, alertas, proxima pergunta, acoes recomendadas e recapitulacao viva na sidebar.
- Nao possui chaves de IA.

### Backend FastAPI

Responsabilidades:

- Receber transcricao em tempo real.
- Persistir memoria da reuniao.
- Orquestrar chamadas de IA.
- Controlar fallback entre provedores.
- Servir dashboard e endpoints de relatorio.
- Sanitizar erros e proteger segredos.

Rotas principais:

- `GET /health`
- `GET /dashboard`
- `POST /tempo-real`
- `POST /recapitulacao-manual`
- `POST /recapitulacao-viva`
- `GET /relatorios`
- `GET /sessoes`
- `POST /ai/provedor/preferido`

### Meeting Memory

Memoria persistida por `meeting_id`.

Campos principais:

- `transcript_full`
- `transcript_buffer`
- `accumulated_summary`
- `current_diagnosis`
- `score_history`
- `key_moments`
- `events`
- `last_ai_at`
- `last_recap_trigger_at`
- `provider_cost_estimate`

### AI Router

O roteador de IA fica no backend e decide qual provedor usar.

Ordem padrao:

1. `deepseek`
2. `openai`
3. `anthropic`
4. `gemini`

Regras:

- Se o provedor preferido falhar, tenta o proximo.
- Se nao houver chave, ignora o provedor.
- Se houver falhas repetidas, aplica cooldown.
- Respostas devem ser JSON estruturado.
- Erros devem ser sanitizados antes de retornar ao frontend.

### Banco de Dados

Producao usa MySQL. Local pode cair para SQLite se MySQL estiver indisponivel.

Tabelas relevantes:

- Relatorios
- MeetingMemory
- Sessoes/transcricoes acumuladas

### Dashboard

O dashboard web permite:

- Ver relatorios.
- Ver sessoes ao vivo.
- Colar transcricao manual para analise.
- Configurar URL da API.
- Visualizar status basico do backend.

## Seguranca

- Segredos ficam apenas no `.env` do backend.
- Frontend nao recebe chaves.
- Logs e respostas de erro devem redigir tokens.
- Deploy deve preservar `.env` de producao.
- Transcricao completa nao deve ser enviada em tempo real para IA.

## Deploy

O deploy de producao atual usa:

- `/opt/saleia`
- `saleia.service`
- `uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 2`
- nginx como reverse proxy para `api.saleia.com.br`

Durante deploy:

- Nao sobrescrever `.env`.
- Nao apagar `data`.
- Nao apagar `logs`.
- Reiniciar `saleia.service`.
- Validar `/health` e `/dashboard`.
