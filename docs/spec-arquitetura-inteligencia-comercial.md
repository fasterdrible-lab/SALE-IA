# Spec: nova arquitetura de inteligencia comercial SALEIA

## 1. Descricao geral

O SALEIA passa a operar como um coach de vendas em tempo real com memoria persistente por reuniao.

Objetivos principais:
- acompanhar a reuniao ao vivo sem sobrecarregar a IA com transcricao completa a cada ciclo
- guardar a transcricao integral no banco
- enviar para IA somente o que for necessario para a decisao: resumo vivo, diagnostico atual, ultimos 1 a 3 minutos e historico de score
- detectar deixas verbais do vendedor para recapitular e sugerir fala pronta
- gerar diagnostico final completo ao fim da reuniao
- manter controle de provedor e fallback no backend, com DeepSeek como primeira opcao

## 2. Arquitetura atual inferida

O sistema atual ja possui:
- captura de legendas e audio na extensao Chrome
- envio periodico de fragmentos para `POST /tempo-real`
- persistencia de sessao por `meeting_id`
- geracao de recapitulação, perfil DISC, diagnostico financeiro e relatorios finais
- roteador central de IA com fallback e circuit breaker

Principais limites atuais:
- a memoria da reuniao esta espalhada entre cache em memoria, tabela de sessoes e relatorios
- a analise em tempo real ainda envia contexto amplo demais
- nao existe uma entidade explicita e unica de `MeetingMemory`
- a deteccao de recapitulacao por deixa verbal nao esta formalizada
- a sidebar ja mostra parte do necessario, mas nao possui fluxo dedicado para mapa mental e acoes de uso

## 3. Superficies do produto

### 3.1 Extensao Chrome

Componentes:
- `chrome-extension/content.js`
- `chrome-extension/background.js`
- `chrome-extension/popup.html`
- `chrome-extension/popup.js`
- `chrome-extension/popup.css`
- `chrome-extension/sidebar.css`

Comportamentos:
- capturar legenda e audio
- montar delta de texto novo
- enviar apenas o necessario ao backend
- exibir dicas em tempo real na sidebar
- mostrar mapa mental, texto falavel e proxima pergunta
- permitir marcar como usado, copiar fala, regenerar e fechar
- oferecer configuracoes para trocar a prioridade do provedor de IA manualmente

### 3.2 API FastAPI

Componentes:
- `api/main.py`
- `api/processador_tempo_real.py`
- `api/ai_router.py`
- `api/database.py`
- `api/webhook_tactiq.py`
- `api/models.py`

Comportamentos:
- receber transcricao parcial e delta
- atualizar a `MeetingMemory`
- analisar em ciclos de 30 a 60 segundos
- salvar transcript completo no banco
- gerar resposta estruturada em JSON
- consolidar eventos, key moments e score history
- gerar diagnostico final e recapitulacao
- expor status operacional dos provedores sem revelar segredo

### 3.3 Camada de agentes

Componentes:
- `agent/agente_tempo_real.py`
- `agent/recapitulacao.py`
- `agent/diagnostico.py`
- `agent/perfil_disc.py`
- `agent/sessao_manager.py`
- `agent/prompt_templates/*`

Comportamentos:
- prompts separados em arquivo proprio
- respostas em JSON estruturado
- prompts menores e especializados por fase
- reutilizacao do conhecimento existente de vendas e diagnostico

### 3.4 Paginas web de apoio

Componentes:
- `frontend/painel.html`
- `frontend/cenario.html`
- `frontend/dashboard.html`
- `frontend/manual.html`
- `frontend/manual_tecnico.html`

Comportamentos:
- manter compatibilidade com o fluxo atual
- refletir score, produto, perfil, mapa e historico
- servir como pagina de consulta e validacao visual

## 4. Componentes de cada superficie

### 4.1 Sidebar ao vivo

Componentes esperados:
- resumo vivo
- diagnostico atual
- score atual e historico
- mapa mental com:
  - dor principal
  - impacto
  - objetivo
  - objeccoes
  - oportunidades
  - proximo passo
- texto falavel
- pergunta de confirmacao
- perguntas faltantes
- dica para o vendedor

### 4.2 Configuracoes da extensao

Componentes esperados:
- status dos provedores
- ordem atual dos provedores
- botao para trocar prioridade manualmente
- feedback de sucesso e erro

### 4.3 Banco de dados

Nova estrutura esperada para `MeetingMemory` por `meeting_id`:
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
- `created_at`
- `updated_at`

## 5. Comportamentos por fase

### Fase 1 - Meeting Memory

Objetivo:
- criar a memoria persistente da reuniao no banco.

Comportamentos:
- salvar transcript completo
- manter buffer curto dos ultimos 1 a 3 minutos
- atualizar resumo vivo
- atualizar diagnostico atual
- registrar score history
- registrar key moments
- registrar events

