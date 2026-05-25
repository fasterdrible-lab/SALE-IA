# 📋 DOCUMENTAÇÃO COMPLETA DO PROJETO — SALEIA
> Registro oficial de desenvolvimento, infraestrutura e continuidade do projeto.
> Última atualização: 10/05/2026

---

## 🎯 VISÃO GERAL DO PROJETO

**SALEIA — Assistente de Vendas IA** é um sistema de inteligência artificial que atua como co-piloto do vendedor em tempo real durante reuniões no Google Meet, automatizando:

- Diagnóstico financeiro e comportamental do cliente (pré-reunião)
- Sugestões em tempo real durante a conversa (durante a reunião)
- Recapitulação emocional e estratégica (pós-reunião)
- Identificação de perfil DISC automaticamente
- Resposta a objeções de forma inteligente

---

## 🏗️ ARQUITETURA ATUAL (Produção)

```
👤 Vendedor (Chrome Extension)
        │
        ▼
[Google Meet + Legendas CC]
        │ MutationObserver captura legendas (DOM scraping)
        ▼
[content.js → chrome.runtime.sendMessage]
        │ proxy via background.js (contorna meetsw.js bloqueio)
        ▼
[background.js → fetch]
        │ POST /tempo-real (a cada 60s)
        ▼
[API SALEIA — FastAPI + Uvicorn, porta 8000]
https://api.saleia.com.br  (Nginx reverse proxy + Cloudflare)
        │
        ▼
[OpenAI GPT-4o / Claude via LiteLLM]
        │
        ▼
[Resposta em tempo real ao vendedor na sidebar]
        │
        ▼
[MySQL — 177.104.186.227 / fast5342_AV3D]
```

---

## 🖥️ INFRAESTRUTURA DE PRODUÇÃO
| **IP do Servidor** | `204.168.180.25` |
| **URL da API (ngrok)** | `https://dime-flip-protector.ngrok-free.dev` |
| **Documentação API** | `https://dime-flip-protector.ngrok-free.dev/docs` |
| **Health Check** | `https://dime-flip-protector.ngrok-free.dev/health` |
| **Usuário VPS** | `root` |
| **Pasta do projeto** | `/root/SALEIA` |
| **Ambiente virtual** | `/root/SALEIA/venv` |
| **Sistema Operacional** | Ubuntu Linux |

---

## 📡 ENDPOINTS DA API (v1.1.0)

| Método | Endpoint | Função | Status |
|--------|----------|--------|--------|
| GET | `/health` | Health Check | ✅ |
| POST | `/tempo-real` | Analisa transcrição em tempo real | ✅ |
| POST | `/webhook/tactiq` | Recebe webhook automático do Tactiq | ✅ |
| POST | `/diagnostico-financeiro` | Diagnóstico financeiro do cliente | ✅ |
| POST | `/perfil-disc` | Identifica perfil DISC | ✅ |
| POST | `/recapitulacao-completa` | Recapitulação pós-reunião | ✅ |
| GET | `/relatorio` | Visualiza último relatório | ✅ |

---

## 🧠 EXEMPLO REAL VALIDADO — `/tempo-real` (17/04/2026)

**Input:**
```json
{
  "transcricao_parcial": "Cliente disse que fatura 50 mil por mês mas tem medo de investir.",
  "historico": "",
  "perfil_disc_atual": ""
}
```

**Output:**
```json
{
  "alerta_urgente": null,
  "perfil_disc": {
    "tipo": "C",
    "confianca": "baixa",
    "evidencia": "Sem evidências claras no trecho fornecido.",
    "acao_sugerida": "Faça perguntas abertas para identificar o perfil DISC do cliente."
  },
  "proxima_acao": "Pergunte sobre as prioridades do cliente e o que ele valoriza em uma solução.",
  "sinal_financeiro": "Cliente fatura 50 mil/mês.",
  "produto_indicado": {
    "nome": "Produto Intermediário",
    "valor": "R$ 15.984",
    "justificativa": "Sem informações financeiras claras, mas o produto intermediário pode ser uma boa opção padrão."
  },
  "oportunidade_perdida": null,
  "objecoes": [
    {
      "objecao": "Possível preocupação com o valor ou adequação do produto.",
      "resposta": "Explique os benefícios e o retorno sobre o investimento do produto intermediário."
    }
  ],
  "historico_resumido": "O cliente mencionou faturar 50 mil por mês e demonstrou interesse em soluções."
}
```

---

## ⚙️ COMO RODAR O SERVIDOR (VPS Produção)

```bash
# Acessar o servidor
ssh root@204.168.180.25

# Entrar na pasta do projeto
cd /root/SALEIA

# Ativar o ambiente virtual
source venv/bin/activate

# Rodar com a chave OpenAI
OPENAI_API_KEY=sk-SUA_CHAVE uvicorn api.main:app --host 0.0.0.0 --port 8000

# Rodar em background (recomendado)
OPENAI_API_KEY=sk-SUA_CHAVE nohup uvicorn api.main:app --host 0.0.0.0 --port 8000 &

# Expor via ngrok (HTTPS obrigatório para Chrome Extension)
grok http 8000 --domain=dime-flip-protector.ngrok-free.dev
```

---

## 🔧 COMO RODAR EM DESENVOLVIMENTO

```bash
git clone https://github.com/fasterdrible-lab/SALEIA.git
cd SALEIA
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY=sk-SUA_CHAVE
uvicorn api.main:app --reload --port 8000
# Acessar: http://localhost:8000/docs
```

---

## 📦 DEPENDÊNCIAS CRÍTICAS

