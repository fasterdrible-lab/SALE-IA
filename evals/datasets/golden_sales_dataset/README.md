# Golden Sales Dataset — Fase 20 do "PROMPT MESTRE — SALE-IA V2"

Dataset versionado de avaliação, schema literal do prompt mestre. **Diferente** do Golden Dataset do `SalesReasoningEngine` (`evals/datasets/sales_reasoning/`, Fase 7) — aquele usa `context` + campos estruturados das Fases 1-6 e é rodado de verdade via Promptfoo/`llm-rubric` contra o motor real; este é um recurso de **conteúdo puro**, ainda não conectado a nenhum runner (decisão de escopo confirmada com o usuário — ver `CLAUDE.md`, seção "Golden Sales Dataset — Fase 20").

## Escopo desta versão (v1.0.0)

- Só o dataset (10 categorias × 4 cenários = 40 cenários), schema literal do prompt mestre (`INPUT`/`EXPECTED FACTS`/`EXPECTED EVENTS`/`EXPECTED FRAMEWORK`/`ACCEPTABLE ACTIONS`/`FORBIDDEN ACTIONS`).
- **Nunca conectado a um runner/Promptfoo nesta rodada** — decisão deliberada, mesma disciplina "contrato primeiro" do resto do roadmap. Quando alguém decidir rodar isto de verdade (ex.: pra alimentar as 6 métricas da Tarefa 19.1 com dado real), vai precisar de um provider novo que traduza este schema pra chamadas reais contra o pipeline (extração de evento, classificação de objeção, `SalesReasoningEngine`) — não construído aqui.
- **Nenhum dado pessoal real** — todo cenário é sintético (nomes/empresas fictícios), mesma disciplina de `objections_fit_gap.yaml` (que também é 100% sintético, ao contrário de `objections_real.yaml`).
- 4 cenários por categoria é uma escolha desta rodada (o prompt mestre não define um número mínimo, diferente do Golden Dataset da Fase 7, que tinha "mínimo 50" explícito) — cobre o caso comum + pelo menos 1 caso de risco (`FORBIDDEN ACTIONS` realista) por categoria, sem inflar o dataset com cenários rasos só pra bater um número.

## Categorias (10, literais do prompt mestre)

| Arquivo | Categoria |
|---|---|
| `discovery.yaml` | discovery |
| `qualification.yaml` | qualification |
| `pricing.yaml` | pricing |
| `objections.yaml` | objections |
| `negotiation.yaml` | negotiation |
| `closing.yaml` | closing |
| `lost_deal.yaml` | lost deal |
| `won_deal.yaml` | won deal |
| `bad_seller_behavior.yaml` | bad seller behavior |
| `good_seller_behavior.yaml` | good seller behavior |

## Schema de cada cenário (literal do prompt mestre)

```yaml
- id: "<categoria>-NN"
  description: "resumo curto de uma linha"
  input: |
    Trecho de conversa ou narrativa sintética da situação (nunca transcrição real).
  expected_facts:
    - campo: "nome do fato esperado (ex.: main_pain, economic_buyer, ticket)"
      valor: "o que deveria ser extraído"
      evidence_quote: "a fala (dentro do input) que sustenta o fato"
  expected_events:
    - "TIPO_DE_SALES_EVENT"   # vocabulário fechado de agent/sales_event_rules.py::SALES_EVENT_TYPES
  expected_framework: "FRAMEWORK_ESPERADO_OU_NULL"  # vocabulário fechado de agent/sales_reasoning_engine.py::SALES_REASONING_FRAMEWORKS, null quando a categoria não mapeia 1:1 (ex.: won/lost deal, comportamento do vendedor)
  acceptable_actions:
    - "ação ou recomendação que seria correta"
  forbidden_actions:
    - "ação que a IA NUNCA deveria tomar/recomendar nessa situação"
```

- `expected_events` usa só os 14 tipos literais de `SALES_EVENT_TYPES` (Fase 1 / Tarefa 1.1): `PAIN_DETECTED`, `IMPACT_IDENTIFIED`, `BUYING_SIGNAL`, `OBJECTION_RAISED`, `OBJECTION_RESOLVED`, `PRICE_DISCUSSION`, `COMPETITOR_MENTIONED`, `DECISION_MAKER_IDENTIFIED`, `CHAMPION_IDENTIFIED`, `BUDGET_IDENTIFIED`, `NEXT_STEP_AGREED`, `DEAL_STALLED`, `DEAL_WON`, `DEAL_LOST`.
- `expected_framework` usa só os 9 valores de `SALES_REASONING_FRAMEWORKS` (Fase 7): `SPIN_SITUATION`, `SPIN_PROBLEM`, `SPIN_IMPLICATION`, `SPIN_NEED_PAYOFF`, `MEDDPICC_QUALIFICATION`, `OBJECTION_INVESTIGATION`, `NEGOTIATION`, `RISK_MITIGATION`, `CLOSING` — ou `null` quando o cenário é sobre resultado/comportamento, não sobre qual pergunta fazer a seguir.
- Objeções (`objections.yaml`) referenciam as 13 categorias de `agent/objection_rules.py::OBJECTION_TIPOS` (`PRICE`, `VALUE`, `BUDGET`, `TIMING`, `TRUST`, `ADOPTION`, `COMPETITOR`, `AUTHORITY`, `PRIORITY`, `IMPLEMENTATION`, `LEGAL`, `PROCUREMENT`, `SECURITY`).

## Regras de rotulagem de `expected_events` (desde v1.2.0)

