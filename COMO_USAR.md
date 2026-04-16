# COMO USAR O SALEIA

## 🚀 INÍCIO RÁPIDO

### 1. Instalar dependências do backend
```bash
cd SALEIA
pip install -r api/requirements.txt
```

### 2. Configurar chave da OpenAI
```bash
# Linux/Mac:
export OPENAI_API_KEY="sua-chave-aqui"

# Windows:
set OPENAI_API_KEY=sua-chave-aqui
```

### 3. Iniciar o backend
```bash
uvicorn api.main:app --reload --port 8000
```

O backend estará disponível em: http://localhost:8000

### 4. Instalar a extensão Chrome
Veja as instruções detalhadas em: `chrome-extension/INSTALAR.md`

---

## 📡 ENDPOINTS DA API

| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/health` | Verificação de saúde |
| POST | `/tempo-real` | Análise em tempo real (chamado pela extensão) |
| POST | `/webhook/tactiq` | Recebe transcrição do Tactiq |
| POST | `/diagnostico-financeiro` | Diagnóstico financeiro do cliente |
| POST | `/perfil-disc` | Identifica perfil DISC |
| POST | `/recapitulacao-completa` | Recapitulação pós-reunião |
| GET | `/relatorio` | Último relatório em HTML |

---

## 🔄 FLUXO AUTOMATIZADO

```
REUNIÃO NO MEET
      ↓
Extensão captura legendas
      ↓
A cada 60s → POST /tempo-real
      ↓
GPT-4o analisa → sidebar atualiza
      ↓
FIM DA REUNIÃO
      ↓
Tactiq webhook → POST /webhook/tactiq
      ↓
Recapitulação completa gerada
      ↓
Disponível em GET /relatorio
```

---

## 📊 ESTRUTURA DE RESPOSTA — /tempo-real

```json
{
  "alerta_urgente": "texto ou null",
  "perfil_disc": {
    "tipo": "D|I|S|C",
    "confianca": "alta|média|baixa",
    "evidencia": "trecho da conversa",
    "acao_sugerida": "o que fazer agora"
  },
  "proxima_acao": "próxima fala sugerida",
  "sinal_financeiro": "sinal identificado ou null",
  "produto_indicado": {
    "nome": "Produto Base|Intermediário|Completo",
    "valor": "valor em R$",
    "justificativa": "por que este produto"
  },
  "oportunidade_perdida": "texto ou null",
  "objecoes": [{"objecao": "...", "resposta": "..."}],
  "historico_resumido": "resumo dos últimos minutos"
}
```