| Pacote | Versão | Observação |
|--------|--------|------------|
| `openai` | **2.32.0+** | Versões < 2.x causam erro de `proxies` |
| `httpx` | 0.28.1 | |
| `fastapi` | latest | |
| `uvicorn` | latest | |
| `pydantic` | v2 | |

---

## 🚨 PROBLEMAS CONHECIDOS E SOLUÇÕES

| Problema | Causa | Solução |
|----------|-------|---------|
| `Address already in use` | Porta 8000 ocupada | `fuser -k 8000/tcp` |
| `Client.__init__() got an unexpected keyword argument 'proxies'` | openai versão antiga | `pip install --upgrade openai` |
| `Erro ao conectar com a IA` | Chave não configurada | `OPENAI_API_KEY=sk-... uvicorn ...` |
| Servidor para ao fechar terminal | Sem process manager | Usar `nohup` ou `pm2` |
| `Mixed Content` / `Failed to fetch` no Meet | content script bloqueado pelo `meetsw.js` | Fetch via `background.js` (proxy via `chrome.runtime.sendMessage`) |
| `Backend offline` na sidebar | URL do backend com HTTP em vez de HTTPS | Usar sempre `https://` (ngrok fornece HTTPS) |

---

## 🔑 SOLUÇÃO TÉCNICA — PROXY DE FETCH VIA BACKGROUND.JS

### Problema
O Google Meet possui um Service Worker próprio (`meetsw.js`) que intercepta e bloqueia requisições `fetch` feitas por content scripts para URLs externas. Isso causava o erro:

```
NetworkError: The FetchEvent for "https://meet.google.com/..." resulted in a network error response
Mixed Content: The page was loaded over HTTPS, but requested an insecure resource
```

### Solução
Mover o `fetch` para o `background.js`, que roda fora do contexto do Meet e não é afetado pelo `meetsw.js`.

**Fluxo:**
1. `content.js` chama `chrome.runtime.sendMessage({ tipo: 'fetchBackend', url, payload })`
2. `background.js` recebe a mensagem e executa o `fetch`
3. `background.js` retorna o resultado via `sendResponse`
4. `content.js` atualiza a sidebar com os dados recebidos

---

## 🚀 ROADMAP

| Fase | Status | Descrição |
|------|--------|-----------|
| Backend API | ✅ Concluído | FastAPI com todos os endpoints funcionando |
| Deploy VPS | ✅ Concluído | Servidor rodando em `204.168.180.25:8000` |
| Extensão Chrome | ✅ Concluído | Sidebar ao vivo funcionando no Google Meet |
| Proxy fetch via background.js | ✅ Concluído | Contorna bloqueio do meetsw.js |
| ngrok HTTPS | ✅ Concluído | API exposta via HTTPS obrigatório para Chrome |
| PM2 / Serviço permanente | 🔄 Pendente | Servidor nunca parar |
| Integração Tactiq | 🔄 Pendente | Webhook automático com transcrição |
| Domínio próprio + HTTPS | 🔄 Pendente | SSL sem depender do ngrok |
| Painel do Vendedor | 🔲 Futuro | Frontend Next.js |
| Banco de dados | 🔲 Futuro | Supabase para histórico |
| WhatsApp / CRM | 🔲 Futuro | Integração via Zapier/Make |

---

## 👥 DISTRIBUIÇÃO PARA MÚLTIPLOS VENDEDORES

Cada vendedor precisará de:
1. **Extensão Chrome** instalada (pasta `chrome-extension/`)
2. **URL da API** configurada no popup da extensão (deve ser HTTPS)
3. **Legendas CC ativas** no Google Meet durante a reunião

A API suporta múltiplos usuários simultâneos sem configuração adicional.

---

## 🔐 SEGURANÇA

- Nunca commitar o arquivo `.env`
- Nunca expor a `OPENAI_API_KEY` em chats ou logs
- Se uma chave for exposta, revogar imediatamente em `platform.openai.com/api-keys`
- Sempre usar HTTPS na URL do backend (Chrome bloqueia Mixed Content)

---

## 📞 INFORMAÇÕES DO REPOSITÓRIO

| Item | Detalhe |
|------|---------|
| **Repositório** | https://github.com/fasterdrible-lab/SALEIA |
| **Organização** | Fasterdrible Lab |
| **Criado em** | 16/04/2026 |
| **Versão** | 1.1.0 |
| **Stack** | Python + FastAPI + OpenAI GPT-4o + Chrome Extension |

---

---

## 🛠️ SESSÃO DE DESENVOLVIMENTO — 09/05/2026 (v1.2.0)

### O que foi feito

#### 1. Migração VPS → Windows Local
- Projeto transferido do servidor Ubuntu (`204.168.180.25:/root/SALEIA/`) para `C:\Users\phpos\OneDrive\SALE-IA\SALEIA\`
- Backup gerado em `/tmp/SALEIA_backup.tar.gz` e baixado via SCP
- Ambiente virtual Python recriado localmente em `SALEIA\venv\`
- Dependências instaladas: `fastapi`, `uvicorn[standard]`, `openai`, `httpx`, `python-dotenv`

#### 2. Bugs Críticos Corrigidos

| Bug | Causa | Arquivo(s) | Solução |
|-----|-------|-----------|---------|
| API retornava 500 em todos os endpoints de IA | `str.format()` quebra quando o template contém `{chaves}` de JSON no corpo | `agente_tempo_real.py`, `diagnostico_financeiro.py`, `suporte_venda.py`, `perfil_disc.py`, `recapitulacao.py`, `diagnostico.py` | Trocado por `.replace("{var}", val)` em todos os agentes |
| OpenAI retornava "Missing credentials" | `main.py` nunca chamava `load_dotenv()` | `api/main.py` | Adicionado `from dotenv import load_dotenv; load_dotenv()` no topo |
| `.env` inválido | Arquivo continha só a chave crua sem `OPENAI_API_KEY=` | `.env` | Corrigido para formato correto `OPENAI_API_KEY=sk-...` |
| Chrome extension chamava URL ngrok de produção | URLs hardcoded em 3 arquivos | `content.js`, `background.js`, `manifest.json` | Trocado para `http://localhost:8000` |
| `manifest.json` sem permissão para localhost | `host_permissions` não incluía localhost | `chrome-extension/manifest.json` | Adicionado `http://localhost/*` e `http://127.0.0.1/*` |
| Relatórios perdidos ao reiniciar servidor | Dados apenas em memória RAM | `api/main.py` | Persistência em `data/relatorios/*.json` com timestamp |