`event_precision` (Fase 25) trata `expected_events` como a lista
**completa**: todo tipo previsto fora dela conta como falso positivo.
Até a v1.1.0 o campo trazia só o evento "principal" do cenário. A
partir da v1.2.0 vale:

**Gerais**

- **G1 — exaustivo**: listar todo tipo cuja definição é satisfeita por
  uma frase literal do `input`.
- **G2 — só o que está no input**: "isso acontece…" sem o problema dito
  no trecho não comprova PAIN_DETECTED.
- **G3 — por tipo**: a métrica compara tipos, não ocorrências; cada tipo
  aparece no máximo uma vez.
- **G4 — qualquer falante**, salvo quando a definição diz "o cliente".

**Por tipo** (definições de `agent/prompt_templates/sales_event_extractor.txt`)

| Tipo | Conta | Não conta |
|---|---|---|
| PAIN_DETECTED | o cliente diz o problema concreto (ex.: "vendedor esqueceu de retornar") | só a consequência ("perdemos 15 mil") sem o problema; referência vaga |
| IMPACT_IDENTIFIED | consequência ou magnitude do problema: dinheiro, tempo, conversão, frequência/volume de perdas, cliente perdido | — |
| BUYING_SIGNAL | o cliente quer comprar/seguir, inclusive condicional ("fecho se…", "topo fechar, mas…", "bora fechar, só que…") ou confirmando o plano escolhido | entusiasmo com benefício ("ia mudar tudo"); só perguntar o preço; compra já fechada (é DEAL_WON) |
| OBJECTION_RAISED | resistência do cliente com motivo numa negociação em curso: preço ("está caro"), timing, confiança, comparação com concorrente, adoção, implementação, condição de pagamento, ameaça de cancelar | hesitação sem motivo ("deixa eu pensar"); falta de tempo para a reunião; motivo de uma recusa definitiva (é DEAL_LOST) |
| OBJECTION_RESOLVED | o cliente diz explicitamente que a objeção deixou de ser problema | revelar a causa real da objeção; o vendedor reformular |
| PRICE_DISCUSSION | valor concreto, desconto, condição de pagamento, condição comercial que mexe no preço (promoção, validade, reajuste, item "sem custo"), pedido explícito de preço | "está caro" genérico; negação ("não é o preço"); juízo vago ("preço competitivo") |
| COMPETITOR_MENTIONED | concorrente ou alternativa citada, inclusive genérica ("outro fornecedor", "outra empresa") e a situação atual quando escolhida no lugar da compra | descrição do processo atual sem colocá-lo como alternativa |
| DECISION_MAKER_IDENTIFIED | dito quem decide/aprova/assina | — |
| CHAMPION_IDENTIFIED | alguém do lado do cliente que vai defender a solução internamente | indicação de terceiro externo ("tenho um parceiro…") |
| BUDGET_IDENTIFIED | orçamento/verba/faixa declarada, inclusive "não temos verba" ou "tem espaço" | — |
| NEXT_STEP_AGREED | passo concreto (reunião, envio, teste, contrato) proposto por uma parte e aceito pela outra no trecho | proposta sem resposta; confirmação de termos sem passo concreto |
| DEAL_STALLED | a negociação parou: sem resposta/contato, ou o cliente encerra adiando sem data | hesitação; objeção de timing dita numa conversa em curso |
| DEAL_WON | o cliente declara a compra fechada ("fechado", "contrato assinado") | decisão de seguir para o contrato (é BUYING_SIGNAL) |
| DEAL_LOST | recusa definitiva: escolheu outro, desistiu, decidiu manter como está, sem verba como resposta final | ameaça condicional ("se não…, vou cancelar") |

## Versionamento

- **v1.0.0** (18/09/2026) — versão inicial, 40 cenários (10 categorias × 4). Mudanças futuras devem incrementar a versão aqui e registrar o que mudou (cenário adicionado/removido/reescrito), nunca sobrescrever silenciosamente um cenário existente sem nota.
- **v1.1.0** (02/10/2026, Tarefa D3) — `objections-04` reescrito: o fato `objection_spoken` passava a citação da causa raiz ("tenho medo da minha equipe não usar...") esperando a categoria da fala literal (PRICE). O classificador recebia a fala de adoção e respondia ADOPTION — correto — e contava como erro: era o único erro dos 75% de `objection_classification`. Agora são 2 fatos: `objection_spoken` = PRICE com "Está caro pra gente agora." e `root_cause_hypothesis` = ADOPTION com a fala de adoção. Nenhum outro cenário mudou.
- **v1.2.0** (05/10/2026, Tarefa A7b) — `expected_events` passa a ser exaustivo, seguindo as regras de rotulagem acima (escritas antes de mudar os rótulos e aplicadas aos 40 cenários). 22 cenários mudaram. A v1.1.0 listava só o evento "principal", e `event_precision` contava como falso positivo todo evento real fora dele (ex.: PRICE_DISCUSSION em "Fechamos o plano completo por R$ 4.500/mês"). Removidos 2 OBJECTION_RESOLVED errados (`objections-04`, `pricing-04`: o cliente só revela a causa real, nada é resolvido), 2 NEXT_STEP_AGREED sem aceite da outra parte (`closing-01`, `good-seller-04`) e 2 BUYING_SIGNAL que não batem com a definição (`discovery-04` "ia mudar tudo", `won-deal-04` compra já fechada). Lista completa no CHANGELOG (V.1.4.165). Os rótulos merecem revisão humana.
- Conjunto à parte de classificação de objeções (30 casos, 17 reais anonimizados + 13 sintéticos): `evals/datasets/objection_classification/`.
