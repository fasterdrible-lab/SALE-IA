# 📦 INSTALAR — Extensão SALEIA para Google Meet

## PRÉ-REQUISITOS
- Google Chrome (versão 88 ou superior)
- Servidor SALEIA rodando localmente ou em nuvem
- Chave de API do provedor escolhido (OpenAI, Anthropic ou Google)

---

## 1. INSTALAR A EXTENSÃO NO CHROME

1. Abra o Chrome e acesse: `chrome://extensions`
2. Ative o **Modo do desenvolvedor** (canto superior direito)
3. Clique em **"Carregar sem compactação"**
4. Selecione a pasta `chrome-extension/` deste repositório
5. A extensão aparece na barra do Chrome com o ícone 🤖

---

## 2. CONFIGURAR O BACKEND

1. Clique no ícone 🤖 na barra do Chrome para abrir o painel
2. Em **"Backend SALEIA"**, insira a URL do servidor:
   - Desenvolvimento local: `http://localhost:8000`
   - Servidor em produção: `https://seu-servidor.com`
3. Clique em **"Testar"** para confirmar a conexão

---

## 3. ESCOLHER O MODELO DE IA

1. Clique no ícone 🤖 na barra do Chrome
2. Na seção **"Modelo de IA"**, clique no modelo desejado:

   | Modelo | Badge | Indicado para |
   |---|---|---|
   | **GPT-4o** | 🟢 Recomendado | Máxima qualidade (~R$3,50/reunião) |
   | **GPT-4o Mini** | 🔵 Econômico | Ótima qualidade com baixo custo (~R$0,30/reunião) |
   | **Claude 3.5 Sonnet** | 🟠 Emocional | Melhor análise emocional (~R$4,00/reunião) |
   | **Gemini 1.5 Pro** | 🔴 Google | Alternativa Google AI (~R$2,00/reunião) |

3. Cole a **chave de API** do provedor escolhido no campo que aparecer
4. A chave é salva automaticamente no seu navegador (não sai da sua máquina!)

> 💡 **DICA:** Comece com GPT-4o. Se quiser economizar, mude para GPT-4o Mini.

---

## 4. USAR DURANTE UMA REUNIÃO

1. Acesse o **Google Meet** normalmente
2. A barra lateral **🤖 SALEIA** aparece automaticamente no lado direito
3. A IA começa a monitorar as legendas e envia dicas a cada 60 segundos:
   - 🚨 **Alerta Urgente** — ação imediata necessária
   - 🎯 **Perfil DISC** — identificação do estilo do cliente
   - 💡 **Dica Oculta** — o que você pode ter deixado passar
   - ⚡ **Próxima Fala** — sugestão do que dizer agora
   - 💰 **Sinal Financeiro** — menção a dinheiro, limite, estoque

> ⚠️ **ATENÇÃO:** Ative as legendas automáticas no Meet para a extensão funcionar  
> (Clique em `⋮` → **Legendas** → **Ativar legendas**)

---

## 5. CONFIGURAR O SERVIDOR SALEIA (BACKEND)

```bash
# Clonar o repositório
git clone https://github.com/fasterdrible-lab/SALEIA
cd SALEIA

# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
cp .env.example .env
# Edite .env e cole suas chaves de API

# Iniciar o servidor
uvicorn api.main:app --reload --port 8000
```

---

## SOLUÇÃO DE PROBLEMAS

| Problema | Solução |
|---|---|
| Sidebar não aparece no Meet | Recarregue a página do Meet (F5) |
| "❌ Sem conexão" no teste do backend | Verifique se o servidor está rodando |
| Dicas param de aparecer | Verifique se as legendas do Meet estão ativadas |
| Chave de API inválida | Recole a chave no popup (sem espaços) |
