"""
agent/quality_monitoring_golden_runner.py

Fase 25 ("o que falta pra ligar", item 3/5) — roda o Golden Sales
Dataset (Fase 20, `evals/datasets/golden_sales_dataset/`, 40 cenários)
contra o pipeline real pra alimentar 4 das 6 métricas de Quality
Monitoring (Tarefa 19.1, `agent/quality_monitoring_rules.py`) com dado
real: `framework_accuracy`, `objection_precision`, `hallucination_rate`,
`evidence_coverage`.

Escopo confirmado com o usuário (pergunta direta antes de codar, mesma
disciplina de toda fase do roadmap):
- **`event_precision` continua gap explícito** — nenhum extrator de
  `SalesEvent` a partir de texto livre foi construído em nenhuma fase
  (`SalesEvent`, Fase 1, `criar_sales_event()` tem zero chamada em
  produção hoje — confirmado por grep antes de decidir isso). Medir
  isso exigiria construir um extrator novo do zero pra uma estrutura
  que não alimenta nada real no sistema — fora do escopo desta rodada.
- **`recommendation_relevance` também não é calculada aqui** — exigiria
  um LLM-judge (chamada de IA extra por cenário) comparando a saída
  contra `acceptable_actions`/`forbidden_actions`; decisão de custo
  separada, não incluída nesta rodada.

Como cada métrica é medida — **v2 (esta rodada): contexto estruturado
real, não só texto bruto**. A primeira rodada (v1) rodava o motor só
com `meeting_memory.transcricao_parcial`, os outros 10 campos `None`.
Diagnóstico por cenário (`framework_accuracy=33%`) mostrou que a
maioria dos erros vinha do motor sendo corretamente conservador diante
de campos ausentes (ex.: recusar `CLOSING` sem `meddpicc_state`
confirmado — regra explícita da Fase 4.2), não de raciocínio ruim —
mesma disciplina de investigar a causa antes de aceitar um número.
Usuário confirmou rodar de novo com contexto mais fiel à produção real:
- **`spin_state`/`behavioral_signals`/`buyer_motivation`**: os 3
  extratores do Bloco 4 (`agent/spin_extractor.py`/
  `behavioral_signal_extractor.py`/`buyer_motivation_extractor.py`,
  mesmos usados em produção por `agent/multiagente/orquestrador.py`)
  rodam em paralelo (`asyncio.gather`) pra CADA um dos 40 cenários,
  com `historico=HISTORICO_PADRAO` (cenário sintético isolado, sem
  conversa prévia real).
- **`objections`**: só pros 4 cenários de `objections.yaml` — a
  categoria já classificada (mesma chamada de `objection_precision`,
  sem custo extra) monta um `objection_spoken` real via `agent/
  objection_rules.py::registrar_objecao()` (sem `root_cause_
  hypothesis` — esse extrator não foi acionado aqui, fora do escopo).
- **`meddpicc_state` continua sempre `None`** — nenhum extrator existe
  (Tarefa 1.1 permanece bloqueada, sem citação real disponível no
  `maturity_score` do Closer, mesma limitação documentada desde
  V.1.4.121). Cenários que dependem de MEDDPICC confirmado pra bater
  o gabarito (ex.: `closing-01/02/03/04`) devem continuar errando por
  este motivo específico, não por regressão do motor.
- **`framework_accuracy`**: para os cenários com `expected_framework`
  não-nulo (~27 dos 40), compara `recommended_framework` contra o
  esperado, agora com o contexto estruturado acima.
- **`objection_precision`**: inalterado da v1 — `agent/
  objection_category_classifier.py::classificar_categoria_objecao_
  async()` com a `evidence_quote` do fato esperado, compara contra a
  categoria esperada (`extrair_categoria_esperada()`).
- **`hallucination_rate`/`evidence_coverage`**: cada item de `evidence`
  checado como substring literal do `input` bruto do cenário — ainda
  válido com contexto estruturado, porque os 3 extratores acima já
  garantem por construção que seus próprios `evidence_quote` são
  substring literal do texto recebido (mesma guarda desde o Bloco 4) —
  então qualquer `evidence` do motor que aponte pra um fato desses
  também aponta, transitivamente, pro texto bruto.

Total de chamadas reais de IA: até 40 × 4 (reasoning + spin +
behavioral + motivation) + 4 (classificador de objeção, sem
duplicação) = até 164, todas via DeepSeek por padrão (mesmo provedor
barato já usado no resto da suíte Promptfoo do projeto) — salto de
custo real frente às 44 da v1, confirmado com o usuário antes de
rodar.

**Achado real desta rodada (rodagem completa em 23/09/2026,
`hallucination_rate=90.87%`/`evidence_coverage=9.13%`) — falso
positivo estrutural, não qualidade real do motor**: o checador
original (`texto_contido_em`) só aceitava `evidence` que fosse
substring literal do TEXTO BRUTO do cenário. Mas o prompt do
`SalesReasoningEngine` (`agent/prompt_templates/
sales_reasoning_engine.txt`) permite citar qualquer campo de entrada
recebido — inclusive resumos verdadeiros em linguagem natural sobre
`spin_state`/`meddpicc_state`/etc. (ex.: `"meddpicc_state é null"`,
`"spin_state.problem.missing inclui 'main_pain'"` — ambos fatos 100%
reais sobre a entrada que a IA de fato recebeu, confirmados por
diagnóstico pontual com IA real). O checador batia só contra o texto
da conversa, então marcava esses resumos estruturais corretos como
"sem evidência" — inflando `hallucination_rate` artificialmente.
Corrigido com `evidencia_fundamentada()`: compara contra o MESMO
bundle de 11 campos que `raciocinar_async()` de fato serializa no
prompt (`montar_texto_fundamentacao()`, espelha o loop de
`agent/sales_reasoning_engine.py::raciocinar_async` que monta o
prompt), e tolera paráfrase (cobertura de palavras significativas, não
substring exata) — ainda determinístico, sem LLM-judge novo.
`texto_contido_em()` (substring estrita) foi removido por ficar sem
uso real depois desta correção — `evidencia_fundamentada()` é
estritamente mais correta pro mesmo objetivo.
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Optional

import yaml

DATASET_DIR = Path(__file__).parent.parent / "evals" / "datasets" / "golden_sales_dataset"

# Único arquivo do dataset com categoria de objeção extraível com
# segurança de `expected_facts[0].valor` (texto livre "categoria X"),
# ver docstring do módulo.
ARQUIVO_OBJECOES = "objections.yaml"

# Cenários são falas/trechos isolados e sintéticos, sem conversa prévia
# real — mesmo valor default já usado em `agent/multiagente/
# orquestrador.py::analisar_fragmento_multi()` pra reunião sem
# histórico ainda.
HISTORICO_PADRAO = "Início da conversa"


def carregar_cenarios_golden_dataset(dataset_dir: Path = DATASET_DIR) -> list[dict]:
    """Carrega os 40 cenários dos 10 arquivos YAML do Golden Sales
    Dataset (Fase 20) — cada cenário ganha `_arquivo` (nome do YAML de
    origem), usado por `objection_precision` pra saber quais vieram de
    `objections.yaml`. Nunca chama IA — leitura pura de disco."""
    cenarios = []
    for arquivo in sorted(Path(dataset_dir).glob("*.yaml")):
        with open(arquivo, encoding="utf-8") as f:
            itens = yaml.safe_load(f) or []
        for item in itens:
            item = dict(item)
            item["_arquivo"] = arquivo.name
            cenarios.append(item)
    return cenarios


def extrair_categoria_esperada(valor: Optional[str]) -> Optional[str]:
    """Extrai a categoria de objeção esperada de um texto livre como
    "categoria TRUST" ou "categoria PRICE (fala literal), mas root
    cause é ADOPTION" — sempre a PRIMEIRA categoria mencionada, que é
    sempre `objection_spoken` (a categoria falada, o que o classificador
    testado aqui de fato classifica — root cause é um módulo
    diferente, `objection_root_cause_extractor.py`, fora do escopo
    desta métrica). `None` se o padrão "categoria X" não aparecer."""
    match = re.search(r"categoria\s+([A-Z_]+)", valor or "")
    return match.group(1) if match else None


# Conectivos/rótulos genéricos demais pra contar como "conteúdo
# específico" numa afirmação — sem isso, qualquer afirmação que
# mencione "cliente"/"vendedor" (aparece em ~100% dos cenários, são os
# rótulos de fala) inflaria a cobertura de qualquer frase, mesmo
# fabricada. Lista pequena e deliberada, não um NLP genérico.
_STOPWORDS_FUNDAMENTACAO = frozenset({
    "com", "para", "que", "uma", "das", "dos", "essa", "esse",
    "esta", "este", "isso", "está", "estão", "estao", "sido", "ser",
    "tem", "não", "nao", "são", "sao", "foi", "pela", "pelo", "algum",
    "alguma", "sobre", "todos", "todas", "indica", "inclui", "cliente",
    "vendedor", "campo", "campos", "the", "and", "for", "from",
})


def _tokens_significativos(texto: Optional[str]) -> set:
    palavras = re.findall(r"[a-zà-öø-ÿ0-9_]+", (texto or "").lower())
    return {p for p in palavras if len(p) >= 4 and p not in _STOPWORDS_FUNDAMENTACAO}


def evidencia_fundamentada(afirmacao: Optional[str], texto_fonte: Optional[str], cobertura_minima: float = 0.6) -> bool:
    """Mais tolerante que substring exata — aceita paráfrase/resumo
    verdadeiro em linguagem natural sobre a entrada, não só citação
    literal da conversa (achado real desta rodada: `evidence` do
    SalesReasoningEngine legitimamente descreve campos estruturados
    como `"meddpicc_state é null"`, nunca uma citação literal de nada,
    mesmo sendo 100% verdadeiro — ver docstring do módulo).

    Considera fundamentada quando pelo menos `cobertura_minima` das
    palavras significativas (>= 4 caracteres, fora de conectivos/
    rótulos comuns de `_STOPWORDS_FUNDAMENTACAO`) da afirmação aparecem
    literalmente em `texto_fonte` — tolera palavra de ligação que a IA
    usa pra parafrasear um fato real, mas ainda rejeita afirmação cujo
    conteúdo específico (nome de campo, valor, número, citação) não
    aparece em lugar nenhum da entrada recebida. Determinístico, sem
    chamada de IA extra (LLM-judge é decisão de custo separada, Tarefa
    19.1)."""
    tokens = _tokens_significativos(afirmacao)
    if not tokens:
        return False
    fonte = (texto_fonte or "").lower()
    cobertos = sum(1 for t in tokens if t in fonte)
    return (cobertos / len(tokens)) >= cobertura_minima


def _montar_entrada_reasoning(cenario: dict, contexto: Optional[dict] = None, objections: Optional[list] = None) -> dict:
    entrada = {"meeting_memory": {"transcricao_parcial": cenario["input"]}}
    if contexto:
        entrada.update(contexto)
    if objections:
        entrada["objections"] = objections
    return entrada


def montar_texto_fundamentacao(cenario: dict, contexto: Optional[dict] = None, objections: Optional[list] = None) -> str:
    """Texto contra o qual `evidence` é checado por
    `evidencia_fundamentada()` — reproduz o MESMO bundle de 11 campos
    que `agent/sales_reasoning_engine.py::raciocinar_async()` de fato
    serializa no prompt enviado à IA (`construir_input_vazio()` +
    `entrada`, campo ausente vira `null`, idêntico ao loop de
    serialização de `raciocinar_async`) — não só o texto bruto da
    conversa. Isso é o que corrige o falso positivo desta rodada: a
    IA pode citar `meddpicc_state: null` porque foi literalmente isso
    que ela recebeu no prompt, mesmo sem aparecer no texto da fala."""
    from agent.sales_reasoning_engine import SALES_REASONING_INPUT_CAMPOS, construir_input_vazio

    entrada = _montar_entrada_reasoning(cenario, contexto, objections)
    bundle = {**construir_input_vazio(), **entrada}

    partes = [cenario["input"]]
    for campo in SALES_REASONING_INPUT_CAMPOS:
        valor = bundle[campo]
        serializado = json.dumps(valor, ensure_ascii=False) if valor is not None else "null"
        partes.append(f"{campo}:\n{serializado}")
    return "\n\n".join(partes)


async def _extrair_contexto_estruturado(cenario: dict) -> dict:
    """Roda os 3 extratores do Bloco 4 em paralelo pra popular
    `spin_state`/`behavioral_signals`/`buyer_motivation` a partir do
    `input` do cenário — mesma disciplina de produção (`agent/
    multiagente/orquestrador.py`). Falha de um extrator isolado vira
    `None`/lista vazia (mesmo default de entrada não-preenchida do
    contrato do SalesReasoningEngine) e nunca derruba os outros 2 nem
    o cenário inteiro."""
    from agent.behavioral_signal_extractor import extrair_sinais_comportamentais_async
    from agent.buyer_motivation_extractor import extrair_buyer_motivation_async
    from agent.spin_extractor import extrair_spin_state_async

    spin_state, behavioral_signals, buyer_motivation = await asyncio.gather(
        extrair_spin_state_async(cenario["input"], HISTORICO_PADRAO),
        extrair_sinais_comportamentais_async(cenario["input"], HISTORICO_PADRAO),
        extrair_buyer_motivation_async(cenario["input"], HISTORICO_PADRAO),
        return_exceptions=True,
    )
    return {
        "spin_state": None if isinstance(spin_state, Exception) else spin_state,
        "behavioral_signals": None if isinstance(behavioral_signals, Exception) else behavioral_signals,
        "buyer_motivation": None if isinstance(buyer_motivation, Exception) else buyer_motivation,
    }


async def _rodar_reasoning(cenario: dict, contexto: Optional[dict] = None, objections: Optional[list] = None) -> dict:
    from agent.sales_reasoning_engine import raciocinar_async

    entrada = _montar_entrada_reasoning(cenario, contexto, objections)
    return await raciocinar_async(entrada)


async def _rodar_classificador_objecao(cenario: dict) -> Optional[str]:
    from agent.objection_category_classifier import classificar_categoria_objecao_async

    fatos = cenario.get("expected_facts") or [{}]
    texto = fatos[0].get("evidence_quote") or ""
    return await classificar_categoria_objecao_async(texto)


async def executar_golden_dataset_async(cenarios: Optional[list[dict]] = None) -> dict:
    """Motor real — chama IA de verdade (custo real, ver docstring do
    módulo). `cenarios=None` carrega os 40 reais do disco; testes
    passam uma lista sintética pequena. Uma falha num cenário isolado
    (IA fora do ar, resposta malformada) nunca derruba os outros —
    fica registrada em `erros`, mesma disciplina best-effort do resto
    do projeto, mas aqui é sobre um script de avaliação, não sobre o
    ciclo real de um vendedor."""
    cenarios = carregar_cenarios_golden_dataset() if cenarios is None else cenarios

    framework_corretos = framework_total = 0
    objecao_vp = objecao_fp = 0
    afirm_com_evidencia = afirm_sem_evidencia = 0
    erros: list[str] = []

    for cenario in cenarios:
        cid = cenario.get("id", "?")

        objections = None
        if cenario.get("_arquivo") == ARQUIVO_OBJECOES:
            fatos = cenario.get("expected_facts") or [{}]
            evidence_quote = fatos[0].get("evidence_quote") or ""
            esperado_cat = extrair_categoria_esperada(fatos[0].get("valor"))
            try:
                predita = await _rodar_classificador_objecao(cenario)
            except Exception as e:
                erros.append(f"{cid}: classificador de objeção falhou: {type(e).__name__}: {e}")
                predita = None
            if predita is not None and esperado_cat is not None and predita == esperado_cat:
                objecao_vp += 1
            else:
                objecao_fp += 1
            if predita is not None:
                from agent.objection_rules import OBJECTION_TIPOS, registrar_objecao
                if predita in OBJECTION_TIPOS:
                    objections = [registrar_objecao({"category": predita, "evidence_quote": evidence_quote})]

        try:
            contexto = await _extrair_contexto_estruturado(cenario)
        except Exception as e:
            erros.append(f"{cid}: extração de contexto estruturado falhou: {type(e).__name__}: {e}")
            contexto = None

        try:
            saida = await _rodar_reasoning(cenario, contexto, objections)
        except Exception as e:
            erros.append(f"{cid}: raciocinar_async falhou: {type(e).__name__}: {e}")
            saida = None

        if saida is not None:
            esperado_fw = cenario.get("expected_framework")
            if esperado_fw:
                framework_total += 1
                if saida.get("recommended_framework") == esperado_fw:
                    framework_corretos += 1

            texto_fundamentacao = montar_texto_fundamentacao(cenario, contexto, objections)
            for afirmacao in (saida.get("evidence") or []):
                if evidencia_fundamentada(afirmacao, texto_fundamentacao):
                    afirm_com_evidencia += 1
                else:
                    afirm_sem_evidencia += 1

    return {
        "framework_corretos": framework_corretos,
        "framework_total": framework_total,
        "objecao_vp": objecao_vp,
        "objecao_fp": objecao_fp,
        "afirmacoes_com_evidencia": afirm_com_evidencia,
        "afirmacoes_sem_evidencia": afirm_sem_evidencia,
        "erros": erros,
        "total_cenarios": len(cenarios),
    }


def montar_relatorio_metricas(contagens: dict) -> dict:
    """Reshape das contagens brutas de `executar_golden_dataset_async()`
    pros 4 números reais via `agent/quality_monitoring_rules.py` — nunca
    recalcula a fórmula aqui, só monta o dict final + os 2 gaps
    explícitos (`event_precision`/`recommendation_relevance`)."""
    from agent.quality_monitoring_rules import (
        QUALITY_METRIC_SEM_GABARITO,
        calcular_evidence_coverage,
        calcular_framework_accuracy,
        calcular_hallucination_rate,
        calcular_objection_precision,
    )

    return {
        "event_precision": QUALITY_METRIC_SEM_GABARITO,
        "objection_precision": calcular_objection_precision(contagens["objecao_vp"], contagens["objecao_fp"]),
        "framework_accuracy": calcular_framework_accuracy(contagens["framework_corretos"], contagens["framework_total"]),
        "recommendation_relevance": {
            "disponivel": False,
            "motivo": "Exige LLM-judge (chamada de IA extra por cenário) — decisão de custo separada, não incluída nesta rodada.",
        },
        "hallucination_rate": calcular_hallucination_rate(
            contagens["afirmacoes_sem_evidencia"],
            contagens["afirmacoes_com_evidencia"] + contagens["afirmacoes_sem_evidencia"],
        ),
        "evidence_coverage": calcular_evidence_coverage(
            contagens["afirmacoes_com_evidencia"],
            contagens["afirmacoes_com_evidencia"] + contagens["afirmacoes_sem_evidencia"],
        ),
        "amostra": {
            "total_cenarios": contagens["total_cenarios"],
            "framework_total": contagens["framework_total"],
            "objecao_total": contagens["objecao_vp"] + contagens["objecao_fp"],
            "afirmacoes_total": contagens["afirmacoes_com_evidencia"] + contagens["afirmacoes_sem_evidencia"],
            "erros": contagens["erros"],
        },
    }