### Fase 2 - Coach em tempo real

Objetivo:
- chamar IA em intervalos controlados e somente com texto novo suficiente.

Comportamentos:
- analisar a reuniao a cada 30 a 60 segundos
- pular chamadas quando nao houver texto suficiente
- devolver dica, alerta, proxima pergunta e acao recomendada
- atualizar score, resumo e diagnostico

### Fase 3 - Eventos e momentos-chave

Objetivo:
- transformar a reuniao em sinalizacao estruturada.

Eventos esperados:
- `objection_detected`
- `buying_signal`
- `recap_trigger`
- `pricing_resistance`
- `closing_signal`
- `competitor_mention`

Key moments esperados:
- type
- quote
- speaker
- timestamp
- importance
- confidence

### Fase 4 - Recapitulacao por deixa verbal

Objetivo:
- identificar quando o vendedor pede resumo ou confirmacao.

Frases gatilho:
- vamos recapitular
- deixa eu ver se entendi
- pelo que voce me falou
- foi isso que eu colhi
- so para confirmar

Comportamentos:
- detectar com cooldown
- evitar repeticao
- gerar mapa mental + texto falavel

### Fase 5 - Mapa mental na sidebar

Objetivo:
- mostrar a recapitulação de forma visual e acionavel.

Comportamentos:
- exibir mapa mental
- exibir texto falavel
- exibir pergunta de confirmacao
- exibir perguntas faltantes
- exibir dica para o vendedor
- permitir copiar fala, regenerar, marcar como usado e fechar

### Fase 6 - Diagnostico final

Objetivo:
- gerar a leitura completa do cliente ao fim da reuniao.

Fontes:
- `accumulated_summary`
- `current_diagnosis`
- `key_moments`
- `score_history`
- `transcript_full` quando necessario

Saidas:
- resumo executivo
- diagnostico do cliente
- dores
- objeccoes
- intencao de compra
- perfil DISC
- capacidade financeira
- risco de perda
- proximos passos
- mensagem de follow-up

### Fase 7 - Seguranca e custo

Objetivo:
- manter o sistema seguro, rastreavel e barato o suficiente para uso ao vivo.

Regras:
- nunca enviar `.env`, tokens ou credenciais
- sanitizar dados sensiveis
- registrar custo estimado por chamada de IA
- tratar erros de API
- ter fallback se DeepSeek falhar
- evitar envio de transcricao completa em tempo real

## 6. Roteamento de IA

Ordem desejada dos provedores:
- DeepSeek
- OpenAI
- Claude
- Gemini

Regras:
- escolha do provedor fica no backend
- o frontend so solicita troca de prioridade
- o estado deve continuar visivel em `/health`
- a troca manual nao pode expor chaves nem permitir bypass do backend

## 7. Contrato de resposta da IA

Todas as respostas devem ser JSON estruturado.

Campos prioritarios no tempo real:
- `alerta_urgente`
- `resumo_vivo`
- `current_diagnosis`
- `score_compra`
- `proxima_acao`
- `proxima_pergunta`
- `dica_vendedor`
- `objecao_detectada`
- `eventos`
- `key_moments`
- `mapa_mental`
- `texto_falavel`
- `pergunta_confirmacao`
- `perguntas_faltantes`

Campos prioritarios no final:
- `resumo_executivo`
- `diagnostico_cliente`
- `dores`
- `objeccoes`
- `intencao_compra`
- `perfil_disc`
- `capacidade_financeira`
- `risco_perda`
- `proximos_passos`
- `follow_up`

## 8. Reutilizacao prevista

Reaproveitar:
- roteador central de IA existente
- captura atual da extensao
- tabela e rotinas de sessao existentes
- prompts ja consolidados em `agent/prompt_templates`
- paginas `cenario.html` e `painel.html` como base visual

Evitar:
- duplicar logica de provedor em frontend
- criar novo fluxo paralelo de analise
- repetir transcricao completa em todo request
- reinventar a persistencia sem necessidade

## 9. Riscos

- duplicacao de memoria entre banco, cache e relatorios
- custo alto se a IA receber transcricao demais
- JSON inconsistente quebrando a sidebar
- trigger de recapitulacao disparando varias vezes
- extensao e backend ficarem desalinhados durante a transicao
- providers novos aumentando complexidade do roteador

## 10. Ordem recomendada

1. Persistir `MeetingMemory` no banco
2. Normalizar contratos e prompts
3. Ajustar `/tempo-real` para buffer curto e resumo vivo
4. Introduzir eventos e momentos-chave
5. Implementar `detectRecapTrigger()`
6. Atualizar sidebar com mapa mental e botoes
7. Fechar o diagnostico final
8. Adicionar custo, seguranca e fallback aprimorado
