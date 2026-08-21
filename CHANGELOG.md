# CHANGELOG — SALEIA
> Registro de todas as implementações, correções e melhorias por versão.

---

## V.1.4.43 — Fix crítico: vazamento de file descriptors nos clientes de IA
> Data: 21/08/2026 | Bug fix (produção)

### INCIDENTE
Todos os 4 provedores de IA apareciam como "degradado" em `/health` em
produção, com contadores de falhas consecutivas subindo continuamente
mesmo sem tráfego novo sendo gerado. Investigação via SSH (`journalctl -u
saleia`) revelou dois problemas distintos:

1. **Gemini**: `PermissionDenied: 403 Lightning dunning decision is deny
   for project: projects/493614671182` — a conta de faturamento do Google
   Cloud do projeto está inadimplente/suspensa. **Não é bug de código —
   requer ação humana no Google Cloud Console** (forma de pagamento/fatura).
2. **DeepSeek/OpenAI/Anthropic**: `OSError: [Errno 24] Too many open
   files` — o servidor esgotou o limite de file descriptors do SO. Causa
   raiz: `_call_openai`, `_call_deepseek` e `_call_anthropic`
   (`api/ai_router.py`) criavam um cliente HTTP novo a cada chamada de IA
   sem nunca fechá-lo (nem `client.close()`, nem `with`) — o fechamento
   ficava a cargo do garbage collector, que falhava silenciosamente sob
   carga (`Exception ignored while calling deallocator
   SyncHttpxClientWrapper.__del__`), vazando sockets/FDs a cada fragmento
   de reunião em tempo real. O lote de migração de 74 reuniões históricas
   (rodado nesta mesma data) acelerou drasticamente o esgotamento por
   gerar um volume grande de chamadas de IA em pouco tempo.

### CORREÇÃO — clientes de IA fechados deterministicamente
Mesma classe de bug já corrigida uma vez para o RAG (V.1.4.38, bug #5:
`AsyncOpenAI` recriado a cada chamada) — dessa vez no caminho de chat/LLM
e em mais alguns pontos que nunca tinham sido auditados. Todos os pontos
que criam um cliente `OpenAI`/`AsyncOpenAI`/`Anthropic`/`AsyncAnthropic`
por chamada agora usam `with`/`async with` para garantir o fechamento do
pool de conexões, mesmo em erro:
- `api/ai_router.py`: `_call_openai`, `_call_deepseek`, `_call_anthropic`
  (os 3 usados em toda chamada de tempo real e recapitulação — a fonte
  principal do vazamento)
- `api/main.py`: transcrição Whisper (`OpenAI`), OCR com fallback
  Anthropic→OpenAI (`AsyncAnthropic`/`AsyncOpenAI`), teste de conexão de
  provedor no painel admin (`AsyncOpenAI`/`AsyncAnthropic` para os 3
  provedores)
- `agent/visual_scenario.py`: geração de imagem DALL-E 3 (`OpenAI`)
- `services/embeddings/openai_provider.py`: `embed`, `embed_async`,
  `embed_batch` (só ativo se `EMBEDDING_PROVIDER=openai`; o padrão
  `ollama` já usava `async with httpx.AsyncClient()` corretamente — não
  contribuía para o incidente)

### NÃO CORRIGIDO NESTA RODADA
- Faturamento do Gemini no Google Cloud (ação humana, fora do código).
- Árvore duplicada `SALEIA/SALEIA/` (fora do escopo — CLAUDE.md pede para
  não analisar essa pasta).

### TESTES
- 3 testes de `tests/test_ai_router.py` e `tests/test_embeddings.py`
  quebraram porque os mocks (`fake_client`/`MagicMock`) não implementavam
  o protocolo de context manager (`__enter__`/`__exit__` /
  `__aenter__`/`__aexit__`) — corrigidos para configurar o retorno do
  `__enter__`/`__aenter__` como o próprio mock configurado, em vez de
  deixar o mock auto-gerar um objeto novo e não configurado.
- `python -m unittest tests.test_smoke tests.test_propensao_rules
  tests.test_base_download tests.test_ai_router tests.test_embeddings`:
  65/65 OK.

### DEPLOY
Restart do `saleia.service` necessário após o deploy — o fix impede
*novos* vazamentos, mas não libera os file descriptors já vazados no
processo atualmente rodando.

### ARQUIVOS ALTERADOS
- `api/ai_router.py`, `api/main.py` (3 pontos + versão),
  `agent/visual_scenario.py`, `services/embeddings/openai_provider.py`,
  `tests/test_ai_router.py`, `tests/test_embeddings.py`

---

## Migração de reuniões históricas (Google Drive → Sales Memory)
> Data: 20/08/2026 | Utilitário / dados (não é versão de produto — sem bump de versão)

### VISÃO
Usuário tinha uma base de ~74 reuniões antigas exportadas do Google Meet
(notas do Gemini em `.docx`, com resumo + transcrição verbatim completa)
guardada no Google Drive, sem estar alimentando o Sales Memory do SALEIA.

### NOVO — `scripts/migrar_reunioes_historico.py`
- Processa uma pasta de arquivos `.txt`/`.docx` (1 reunião por arquivo)
  chamando `POST /recapitulacao-manual` (local ou remoto) — reaproveita
  100% do pipeline existente, sem duplicar lógica de negócio: gera
  relatório completo (recapitulação + DISC + diagnóstico financeiro +
  propensão) e dispara a extração de Sales Memory (e Playbook automático
  em reuniões "ganhas") em background, como qualquer reunião analisada
  manualmente no dashboard.
- Leitura de `.docx` sem depender de `python-docx` — extração via
  `zipfile` + `xml` da stdlib (um `.docx` é um zip com `word/document.xml`);
  remove boilerplate fixo do Gemini (aviso de pesquisa, disclaimer de
  transcrição) que não agrega sinal e só consome tokens.
- Idempotente: `meeting_id` estável (hash do nome do arquivo) registrado
  em arquivo de estado local — reexecutar pula o que já deu certo.
- Retry automático (1x, com 30s de espera) em erros 503/504, sob a
  hipótese de o circuit breaker de IA estar em cooldown.

### EXECUÇÃO — 51/74 migradas com sucesso (20/08/2026)
- Rodado contra produção (`api.saleia.app.br`): 51 relatórios + entradas
  de Sales Memory criados a partir de reuniões reais.
- 23 reuniões falharam consistentemente com 503, mesmo após retry —
  DeepSeek/OpenAI/Anthropic entraram em estado degradado durante o lote
  (só Gemini saudável) e as falhas parecem correlacionadas a reuniões
  maiores (média 127k chars nas que falharam vs 99k nas que deram certo,
  sem corte limpo — não é só tamanho, causa raiz não confirmada sem
  acesso a logs da VPS/nginx).
- Estado da migração persistido em `data/migracao_reunioes_estado.json`
  (não commitado — dado de execução local) — permite retomar só as 23
  pendentes numa próxima rodada sem reprocessar as 51 já feitas.
- Pendência documentada em `docs/TASKS.md`.

### ARQUIVOS ALTERADOS
- `scripts/migrar_reunioes_historico.py` (novo)

---

## V.1.4.42 — Visual Cenário removido da navegação visível (dashboard + cenario.html)
> Data: 20/08/2026 | Ajuste (Visual Cenário)

### VISÃO
Revisão de continuidade da V.1.4.40/V.1.4.41: o Visual Cenário havia sido
removido apenas da sidebar da extensão Chrome, mas ainda aparecia como item
de navegação no Dashboard e como botão em `cenario.html`. Decisão do
usuário: remover também esses dois pontos de entrada visíveis — a feature
em si (página, endpoint de geração) continua funcional no backend, só deixa
de ser descoberta por navegação.

### FRONTEND — `frontend/dashboard.html`
- Removido o item de menu `🎬 Visual Cenário` (link para `/visual-scenario`)
  da sidebar de navegação.

### FRONTEND — `frontend/cenario.html`
- Removido o botão `🎬 Visual` (abria `/visual-scenario` em nova aba) e a
  função `abrirVisualScenario()`, que ficou órfã sem o botão.

### O QUE NÃO MUDOU (mantido no backend, de propósito)
- `POST /generate-visual-scenario` (`api/main.py`) — endpoint intocado.
- `frontend/visual-scenario.html` — página continua servida e funcional,
  só não é mais alcançável por um botão/menu; acessível por URL direta
  (`/visual-scenario` ou `/visual-scenario?meeting=<id>`) para quem
  precisar validar manualmente (ver pendência em `TASKS.md`).
- `frontend/manual.html`/`manual_tecnico.html` — documentação da feature
  não foi alterada (a feature continua existindo, só não é mais promovida
  na navegação principal).

### VERSÃO
- Backend: `1.4.41` → `1.4.42` (`/health`, `/monitor/metricas`).

### VERIFICAÇÃO
- Sintaxe verificada (Node `--check`) nos blocos `<script>` de
  `cenario.html` e `dashboard.html`.
- `python -m unittest tests.test_smoke -v`: 8/8 OK (sem regressão).

### ARQUIVOS ALTERADOS
- `frontend/dashboard.html`, `frontend/cenario.html`, `api/main.py` (versão)

---

## V.1.4.41 — Ajustes na Propensão: dimensões nomeadas no prompt + limiares configuráveis
> Data: 20/08/2026 | Fix / Ajuste (Propensão de Compra)

### VISÃO
Revisão da V.1.4.40 contra a especificação original identificou duas lacunas
pequenas e mecânicas (sem decisão de produto pendente) na Propensão de
Compra: o prompt de recapitulação não guiava a IA por dimensões de venda
nomeadas, e os limiares de classificação eram constantes fixas no código.

### BACKEND — `api/main.py` (`PROMPT_RECAPITULACAO`)
- Nova regra no bloco `propensao`: a IA deve avaliar as dimensões Dor,
  Urgência, Orçamento, Autoridade (quem decide), Interesse, Intenção de
  compra, Engajamento, Próximo passo e Objeções — só incluindo como fator
  a dimensão que realmente apareceu na conversa (sem forçar as 9).

### BACKEND — `agent/propensao_rules.py`
- `LIMIAR_ALTA`/`LIMIAR_MEDIA` deixam de ser constantes fixas e passam a
  ler `PROPENSAO_LIMIAR_ALTA`/`PROPENSAO_LIMIAR_MEDIA` do `.env` (via
  `_limiar_env()`, com fallback para os valores padrão 70/45 se a variável
  estiver ausente ou inválida) — continuam sendo o único lugar do código
  com esses limiares, agora sem precisar de deploy para ajustar.
- `.env.example`: nova seção documentando as duas variáveis.

### VERSÃO
- Backend: `1.4.40` → `1.4.41` (`/health`, `/monitor/metricas`).

### TESTES — cobertura das lacunas #49 e #51 do spec original
- `tests/test_base_download.py` (7 testes, novo): `GET /base/{doc_id}/download`
  — exige JWT válido, preserva conteúdo/nome/mime original (PDF e DOCX
  testados), 404 quando o documento não tem arquivo, quando o documento não
  existe e quando o arquivo foi removido do disco. Sem MySQL: `_get_conn` é
  mockado com uma conexão/cursor falsos.
- `tests/test_propensao_rules.py` (7 testes, novo): as 4 faixas de
  classificação (incluindo limites inclusivos), score ausente/inválido,
  limiares padrão e limiares configuráveis via `.env` (incluindo fallback
  em valor inválido).
- Auditoria de código morto (Visual Cenário/Mapa Financeiro/Score/Cenário do
  Cliente): nenhum resquício órfão encontrado — a limpeza da V.1.4.40 já
  removeu handlers junto com a UI; o backend relacionado que ainda existe
  está em uso ativo por outras partes do sistema.
- Testes de UI/JS (toggle da extensão, busca de sessões, responsividade)
  ficam fora do escopo — projeto não tem infraestrutura de teste JS
  (Jest/jsdom); decisão de não introduzi-la agora.

### VERIFICAÇÃO
- `python -m unittest tests.test_smoke tests.test_propensao_rules tests.test_base_download -v`: 22/22 OK (sem regressão).

### ARQUIVOS ALTERADOS
- `api/main.py` (prompt + versão), `agent/propensao_rules.py`, `.env.example`,
  `tests/test_base_download.py` (novo), `tests/test_propensao_rules.py` (novo)

---

## V.1.4.40 — Simplificação da extensão, download na Base, busca em Sessões e Propensão de Compra
> Data: 19/08/2026 | Feature (extensão Chrome + Base de Conhecimento + Sessões + Propensão)

### VISÃO
Rodada de limpeza/simplificação: extensão Chrome reduzida ao essencial para o
vendedor durante a reunião (sem informação técnica/administrativa), download
do arquivo original na Base de Conhecimento, busca/filtro em Sessões ao Vivo,
e substituição do score numérico de compra por uma classificação de
Propensão (Alta/Média/Baixa/Não determinada) explicável.

### EXTENSÃO CHROME — Toggle "API ativa/desligada" completo
- Auditados todos os pontos de chamada de rede em `content.js`/`background.js`
  e adicionado guard `if (!estado.ativo) return;` em todos que faltavam:
  `enviarParaBackend`, `enviarChunkWhisper`, `registrarSessao`,
  `solicitarRegeneracaoRecapitulacao`. O heartbeat de 15s em `background.js`
  (`verificarHeartbeat`) também passa a não disparar `/health` quando a API
  está desligada — antes rodava incondicionalmente.
- **Bug de persistência corrigido**: `estadoExtensao.ativo` (background.js)
  nunca era restaurado do `chrome.storage.local` fora do evento `onInstalled`
  — se o service worker MV3 reciclasse (comum), o estado "API desligada"
  salvo pelo usuário era perdido e a extensão voltava a enviar dados sem
  avisar. Corrigido lendo `saleiaAtivo` do storage também na inicialização
  normal do service worker.
