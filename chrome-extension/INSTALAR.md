# COMO INSTALAR A EXTENSÃO SALEIA

## PRÉ-REQUISITOS
- Google Chrome instalado
- Backend SALEIA rodando (veja instruções abaixo)

---

## INSTALAÇÃO DA EXTENSÃO

1. Abra o Chrome e acesse: `chrome://extensions`
2. Ative o **"Modo do desenvolvedor"** (canto superior direito)
3. Clique em **"Carregar sem compactação"**
4. Selecione a pasta: `SALEIA/chrome-extension`
5. A extensão aparece na barra do Chrome com o ícone 🤖

---

## INICIAR O BACKEND SALEIA

```bash
# Na pasta raiz do projeto SALEIA:
cd SALEIA
pip install -r api/requirements.txt
uvicorn api.main:app --reload --port 8000
```

O backend estará disponível em: `http://localhost:8000`

---

## COMO USAR

1. **Garanta que o backend SALEIA está rodando** (ver acima)
2. **Abra qualquer reunião no Google Meet**
3. **Ative as legendas no Meet:**
   - Clique no botão **"CC"** (Closed Captions) na barra inferior do Meet
   - Ou pressione `Shift+C` dentro do Meet
4. **A sidebar SALEIA aparece automaticamente** no lado direito da tela
5. Aguarde a primeira análise (60 segundos após o início)
6. **Venda! O resto é com a IA.** 🚀

---

## CONFIGURAR URL DO BACKEND

- Clique no ícone 🤖 na barra do Chrome
- Altere a URL se seu servidor estiver em outro endereço
- Padrão: `http://localhost:8000`
- Clique em **"Salvar URL"**

---

## O QUE A SIDEBAR MOSTRA

| Seção | O que significa |
|---|---|
| 🎯 **Perfil DISC** | Tipo de personalidade do cliente (D/I/S/C) + nível de confiança |
| 💬 **Próxima Fala** | Sugestão do que dizer agora para avançar a venda |
| 💰 **Sinal Financeiro** | Indícios de capacidade de investimento detectados na conversa |
| 📦 **Produto Indicado** | Qual produto recomendar e por quê |
| ⚡ **Oportunidade** | Oportunidades que podem estar sendo perdidas |
| 🛡️ **Objeções** | Objeções prováveis + respostas sugeridas |
| ⚠️ **Alerta Urgente** | Situação crítica que exige ação imediata |

---

## SOLUÇÃO DE PROBLEMAS

**"Backend offline"** aparece na sidebar:
- Verifique se o backend está rodando: `uvicorn api.main:app --reload`
- Verifique a URL configurada no popup da extensão

**Não captura legendas:**
- Certifique-se de que as legendas estão ativas no Meet (botão "CC")
- A sidebar exibirá: _"⚠️ Ative as legendas no Meet"_

**A sidebar não aparece:**
- Recarregue a página do Google Meet (F5)
- Verifique se a extensão está ativa em `chrome://extensions`

---

## INTEGRAÇÃO COM TACTIQ (opcional)

Para envio automático de transcrição completa ao final da reunião:

1. Instale o [Tactiq](https://tactiq.io) no Chrome
2. Após a reunião, o Tactiq pode enviar a transcrição via Webhook
3. Configure o Webhook no Tactiq: `http://seu-servidor:8000/webhook/tactiq`
4. O SALEIA processará automaticamente e gerará a recapitulação completa

---

*SALEIA — Sistema de Automação de Leads, Engajamento e Inteligência Artificial em Atendimento*
