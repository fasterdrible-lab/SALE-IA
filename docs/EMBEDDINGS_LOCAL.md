# Embeddings locais com Ollama

O SALEIA usa embeddings (vetores numéricos) para dois recursos:

- **RAG** (base de conhecimento) — encontra transcrições antigas parecidas com a reunião atual.
- **Sales Memory** — encontra aprendizados comerciais (objeções, dores, sinais de compra) de reuniões anteriores.

Por padrão, o SALEIA gera esses vetores **localmente, na sua própria máquina**, usando o [Ollama](https://ollama.com), sem enviar nenhum texto para a OpenAI ou qualquer outro serviço externo. A OpenAI continua disponível como alternativa, se preferir.

## 1. Instalar o Ollama

**Windows:**
1. Baixe o instalador em https://ollama.com/download/windows
2. Execute o instalador (não precisa de configuração adicional)
3. O Ollama fica rodando em segundo plano automaticamente, servindo em `http://localhost:11434`

**Linux (VPS ou servidor):**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```
Isso instala o Ollama e já cria um serviço systemd (`ollama.service`) rodando em `http://localhost:11434`.

## 2. Baixar o modelo de embedding

```bash
ollama pull embeddinggemma
```

Em ambos os sistemas o comando é o mesmo — só precisa ter o Ollama instalado e em execução primeiro.

## 3. Testar

**Windows (PowerShell):**
```powershell
Invoke-RestMethod -Uri http://localhost:11434/api/embeddings -Method Post -Body '{"model":"embeddinggemma","prompt":"teste"}' -ContentType "application/json"
```

**Linux/macOS:**
```bash
curl http://localhost:11434/api/embeddings -d '{"model":"embeddinggemma","prompt":"teste"}'
```

Se retornar um JSON com uma lista grande de números em `"embedding"`, está funcionando.

## 4. Configurar o SALEIA

No `.env` do SALEIA:

```env
EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=embeddinggemma
```

Se o Ollama estiver rodando em outra máquina/porta, ajuste `OLLAMA_BASE_URL` de acordo (ex.: `http://192.168.1.10:11434`).

## 5. Reindexar a base existente

Se você já tinha documentos/memórias indexados com a OpenAI antes de trocar para o Ollama, os vetores antigos **não são compatíveis** com os novos (dimensões diferentes) e ficam marcados como pendentes. Regenere-os:

```bash
# Confira antes, sem gravar nada:
python -m scripts.reindex_embeddings --dry-run --table all

# Depois, gere de verdade:
python -m scripts.reindex_embeddings --table all
```

O script nunca apaga um embedding antigo antes de confirmar que o novo foi gerado com sucesso — se for interrompido, pode ser executado novamente sem risco (linhas já atualizadas são puladas).

## 6. Iniciar o SALEIA

```bash
uvicorn api.main:app --reload
```

Se o Ollama não estiver acessível quando o SALEIA iniciar, o backend **não cai** — RAG e Sales Memory ficam temporariamente indisponíveis (retornam sem contexto extra) até o Ollama voltar. Para confirmar o status, use o endpoint de diagnóstico (requer login de admin):

```
GET /admin/embeddings/status
```

## Voltar para a OpenAI

Basta trocar no `.env`:

```env
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

e reiniciar o SALEIA. Assim como na troca inversa, embeddings gerados por um modelo diferente não são comparados entre si — rode o `reindex_embeddings.py` novamente se quiser que a base toda volte a usar OpenAI.

## Observações

- `EMBEDDING_PROVIDER=ollama` é 100% local: nenhum texto de reunião, documento ou memória comercial sai da máquina onde o Ollama está rodando.
- Em produção (VPS), o Ollama precisa estar instalado **na própria VPS** — não é algo que o código do SALEIA resolve sozinho.
- `EMBEDDING_FALLBACK_PROVIDER` é opcional e vazio por padrão — só ative (ex.: `EMBEDDING_FALLBACK_PROVIDER=openai`) se você entender e aceitar que, nesse caso, textos podem ser enviados à OpenAI quando o Ollama estiver indisponível.
