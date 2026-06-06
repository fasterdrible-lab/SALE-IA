# COMO USAR O SALEIA — V.1.4.5

> Assistente de Vendas com IA para Google Meet
> Produção: https://api.saleia.com.br | Dashboard: https://api.saleia.com.br/dashboard

---

## ACESSO RÁPIDO

| O que fazer | Onde |
|---|---|
| Ver análises e relatórios | https://api.saleia.com.br/dashboard |
| Configurar APIs e transcrição | Dashboard → Configurações |
| Gerenciar usuários | Dashboard → Configurações → Usuários |
| Recuperar senha | https://api.saleia.com.br/login → "Esqueci minha senha" |
| Verificar saúde do servidor | https://api.saleia.com.br/health |

---

## EXTENSÃO CHROME — INSTALAÇÃO

1. Abra `chrome://extensions` no Chrome
2. Ative o **Modo do desenvolvedor** (canto superior direito)
3. Clique em **Carregar sem compactação**
4. Selecione a pasta: `SALEIA/chrome-extension`
5. A extensão aparece na barra do Chrome com o ícone SALEIA

Para atualizar após mudanças: `chrome://extensions` → botão recarregar (🔄) na extensão SALEIA.

---

## EXTENSÃO CHROME — COMO USAR

1. Abra uma reunião no **Google Meet**
2. Ative as legendas no Meet: clique em **CC** ou pressione `Shift+C`
3. A sidebar SALEIA aparece automaticamente no lado direito
4. Faça login com sua conta SALEIA quando solicitado
5. Clique em **Iniciar captura de áudio** para transcrição em tempo real
6. O coach aparece na sidebar com sugestões a cada análise

### O que aparece na sidebar

| Seção | Descrição |
|---|---|
| Coach em tempo real | Sugestões de fala, perfil DISC, alertas de objeção |
| Captura de áudio | Status da transcrição (Whisper ou Groq) |
| Recapitulação | Resumo gerado automaticamente ao detectar deixa verbal |
| Próxima análise | Contador regressivo até a próxima chamada de IA |

---

## DASHBOARD — SEÇÕES

### Reuniões
Lista todas as reuniões com score final, provedor de IA, perfil DISC e custo estimado.
Filtros disponíveis: data início/fim, provedor de IA, busca por texto.

### Histórico
Gráfico de evolução do score por reunião, momentos-chave e eventos estruturados.

### Relatórios
Análises manuais e diagnósticos financeiros gerados fora do fluxo ao vivo.

### Condução (Cenário)
Geração de roteiros de apresentação, recapitulação e fechamento via IA.
Acesso pelo botão **Cenário** durante ou após uma reunião.

---

## CONFIGURAÇÕES — GUIA COMPLETO

Acesso: Dashboard → aba **Configurações** (requer conta admin)

### Usuários
- Lista todos os usuários cadastrados com nome, e-mail, perfil e plano
- Ações: editar perfil/plano, resetar senha, ativar/desativar conta

### Configuração de APIs (Provedores de IA)
Ordem ativa de fallback: **DeepSeek → OpenAI → Anthropic → Gemini**

Para cada provedor:
- **Adicionar chave**: cole a chave → Salvar
- **Testar**: verifica se a chave está válida
- **Ativar/Inativar**: remove o provedor da cadeia de fallback
- **Definir como principal**: coloca o provedor na primeira posição

| Provedor | Variável | Modelo padrão |
|---|---|---|
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| OpenAI | `OPENAI_API_KEY` | `gpt-4o` |
| Anthropic | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` |
| Gemini | `GEMINI_API_KEY` | `gemini-2.0-flash` |

### Transcrição de Áudio
Controla qual serviço transcreve o áudio capturado durante a reunião.

| Provedor | Modelo | Chave necessária | Custo |
|---|---|---|---|
| **Whisper** (OpenAI) | `whisper-1` | `OPENAI_API_KEY` | Pago por minuto |
| **Groq** | `whisper-large-v3` | `GROQ_API_KEY` | Grátis até cota diária |

**Como configurar o Groq:**
1. Crie uma conta em https://console.groq.com
2. Vá em **API Keys** → **Create API key** (começa com `gsk_...`)
3. No Dashboard → Configurações → Transcrição de Áudio → card Groq
4. Cole a chave no campo → clique 👁 para confirmar o valor → **Salvar chave**
5. Após salvo, clique em **Usar este provedor**

**Nota:** o botão 👁 mostra/oculta a chave digitada. Clique novamente para ocultar (🙈).

### Base de Conhecimento (RAG)
Documentos que a IA usa como contexto durante as análises.
- Adicionar: título + tipo + texto → **Adicionar à base**
- Exportar sessão: converte transcrições de reuniões em documentos da base
- Excluir: botão 🗑 em cada documento

---

## TRANSCRIÇÃO DE ÁUDIO — FLUXO TÉCNICO

```
Microfone (getUserMedia)
      ↓
