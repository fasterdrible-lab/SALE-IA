"""
SALEIA — agent/win_loss_rules.py

Regras puras de Win/Loss Intelligence (FASE 8 / TAREFA 8.2 do "PROMPT
MESTRE — SALE-IA V2"). Nenhuma chamada de IA, nenhum acesso a banco,
nenhuma dependência nova (zero numpy/scipy — estatística implementada
em Python puro) — mesmo padrão de agent/outcome_rules.py.

Objetivo do prompt mestre: comparar oportunidades ganhas e perdidas
pelas 15 variáveis em WIN_LOSS_VARIAVEIS (documentação do vocabulário
esperado — as funções abaixo são genéricas sobre qualquer campo
presente nos dicts recebidos, não travadas a esses 15 nomes).

Regra científica central (imposta estruturalmente, não só por
instrução): **nunca declarar causalidade** ("X causa vendas") —
**sempre associação** ("X está associado a maior conversão nesta
amostra"). As únicas strings de texto livre que este módulo produz
vêm de `TEMPLATE_AFIRMACAO_ASSOCIACAO`/`TEMPLATE_AMOSTRA_INSUFICIENTE`/
`TEMPLATE_SIMPSONS_PARADOX` — templates fixos, nunca f-strings ad hoc
espalhadas pelo código — guardados por
`tests/test_win_loss_rules.py::GuardaContraCausalidadeTest`.
"""

from typing import Optional

# As 15 variáveis literais do prompt mestre — documentação do
# vocabulário esperado, não uma lista fechada imposta pelas funções
# abaixo (que aceitam qualquer nome de campo presente nos dicts).
WIN_LOSS_VARIAVEIS = frozenset({
    "segment", "seller", "origin", "ticket", "cycle", "pain",
    "objection", "decision_maker", "champion", "strategy",
    "spin_coverage", "meddpicc_coverage", "talk_ratio", "next_step",
    "season",
})

# Amostra mínima para considerar uma taxa de conversão comparável —
# regra de bolso padrão para a aproximação normal de proporções ser
# razoável (np >= 5 e n(1-p) >= 5 quase sempre valem com n>=30 mesmo
# em taxas extremas). Sobrescrevível por chamada.
AMOSTRA_MINIMA_PADRAO = 30

_Z_SCORES = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}

TEMPLATE_AFIRMACAO_ASSOCIACAO = (
    "{campo}={valor!r} está associado a uma taxa de conversão de "
    "{taxa:.0%} nesta amostra (n={n})."
)
TEMPLATE_AMOSTRA_INSUFICIENTE = (
    "{campo}={valor!r}: amostra insuficiente (n={n} < {minimo}) para "
    "afirmar qualquer associação."
)
TEMPLATE_SIMPSONS_PARADOX = (
    "Possível paradoxo de Simpson: a tendência agregada ({grupo_a!r} vs "
    "{grupo_b!r}) se inverte em todos os {n_segmentos} segmentos "
    "analisados de {campo_segmento!r}. Investigar antes de afirmar "
    "qualquer associação entre {campo!r} e conversão."
)


def calcular_taxa_conversao(opportunities: list) -> dict:
    """Taxa de conversão geral. Só conta status won/lost — "open" e
    "abandoned" não são um desfecho comparável ainda (Fase 8 / Tarefa
    8.1)."""
    won = sum(1 for o in opportunities if o.get("status") == "won")
    lost = sum(1 for o in opportunities if o.get("status") == "lost")
    total = won + lost
    return {
        "won": won,
        "lost": lost,
        "total": total,
        "taxa_conversao": (won / total) if total else None,
    }


def amostra_suficiente(n: int, minimo: int = AMOSTRA_MINIMA_PADRAO) -> bool:
    return n >= minimo


def intervalo_confianca_wilson(
    sucessos: int, total: int, confianca: float = 0.95,
) -> Optional[tuple]:
    """Intervalo de confiança de Wilson para uma proporção — mais
    confiável que a aproximação normal simples para amostras pequenas
    ou taxas perto de 0/1 (caso comum em win rate de vendas). Retorna
    None quando `total` é 0."""
    if total == 0:
        return None
    if confianca not in _Z_SCORES:
        raise ValueError(f"confiança não suportada: {confianca!r} (use um de {sorted(_Z_SCORES)})")
    z = _Z_SCORES[confianca]
    p = sucessos / total
    denominador = 1 + z**2 / total
    centro = (p + z**2 / (2 * total)) / denominador
    margem = (z * ((p * (1 - p) / total + z**2 / (4 * total**2)) ** 0.5)) / denominador
    return (max(0.0, centro - margem), min(1.0, centro + margem))


