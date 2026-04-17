# 📋 DOCUMENTAÇÃO COMPLETA DO PROJETO — SALEIA
> Registro oficial de desenvolvimento, infraestrutura e continuidade do projeto.
> Última atualização: 16/04/2026

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
[Google Meet + Tactiq]
        │ transcrição em tempo real
        ▼
[API SALEIA — FastAPI]
http://204.168.180.25:8000
        │
        ▼
[OpenAI GPT-4o]
        │
        ▼
[Resposta em tempo real ao vendedor]
```

---

## 🖥️ INFRAESTRUTURA DE PRODUÇÃO

| Item | Detalhe |
|------|---------|
| **Servidor** | VPS Ubuntu — 4GB RAM |
| **IP do Servidor** | `204.168.180.25` |
| **URL da API** | `http://204.168.180.25:8000` |
| **Documentação API** | `http://204.168.180.25:8000/docs` |
| **Health Check** | `http://204.168.180.25:8000/health` |
| **Usuário VPS** | `root` |
| **Pasta do projeto** | `/root/SALEIA` |
| **Ambiente virtual** | `/root/SALEIA/venv` |
| **Sistema Operacional** | Ubuntu Linux |

---

## 📡 ENDPOINTS DA API (v1.0.0)

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

## 🧠 EXEMPLO REAL VALIDADO — `/tempo-real` (16/04/2026)

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
    "tipo": "S",
    "confianca": "alta",
    "evidencia": "Cliente disse que fatura 50 mil por mês mas tem medo de investir.",
    "acao_sugerida": "Ofereça garantias e exemplos para tranquilizar o cliente."
  },
  "proxima_acao": "Explique os benefícios do produto intermediário, destacando casos de sucesso.",
  "sinal_financeiro": "Cliente fatura 50 mil/mês.",
  "produto_indicado": {
    "nome": "Produto Intermediário",
    "valor": "R$ 15.984",
    "justificativa": "O cliente tem capacidade financeira média e precisa de segurança para investir."
  },
  "oportunidade_perdida": "Não foram explorados exemplos de sucesso de outros clientes.",
  "objecoes": [
    {
      "objecao": "Medo de investir devido a experiências passadas negativas.",
      "resposta": "Compartilhe histórias de sucesso de clientes semelhantes e ofereça uma garantia."
    }
  ],
  "historico_resumido": "O cliente mencionou faturar 50 mil por mês, expressou medo de investir e perguntou sobre o custo."
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

---

## 🚀 ROADMAP

| Fase | Status | Descrição |
|------|--------|-----------|
| Backend API | ✅ Concluído | FastAPI com todos os endpoints funcionando |
| Deploy VPS | ✅ Concluído | Servidor rodando em `204.168.180.25:8000` |
| PM2 / Serviço permanente | 🔄 Pendente | Servidor nunca parar |
| Extensão Chrome | 🔄 Pendente | Distribuir para os vendedores |
| Integração Tactiq | 🔄 Pendente | Webhook automático com transcrição |
| Domínio + HTTPS | 🔄 Pendente | SSL para a API |
| Painel do Vendedor | 🔲 Futuro | Frontend Next.js |
| Banco de dados | 🔲 Futuro | Supabase para histórico |
| WhatsApp / CRM | 🔲 Futuro | Integração via Zapier/Make |

---

## 👥 DISTRIBUIÇÃO PARA MÚLTIPLOS VENDEDORES

Cada vendedor precisará de:
1. **Extensão Chrome** instalada (pasta `chrome-extension/`)
2. **URL da API** configurada: `http://204.168.180.25:8000`
3. **Tactiq** instalado no Chrome para transcrição automática

A API suporta múltiplos usuários simultâneos sem configuração adicional.

---

## 🔐 SEGURANÇA

- Nunca commitar o arquivo `.env`
- Nunca expor a `OPENAI_API_KEY` em chats ou logs
- Se uma chave for exposta, revogar imediatamente em `platform.openai.com/api-keys`

---

## 📞 INFORMAÇÕES DO REPOSITÓRIO

| Item | Detalhe |
|------|---------|
| **Repositório** | https://github.com/fasterdrible-lab/SALEIA |
| **Organização** | Fasterdrible Lab |
| **Criado em** | 16/04/2026 |
| **Versão** | 1.0.0 |
| **Stack** | Python + FastAPI + OpenAI GPT-4o |

---

*Documentação gerada em 16/04/2026 — SALEIA v1.0.0*