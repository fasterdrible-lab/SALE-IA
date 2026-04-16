# 🤖 SALEIA — Sistema de Automação de Leads, Engajamento e Inteligência Artificial em Atendimento de Vendas

> **SALEIA** é uma plataforma de inteligência artificial que atua ao lado do vendedor humano em tempo real, automatizando diagnósticos pré-reunião, suporte durante a venda e recapitulação estratégica pós-reunião.

---

## 🧭 O que é o SALEIA?

O SALEIA integra IA generativa (OpenAI GPT-4o) ao processo comercial de vendas consultivas. O sistema:

- **Antes da reunião:** gera um diagnóstico personalizado do cliente com base em seus dados (segmento, dores, objetivos)
- **Durante a reunião:** atua como um "co-piloto" ao lado do vendedor, sugerindo próximas falas, identificando gatilhos emocionais e respondendo objeções em tempo real
- **Após a reunião:** gera automaticamente uma recapitulação emocional + estratégica + próximos passos com base na transcrição

---

## 🏗️ Arquitetura do Sistema

```
LEAD ENTRA
    │
    ▼
[1. CAPTURA & QUALIFICAÇÃO]
    │  (formulário Typeform / tally.so)
    ▼
[2. DIAGNÓSTICO INTELIGENTE PRÉ-REUNIÃO]
    │  POST /diagnostico → GPT-4o gera briefing do cliente
    ▼
[3. AGENTE IA EM REUNIÃO — SUPORTE EM TEMPO REAL]
    │  POST /suporte-venda → próxima fala, gatilho, objeção, oferta
    ▼
[4. RECAPITULAÇÃO EMOCIONAL + ESTRATÉGICA PÓS-REUNIÃO]
    │  POST /recapitulacao → análise da transcrição
    ▼
[5. PROPOSTA PERSONALIZADA]
    │
    ▼
[6. FOLLOW-UP AUTOMATIZADO]
```

### Stack Tecnológica

| Camada | Tecnologia |
|--------|-----------|
| Backend API | Python + FastAPI |
| Inteligência Artificial | OpenAI GPT-4o via API |
| Orquestração de prompts | LangChain |
| Validação de dados | Pydantic v2 |
| Servidor ASGI | Uvicorn |
| Transcrição de áudio | Whisper API (futura integração) |
| Frontend (painel vendedor) | Next.js (fase futura) |
| Banco de dados | Supabase / Firebase (fase futura) |

---

## 📁 Estrutura de Pastas

```
SALEIA/
├── api/
│   ├── main.py          ← Backend FastAPI (endpoints da API)
│   └── config.py        ← Configuração de variáveis de ambiente
├── agent/
│   ├── prompt_templates/
│   │   ├── diagnostico.txt      ← Prompt para diagnóstico pré-call
│   │   ├── suporte_venda.txt    ← Prompt para suporte em tempo real
│   │   └── recapitulacao.txt    ← Prompt para recapitulação pós-reunião
│   ├── diagnostico.py           ← Módulo de geração de diagnóstico
│   ├── recapitulacao.py         ← Módulo de recapitulação
│   └── suporte_venda.py         ← Módulo de suporte ao vendedor
├── data/
│   ├── clientes/                ← JSONs de perfis de clientes
│   │   └── exemplo_cliente.json
│   ├── precos/                  ← Tabela de preços em JSON
│   │   └── valores.json
│   └── scripts/                 ← Scripts de vendas estruturados
├── .env.example                 ← Variáveis de ambiente (modelo)
├── .gitignore
├── requirements.txt
└── README.md
```

---

## ⚙️ Como Instalar e Rodar

### Pré-requisitos

- Python 3.11+
- Chave de API da OpenAI (`OPENAI_API_KEY`)

### 1. Clonar o repositório

```bash
git clone https://github.com/fasterdrible-lab/SALEIA.git
cd SALEIA
```

