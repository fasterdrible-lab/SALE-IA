# Aprendizado com as reuniões do Paulo (vendedor de referência)

> Iniciado em 17/10/2026. Estado em 22/10/2026: Etapa 1 concluída, Etapa 2
> (v4, Flash) rodada em **733 de 1.049** reuniões — parou na trava de saldo;
> faltam 316 (~US$ 5,20). Scripts em `scripts/aprendizado_paulo/`.
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

**4º zip em 18/10** (`drive-download-20261018T194416Z-1-001.zip`): 74 .docx
novos (nenhum repetido), 23/07 a 16/08/2026 — Paulo fala em 66, 65 com
transcrição. Com ele: **1.250 reuniões, 1.049 com transcrição, 941
clientes** (tabela abaixo ainda com os números do 1º lote). Backup dos
resultados anteriores em `C:\SALEIA_dados\paulo\backup_20261018_pre_zip4\`.
**Nada depois de 16/08/2026** — conferir se o Paulo parou de usar as
anotações do Gemini ou se falta exportar.

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

## Sinais de venda — lista provisória de quem comprou (18/10, sem IA)

`sinais_venda.py` lê o resumo do Gemini **e** a transcrição de cada reunião
e dá um nível, sempre com a frase que prova. Substitui o
`fechou_pelo_resumo` da Etapa 1, que contava como venda frases como
"bônus para quem decidir fechar na reunião" (de 72 reuniões que ela marcava
e a regra nova não, a amostra lida não tinha nenhuma venda clara).

| Nível | O que prova | Clientes (de 941, com o 4º zip) |
|---|---|---|
| PAGOU | comprovante/pagamento confirmado ("chegou aqui… agora de forma oficial, seja bem-vindo"; "enviou o comprovante") | **158** |
| FECHOU_VERBAL | ritual de fechamento do Paulo sem prova de pagamento ("seja muito bem-vindo, que Deus abençoe esse projeto, parabéns por essa decisão") | 168 |
| COMPROMISSO | combinou pagar (entrada, link, comprovante pedido no fim) | 40 |
| VAI_PENSAR | adiou ("não vou fechar agora", conversar com a esposa/sócio, recusou o sinal) | 134 |
| NAO_FECHOU | recusa explícita | 18 |
| SEM_SINAL | nada encontrado | 423 |

O que aprendemos ao montar as regras (cada uma veio de um falso positivo
visto na amostra):
- O ritual do Paulo acontece no fim (≥ 60% da reunião). Antes disso as
  mesmas palavras são pitch ou história de outro cliente ("o [cliente]
  falou: pode mandar o Pix") — ignoradas. Os nomes dos casos de sucesso
  que o Paulo conta ficam em `C:\SALEIA_dados\paulo\casos_de_sucesso.txt`
  (fora do git).
- "Agora de forma oficial" só vira PAGOU se a fala ou as 4 anteriores têm
  dinheiro **chegando** (chegou, caiu, comprovante, aprovado, recebi).
  "Pix"/"pagamento" sozinhos aparecem na proposta.
- O Paulo **adianta** as boas-vindas antes do pagamento ("posso te adiantar
  um seja muito bem-vindo?") — coluna `antecipado` (82 reuniões). Sim
  verbal, não venda.
- Pré-fechamento condicional ("se você entender que somos a empresa ideal,
  seja bem-vindo… posso contar com o sincero sim ou não?") não conta.
- "Não vou fechar **agora**" é adiamento (VAI_PENSAR), não recusa.

Precisão **não medida**: na leitura de amostras (~20 por nível), PAGOU
saiu quase todo certo; FECHOU_VERBAL tem casos fracos (só o "posso
adiantar…?"). NAO_FECHOU é o nível menos confiável (frases hipotéticas).
A lista oficial mede de verdade.

Saídas (em `C:\SALEIA_dados\paulo\`, fora do git — têm nomes reais):
`sinais_venda_clientes.csv` (1 linha por cliente, com `nomes_reais` e a
coluna vazia `lista_oficial_comprou` para o cruzamento),
`sinais_venda_reunioes.csv`, `resumo_sinais_venda.json`.

## Quando vende × quando não vende — 1ª comparação (18/10, provisória, sem IA)

`comparar_vendeu.py`: 1ª reunião com transcrição (≥ 30 min) de cada cliente,
grupos pelos sinais acima — **vendeu** (PAGOU/FECHOU_VERBAL, 276),
**adiou/recusou** (VAI_PENSAR/NAO_FECHOU, 135), **sem sinal** (212).
(Percentuais abaixo da rodada anterior; a final difere em ≤ 1 ponto.)
Saída: `comparar_vendeu.json`.

| | vendeu | adiou/recusou | sem sinal |
|---|---|---|---|
| Chegou a apresentar a oferta (investimento/entrada/12x) | **80%** | 66% | 56% |
| Momento da oferta (% da reunião) | 66% | 68% | 68% |
| Perguntas do Paulo por hora | 61 | 62 | 61 |
| Paulo fala (% palavras) | 63% | 60% | 56% |
| *Entre as que chegaram à oferta:* parcelamento 12x sem juros | **80%** | 48% | 49% |
| … oferece bônus | **56%** | 41% | 36% |
| … pede sinal | **26%** | 15% | 13% |
| … "posso contar com o sincero sim ou não?" | **19%** | 5% | 10% |
| Cliente fala de dinheiro curto | 24% | 15% | 12% |

- **Sem diferença**: ritmo de perguntas (o "mais perguntas" das vendas era
  só reunião mais longa) e momento do preço (~2/3 da reunião sempre).
- **Diferença**: nas vendas o Paulo chega à oferta e a monta com 12x sem
  juros + bônus + sinal + pedido de sim/não sincero. Conferido que isso vem
  **antes** do sim (201 vendas com o momento do sim localizado: 12x antes
  em 68%, só depois em 13%; bônus 54% × 7%) — não é o link de pagamento.
- "Dinheiro curto" aparece **mais** nas vendas: a objeção surge quando o
  preço é discutido a sério, e o Paulo a contorna com o parcelamento.
- Cuidados: grupos pelos sinais (não pela lista oficial); associação, não
  causa — o Paulo pode oferecer 12x/bônus só quando sente o cliente pronto
  (causa invertida); "sem sinal" mistura quem pagou depois. Próximo passo
  com IA (Etapa 2 nas 1.049): o **conteúdo** de como ele monta a oferta e
  trata "dinheiro curto", que regra de texto não pega.

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

## Etapa 2 completa — 1ª rodada (21-22/10/2026)

Usuário recarregou o DeepSeek (US$ 19,99). `etapa2_preparar.py todas`
pseudonimizou as 1.049 reuniões com transcrição em
`C:\SALEIA_dados\paulo\completo\` (ids `C0001`…, por data; 0 e-mails e 0
"Pagoti" restantes). `etapa2_extrair.py todas deepseek-flash completo`:

| | |
|---|---|
| Extraídas | **733** de 1.049 (`completo/extracoes_deepseek-flash/`) |
| Custo real | **US$ 12,05** (saldo 19,99 → 7,94) ≈ US$ 0,016/reunião |
| Citações descartadas pelo validador | 7,9% (37.592 ok, 3.237 fora) — a maioria o modelo "limpando" a fala ("cara", "uhum"); poucas paráfrases reais |
| Planilha | `completo/revisao_deepseek-flash.csv`, 22.461 itens |
| Falha | C0381 (JSON quebrado na resposta 3×) — entra na próxima rodada |
| Parada | trava de saldo US$ 8 (conta da produção) |

Travas novas no extrator: para abaixo de US$ 8 de saldo e no pico do
DeepSeek (01-04 e 06-10 UTC, dias úteis); rodar de novo retoma pulando o
que já foi extraído. Log: `completo/log_lote1.txt`.

## Custos

Piloto inteiro (v1-v4 + diagnóstico): ~US$ 1,30. Etapa 2 completa, 1ª
rodada: US$ 12,05 (733 reuniões). Mesma conta da produção — alerta abaixo
de US$ 2, trava do lote em US$ 8.

## Pendências (em ordem)

> **22/10/2026**: 733 de 1.049 extraídas. Para fechar: recarregar ~US$ 6-8
> no DeepSeek e rodar de novo o mesmo comando (retoma as 316 restantes).
> Combinado em 18/10 (Etapa 2 nas 1.049, v4, Flash). Foco da análise:
> como o Paulo **monta a oferta** (12x, bônus, sinal, "sincero sim ou não")
> e como trata **"dinheiro curto"** — o que a 1ª comparação apontou e regra
> de texto não alcança. Até lá, nada a fazer nesta frente.

1. **Lista de quem comprou** (nome + se comprou + data; telefone/e-mail
   ajuda) — o usuário vai pedir ao responsável. Sem ela não dá para
   comparar o que o Paulo faz quando vende × quando não vende. Enquanto
   não chega: lista provisória por sinais (seção acima, 158 PAGOU + 168
   FECHOU_VERBAL); quando chegar, cruzar e medir o acerto dos sinais.
   Usuário fazendo levantamento completo no Drive (18/10) — rodar Etapa 1
   e `sinais_venda.py` de novo com os documentos novos.
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
# Etapa 2 em todas as reuniões (pasta completo/, retoma de onde parou)
python -I scripts/aprendizado_paulo/etapa2_preparar.py todas
python -I scripts/aprendizado_paulo/etapa2_extrair.py todas deepseek-flash completo
```

Os scripts usam caminhos fixos em `C:\SALEIA_dados\paulo\` (dados) e o
`.env` do SALEIA (chave do DeepSeek). As cópias de trabalho ficam em
`C:\SALEIA_dados\paulo\scripts\`.
