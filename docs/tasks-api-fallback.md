# Tasks: fallback automatico entre APIs de IA

## Issue 1 - Centralizar fallback de chat no backend

Arquivos:
- Modificar `api/ai_router.py`
- Modificar `api/llm_router.py`
- Modificar `agent/agente_tempo_real.py`
- Modificar `agent/recapitulacao.py`
- Modificar `agent/diagnostico.py`
- Modificar `agent/diagnostico_financeiro.py`
- Modificar `agent/perfil_disc.py`
- Modificar `agent/suporte_venda.py`
- Modificar `api/config.py`

Reutilizacao:
- Reaproveitar o `api/ai_router.py` existente, sem criar outro roteador paralelo.
- Reaproveitar prompts atuais dos agentes.

Dependencias:
- `openai`, `anthropic`, `google-generativeai` ja estao no `requirements.txt` principal.
- Atualizar `api/requirements.txt` se ele continuar sendo usado em deploy isolado da API.

Cenarios:
- Sucesso no provedor primario.
- Fallback para segundo ou terceiro provedor.
- Falha por chave ausente, timeout, rate limit, sem saldo, erro 5xx, SDK ausente e JSON invalido.

Status: planejada para implementacao nesta rodada.

## Issue 2 - Expor saude operacional dos provedores

Arquivos:
- Modificar `api/ai_router.py`
- Usar `GET /health` existente em `api/main.py`

Reutilizacao:
- Reaproveitar `status_provedores()`.

Dependencias:
- Nenhuma nova dependencia.

Cenarios:
- Provedor sem chave.
- Provedor ok.
- Provedor degradado.
- Provedor em cooldown.

Status: planejada para implementacao nesta rodada.

## Issue 3 - Remover segredo hardcoded de configuracao PM2

Arquivos:
- Modificar `ecosystem.config.js`
- Modificar `agent/base_conhecimento.py`
- Modificar `agent/sessao_manager.py`

Reutilizacao:
- Manter a estrutura PM2 atual.

Dependencias:
- Variaveis de ambiente do servidor.

Cenarios:
- Processo herda `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` e `GOOGLE_API_KEY` do ambiente.
- Nenhuma chave fica gravada no arquivo versionavel.
- Conexao MySQL exige `DB_HOST`, `DB_USER`, `DB_PASS` e `DB_NAME` no ambiente.

Status: planejada para implementacao nesta rodada.

## Issue 4 - Testes unitarios do fallback sem chamadas reais

Arquivos:
- Criar `tests/test_ai_router.py`

Reutilizacao:
- Usar `unittest` e `unittest.mock` da biblioteca padrao.

Dependencias:
- Nenhuma nova dependencia.

Cenarios:
- Primeiro provedor responde.
- Primeiro provedor falha e segundo responde.
- Provedores sem chave sao pulados.
- Todos falham e o backend retorna indisponivel.

Status: planejada para implementacao nesta rodada.

## Fora de escopo desta rodada

- Fallback para transcricao de audio Whisper.
- Fallback para embeddings da base de conhecimento.
- Persistencia do circuit breaker em banco/Redis.
- Interface visual para trocar ordem de provedores.