content.js — grava chunks de ~15s em WebM
      ↓
chrome.runtime.sendMessage({ tipo: 'whisperChunk' })
      ↓
background.js — POST /audio-transcricao (base64 + meeting_id)
      ↓
api/main.py — decodifica → salva temp → chama SDK Whisper ou Groq
      ↓
Texto retornado → salvo em transcricao_bruta + exibido na sidebar
```

---

## RECUPERAÇÃO DE SENHA

1. Acesse https://api.saleia.com.br/login
2. Clique em **Esqueci minha senha**
3. Digite o e-mail cadastrado → **Enviar**
4. Acesse o link recebido no e-mail (válido por 1 hora)
5. Digite a nova senha → **Redefinir**

---

## VARIÁVEIS DE AMBIENTE (.env na VPS)

```env
# IA
DEEPSEEK_API_KEY=...
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GEMINI_API_KEY=...
PROVEDOR_PREFERIDO=deepseek

# Transcrição de áudio
GROQ_API_KEY=gsk_...
TRANSCRICAO_PROVEDOR=whisper   # ou groq

# Auth
JWT_SECRET=...

# Banco de dados
DB_HOST=177.104.186.227
DB_NAME=fast5342_AV3D
DB_USER=...
DB_PASS=...

# E-mail (recuperação de senha)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASS=...
EMAIL_FROM=noreply@saleia.com.br
APP_BASE_URL=https://api.saleia.com.br
```

---

## SOLUÇÃO DE PROBLEMAS

**"Backend offline" na sidebar:**
- Verifique https://api.saleia.com.br/health
- Se offline: `ssh root@204.168.180.25 "systemctl restart saleia"`

**Extensão não captura legendas:**
- As legendas devem estar ativas no Meet (botão CC ou Shift+C)
- A sidebar exibe "Ative as legendas no Meet"

**Erro de transcrição na sidebar (⚠️):**
- `401 Invalid API Key` → chave Groq inválida; configure uma chave válida em console.groq.com
- `OPENAI_API_KEY não configurada` → configure a chave OpenAI no Dashboard
- Para voltar ao Whisper imediatamente: Dashboard → Transcrição de Áudio → Whisper → Usar este provedor

**Sidebar não aparece:**
- Recarregue a página do Google Meet (F5)
- Verifique se a extensão está ativa em `chrome://extensions`
- Recarregue a extensão (botão 🔄) após qualquer atualização

**Chave Groq não salva:**
- Use o botão 👁 para confirmar que a chave foi digitada corretamente
- Chaves Groq começam com `gsk_` e têm ~54 caracteres
- Verifique o feedback inline abaixo do botão (✅ ou ❌ com descrição do erro)

---

## DEPLOY (apenas para administradores)

```powershell
# Enviar arquivo alterado para VPS:
scp -i "C:\Users\phpos\.ssh\saleia_vps" -o StrictHostKeyChecking=no `
  "C:\Users\phpos\OneDrive\SALE-IA\SALEIA\api\main.py" `
  root@204.168.180.25:/opt/saleia/api/main.py

# Reiniciar o serviço:
ssh -i "C:\Users\phpos\.ssh\saleia_vps" root@204.168.180.25 "systemctl restart saleia"

# Verificar saúde:
curl https://api.saleia.com.br/health
```

Nunca sobrescrever em deploy: `.env`, `venv/`, `data/`, `logs/`
