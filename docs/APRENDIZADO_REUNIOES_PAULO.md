# Aprendizado com as reuniões do Paulo (vendedor de referência)

> Iniciado em 17/10/2026. Estado em 23/10/2026: Etapa 1 concluída, **Etapa 2
> (v4, Flash) concluída nas 1.049 reuniões** (3 rodadas, ~US$ 17). Próximo:
> achar os padrões das vendas. Scripts em `scripts/aprendizado_paulo/`.
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

### 2ª e 3ª rodadas (22-23/10/2026) — Etapa 2 concluída

| Rodada | Trava de saldo | Reuniões | Log |
|---|---|---|---|
| 2ª (22/10) | US$ 3 | 733 → 1.020 (parou com saldo US$ 2,90) | `completo/log_lote2.txt` |
| 3ª (23/10, 12:35 UTC, após recarga) | US$ 5 | 1.020 → **1.049** (C0381 incluída; 0 falhas) | `completo/log_lote3.txt` |

Total das 1.049: 51.941 citações verificadas, 5.763 descartadas (10,0%);
custo estimado fora de pico ~US$ 16,81 (3ª rodada: saldo 7,68 → 7,19).
Planilha `completo/revisao_deepseek-flash.csv` com **31.251 itens**.

## Padrões das vendas sobre a Etapa 2 (23/10/2026, provisório, sem IA)

`padroes_vendeu.py` lê as 1.049 extrações e cruza com os grupos de
`sinais_venda.py` (não a lista oficial). Saídas (fora do git):
`padroes_vendeu.json` e `padroes_vendeu_exemplos.csv` (741 objeções de
dinheiro superadas/parciais com a resposta do Paulo, superadas primeiro).

**Por cliente** (1ª reunião extraída ≥ 30 min; vendeu 321, adiou/recusou
142, sem sinal 263):

| | vendeu | adiou/recusou | sem sinal |
|---|---|---|---|
| Apresentou o preço | **77%** | 52% | 47% |
| *Se apresentou:* 12x / sem juros | **78%** | 62% | 59% |
| … entrada | **68%** | 53% | 49% |
| … Pix / cartão recorrente / restante em 30 dias | **39 / 34 / 35%** | 32 / 28 / 27% | 28 / 25 / 26% |
| … bônus / sinal / desconto | 14 / 12 / 21% | 14 / 12 / 20% | 11 / 5 / 16% |
| … garantia | 22% | **30%** | 21% |
| Teve objeção de dinheiro | 78% | 66% | 70% |
| ↳ superada / não superada | **20% / 8%** | 4% / 25% | 4% / 17% |
| Fechamento: pedido direto / urgência | 79 / 61% | 62 / 52% | 54 / 36% |
| Dores, objeções, perguntas de descoberta (medianas) | 5 / 3 / 10 | 5 / 3 / 10 | 5 / 3 / 10 |
| Resposta do cliente atende à pergunta | 65% | 65% | 65% |

**Objeções de dinheiro em todas as reuniões — técnica × desfecho**
(desfecho só com fala do cliente depois, validador da v4):

| Técnica do Paulo | n | Superada, entre as com reação clara |
|---|---|---|
| **condição de pagamento** | 495 | **24,7%** |
| outra | 146 | 11,7% |
| garantia | 46 | 9,1% (e a maior taxa de "não superada": 15 de 44) |
| reformular valor | 184 | 8,2% |
| prova social, comparação de custo, isolar, aprofundar, empatia | 24-55 cada | 2-8% |

**O que isso diz (associação, não causa):**
- **A descoberta não separa venda de não venda**: mesmas dores,
  perguntas e qualidade de resposta nos três grupos. A diferença está
  **na oferta**.
- **Chegar ao preço** é o maior separador (77% × ~50%).
- **"Dinheiro curto" se resolve com estrutura de pagamento, não com
  argumento.** Lendo as 136 superadas, o Paulo **ajusta a oferta à
  restrição real do cliente**: entrada que cabe no limite do cartão,
  restante no recorrente ou em 30 dias, fechar no dia em que o cartão
  vira, boleto quando a empresa só paga boleto, entrada mínima + 12x sem
  juros. Desconto aparece pouco e no fim, perto do piso.
