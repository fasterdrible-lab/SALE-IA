# SALEIA — Estratégia de Testes

> Seção 35 do "PROMPT MESTRE — SALE-IA V2" (Tarefa D9). Estado em
> **V.1.4.164** (05/10/2026).

## 1. Camadas

| Camada | Onde | Custo de IA | Quando roda |
|---|---|---|---|
| Unitários de regra | `tests/test_*_rules.py` | zero | toda mudança |
| Integração (API, banco SQLite, orquestrador com IA mockada) | `tests/test_*.py` | zero | toda mudança |
| E2E dos 10 cenários de venda (D4) | `tests/test_e2e_cenarios_venda.py` | zero (IA mockada só no provedor) | toda mudança |
| Contrato e reparo de JSON (D5) | `tests/test_contract_repair.py` | zero | toda mudança |
| Evals de prompt (Promptfoo) | `evals/promptfooconfig*.yaml` | real (DeepSeek) | CI em PR que mexe em prompt/agente/router |
| Golden Sales Dataset | `scripts/quality_monitoring_golden_run.py --real` | real (até ~234 chamadas) | sob demanda, com OK de custo |
| Diagnóstico de SalesEvent | `scripts/sales_event_diagnostico.py --real` | real (40 chamadas) | sob demanda (A7b) |
| Benchmark de transcrição | `scripts/transcription_benchmark_run.py` | real | sob demanda |
| Qualidade de recomendação | `scripts/recommendation_quality_run.py --real` | zero (embeddings locais) | sob demanda |

Hoje: **140 arquivos de teste, ~1.790 testes** (`unittest`). A suíte
completa leva ~27 min; rodar em segundo plano ou só os arquivos tocados
pela mudança.

```bash
python -m unittest discover -s tests            # suíte completa
python -m unittest tests.test_alertas -v        # um arquivo
```

## 2. Regras para escrever teste

- **Regra pura primeiro.** Lógica nova vai para `agent/*_rules.py` e é
  testada sem IA nem banco.
- **IA mockada no provedor**, não no orquestrador: o roteador real
  (guardas, reparo, fallback) entra no teste.
- **Banco**: SQLite em memória. **Cuidado**: `api/database.py` carrega o
  `.env` local, cujo `DB_HOST` aponta para o MySQL de **produção**. Teste
  que não isola o engine grava em produção. O E2E bloqueia o MySQL do
  `.env` durante a suíte; testes de Shadow/Piloto desligam os
  kill-switches de escrita.
- **Logging global**: vários arquivos chamam
  `logging.disable(logging.CRITICAL)` no import. Teste que usa
  `assertLogs` precisa salvar e restaurar `logging.root.manager.disable`
  no `setUp`/`tearDown`, senão passa isolado e falha na suíte.
- Teste de comportamento real, não de implementação: o que o vendedor
  veria, o que é gravado, o que é bloqueado.

## 3. Golden Sales Dataset

`evals/datasets/golden_sales_dataset/`: 40 cenários em 10 categorias
(descoberta, qualificação, objeções, preço, negociação, fechamento,
ganha, perdida, vendedor bom/ruim). Cada cenário traz `expected_facts`,
`expected_events`, `expected_framework`, ações aceitáveis/proibidas.
Mais 30 casos de classificação de objeção em
`evals/datasets/objection_classification/` (17 reais anonimizados).

Métricas (`agent/quality_monitoring_rules.py`): `event_precision`,
`objection_precision`, `framework_accuracy`, `hallucination_rate`,
`critical_hallucination_rate`, `evidence_coverage`. A rodada `--real`
grava o resultado em `readiness_medicoes` (painel `/admin/readiness`).

Última rodada real (03/10/2026, V.1.4.162):

| Métrica | Valor | Alvo Fase 25 |
|---|---|---|
| objection_classification | 100% | ≥ 90% |
| critical_hallucination_rate | 2,5% (1 falso positivo) | ≈ 0 |
| event_precision | 48,9% | ≥ 90% |

**Lição registrada duas vezes (D3 e A7b):** antes de mexer no prompt,
olhar o erro cenário a cenário. Parte dos erros era gabarito incompleto
ou errado, não a IA.

## 4. Mudança de prompt em produção

Seguir [evals/APPROVAL_CRITERIA.md](../evals/APPROVAL_CRITERIA.md):
rodar o eval correspondente antes e depois, não regredir schema nem
accuracy, registrar a decisão no CHANGELOG.

## 5. Definition of Done (seção 36)

Código + testes da mudança passando + testes dos módulos vizinhos
passando + CHANGELOG + `docs/CURRENT_STATE.md` + fila em
`docs/tasks-prompt-mestre-v2-restante.md`. Deploy só com confirmação
explícita (ver CLAUDE.md).
