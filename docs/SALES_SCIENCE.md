# SALEIA — Sales Science

> Seção 35 do "PROMPT MESTRE — SALE-IA V2" (Tarefa D9). Como o SALEIA
> tira conclusões estatísticas de dados de venda, em **V.1.4.164**
> (05/10/2026).

## 1. Regras inegociáveis

1. **Associação, nunca causa.** Toda afirmação sai de um template fixo
   (`win_loss_rules.TEMPLATE_AFIRMACAO_ASSOCIACAO`): "X está associado a
   uma taxa de conversão de Y% (n=Z)". Teste dedicado:
   `tests/test_win_loss_rules.py::GuardaContraCausalidadeTest`.
2. **Amostra mínima.** Abaixo de `AMOSTRA_MINIMA_PADRAO = 30`
   oportunidades, nenhuma associação é afirmada: sai só
   `TEMPLATE_AMOSTRA_INSUFICIENTE`.
3. **Incerteza explícita.** Taxas vêm com intervalo de confiança de
   **Wilson** (90/95/99%), não com ponto solto.
4. **Outliers isolados.** Variáveis numéricas (ticket, ciclo) usam IQR
   (Q1 − 1,5·IQR, Q3 + 1,5·IQR) para não distorcer média/mediana.
5. **Paradoxo de Simpson checado** (`detectar_simpsons_paradox`): uma
   associação que inverte dentro dos segmentos é sinalizada, não afirmada.
6. **Zero dependência estatística externa.** Tudo em Python puro (sem
   numpy/scipy), para ser auditável e testável.

## 2. Módulos

Todos são funções puras em `agent/` (sem IA, sem banco):

| Módulo | Fase | O que faz |
|---|---|---|
| `outcome_rules` | 8.1 | valida desfecho (won/lost/abandoned, valor, ciclo, concorrente) |
| `win_loss_rules` | 8.2 | taxa de conversão, Wilson, IQR, comparação por variável, Simpson |
| `data_warehouse_rules` | 9.1 | dataset analítico mínimo |
| `seasonality_rules` / `contextual_seasonality_rules` | 9.2/9.3 | sazonalidade temporal e por contexto |
| `recommendation_usage_rules` | 10.2 | estado de uso da recomendação (USED ≥ 0,55, PARTIAL ≥ 0,35 de similaridade) |
| `recommendation_effectiveness_rules` + `recommendation_outcome_rules` | 10.3/B2 | recomendação → uso → avanço de estágio → resultado |
| `conversation_metrics_rules` / `seller_scorecard_rules` | 11 | métricas de conversa e scorecard do vendedor |
| `seller_benchmark_rules` | 12.1 | benchmark top/median/low com variáveis de controle (segmento, origem, ticket, produto) |
| `pattern_discovery_rules` | 12.2 | padrão top × control |
| `objection_trend_analyzer` / `conversion_driver_analyzer` | 13 | tendência de objeções e drivers de conversão |
| `sales_science_engine` | 13 | consolida os submódulos num contrato único (não recalcula nada) |
| `experiment_engine_rules` | 14 | desenho de experimento com checagens de segurança |
| `seller_dna_rules` | 15 | estilo do vendedor; mín. 10 reuniões; bloqueia alegação de eficácia |
| `historical_pattern_rules` | Bloco 2 | leva o insight de Win/Loss do estágio atual ao motor de raciocínio |

## 3. Como o insight chega ao vendedor

Só por `historical_patterns` no SalesReasoningEngine, filtrado pelo
estágio da oportunidade vinculada, e sempre como associação. O
`seller_context` (SellerDNA) adapta só a **forma** da recomendação
(estilo), nunca é usado como prova de que uma estratégia funciona.

## 4. Estado dos dados (05/10/2026)

- Oportunidades e clientes passaram a nascer automaticamente da
  recapitulação na V.1.4.144 (B7); antes disso havia **0 oportunidades
  em produção**. O volume ainda é pequeno: a maioria das análises
  devolve "amostra insuficiente", que é o comportamento correto.
- `recommendation_quality`: limiares de uso (0,55/0,35) **nunca foram
  calibrados** com rótulo humano (Tarefa C8). Até lá não serve como
  critério da Fase 25.
- Seller Benchmark depende de `seller_tier` real (Tarefa B5), ainda sem
  amostra.

## 5. Medições de qualidade da IA (não são Sales Science)

Golden Sales Dataset, benchmark de transcrição e qualidade de
recomendação estão em [TEST_STRATEGY.md](TEST_STRATEGY.md).