def _percentil(ordenados: list, p: float) -> float:
    """Percentil por interpolação linear (mesmo método default do
    `numpy.percentile`) — sem depender de numpy."""
    if not ordenados:
        raise ValueError("lista vazia")
    k = (len(ordenados) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(ordenados) - 1)
    if f == c:
        return ordenados[f]
    return ordenados[f] + (ordenados[c] - ordenados[f]) * (k - f)


def calcular_limites_iqr(valores: list) -> Optional[tuple]:
    """(limite_inferior, limite_superior) pelo método IQR clássico
    (Q1 - 1.5*IQR, Q3 + 1.5*IQR). None quando a amostra é pequena
    demais pra quartis fazerem sentido (< 4 valores)."""
    if len(valores) < 4:
        return None
    ordenados = sorted(valores)
    q1 = _percentil(ordenados, 25)
    q3 = _percentil(ordenados, 75)
    iqr = q3 - q1
    return (q1 - 1.5 * iqr, q3 + 1.5 * iqr)


def detectar_outliers_iqr(valores: list) -> list:
    """Valores fora dos limites IQR. Lista vazia quando a amostra é
    pequena demais (`calcular_limites_iqr` retorna None) — nunca
    levanta, só não detecta nada."""
    limites = calcular_limites_iqr(valores)
    if limites is None:
        return []
    inferior, superior = limites
    return [v for v in valores if v < inferior or v > superior]


def comparar_por_variavel_categorica(
    opportunities: list,
    campo: str,
    minimo_amostra: int = AMOSTRA_MINIMA_PADRAO,
    confianca: float = 0.95,
) -> dict:
    """Agrupa oportunidades won/lost pelo valor de `campo` (qualquer
    uma das variáveis categóricas do prompt mestre — segment, seller,
    origin, pain, objection, decision_maker, champion, strategy,
    next_step, season) e compara a taxa de conversão por grupo.

    Oportunidades sem valor em `campo` (None/ausente) são contadas em
    "sem_dado", nunca descartadas silenciosamente nem tratadas como um
    grupo "None". Grupo com amostra insuficiente nunca recebe intervalo
    de confiança nem afirmação de associação — só o aviso de amostra
    insuficiente."""
    if not campo:
        raise ValueError("campo é obrigatório")

    contagens: dict = {}
    sem_dado = 0
    for o in opportunities:
        if o.get("status") not in ("won", "lost"):
            continue
        valor = o.get(campo)
        if valor is None:
            sem_dado += 1
            continue
        grupo = contagens.setdefault(valor, {"won": 0, "lost": 0})
        grupo[o["status"]] += 1

    grupos = {}
    for valor, contagem in contagens.items():
        total = contagem["won"] + contagem["lost"]
        taxa = contagem["won"] / total if total else None
        suficiente = amostra_suficiente(total, minimo_amostra)
        if suficiente:
            ic = intervalo_confianca_wilson(contagem["won"], total, confianca)
            afirmacao = TEMPLATE_AFIRMACAO_ASSOCIACAO.format(campo=campo, valor=valor, taxa=taxa, n=total)
        else:
            ic = None
            afirmacao = TEMPLATE_AMOSTRA_INSUFICIENTE.format(campo=campo, valor=valor, n=total, minimo=minimo_amostra)
        grupos[valor] = {
            "won": contagem["won"],
            "lost": contagem["lost"],
            "total": total,
            "taxa_conversao": taxa,
            "amostra_suficiente": suficiente,
            "intervalo_confianca": ic,
            "afirmacao": afirmacao,
        }

    return {"campo": campo, "grupos": grupos, "sem_dado": sem_dado}


