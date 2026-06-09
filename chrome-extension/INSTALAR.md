# COMO INSTALAR A EXTENSÃO SALEIA — V.1.4.2

## PRÉ-REQUISITOS

- Google Chrome instalado
- Conta SALEIA cadastrada (crie em https://api.saleia.app.br/login)
- Backend em produção: https://api.saleia.app.br (já configurado)

---

## INSTALAÇÃO

1. Abra `chrome://extensions` no Chrome
2. Ative o **Modo do desenvolvedor** (canto superior direito)
3. Clique em **Carregar sem compactação**
4. Selecione a pasta: `SALEIA/chrome-extension`
5. A extensão aparece na barra do Chrome

**Após qualquer atualização dos arquivos da extensão**, volte em `chrome://extensions` e clique no botão **🔄 recarregar** na extensão SALEIA para aplicar as mudanças.

---

## COMO USAR

### 1. Abrir uma reunião no Google Meet

### 2. Ativar as legendas
- Clique em **CC** na barra inferior do Meet
- Ou pressione `Shift+C`

### 3. Fazer login
- A sidebar SALEIA aparece no lado direito
- Insira seu e-mail e senha quando solicitado

### 4. Iniciar captura de áudio
- Clique em **Iniciar captura de áudio** na sidebar
- O status muda para "gravando..." — o áudio é enviado em chunks de ~15s
- A transcrição aparece automaticamente no histórico da reunião

### 5. Acompanhar o coach
- A cada análise, a sidebar atualiza com sugestões em tempo real
- O contador "Próxima análise em Xs" mostra quando a próxima chamada de IA ocorre

---

## SIDEBAR — O QUE APARECE

| Elemento | Descrição |
|---|---|
| Status de áudio | Indica se a captura está ativa, com erro ou aguardando |
| Coach IA | Sugestões de fala, alertas e perfil DISC do cliente |
| Recapitulação | Resumo gerado automaticamente por deixa verbal |
| Botão Cenário | Abre a página de condução/apresentação da reunião |

---

## SOLUÇÃO DE PROBLEMAS

**"Backend offline":**
- Verifique https://api.saleia.app.br/health
- Se retornar 502, aguarde 5-10 segundos e tente novamente

**Sidebar não aparece:**
- Recarregue o Google Meet (F5)
- Verifique em `chrome://extensions` se a extensão está ativa

**Não captura legendas:**
- As legendas CC devem estar ativas no Meet
- A sidebar exibe aviso se não estiver detectando texto

**Erro de transcrição ⚠️:**
- `401 Invalid API Key` → chave Groq inválida no servidor
- `OPENAI_API_KEY não configurada` → configure no Dashboard
- Entre em contato com o administrador para corrigir as chaves

**Extensão desatualizada após deploy:**
- Acesse `chrome://extensions` → 🔄 recarregar na extensão SALEIA