### 2. Criar e ativar o ambiente virtual

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# ou
.venv\Scripts\activate      # Windows
```

### 3. Instalar dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Edite o arquivo .env e insira sua OPENAI_API_KEY
```

### 5. Rodar o servidor

```bash
uvicorn api.main:app --reload --port 8000
```

O servidor estará disponível em: http://localhost:8000

A documentação interativa da API estará em: http://localhost:8000/docs

---

## 🔑 Variáveis de Ambiente

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `OPENAI_API_KEY` | Chave de API da OpenAI (obrigatória) | `sk-...` |
| `OPENAI_MODEL` | Modelo da OpenAI a ser utilizado | `gpt-4o` |
| `APP_PORT` | Porta do servidor | `8000` |
| `APP_ENV` | Ambiente de execução | `development` |

---

## 📡 Endpoints da API

### `GET /`
Health check — verifica se o sistema está online.

**Resposta:**
```json
{"status": "SALEIA online"}
```

---

### `POST /diagnostico`
Gera um diagnóstico personalizado do cliente para preparar o vendedor antes da reunião.

**Corpo da requisição:**
```json
{
  "nome": "João Silva",
  "segmento": "Esporte / Futebol",
  "dores": ["falta de estrutura de treino", "não sabe como evoluir"],
  "objetivos": ["melhorar performance", "chegar ao profissional"]
}
```

**Resposta:**
```json
{
  "diagnostico": "1. PERFIL EMOCIONAL DO CLIENTE\n..."
}
```

---

### `POST /suporte-venda`
Retorna sugestões em tempo real durante a conversa com o cliente.

**Corpo da requisição:**
```json
{
  "perfil_cliente": "Ansioso, motivado, busca validação",
  "fase": "Apresentação da solução",
  "ultima_fala": "Mas será que vai funcionar para mim?",
  "historico": "Cliente demonstrou interesse em evolução técnica"
}
```

**Resposta:**
```json
{
  "proxima_fala": "...",
  "gatilho_emocional": "...",
  "objecao_e_resposta": "...",
  "melhor_oferta": "..."
}
```

---

### `POST /recapitulacao`
Gera recapitulação emocional + estratégica + próximos passos da reunião.

**Corpo da requisição:**
```json
{
  "transcricao": "Vendedor: Olá João... Cliente: Tenho dificuldades com..."
}
```

**Resposta:**
```json
{
  "recapitulacao": "🧠 RECAPITULAÇÃO EMOCIONAL\n..."
}
```

---

## 📊 Dados de Referência

O projeto inclui arquivos de referência reais utilizados para treinar a lógica dos prompts:

- **PDFs de Consultoria Gratuita:** Christian, Cleber Panta, Nilton Vieira, Ruan Mendes
- **Diagnósticos de Clientes:** Andrea, Igor
- **Script Otimizado de Vendas:** versão final estruturada
- **Planilha de Valores:** tabela de preços e planos
- **Recapitulação Emocional e Estratégica:** modelo de pós-reunião com IA

---

## 🚀 Roadmap

| Fase | Status | Descrição |
|------|--------|-----------|
| Fase 1 — Estrutura base | ✅ Concluída | API, agentes, templates de prompt |
| Fase 2 — Painel do vendedor | 🔄 Planejada | Frontend Next.js com suporte em tempo real |
| Fase 3 — Transcrição de áudio | 🔄 Planejada | Integração com Whisper API |
| Fase 4 — Funil automatizado | 🔄 Planejada | Zapier/Make, WhatsApp, CRM |
| Fase 5 — Proposta automática | 🔄 Planejada | Geração de PDF com LaTeX/HTML |

---

## 🔒 Segurança

- **Nunca** insira a `OPENAI_API_KEY` diretamente no código
- O arquivo `.env` está no `.gitignore` e nunca deve ser commitado
- Use sempre o `.env.example` como referência para configuração

---

## 📄 Licença

Este projeto é propriedade de **Fasterdrible Lab**. Todos os direitos reservados.