def resumir_variavel_numerica(
    opportunities: list,
    campo: str,
    status_filtro: Optional[str] = None,
) -> dict:
    """Resumo estatístico de uma variável numérica (ticket, cycle,
    talk_ratio, spin_coverage, meddpicc_coverage) — separa outliers
    (IQR) da média/mediana em vez de deixá-los distorcer o resumo
    silenciosamente; `n_outliers`/`outliers` sempre reportados, nunca
    escondidos."""
    valores = []
    for o in opportunities:
        if status_filtro and o.get("status") != status_filtro:
            continue
        valor = o.get(campo)
        if valor is None:
            continue
        valores.append(float(valor))

    if not valores:
        return {"n": 0, "n_outliers": 0, "outliers": [], "media_sem_outliers": None, "mediana_sem_outliers": None}

    limites = calcular_limites_iqr(valores)
    if limites is not None:
        inferior, superior = limites
        sem_outliers = [v for v in valores if inferior <= v <= superior]
        outliers = [v for v in valores if v < inferior or v > superior]
    else:
        sem_outliers, outliers = valores, []

    media = sum(sem_outliers) / len(sem_outliers) if sem_outliers else None
    mediana = _percentil(sorted(sem_outliers), 50) if sem_outliers else None

    return {
        "n": len(valores),
        "n_outliers": len(outliers),
        "outliers": outliers,
        "media_sem_outliers": media,
        "mediana_sem_outliers": mediana,
    }


def detectar_simpsons_paradox(opportunities: list, campo: str, campo_segmento: str) -> dict:
    """Compara exatamente 2 valores de `campo` (ex.: 2 estratégias) e
    detecta se a direção da comparação agregada se inverte quando os
    dados são segmentados por `campo_segmento` — a assinatura clássica
    do paradoxo de Simpson. Exige exatamente 2 valores em `campo`; o
    paradoxo clássico compara 2 grupos, generalizar pra N grupos é
    escopo futuro não pedido pela Tarefa 8.2."""
    agregado = comparar_por_variavel_categorica(opportunities, campo)
    valores = sorted(agregado["grupos"].keys(), key=str)
    if len(valores) != 2:
        raise ValueError(f"Simpson's paradox exige exatamente 2 valores de {campo!r}, recebido {len(valores)}: {valores}")

    grupo_a, grupo_b = valores
    taxa_a = agregado["grupos"][grupo_a]["taxa_conversao"]
    taxa_b = agregado["grupos"][grupo_b]["taxa_conversao"]
    if taxa_a is None or taxa_b is None or taxa_a == taxa_b:
        direcao_agregada = None
    else:
        direcao_agregada = grupo_a if taxa_a > taxa_b else grupo_b

    valores_segmento = sorted({o.get(campo_segmento) for o in opportunities if o.get(campo_segmento) is not None}, key=str)
    direcoes_por_segmento = {}
    reversoes = 0
    segmentos_validos = 0
    for seg in valores_segmento:
        subset = [o for o in opportunities if o.get(campo_segmento) == seg]
        comparacao = comparar_por_variavel_categorica(subset, campo)
        grupos_seg = comparacao["grupos"]
        if grupo_a not in grupos_seg or grupo_b not in grupos_seg:
            continue  # segmento sem dado pros dois grupos, nao comparavel
        ta = grupos_seg[grupo_a]["taxa_conversao"]
        tb = grupos_seg[grupo_b]["taxa_conversao"]
        if ta is None or tb is None or ta == tb:
            continue
        direcao_seg = grupo_a if ta > tb else grupo_b
        direcoes_por_segmento[seg] = direcao_seg
        segmentos_validos += 1
        if direcao_agregada is not None and direcao_seg != direcao_agregada:
            reversoes += 1

    possivel_paradox = (
        direcao_agregada is not None
        and segmentos_validos > 0
        and reversoes == segmentos_validos
    )

    afirmacao = None
    if possivel_paradox:
        afirmacao = TEMPLATE_SIMPSONS_PARADOX.format(
            grupo_a=grupo_a, grupo_b=grupo_b, n_segmentos=segmentos_validos, campo_segmento=campo_segmento, campo=campo,
        )

    return {
        "direcao_agregada": direcao_agregada,
        "direcoes_por_segmento": direcoes_por_segmento,
        "possivel_simpsons_paradox": possivel_paradox,
        "afirmacao": afirmacao,
    }
