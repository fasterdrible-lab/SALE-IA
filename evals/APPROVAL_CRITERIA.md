# Criterios de Aprovacao — Troca de Prompt em Producao

TAREFA 2.7 do `PROMPT MESTRE — EVOLUÇÃO DA SALEIA.txt`. Aplica-se a
qualquer mudanca em `agent/prompt_templates/*.txt` usado pelos agentes do
multiagente (`coach`, `disc`, `finance`, `closer`).

## Antes de trocar um prompt em producao

1. **Accuracy nao pode cair.** Rode a suite atual (`npm run eval:coach` /
   `eval:finance`) com o prompt antigo (baseline) e com o novo, e compare
   os resultados em `evals/results/*.json` — nenhuma assertion que
   passava no baseline pode passar a falhar no novo prompt sem uma razao
   documentada.
2. **JSON validity >= 99%.** A assertion `is-json` (aplicada por padrao
   a todo teste via `defaultTest`) precisa passar em praticamente 100%
   dos casos — os agentes tem `try/except` de degradacao no orquestrador
   (`agent/multiagente/orquestrador.py::_safe`), mas um prompt que quebra
   o formato JSON com frequencia gera fallback silencioso em producao.
3. **Hallucination rate <= limite.** Para o Finance Agent em especifico,
   ver os testes `CASH_FLOW`/"Sem mencao financeira" em
   `datasets/finance/price_objections.yaml` — o prompt manda "nunca
   invente valores"; qualquer regressao ai (campo preenchido sem o
   cliente ter mencionado) bloqueia a troca.
4. **Cost delta conhecido.** Comparar tamanho do prompt (tokens de
   entrada) e o `tokenUsage`/custo reportado pelo Promptfoo entre versoes
   — se o novo prompt for sensivelmente mais caro, isso precisa ser uma
   decisao consciente, nao um efeito colateral.
5. **Latency delta conhecido.** Mesma logica do item anterior, usando a
   latencia reportada pelo Promptfoo.
6. **Sem regressao de seguranca.** Rodar `npm run eval:redteam`
   (`evals/promptfooconfig.redteam.yaml`) contra o novo prompt — nenhum
   caso que resistia a injection/role override/exfiltration antes pode
   passar a vazar informacao ou mudar de comportamento.

## O que NAO bloqueia a troca

- Diferencas de fraseado que nao mudam o schema nem o comportamento
  avaliado (os testes usam `llm-rubric`/assertions de comportamento, nao
  match exato de texto, justamente para nao travar em parafraseamento).
- Economia de custo/latencia sem perda de accuracy — sempre bem-vinda.

## Registro da decisao

Toda troca de prompt aprovada por este processo deve ser documentada no
`CHANGELOG.md` (mesmo padrao ja usado no projeto: o que mudou, por que, e
o resultado do eval que embasou a decisao) — ainda nao existe um script
automatico de "diff de eval entre 2 rodadas"; a comparacao acima e feita
manualmente lendo os JSONs de `evals/results/` ate que a TAREFA 2.9 (CI)
gere esse relatorio automaticamente por PR.