- Rótulos "API ativa" / "API desligada" com as mensagens de confirmação
  ("A extensão não enviará dados até ser reativada." / "Conexão
  restabelecida.") no popup (`#api-toggle-feedback`) e na sidebar
  (`#saleia-status`).

### EXTENSÃO CHROME — Remoções de UI (mantendo processamento interno)
- **Visual Cenário**: removido botão de captura de foto (📸) e todo o fluxo
  `capturarFotoCliente`/`abrirCenarioComFoto`/`_fotoAbrirVS` do content.js;
  handler `abrirCenarioComFoto` removido de background.js (órfão). Backend
  (`agent/visual_scenario.py`, `frontend/visual-scenario.html`) intocado —
  a funcionalidade nunca era disparada automaticamente pelo tempo real.
- **Mapa Financeiro**: removido o card da sidebar e seu bloco de renderização.
  Mantido o merge de `estado.mapaFinanceiro` que é reenviado ao backend a
  cada ciclo — `finance_agent`/`closer_agent` continuam recebendo esse dado.
- **Score de Compra → Propensão de Compra**: removido o card numérico
  (valor/100 + barra de progresso). Novo card `#saleia-propensao` mostra
  apenas o rótulo textual (Alta/Média/Baixa/Não determinada).
- **Cenário do Cliente**: removido o botão "📊 Abrir cenário do cliente" (fazia
  parte do card de Score). `buscar_resumo_cliente_para_reuniao()` mantido no
  backend — é input direto do prompt do coach_agent.
- **"Backend online" + URL**: popup não exibe mais a URL do backend nem a
  tabela detalhada de provedores/modelos/falhas (`#api-status`). Substituído
  por um indicador simples "Conectado"/"Desconectado"/"Conectando..."
  (`#conexao-status`). Campo de edição de URL removido da interface — a URL
  continua configurada internamente (auto-correção já existente em
  `background.js` para o domínio canônico).
- `manifest.json`: permissão `scripting` removida (só era usada pelo fluxo
  de Visual Cenário agora removido). Versão da extensão `1.4.2` → `1.4.3`.

### BASE DE CONHECIMENTO — Download do arquivo original
- Novas colunas nullable em `base_conhecimento`:
  `arquivo_nome_original`, `arquivo_path`, `arquivo_mime`, `arquivo_tamanho`
  (migração idempotente em `migrar_colunas_embedding_metadata_base_conhecimento`,
  `agent/sessao_manager.py`) — nulas para os documentos legados (sem arquivo
  original, sem botão de download para eles).
- `POST /base` passou de JSON puro para multipart (`Form` + `UploadFile`
  opcional) — o texto extraído continua vindo do mesmo fluxo de sempre
  (colado ou via OCR client-side); quando um arquivo é anexado, ele é
  gravado em `data/base_arquivos/<uuid>_<nome>` e referenciado nas novas
  colunas. Nenhuma extração automática nova de PDF/DOCX no backend.
- Novo `GET /base/{id}/download` — exige JWT (`_req_auth`, mesmo padrão de
  `/historico/uso`); base é global/compartilhada, sem conceito de tenant, a
  permissão é "estar autenticado". 404 se o documento não tiver arquivo ou
  se o arquivo não existir mais em disco.
- `DELETE /base/{id}` agora também apaga o arquivo em disco, se houver.
- Dashboard: botão "⬇️ Baixar" por documento (só aparece quando há arquivo);
  `adicionarDocumento()` envia `FormData` (com o `File` original guardado em
  `_arquivoBaseSelecionado` desde a seleção/drop) em vez de JSON.

### SESSÕES AO VIVO — Busca, filtros e ordenação
- `listar_sessoes()` (`agent/sessao_manager.py`) enriquecida com
  `cliente_nome`/`cliente_empresa` via subquery em `client_meetings` +
  `client_profiles` (Sales Brain Fase 4) — sem alterar o schema de
  `sessoes`. Limite de listagem `50` → `200` (para filtro client-side).
- Dashboard: busca única por cliente/empresa/link (aceita URL completa do
  Meet, extrai o código `xxx-yyyy-zzz`), filtros de data/hora, atalhos
  Hoje/Ontem/7 dias/30 dias, filtro por status e ordenação (recente/antiga/
  cliente/status) — mesmo padrão client-side já usado em "Filtros de
  Reuniões" (V.1.4.0).
- **Simplificação deliberada**: sem coluna de status persistida no banco,
  status é derivado apenas como "Ao vivo" (atualizado nos últimos 5 min) ou
  "Finalizada" — não foram inventados os estados "Processando"/"Erro" por
  falta de sinal real no banco para sustentá-los.
- Card de sessão agora mostra cliente/empresa (quando vinculado), duração
  aproximada (`updated_at - created_at`) e badge de status.

### PROPENSÃO DE COMPRA — substitui o score numérico
- Novo `agent/propensao_rules.py`: único lugar com os limiares
  (`LIMIAR_ALTA=70`, `LIMIAR_MEDIA=45` — mesmos limiares já usados na
  coloração do score na extensão/dashboard antes desta versão) e
  `classificar_propensao(score)` →
  `alta|media|baixa|nao_determinada`.
- **Tempo real (extensão)**: `orquestrador.py::_mesclar` passa a incluir
  `resultado["propensao"] = {"nivel": classificar_propensao(score_compra.valor)}`
  — classificação puramente determinística a partir do score já calculado
  pelo `closer_agent`, sem nenhuma chamada de IA extra por fragmento.
  `score_compra` continua calculado e persistido normalmente (uso interno).
- **Dashboard (pós-reunião)**: `PROMPT_RECAPITULACAO` (`api/main.py`) ganhou
  o bloco `propensao` (nivel, confiança, resumo, fatores_positivos/
  negativos/pendentes com evidência literal da transcrição, como_avancar).
  Regras explícitas no prompt: nunca inventar fator sem evidência real,
  `nivel: "nao_determinada"` em vez de forçar uma classificação quando a
  transcrição for insuficiente. `probabilidade_fechamento`/
  `justificativa_probabilidade` mantidos intactos (usados por
  `playbook_generator.py`).
- **Cache/custo**: nenhuma tabela ou versionamento novo — `propensao` chega
  dentro do mesmo JSON que já é salvo uma única vez por recapitulação; abrir
  "Ver detalhamento" no dashboard só lê o que já foi persistido, sem nova
  chamada de IA.
- Dashboard: card "📊 Score de Compra" (número + barra) removido de
  `verDetalhe()` e do card de lista de reuniões (`cardReuniaoHTML` — círculo
  agora mostra a letra da propensão, não o score). Card "🎯 Probabilidade de
  Fechamento" evoluído para "🎯 Propensão de Compra" com `<details>`
  expansível mostrando sinais positivos (✓), sinais de atenção (!) e "o que
  falta para avançar".

### VERSÃO
- Backend: `1.4.39` → `1.4.40` (`/health`, `/monitor/metricas`).
- Extensão Chrome: `1.4.2` → `1.4.3` (`manifest.json`).

### VERIFICAÇÃO
- `python -m unittest tests.test_smoke -v`: 8/8 OK (sem regressão).
- `agent/multiagente/orquestrador.py::_mesclar` testado isoladamente para as
  4 faixas de score (alta/média/baixa/não determinada) — classificação
  correta em todos os casos.
- Sintaxe verificada (Node) em `content.js`, `popup.js`, `background.js` e
  no bloco `<script>` de `dashboard.html`.
- **Achado, não corrigido (fora do escopo desta rodada)**: `python -m
  unittest discover -s tests` mostra 8 falhas pré-existentes em
  `test_next_best_question.py` e `test_realtime_memory.py`, todas em
  `api/processador_tempo_real.py`/`api/database.py` — arquivos não tocados
  nesta sessão. Parecem testes desatualizados desde a migração para o
  orquestrador multiagente (V.1.4.36) que nunca foram revisados.
- **Limitação do ambiente local**: sem MySQL acessível desta máquina (aponta
  para o host de produção), não foi possível validar o fluxo completo de
  upload/download da Base contra um banco real — validado via leitura
  cuidadosa do código, compilação e smoke tests. Recomenda-se validar
  upload → listagem → download → exclusão manualmente após o deploy.

### ARQUIVOS ALTERADOS
- `chrome-extension/background.js`, `content.js`, `popup.html`, `popup.js`,
  `popup.css`, `sidebar.css`, `manifest.json`
- `agent/sessao_manager.py`, `agent/multiagente/orquestrador.py`,
  `agent/propensao_rules.py` (novo)
- `api/main.py` (versão `1.4.39` → `1.4.40`)
- `frontend/dashboard.html`

---

## V.1.4.39 — Embeddings desacoplados: Ollama local (padrão) + OpenAI opcional
> Data: 17/08/2026 | Feature (infraestrutura de RAG / Sales Memory)

### VISÃO
Até esta versão, RAG (`base_conhecimento`) e Sales Memory (`sales_memories`)
dependiam obrigatoriamente da OpenAI (`text-embedding-3-small`) para gerar
embeddings, em 4 pontos diferentes do código. Introduzida uma camada
`EmbeddingProvider` desacoplada — Ollama local vira o padrão (nenhum texto
de reunião/documento sai da máquina), com OpenAI mantida como alternativa
configurável. Nenhum comportamento de RAG, Sales Memory, Knowledge Extractor
ou dos provedores de LLM de chat (DeepSeek/OpenAI/Anthropic/Gemini) mudou.

### BUG FECHADO — comparação de embeddings de dimensões diferentes
Antes desta versão, trocar de modelo de embedding sem reindexar quebrava a
requisição com `ValueError` dentro de `cosine_top_k` (vetores de dimensões
diferentes não podem ser multiplicados). Agora, `is_dimension_compatible()`
é checado antes de qualquer comparação — incompatibilidade vira "nada
encontrado" + log, nunca um crash.

### BACKEND — `services/embeddings/` (pacote novo)
- `provider.py`: interface `EmbeddingProvider` (`embed`, `embed_async`,
  `embed_batch`, `provider_name`, `model_name`, `dimension`, `health_check`),
  `EmbeddingResult`, `EmbeddingProviderError`, `cosine_top_k` (consolidado a
  partir da implementação antes duplicada em `base_conhecimento.py` e
  `sales_memory.py`), `is_dimension_compatible`
- `ollama_provider.py`: `OllamaEmbeddingProvider` — HTTP via `httpx` contra
  `POST /api/embeddings` do Ollama local; dimensão nunca hardcoded (resolvida
  de `len(embedding)` na primeira chamada real); retries só para falhas
  transitórias; zero import de SDKs de LLM externos
- `openai_provider.py`: `OpenAIEmbeddingProvider` — wrapper do código OpenAI
  já existente (mesmo modelo padrão `text-embedding-3-small`)
- `factory.py`: `get_embedding_provider()` lê `EMBEDDING_PROVIDER`
  (`ollama` padrão | `openai`), erro explícito em valor desconhecido — nunca
  fallback silencioso; `get_fallback_provider()` só ativa se
  `EMBEDDING_FALLBACK_PROVIDER` for explicitamente configurado

### BACKEND — refatoração dos 4 pontos que geravam embeddings
- `agent/base_conhecimento.py` (RAG): usa `services.embeddings`; cache passa
  a rastrear metadados de provider/modelo/dimensão e exclui linhas
  divergentes da matriz (com log) em vez de misturá-las
- `agent/sales_memory.py` (Sales Memory): idem; `gerar_e_salvar_embeddings_em_lote`
  passa a persistir metadados por linha; nova `migrar_colunas_embedding_metadata_memories()`
- `api/main.py::adicionar_base` (`POST /base`): usa `services.embeddings`;
  aviso de "sem embedding" agora nomeia o provedor configurado em vez do
  texto fixo "quota OpenAI esgotada"
- `agent/sessao_manager.py::exportar_para_base_conhecimento`: usa
  `services.embeddings`; **mudança de comportamento deliberada** — antes,
  falha ao gerar embedding derrubava a exportação inteira; agora salva sem
  embedding (mesmo padrão de `POST /base`); nova
  `migrar_colunas_embedding_metadata_base_conhecimento()` (também cobre a
  ausência de uma `criar_tabela_base_conhecimento()` centralizada, lacuna
  pré-existente)

### BACKEND — schema
- Novas colunas nullable `embedding_provider`, `embedding_model`,
  `embedding_dim` em `base_conhecimento` e `sales_memories`, migradas
  automaticamente no `on_startup()` (mesmo padrão try/except-por-migração já
  usado para as demais tabelas)

### BACKEND — diagnóstico e reindexação
- `GET /admin/embeddings/status` (novo, requer JWT admin): provider/modelo
  ativo, status de saúde, dimensão, contagem de documentos/memórias
  indexados vs. já no provedor atual, status do cache — nunca retorna
  chaves, `.env`, conteúdo de documentos/memórias ou vetores brutos
- `scripts/reindex_embeddings.py` (novo): CLI para regerar embeddings sob o
  provedor configurado; idempotente (linha já atualizada é pulada); nunca
  deleta um embedding antes de validar o novo; processa em lotes;
  `--dry-run`, `--provider`, `--table`, `--limit`, `--report-file`

### CONFIGURAÇÃO
- `.env.example`: nova seção `EMBEDDINGS / RAG` (`EMBEDDING_PROVIDER`,
  `OLLAMA_BASE_URL`, `OLLAMA_EMBEDDING_MODEL`, `OPENAI_EMBEDDING_MODEL`,
  `EMBEDDING_BATCH_SIZE`, `EMBEDDING_TIMEOUT`, `EMBEDDING_FALLBACK_PROVIDER`)
- `requirements.txt`: `httpx` adicionada explicitamente (já era dependência
  transitiva via `openai`)
- `docs/EMBEDDINGS_LOCAL.md` (novo): guia de instalação do Ollama para
  Windows e Linux, configuração, reindexação e rollback para OpenAI

### TESTES
- `tests/test_embeddings.py` (novo): interface dos providers, factory
  (incl. erro em provider desconhecido), Ollama (HTTP mockado), OpenAI (SDK
  mockado), `cosine_top_k`, `is_dimension_compatible`, validação de vetor e
  lógica de reindexação (banco mockado) — sem rede/DB real
- `tests/test_embeddings_semantic_ranking.py` (novo): prova de ranking
  semântico contra um Ollama local real, auto-skip se indisponível — nunca
  exige rede na suíte padrão

### PENDÊNCIA — deploy em produção
Ollama **não está instalado** na VPS (`37.27.214.33`). Como
`EMBEDDING_PROVIDER=ollama` é o padrão, fazer deploy sem instalar o Ollama
lá degrada silenciosamente RAG/Sales Memory (não derruba o serviço, mas
para de retornar contexto). Antes do deploy: instalar Ollama na VPS
(`docs/EMBEDDINGS_LOCAL.md`) **ou** definir `EMBEDDING_PROVIDER=openai`
explicitamente no `.env` da VPS.

### ARQUIVOS ALTERADOS
- `agent/base_conhecimento.py`, `agent/sales_memory.py`,
  `agent/sessao_manager.py`, `api/main.py` (versão `1.4.38` → `1.4.39`),
  `.env.example`, `requirements.txt`

---

## V.1.4.38 — Fix: 6 bugs corrigidos (connection leak, dead code, Sales Memory, multi-worker, RAG singleton)
> Data: 16/06/2026 | Bug fix

### BUGS CORRIGIDOS

**Bug #1 — Connection leak em `enriquecer_perfil_apos_relatorio` (ALTO)**
- `agent/client_intelligence.py`: a conexão MySQL aberta para buscar `objecoes_recorrentes` / `dores_recorrentes` nunca era fechada se uma exceção ocorresse antes do `conn.close()` no final do bloco `try`
- Correção: `conn` agora envolto em `try/finally: conn.close()` imediatamente após o `with conn.cursor()`, antes de chamar `atualizar_cliente()` e `vincular_reuniao()` (que abrem suas próprias conexões)

**Bug #2 — Dead code: `processar_fragmento_tempo_real` sobrescrita silenciosamente (ALTO)**
- `api/processador_tempo_real.py`: a função `processar_fragmento_tempo_real` era definida nas linhas 304–429 usando o agente legado (`analisar_fragmento`), mas na linha 792 o nome era reatribuído a `analyzeRealtimeMeeting`, tornando as 126 linhas anteriores código morto permanente — nunca chamado
- Correção: função legada removida; alias `processar_fragmento_tempo_real = analyzeRealtimeMeeting` mantido para compatibilidade com importadores existentes

**Bug #3 — Sales Memory não injetada no path multiagente (ALTO)**
- `agent/multiagente/orquestrador.py`: o orquestrador chamava apenas `buscar_contexto_similar` (RAG de transcrições históricas de `base_conhecimento.py`), ignorando completamente o sistema de Sales Memory introduzido em V.1.4.31
- Todas as memórias comerciais extraídas pelo `knowledge_extractor.py` (objeções, buying signals, padrões DISC, discovery patterns, playbook insights) estavam sendo gravadas no banco mas nunca recuperadas em tempo real
- Correção: adicionada chamada a `buscar_contexto_para_reuniao()` de `agent/sales_memory.py` logo após o RAG; resultado concatenado ao `client_context` e distribuído para todos os 4 agentes paralelos; falha silenciosa com `logger.debug`

**Bug #4 — `mapa_financeiro` inconsistente com 2 workers uvicorn (MÉDIO)**
- `api/processador_tempo_real.py`: `_cache_transcricoes` é um dict em memória por processo; com `--workers 2`, fragmentos da mesma reunião atendidos por workers diferentes acumulavam mapas financeiros separados
- Correção: após carregar `memoria_atual` do banco, se `cache["mapa_financeiro"]` estiver vazio e `diagnostico_atual` (salvo no MySQL) contiver `mapa_financeiro`, ele é restaurado para o cache local — garantindo continuidade independente de qual worker atende cada requisição

**Bug #5 — `AsyncOpenAI` recriado a cada chamada RAG (MÉDIO)**
- `agent/base_conhecimento.py`: a cada fragmento analisado em tempo real, `AsyncOpenAI(api_key=...)` era instanciado dentro de `buscar_contexto_similar()`, criando e destruindo o pool de conexões HTTP a cada chamada
- Correção: `_get_openai_client()` singleton lazy — instancia uma vez e reutiliza; recria automaticamente se `OPENAI_API_KEY` mudar em runtime (rotação via painel admin)

**Bug #6 — `MAX(score)` computado mas nunca lido em `_recalcular_stats` (BAIXO)**
- `agent/client_intelligence.py`: `SELECT COUNT(*) as total, AVG(score) as media, MAX(score) as ultimo` — o alias `ultimo` nunca era lido pelo Python (comentário no próprio código confirmava: "use date ordering below"); uma segunda query por data era a única usada para `ultimo_score`
- Correção: `MAX(score) as ultimo` removido do SELECT; query mais limpa e sem processamento SQL desnecessário

### ARQUIVOS ALTERADOS
- `agent/client_intelligence.py` (bugs #1 e #6)
- `api/processador_tempo_real.py` (bugs #2 e #4)
- `agent/multiagente/orquestrador.py` (bug #3)
- `agent/base_conhecimento.py` (bug #5)
- `api/main.py` (versão `1.4.37` → `1.4.38`, + correção de versões defasadas nos endpoints `/health` e `/monitor/metricas` que ainda exibiam `1.4.35`)

---

## V.1.4.37 — Sales Brain Fase 6: Follow-up Inteligente (T6.1 + T6.2 + T6.3)
> Data: 14/06/2026 | Feature (SALEIA Sales Brain — Fase 6)

### VISÃO
Geração automática de mensagens de follow-up para 3 canais (WhatsApp, Email, LinkedIn), adaptadas ao perfil DISC do cliente, com agenda inteligente baseada no score de compra. Botão "📩 Follow-up" integrado à página de detalhe de cada reunião.

### BACKEND — `agent/followup_generator.py` (novo arquivo)

**T6.1 — Follow-up Generator:**
- `criar_tabela_followups()`: tabela MySQL `followups` (id, meeting_id, client_id, canal, assunto, mensagem, call_to_action, tom, disc_profile, score, dias_apos, agendado_para, status)
- `gerar_followups()`: 1 chamada IA gera mensagens para os 3 canais adaptadas ao DISC
- `gerar_e_salvar_followups()`: orquestra IA + agenda + persistência MySQL; retorna lista de follow-ups

**T6.2 — Estratégia por Perfil:**
- Prompt `followup_generator.txt` com regras por DISC: D=curto/direto, I=entusiasmado/social proof, S=caloroso/sem pressão, C=dados/critérios
- Regras por canal: WhatsApp=informal/5 linhas, Email=profissional/3 parágrafos, LinkedIn=breve/sem venda direta

**T6.3 — Agenda Inteligente:**
- `agenda_inteligente(score)`: retorna timings adaptados ao score
  - Score 65+: 1 dia (WhatsApp), 4 dias (Email), 10 dias (LinkedIn)
  - Score 35-65: 3 dias (WhatsApp), 7 dias (Email), 15 dias (LinkedIn)
  - Score <35: 2 dias (WhatsApp), 5 dias (Email), 14 dias (LinkedIn)
- CRUD: `listar_followups()`, `obter_followup()`, `atualizar_followup()`, `deletar_followup()`

### BACKEND — `agent/prompt_templates/followup_generator.txt` (novo arquivo)
- Injeta: nome_cliente, disc_profile, score, resumo, dores, proximos_passos
- Retorna JSON com `whatsapp`, `email`, `linkedin` (mensagem, assunto, call_to_action, tom)

### BACKEND — `api/main.py`
- Startup: `criar_tabela_followups()`
- `POST /relatorios/{meeting_id}/followups/gerar` — lê memória da reunião (score, DISC, dores, resumo), verifica cliente vinculado, chama gerador IA
- `GET /relatorios/{meeting_id}/followups` — lista follow-ups da reunião
- `PATCH /followups/{id}` — edição de mensagem ou status (pendente/enviado/descartado)
- `DELETE /followups/{id}` — remoção
- Versão: `1.4.36` → `1.4.37`

### FRONTEND — `frontend/dashboard.html`
- Botão "📩 Follow-up" na página de detalhe de reunião (ao lado de "🔗 Vincular ao Cliente")
- `<div id="followup-section">` na página de detalhe — carrega follow-ups existentes automaticamente ao abrir
- Seção "📩 Follow-up Inteligente": grid de cards por canal com ícone, assunto, mensagem, CTA, timing colorido por prioridade
- Funções JS: `abrirFollowup()`, `carregarFollowupsExistentes()`, `renderizarFollowups()`, `copiarFollowup()`, `marcarEnviado()`, `deletarFollowup()`
- Copy to clipboard nativo via `navigator.clipboard`
- Badge de status (pendente/enviado/descartado) com cores

---

## V.1.4.36 — Sales Brain Fase 5: Multiagent Sales System (T5.1–T5.5)
> Data: 14/06/2026 | Feature (SALEIA Sales Brain — Fase 5)

### VISÃO
Substituição do agente único por 4 agentes especializados rodando em paralelo via `asyncio.gather`. Cada agente recebe somente o contexto relevante, responde em JSON focado e o orquestrador consolida no mesmo schema da extensão Chrome — sem quebrar backward compat.

### ARQUITETURA
```
Transcrição
↓
Coach + DISC + Finance + Closer  (asyncio.gather — paralelo)
↓
Orquestrador → consolida → JSON unificado → Sidebar
```

### BACKEND — `agent/multiagente/` (diretório novo)

**`coach_agent.py`** (T5.1)
- Responsável: condução, rapport, estágio da conversa, next_best_action, alertas, key_moments, filtro_cliente
- Recebe: transcricao, historico, resumo_vivo, diagnostico, eventos, skill_context, client_context
- Retorna: conversation_stage, next_best_action, alerta_urgente, dica_vendedor, key_moments, eventos, filtro_cliente, texto_falavel

**`disc_agent.py`** (T5.2)
- Responsável: perfil comportamental DISC, tipo de conta KARE, temperatura emocional
- Recebe: transcricao, historico, perfil_disc_atual, diagnostico
- Retorna: perfil_disc, kare_type, temperatura

**`finance_agent.py`** (T5.3)
- Responsável: capacidade financeira, potencial de compra, objeção de preço, produto recomendado
- Recebe: transcricao, historico, mapa_financeiro
- Retorna: mapa_financeiro, objecao_detectada

**`closer_agent.py`** (T5.4)
- Responsável: score de compra, maturity_score, resumo vivo, diagnóstico atual, próximos passos
- Recebe: transcricao, resumo_vivo, historico_scores, diagnostico
- Retorna: score_compra, maturity_score, resumo_vivo, current_diagnosis, proxima_acao

**`orquestrador.py`** (T5.5)
- `analisar_fragmento_multi()`: busca RAG uma vez, dispara 4 agentes com `asyncio.gather(return_exceptions=True)`, consolida com `_mesclar()`
- Falhas individuais degradam graciosamente — agente que falha usa fallback sem parar os outros
- `_nba_para_nbq()`: gera alias `next_best_question` a partir do `next_best_action` do Coach
- `_safe()`: desempacota resultado ou retorna `{}` se Exception

### BACKEND — `agent/prompt_templates/`
- `multiagente_coach.txt`: estágio SPIN + matriz de decisão next_best_action (10 cenários prioritizados)
- `multiagente_disc.txt`: classificação DISC + KARE + temperatura emocional
- `multiagente_finance.txt`: extração de sinais financeiros + produto recomendado
- `multiagente_closer.txt`: regras de score_compra + maturity_score (7 critérios)

### BACKEND — `api/processador_tempo_real.py`
- `analyzeRealtimeMeeting()` agora resolve skill_context + client_context (antes estavam só na função legada)
- Substitui `analisar_fragmento()` por `analisar_fragmento_multi()` do orquestrador
- Remove import `analisar_fragmento` desnecessário

### BACKEND — `api/main.py`
- Versão: `1.4.35` → `1.4.36`

---

## V.1.4.35 — Sales Brain Fase 4: Client Intelligence (T4.1 + T4.2 + T4.3)
> Data: 14/06/2026 | Feature (SALEIA Sales Brain — Fase 4)

### VISÃO
Perfis acumulativos por cliente: histórico de reuniões, enriquecimento automático de objeções/dores/DISC, contexto do cliente injetado no prompt em tempo real. Dashboard com timeline comercial.

### BACKEND — `agent/client_intelligence.py` (novo arquivo)
- Tabelas MySQL: `client_profiles` (perfil completo, listas JSON de objeções/dores, stats agregados) e `client_meetings` (vínculo reunião↔cliente com UNIQUE KEY)
- `criar_tabelas_clientes()`, `criar_cliente()`, `obter_cliente()` (inclui lista `reunioes`), `listar_clientes(busca, status, limit, offset)`, `atualizar_cliente()`, `deletar_cliente()` (cascade)
- `vincular_reuniao(client_id, meeting_id, titulo, score, data)` — upsert + `_recalcular_stats()` (score_medio, ultimo_score, total_reunioes)
- `desvincular_reuniao()`, `obter_timeline(client_id)`
- `buscar_cliente_por_reuniao(meeting_id)` → client_id | None
- `buscar_resumo_cliente_para_reuniao(meeting_id)` → bloco `[CONTEXTO DO CLIENTE]` para injeção no prompt
- `enriquecer_perfil_apos_relatorio()` — merge de novas objeções/dores/DISC após recapitulação

### BACKEND — `agent/agente_tempo_real.py`
- `analisar_fragmento()` ganha parâmetro `client_context: str = ""`
- Client context injetado no prompt antes da skill context: `contexto_str + client_context + skill_context`

### BACKEND — `api/processador_tempo_real.py`
- Antes de `analisar_fragmento()`: chama `buscar_resumo_cliente_para_reuniao(meeting_id)`, passa para `analisar_fragmento()` como `client_context`

### BACKEND — `api/main.py`
- Startup: `criar_tabelas_clientes()`
- `GET /clientes` — lista com busca e filtro por status
- `POST /clientes` — criação de perfil
- `GET /clientes/{id}` — perfil com lista de reuniões vinculadas
- `PATCH /clientes/{id}` — atualização parcial (notas, status, DISC, etc.)
- `DELETE /clientes/{id}` — remoção com cascade
- `POST /clientes/{id}/reunioes` — vínculo reunião↔cliente
- `DELETE /clientes/{id}/reunioes/{meeting_id}` — desvínculo
- `GET /clientes/por-reuniao/{meeting_id}` — busca rápida por meeting_id
- Versão: `1.4.34` → `1.4.35`

### FRONTEND — `frontend/dashboard.html`
- Nav item "👤 Clientes" (após Playbooks)
- Página `page-clientes`: métricas (total, ativos, ganhos, score médio), busca, filtro por status, grid de cards
- Página `page-cliente-detalhe`: timeline de reuniões com score visual, objeções e dores recorrentes, notas, seletor de status, botões Notas e Vincular Reunião
- Funções JS: `carregarClientes()`, `filtrarClientes()`, `renderizarClientes()`, `cardClienteHTML()`, `verClienteDetalhe()`, `voltarParaClientes()`, `renderClienteDetalhe()`, `alterarStatusCliente()`, `editarNotasCliente()`, `vincularReuniaoAoCliente()`, `desvinculaReuniaoCliente()`, `abrirNovoCliente()`
- Botão "🔗 Vincular ao Cliente" em toda página de detalhe de reunião com seleção de cliente existente ou criação inline

---

## V.1.4.34 — Sales Brain Fase 3: Sales Skills (T3.1 + T3.2 + T3.3)
> Data: 14/06/2026 | Feature (SALEIA Sales Brain — Fase 3)

### VISÃO
Skills especializadas injetadas automaticamente no prompt de análise em tempo real, baseadas no perfil DISC, score atual e estágio da conversa. Geração via IA a partir de playbooks.

### BACKEND — `agent/skills/` (5 arquivos JSON builtin)
- `disc-dominant.json` — DISC D, qualquer score/estágio: direto, ROI, opções A/B
- `objection-price.json` — score 20-65, estágios negociacao/resistencia/fechamento: gestão de objeção de preço
- `high-ticket-close.json` — score 65+, estágios fechamento/negociacao/compromisso: momentum high-ticket
- `financial-diagnosis.json` — score 0-45, estágios abertura/descoberta/desenvolvimento: coleta de dados financeiros
- `follow-up-recovery.json` — score 0-35, qualquer estágio: resgate de reunião fria

### BACKEND — `agent/skill_resolver.py` (novo arquivo)
- `criar_tabela_skills()`: tabela MySQL para skills customizadas/geradas
- `_carregar_skills_builtin()`: lê JSONs de `agent/skills/`
- `_carregar_skills_db()`: lê skills ativas do MySQL
- `listar_skills(apenas_ativas)`: merge builtin + DB com ordenação por priority
- `resolver_melhor_skill(disc, score, stage)`: match por DISC + range de score + estágio; tiebreak por priority
- `resolver_skill_context(disc, score, stage)`: retorna `system_injection` como string (ou "" se sem match)
- `salvar_skill()`, `atualizar_skill()`, `deletar_skill()`: CRUD para skills customizadas
- `gerar_skill(contexto, playbook_id)`, `gerar_e_salvar_skill()`: geração via `chamar_ia()` + prompt `skill_generation.txt`

### BACKEND — `agent/prompt_templates/skill_generation.txt` (novo arquivo)
- Instrui IA a criar skills com: name, description, triggers (disc/score/stages), priority, system_injection, tactics

### BACKEND — `agent/agente_tempo_real.py`
- `analisar_fragmento()` ganha parâmetro `skill_context: str = ""`
- Texto da skill injetado no final do prompt (após RAG context)

### BACKEND — `api/processador_tempo_real.py`
- Antes de `analisar_fragmento()`: carrega MeetingMemory, extrai score e stage, chama `resolver_skill_context()`
- Skill context passado para `analisar_fragmento()` — zero impacto se nenhuma skill aplicável

### BACKEND — `api/main.py`
- Startup: `criar_tabela_skills()`
- `GET /skills` — lista builtins + customizadas
- `POST /skills/gerar` — gera skill via IA em background (contexto + source_playbook_id)
- `PATCH /skills/{id}` — edição de skills DB
- `DELETE /skills/{id}` — remoção de skills DB (admin)
- Versão: `1.4.33` → `1.4.34`

### FRONTEND — `frontend/dashboard.html`
- Botão "🧠 Skill" em cada card de playbook → `transformarEmSkill(playbook_id)`
- Seção "🧠 Skills Ativas" na página Playbooks: grid de cards com DISC/score/stage/origem
- `carregarSkills()`, `renderizarSkills()`, `cardSkillHTML()`, `toggleSkill()`, `deletarSkill()`, `transformarEmSkill()`
- Skills builtin mostradas como somente-leitura (sem botões editar/deletar); skills DB têm toggle e delete

---

## V.1.4.33 — Sales Brain Fase 2 · T2.3: Biblioteca de Playbooks (Dashboard)
> Data: 14/06/2026 | Feature (SALEIA Sales Brain — Fase 2)

### VISÃO
Nova aba "Playbooks" no dashboard com busca, filtro por ativos, cards expansíveis e edição/ativação/exclusão inline.

### FRONTEND — `frontend/dashboard.html`
- Nav: novo item "🎯 Playbooks" entre Histórico e Base de IA
- Página `page-playbooks`: busca por nome/persona, checkbox "Apenas ativos", botão atualizar, métricas (total / ativos)
- `carregarPlaybooks()`: GET /playbooks com flag apenas_ativos
- `filtrarPlaybooks()`: filtro client-side sobre cache
- `cardPlaybookHTML(p)`: card com nome, persona, badge Ativo/Inativo, meeting de origem, data, seções expansíveis (`<details>`) para Passos, Objeções, Argumentos vencedores, Sequência de fechamento
- `togglePlaybook(id, novoAtivo)`: PATCH is_active com atualização otimista de cache
- `editarPlaybook(id)`: prompt() para nome e persona, PATCH
- `deletarPlaybook(id)`: confirm() + DELETE com remoção do cache

### BACKEND — `api/main.py`
- Versão: `1.4.32` → `1.4.33`

---

## V.1.4.32 — Sales Brain Fase 2 · T2.1+T2.2: Playbook Engine
> Data: 14/06/2026 | Feature (SALEIA Sales Brain — Fase 2)

### VISÃO
Reuniões vencedoras geram playbooks automaticamente. Critério de sucesso: probabilidade_fechamento=="alta", score_compra>80 ou status marcado manualmente como "won".

### BACKEND — `agent/playbook_generator.py` (novo arquivo)
- `criar_tabelas_playbook()`: cria `meeting_status` (meeting_id PK, status, updated_at) e `playbooks` (id UUID, name, targetPersona, steps, objections, winningArguments, closingSequence, source_meeting_id, is_active)
- `_eh_reuniao_de_sucesso(relatorio, meeting_id)`: 3 critérios em cascata — probabilidade=="alta", score>80, status=="won"
- `atualizar_status_reuniao(meeting_id, status)`: upsert em `meeting_status`
- `obter_status_reuniao(meeting_id)`: leitura com fallback "open"
- `listar_status_reunioes(meeting_ids)`: batch lookup para enriquecer listagem
- `salvar_playbook(playbook)`, `listar_playbooks()`, `obter_playbook()`, `atualizar_playbook()`, `deletar_playbook()`: CRUD completo
- `gerar_playbook(relatorio, transcricao, meeting_id)`: chama `chamar_ia()` com prompt playbook_generation.txt
- `gerar_e_salvar_playbook(relatorio, transcricao, meeting_id)`: pipeline completo para BackgroundTask

### BACKEND — `agent/prompt_templates/playbook_generation.txt` (novo arquivo)
- Prompt especializado: extrai name, targetPersona, steps, objections, winningArguments, closingSequence
- Instrui IA a focar no que REALMENTE funcionou nessa reunião, não no que "costuma funcionar"

### BACKEND — `api/main.py`
- Startup: `criar_tabelas_playbook()` adicionado
- `/recapitulacao-manual` e `/recapitulacao-completa`: após extrair memórias, detecta sucesso e agenda `gerar_e_salvar_playbook()` como BackgroundTask adicional
- `PATCH /relatorios/{meeting_id}/status` — define status (open/won/lost) com JWT
- `GET /relatorios/{meeting_id}/status` — consulta status com JWT
- `GET /playbooks` — lista playbooks (filtro `apenas_ativos`, `limit`, `offset`)
- `GET /playbooks/{id}` — detalhe do playbook
- `PATCH /playbooks/{id}` — edição inline (name, steps, is_active, etc.)
- `DELETE /playbooks/{id}` — remoção (admin)
- `POST /playbooks/gerar/{meeting_id}` — geração manual forçada (admin)
- `GET /relatorios` agora retorna campos `meeting_id` e `status` em cada item
- Versão: `1.4.31` → `1.4.32`

### FRONTEND — `frontend/dashboard.html`
- `cardReuniaoHTML()`: exibe badge "✓ Ganha" (verde) ou botão "Ganha" (dourado) por reunião
- `marcarComoGanha(event, meetingId)`: PATCH no endpoint de status, atualiza cache local e re-renderiza sem reload

---

## V.1.4.31 — Sales Brain Fase 1 · Tarefa 1.3: Busca Semântica em Memórias Comerciais
> Data: 14/06/2026 | Feature (SALEIA Sales Brain — Fase 1)

### VISÃO
Motor de busca semântica sobre as memórias comerciais: embeddings OpenAI `text-embedding-3-small`,
similaridade de cosseno via NumPy, cache in-memory lazy-loaded. Três novos endpoints REST expostos.

### BACKEND — `agent/sales_memory.py` (extensão T1.3)
- `migrar_coluna_embedding_memories()`: garante coluna `embedding LONGTEXT` na tabela `sales_memories`
- `gerar_embedding(texto)`: gera vetor 1536-dim via `text-embedding-3-small` (limite 6000 chars)
- `salvar_embedding_memoria(mem_id, embedding)`: persiste JSON do vetor no banco
- `gerar_e_salvar_embeddings_em_lote(itens)`: processa lista `[(id, content), ...]`, invalida cache ao final
- `_carregar_cache_memorias()`: carrega todos os embeddings em matriz NumPy (lazy, global)
- `invalidar_cache_memorias()`: força recarga no próximo acesso
- `buscar_memorias_semantico(query, top_k, memory_type, confidence_min, similarity_min)`: busca semântica completa com filtros
- `buscar_contexto_para_reuniao(fragmento, top_k)`: retorna texto formatado para injeção em prompts (similarity_min=0.30)

### BACKEND — `agent/knowledge_extractor.py` (atualização T1.3)
- `extrair_e_salvar_memorias()` agora chama `gerar_e_salvar_embeddings_em_lote()` após salvar
- Embeddings gerados no mesmo thread de background — não exige tarefa adicional

### BACKEND — `api/main.py` — novos endpoints
- `GET /sales-memories` — lista memórias com filtros `memory_type`, `limit`, `offset` (JWT)
- `GET /sales-memories/buscar` — busca semântica via querystring `?q=...&top_k=5&memory_type=...` (JWT)
- `GET /sales-memories/stats` — contagem de memórias por tipo (JWT)
- Versão: `1.4.30` → `1.4.31`

### BANCO
- `sales_memories.embedding` (LONGTEXT) — coluna adicionada via migration idempotente no startup

---

## V.1.4.30 — Sales Brain Fase 1 · Tarefa 1.2: Knowledge Extractor (pipeline pós-reunião)
> Data: 14/06/2026 | Feature (SALEIA Sales Brain — Fase 1)

### VISÃO
Pipeline automático que extrai aprendizados comerciais reutilizáveis após cada reunião.
Executa em background (não bloqueia a resposta do relatório) via FastAPI BackgroundTasks.

### BACKEND — `agent/knowledge_extractor.py` (novo arquivo)
- `_montar_contexto(relatorio, transcricao)`: monta contexto compacto do relatório (recap, DISC, financeiro, trecho da transcrição até 6000 chars) para enviar à IA
- `_validar_memoria(dict)`: valida tipos, título, conteúdo e normaliza confidence (0.0-1.0)
- `extrair_memorias(relatorio, transcricao)`: chama `chamar_ia()` com o prompt de extração e parseia o campo `memorias` do dict retornado
- `extrair_e_salvar_memorias(relatorio, transcricao, meeting_id, organization_id)`: pipeline completo — extrai + salva via `salvar_memorias_em_lote()`, captura exceções internamente

### BACKEND — `agent/prompt_templates/knowledge_extraction.txt` (novo arquivo)
- Prompt especializado em extração de conhecimento comercial
- Instrui a IA a retornar `{"memorias": [...]}` (json_object compatível)
- Diferencia BOA memória (generalizável, acionável) de MÁ memória (específica demais, óbvia)
- Descreve os 8 tipos com exemplos implícitos

### BACKEND — `api/main.py`
- `RecapitulacaoRequest` ganha campo `meeting_id: Optional[str]` para rastreabilidade
- `/recapitulacao-manual`: aceita `BackgroundTasks`, agenda extração após salvar relatório
- `/recapitulacao-completa`: idem
- Versão: `1.4.29` → `1.4.30`

### FLUXO COMPLETO
```
Usuário analisa transcrição no Dashboard
↓ POST /recapitulacao-manual
↓ IA gera recapitulação + DISC + diagnóstico (síncrono)
↓ Resposta retornada ao usuário
↓ BackgroundTask: extrair_e_salvar_memorias()
  ↓ chamar_ia() com prompt knowledge_extraction.txt
  ↓ Parseia {"memorias": [...]}
  ↓ Valida cada memória
  ↓ salvar_memorias_em_lote() → tabela sales_memories
```

### ARQUIVOS ALTERADOS
- `agent/knowledge_extractor.py` (novo)
- `agent/prompt_templates/knowledge_extraction.txt` (novo)
- `api/main.py` (RecapitulacaoRequest + 2 endpoints + versão)

---

## V.1.4.29 — Sales Brain Fase 1 · Tarefa 1.1: Sales Memory (tabela + módulo)
> Data: 14/06/2026 | Feature (SALEIA Sales Brain — Fase 1)

### VISÃO
Primeira entrega do SALEIA Sales Brain — infraestrutura de memória comercial persistente.
Cada reunião passa a gerar aprendizados reutilizáveis que enriquecem futuras análises.

### BACKEND — `agent/sales_memory.py` (novo arquivo)
- Tabela `sales_memories` criada via `criar_tabela_sales_memories()` no startup
- 8 tipos de memória: `objection`, `pain_point`, `buying_signal`, `closing_signal`, `discovery_pattern`, `disc_pattern`, `financial_pattern`, `playbook_insight`
- `salvar_memoria()` — persiste um aprendizado com validação de tipo, UUID automático, tags JSON
- `salvar_memorias_em_lote()` — pipeline de múltiplas memórias pós-reunião
- `listar_memorias()` — filtros por tipo, reunião, organização, confidence mínimo, paginação
- `buscar_por_reuniao()` — todas as memórias de uma reunião específica
- `contar_por_tipo()` — estatísticas de memória agrupadas
- `atualizar_memoria()` / `deletar_memoria()` — gestão CRUD completa
- Índices: `memory_type`, `source_meeting_id`, `organization_id+memory_type`, `created_at`
- Padrão de conexão idêntico ao restante do projeto (pymysql direto, sem ORM)

### BACKEND — `api/main.py`
- Startup chama `criar_tabela_sales_memories()` na sequência de migrações
- Versão: `1.4.28` → `1.4.29`

### TESTES — `tests/test_smoke.py`
- `agent.sales_memory.criar_tabela_sales_memories` adicionado ao patch list do smoke suite

### ARQUIVOS ALTERADOS
- `agent/sales_memory.py` (novo)
- `api/main.py` (startup + versão)
- `tests/test_smoke.py` (patch list)

---

## V.1.4.28 — Motor de Próxima Melhor Ação & Insight Consultivo
> Data: 14/06/2026 | Feature Major

### VISÃO GERAL
Evolução do campo "Próxima fala" para um motor completo de condução consultiva da venda, combinando SPIN Selling, Sandler Enterprise Selling e Venda Desafiadora.

### BACKEND — `agent/prompt_templates/agente_tempo_real.txt`
- **`next_best_action`** (novo campo primário): substitui e expande `next_best_question`
  - Campos: `type` (question|insight|warning|next_step), `category`, `title`, `message`, `objective`, `reason`, `expected_effect`, `risk_if_ignored`, `follow_up`, `confidence`
- **`conversation_stage`**: classifica o estágio dominante da conversa (abertura | situacao | problema | implicacao | necessidade_solucao | qualificacao | proposta | compromisso)
- **`kare_type`**: classifica a conta (keep | attain | recapture | expand)
- **`maturity_score`**: novo score de maturidade da oportunidade (0-100), independente do Score de Compra
  - 7 critérios: dor_identificada (0-20), impacto_quantificado (0-20), urgencia_identificada (0-15), budget_identificado (0-15), decisores_mapeados (0-10), valor_verbalizado_cliente (0-10), proximo_passo_claro (0-10)
- **Matriz de decisão** (10 regras em ordem de prioridade): objeção ativa → alta maturidade → preço antes de valor → problema operacional com impacto estratégico → dor sem impacto → dor sem urgência → dor não identificada → decisor desconhecido → budget ausente → valor não verbalizado
- **Insight Desafiador**: tipo `insight` para quando cliente foca em preço, trata problema como operacional, não percebe custo da inação ou avalia fornecedores como commodities
- **DISC expandido**: exemplos de pergunta específicos por perfil (D/I/S/C) para cada regra da matriz
- **`next_best_question`** mantido como alias de `next_best_action` para backward compat

### BACKEND — `api/processador_tempo_real.py`
- `_fallback_next_best_action()`: novo fallback completo para `next_best_action`
- `_fallback_maturity()`: fallback para maturity_score zerado
- `_nba_para_nbq()`: converte `next_best_action` → `next_best_question` para backward compat
- `_normalizar_resposta_realtime()`: normaliza `next_best_action`, `maturity_score`, `conversation_stage`, `kare_type`
- `_extrair_ultima_analise_memoria()`: propaga novos campos do cache

### FRONTEND — `chrome-extension/content.js`
- Sidebar renomeada: "PRÓXIMA MELHOR PERGUNTA" → "PRÓXIMA MELHOR AÇÃO"
- Novo bloco **Stage + KARE**: badges de estágio da conversa e tipo KARE com cores por contexto
- Novo bloco **Maturity Score**: grid de chips coloridos (verde=completo, amarelo=parcial, cinza=ausente) com total 0-100
- `renderizarNBQ()` atualizado para `next_best_action`:
  - Ícone do tipo (❓ pergunta / 💡 insight / ⚠️ alerta / ▶️ próx.passo)
  - Título + objetivo em linha
  - Mensagem principal com botão copiar
  - Motivo (por que agora)
  - Risco se ignorado (em laranja)
  - Follow-up (em cinza itálico)
  - Confiança como percentual colorido (verde/amarelo/cinza)
- Novo `renderizarStageKare()`: badges de estágio e KARE no topo da sidebar
- Novo `renderizarMaturity()`: grid de maturidade

### FRONTEND — `chrome-extension/content.css`
- Estilos para `.saleia-stage-kare`, `.saleia-stage-badge`, `.saleia-kare-badge`
- Estilos para `.saleia-nbq-type`, `.saleia-nbq-risco`, `.saleia-nbq-followup`
- Estilos para `.saleia-maturity-box`, `.saleia-maturity-grid`, `.saleia-maturity-chip`

### DOCUMENTAÇÃO — `frontend/manual.html` + `frontend/manual_tecnico.html`
- Manual do usuário atualizado para V.1.4.28: nova seção 7 "Motor de Próxima Melhor Ação" (4 tipos de ação, 8 estágios SPIN, KARE, Maturity Score 7 critérios, matriz de decisão, como usar na prática)
- Seção 6 (Sidebar) expandida com badges Stage+KARE, bloco Próxima Melhor Ação, Maturity Score grid
- 2 novas dicas na seção Dicas (badge de estágio, Insight Desafiador)
- Manual técnico: VPS corrigida para `37.27.214.33`, seção Motor NBA adicionada (schema completo, regras, arquivos), troubleshoot 502/zombie workers, deploy atualizado para git pull

### ARQUIVOS ALTERADOS
- `agent/prompt_templates/agente_tempo_real.txt` (reescrito)
- `api/processador_tempo_real.py`
- `chrome-extension/content.js`
- `chrome-extension/content.css`
- `api/main.py` (versão 1.4.26 → 1.4.28)
- `frontend/manual.html` (V.1.4.8 → V.1.4.28)
- `frontend/manual_tecnico.html` (V.1.4.26 → V.1.4.28)

---

## V.1.4.27 — Fix: logo quebrada na tela de login + estabilidade VPS
> Data: 14/06/2026 | Fix / Infra

### PROBLEMA 1 — 502 Bad Gateway em api.saleia.app.br
Workers uvicorn entraram em estado zumbi após ~2,5 dias de uptime: aceitavam conexão TCP mas retornavam empty reply. O loop de métricas SQLite (`metricas_historico.py`) falhava a cada 60s com `unable to open database file`, contribuindo para a degradação.

**Correção:**
- `systemctl restart saleia` restaurou o serviço
- Adicionado `RuntimeMaxSec=86400` em `/etc/systemd/system/saleia.service` para reinício automático diário, prevenindo recorrência

### PROBLEMA 2 — Logo quebrada na tela de login
`<img src="/logo-saleia.png">` referenciava caminho não servido pelo nginx (apenas `/static/` está configurado como alias para o filesystem).

**Correção:**
- `frontend/login.html`: src alterado para `/static/logo-saleia.png`
- Criado diretório `frontend/static/` e adicionado `logo-saleia.png`
- Arquivo deployado em `/opt/saleia/frontend/static/logo-saleia.png` na VPS

### ARQUIVOS ALTERADOS
- `frontend/login.html` (src do logo corrigido)
- `frontend/static/logo-saleia.png` (novo)

---

## V.1.4.26 — Campo de chave OPENAI_API_KEY no card OpenAI Whisper
> Data: 09/06/2026 | Feature

### DASHBOARD — Configurações → Transcrição de Áudio

- Card **OpenAI Whisper** agora exibe campo `type="password"` + botão 👁 + **Salvar chave**, idêntico ao card Groq
- Backend: `TranscricaoConfigRequest` aceita novo campo `openai_api_key`; quando `provedor=whisper` e chave fornecida, `_salvar_env_key("OPENAI_API_KEY", ...)` é chamado
- Função `salvarChaveWhisper()` e `toggleVerChaveWhisper()` adicionadas ao frontend

### ARQUIVOS ALTERADOS
- `api/main.py` (1.4.25 → 1.4.26)
- `frontend/dashboard.html`

---

## V.1.4.25 — Teste de transcrição via models.list (sem áudio)
> Data: 09/06/2026 | Fix

### PROBLEMA
Endpoint `POST /admin/transcricao/teste` enviava WAV mínimo de 44 bytes que era rejeitado com `400 — Audio file is too small` pelo Groq e OpenAI Whisper.

### CORREÇÃO
Substituído por `client.models.list()` — chamada leve que valida a chave sem precisar de áudio. Mensagem de erro para Whisper atualizada para indicar que a chave é configurada em "Configuração de APIs".

### ARQUIVOS ALTERADOS
- `api/main.py` (1.4.24 → 1.4.25)
- `frontend/dashboard.html` (nota Whisper substituída por campo de chave — preparação para V.1.4.26)

---

## V.1.4.24 — Botão "Testar conexão" na seção Transcrição de Áudio
> Data: 09/06/2026 | Feature

### DASHBOARD — Configurações → Transcrição de Áudio

- Novo endpoint `POST /admin/transcricao/teste` (requer JWT admin) — valida chave Groq ou OpenAI Whisper
- Badge Online/Offline no cabeçalho de cada card, idêntico aos cards de provedores IA
- Frontend: função `testarTranscricao(pid)` + badge `tr-status-{pid}` — mensagem de erro detalhada em `tr-fb-{pid}` ao clicar

### ARQUIVOS ALTERADOS
- `api/main.py` (1.4.23 → 1.4.24, novo endpoint)
- `frontend/dashboard.html` (botão + badge por card)

---

## Fix — Timestamps UTC exibidos em horário local (Sessões ao Vivo)
> Data: 09/06/2026 | Fix UX

### PROBLEMA
VPS em UTC+0, usuário em UTC-3 (Brasil). Sessões mostravam `23:08` quando eram `20:09` local.

### CORREÇÃO
Função `_fmtLocal(utcStr)` adicionada ao dashboard: appenda `Z` ao timestamp sem timezone e converte via `toLocaleString('pt-BR')`. Aplicada nos 3 pontos que renderizam `created_at`/`updated_at` nas Sessões ao Vivo.

### ARQUIVOS ALTERADOS
- `frontend/dashboard.html`

---

## Fix — autocomplete=new-password no campo Groq API Key
> Data: 09/06/2026 | Fix UX

Chrome associava o campo `type="password"` do Groq ao login do usuário e exibia prompt "Salvar senha?". Trocado `autocomplete="off"` por `autocomplete="new-password"` — instrução aceita pelo Chrome para não sugerir salvar nem preencher automaticamente.

### ARQUIVOS ALTERADOS
- `frontend/dashboard.html`

---

## Extensão Chrome — Fix: migrar URL do storage de saleia.com.br para saleia.app.br
> Data: 09/06/2026 | Fix

`chrome.storage.local` retinha `api.saleia.com.br` do install anterior, ignorando o novo padrão `api.saleia.app.br`. `background.js` agora inclui `saleia.com.br` na lista de URLs obsoletas — ao recarregar a extensão, o storage é migrado automaticamente.

### ARQUIVOS ALTERADOS
- `chrome-extension/background.js`

---

## Extensão Chrome V.1.4.2 — Migração de domínio para api.saleia.app.br
> Data: 09/06/2026 | Fix

### CORREÇÃO

Todos os arquivos da extensão Chrome ainda apontavam para `api.saleia.com.br` (VPS antiga). Substituído por `api.saleia.app.br` (nova VPS Hetzner) em:

- `background.js` — `estadoExtensao.backendUrl` e `BACKEND_URL_CANONICAL`
- `content.js` — `CONFIG.backendUrl`
- `popup.js` — fallback de `backendAtual()`
- `popup.html` — `placeholder` e `value` do campo de URL
- `manifest.json` — `host_permissions` (removida entrada HTTP, mantida HTTPS)
- `INSTALAR.md` — URLs de documentação

Versão da extensão: `1.4.1` → `1.4.2`

**Para aplicar:** reinstalar a extensão (`chrome://extensions` → remover → carregar sem compactação) ou clicar em 🔄 recarregar se já estiver instalada.

### ARQUIVOS ALTERADOS
- `chrome-extension/background.js`, `content.js`, `popup.js`, `popup.html`, `manifest.json`, `INSTALAR.md`

---

## V.1.4.23 — Fix crítico: status de provedores oscilando com 2 workers uvicorn
> Data: 09/06/2026 | Bug fix crítico

### CAUSA RAIZ — Bug "Atualizar troca status das APIs no Monitor"

Com `--workers 2`, o uvicorn cria **2 processos independentes**, cada um com sua própria cópia de `_ultimo_teste` (dict in-memory). Quando o usuário clicava "Testar conexão" na aba Config APIs, o resultado era salvo apenas no worker que atendeu aquela requisição. Ao clicar "↺ Atualizar" no Monitor, a request podia cair no outro worker (com `_ultimo_teste` vazio) → mostrava "✅ Online" via circuit breaker "ok". Na próxima atualização caía no primeiro worker → mostrava "❌ Offline". Status **alternava a cada clique** dependendo de qual worker atendia.

### CORREÇÃO

- **`api/metricas_historico.py`**: novas funções `criar_tabela_teste_provedores()`, `salvar_teste_provedor(pid, ok, ts, detalhe)`, `ler_testes_provedores()` — tabela SQLite `teste_provedores` com `ON CONFLICT ... DO UPDATE` (upsert atômico)
- **`api/main.py`**: 
  - `_ler_testes_compartilhados()` — lê do SQLite e mescla com in-memory (o mais recente vence)
  - `on_startup`: chama `criar_tabela_teste_provedores()` junto com outras tabelas
  - `admin_testar_provedor`: persiste resultado em SQLite além do dict in-memory
  - `/monitor/metricas`: substitui `_ultimo_teste` por `_ler_testes_compartilhados()`

### POR QUE FUNCIONA

SQLite usa WAL mode — múltiplos leitores simultâneos, escritas serializadas e atômicas. Todos os workers leem da mesma `metricas.db` em disco. O upsert garante que o resultado mais recente de qualquer worker fique disponível para todos.

### ARQUIVOS ALTERADOS
- `api/metricas_historico.py` (3 novas funções)
- `api/main.py` (`1.4.22` → `1.4.23`, `_ler_testes_compartilhados`, persistência de testes)

---

## V.1.4.22 — Refatoração: 6 bugs corrigidos (transcrição + provedores + Monitor)
> Data: 09/06/2026 | Bug fix (refatoração profunda)

### BUGS CORRIGIDOS

**Bug #1 — RAIZ: "Atualizar muda API de transcrição"**
- `GET /monitor/metricas` usava `os.getenv("TRANSCRICAO_PROVEDOR", "groq")` enquanto `GET /admin/transcricao/config` usava `env.get(..., "whisper")` (padrões diferentes, fontes diferentes: `os.environ` vs arquivo `.env`). Monitor mostrava Groq como ativo, Config mostrava Whisper — parecendo que "Atualizar" trocou o provedor. Fix: alinhar padrão para `"whisper"` em ambos endpoints

**Bug #2 — Double-reload na transcrição**
- `salvarChaveGroq` e `ativarTranscricaoProvedor` disparavam `setTimeout(() => carregarTranscricaoConfig(), ...)` independentes. Se chamados em sequência (salvar chave → ativar), dois reloads corriam em paralelo. Fix: `_trReloadTimer` cancela reload anterior antes de agendar novo

**Bug #3 — `delete _accLoaded['transcricao']` incorreto**
- `ativarTranscricaoProvedor` deletava `_accLoaded['transcricao']` antes de recarregar, fazendo o accordion recarregar novamente ao ser reaberto desnecessariamente. Fix: removido — o reload direto via `carregarTranscricaoConfig()` é suficiente

**Bug #4 — Provedores com status desatualizado após toggle**
- `toggleProvedor` chamava `carregarProvedoresApi()` sem `await` e sem limpar `_testeStatus[id]`. Resultado: re-render corria em background, e o badge do provedor mostrava status antigo (cacheado). Fix: limpa `_testeStatus[id]` + `_testePendente.delete(id)` + `await carregarProvedoresApi()` → aciona re-teste automático pós-reload

**Bug #5 — `_autoTestarProvedores` não mostrava `⏳ Testando...` para pré-testes**
- Quando `_preTestarProvedores` iniciava um teste em background e o accordion abria antes do término, `_autoTestarProvedores` via `_testePendente.has(pid)` e pulava sem setar o badge — ficava em branco. Fix: exibe `⏳ Testando...` mesmo para testes já em andamento

**Bug #6 — Monitor: múltiplos timers**
- `_iniciarMonitor` usava `if (!_monitorTimer)` que poderia falhar em edge cases (navegação rápida). Fix: sempre chama `_pararMonitor()` antes de iniciar novo timer

**Bônus: `fetchJsonWithFallback`**
- Ao mudar URL de API (fallback para produção), `_accLoaded` não era invalidado. Fix: limpa flags de cache ao trocar de URL

### ARQUIVOS ALTERADOS
- `api/main.py` (`1.4.21` → `1.4.22`, padrão `TRANSCRICAO_PROVEDOR` alinhado para `"whisper"`)
- `frontend/dashboard.html` (6 correções acima + variável `_trReloadTimer`)

---

## V.1.4.21 — Config APIs: pré-teste em background + badge de carregamento
> Data: 09/06/2026 | UX fix

### DASHBOARD — Aba Configuração de APIs

- **Pré-teste ao navegar para Configurações**: `_preTestarProvedores()` dispara os 4 testes em background assim que o usuário clica na aba — quando o accordion for aberto, os resultados já estão prontos e os badges aparecem instantaneamente via `_aplicarTesteStatus()`
- **Badge "⏳ Testando..."**: enquanto o teste ainda está em andamento (accordion aberto antes do teste concluir), os badges mostram "⏳ Testando..." ao invés de ficarem em branco
- **Sem duplicatas**: `_testePendente` (Set) impede que `_autoTestarProvedores` dispare um segundo teste para o mesmo provedor se `_preTestarProvedores` já iniciou um

### ARQUIVOS ALTERADOS
- `api/main.py` (versão `1.4.20` → `1.4.21`)
- `frontend/dashboard.html` (`_preTestarProvedores`, `_testePendente`, `_autoTestarProvedores` com badge de loading, `testarProvedor` limpa `_testePendente`, `mostrarPagina` chama `_preTestarProvedores`)

---

## V.1.4.20 — Config APIs: status real automático ao abrir accordion
> Data: 09/06/2026 | Bug fix (2 iterações)

### DASHBOARD — Aba Configuração de APIs

- **Teste automático real**: ao abrir o accordion "Configuração de APIs", `_autoTestarProvedores()` dispara `testarProvedor()` para cada um dos 4 provedores em background — os mesmos testes do botão "Testar conexão", sem interação do usuário
- **Status preciso**: abordagem anterior usava `/monitor/metricas` (circuit breaker), que mostrava todos como ✅ Online mesmo quando Anthropic/Gemini estavam sem créditos; substituída por chamadas reais à API de cada provedor
- **Prioridade manual**: provedores já testados manualmente na sessão (`_testeStatus`) são ignorados — não duplica chamadas
- **Sessão preservada**: resultado dos testes persiste na sessão via `_testeStatus`; ao re-renderizar a lista (toggle/inativar/ativar), `_aplicarTesteStatus` restaura os badges

### ARQUIVOS ALTERADOS
- `api/main.py` (versão `1.4.19` → `1.4.20`)
- `frontend/dashboard.html` (`_preencherStatusProvedores` substituída por `_autoTestarProvedores`; chamadas em `carregarProvedoresApi` atualizadas)

---

## V.1.4.19 — Monitor: provedores sempre visíveis + status transcrição
> Data: 09/06/2026 | Feature + Bug fix

### DASHBOARD — Aba Monitor

- **Tabela de Provedores**: sempre exibe os 4 provedores (DeepSeek, OpenAI, Anthropic, Gemini) mesmo sem chamadas registradas — antes exibia "Nenhuma chamada registrada" quando nenhuma análise tinha sido feita após o restart
- **Status real-time**: status usa `provedores_status` do router como fallback quando não há teste manual recente — reflete estado correto sem precisar clicar em "Testar conexão"
- **Transcrição de Áudio**: novo card no Monitor mostrando status de Groq (Whisper Large v3) e OpenAI Whisper, com badge "ATIVO" no provedor em uso

### BACKEND — `/monitor/metricas`

- Campo `transcricao` adicionado ao response: `provedor_ativo`, `groq.status`, `openai_whisper.status` (derivados de presença de chave no `.env`)

### ARQUIVOS ALTERADOS
- `api/main.py` (versão `1.4.18` → `1.4.19`, campo `transcricao` no endpoint)
- `frontend/dashboard.html` (tabela fixa de 4 provedores, card de transcrição)

---

## V.1.4.18 — Fix compatibilidade openai + httpx
> Data: 09/06/2026 | Bug fix

### BUG FIX

- `openai==1.35.7` usava parâmetro `proxies` removido no `httpx>=0.28.0` — causava erro `AsyncClient.__init__() got an unexpected keyword argument 'proxies'` ao testar conexão com DeepSeek/OpenAI no dashboard
- `requirements.txt`: `openai==1.35.7` → `openai>=1.52.0` (compatível com httpx 0.28+)

### ARQUIVOS ALTERADOS
- `requirements.txt`
- `api/main.py` (versão `1.4.17` → `1.4.18`)

---

## V.1.4.17 — Migração para VPS Dedicada + Novo Domínio
> Data: 09/06/2026 | Operação de infraestrutura

### INFRAESTRUTURA

- **Nova VPS dedicada**: Hetzner CPX32 — 4 vCPU AMD, 8GB RAM, 160GB SSD, Helsinki (`37.27.214.33`)
- **MySQL local**: banco migrado de servidor remoto compartilhado (`177.104.186.227`, 676ms) para instância local na própria VPS (`127.0.0.1`, ~2ms) — redução de 338x na latência
- **Novo domínio**: `saleia.app.br` criado no Registro.br e delegado ao Cloudflare (proxy ativo); subdomínio `api.saleia.app.br` configurado
- **Deploy**: `git clone` do GitHub + venv Python 3.14 + systemd `TimeoutStopSec=30` (previne SIGKILL em restart)
- **nginx**: configurado para `api.saleia.app.br` com proxy reverso para `127.0.0.1:8000`
- **Dados migrados**: `mysqldump` do banco compartilhado → import na nova instância; tabelas de outros projetos removidas; 5 tabelas SALEIA preservadas (`admin_route_rules`, `alertas_automaticos`, `api_integrations`, `audit_logs`, `base_conhecimento` com 49 docs RAG)

### BUG FIX — Versão no health endpoint

- `/health` e `/monitor/metricas` tinham versão hardcoded defasada (`1.4.14` e `1.4.15`); corrigidos para `1.4.17`

### ARQUIVOS ALTERADOS
- `api/main.py` (versões `1.4.14`/`1.4.15`/`1.4.16` → `1.4.17`)
- `docs/CURRENT_STATE.md`
- `docs/TASKS.md`
- `CHANGELOG.md`

### DEPLOY
Nova VPS ativa em `37.27.214.33`. Domínio `api.saleia.app.br` aguardando propagação DNS (~2h). VPS antiga (`204.168.180.25`) aguarda descomissionamento.

---

## V.1.4.16 — Próxima Melhor Pergunta (next_best_question)
> Data: 09/06/2026 | Desenvolvido com Claude Sonnet 4.6

### BACKEND — Prompt da IA (`agent/prompt_templates/agente_tempo_real.txt`)

- Seção **LOGICA DA PROXIMA MELHOR PERGUNTA** adicionada ao prompt de tempo real
- 9 categorias de pergunta definidas com lógica de prioridade explícita: `descoberta_dor`, `amplificacao_dor`, `impacto_financeiro`, `urgencia`, `prioridade`, `autoridade`, `objecao`, `fechamento`, `recapitulacao`
- Adaptação por perfil DISC: D (resultado/números), I (visão/cenário), S (segurança/processo), C (dados/critérios)
- Campo `next_best_question` adicionado ao schema JSON de resposta com 7 subcampos: `question`, `category`, `objective`, `reason`, `expected_score_impact`, `urgency_level`, `follow_up_question`
- Fallback neutro para contexto insuficiente (< 50 palavras do cliente)

### BACKEND — Processador tempo real (`api/processador_tempo_real.py`)

- `_FALLBACK_NBQ_QUESTION` e `_fallback_next_best_question()` adicionados ao módulo
- `_normalizar_resposta_realtime`: preenche `next_best_question` com fallback se ausente, não-dict ou question vazia
- `_extrair_ultima_analise_memoria`: propaga `next_best_question` do cache persistido
- `analyzeRealtimeMeeting`: acumula cada `next_best_question` real (não-fallback) como `key_moment` com `type="next_best_question"` — aparecem no relatório pós-reunião em `/historico/uso/{meeting_id}`

### BACKEND — Banco de dados (`api/database.py`)

- `registrar_analise_meeting`: `diagnostico_atual` inclui `next_best_question` — persiste junto ao `current_diagnosis` do `MeetingMemory`

### EXTENSÃO CHROME — Sidebar (`chrome-extension/content.js`, `sidebar.css`)

- Seção `#saleia-proxima-fala` substituída por `#saleia-nbq` com bloco estruturado:
  - Badge de categoria + badge de urgência colorido (vermelho/amarelo/cinza)
  - Label "Objetivo:" em 3–5 palavras
  - Pergunta em destaque dourado entre aspas
  - Motivo (por que perguntar agora) em itálico
  - Impacto esperado no score
  - Botão "📋 Copiar pergunta" (usa `navigator.clipboard`)
- Fallback: se `next_best_question` ausente, exibe `proxima_pergunta` / `proxima_fala` / `texto_falavel` sem badges
- Função `renderizarNBQ(dados)` com mapa de labels por categoria e cores por urgência
- CSS: `.saleia-nbq-box`, `.saleia-nbq-badge`, `.saleia-nbq-urgency`, `.saleia-nbq-objetivo`, `.saleia-nbq-pergunta`, `.saleia-nbq-motivo`, `.saleia-nbq-impacto`

### TESTES (`tests/test_next_best_question.py`)

- 20 testes em 4 suítes: `TestNBQFallback`, `TestNBQNormalizacao`, `TestNBQCenariosNegocio`, `TestNBQPersistencia`
- 8 cenários de negócio: sem dor, dor operacional, objeção de preço, urgência alta, score baixo, score alto, DISC C analítico, decisor ausente
- Resultado: **20/20 OK** em 0.2s — sem chamadas reais de IA ou banco

### ARQUIVOS ALTERADOS
- `agent/prompt_templates/agente_tempo_real.txt`
- `api/processador_tempo_real.py`
- `api/database.py`
- `api/main.py` (versão `1.4.15` → `1.4.16`)
- `chrome-extension/content.js`
- `chrome-extension/sidebar.css`
- `tests/test_next_best_question.py` (novo)
- `docs/CURRENT_STATE.md`
- `docs/TASKS.md`
- `CHANGELOG.md`

### DEPLOY
Não deployado — apenas local + GitHub (produção programada).

---

## V.1.4.15 — Monitor: gastos USD, status real, Dev Manual
> Data: 08/06/2026 | Desenvolvido com Claude Sonnet 4.6

### BACKEND — Cache de resultado de teste por provedor (`api/main.py`)

- `_ultimo_teste: dict` — cache em memória que armazena `{ok, ts, detalhe}` por provedor após cada "Testar conexão"
- `POST /admin/api/teste` salva o resultado no cache após cada chamada
- `GET /monitor/metricas` expõe `ultimo_teste` para o frontend
- `admin_testar_provedor`: modelo Gemini corrigido — usa `os.environ.get("GEMINI_MODEL")` em vez de `"gemini-2.0-flash"` hardcoded
- `GET /monitor/metricas` inclui `provedores_status` (circuit breaker + chave) em resposta ao endpoint

### BACKEND — Monitoramento de gastos (`api/ai_router.py`)

- `_counters` ampliado com `custo_total_usd` (global) e `custo_usd` por provedor
- `chamar_ia()` acumula custo estimado USD a cada chamada bem-sucedida
- `snapshot_metricas()` expõe `custo_total_usd` e `custo_usd` por provedor com arredondamento 6 casas

### FRONTEND — Monitor atualizado (`frontend/dashboard.html`)

- Card **💰 Gasto (USD)** com total acumulado desde o último restart
- Coluna **Custo (USD)** na tabela de provedores (valores em dourado)
- Coluna **STATUS ATUAL** usa `ultimo_teste` como fonte principal:
  - ✅ Online / ❌ Offline com tempo decorrido ("agora", "5min atrás")
  - Fallback para status do circuit breaker se nenhum teste foi realizado
- `Sem chave` / `cooldown` / `degradado` exibidos com cores distintas

### FRONTEND — Dev Manual (`frontend/manual_tecnico.html`)

- Reescrito com tema gold/black do sistema
- Seções: Arquitetura, VPS/Infra, Deploy, Variáveis de Ambiente, Estrutura de Arquivos, Endpoints, Roteador de IA, Banco de Dados, Monitor, Segurança, Troubleshoot
- Comandos prontos para copiar (SSH, SCP, diagnóstico)
- Link **🛠️ Dev Manual** adicionado na sidebar do dashboard
- Acessível em `/manual-tecnico` (rota já existia em `main.py`)

### VALIDAÇÕES

- Gasto USD acumulando corretamente por provedor ✅
- STATUS ATUAL reflete resultado do último teste real ✅
- Dev Manual acessível em produção ✅
- Modelo Gemini no teste usa variável de ambiente ✅

### ARQUIVOS ALTERADOS
- `api/main.py`
- `api/ai_router.py`
- `frontend/dashboard.html`
- `frontend/manual_tecnico.html`
- `docs/CURRENT_STATE.md`
- `CHANGELOG.md`

### DEPLOY
- Todos os arquivos deployados via SCP para `/opt/saleia/`
- `systemctl restart saleia` executado

---

## V.1.4.14 — Fix monitor provedores + inativar API + ordem DeepSeek + RAG restaurado
> Data: 08/06/2026 | Desenvolvido com Claude Sonnet 4.6

### BACKEND — Monitor: contador de provedores sem chave (`api/ai_router.py`)

- Provedores pulados por `missing_api_key` agora incrementam `_counters["por_provedor"][name]["falha"]`
- Antes: provedor sem chave aparecia como 0/0 no Monitor (invisível, sem diagnóstico)
- Após: exibe falha no Monitor com log `WARNING: Skipping {name}: API key not configured`

### BACKEND — Fix botão "Inativar" na gestão de APIs (`api/main.py`)

- `admin_listar_provedores`: campo `ativo` agora lê `os.environ.get(env_key)` (estado em runtime) em vez de `_ler_env().get(env_key)` (arquivo .env)
- Causa do bug: ao inativar, o backend zerova `os.environ[env_key]` em memória, mas ao recarregar a lista o endpoint lia o arquivo .env (que ainda tinha a chave) e devolvia `ativo: true` — o botão revertia imediatamente
- Separação: `tem_chave` continua lendo do arquivo (indica se existe chave salva); `ativo` reflete o estado de execução

### VPS — Ordem dos provedores corrigida

- `data/ai_provider_order.json` ajustado para `deepseek → openai → anthropic → gemini`
- Estava `anthropic → openai → gemini → deepseek` — Anthropic resolvia tudo, DeepSeek nunca era chamado
- Monitor agora exibe contadores corretos por provedor

### VPS — Modelo Gemini atualizado

- `GEMINI_MODEL` atualizado de `gemini-2.0-flash` (retornava 404 — modelo descontinuado) para `gemini-2.5-flash`

### VPS — RAG restaurado (OpenAI embeddings)

- Chave `OPENAI_API_KEY` renovada via painel admin
- Embedding `text-embedding-3-small` testado: 1536 dimensões ✅
- Base de conhecimento com 49 transcrições indexadas

### VALIDAÇÕES

- DeepSeek: ✅ Online, PRINCIPAL — primeiro na cadeia
- OpenAI: ✅ Online — fallback + RAG/embeddings funcionando
- Embedding test: `OK dimensoes: 1536` ✅
- Botão "Inativar" atualiza corretamente o estado visual após click ✅

### ARQUIVOS ALTERADOS
- `api/ai_router.py`
- `api/main.py`
- `docs/CURRENT_STATE.md`
- `CHANGELOG.md`

### DEPLOY
- `api/ai_router.py` e `api/main.py` deployados via SCP para `/opt/saleia/`
- `data/ai_provider_order.json` corrigido diretamente na VPS
- `GEMINI_MODEL` atualizado no `.env` da VPS via `sed`
- `systemctl restart saleia` executado

---

## V.1.4.13 — Observabilidade: OTel fix + Grafana Cloud Tempo ativo + Monitor auth
> Data: 07/06/2026 | Desenvolvido com Claude Sonnet 4.6

### BACKEND — Fix instrumentação OpenTelemetry (`api/main.py`)

- `_configurar_opentelemetry()` movida do `on_startup` para o **nível do módulo** (chamada imediatamente após o setup de middlewares)
- Causa do bug: `FastAPIInstrumentor.instrument_app(app)` chamado dentro do `on_startup` era tarde demais — o Starlette já havia finalizado o middleware stack antes da primeira requisição, impedindo a geração de spans para rotas HTTP
- Resultado: traces de todas as rotas FastAPI (`GET /health`, `POST /tempo-real`, etc.) agora chegam ao **Grafana Cloud Tempo** em tempo real
- Versão bumped para `1.4.13`

### FRONTEND — Auth interceptor global (`frontend/dashboard.html`)

- Adicionado interceptor de `window.fetch` no topo do script principal
- Injeta automaticamente `Authorization: Bearer <token>` em todas as requisições para `api.saleia.com.br` ou rotas relativas (`/...`) quando `saleia_token` existe no localStorage
- Elimina a necessidade de passar headers de auth manualmente em cada chamada `fetchJsonWithFallback()`
- Corrige o erro `HTTP 401` na aba Monitor (endpoints `/monitor/metricas` e `/monitor/historico`)

### VALIDAÇÕES

- Grafana Cloud Tempo: query `{}` retorna múltiplos traces `saleia` — `GET /health`, `GET /monitor/metricas`, etc. ✅
- OTel startup log: `"OpenTelemetry ativo → https://otlp-gateway-prod-sa-east-1.grafana.net/otlp"` (2 workers) ✅
- Serviço ativo após deploy: `systemctl is-active saleia` → `active` ✅

### ARQUIVOS ALTERADOS
- `api/main.py`
- `frontend/dashboard.html`
- `docs/CURRENT_STATE.md`
- `CHANGELOG.md`

### DEPLOY
- Arquivos deployados via SCP para `/opt/saleia/`
- `systemctl restart saleia` executado
- `GET /health` → `versao: 1.4.13`, `status: online` ✅

---

## V.1.4.12 — Fase 3 Observabilidade: Histórico SQLite + Alertas threshold + Sparklines
> Data: 07/06/2026 | Desenvolvido com Claude Sonnet 4.6

### BACKEND — Histórico de métricas SQLite (`api/metricas_historico.py` — novo)

- Tabela `metricas_historico` em `data/metricas.db` (SQLite)
- Colunas: `ts`, `banco_latencia`, `banco_modo`, `reunioes_ativas`, `reunioes_hoje`, `chamadas_ia`, `falhas_ia`
- `criar_tabela_metricas()` — cria tabela + índice em ts
- `registrar(banco, ativas, hoje, chamadas, falhas)` — deduplicação por DB: ignora se já existe linha nos últimos 55s (safe com 2 workers uvicorn)
- `obter(horas=6)` — retorna lista ordenada das últimas N horas (máx 24h)
- Limpeza automática: deleta linhas com mais de 25h a cada inserção

### BACKEND — Background task e endpoint historico (`api/main.py`)

- `on_startup` convertido de `def` → `async def` para suportar `asyncio.create_task`
- `_loop_metricas()` async: loop com `asyncio.sleep(60)`, startup delay de 15s
  - Coleta: `db_health()`, `contar_reunioes_ativas()`, `contar_reunioes_hoje()`, `snapshot_metricas()`
  - Grava snapshot via `metricas_historico.registrar()`
  - Chama `alertas.verificar_thresholds(ia_snap, banco)`
  - Tolerante a erros: nunca derruba o loop
- `GET /monitor/historico?horas=N` (requer JWT): retorna série temporal das últimas N horas

### BACKEND — Alertas por threshold (`agent/alertas.py`)

- `_last_alerta: dict` e `_COOLDOWN_S = 3600` — cooldown de 1h por tipo
- `_pode_alertar(chave)` — controla cooldown
- `verificar_thresholds(metricas_ia, banco)` — verifica:
  - Banco offline (erro não nulo)
  - Banco lento (latência > 1500 ms)
  - Taxa de erro IA > 30% (mínimo 10 chamadas)
  - Fallback rate > 50% das chamadas com sucesso

### FRONTEND — Sparklines no Monitor tab (`frontend/dashboard.html`)

- Seção "Histórico — últimas 6h" adicionada no Monitor tab
- `_carregarHistoricoMonitor()` — chama `GET /monitor/historico?horas=6`
- `_sparklineSVG(values, color, unit)` — SVG polyline com gradient fill, dot no valor atual, label de valor
- `_renderHistorico(pontos)` — renderiza 4 sparklines:
  - Latência banco (ms) — amarelo
  - Reuniões ativas — azul
  - Chamadas IA (acumulado) — roxo
  - Reuniões hoje — verde
- Auto-refresh de 60s (alinhado com o background task) enquanto o Monitor tab está aberto

### INFRA — Templates Grafana Cloud (`infra/`)

- `infra/grafana-alloy.alloy` — config pronta para Grafana Alloy com placeholders GRAFANA_CLOUD_URL / USER / API_KEY
- `infra/grafana-setup.sh` — script de instalação do Grafana Alloy na VPS
- Comentários completos com instruções passo a passo

### ARQUIVOS ALTERADOS
- `api/metricas_historico.py` (novo)
- `api/main.py`
- `agent/alertas.py`
- `frontend/dashboard.html`
- `infra/grafana-alloy.alloy` (novo)
- `infra/grafana-setup.sh` (novo)
- `docs/CURRENT_STATE.md`
- `CHANGELOG.md`

### DEPLOY
- 4 arquivos deployados via SCP para `/opt/saleia/`
- `systemctl restart saleia` executado
- Validação: `GET /health` → `versao: 1.4.12`, `status: online`
- Validação: `GET /monitor/historico` → 401 sem token ✅
- Validação: `data/metricas.db` criado (16K), 1° snapshot com latência 678ms (MySQL) ✅

---

## V.1.4.11 — Fase 2 Observabilidade: Métricas IA + aba Monitor
> Data: 07/06/2026 | Desenvolvido com Claude Sonnet 4.6

### BACKEND — Contadores de uso da IA em memória (`api/ai_router.py`)

- `import threading` adicionado
- `_counters_lock = threading.Lock()` + `_counters` dict criados após `_breakers`
- Contadores: `chamadas_total`, `chamadas_sucesso`, `chamadas_falha`, `fallbacks`, `circuit_breaker_aberturas`, `por_provedor[name]{sucesso, falha, total_ms}`
- `chamar_ia()` instrumentado: incrementa contadores no início, em cada sucesso/falha de provedor e no 503 final
- `fallbacks` incrementado quando há ao menos 1 falha antes do sucesso
- `CircuitBreaker.register_failure()` incrementa `circuit_breaker_aberturas` ao abrir
- `snapshot_metricas() → dict` exporta cópia thread-safe com `uptime_segundos` e `latencia_media_ms` por provedor

### BACKEND — Endpoint de métricas (`api/main.py`)

- `snapshot_metricas` importado de `ai_router`
- `GET /monitor/metricas` adicionado após `/health`
  - Requer JWT (`_req_auth`)
  - Retorna: `ia` (snapshot_metricas), `banco` (modo/latencia/erro), `reunioes_ativas`, `reunioes_hoje`, `versao`, `timestamp`
- Versão atualizada para `1.4.11`

### FRONTEND — Aba Monitor (`frontend/dashboard.html`)

- Nav item "📡 Monitor" adicionado antes de "Visual Cenário"
- `<div id="page-monitor">` adicionado antes de `page-configuracoes`
  - Cards: Uptime, Chamadas, Sucesso, Falha, Fallbacks, Circuit Breaks, Reuniões Ativas, Reuniões Hoje
  - Tabela de provedores: Sucesso / Falha / Latência Média / Taxa de Sucesso %
  - Card de banco: modo, latência, status
- `mostrarPagina()` atualizado: `_iniciarMonitor()` ao entrar, `_pararMonitor()` ao sair
- `_iniciarMonitor()` / `_pararMonitor()`: controla `setInterval` de 15 s
- `carregarMonitor()`: chama `GET /monitor/metricas`, renderiza via `_renderMonitor()`
- Contadores zerados ficam com cor `var(--muted)` para indicar inatividade

### ARQUIVOS ALTERADOS
- `api/ai_router.py`
- `api/main.py`
- `frontend/dashboard.html`
- `docs/CURRENT_STATE.md`
- `CHANGELOG.md`

### DEPLOY
- 3 arquivos deployados via SCP para `/opt/saleia/`
- `systemctl restart saleia` executado
- Validação: `GET /health` → `versao: 1.4.11`, `status: online`
- Validação: `GET /monitor/metricas` sem token → 401 ✅; módulo `snapshot_metricas()` testado diretamente → retorna estrutura correta ✅

---

## V.1.4.10 — Toggle de chave API e badge de status persistente
> Data: 07/06/2026 | Desenvolvido com Claude Sonnet 4.6

### DASHBOARD — Botão 👁 nos campos de chave de API (`frontend/dashboard.html`)

**Problema:** Os campos de chave dos provedores (DeepSeek, OpenAI, Anthropic, Gemini) usavam `type="password"` sem toggle de visibilidade. O Chrome tratava o campo como senha e preenchia automaticamente com a última senha salva no gerenciador, sobrepondo a chave real.

**Solução:**
- `autocomplete="new-password"` substituiu `autocomplete="off"` — instrução efetiva para o Chrome não sugerir senhas salvas nesses campos
- Botão 👁 adicionado entre o campo de chave e o botão "Salvar" em cada card de provedor
- Função `toggleVerChave(pid, btn)` adicionada — alterna `input.type` entre `password` e `text`; ícone muda para 🙈 quando visível
- Mesma lógica já existente no campo Groq (V.1.4.5) aplicada aos 4 provedores principais

### DASHBOARD — Badge de status persistente após teste de conexão (`frontend/dashboard.html`)

**Problema:** O botão "Testar conexão" mostrava "✅ Conectado" no span de feedback mas limpava o texto após 4 segundos via `setTimeout`. Não havia forma de confirmar visualmente que a API estava online após o teste.

**Solução:**
- `<span id="status-teste-${p.id}">` adicionado na linha de badges de cada card (ao lado de "Ativo/Inativo" e "Principal")
- `testarProvedor(id)` reescrito:
  - **Sucesso:** badge `✅ Online` (dourado, estilo gold do tema) inserido permanentemente no `status-teste-${id}`; feedback de texto limpo imediatamente
  - **Falha / sem resposta:** badge `❌ Offline` inserido no mesmo slot; mensagem de erro no span de feedback desaparece após 4 s
- O badge persiste até o usuário fechar e reabrir o accordion (quando os cards são re-renderizados)

### ARQUIVOS ALTERADOS

| Arquivo | Tipo |
|---|---|
| `frontend/dashboard.html` | feat: toggle 👁 + `autocomplete="new-password"` + badge `status-teste` permanente + `testarProvedor` reescrito |

---

## T18 — Deploy V.1.4.3–V.1.4.9 na VPS
> Data: 07/06/2026 | Desenvolvido com Claude Sonnet 4.6

### DEPLOY — VPS `204.168.180.25` (`/opt/saleia/`)

17 arquivos enviados via SCP com chave `saleia_vps`:

| Arquivo | Versão |
|---|---|
| `api/main.py` | V.1.4.3+ |
| `agent/sessao_manager.py` | V.1.4.3 |
| `requirements.txt` | V.1.4.5 |
| `frontend/dashboard.html` | V.1.4.8 |
| `frontend/visual-scenario.html` | V.1.4.8 |
| `frontend/cenario.html` | V.1.4.8 |
| `frontend/login.html` | V.1.4.6 |
| `frontend/logo-saleia.png` | V.1.4.6 (novo) |
| `frontend/manual.html` | V.1.4.9 |
| `chrome-extension/background.js` | V.1.4.1 |
| `chrome-extension/manifest.json` | V.1.4.8 |
| `chrome-extension/popup.html` | V.1.4.8 |
| `chrome-extension/popup.js` | V.1.4.1 |
| `chrome-extension/popup.css` | V.1.4.8 |
| `chrome-extension/sidebar.css` | V.1.4.8 |
| `chrome-extension/content.css` | V.1.4.8 |
| `chrome-extension/content.js` | V.1.4.8 |

**Resultado:**
- `pip install -r requirements.txt` — OK (groq instalado)
- `systemctl restart saleia` — `active`
- `GET /health` — `online`, 4 provedores ok (anthropic/openai/gemini/deepseek)
- `GET /dashboard` — 200
- `GET /logo-saleia.png` — 200

**Pendente após deploy:**
- Reinstalar extensão Chrome no navegador (tema gold/black + multi-clientes)

---

## V.1.4.9 — Manual de instruções atualizado para V.1.4.8
> Data: 06/06/2026 | Desenvolvido com Claude Sonnet 4.6

### DOCS — Reescrita completa do manual (`frontend/manual.html`)

Manual atualizado de V.1.4.5 para V.1.4.8 com todas as funcionalidades documentadas:

- **Versão** atualizada para 1.4.8 no badge do cabeçalho e rodapé
- **Nova seção 7 — Cenário do Cliente:** slides interativos, botões de condução (DISC, Recapitulação, Diagnóstico, Fechamento), uso em segundo monitor
- **Nova seção 8 — Visual Cenário AI:** as três colunas (Cliente / Cenário Atual / Cenário Futuro), como vincular à reunião (link completo ou só o código), passo a passo de uso, tabela de botões, fullscreen e comparação, histórico, aviso DALL-E 3
- **Seção 3 — Extensão Chrome:** documentado suporte a múltiplos clientes no modal Participantes (botão **+ Adicionar**, botão ✕, persistência via `chrome.storage.local`)
- **Seção 10 — Relatório:** documentado campo multi-clientes na análise manual (Dashboard → Relatórios) com explicação de por que informar vários nomes melhora a precisão
- **Seção 11 — Dashboard:** adicionados links para Cenário do Cliente e Visual Cenário AI
- **Seção 14 — FAQ:** novas entradas para multi-clientes, botão Início do Visual Cenário, Visual Cenário sem meeting_id, análise de reuniões já encerradas
- **Nav sticky:** link "Visual Cenário" adicionado na barra de navegação
- **Bloco de ações rápidas** no rodapé: botões diretos para Dashboard, Visual Cenário AI, Status e Login

**Arquivo alterado:**
- `frontend/manual.html` — reescrita completa, V.1.4.5 → V.1.4.8

---

## V.1.4.8 — Multi-clientes, correções de navegação e redesign extensão
> Data: 06/06/2026 | Desenvolvido com Claude Sonnet 4.6

### FRONTEND — Múltiplos clientes na análise (`dashboard.html`)
- Campo "Cliente" substituído por lista dinâmica de clientes
- Botão **+ Cliente** permite adicionar quantos clientes forem necessários
- Botão ✕ remove clientes extras (mínimo 1 sempre presente)
- `analisar()` coleta array `clientes[]` de `_clientesLista`
- `detectarFalas()` atualizado: recebe `nomes.clientes[]` e identifica fala de qualquer cliente pelo nome
- Speaker das falas preserva nome original (não colapsa tudo em um "Cliente" único)

### FRONTEND — Correção botão "Início" (`visual-scenario.html`)
- Botão "← Início" corrigido: volta para `/cenario/{meeting_id}` em vez de `/` (que deslogava)
- Fallback para `/dashboard` quando não há meeting ID
- Extrai só o código da reunião mesmo que o `meetingId` seja a URL completa do Google Meet (`https://meet.google.com/xxx` → `xxx`)

### FRONTEND — Paleta gold/black na tela Cenário do Cliente (`cenario.html`)
- Variáveis CSS: `--bg #0A0A0A`, `--card #111111`, `--card2 #000000`, `--borda rgba(212,175,55,0.18)`
- `--verde/#azul/#roxo` → `#D4AF37`/`#F5C542` (dourado)
- Header, dropdowns, overlay, painéis, chips e botões atualizados

### EXTENSÃO CHROME — Paleta gold/black
**`popup.css`:** Background `#0A0A0A`, header gradiente preto, teal `#14B8A6` → `#D4AF37`, laranja → dourado, toggle/inputs/botões/links em ouro

**`sidebar.css`:** Fundo `rgba(0,0,0,0.97)`, bordas douradas, seções/recap/badges/temperatura/modal em ouro, dot pulsante dourado

**`content.css`:** Background, header, cards, hover — padrão preto/dourado

### EXTENSÃO CHROME — Multi-clientes no modal Participantes (`content.js`)
- Modal "Participantes": campo "Nome do cliente" → lista dinâmica **"Clientes"** com botão **"+ Adicionar"**
- Botão ✕ por linha remove cliente (mínimo 1)
- Event delegation via `container.onclick`/`container.oninput` com `data-ri`/`data-ci` (fix: inline `onclick` não funciona no mundo isolado do content script)
- `salvarParticipantes()`: lê inputs diretamente via `querySelectorAll('[data-ci]')` para garantir valores corretos
- `rotuloParticipante()`: identifica fala contra todos os clientes do array
- `atualizarResumoParticipantes()`: exibe `Vendedor -> Cliente1, Cliente2`
- Migração automática de dados antigos: `{ cliente: "X" }` → `{ clientes: ["X"] }`
- `estado.participantes.clientes` persiste via `chrome.storage.local`

**Arquivos alterados:**
- `frontend/dashboard.html` — multi-clientes + menu "Visual Cenário"
- `frontend/visual-scenario.html` — botão Início corrigido + paleta gold
- `frontend/cenario.html` — paleta gold/black completa
- `chrome-extension/popup.css` — paleta gold/black
- `chrome-extension/sidebar.css` — paleta gold/black
- `chrome-extension/content.css` — paleta gold/black
- `chrome-extension/content.js` — multi-clientes com event delegation

---

## V.1.4.7 — Visual Cenário: paleta gold/black + correção de nomenclatura
> Data: 06/06/2026 | Desenvolvido com Claude Sonnet 4.6

### FRONTEND — Padronização visual da tela Visual Cenário

**`frontend/visual-scenario.html` — redesign de cores:**
- Paleta CSS atualizada para o padrão gold/black do dashboard:
  - `--bg: #0A0A0A`, `--card: #111111`, `--field: #1A1A1A`
  - `--border: rgba(212,175,55,0.18)`, `--primary: #D4AF37`, `--secondary: #F5C542`
  - `--muted: #888`, `--gold: #D4AF37`
- Header: fundo `#000000` (era `#201E30` roxo)
- Action bar: fundo `rgba(0,0,0,.4)` (era roxo semi-transparente)
- Botão primário: gradiente `#A67C00 → #D4AF37 → #F5C542`, texto preto (era teal)
- Ícones de painel: dourado sutil (era azul/teal)
- Chips de contexto (`chip-disc`, `chip-maturity`): ouro (era azul/teal)
- Toast de sucesso: dourado (era teal)
- Loading overlay: `rgba(0,0,0,.92)` (era roxo escuro)
- Spinner border: `rgba(212,175,55,.2)` (era teal)
- Modal fullscreen: fundo `#000000` (era `#0A0914`)
- Modal crop: fundo `#000000` + botão confirmar em gradiente dourado
- Hover dos painéis: borda dourada `rgba(212,175,55,.35)`
- Título `<title>` e `<h1>`: "Visual **Cenário** AI" (era "Visual Scenario AI")

**`frontend/dashboard.html` — correção de nomenclatura:**
- Item do menu lateral: "Visual Scenario" → "Visual Cenário"

---

## V.1.4.6 — Redesign Visual Premium (Gold/Black Theme)
> Data: 06/06/2026 | Desenvolvido com Claude Sonnet 4.6

### FRONTEND — Redesign completo da identidade visual

Aplicada nova paleta de cores premium em toda a plataforma, sem alteração de funcionalidades.

**Paleta adotada:**
- Dourado metálico: `#D4AF37` (nova cor primária — substituiu teal `#14B8A6`)
- Dourado brilhante: `#F5C542` (secundária — substituiu azul `#38BDF8`)
- Preto absoluto: `#000000` (sidebar)
- Preto premium: `#0A0A0A` (fundo geral)
- Cinza grafite: `#111111` (cards)
- Cinza tecnológico: `#1A1A1A` (inputs/fields)

**`dashboard.html` — mudanças visuais:**
- Todas as variáveis CSS atualizadas (`--bg`, `--card`, `--field`, `--border`, `--primary`, `--secondary`)
- Sidebar: fundo `#000000` (antes roxo `#201E30`)
- Nav itens ativos/hover: dourado `rgba(212,175,55,...)` (antes laranja `rgba(249,115,22,...)`)
- Botão principal: gradiente dourado `#A67C00 → #D4AF37 → #F5C542` (antes laranja/vermelho)
- Badges e indicadores: dourado (antes teal/azul)
- Accordion aberto: borda dourada `rgba(212,175,55,.35)`
- Ícones de accordion: fundo dourado discreto
- Background tecnológico: grid de linhas douradas sutis + glow radial no topo
- Tipografia: `Inter` + `Sora` via Google Fonts (antes Segoe UI)
- Focus inputs: glow dourado `rgba(212,175,55,.12)`

**`login.html` — mudanças visuais:**
- Logo SALEIA original (PNG premium 3D dourado) integrado via Nginx static location
- Imagem exibida com `object-fit: cover` + `object-position: top` mostrando S + SALEIA + tagline
- Removidos: badge de versão, taglines duplicadas, espaçamentos excessivos
- Padding do body reduzido para melhor fit em mobile

**Nginx (`/etc/nginx/sites-enabled/saleia`) — nova location:**
```nginx
location = /logo-saleia.png {
    alias /opt/saleia/frontend/logo-saleia.png;
    add_header Cache-Control "public, max-age=2592000";
}
```

**Arquivos alterados:**
- `frontend/dashboard.html` — redesign CSS completo
- `frontend/login.html` — logo + layout compacto
- `frontend/logo-saleia.png` — logo PNG premium adicionado (novo)

---

## V.1.4.5 — SDK Groq Oficial, Toggle de Chave e Separação de Ações
> Data: 06/06/2026 | Desenvolvido com Claude Sonnet 4.6

### BACKEND — SDK oficial Groq

Substituído o workaround `OpenAI(base_url="https://api.groq.com/openai/v1")` pelo SDK oficial `groq>=0.9.0`:

- Pacote `groq>=0.9.0` adicionado ao `requirements.txt`
- Modelo atualizado de `whisper-large-v3-turbo` para `whisper-large-v3` (maior qualidade)
- Arquivo passado como tupla `(caminho, bytes)` conforme documentação oficial Groq
- Flag `temperature=0` e `response_format="verbose_json"` adicionados

### BACKEND — Flag `apenas_salvar` no endpoint de transcrição

`POST /admin/transcricao/config` aceita novo campo `apenas_salvar: bool`:

- `apenas_salvar: true` → salva a chave Groq no `.env` **sem** mudar o provedor ativo
- `apenas_salvar: false` (padrão) → comportamento anterior: salva chave e ativa o provedor
- Validação de tamanho mínimo da chave removida (qualquer string não vazia é aceita)

### DASHBOARD — Botão 👁 mostrar/ocultar chave Groq

- Botão 👁 ao lado do campo de senha: alterna entre `type="password"` e `type="text"`
- Ícone muda para 🙈 quando a chave está visível
- Função `toggleVerChaveGroq()` adicionada

### DASHBOARD — Correção crítica em `salvarChaveGroq`

- Substituído `fetch(API + '/admin/...')` por `fetchJsonWithFallback('/admin/...')` — corrige falha silenciosa quando `API` aponta para URL incorreta
- `apenas_salvar: true` enviado: salvar chave não muda mais o provedor ativo
- Após salvo com sucesso, recarrega o accordion automaticamente via `carregarTranscricaoConfig()`
- Mensagem de erro agora inclui o status HTTP (`Erro 401`, `Erro 400`, etc.)

### EXTENSÃO CHROME — Visibilidade de erros de transcrição

`enviarChunkWhisper` em `content.js` agora exibe erros do backend na barra de status da sidebar:

- `data.ok === false` ou `data.error` → `setAudioStatus('⚠️ ' + msgErro, '#ff9900')`
- Antes: erros apenas no `console.warn`, invisíveis ao usuário

### ARQUIVOS ALTERADOS

| Arquivo | Tipo |
|---|---|
| `requirements.txt` | feat: `groq>=0.9.0` |
| `api/main.py` | feat: SDK Groq oficial; flag `apenas_salvar`; validação de chave relaxada |
| `frontend/dashboard.html` | feat: toggle 👁; fix `fetchJsonWithFallback`; `apenas_salvar: true` |
| `chrome-extension/content.js` | fix: erros de transcrição exibidos na sidebar |

---

## V.1.4.4 — Transcrição de Áudio com Whisper e Groq
> Data: 06/06/2026 | Desenvolvido com Claude Sonnet 4.6

### BACKEND — Roteamento de provedor em `/audio-transcricao`

O endpoint `/audio-transcricao` agora lê `TRANSCRICAO_PROVEDOR` do `.env` para decidir qual API usar:

| Valor | Provedor | Modelo | Chave necessária |
|---|---|---|---|
| `whisper` (padrão) | OpenAI Whisper | `whisper-1` | `OPENAI_API_KEY` |
| `groq` | Groq | `whisper-large-v3-turbo` | `GROQ_API_KEY` |

A Groq usa a mesma interface da OpenAI SDK com `base_url="https://api.groq.com/openai/v1"` — nenhuma dependência nova. O rótulo salvo na transcrição bruta passou de `[Whisper]` para `[Whisper]` ou `[Groq]` conforme o provedor ativo. O response agora inclui `provedor`.

### BACKEND — Novos endpoints de configuração

| Endpoint | Método | Descrição |
|---|---|---|
| `/admin/transcricao/config` | GET | Retorna provedores disponíveis, provedor ativo, modelo e se a chave existe |
| `/admin/transcricao/config` | POST | Define o provedor ativo; aceita `groq_api_key` opcional para salvar a chave Groq |

Ambos exigem JWT admin.

### DASHBOARD — Novo accordion "Transcrição de Áudio"

Adicionado entre "Configuração de APIs" e "Base de Conhecimento" na página Configurações:

- Cards para Whisper (OpenAI) e Groq com nome, modelo e nota informativa
- Card do Groq exibe campo de senha para colar a `GROQ_API_KEY`
- Botão "Usar este provedor" envia chave (se preenchida) e ativa o provedor
- Feedback inline de sucesso/erro; recarrega após ativação para refletir novo estado

### ARQUIVOS ALTERADOS

| Arquivo | Tipo |
|---|---|
| `api/main.py` | feat: `_TRANSCRICAO_PROVEDORES`, `GET/POST /admin/transcricao/config`, roteamento em `/audio-transcricao` |
| `frontend/dashboard.html` | feat: accordion `acc-transcricao`, funções `carregarTranscricaoConfig`, `renderizarTranscricaoConfig`, `ativarTranscricaoProvedor` |
| `.env.example` | docs: `GROQ_API_KEY` e `TRANSCRICAO_PROVEDOR` |

---

## V.1.4.3 — Correção de Bugs e Refatoração
> Data: 06/06/2026 | Desenvolvido com Claude Sonnet 4.6

### BUGS CORRIGIDOS

| # | Arquivo | Problema | Solução |
|---|---|---|---|
| 1 | `agent/sessao_manager.py` | `exportar_para_base_conhecimento` usava coluna `conteudo` no CREATE TABLE e INSERT — a coluna real é `texto`; toda exportação de sessão para a Base de IA falhava silenciosamente | Renomeado `conteudo` → `texto` na DDL e no INSERT |
| 2 | `agent/sessao_manager.py` | Invalidação do cache RAG após exportação chamava `_cache.clear()` — isso limpa o dict em memória mas deixa `_cache is not None`, fazendo `_carregar_cache()` retornar `{}` sem recarregar e causando `KeyError` na próxima consulta | Substituído por `invalidar_cache()` (que seta `_cache = None`) |
| 3 | `api/main.py` | `PATCH /admin/api/provedores/{pid}/status` com `ativo=False` não propagava a desativação ao `os.environ` — provedor continuava sendo usado pelo `ai_router` | Adicionado `os.environ[env_key] = ""` quando `ativo=False` e `os.environ[env_key] = chave` quando `ativo=True` |
| 4 | `api/main.py` | Importação de `db_salvar`, `db_listar`, `db_ultimo` duplicada nas linhas 33 e 67 | Removida a segunda importação (linha 67) |
| 5 | `api/main.py` | `admin_definir_principal` setava `os.environ["PROVEDOR_PREFERIDO"]` manualmente logo após chamar `_salvar_env_key` que já faz isso internamente | Removida linha redundante |

### ARQUIVOS ALTERADOS

| Arquivo | Tipo |
|---|---|
| `agent/sessao_manager.py` | fix: `conteudo` → `texto` em `exportar_para_base_conhecimento`; `invalidar_cache()` correto |
| `api/main.py` | fix: propagação de status do provedor; remoção de import duplicado e `os.environ` redundante |

---

## V.1.4.2 — Filtro por Provedor de IA em Reuniões
> Data: 06/06/2026 | Desenvolvido com Claude Sonnet 4.6

### BACKEND — `GET /relatorios` com campo `provedor`

O endpoint `/relatorios` agora inclui o campo `provedor` em cada item da lista.

**Origem do valor:** extraído de `_provedor_ia` armazenado dentro de `dados.recapitulacao` (ou `dados.perfil_disc` / `dados.diagnostico_financeiro` como fallback). Funciona tanto para a fonte SQLite quanto para o fallback de arquivos JSON.

**Valores possíveis:** `deepseek`, `openai`, `anthropic`, `gemini` ou `""` (vazio para relatórios anteriores que não tinham o campo).

### FRONTEND — Filtro de provedor no toolbar de Reuniões (`frontend/dashboard.html`)

- `<select id="filtro-provedor">` adicionado ao toolbar após o filtro de propensão, com opções: Todos os provedores / DeepSeek / OpenAI / Anthropic / Gemini.
- `filtrarReunioes()` atualizada para incluir o filtro por `r.provedor`.
- `limparFiltrosReunioes()` atualizada para resetar o select de provedor.
- `cardReuniaoHTML()` exibe o nome do provedor como label discreta (`var(--muted)`) ao lado da data/score no card de cada reunião.

### ARQUIVOS ALTERADOS

| Arquivo | Tipo de alteração |
|---|---|
| `api/main.py` | feat: campo `provedor` no response de `GET /relatorios` (SQLite + fallback JSON) |
| `frontend/dashboard.html` | feat: select filtro-provedor, filtrarReunioes, limparFiltrosReunioes, cardReuniaoHTML |

---

## V.1.4.1 — Recuperação de Senha por E-mail + Correção de Bug Crítico na Extensão Chrome
> Data: 29/05/2026 | Desenvolvido com Claude Sonnet 4.6

---

### RECUPERAÇÃO DE SENHA — IMPLEMENTAÇÃO REAL (`api/main.py`, `agent/sessao_manager.py`, `agent/email_service.py`)

**Problema anterior:** `POST /auth/recuperar-senha` era um stub que apenas confirmava recebimento sem enviar e-mail.

**Solução completa:**

**Novo módulo `agent/email_service.py`:**
- Envio de e-mail HTML via `smtplib` (stdlib — nenhuma dependência nova)
- Configurado por variáveis de ambiente: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM`, `APP_BASE_URL`
- Link formatado com botão estilizado no tema SALEIA (dark)
- Retorna `True`/`False` para controle do caller; falha não derruba o endpoint

**Migração de banco — `agent/sessao_manager.py`:**
- `migrar_colunas_usuarios()` — adiciona `reset_token VARCHAR(128)` e `reset_token_exp DATETIME` via `ALTER TABLE` idempotente (ignora erro se coluna já existe)
- Chamada no startup junto com `criar_tabela_usuarios()`

**`api/main.py` — 3 novos endpoints + 1 substituição:**

| Endpoint | Método | Descrição |
|---|---|---|
| `/auth/recuperar-senha` | POST | **Substituído**: gera token seguro (`secrets.token_urlsafe(32)`), expira em 1h, salva no banco, envia e-mail em `BackgroundTask`. Resposta sempre neutra. |
| `/reset` | GET | Serve página HTML inline com formulário de nova senha. Retorna 400 se token ausente. |
| `/auth/redefinir-senha` | POST | Valida token + expiração, aplica `bcrypt`, limpa `reset_token` e `reset_token_exp`. |

**Novo model Pydantic:**
```python
class AuthRedefinirSenhaRequest(BaseModel):
    token: str
    nova_senha: str
```

**Fluxo completo:**
1. Usuário clica "Recuperar senha" no `login.html`
2. `POST /auth/recuperar-senha { email }` → gera token, salva no banco, envia e-mail em background
3. Usuário recebe e-mail com link `https://api.saleia.com.br/reset?token=<token>`
4. `GET /reset?token=...` → página HTML com formulário de nova senha
5. `POST /auth/redefinir-senha { token, nova_senha }` → valida, aplica hash bcrypt, limpa token
6. Usuário volta ao login

**`.env.example` atualizado:**
```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=seu-email@gmail.com
SMTP_PASS=sua-senha-de-app-google
EMAIL_FROM=noreply@saleia.com.br
APP_BASE_URL=https://api.saleia.com.br
```

---

### EXTENSÃO CHROME — CORREÇÃO DE BUG CRÍTICO (`chrome-extension/background.js`)

**Problema:** O handler `abrirCenarioComFoto` no `background.js` lia `msg.foto` que sempre era `undefined`. O `content.js` grava a foto em `chrome.storage.local['saleia_foto_pendente']` e **não a inclui na mensagem**. Resultado: `_aplicarDataUrl()` era chamado com `undefined` e a foto do cliente nunca aparecia no Visual Scenario.

**Correção:** O handler agora lê a foto de `chrome.storage.local` após o tab carregar:
```js
chrome.storage.local.get(['saleia_foto_pendente'], function (result) {
    var fotoData = result.saleia_foto_pendente ? result.saleia_foto_pendente.foto : null;
    if (!fotoData) return;
    chrome.scripting.executeScript({ ..., args: [fotoData] });
});
```

---

### EXTENSÃO CHROME — ATUALIZAÇÕES MENORES

| Arquivo | Alteração |
|---|---|
| `chrome-extension/manifest.json` | Versão atualizada: `1.2.0` → `1.4.1` |
| `chrome-extension/popup.html` | Versão no rodapé atualizada de `v1.0.0` para `v1.4.1` |
| `chrome-extension/popup.js` | Versão passa a ser lida dinamicamente via `chrome.runtime.getManifest().version` (nunca mais precisa de atualização manual) |

---

### DOCUMENTAÇÃO — CONTEXTO MÍNIMO CRIADO

| Arquivo | Conteúdo |
|---|---|
| `docs/CURRENT_STATE.md` | Estado completo do projeto: ambiente, deploy, funcionalidades, provedores, pendências |
| `docs/TASKS.md` | Fila operacional: T01–T10 concluídas, T11 concluída, T12–T13 pendentes |
| `docs/ARCHITECTURE.md` | Atualizado com todos os endpoints da V.1.4.0/V.1.4.1 (auth, admin, histórico, cenário, base) |

---

### ARQUIVOS ALTERADOS NESTA VERSÃO

| Arquivo | Tipo de alteração |
|---|---|
| `agent/email_service.py` | **novo** — módulo SMTP para recuperação de senha |
| `agent/sessao_manager.py` | feat: `migrar_colunas_usuarios()` — colunas `reset_token` e `reset_token_exp` |
| `api/main.py` | feat: `POST /auth/recuperar-senha` real, `GET /reset`, `POST /auth/redefinir-senha`, `AuthRedefinirSenhaRequest`; startup chama `migrar_colunas_usuarios()` |
| `.env.example` | feat: vars SMTP adicionadas |
| `chrome-extension/background.js` | fix: `abrirCenarioComFoto` lê foto de `chrome.storage.local` em vez de `msg.foto` |
| `chrome-extension/manifest.json` | chore: versão `1.2.0` → `1.4.1` |
| `chrome-extension/popup.html` | chore: versão `v1.0.0` → `v1.4.1` |
| `chrome-extension/popup.js` | chore: versão dinâmica via `getManifest()` |
| `docs/CURRENT_STATE.md` | docs: atualizado para V.1.4.1 |
| `docs/TASKS.md` | docs: T11 concluída, T12–T13 adicionadas |
| `docs/ARCHITECTURE.md` | docs: endpoints V.1.4.0/V.1.4.1 documentados |

---

## V.1.4.0 — Auth, Admin, Histórico de Uso, Filtros, Smoke Tests, Visual Scenario DALL-E 3
> Data: 28/05/2026 | Desenvolvido com Claude Sonnet 4.6

---

### AUTENTICAÇÃO (`api/main.py`, `agent/sessao_manager.py`)

**Endpoints implementados e validados:**
- `POST /auth/login` — verifica senha (bcrypt), gera JWT 72h, atualiza `ultimo_acesso`
- `POST /auth/cadastro` — valida dados, hash bcrypt, primeiro usuário vira admin/ativo, demais operador/pendente
- `POST /auth/recuperar-senha` — stub seguro (não vaza se e-mail existe ou não)

**Tabela `usuarios` criada automaticamente no startup** via `criar_tabela_usuarios()` adicionada a `agent/sessao_manager.py` e chamada em `on_startup`. Schema: `id UUID`, `nome`, `email UNIQUE`, `senha_hash`, `perfil`, `plano`, `status`, `data_cadastro`, `ultimo_acesso`.

**Dependências adicionadas a `requirements.txt`:** `bcrypt>=4.0.0`, `PyJWT>=2.8.0`.

**Helpers de autorização:**
- `_req_auth(authorization)` — verifica JWT, aceita qualquer perfil autenticado
- `_req_admin(authorization)` — verifica JWT e exige `perfil == "admin"`

---

### CONDUÇÃO — AUTENTICAÇÃO ADICIONADA (`api/main.py`)

**Problema anterior:** `POST /cenario/{meeting_id}/conducao` não exigia autenticação e tinha bug silencioso de `_get_conn` não importado em `_buscar_conteudo_programa`.

**Correções:**
- Adicionado `Header` ao import FastAPI no topo do arquivo
- Endpoint recebe `authorization: str | None = Header(default=None)` e chama `_req_auth` como primeira linha
- Validação de `meeting_id` adicionada (padrão `xxx-xxxx-xxx`)
- `_get_conn` importado localmente em `_buscar_conteudo_programa` (bug: caía no `except` e retornava sempre placeholder)

---

### ADMIN — GERENCIAMENTO DE USUÁRIOS E APIs (`api/main.py`)

**Endpoints de usuários** (todos com `_req_admin`):
| Endpoint | Ação |
|---|---|
| `GET /admin/usuarios` | Lista todos com perfil, plano, status, datas |
| `PATCH /admin/usuarios/{uid}/perfil` | Altera perfil (admin/gerente/operador/usuario) |
| `PATCH /admin/usuarios/{uid}/plano` | Altera plano (free/pro/enterprise) |
| `PATCH /admin/usuarios/{uid}/status` | Altera status (ativo/inativo/pendente) |
| `PATCH /admin/usuarios/{uid}/inativar` | Atalho: status → inativo |
| `PATCH /admin/usuarios/{uid}/reativar` | Atalho: status → ativo |
| `PATCH /admin/usuarios/{uid}/resetar-senha` | Reset para "Saleia@2025" |
| `DELETE /admin/usuarios/{uid}` | Remove permanentemente |

**Endpoints de APIs** (todos com `_req_admin`):
| Endpoint | Ação |
|---|---|
| `GET /admin/api/provedores` | Lista provedores com status de chave (sem expor a chave) |
| `POST /admin/api/provedores/{pid}/chave` | Salva chave no `.env` + `os.environ` |
| `POST /admin/api/teste` | Testa conectividade real com o SDK do provedor |
| `PATCH /admin/api/provedores/{pid}/status` | Ativa/inativa provedor |
| `POST /admin/api/principal` | Define provedor preferido (persiste em `.env`) |

---

### HISTÓRICO DE USO (`api/main.py`)

**Novos endpoints:**
- `GET /historico/uso` — lista últimas 100 reuniões com `custo_estimado_usd`, `score_final`, `disc_identificado`, `num_analises`, `num_key_moments`, `num_eventos`. Requer JWT. Cruza `MeetingMemory` (SQLModel) com `sessoes` (MySQL raw). Retorna `custo_total_usd` acumulado.
- `GET /historico/uso/{meeting_id}` — detalhe de uma reunião: `score_history[]` completo, `key_moments[]`, `eventos[]`, infos da sessão. Valida formato do `meeting_id`.

---

### PÁGINA HISTÓRICO NO DASHBOARD (`frontend/dashboard.html`)

**Nav item:** `📈 Histórico` adicionado à sidebar entre Analisar e Base de IA.

**Página `page-historico`:**
- Métricas resumidas: total de reuniões, custo total estimado (U$), score médio
- Lista de cards com meeting_id, data, número de análises, custo, score e DISC

**Página `page-historico-detalhe`** (ao clicar em uma reunião):
- Card de metadados (meeting_id, custo, score, análises, DISC, iniciada_em)
- Gráfico de barras da evolução do score ao longo da reunião
- Momentos-chave com tipo, fala, importância e timestamp
- Eventos com ícones por tipo (💰 pricing, 🛡️ objeção, ⚠️ alerta, 🔔 recap)

---

### FILTROS DE REUNIÕES — MELHORIAS (`frontend/dashboard.html`)

**Adicionado ao toolbar de Reuniões:**
- `input[type=date]` "De" e "Até" — filtro por intervalo de data (`r.data` ou `r.criado_em`)
- Botão `✕ Limpar` — zera todos os filtros de uma vez
- Contador `"X de Y reuniões"` aparece quando qualquer filtro está ativo

**CSS:** `input[type=date]` incluído nas regras dark (`color-scheme: dark` para o calendário do sistema).

**Nota:** filtro por provedor não implementado — campo ausente no response de `/relatorios`.

---

### SMOKE TESTS (`tests/test_smoke.py`)

**8 testes automatizados**, sem dependências externas (DB e IA mockados):

| Endpoint | Testes |
|---|---|
| `GET /health` | status 200, shape `{status, servico, versao, timestamp}`, status ∈ `{online, degradado}` |
| `GET /dashboard` | status 200, `content-type: text/html`, HTML contém `SALEIA` |
| `POST /recapitulacao-manual` | status 200, chaves `{recapitulacao, perfil_disc, diagnostico_financeiro, gerado_em}`, rejeita `transcricao: ""` com 400 |

**Resultado:** 8/8 OK em 1.1s.

**Como rodar:** `.\venv\Scripts\python.exe -m unittest tests.test_smoke -v`

---

### VISUAL SCENARIO AI — PERSISTÊNCIA (`agent/visual_scenario.py`)

**Problema anterior:** `ImageGenerator` retornava URLs do CDN da OpenAI que expiram após 1 hora. O botão `🕒 Histórico` em `visual-scenario.html` quebrava na segunda visita.

**Solução:** `response_format="b64_json"` — a imagem retorna como base64 e é armazenada como `data:image/png;base64,...` diretamente nas colunas `current_url`/`future_url` (`LONGTEXT`) do MySQL. Imagens persistem indefinidamente.

Timeout aumentado de 60s para 90s (DALL-E 3 pode levar 30–60s por imagem).

**Fluxo completo:**
1. `PainExtractor.extract()` — extrai segmento, dores, DISC, maturidade, urgência, descrições de ambiente via IA de texto
2. `PromptBuilder.build_current/future()` — monta prompts cinematográficos personalizados
3. `ImageGenerator.generate()` × 2 em paralelo (`asyncio.gather`) via DALL-E 3
4. `_salvar_cenario()` — persiste no MySQL
5. Retorna URLs (data URIs) + contexto + pain points

**Acesso:** `cenario.html` → botão `🎬 Visual` → `visual-scenario.html?meeting=<id>`

---

## V.1.3.6 — Configurações Accordion + Condução Conectada aos Prompts + RAG Corrigido
> Data: 27/05/2026 | Desenvolvido com Claude Sonnet 4.6

---

### CONFIGURAÇÕES — REDESIGN EM ACCORDION (`frontend/dashboard.html`)

**Problema anterior:** Página Configurações exibia todos os cards abertos e expandidos simultaneamente, ocupando muito espaço e carregando dados desnecessariamente.

**Solução:** Substituição dos cards planos por acordeão colapsável.

**Novo comportamento:**
- 3 seções colapsáveis com ícone + título + subtítulo + chevron (▾)
- Clique no cabeçalho abre/fecha — chevron rotaciona
- **Lazy-load:** cada seção carrega os dados apenas na primeira abertura (não dispara requisições desnecessárias)
- Ao re-navegar para Configurações: todas as seções fecham e o cache de load é resetado (dados sempre frescos)
- Rodapé fixo: status do backend (dot online/offline) + endpoint + versão + copyright

**Seções:**
| Ícone | Seção | Badge | Conteúdo ao abrir |
|---|---|---|---|
| 👥 (laranja) | Gerenciamento de Usuários | Admin | Tabela de usuários com selects inline |
| 🔑 (azul) | Configuração de APIs | Admin | Cards dos provedores de IA |
| 📚 (teal) | Base de Conhecimento | — | Contagem de documentos + botão ir à Base de IA |

**Novos CSS:** `.acc-wrap`, `.acc-item`, `.acc-item.open`, `.acc-header`, `.acc-icon`, `.acc-icon.orange`, `.acc-icon.blue`, `.acc-label`, `.acc-chevron`, `.acc-body`, `.acc-divider`, `.cfg-status-footer`

**Novas funções JS:**
```javascript
toggleAcc(id)          // abre/fecha seção + lazy-load na primeira abertura
carregarResumoBase()   // busca total de documentos via GET /base
```

---

### CONDUÇÃO — ENDPOINT CRIADO (`api/main.py`)

**Problema anterior:** `cenario.html` chamava `POST /cenario/{meeting_id}/conducao` mas o endpoint **não existia** — retornava erro e o overlay fechava com "❌ Não foi possível gerar o conteúdo". Os 4 arquivos de prompt template existiam mas nunca eram usados.

**Solução:** Endpoint implementado do zero.

| Endpoint | Método | Descrição |
|---|---|---|
| `/cenario/{meeting_id}/conducao` | POST | Gera script de condução ao vivo baseado no tipo e dados do cliente |

**Modelo Pydantic:**
```python
class ConducaoRequest(BaseModel):
    tipo: str        # recapitulacao | programa-aceleracao | performance | fechamento
    dados: Optional[dict] = None  # objeto completo de análise do cenário
```

**Roteamento por tipo:**
| `tipo` recebido | Template carregado |
|---|---|
| `recapitulacao` | `conducao_recapitulacao.txt` |
| `programa-aceleracao` | `conducao_programa_aceleracao.txt` |
| `performance` | `conducao_performance.txt` |
| `fechamento` | `conducao_fechamento.txt` |

**Variáveis extraídas do objeto `dados`:**
| Placeholder | Origem em `dados` |
|---|---|
| `{perfil_disc_tipo}` | `dados.perfil_disc.tipo` |
| `{perfil_disc_descricao}` | `dados.perfil_disc.descricao` ou `.evidencia` |
| `{faturamento}` | `dados.mapa_financeiro.faturamento_mensal` ou `.renda_clt` |
| `{capacidade_investimento}` | `dados.mapa_financeiro.capacidade_investimento` |
| `{produto_nome}` | `dados.mapa_financeiro.produto_indicado.nome` |
| `{produto_justificativa}` | `dados.mapa_financeiro.produto_indicado.justificativa` |
| `{score}` | `dados.score_compra.valor` |
| `{temperatura}` | `dados.temperatura.nivel` |
| `{conteudo_programa}` | Documentos da Base de IA (ver seção abaixo) |

**Compatibilidade com `chamar_ia_async` (que espera JSON):**
```python
system_prompt = (
    'Você é um assistente de vendas. '
    'Responda APENAS com um JSON válido sem markdown, no formato: '
    '{"conteudo": "script do vendedor aqui"}'
)
resultado = await chamar_ia_async(system_prompt, prompt_preenchido)
conteudo = resultado.get("conteudo") or ...
```

---

### CONDUÇÃO — INJEÇÃO DE DOCUMENTOS DA BASE DE IA (`api/main.py`)

**Problema:** Os prompts de Apresentação (Programa de Aceleração e Performance) geravam scripts genéricos porque a IA não sabia o que são esses programas na empresa.

**Solução:** O endpoint busca automaticamente documentos da `base_conhecimento` pelo `tipo` correspondente e injeta o conteúdo no prompt como `{conteudo_programa}`.

**Função adicionada:**
```python
def _buscar_conteudo_programa(tipo_base: str) -> str:
    # Query: SELECT titulo, texto FROM base_conhecimento WHERE tipo = %s ORDER BY created_at
    # Concatena todos os documentos do tipo com separador ### Titulo
```

**Mapeamento tipo condução → tipo Base de IA:**
```python
_CONDUCAO_TIPO_BASE = {
    "programa-aceleracao": "programa_aceleracao",
    "performance":         "performance",
}
```

**Como usar — fluxo completo:**
1. No Dashboard → Base de IA → adicionar documento
2. Selecionar tipo: **🚀 Programa de Aceleração** ou **📈 Programa Performance**
3. Escrever o conteúdo completo do programa (metodologia, benefícios, resultados, investimento...)
4. Salvar — entra em vigor imediatamente na próxima chamada de Condução
5. Múltiplos documentos do mesmo tipo são concatenados automaticamente

---

### PROMPT TEMPLATES ATUALIZADOS

Ambos os templates de Apresentação receberam bloco `INFORMAÇÕES DO PROGRAMA` com `{conteudo_programa}`:

**`conducao_programa_aceleracao.txt`** — adicionado:
```
INFORMAÇÕES DO PROGRAMA DE ACELERAÇÃO:
{conteudo_programa}
```
Instrução atualizada: *"Use as informações do programa acima para embasar a fala com detalhes reais."*

**`conducao_performance.txt`** — adicionado:
```
INFORMAÇÕES DO PROGRAMA PERFORMANCE:
{conteudo_programa}
```
Instrução atualizada: *"Use as informações reais do programa acima para mostrar o que muda na vida ou no negócio do cliente."*

---

### BASE DE IA — NOVO TIPO `performance` (`frontend/dashboard.html`)

**Adicionado:**
- Option `📈 Programa Performance` no `<select>` de tipo do formulário
- `_TIPOS_BASE` map: `performance: '📈 Prog. Performance'`

**Tipos disponíveis agora:**
```
instrucao, script_venda, programa_aceleracao, performance,
diagnostico, consultoria, reuniao_1_1, reuniao, outro
```

---

### CORREÇÕES DE BUGS

| # | Arquivo | Problema | Solução |
|---|---|---|---|
| 1 | `agent/base_conhecimento.py` | RAG buscava coluna `tipo_reuniao` (inexistente) | Corrigido para `tipo` (nome real da coluna adicionada em V.1.3.5) |
| 2 | `api/main.py` | `POST /cenario/{id}/conducao` retornava 404/405 | Endpoint criado do zero |
| 3 | `frontend/dashboard.html` | Configurações carregava todos os dados simultaneamente ao abrir | Lazy-load com accordion resolve |

---

### ARQUIVOS ALTERADOS NESTA VERSÃO

| Arquivo | Tipo de alteração |
|---|---|
| `api/main.py` | feat: `ConducaoRequest`, endpoint `/cenario/{id}/conducao`, `_buscar_conteudo_programa` |
| `frontend/dashboard.html` | feat: accordion Configurações, tipo `performance` na Base de IA |
| `agent/base_conhecimento.py` | fix: `tipo_reuniao` → `tipo` |
| `agent/prompt_templates/conducao_programa_aceleracao.txt` | feat: bloco `{conteudo_programa}` |
| `agent/prompt_templates/conducao_performance.txt` | feat: bloco `{conteudo_programa}` |

---

## V.1.3.5 — Deploy VPS + Auth + Admin + Base de IA Avançada
> Data: 27/05/2026 | Desenvolvido com Claude Sonnet 4.6

---

### DEPLOY EM PRODUÇÃO

| Item | Detalhe |
|---|---|
| Servidor | VPS Hetzner — `204.168.180.25` |
| Domínio | `api.saleia.com.br` (Nginx + Certbot SSL) |
| Serviço | `saleia.service` (systemd, reinicia automaticamente) |
| Processo | `uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 2` |
| Banco | MySQL remoto `177.104.186.227` — base `fast5342_AV3D` |
| Deploy | SFTP direto (repo VPS apontava para `SALEIA.git` errado; migrado para `SALE-IA.git`) |

---

### AUTENTICAÇÃO (`/auth/*`)

**Problema anterior:** login.html chamava endpoints que não existiam → "Not Found".

| Endpoint | Método | Descrição |
|---|---|---|
| `/auth/login` | POST | Verifica email + senha bcrypt, retorna JWT (72h) |
| `/auth/cadastro` | POST | Cria usuário; primeiro usuário vira admin automaticamente |
| `/auth/recuperar-senha` | POST | Stub (confirma recebimento; envio de e-mail pendente) |

**Detalhes técnicos:**
- Hash: `bcrypt` (instalado no venv do VPS)
- Token: `PyJWT` HS256, expiração 72h
- JWT secret: variável `JWT_SECRET` no `.env` (fallback padrão se não definida)
- Tabela: `usuarios` (MySQL) — campos: `id`, `nome`, `email`, `senha_hash`, `perfil`, `plano`, `status`, `data_cadastro`, `ultimo_acesso`
- Coluna `plano` adicionada via `ALTER TABLE` (padrão `free`)

---

### ADMIN — GERENCIAMENTO DE USUÁRIOS (`/admin/usuarios/*`)

Todos os endpoints exigem JWT Bearer com `perfil = admin`.

| Endpoint | Método | Descrição |
|---|---|---|
| `/admin/usuarios` | GET | Lista todos os usuários |
| `/admin/usuarios/{id}/inativar` | PATCH | Define `status = inativo` |
| `/admin/usuarios/{id}/reativar` | PATCH | Define `status = ativo` |
| `/admin/usuarios/{id}/status` | PATCH | Define status arbitrário (`ativo`, `pendente`, `inativo`) |
| `/admin/usuarios/{id}/resetar-senha` | PATCH | Redefine senha para `Saleia@2025`, retorna nova senha |
| `/admin/usuarios/{id}/perfil` | PATCH | Altera perfil (`admin`, `gerente`, `operador`, `usuario`) |
| `/admin/usuarios/{id}/plano` | PATCH | Altera plano (`free`, `pro`, `enterprise`) |
| `/admin/usuarios/{id}` | DELETE | Exclui usuário permanentemente |

**UI — Tabela com menus suspensos inline:**
- **Perfil**: `<select>` direto na linha — salva ao trocar
- **Plano**: `<select>` direto na linha — salva ao trocar
- **Status**: `<select>` direto na linha — salva ao trocar
- **⋮ Ações**: dropdown com → 🔑 Reset senha / 🗑 Excluir
- Dropdown fecha ao clicar fora da tabela

---

### ADMIN — CONFIGURAÇÃO DE APIs (`/admin/api/*`)

| Endpoint | Método | Descrição |
|---|---|---|
| `/admin/api/provedores` | GET | Lista os 4 provedores com status atual baseado no `.env` |
| `/admin/api/provedores/{id}/chave` | POST | Salva chave no `.env` e recarrega em tempo real |
| `/admin/api/teste` | POST | Testa conectividade do provedor (chamada real de 1 token) |
| `/admin/api/provedores/{id}/status` | PATCH | Ativa/inativa provedor |
| `/admin/api/principal` | POST | Define provedor preferido (`PROVEDOR_PREFERIDO` no `.env`) |

**Provedores suportados:** DeepSeek · OpenAI · Anthropic · Gemini

---

### BASE DE CONHECIMENTO — CRUD (`/base/*`)

**Problema anterior:** endpoint usava coluna `conteudo` mas a tabela tem `texto`.

| Endpoint | Método | Descrição |
|---|---|---|
| `/base` | GET | Lista documentos (id, título, tipo, chars, data) |
| `/base` | POST | Adiciona documento; gera embedding via `text-embedding-3-small` |
| `/base/{id}` | DELETE | Remove documento e invalida cache RAG |
| `/base/ocr` | POST | OCR de imagem via AI Vision (Claude → GPT-4o fallback) |

**Fallback de embedding:** quando a quota OpenAI está esgotada, documento é salvo com `embedding = NULL` e o usuário recebe aviso laranja em vez de erro 502.

**Migração de banco:**
```sql
ALTER TABLE base_conhecimento ADD COLUMN tipo VARCHAR(100) DEFAULT 'outro' AFTER titulo;
```

---

### UPLOAD DE ARQUIVOS — DRAG & DROP

**Localização:** Dashboard → Base de Conhecimento

**Formatos suportados:**

| Formato | Método de extração |
|---|---|
| `.txt` `.md` `.csv` | FileReader nativo (browser) |
| `.pdf` | PDF.js 3.11 via CDN (extração página a página) |
| `.docx` `.doc` | Mammoth.js 1.6 via CDN (texto limpo) |
| `.jpg` `.jpeg` `.png` `.webp` `.gif` | OCR via AI Vision (`/base/ocr`) — Claude ou GPT-4o |

**Comportamento:**
- Arrastar arquivo para a zona **ou** clicar para selecionar
- Nome do arquivo vira sugestão de título automaticamente
- Exibe quantidade de caracteres extraídos
- Erros de extração exibidos em vermelho na própria zona

**Correções de bugs no drag-drop:**
- `_dropzoneInited` flag → evita listeners duplicados ao alternar páginas
- `dragenter` + `dragleave` com `relatedTarget` → fix do flicker em elementos filhos
- `.base-dropzone * { pointer-events: none }` → filhos não interceptam eventos de drag
- `document.dragover/drop` com `preventDefault` → evita browser abrir o arquivo

---

### ROTAS HTML ADICIONADAS

| Rota | Arquivo servido |
|---|---|
| `GET /` | `frontend/login.html` |
| `GET /login` | `frontend/login.html` |

**Problema anterior:** botão "Sair" redirecionava para `/login` que retornava 404 (FastAPI não tinha essa rota).

---

### CORREÇÕES DE BUGS

| # | Problema | Solução |
|---|---|---|
| 1 | POST `/base` retornava 500 — coluna `conteudo` não existe | Corrigido para `texto` (nome real no banco) |
| 2 | GET `/base` retornava 500 — `tipo` não existia na tabela | `ALTER TABLE` adicionou coluna `tipo` |
| 3 | Botão Sair → `/login` → 404 | Adicionado `GET /login` no FastAPI |
| 4 | POST `/base` retornava 502 quando quota OpenAI esgotada | Fallback: salva sem embedding + aviso ao usuário |
| 5 | Botão "🗑 Excluir" invisível na Base de IA | CSS `.cfg-btn-acao.danger` estava sem definição |
| 6 | Drag-drop não funcionava | 3 bugs corrigidos (ver seção acima) |
| 7 | Git remoto VPS apontava para repo errado (`SALEIA` vs `SALE-IA`) | Atualizado via `git remote set-url` + SFTP deploy |

---

## V.1.3.4 — Recapitulação com Mapa Mental + Base de IA + Logout
> Data: 27/05/2026

### FUNCIONALIDADES

**Cenário → Condução → Recapitulação:**
- Painel alargado (`min(760px, 100vw - 32px)`) ao abrir Recapitulação
- Exibe texto gerado pela IA + Mapa Mental inline com 6 cards:
  - DISC (tipo + cor), Score de compra, Temperatura, Faturamento/Renda, Capacidade de investimento, Produto indicado
- Mapa Mental usa cores DISC: D=`#EF4444` I=`#F97316` S=`#14B8A6` C=`#38BDF8`

**Dashboard — Página "Base de IA":**
- Formulário: Título, Tipo (7 categorias), Conteúdo
- Tabela de documentos com botão Excluir
- Tipos: instrucao, script_venda, programa_aceleracao, diagnostico, consultoria, reuniao_1_1, outro

**Botão Sair:**
- Localização: rodapé da sidebar
- Ação: remove `saleia_token` do localStorage → redireciona para `/login`

**Arquivos alterados:** `api/main.py`, `frontend/dashboard.html`, `frontend/cenario.html`, `frontend/login.html`, `agent/base_conhecimento.py`, `agent/prompt_templates/*.txt`

---

## INFRAESTRUTURA

### Banco de dados (MySQL `fast5342_AV3D`)

**Tabelas relevantes:**

| Tabela | Uso |
|---|---|
| `usuarios` | Autenticação e gerenciamento de usuários |
| `base_conhecimento` | Documentos para RAG (embeddings OpenAI) |
| `sessoes` | Sessões de reunião |
| `meeting_memory` | Memória por meeting_id |

**Colunas adicionadas nesta versão:**
```sql
ALTER TABLE usuarios ADD COLUMN plano VARCHAR(30) NOT NULL DEFAULT 'free';
ALTER TABLE base_conhecimento ADD COLUMN tipo VARCHAR(100) DEFAULT 'outro' AFTER titulo;
```

### VPS — Pacotes instalados no venv

```bash
pip install PyJWT bcrypt
```

### Variáveis de ambiente (`.env`)

```env
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GEMINI_API_KEY=...
DEEPSEEK_API_KEY=...
DEEPSEEK_MODEL=deepseek-chat
DB_HOST=177.104.186.227
DB_PORT=3306
DB_USER=fast5342_AV3D
DB_PASS=...
DB_NAME=fast5342_AV3D
JWT_SECRET=...              # novo — segredo para JWT
PROVEDOR_PREFERIDO=deepseek # novo — provedor ativo principal
```

---

## COMMITS DESTA SESSÃO

```
9a49917  fix: botão Excluir visível e funcional na Base de IA
0382369  fix: corrigir drag-and-drop na Base de IA
7582bc3  feat: OCR de imagens (JPEG/PNG/WEBP) via AI Vision na Base de IA
e5f065d  feat: drag-and-drop de arquivos na Base de IA (PDF, DOCX, TXT, MD)
a7656f2  fix: salvar documento na base mesmo sem embedding (fallback gracioso)
c2f617c  feat: implementar endpoints /admin/usuarios e /admin/api/provedores
14e9d38  feat: implementar endpoints /auth/login, /auth/cadastro e /auth/recuperar-senha
d413ae2  fix: adicionar rota /login e / para servir login.html
f89e984  fix: usar coluna 'texto' em vez de 'conteudo' nos endpoints /base
53f2b0d  feat: V.1.3.4 — Recapitulação com Mapa Mental integrado + versão atualizada
```

---

*Documento gerado em 27/05/2026 — SALEIA / HEXAGON TECNOLOGIA*
