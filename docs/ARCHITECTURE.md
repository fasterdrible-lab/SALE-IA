# SALEIA - Arquitetura

## Visao Geral

O SALEIA monitora reunioes de vendas, captura transcricoes, orienta o vendedor em tempo real e gera relatorios de diagnostico e recapitulação. A arquitetura mantém a logica de negocio e as chaves de IA no backend; o frontend apenas envia dados e exibe respostas.

## Componentes

### Chrome Extension

- Captura legendas/transcricao do Google Meet.
- Envia trechos novos para o backend.
- Exibe dicas, alertas, proxima pergunta, acoes recomendadas, recapitulacao viva e propensao de compra (Alta/Media/Baixa/Nao determinada) na sidebar.
- Toggle "API ativa/desligada" (V.1.4.40): usuario pode pausar todo envio de dados ao backend sem encerrar a reuniao; estado persiste em `chrome.storage.local`.
- Nao possui chaves de IA.
- Nao exibe informacoes tecnicas/administrativas (URL do backend, nome/modelo de provedor de IA, score numerico) — ficam restritas ao Dashboard.

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
- `POST /base` (multipart desde V.1.4.40 — texto + arquivo original opcional)
- `GET /base/{id}/download` (V.1.4.40, exige JWT — base é global, sem tenant)
- `DELETE /base/{id}` (apaga tambem o arquivo em disco, se houver)
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

### Propensão de Compra (agent/propensao_rules.py, V.1.4.40)

Classificação qualitativa (Alta/Média/Baixa/Não determinada) que substitui o
score numérico de compra na extensão Chrome.

- `classificar_propensao(score_valor)`: função pura e determinística — único
  lugar com os limiares (`LIMIAR_ALTA=70`, `LIMIAR_MEDIA=45`).
- Usada em `agent/multiagente/orquestrador.py::_mesclar`, logo após o
  `score_compra` do Closer — adiciona `resultado["propensao"] = {"nivel": ...}`
  ao JSON de `POST /tempo-real` sem nenhuma chamada de IA extra por
  fragmento (`score_compra` continua calculado e persistido normalmente,
  só deixa de ser exibido como número).
- Para o detalhamento pós-reunião (fatores, evidências, o que falta para
  avançar), `PROMPT_RECAPITULACAO` (`api/main.py`) retorna um bloco
  `propensao` mais rico (com `confianca`, `resumo`, `fatores_positivos`,
  `fatores_negativos`, `fatores_pendentes`, `como_avancar`), consumido pelo
  Dashboard em `verDetalhe()` — gerado uma única vez por recapitulação e
  nunca regenerado ao abrir o relatório.

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

- Ver relatorios, com propensao de compra e detalhamento expansivel (fatores, evidencias, o que falta avancar).
- Ver sessoes ao vivo, com busca por cliente/empresa/link/data/hora, filtros de status e ordenacao (V.1.4.40).
- Colar transcricao manual para analise.
- Gerenciar Base de Conhecimento, incluindo baixar o arquivo original de um documento (V.1.4.40).
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
