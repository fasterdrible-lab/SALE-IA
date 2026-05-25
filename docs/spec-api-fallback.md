# Spec: fallback automatico entre APIs de IA

## Descricao geral

Implementar uma camada backend unica para chamadas de IA generativa do SALEIA, com fallback automatico entre OpenAI, Anthropic e Gemini. A camada deve evitar que o vendedor fique sem resposta quando o provedor principal estiver lento, sem saldo, fora do ar, sem chave configurada ou retornando erro.

O frontend e a extensao Chrome continuam apenas enviando transcricoes e exibindo respostas. A escolha de provedor, chaves, timeouts, circuit breaker e tratamento de erro ficam exclusivamente no backend.

## Paginas e superficies afetadas

### Extensao Chrome

Componentes:
- `popup.html` / `popup.js`: configuracao e acionamento da extensao.
- `content.js`: captura contexto da reuniao e envia transcricao ao backend.
- `background.js`: captura audio e heartbeat.

Comportamento do usuario:
- O vendedor inicia a extensao durante a reuniao.
- A extensao envia transcricoes para `/tempo-real`.
- Se uma API de IA falhar, a extensao nao escolhe outro provedor; ela recebe a resposta normal do backend quando algum fallback funcionar.

### Painel e paginas HTML

Componentes:
- `frontend/dashboard.html`: consulta relatorios e sessoes.
- `frontend/cenario.html`: consulta a ultima analise por reuniao.
- `frontend/manual.html` e `frontend/manual_tecnico.html`: documentacao operacional.

Comportamento do usuario:
- O usuario acessa as paginas do backend.
- As paginas continuam consumindo endpoints existentes.
- O status de IA fica disponivel em `/health`, sem expor chaves.

### API FastAPI

Componentes:
- `api/main.py`: endpoints publicos.
- `api/ai_router.py`: camada central de fallback.
- `api/processador_tempo_real.py`: orquestracao da analise ao vivo.
- `agent/agente_tempo_real.py`: prompt e retorno JSON para reuniao ao vivo.
- `agent/recapitulacao.py`: dicas e recapitulacoes auxiliares.

Comportamento do usuario:
- Ao chamar `/tempo-real`, `/diagnostico-financeiro`, `/perfil-disc`, `/recapitulacao-completa` ou `/recapitulacao-manual`, o backend tenta os provedores em ordem configurada.
- Se um provedor falhar por timeout, rate limit, falta de saldo, erro 5xx, erro de SDK, JSON invalido ou chave ausente, o backend tenta o proximo provedor elegivel.
- Se todos falharem, retorna erro 503 com mensagem operacional, sem dados sensiveis.

## Regras de fallback

- Ordem padrao: `openai,anthropic,gemini`.
- Ordem configuravel por `AI_PROVIDER_ORDER`.
- Modelos configuraveis por `OPENAI_MODEL`, `ANTHROPIC_MODEL` e `GEMINI_MODEL`.
- Timeout configuravel por `AI_PROVIDER_TIMEOUT_SECONDS`.
- Circuit breaker em memoria por provedor.
- Chaves ficam apenas em variaveis de ambiente.
- Logs e respostas nao devem expor chave, token, prompt completo ou dados sensiveis.

## Banco de dados

Nao ha mudanca de estrutura de banco nesta tarefa. O estado do circuit breaker fica em memoria por processo.

## Sucesso, erro e edge cases

Sucesso:
- OpenAI responde corretamente.
- OpenAI falha e Anthropic responde.
- OpenAI e Anthropic falham e Gemini responde.
- `/health` mostra status dos provedores sem revelar segredos.

Erro:
- Nenhum provedor configurado.
- Todos os provedores indisponiveis.
- Provedor retorna JSON invalido.
- SDK do provedor nao esta instalado.

Edge cases:
- Provedor entra em cooldown depois de falhas consecutivas.
- Cooldown expira e o provedor volta a ser testado.
- Variavel `GOOGLE_API_KEY` ou `GEMINI_API_KEY` pode configurar Gemini.
- Fluxos de audio/Whisper e embeddings continuam usando OpenAI porque nao sao equivalentes aos provedores de chat.