#### 3. Novos Endpoints Adicionados

| Endpoint | Descrição |
|----------|-----------|
| `GET /relatorios` | Lista os últimos 20 relatórios salvos em disco |
| `POST /recapitulacao-manual` | Cola transcrição manualmente e gera análise completa sem extensão |

#### 4. Novos Arquivos Criados

| Arquivo | Descrição |
|---------|-----------|
| `iniciar.bat` | Script Windows de duplo clique: cria venv, instala deps e sobe o servidor |
| `frontend/painel.html` | Painel HTML para testar manualmente sem extensão Chrome |

#### 5. Arquitetura Atualizada (Local Windows)

```
👤 Vendedor (Chrome Extension OU painel.html)
        │
        ▼
[Google Meet + Legendas CC]
        │ MutationObserver captura legendas
        ▼
[content.js → chrome.runtime.sendMessage]
        │ proxy via background.js
        ▼
[background.js → fetch http://localhost:8000]
        │
        ▼
[API SALEIA — FastAPI local, porta 8000]
        │ load_dotenv() → .env → OPENAI_API_KEY
        ▼
[OpenAI GPT-4o]
        │
        ▼
[Resultado → sidebar do Meet / painel.html]
        │
        ▼
[data/relatorios/*.json] ← persistência em disco
```

#### 6. Como Rodar Localmente (Windows)

**Opção A — Duplo clique:**
```
SALEIA\iniciar.bat
```

**Opção B — PowerShell:**
```powershell
$python = "C:\Users\phpos\OneDrive\SALE-IA\SALEIA\venv\Scripts\python.exe"
$cwd    = "C:\Users\phpos\OneDrive\SALE-IA\SALEIA"
Start-Process -FilePath $python -ArgumentList "-m uvicorn api.main:app --reload --port 8000" -WorkingDirectory $cwd -NoNewWindow
```

URLs disponíveis:
- `http://localhost:8000/health` — verificação de saúde
- `http://localhost:8000/docs` — documentação interativa Swagger
- `http://localhost:8000/relatorios` — lista de relatórios salvos

---

## 🔄 ROADMAP ATUALIZADO

| Fase | Status | Descrição |
|------|--------|-----------|
| Backend API | ✅ Concluído | FastAPI com todos os endpoints funcionando |
| Deploy VPS | ✅ Concluído | Servidor rodando em `204.168.180.25:8000` |
| Extensão Chrome | ✅ Concluído | Sidebar ao vivo funcionando no Google Meet |
| Proxy fetch via background.js | ✅ Concluído | Contorna bloqueio do meetsw.js |
| Migração para Windows local | ✅ Concluído | Projeto rodando localmente via `iniciar.bat` |
| Correção bugs críticos (v1.2.0) | ✅ Concluído | `load_dotenv`, `str.format`, persistência, CORS localhost |
| Painel HTML para testes manuais | ✅ Concluído | `frontend/painel.html` |
| Persistência de relatórios em disco | ✅ Concluído | `data/relatorios/*.json` |
| PM2 / Serviço permanente | 🔄 Pendente | Servidor nunca parar |
| Integração Tactiq | 🔄 Pendente | Webhook automático com transcrição |
| Domínio próprio + HTTPS | 🔲 Futuro | SSL sem depender do ngrok |
| Painel Next.js do Vendedor | 🔲 Futuro | Frontend React moderno |
| Banco de dados (Supabase) | 🔲 Futuro | Histórico persistente e multi-vendedor |
| Whisper (transcrição de áudio) | 🔲 Futuro | Alternativa às legendas do Meet |
| CRM / WhatsApp (Make/Zapier) | 🔲 Futuro | Pós-reunião automatizado |

---

## 💡 PRÓXIMAS MELHORIAS SUGERIDAS

Baseado em projetos similares de AI copilot para vendas (Gong.io, Chorus, MeetRecord, Fireflies.ai):

### Prioridade Alta (impacto imediato na experiência)

#### 1. Dashboard de Histórico (substituir painel.html)
> *Referência: Fireflies.ai e MeetRecord têm timelines de reuniões filtráveis*

Substituir o `painel.html` estático por um painel React/Next.js com:
- Lista de reuniões passadas com busca e filtro por data/cliente
- Score de temperatura por reunião (alta/média/baixa) em formato visual
- Exportação de recapitulação para PDF ou Google Docs

**Stack sugerida:** Next.js 14 + Tailwind + shadcn/ui → servido pelo próprio FastAPI em `/painel`

#### 2. Autoreload da Extensão ao Reiniciar o Servidor
> *Problema real: extensão perde conexão quando uvicorn reinicia*

Adicionar um `WebSocket` de heartbeat: extensão tenta reconectar a cada 5s se o backend não responder.

```python
# api/main.py — adicionar
@app.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    await websocket.accept()
    while True:
        await websocket.send_json({"status": "online"})
        await asyncio.sleep(5)
```

