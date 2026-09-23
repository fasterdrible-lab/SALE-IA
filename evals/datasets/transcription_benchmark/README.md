# Transcription Benchmark Dataset — Fase 25 do "PROMPT MESTRE — SALE-IA V2"

Dataset sintético (texto + áudio) pra alimentar o critério literal
`transcription reliability >= alvo definido` (Fase 25, item 4/5 de
"o que falta pra ligar") com número real — o motor de cálculo
(`agent/transcription_benchmark_rules.py`, V.1.4.133) já existia, mas
nunca tinha dataset real pra rodar contra os 3 provedores de
transcrição do projeto.

## Escopo desta versão (v1.0.0)

- **8 falas** sintéticas de vendas em português (variedade de
  categorias: apresentação, objeção de orçamento, objeção de
  implementação, fechamento, comparação com concorrente, adiamento de
  decisão, contexto atual, pergunta de prazo) — mistura números por
  extenso/dígitos e jargão comercial de propósito, pra ser um teste
  real de WER, não trivial.
- **Áudio gerado via gTTS** (Google Translate TTS, gratuito, sem
  chave) — **OpenAI TTS estava indisponível** no momento da geração
  (créditos esgotados, mesmo incidente de saldo já documentado desde
  15-16/09/2026 no CHANGELOG). Decisão pragmática pra não bloquear a
  medição por uma questão financeira separada.
- **Transcrito contra os 3 provedores reais do projeto**
  (`api/main.py::_transcrever_via_openai`/`_transcrever_via_groq`/
  `_transcrever_via_whisper_local`, reaproveitados sem duplicar
  lógica) — não é simulação, é o mesmo código que roda em produção.
- **Nenhum dado pessoal real** — todo texto é sintético, escrito pra
  este dataset (mesma disciplina de `golden_sales_dataset/`).

## Achado real desta rodada (23/09/2026)

O provedor `whisper` (OpenAI) falhou em **100% das 8 chamadas** com
`RateLimitError: credit_balance_exhausted` — o mesmo incidente de
saldo já documentado (15-16/09/2026). Isso produz `wer=1.0` por
construção (hipótese vazia = 100% de deleção), **não é uma medição
real de qualidade do Whisper** — é o incidente financeiro já
conhecido se manifestando aqui também. `groq` e `whisper_local`
rodaram normalmente:

| Provider | WER médio | Atinge meta (≤10%) | Latência p50 |
|---|---|---|---|
| `groq` | 7.3% | ✅ sim | ~414 ms |
| `whisper_local` | 11.0% | ❌ não (por pouco) | ~1.592 ms |
| `whisper` (OpenAI) | 100%* | — | — (0 chamadas com sucesso) |

\*Artefato do incidente de saldo, não representa a qualidade real do
Whisper via API OpenAI — remedir quando o saldo for resolvido.

Resultado completo em `docs/TRANSCRIPTION_BENCHMARK_REPORT.json`.

## Como rodar de novo

```bash
python -m scripts.transcription_benchmark_run             # dry-run, sem custo
python -m scripts.transcription_benchmark_run --real       # roda de verdade (Groq/OpenAI custam; Whisper Local é grátis)
python -m scripts.transcription_benchmark_run --real --out relatorio.json
```

Exige `GROQ_API_KEY`/`OPENAI_API_KEY` configuradas (mesmas variáveis
já usadas pelo `/audio-transcricao` real) e o modelo `faster-whisper`
já baixado (`agent/whisper_local.py`) pra rodar `whisper_local`.

## Schema de cada item (`gabarito.yaml`)

```yaml
- id: "frase_NN"
  categoria: "categoria curta (ex.: objecao_orcamento)"
  audio: "audio/frase_NN.mp3"
  texto: "transcrição-gabarito exata do que o áudio fala"
```

## Versionamento

- **v1.0.0** (23/09/2026) — versão inicial, 8 falas. Mudanças futuras
  devem incrementar a versão aqui e registrar o que mudou, nunca
  sobrescrever silenciosamente um item existente sem nota. Quando o
  saldo OpenAI for resolvido, recomenda-se regenerar `whisper` (e,
  opcionalmente, trocar o áudio pra OpenAI TTS pra maior fidelidade)
  e atualizar esta tabela.
