# 📋 DOCUMENTAÇÃO COMPLETA DO PROJETO — SALEIA
> Registro oficial de desenvolvimento, infraestrutura e continuidade do projeto.
> Última atualização: 17/04/2026

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
        │ MutationObserver captura legendas
        ▼
[content.js → chrome.runtime.sendMessage]
        │ proxy via background.js (contorna meetsw.js)
        ▼
[background.js → fetch]
        │ POST /tempo-real
        ▼
[API SALEIA — FastAPI + ngrok]
https://dime-flip-protector.ngrok-free.dev
        │
        ▼
[OpenAI GPT-4o]
        │
        ▼
[Resposta em tempo real ao vendedor na sidebar]
```

---

## 🖥️ INFRAESTRUTURA DE PRODUÇÃO

| Item | Detalhe |
|------|---------|
| **Servidor** | VPS Ubuntu — 4GB RAM, Hetzner Helsinki |
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

*Documentação atualizada em 17/04/2026 — SALEIA v1.1.0*