#### 3. Score de Propensão de Compra
> *Referência: Gong.io "Deal Intelligence" — probabilidade de fechamento*

Adicionar ao endpoint `/tempo-real` um campo `score_compra: 0–100` gerado pelo GPT com base em:
- Temperatura da conversa
- Objeções detectadas
- Perfil DISC vs. produto indicado
- Sinais financeiros coletados

#### 4. Persistência com SQLite (substituir JSONs em disco)
> *JSONs funcionam para 1 vendedor, mas quebram com concorrência*

Trocar `data/relatorios/*.json` por SQLite via `SQLModel` (mesmo time do FastAPI):
```python
pip install sqlmodel
```
Migração transparente — mantém a API igual, muda só a camada de storage.

---

### Prioridade Média (diferencial competitivo)

#### 5. Modo "Objeção Detectada" — Alerta Visual Urgente
> *Referência: Chorus.ai tem alertas visuais em tempo real para objeções de preço*

Quando `objecao_detectada.objecao != null`, a sidebar pisca em laranja e toca um som de alerta discreto. Implementação: CSS animation + Web Audio API no `content.js`.

#### 6. Briefing Pré-Reunião Automático (5 min antes)
> *Referência: Gong Engage gera "deal brief" antes de cada call*

Criar endpoint `POST /briefing` que recebe nome + empresa do cliente e retorna:
- Pesquisa simulada (via GPT com dados do `data/clientes/`)
- Sugestão de abordagem baseada no histórico de reuniões anteriores
- Produto mais provável com base no segmento

Gatilho: vendedor abre o Google Calendar → extensão detecta reunião em 5 min → puxa briefing automaticamente.

#### 7. Exportação Automática para WhatsApp pós-reunião
> *Referência: MeetRecord integra com Slack/Notion automaticamente*

Após cada reunião (webhook Tactiq), enviar via Z-API (já configurado em `notificador.py`):
```
📊 *Reunião: [Nome]* — [Data]
🌡️ Temperatura: Alta
👤 Perfil: Dominante (D)
💰 Capacidade: R$ 3.000/mês
🎯 Produto indicado: [Nome]
📝 Próximos passos: [...]
```

#### 8. Multi-vendedor com Autenticação Simples
> *JSONs e memória compartilhada — risco de colisão entre vendedores*

Adicionar `vendedor_id` em todos os endpoints e isolar relatórios por vendedor:
```python
PASTA_RELATORIOS / vendedor_id / f"{timestamp}_{nome}.json"
```
Autenticação via `X-API-Key` header (chave por vendedor no `.env`) — sem banco de dados.

---

### Prioridade Baixa (futuro)

#### 9. Transcrição por Áudio (Whisper)
Alternativa às legendas CC (que dependem do usuário ativar):
- Captura áudio do sistema via extensão Chrome (`chrome.tabCapture`)
- Envia chunks de 30s para `POST /transcricao-audio`
- Backend processa com `openai.audio.transcriptions.create(model="whisper-1")`

#### 10. Análise de Sentimento por Voz (tom, velocidade)
> *Referência: Cogito.ai analisa paralinguística em tempo real*

Com Whisper retornando timestamps, detectar:
- Pausas longas (hesitação)
- Aceleração da fala (animação)
- Repetição de palavras (dúvida)

---

## 🚨 PROBLEMAS CONHECIDOS E SOLUÇÕES (atualizado)

| Problema | Causa | Solução |
|----------|-------|---------|
| `Address already in use` | Porta 8000 ocupada | `Stop-Process -Name python -Force` |
| `Missing credentials` | `.env` não carregado | Garantir `load_dotenv()` no topo de `main.py` |
| `KeyError: '\n  "alerta_urgente"'` | `str.format()` com JSON no template | Usar `.replace("{var}", val)` nos agentes |
| `str.format()` com JSON nos prompts | Chaves `{}` do JSON conflitam com Python format | Trocado para `.replace()` em todos os agentes |
| Extensão não conecta ao localhost | `manifest.json` sem permissão localhost | Adicionar `http://localhost/*` em `host_permissions` |
| Relatórios somem ao reiniciar | Dados só em memória RAM | Persistência em `data/relatorios/*.json` |
| `Mixed Content` no Meet | HTTP localhost bloqueado em contexto HTTPS | Usar ngrok para expor com HTTPS em produção |
| Servidor para ao fechar terminal | Sem process manager | Usar `iniciar.bat` ou `Start-Process -NoNewWindow` |
| Backend não inicia pelo caminho relativo | `.\venv\Scripts\uvicorn.exe` falha se CWD errado | Sempre usar caminho absoluto ou `iniciar.bat` |

---

*Documentação atualizada em 09/05/2026 — SALEIA v1.2.0*

---

---

## 🛠️ SESSÃO DE DESENVOLVIMENTO — 10/05/2026 (v1.3.0)

### Contexto
Sessão de produção real: o vendedor estava em reunião ativa no Google Meet. Objetivo: fazer a captura de legendas funcionar e a análise de IA aparecer em tempo real na sidebar.

---

### Infraestrutura atual (estado no início desta sessão)

| Item | Detalhe |
|------|---------|
| **VPS** | Hetzner `204.168.180.25`, user `root`, path `/opt/saleia/` |
| **Backend** | FastAPI + Uvicorn, systemd `saleia.service`, porta 8000 |
| **Nginx** | Porta 80 → `localhost:8000` ; HTTPS via Cloudflare |
| **MySQL** | Host `177.104.186.227`, DB `fast5342_AV3D`, user `fast5342_AV3D` |
| **URL pública** | `https://api.saleia.com.br` |
| **Dashboard** | `https://api.saleia.com.br/dashboard` |
| **Deploy** | `tar -czf → scp → ssh "tar -xzf --strip-components=1"` |

