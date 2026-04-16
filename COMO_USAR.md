# SALEIA — Como Usar

> **Sistema de Automação de Leads, Engajamento e Inteligência Artificial em Atendimento**

O SALEIA automatiza 100% do processo pós-reunião: o vendedor só precisa fazer a reunião — o sistema cuida do resto sozinho.

---

## CONFIGURAÇÃO INICIAL (fazer só 1 vez)

### 1. Instalar dependências

```bash
pip install -r requirements.txt
```

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Abra o .env e preencha suas credenciais reais
```

Variáveis obrigatórias:
- `OPENAI_API_KEY` — sua chave da OpenAI (GPT-4o)
- `ZAPI_INSTANCE` + `ZAPI_TOKEN` + `ZAPI_PHONE` — para notificações WhatsApp
- **OU** `SMTP_USER` + `SMTP_PASS` + `EMAIL_VENDEDOR` — para notificações por e-mail

### 3. Iniciar o servidor

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

O servidor estará disponível em: `http://localhost:8000`

Documentação interativa: `http://localhost:8000/docs`

---

## CONFIGURAÇÃO DO TACTIQ (fazer só 1 vez)

```
CONFIGURAÇÃO ÚNICA (fazer só 1 vez):
1. Acesse app.tactiq.io → Settings → Integrations → Webhooks
2. Cole a URL: https://SEU_SERVIDOR/webhook/tactiq
3. Pronto! A partir de agora toda reunião é processada automaticamente.
```

---

## DURANTE A REUNIÃO

- **Só vender.** O Tactiq cuida da transcrição automaticamente no Google Meet.
- O painel do vendedor pode ser consultado a cada 60 segundos para receber dicas em tempo real.
- Endpoint de dicas: `GET /tactiq/status/{meeting_id}`

---

## APÓS A REUNIÃO

- **Aguarde ~30 segundos**
- O Tactiq dispara o webhook automaticamente para o SALEIA
- O SALEIA processa tudo em paralelo:
  - 💰 Diagnóstico Financeiro
  - 🎯 Perfil DISC
  - 🧠 Recapitulação Completa
  - 📦 Produto Recomendado
  - ⚠️ Objeções + Respostas
- **Receba o relatório completo no WhatsApp/e-mail automaticamente**

---

## FLUXO COMPLETO

```
VENDEDOR ENTRA NO MEET
        ↓
Tactiq transcreve automaticamente (já instalado)
        ↓
REUNIÃO ENCERRA
        ↓
Tactiq dispara Webhook → SALEIA /webhook/tactiq
        ↓
SALEIA processa tudo em paralelo:
  - Diagnóstico Financeiro
  - Perfil DISC
  - Recapitulação Completa
  - Produto Recomendado
  - Objeções + Respostas
        ↓
Relatório enviado automaticamente ao vendedor
(WhatsApp via Z-API ou e-mail)
        ↓
VENDEDOR RECEBE TUDO PRONTO — sem fazer nada
```

---

## PROCESSAMENTO MANUAL (transição)

Enquanto o webhook automático não estiver configurado, você pode processar manualmente:

```bash
curl -X POST http://localhost:8000/processar/manual \
  -H "Content-Type: application/json" \
  -d '{
    "transcript": "Cole aqui a transcrição do Tactiq...",
    "meeting_title": "Consultoria - Cliente João",
    "nome_cliente": "João Silva"
  }'
```

---

## ENDPOINTS DISPONÍVEIS

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `POST` | `/webhook/tactiq` | Webhook automático do Tactiq |
| `POST` | `/processar/manual` | Processamento manual de transcrição |
| `GET` | `/relatorios` | Listar todos os relatórios |
| `GET` | `/relatorio/{id}` | Buscar relatório específico |
| `POST` | `/notificar/{id}` | Reenviar notificação de um relatório |
| `GET` | `/tactiq/status/{meeting_id}` | Dicas em tempo real durante a reunião |
| `POST` | `/tactiq/transcript/{meeting_id}` | Atualizar transcrição parcial manualmente |
| `POST` | `/diagnostico-financeiro` | Apenas diagnóstico financeiro |
| `POST` | `/perfil-disc` | Apenas análise DISC |
| `POST` | `/recapitulacao` | Pipeline completo (sem salvar) |
| `GET` | `/health` | Status do sistema |

Documentação completa: `http://localhost:8000/docs`

---

## ESTRUTURA DE PASTAS

```
SALEIA/
├── /api
│   ├── main.py                  ← FastAPI — todos os endpoints
│   ├── webhook_tactiq.py        ← Processamento do webhook Tactiq
│   ├── notificador.py           ← Envio WhatsApp (Z-API) + E-mail (SMTP)
│   └── processador_tempo_real.py← Dicas em tempo real durante a reunião
├── /agent
│   ├── diagnostico.py           ← Diagnóstico financeiro do cliente
│   ├── perfil_disc.py           ← Perfil DISC + objeções
│   ├── recapitulacao.py         ← Recapitulação completa pós-reunião
│   └── prompt_templates/
│       └── mensagem_whatsapp.txt← Template da mensagem WhatsApp
├── /data
│   └── relatorios/              ← Relatórios JSON salvos automaticamente
├── .env.example                 ← Template de variáveis de ambiente
├── requirements.txt             ← Dependências Python
└── COMO_USAR.md                 ← Este arquivo
```

---

## CRITÉRIO DE PRODUTO

| Perfil do Cliente | Produto | Valor |
|-------------------|---------|-------|
| Fatura pouco / CLT baixo / tem estoque | Produto Base | R$ 3.000 - R$ 4.000 |
| Capacidade financeira média | Produto Intermediário | R$ 15.984,00 |
| Boa capacidade financeira | Produto Completo | R$ 29.892,00 |

---

## PERFIS DISC

| Perfil | Nome | Como Abordar |
|--------|------|--------------|
| **D** | Dominante | Direto, resultado rápido, sem rodeios |
| **I** | Influente | Emoção, histórias, entusiasmo |
| **S** | Estável | Segurança, garantias, sem pressão |
| **C** | Consciente | Dados, comparações, lógica |