- **Amarração antes de ceder**: "se a gente chegar nesses 18 em 12x, a
  gente starta?" e teste de capacidade antes do preço ("você consegue
  honrar R$ 1.500 por um, dois meses?").
- **Bônus e sinal não se confirmam** como diferencial: a 1ª comparação
  (regex em toda a fala do Paulo) via 56% × 41% de bônus; nas condições
  que a IA extraiu da oferta, a diferença some. Bônus provavelmente
  aparece no pitch, não como condição.
- **Garantia vem mais quando não vende** e é a resposta que menos supera
  objeção de dinheiro. Provável sinal de que a objeção era de confiança.

**Cuidados**: "superada" e "pedido direto" se misturam com o próprio
fechamento (que define o grupo "vendeu"), então não são prova de causa.
Os grupos vêm de sinais, não da lista oficial. A taxa por técnica não
depende dos grupos, mas a técnica é rótulo da IA (não revisado).

## Extrações × etapas do método (23/10/2026, provisório, sem IA)

Método da empresa (definido pelo usuário): **1. Diagnóstico** (entender o
cenário, perguntas que fazem o lead enxergar necessidade e urgência,
"fechar todas as portas" antes da solução) → **2. Apresentação** (conectar
o projeto ao que o próprio cliente trouxe) → **3. Fechamento** (amarração
antes do investimento + quebra de objeção depois: "vou pensar", "preciso
falar com outra pessoa").

`etapas_reuniao.py` marca as etapas em cada transcrição pela fala do
vendedor e localiza cada item extraído pela citação. Saídas (fora do git):
`etapas_reunioes.csv`, `etapas_amostra.txt`, `etapas_analise.json`,
`etapas_exemplos_fechamento.csv` (203 objeções não financeiras depois do
preço, superadas/parciais).

| Corte | Marcador | Cobertura |
|---|---|---|
| Fim do diagnóstico | 1ª recapitulação / "vou compartilhar a tela" depois de 15% | 898 de 1.049 (mediana 41% da reunião) — **10/10 certos na amostra** |
| Investimento | 1ª oferta com valor ou condição (12x, sem juros, "entrada de R$") | 505 (mediana 77%) |
| Fechamento antes do investimento | última amarração na reta final antes do preço ("se eu conseguir encaixar, a gente avança") | 79 |
| Combinado do "sincero sim ou não" | amarração no começo da apresentação ("no final quero contar com o sincero sim ou não") | medido à parte |

A 1ª versão errava dois cortes (corrigidos e conferidos de novo na
amostra): tomava o combinado do sim ou não por fechamento, e "o
investimento é baseado no retorno" / "10 vezes a mais" por oferta.

**Etapa 1 — Diagnóstico**
- Mistura de perguntas **igual** em venda e não venda (1ª reunião de cada
  cliente): ~50% situação, ~18% problema, **~10% implicação**, ~22%
  necessidade de solução; resposta do cliente atende em 67%. A IA guardou
  até 12 perguntas por reunião, então é amostra das perguntas.
- "Fechar as portas" (pergunta do vendedor no diagnóstico × a objeção que
  ela deveria evitar depois, 505 reuniões com diagnóstico e preço):

  | Porta | Perguntou | Objeção depois | Não perguntou | Objeção depois |
  |---|---|---|---|---|
  | Decisor (esposa, sócio, "decide sozinho?") | 102 | 29% | 403 | 18% |
  | Investimento / orçamento | 246 | 85% | 259 | 74% |
  | Urgência ("por que agora?", "o que acontece se nada mudar?") | 50 | **12%** | 455 | 20% |

  Decisor e investimento: quem perguntou teve **mais** objeção. Provável
  causa invertida — o vendedor pergunta quando o cliente já deu sinal
  (cita esposa, fala de dinheiro). A regra de texto vê se perguntou, não
  se a porta **fechou** (cliente responde "a decisão é minha"). Urgência
  vai na direção esperada, mas com só 50 reuniões. **Ainda não dá para
  afirmar** que fechar portas reduz objeção; precisa olhar a resposta do
  cliente.

**Etapa 2 — Apresentação (conexão com o diagnóstico)**
- Das dores/objetivos que o cliente disse no diagnóstico, o vendedor
  retoma depois **70%** (mediana) × **50%** do placebo (dores de outra
  reunião contra a mesma apresentação): **+20 pontos de personalização
  real**. Margem parecida nos grupos (vendeu 80 × 62,5; adiou 67 × 50;
  sem sinal 57 × 43) — o Paulo personaliza sempre; não é o que separa.

**Etapa 3 — Fechamento**
- Chegou ao investimento: vendeu **74%** × adiou 41% × sem sinal 35%.
- **Combinado do "sincero sim ou não" no começo da apresentação**, entre
  as que chegaram ao preço: vendeu **31%** × adiou 17% × sem sinal 12%.
- Amarração logo antes do preço: 16% × 21% × 13% — **não separa**.
- Objeções de risco ("e se não der resultado?") e confiança aparecem
  mais no diagnóstico e na apresentação; as de dinheiro, depois do preço.
- Depois do preço, "preciso falar com outra pessoa" (75) e "agora não /
  vou pensar" (66) **quase nunca são superadas na call**: envolver o
  decisor 0 de 31 superadas (10 não); urgência 3 de 19 (7 não). A única
  que resolve "agora não" com alguma frequência é condição de pagamento
  (3 de 9, nenhuma não superada). Risco depois do preço respondido com
  garantia: 1 de 49.

## Custos

Piloto inteiro (v1-v4 + diagnóstico): ~US$ 1,30. Etapa 2 completa, 1ª
rodada: US$ 12,05 (733 reuniões); 2ª + 3ª: ~US$ 5,50 (316 reuniões).
Mesma conta da produção — alerta abaixo de US$ 2, trava do lote em US$ 8
por padrão (`SALDO_MINIMO_USD`).

## Pendências (em ordem)

> **23/10/2026**: Etapa 2 concluída (1.049 de 1.049) e 1ª leitura dos
> padrões feita (seção acima). **Rascunho da fonte para a Biblioteca
> pronto**: `C:\SALEIA_dados\paulo\biblioteca\paulo_oferta_e_dinheiro_curto.md`
> (11 itens validados pelo usuário em 23/10 + 1 novo das etapas, o
> combinado do "sincero sim ou não", aguardando validação; cada item com
> a linha `Etapa:`; um por `##`, exemplos reais pseudonimizados — fora do
> git). Fluxo: usuário revisa → Dashboard → Biblioteca → enviar como
> `PLAYBOOK` → extrair → compilar (IA, 11 seções) → aprovar item a item
> (só `APPROVED` entra na sugestão ao vivo). Precisa de
> `KNOWLEDGE_COMPILER_ENABLED=true` na VPS.

1. **Lista de quem comprou** (nome + se comprou + data; telefone/e-mail
   ajuda) — o usuário vai pedir ao responsável. Sem ela não dá para
   comparar o que o Paulo faz quando vende × quando não vende. Enquanto
   não chega: lista provisória por sinais (seção acima, 158 PAGOU + 168
   FECHOU_VERBAL); quando chegar, cruzar e medir o acerto dos sinais.
   Usuário fazendo levantamento completo no Drive (18/10) — rodar Etapa 1
   e `sinais_venda.py` de novo com os documentos novos.
2. **Revisão humana** da amostra `piloto/REVISAR_amostra_v4.csv` (coluna
   "CORRETO?" S/N/parcial) — critério para rodar todas: ≥ 90%.
3. ~~Recarregar o DeepSeek~~ — feito (21/10 e 23/10).
4. **Documentos fora do download** — Takeout ou conector do Drive.
5. ~~Rodar todas (Flash)~~ — feito 23/10 (1.049); ~~padrões com a lista
   provisória~~ — feito 23/10. Falta: refazer com a lista oficial
   (`python -I scripts/aprendizado_paulo/padroes_vendeu.py`), transformar em itens da
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