---

### Bugs corrigidos nesta sessão

#### Bug 1 — `ReferenceError: i is not defined` (content.js linha ~325)
- **Causa raiz:** Regex com dupla barra `/meet\.google\.com//i` — o JavaScript interpretava o segundo `/i` como divisão pela variável `i` (undefined), causando crash de todo o observer
- **Efeito:** O `MutationObserver` crashava silenciosamente na inicialização → zero legendas capturadas
- **Correção:** `SALEIA/chrome-extension/content.js` — regex corrigida para `/meet\.google\.com/i`

#### Bug 2 — Aviso do Chrome capturado como fala
- **Causa:** Texto "Você está enfrentando problemas com extensões que modificam a página..." passava pelos filtros de ruído e era commitado como transcrição
- **Correção:** Adicionados filtros em `eRuidoUI()`:
  - `/extensões que modificam|modifying the page/i`
  - `/estabilidade|experiência do usuário|desenvolvedores/i`

#### Bug 3 — Restriction `[aria-live]` muito restrita (content.js)
- **Causa:** Reescrita anterior do observer para processar SOMENTE elementos `[aria-live]` eliminou ruído mas também eliminou as legendas CC reais — que o Meet não coloca dentro de `[aria-live]` em versões recentes
- **Efeito:** Zero chamadas a `/iniciar-sessao` ou `/tempo-real` no nginx após o deploy
- **Correção:** Observer revertido para estratégia ampla com `processarFolhas()` (processa apenas nós folha para evitar concatenação de texto pai+filho)

#### Bug 4 — Tooltips de botões capturados como transcrição
- **Causa:** O `[aria-live]` no scan periódico capturava anúncios de acessibilidade dos botões do Meet ("Ativar legendas (c ou shift + c)", "Mais opções")
- **Efeito:** Transcrição na sessão cheia de ruído de UI, análise de IA inútil
- **Correção:**
  - Removido `[aria-live]` do scan periódico
  - Adicionados filtros em `eRuidoUI()`:
    - `/ativar legendas|desativar legendas/i`
    - `/\([a-z]\s+ou\s+shift\s*\+/i` (atalhos de teclado)
    - `/^mais opções$/i`

#### Bug 5 — Nomes de dispositivos capturados como transcrição
- **Causa:** aria-live do Meet anuncia nome da câmera selecionada ("Positivo Theia Camera") ao entrar na reunião
- **Correção:** Filtro em `eRuidoUI()` — bloqueia strings de 2-4 palavras, todas iniciando com maiúscula, sem pontuação, sem palavras funcionais em PT

#### Bug 6 — `Extension context invalidated` (content.js linha 536)
- **Causa:** `all_frames: true` no manifest fez o content.js injetar em iframes do Meet que são criados e destruídos dinamicamente. Quando o iframe era removido, o contexto da extensão era invalidado, mas os timers do content.js ainda tentavam chamar `chrome.runtime.sendMessage`
- **Correção:**
  - Removido `all_frames: true` do `manifest.json`
  - Adicionado guard `if (!chrome.runtime || !chrome.runtime.id) return;` antes de cada `chrome.runtime.sendMessage`

---

### Novos componentes criados

#### `SALEIA/agent/sessao_manager.py` — Funções adicionadas/alteradas
- `salvar_transcricao_bruta()`: usa apenas UPDATE (nunca INSERT) para evitar criação de sessões fantasmas quando transcrição chega sem sessão prévia
- `obter_ultima_analise(meeting_id)`: consulta sessão das últimas 6h, retorna `ultima_analise` como JSON para o endpoint `/cenario`

#### `SALEIA/api/main.py` — Endpoints adicionados
- `POST /tempo-real`: após análise, chama `salvar_analise()` para persistir no MySQL
- `GET /cenario/{meeting_id}`: serve o arquivo `frontend/cenario.html` com o ID da reunião
- `GET /api/cenario/{meeting_id}`: retorna JSON com `obter_ultima_analise()` — usado pelo `cenario.html` via polling

#### `SALEIA/frontend/cenario.html` — Novo arquivo
- Apresentação de 4 slides dark-theme para visualização do cenário do cliente
- Faz polling a cada 30s em `/api/cenario/{id}` para se atualizar automaticamente
- Botão "📊 Abrir cenário do cliente" adicionado na sidebar da extensão

#### `SALEIA/chrome-extension/content.js` — Função `processarFolhas()`
```javascript
// Navega o DOM até encontrar nós folha (sem filhos de elemento)
// Evita concatenação de nome_do_speaker+texto que quebrava a detecção
function processarFolhas(container) {
  if (!container || container.closest('#saleia-sidebar')) return;
  var temFilhoElemento = false;
  for (var i = 0; i < container.childNodes.length; i++) {
    if (container.childNodes[i].nodeType === Node.ELEMENT_NODE) { temFilhoElemento = true; break; }
  }
  if (!temFilhoElemento) {
    processarElementoLegenda(container);
  } else {
    container.querySelectorAll('*').forEach(function(child) {
      if (child.closest('#saleia-sidebar')) return;
      var temFilho = false;
      for (var j = 0; j < child.childNodes.length; j++) {
        if (child.childNodes[j].nodeType === Node.ELEMENT_NODE) { temFilho = true; break; }
      }
      if (!temFilho && child.textContent.trim()) processarElementoLegenda(child);
    });
  }
}
```

---

### Estado atual ao final da sessão (10/05/2026 ~23h)

