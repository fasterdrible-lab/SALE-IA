# Aprendizado com as reuniões do Paulo (vendedor de referência)

> Iniciado em 17/10/2026. Estado em 18/10/2026: Etapa 1 concluída, Etapa 2
> em piloto (10 reuniões, v4). Scripts em `scripts/aprendizado_paulo/`.
> **Os dados NÃO ficam no repositório** (ver Privacidade).

## Objetivo

O Paulo é o vendedor consolidado da empresa (muitas vendas). A ideia é a
SALEIA aprender **o que ele faz quando vende** — como conduz o diagnóstico,
trata objeções, apresenta preço e fecha — e usar isso como referência:

- nas sugestões ao vivo (trechos reais do Paulo para a situação atual);
- como referência do Seller Coaching (comparar outros vendedores com ele);
- como gabarito real para medir a qualidade das recomendações (C4), o que
  destrava o Piloto (C3 → C6).

## Fontes pesquisadas (o caminho foi escolhido com base nelas)

| Tema | Fonte | O que diz |
|---|---|---|
| Comparar ganhos × perdidos | [Gong Labs — talk-to-listen](https://www.gong.io/resources/labs/talk-to-listen-conversion-ratio/) | 326 mil ligações ≥ 10 min: vendedor fala 57% nas ganhas × 62% nas perdidas; 15-16 perguntas × ~20. As diferenças aparecem **comparando ganhos com perdidos** |
| Viés de sobrevivência | [HubSpot](https://consultevo.com/hubspot-survivorship-bias-guide/) | Copiar o roteiro do vendedor top olhando só vendas fechadas leva a conclusões erradas |
| Extração + busca, não treino | [Anthropic — Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) | Acima de ~200 mil tokens a base precisa de busca; busca contextual reduz falhas em 49% (67% com reordenação) |
| Processamento em lote | [Anthropic — Batch processing](https://platform.claude.com/docs/en/build-with-claude/batch-processing) | 50% mais barato, até 100 mil pedidos, maioria termina em < 1 h |
| Preço do DeepSeek | [DeepSeek — Pricing](https://api-docs.deepseek.com/quick_start/pricing) | `deepseek-v4-pro` e `deepseek-flash`; metade do preço fora do pico (pico: 01-04 e 06-10 UTC, dias úteis) |
| LGPD / anonimização | [Mattos Filho sobre a consulta da ANPD](https://www.mattosfilho.com.br/unico/anonimizacao-pseudonimizacao-direitos-titulares/) | Anonimizar já é tratamento de dados: exige base legal e finalidade compatível |

## Dados recebidos

3 zips baixados do Google Drive em 17/10 (`drive-download-20261017T*.zip`,
pasta Downloads do usuário). Total real: **1.178 documentos** (.docx) + 70
chats .txt (quase vazios, não usados). Período: mai/2025 a jul/2026.

| | Quantidade |
|---|---|
| Com transcrição completa (falas com o nome de quem fala) | **985** |
| ↳ formato "Anotações do Gemini" (abas Observações + Transcrição) | 847 |
| ↳ formato antigo "… - Transcript.docx" (só transcrição) | 138 |
| Só com o resumo do Gemini | 112 |
| Vazios ("o resumo não foi gerado") | 79 |
| Clientes distintos (reuniões agrupadas por participante) | 889 (176 com 2+ reuniões) |

Pegadinhas de leitura já tratadas (`etapa1_paulo.py`):
- falas separadas só por quebra de linha interna do Word (`<w:br/>`) —
  sem isso, falas do cliente e do Paulo saíam grudadas e o % de fala
  ficava errado;
- "Apresentação de Paulo Henrique…" = o Paulo falando com a tela
  compartilhada;
- formato antigo "Transcript.docx" (título "Transcrição" sem ícone, data
  com hífen);
- o tamanho grande dos .docx (600-950 KB) são fontes embutidas, não texto.

**Pode haver documentos no Drive fora do download**: a reunião do print
do usuário (doc com abas Observações + Transcrição) não está nos zips.
Para trazer tudo: Google Takeout (Drive → DOCX) ou conector do Google
Drive no claude.ai (precisa ser autorizado pelo usuário).

## Privacidade

- Tudo fica em **`C:\SALEIA_dados\paulo\`**, fora do OneDrive e de
  qualquer repositório git. Nada com nome de cliente vai para o GitHub.
- Cada pessoa vira um código (`PESSOA_0123`; Paulo = `VENDEDOR_REF` /
  `VENDEDOR`) em `mapa_pseudonimos.csv`. Os códigos são estáveis entre
  execuções (o mapa existente é reaproveitado).
- Antes de qualquer envio à IA: troca de nomes dos participantes (completo
  e cada parte), primeiros nomes conhecidos de outros clientes, e-mail,
  telefone, CPF e CNPJ.
- **Risco residual**: nomes citados na conversa que não são de nenhum
  participante (ex.: cônjuge) podem passar sem troca.
- Os casos de teste da auditoria (têm citações de clientes) ficam em
  `C:\SALEIA_dados\paulo\casos_auditoria.json`, não no repositório.
- Provedor escolhido pelo usuário: **DeepSeek** (mesma conta da produção).

## Etapa 1 — leitura e métricas (sem IA, sem custo)

`etapa1_paulo.py` → `reunioes.jsonl` (texto), `reunioes_metricas.csv`,
`clientes_jornada.csv`, `mapa_pseudonimos.csv`, `resumo_etapa1.json`.

Medianas (985 reuniões; % de fala por **palavras** — a transcrição do
Gemini não tem o tempo de cada fala):

| | Geral | Diagnóstico | Consultoria gratuita |
|---|---|---|---|
| Duração | 83,5 min | 90,7 min | 82,7 min |
| Paulo fala | 62,5% | 62,1% | 60,2% |
| Maior trecho seguido do Paulo (estimado a 150 palavras/min) | 2,4 min | 2,8 min | 2,3 min |
| Perguntas do Paulo (≥ 3 palavras, sem confirmações) | 85 (25% abertas) | 95 | 87 |
| Confirmações ("né?", "concorda comigo?") | 63 | 64 | 62 |
| Perguntas do cliente | 19 | 20 | 20 |

Resultado **provisório** (resumo do Gemini diz que fechou; não confiável):
clientes que "fecharam" × não — fala 63,9% × 61,9%, perguntas do cliente
24 × 17, duração 90 × 80 min. Diferença pequena nas métricas estruturais:
o diferencial do Paulo parece estar **no que ele diz**, não em quanto fala.
Parte das 85 perguntas ainda é retórica (só a IA separa bem).

## Etapa 2 — extração com IA (piloto)

`etapa2_preparar.py` escolhe 50 reuniões (metade de clientes que "fecharam"
pelo resumo, metade não; 30-120 min) e pseudonimiza. `etapa2_extrair.py`
extrai, por reunião: tipo, resultado, situação/dores/objetivos do cliente,
objeções (com resposta do Paulo, técnica, reação e desfecho), perguntas de
descoberta (SPIN), preço, fechamento e próximo passo.

**Regras que valem em todas as versões**
- Toda informação vem com **citação literal**; o validador confere cada
  citação contra a transcrição e **descarta** o que não achar.
- Campos de interpretação ("o que o cliente quis dizer", "intenção do
  vendedor", "motivo") ficam separados da citação.
- A planilha de revisão traz o **trecho real da conversa** em volta de
  cada citação (3 falas antes e depois, centrado na citação) — sai da
  transcrição, não da IA.

### Modelo: Pro × Flash (mesmas 10 reuniões, v1)

| | deepseek-v4-pro | deepseek-flash |
|---|---|---|
| Custo por reunião | US$ 0,044 | **US$ 0,012** |
| Citações descartadas (não batiam com o texto) | 8,5% | **1,5%** |
| Observação | modelo de raciocínio (~12 mil tokens "pensando"); com limite de 8 mil a resposta vinha cortada | mais cauteloso nos desfechos |

Escolhido: **Flash** para o volume. A v4 custa ~US$ 0,017 por reunião
(escreve mais por item) → ~US$ 17 para as 985.

### Versões

| Versão | O que mudou | Por quê |
|---|---|---|
| v1 | Extração com citação | — |
| v2 | Contexto, "o que quis dizer", intenção do vendedor, trecho real da conversa | Usuário: frases soltas não dão o sentido |
| v3 | "Superada" só com prova; "retorno sem data"; resposta do cliente ≤ 4 falas após a pergunta; objeção ≥ 6 palavras; trecho centrado | Auditoria (abaixo) |
| v4 | Plano T1–T6 da auditoria (abaixo) | Auditoria |

### Auditoria externa (17/10)

Relatório `SALEIA_Relatorio_Detalhado_Auditoria_67_Registros.docx`
(Downloads do usuário) sobre a amostra de 67 itens da v2. Achados:
"superada" usado com folga, "reunião marcada" sem prova de aceite,
respostas que não respondem à pergunta, citação curta/mal reconhecida,
trecho de contexto descentrado. Plano proposto e o que foi feito:

| Item | O que pede | Feito na v4 |
|---|---|---|
| T1 Rastreio | ID, citação, contexto, falante, motivo | `item_id` + `motivo_da_ia` em todo item |
| T2 Objeções | Nada de "superada" sem reação que sustente | Prova obrigatória = fala do **cliente**, **depois** da objeção; senão vira "indefinido" |
| T3 Pergunta × resposta | Comparar dimensão (atual/futura, receita/lucro) | `dimensao` + `resposta_atende` (sim/parcial/não/sem resposta) |
| T4 Resultado | Separar vai pensar, promete retorno, reunião proposta/confirmada, contrato pendente, pagamento confirmado | 8 status; "confirmada" exige fala de aceite do cliente |
| T5 Áudio | Comparar com o áudio original | Pendente (há gravações no Drive) |
| T6 Regressão | 67 casos versionados | `regressao_auditoria.py`, 19 casos dos achados |

Resultado no teste da auditoria: **v3 6/19 → v4 16/19, 0 falhas**, 3 não
extraídos. Dois casos em que a v4 discorda da auditoria com prova: L19
(o cliente aceita "18 mil em 12 vezes" 21 falas depois — a auditoria só
via o trecho curto) e L67 (o próprio cliente propõe 10h e o Paulo aceita).

Primeiro padrão observado: em 7 das 10 reuniões o Paulo não termina sem
um horário combinado ("me dá sua palavra", "vou colocar 5 horas").
Nenhuma das 10 fechou **durante** a reunião (pagamento vem depois).

## Custos

Piloto inteiro (v1-v4 + diagnóstico): ~US$ 1,30. Saldo DeepSeek em 18/10:
US$ 3,16 (crédito de compensação; mesma conta da produção — alerta abaixo
de US$ 2).

## Pendências (em ordem)

1. **Lista de quem comprou** (nome + se comprou + data; telefone/e-mail
   ajuda) — o usuário vai pedir ao responsável. Sem ela não dá para
   comparar o que o Paulo faz quando vende × quando não vende.
2. **Revisão humana** da amostra `piloto/REVISAR_amostra_v4.csv` (coluna
   "CORRETO?" S/N/parcial) — critério para rodar todas: ≥ 90%.
3. **Recarregar o DeepSeek** (US$ 15-20) antes de rodar as 985.
4. **Documentos fora do download** — Takeout ou conector do Drive.
5. Depois: rodar as 985 (Flash), cruzar com a lista de compradores,
   achar os padrões que distinguem vendas, transformar em itens da
   Biblioteca "pendentes" para aprovação, usar na sugestão ao vivo e
   como gabarito da C4.

## Como rodar

```
# Etapa 1 (local, sem IA)
python -I scripts/aprendizado_paulo/etapa1_paulo.py C:\SALEIA_dados\paulo <zip1> <zip2> ...
# Etapa 2
python -I scripts/aprendizado_paulo/etapa2_preparar.py 50
python -I scripts/aprendizado_paulo/etapa2_extrair.py 10 deepseek-flash
python -I scripts/aprendizado_paulo/regressao_auditoria.py
```

Os scripts usam caminhos fixos em `C:\SALEIA_dados\paulo\` (dados) e o
`.env` do SALEIA (chave do DeepSeek). As cópias de trabalho ficam em
`C:\SALEIA_dados\paulo\scripts\`.
