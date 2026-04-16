# 📖 COMO USAR — SALEIA

> **SALEIA** — Sistema de Automação de Leads, Engajamento e Inteligência Artificial em Atendimento

---

## ⚙️ INSTALAÇÃO (1 vez)

```bash
# 1. Clone o repositório (se ainda não fez)
git clone https://github.com/fasterdrible-lab/SALEIA.git
cd SALEIA

# 2. Crie o ambiente virtual Python
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Configure sua chave OpenAI
cp .env.example .env
# Edite o arquivo .env e insira sua OPENAI_API_KEY

# 5. Inicie o servidor
uvicorn api.main:app --reload --port 8000
```

A API estará disponível em: `http://localhost:8000`
Documentação interativa: `http://localhost:8000/docs`

---

## 🔴 ANTES DA REUNIÃO

1. Inicie o servidor SALEIA (passo 5 acima)
2. **Abra o painel no segundo monitor ou celular:**
   - Abra o arquivo `frontend/painel.html` diretamente no navegador (duplo clique)
   - Ou acesse: `file:///caminho/para/SALEIA/frontend/painel.html`
3. Instale o **Tactiq** no Chrome (extensão gratuita): https://tactiq.io
4. Abra o Google Meet normalmente — o Tactiq irá transcrever automaticamente

---

## 🟡 DURANTE A REUNIÃO (A cada ~5 minutos)

1. **Tactiq transcreve automaticamente** no Google Meet — você não precisa fazer nada
2. A cada 5 minutos, copie o trecho mais recente da transcrição do Tactiq
3. Cole no campo do **Painel SALEIA** (aberto no celular ou segundo monitor)
4. Clique em **"ANALISAR AGORA"** (ou use `Ctrl+Enter`)
5. Leia as dicas em tempo real **sem que o cliente veja**:
   - 🚨 **Alerta Urgente** — se houver algo crítico para agir agora
   - 🎯 **Perfil DISC** — como o cliente está se comportando
   - 💡 **Sinal Oculto** — o que ele não disse mas sinalizou
   - ⚡ **Próxima Ação** — o que fazer nos próximos 60 segundos
   - 💰 **Sinal Financeiro** — valores, cartão, salário, estoque detectados

---

## 🟢 APÓS A REUNIÃO

### Opção A — Webhook automático com Tactiq (recomendado)

Configure o Tactiq para enviar a transcrição automaticamente ao SALEIA:
- URL do webhook: `http://seu-servidor.com/webhook/tactiq`
- O relatório é gerado automaticamente e você recebe tudo pronto

### Opção B — Manual via API

1. Copie a transcrição completa do Tactiq
2. Acesse `http://localhost:8000/docs`
3. Use o endpoint `POST /recapitulacao-completa`
4. Cole a transcrição e receba o relatório completo

### O relatório gerado inclui:

```
━━━━━━━━━━━━━━━━━━━━━━━━━
🧠 RECAPITULAÇÃO EMOCIONAL
━━━━━━━━━━━━━━━━━━━━━━━━━
(O que o cliente sentiu, esperanças, medos, entusiasmo e resistência)

━━━━━━━━━━━━━━━━━━━━━━━━━
📊 RECAPITULAÇÃO ESTRATÉGICA
━━━━━━━━━━━━━━━━━━━━━━━━━
(Dores confirmadas, interesses, sinais de compra, objeções)

━━━━━━━━━━━━━━━━━━━━━━━━━
💰 DIAGNÓSTICO FINANCEIRO
━━━━━━━━━━━━━━━━━━━━━━━━━
(Capacidade financeira, produto recomendado, estratégia de pagamento)

━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 PERFIL DISC + OBJEÇÕES
━━━━━━━━━━━━━━━━━━━━━━━━━
(Perfil identificado, top 3 objeções + respostas prontas)

━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ O QUE O VENDEDOR NÃO PERCEBEU
━━━━━━━━━━━━━━━━━━━━━━━━━
(Sinais ocultos, oportunidades perdidas, gatilhos não explorados)

━━━━━━━━━━━━━━━━━━━━━━━━━
✅ PRÓXIMOS PASSOS (24-48h)
━━━━━━━━━━━━━━━━━━━━━━━━━
1. ação específica
2. ação específica
3. ação específica

━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ RESUMO EXECUTIVO
━━━━━━━━━━━━━━━━━━━━━━━━━
(3 linhas: quem é, o que quer, como fechar)
```

---

## 📡 ENDPOINTS DA API

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET`  | `/` | Health check — verifica se a API está no ar |
| `POST` | `/webhook/tactiq` | Recebe transcrição automática do Tactiq e gera relatório completo |
| `POST` | `/tempo-real` | Análise em tempo real durante a reunião |
| `POST` | `/diagnostico-financeiro` | Extrai dados financeiros da transcrição |
| `POST` | `/perfil-disc` | Identifica perfil DISC + objeções previstas |
| `POST` | `/recapitulacao-completa` | Gera relatório completo pós-reunião |
| `POST` | `/produto-recomendado` | Retorna produto ideal baseado no diagnóstico |

---

## 💰 TABELA DE PRODUTOS

| Produto | Valor | Perfil do Cliente |
|---------|-------|-------------------|
| **Produto Base** | R$ 3.000 – R$ 4.000 | Fatura pouco / tem estoque parado |
| **Produto Intermediário** | R$ 15.984,00 | Faturamento moderado |
| **Produto Completo** | R$ 29.892,00 | Alta capacidade de investimento |

---

## 🎯 PERFIS DISC — Referência Rápida

| Perfil | Características | Como fechar |
|--------|----------------|-------------|
| **D** Dominante | Direto, quer resultados, decidido | Vá ao ponto, mostre ROI rápido |
| **I** Influente | Emotivo, empolgado, relacional | Use histórias, crie conexão emocional |
| **S** Estável | Cauteloso, precisa de segurança | Mostre garantias, depoimentos, suporte |
| **C** Consciente | Analítico, quer dados, detalhista | Apresente números, comparativos, planilhas |

---

## ⚠️ OBSERVAÇÕES IMPORTANTES

- **Nunca** commite o arquivo `.env` com sua chave real
- Sempre informe ao cliente que a reunião está sendo transcrita (LGPD)
- A chave `OPENAI_API_KEY` cobre tanto o GPT-4o quanto o Whisper API
- O painel HTML funciona diretamente no navegador **sem servidor** — basta abrir o arquivo

---

## 🆘 SUPORTE

- Documentação interativa da API: `http://localhost:8000/docs`
- Repositório: https://github.com/fasterdrible-lab/SALEIA