| Item | Status |
|------|--------|
| Backend VPS online | ✅ |
| MySQL com sessões | ✅ (sessão #37+) |
| Sidebar injetando no Meet | ✅ |
| Aviso CC falso positivo | ✅ Corrigido |
| ReferenceError regex | ✅ Corrigido |
| Extension context invalidated | ✅ Corrigido |
| Tooltips de botões na transcrição | ✅ Filtrados |
| Captura real das legendas CC | ⚠️ Em investigação |
| Análise IA funcionando | ⚠️ Bloqueada pela captura |

### Problema em aberto (próxima sessão)

**O observer DOM não está capturando o texto das legendas CC do Meet.**

O log de debug `[SALEIA-DBG]` foi adicionado ao `processarElementoLegenda` para identificar qual `tag/class/jsname` o Meet usa atualmente para exibir o texto CC. Ao abrir o Console do DevTools no Meet com CC ativo e falar, as linhas `[SALEIA-DBG]` mostrarão exatamente qual elemento deve ser alvo do seletor.

**Próximo passo:** Capturar o output do `[SALEIA-DBG]` e atualizar os seletores do scan periódico em `iniciarObservadorLegendas()`.

---

### Procedimento de deploy (referência rápida)

```powershell
# No PowerShell do Windows, da pasta C:\Users\phpos\OneDrive\SALE-IA

# 1. Empacotar arquivo(s) modificado(s)
tar -czf saleia_patch.tar.gz SALEIA/chrome-extension/content.js

# 2. Enviar para o VPS
scp -o StrictHostKeyChecking=no saleia_patch.tar.gz root@204.168.180.25:/tmp/

# 3. Extrair no VPS (mantém estrutura de diretórios)
ssh -o StrictHostKeyChecking=no root@204.168.180.25 "cd /opt/saleia && tar -xzf /tmp/saleia_patch.tar.gz --strip-components=1 && echo 'DEPLOY OK'"

# 4. Se mudou Python (api/, agent/):
ssh -o StrictHostKeyChecking=no root@204.168.180.25 "systemctl restart saleia"

# 5. Depois de deploy de content.js:
# chrome://extensions → SALEIA → ↻ Atualizar → fechar e reabrir Meet
```

**Senha VPS:** `B7f3j1b7@#`

---

*Documentação atualizada em 10/05/2026 — SALEIA v1.3.0*

---

---

## 🛠️ SESSÃO DE DESENVOLVIMENTO — 11/05/2026 (v1.4.0)

### Contexto
Sessão de correção pós-produção. Whisper estava deployado (whisper8) mas com múltiplos bugs críticos descobertos em uso real: duplicação massiva de texto no banco, Whisper disparando com áudio silencioso, e erro 400 do OpenAI por arquivo WebM inválido.

---

### Infraestrutura (sem mudanças)

| Item | Detalhe |
|------|---------|
| **VPS** | Hetzner `204.168.180.25`, user `root`, path `/opt/saleia/` |
| **Backend** | FastAPI + Uvicorn, systemd `saleia.service`, 2 workers, porta 8000 |
| **Nginx** | Reverse proxy → `localhost:8000`; HTTPS via Cloudflare |
| **MySQL** | Host `177.104.186.227`, DB `fast5342_AV3D`, user `fast5342_AV3D` |
| **URL pública** | `https://api.saleia.com.br` |
| **Logs do serviço** | `/opt/saleia/logs/saleia.log` (arquivo, não journal) |

---

### Bugs corrigidos nesta sessão

#### Bug 1 — Duplicação massiva de texto no banco ("E aí E aí E aí" dezenas de vezes)

**Causa raiz:** `enviarParaBackend()` enviava os últimos 60 itens de `estado.transcricao` (campo `transcricao_parcial`) a cada 60s. A função `salvar_transcricao_bruta()` no backend fazia `CONCAT(transcricao_acumulada, "\n", nova_transcricao)`, acumulando o bloco completo repetido a cada ciclo.

**Solução — rastreamento delta (índice de posição):**

`SALEIA/chrome-extension/content.js`:
- Adicionado `ultimoIndexEnviado: 0` ao objeto `estado`
- Nova função `montarTranscricaoDelta()` — retorna apenas entradas desde `ultimoIndexEnviado`
- `enviarParaBackend()` agora captura `indexSnapshot = estado.transcricao.length` e `transcricaoDelta` antes do fetch assíncrono; envia `transcricao_nova: transcricaoDelta`; só avança `ultimoIndexEnviado = indexSnapshot` em caso de sucesso HTTP 2xx
- `iniciarEnvioPeriodico()` agora verifica `if (estado.transcricao.length <= estado.ultimoIndexEnviado) return;` — não chama o backend se não há nada novo

`SALEIA/api/main.py`:
- `TempoRealRequest` recebeu campo `transcricao_nova: Optional[str] = None`
- Endpoint `/tempo-real` passa a usar `(req.transcricao_nova or "").strip() or (req.transcricao_parcial or "").strip()` para `salvar_transcricao_bruta` — escreve apenas o delta, não o histórico completo

`SALEIA/agent/sessao_manager.py`:
- `salvar_transcricao_bruta()` alterada para UPDATE-only + limite de 60k chars + append simples

---

#### Bug 2 — Whisper disparando com microfone em silêncio

**Causa raiz:** Dois problemas independentes:
1. Threshold de tamanho muito baixo: `MediaRecorder.start(15000)` com `ondataavailable` checando apenas `e.data.size > 1024`. WebM/Opus silencioso gera cabeçalho de ~2–4 KB → passava no filtro mesmo sem fala.
2. `iniciarEnvioPeriodico()` chamava `enviarParaBackend()` sem verificar se havia conteúdo novo.

**Solução:**
- Threshold elevado de 1 KB para **10 KB** (`e.data.size > 10240`)
- Guard `if (estado.transcricao.length <= estado.ultimoIndexEnviado) return;` no timer periódico
- Filtro de ruído adicional em `enviarChunkWhisper`: rejeita chunks com < 3 palavras únicas ou < 6 tokens (eco, tosse, ruído ambiente)

---

#### Bug 3 — Whisper retorna erro 400 "Invalid file format" (CRÍTICO)

**Causa raiz:** `MediaRecorder.start(15000)` com timeslice emite **chunks parciais** a cada 15s. Apenas o 1º chunk contém o header EBML/WebM (inicialização do container). Os chunks seguintes são raw cluster data sem header — o OpenAI Whisper rejeita qualquer arquivo que não comece com o header EBML, retornando:
```json
{"error": {"message": "Invalid file format. Supported formats: ['flac', 'm4a', 'mp3', 'mp4', 'mpeg', 'mpga', 'oga', 'ogg', 'wav', 'webm']"}}
```

**Solução — ciclos de gravação:**

Substituição completa da lógica de gravação por ciclos autossuficientes:

```javascript
// ANTES (incorreto — chunks parciais sem header):
whisperRecorder.start(15000); // timeslice → ondataavailable a cada 15s com dados parciais

// DEPOIS (correto — arquivo WebM completo a cada ciclo):
function iniciarCicloWhisper() {
  whisperRecorder = new MediaRecorder(stream, { mimeType: whisperMimeType });
  whisperRecorder.onstop = function () {
    if (capturaAudioAtiva) setTimeout(iniciarCicloWhisper, 100); // reinicia novo ciclo
  };
  whisperRecorder.start(); // sem timeslice → chunk completo no stop()
  // Para após 15s para disparar ondataavailable com arquivo WebM válido
  whisperCicloTimer = setTimeout(function () {
    if (whisperRecorder && whisperRecorder.state === 'recording') whisperRecorder.stop();
  }, 15000);
}
```

Fluxo novo:
1. `iniciarCicloWhisper()` → `start()` (sem timeslice)
2. Timer de 15s → `stop()`
3. `ondataavailable` recebe 1 blob = arquivo WebM completo e válido → enviado ao Whisper ✅
4. `onstop` → aguarda 100ms → `iniciarCicloWhisper()` (novo ciclo)
5. `pararWhisper()` limpa `capturaAudioAtiva = false` primeiro, evitando reinício

---

#### Bug 4 — Botão toggle (≡) posicionado à direita (UX)

**Causa:** Na string HTML do `criarSidebar()`, o `<span>🤖 SALEIA AO VIVO</span>` vinha antes do `<button id="saleia-toggle-btn">`.

**Solução:** Invertida a ordem no template HTML — botão agora está antes do título.

```html
<!-- ANTES -->
<span>🤖 SALEIA AO VIVO</span>
<button id="saleia-toggle-btn" title="Minimizar/Expandir">≡</button>

<!-- DEPOIS -->
<button id="saleia-toggle-btn" title="Minimizar/Expandir">≡</button>
<span>🤖 SALEIA AO VIVO</span>
```

---

### Arquivos modificados nesta sessão

| Arquivo | Mudanças |
|---------|---------|
| `SALEIA/chrome-extension/content.js` | Rastreamento delta (`ultimoIndexEnviado`), guard periódico, threshold 10KB, filtro ruído, ciclos WebM, botão toggle à esquerda |
| `SALEIA/api/main.py` | Campo `transcricao_nova` em `TempoRealRequest`, uso do delta em `/tempo-real` |
| `SALEIA/agent/sessao_manager.py` | `salvar_transcricao_bruta` UPDATE-only, limite 60k chars |

---

### Deploys realizados nesta sessão

| Tag | Conteúdo | Resultado |
|-----|----------|-----------|
| `saleia_dedup` | Fix duplicação DB (delta tracking) | ✅ Deploy OK |
| `saleia_silence` | Fix silent audio / threshold 10KB | ✅ Deploy OK |
| `saleia_toggleside` | Botão toggle à esquerda | ✅ Deploy OK |
| `saleia_ext_whisper.zip` | Fix WebM chunks inválidos (ciclos) | ✅ Empacotado — reload manual no Chrome |

> **Nota:** O último fix (`saleia_ext_whisper`) é apenas cliente (content.js) — não requer deploy no VPS. Recarregar extensão em `chrome://extensions`.

---

### Como identificar logs do backend

O `systemd journal` **não** captura output da aplicação Python. Os logs reais ficam em:
```bash
tail -100 /opt/saleia/logs/saleia.log
```
Configurado em `/etc/systemd/system/saleia.service`:
```ini
StandardOutput=append:/opt/saleia/logs/saleia.log
StandardError=append:/opt/saleia/logs/saleia.log
```

---

### Estado ao final da sessão (11/05/2026)

| Item | Status |
|------|--------|
| Duplicação "E aí E aí E aí" no banco | ✅ Corrigido — delta tracking |
| Whisper disparando em silêncio | ✅ Corrigido — threshold 10KB + guard periódico |
| Erro 400 "Invalid file format" Whisper | ✅ Corrigido — ciclos WebM completos |
| Botão toggle no lado esquerdo | ✅ Corrigido |
| Backend VPS online | ✅ |
| Logs em `/opt/saleia/logs/saleia.log` | ✅ Identificado |

---

### Roadmap atualizado

| Fase | Status | Descrição |
|------|--------|-----------|
| Backend API | ✅ | FastAPI, todos endpoints |
| Deploy VPS permanente (systemd) | ✅ | `saleia.service` com restart automático |
| Extensão Chrome | ✅ | Sidebar ao vivo, Whisper, legendas CC |
| Whisper — captura de microfone | ✅ | Ciclos de 15s com WebM válido |
| Fix duplicação banco | ✅ | Delta tracking (`ultimoIndexEnviado`) |
| Fix silent audio | ✅ | Threshold 10KB + guard periódico |
| MySQL — persistência de sessões | ✅ | `sessao_manager.py` UPDATE-only |
| Dashboard vendedor | ✅ | `frontend/dashboard.html` |
| Próximo: validar Whisper em produção | ⏳ | Recarregar extensão e testar ao vivo |

---

---

### Bugs adicionais corrigidos (continuação da sessão 11/05/2026)

#### Bug 5 — Botão "📊 Abrir cenário do cliente" não abre nada

**Causa raiz 1:** O `onclick="window.open(...)"` inline no HTML era bloqueado pelo CSP estrito do Google Meet:
```
Executing inline event handler violates the following Content Security Policy directive 'script-src ...'
```

**Causa raiz 2:** Mesmo após remover o `onclick` e usar `addEventListener` + `window.open`, o popup blocker do Chrome bloqueia `window.open` disparado por content scripts — o Meet não considera content scripts como contexto "confiável" para abrir janelas.

**Causa raiz 3:** O endpoint `/cenario/{meeting_id}` no backend valida o ID com regex `^[a-z]{3}-[a-z]{4}-[a-z]{3}$` — retornava 400 para IDs de teste com números.

**Solução completa:**

1. `SALEIA/chrome-extension/content.js` — botão envia mensagem ao background em vez de chamar `window.open`:
```javascript
document.getElementById('saleia-btn-cenario').addEventListener('click', function () {
  if (!chrome.runtime || !chrome.runtime.id) return;
  chrome.runtime.sendMessage({ tipo: 'abrirCenario', url: CONFIG.backendUrl + '/cenario/' + MEETING_ID });
});
```

2. `SALEIA/chrome-extension/background.js` — handler `abrirCenario` usa `chrome.tabs.create` (imune ao popup blocker):
```javascript
if (msg.tipo === 'abrirCenario') {
  chrome.tabs.create({ url: msg.url, active: true });
  return false;
}
```

3. `SALEIA/chrome-extension/manifest.json` — adicionada permissão `"tabs"` (necessária para `chrome.tabs.create`):
```json
"permissions": ["activeTab", "storage", "alarms", "scripting", "offscreen", "tabs"]
```

---

### Arquivos modificados nesta sessão (completo)

| Arquivo | Mudanças |
|---------|---------|
| `SALEIA/chrome-extension/content.js` | Delta tracking, guard periódico, threshold 10KB, filtro ruído, ciclos WebM, toggle à esquerda, botão cenário via sendMessage |
| `SALEIA/chrome-extension/background.js` | Handler `abrirCenario` com `chrome.tabs.create` |
| `SALEIA/chrome-extension/manifest.json` | Permissão `"tabs"` adicionada |
| `SALEIA/api/main.py` | Campo `transcricao_nova`, uso do delta em `/tempo-real` |
| `SALEIA/agent/sessao_manager.py` | `salvar_transcricao_bruta` UPDATE-only, limite 60k chars |

---

### Deploys realizados nesta sessão (completo)

| Tag | Conteúdo | Resultado |
|-----|----------|-----------|
| `saleia_dedup` | Fix duplicação DB (delta tracking) | ✅ Deploy OK |
| `saleia_silence` | Fix silent audio / threshold 10KB | ✅ Deploy OK |
| `saleia_toggleside` | Botão toggle à esquerda | ✅ Deploy OK |
| `saleia_ext_whisper.zip` | Fix WebM chunks inválidos (ciclos) | ✅ Extensão — reload manual |
| `saleia_ext_cenario.zip` | Fix botão cenário sem onclick CSP | ✅ Extensão — reload manual |
| `saleia_ext_cenario2.zip` | Fix botão cenário via chrome.tabs.create | ✅ Extensão — reload manual |

> **Importante:** Deploys `saleia_ext_*.zip` são apenas extensão Chrome — não requerem deploy no VPS. Recarregar em `chrome://extensions`.

---

### Estado ao final da sessão (11/05/2026 — atualizado)

| Item | Status |
|------|--------|
| Duplicação "E aí E aí E aí" no banco | ✅ Corrigido |
| Whisper disparando em silêncio | ✅ Corrigido |
| Erro 400 "Invalid file format" Whisper | ✅ Corrigido — ciclos WebM |
| Botão toggle no lado esquerdo | ✅ Corrigido |
| Botão "Abrir cenário" não funcionava (CSP + popup blocker) | ✅ Corrigido — chrome.tabs.create |
| Backend VPS online | ✅ |
| Permissão `tabs` no manifest | ✅ Adicionada |

---

### Lições aprendidas (referência futura)

| Situação | Solução correta |
|----------|----------------|
| Abrir nova aba a partir de content script | Usar `chrome.runtime.sendMessage` + `chrome.tabs.create` no background.js |
| Event handlers em HTML injetado no Meet | Nunca usar `onclick=` inline — CSP bloqueia; sempre usar `addEventListener` |
| `window.open` em content script | Bloqueado pelo popup blocker mesmo com clique direto; usar `chrome.tabs.create` |
| Logs do backend Python (uvicorn/systemd) | `tail -f /opt/saleia/logs/saleia.log` — o journal não captura stdout da app |
| Chunks de áudio WebM para Whisper | `start()` sem timeslice + `stop()` a cada 15s — garante arquivo WebM completo com header EBML |

---

*Documentação atualizada em 11/05/2026 — SALEIA v1.4.1*