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

Autenticacao (V.1.3.5+):

- `POST /auth/login`
- `POST /auth/cadastro`
- `POST /auth/recuperar-senha` (stub — sem envio real de e-mail)

Admin (exige JWT admin):

- `GET /admin/usuarios`
- `PATCH /admin/usuarios/{uid}/perfil|plano|status|inativar|reativar|resetar-senha`
- `DELETE /admin/usuarios/{uid}`
- `GET /admin/api/provedores`
- `POST /admin/api/provedores/{pid}/chave`
- `POST /admin/api/teste`
- `PATCH /admin/api/provedores/{pid}/status`
- `POST /admin/api/principal`
- `GET /admin/embeddings/status` (V.1.4.39) — status do provedor de embeddings ativo, dimensao, contagem de documentos/memorias indexados

Historico (exige JWT):

- `GET /historico/uso`
- `GET /historico/uso/{meeting_id}`

Cenario / Conducao (exige JWT):

- `POST /cenario/{meeting_id}/conducao`
- `POST /generate-visual-scenario`

Base de Conhecimento:

- `GET /base`
- `POST /base`
- `DELETE /base/{id}`
- `POST /base/ocr`

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

### Embeddings (services/embeddings/, V.1.4.39)

Camada desacoplada de geração de embeddings para RAG e Sales Memory —
independente do AI Router (que trata apenas chat/LLM).

- `EmbeddingProvider`: interface comum (`embed`, `embed_async`, `embed_batch`, `health_check`).
- `OllamaEmbeddingProvider`: local via `httpx`, padrão (`EMBEDDING_PROVIDER=ollama`).
- `OpenAIEmbeddingProvider`: opcional (`EMBEDDING_PROVIDER=openai`).
- `get_embedding_provider()`: única forma de obter o provider — nenhum módulo de negócio instancia um provider diretamente.
- Metadados (`embedding_provider`, `embedding_model`, `embedding_dim`) em `base_conhecimento` e `sales_memories` garantem que vetores de dimensões/modelos diferentes nunca sejam comparados entre si.
- Reindexação: `scripts/reindex_embeddings.py`.

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
