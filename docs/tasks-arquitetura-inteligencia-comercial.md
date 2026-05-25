# Tasks: nova arquitetura de inteligencia comercial SALEIA

## Issue 1 - Definir MeetingMemory e persistencia total no banco

Arquivos:
- Modificar `api/database.py`
- Modificar `api/models.py`
- Modificar `agent/sessao_manager.py`
- Modificar `api/main.py`

Reutilizacao:
- Reaproveitar a estrutura de persistencia atual de relatorios e sessoes.
- Reaproveitar `meeting_id` como chave primaria funcional da reuniao.

Dependencias:
- Banco atual ja configurado por ambiente.

Cenarios:
- criar memoria para um `meeting_id` novo
- atualizar memoria existente
- recuperar memoria apos restart
- lidar com banco indisponivel com erro claro

## Issue 2 - Separar contrato da analise em tempo real

Arquivos:
- Modificar `api/processador_tempo_real.py`
- Modificar `agent/agente_tempo_real.py`
- Modificar `agent/prompt_templates/agente_tempo_real.txt`
- Modificar `api/main.py`

Reutilizacao:
- Reaproveitar o handler atual de `/tempo-real`.
- Reaproveitar o roteador central de IA.

Dependencias:
- Nenhuma nova, mas o JSON da IA precisa ficar estabilizado.

Cenarios:
- texto novo suficiente
- texto novo insuficiente
- resumo vivo atualizado
- score atualizado

## Issue 3 - Criar analiseRealtimeMeeting e buffer curto

Arquivos:
- Criar novo modulo em `api/`
- Modificar `api/processador_tempo_real.py`
- Modificar `chrome-extension/content.js`

Reutilizacao:
- Reaproveitar o delta ja enviado pela extensao.
- Reaproveitar o historico local da aba.

Dependencias:
- tempo de analise configuravel por ambiente ou constante segura.

Cenarios:
- buffer de 1 a 3 minutos
- sem envio de transcricao completa em tempo real
- debounce para evitar chamada demais

## Issue 4 - Criar eventos estruturados e key moments

Arquivos:
- Criar novo modulo em `api/` ou `agent/`
- Modificar `agent/prompt_templates/*`
- Modificar `api/main.py`

Reutilizacao:
- Reaproveitar a leitura contextual da conversa.
- Reaproveitar score e diagnostico existente como base de inferencia.

Dependencias:
- Nenhuma nova.

Cenarios:
- `objection_detected`
- `buying_signal`
- `recap_trigger`
- `pricing_resistance`
- `closing_signal`
- `competitor_mention`
- separar fato de inferencia
- registrar confidence score

## Issue 5 - Detectar deixa verbal de recapitulacao

Arquivos:
- Criar novo modulo em `api/` ou `agent/`
- Modificar `chrome-extension/content.js`
- Modificar `agent/prompt_templates/recapitulacao.txt` ou novo prompt proprio

Reutilizacao:
- Reaproveitar a sidebar atual e o fluxo de envio periodico.

Dependencias:
- cooldown por `meeting_id`.

Cenarios:
- frase gatilho detectada
- mesma deixa repetida dentro do cooldown
- sem disparo em contexto insuficiente

## Issue 6 - Gerar mapa mental e texto falavel na sidebar

Arquivos:
- Modificar `chrome-extension/content.js`
- Modificar `chrome-extension/sidebar.css`
- Modificar `frontend/cenario.html` se necessario para compatibilidade visual

Reutilizacao:
- Reaproveitar as secoes atuais de recapitulacao, temperatura, proxima fala e score.

Dependencias:
- resposta JSON padronizada da IA.

Cenarios:
- exibir dor principal, impacto, objetivo, objeccoes, oportunidades e proximo passo
- copiar fala
- regenerar
- marcar como usado
- fechar

## Issue 7 - Gerar diagnostico final completo

Arquivos:
- Modificar `api/webhook_tactiq.py`
- Modificar `agent/recapitulacao.py`
- Modificar `agent/diagnostico.py`
- Modificar `agent/prompt_templates/recapitulacao_completa.txt`
- Criar novo prompt de diagnostico final

Reutilizacao:
- Reaproveitar o webhook final atual.
- Reaproveitar diagnostico financeiro e DISC ja existentes como insumos.

Dependencias:
- memoria persistida da reuniao.

Cenarios:
- reuni ao final com memoria completa
- faltando algum trecho, mas com dados suficientes
- resposta final com follow-up e risco de perda

## Issue 8 - Ajustar rota de provedores para DeepSeek primeiro e trocar manualmente

Arquivos:
- Modificar `api/ai_router.py`
- Modificar `api/main.py`
- Modificar `chrome-extension/popup.html`
- Modificar `chrome-extension/popup.js`
- Modificar `chrome-extension/popup.css`

Reutilizacao:
- Reaproveitar o endpoint atual de health e a troca manual ja existente no popup.

Dependencias:
- variaveis de ambiente para DeepSeek.

Cenarios:
- ordem padrao DeepSeek -> OpenAI -> Claude -> Gemini
- troca manual de prioridade
- status visivel sem expor segredo

## Issue 9 - Tratar seguranca, sanitizacao e custo

Arquivos:
- Modificar `api/ai_router.py`
- Modificar `api/processador_tempo_real.py`
- Modificar `api/webhook_tactiq.py`
- Modificar `api/main.py`

Reutilizacao:
- Reaproveitar a sanitizacao ja existente em partes do backend.

Dependencias:
- nenhuma nova.

Cenarios:
- remover dados sensiveis do payload
- registrar custo estimado por chamada
- fallback se DeepSeek falhar
- erro de API tratado sem quebrar a sessao

## Issue 10 - Validacao e regressao

Arquivos:
- Criar ou atualizar testes em `tests/`
- Validar `api/main.py`, `api/ai_router.py`, `api/processador_tempo_real.py`

Reutilizacao:
- Reaproveitar padrao de testes existente.

Dependencias:
- banco local ou mock.

Cenarios:
- Fase 1 persistindo memoria
- fallback de provedor
- trigger de recapitulação
- payload JSON valido

## Fora de escopo desta rodada

- redesenho visual completo da interface
- migração para Redis
- dashboard analitico novo
- reescrita total da extensao
