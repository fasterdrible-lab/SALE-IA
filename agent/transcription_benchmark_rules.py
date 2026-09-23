"""
agent/transcription_benchmark_rules.py

Fase 25 do "PROMPT MESTRE — SALE-IA V2" (Critério para iniciar o
Digital Sales Twin), item 4/5 de "o que falta pra ligar" — benchmark
de transcrição, alimentando o critério literal `transcription
reliability >= alvo definido`. Função pura, zero IA/banco, mesmo
padrão de `observability_metrics_rules.py`/`win_loss_rules.py`.

Escopo confirmado com o usuário antes de codar: só o motor de cálculo
(WER, latência, custo, comparação entre provedores) — nenhum dataset
de áudio real com transcrição-gabarito existe hoje no projeto
(confirmado por grep antes de perguntar escopo). Reaproveita
`win_loss_rules.calcular_limites_iqr`/`detectar_outliers_iqr` (Fase 8)
e `observability_metrics_rules.calcular_estatisticas_latencia` (Fase
19) em vez de duplicar — WER numérico recebe o mesmo tratamento de
outlier já usado para ticket/cycle/talk_ratio.

`TRANSCRIPTION_PROVIDERS` espelha as 3 chaves reais de
`api/main.py::_TRANSCRICAO_PROVEDORES` (whisper/groq/whisper_local) —
documentação do vocabulário esperado, nunca imposta pelas funções
abaixo (que aceitam qualquer string de provider), mesmo princípio de
`WIN_LOSS_VARIAVEIS` em `win_loss_rules.py`.
"""

from typing import Optional

from agent.observability_metrics_rules import calcular_estatisticas_latencia
from agent.win_loss_rules import calcular_limites_iqr, detectar_outliers_iqr

TRANSCRIPTION_PROVIDERS = frozenset({"whisper", "groq", "whisper_local"})

# "alvo definido" (texto literal do prompt mestre, Fase 25) — decisão
# desta rodada: WER <= 10% (90% de acurácia de palavras), mesma ordem
# de grandeza dos outros 2 critérios de acurácia da fase (event
# precision / objection classification >= 90%). Sobrescrevível por
# chamada.
WER_ALVO_PADRAO = 0.10

TRANSCRIPTION_BENCHMARK_SEM_DATASET_REAL = {
    "disponivel": False,
    "motivo": (
        "Nenhum dataset de áudio real com transcrição-gabarito existe "
        "hoje no projeto — as funções deste módulo calculam WER/"
        "latência/custo corretamente a partir de pares (referência, "
        "hipótese) já coletados pelo chamador, mas rodar o benchmark "
        "de verdade contra os 3 provedores reais exige gravar/reunir "
        "esse dataset primeiro (decisão de escopo separada, análoga "
        "ao Golden Sales Dataset da Fase 20)."
    ),
}


def calcular_wer(referencia: str, hipotese: str) -> dict:
    """Word Error Rate clássico: (substituições + deleções + inserções)
    / palavras da referência, via distância de edição (Levenshtein) a
    nível de palavra — implementação em Python puro, sem dependência
    nova (mesmo princípio de `win_loss_rules.py`: zero numpy/scipy).
    Comparação sempre case-insensitive (decisão desta rodada — WER
    mede conteúdo transcrito, não capitalização). `referencia` vazia
    devolve `wer=None` (indefinido, nunca dividido por zero)."""
    ref = [p.lower() for p in referencia.split()]
    hip = [p.lower() for p in hipotese.split()]
    n, m = len(ref), len(hip)

    if n == 0:
        return {
            "wer": None,
            "substitutions": 0,
            "deletions": 0,
            "insertions": m,
            "referencia_palavras": 0,
        }

    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref[i - 1] == hip[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])

    i, j = n, m
    substitutions = deletions = insertions = 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and ref[i - 1] == hip[j - 1] and dp[i][j] == dp[i - 1][j - 1]:
            i, j = i - 1, j - 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            substitutions += 1
            i, j = i - 1, j - 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            deletions += 1
            i -= 1
        else:
            insertions += 1
            j -= 1

    return {
        "wer": round(dp[n][m] / n, 4),
        "substitutions": substitutions,
        "deletions": deletions,
        "insertions": insertions,
        "referencia_palavras": n,
    }


def avaliar_meta_confiabilidade(wer: Optional[float], alvo: float = WER_ALVO_PADRAO) -> Optional[bool]:
    """`True` quando `wer` (0-1) atinge o alvo de confiabilidade
    (`wer <= alvo`). `None` quando `wer` é `None` (referência vazia ou
    amostra sem dado) — indefinido, nunca tratado como sucesso nem
    falha por omissão."""
    if wer is None:
        return None
    return wer <= alvo


def montar_resultado_transcricao(
    provider: str,
    referencia: str,
    hipotese: str,
    latencia_ms: Optional[float] = None,
    custo_usd: Optional[float] = None,
) -> dict:
    """1 linha do benchmark: WER + latência + custo de 1 chamada real
    a um provedor. `provider` é string livre — não travado a
    `TRANSCRIPTION_PROVIDERS` (documentação do vocabulário esperado,
    não imposição, mesmo princípio de `win_loss_rules.py`)."""
    resultado_wer = calcular_wer(referencia, hipotese)
    return {
        "provider": provider,
        "wer": resultado_wer["wer"],
        "substitutions": resultado_wer["substitutions"],
        "deletions": resultado_wer["deletions"],
        "insertions": resultado_wer["insertions"],
        "referencia_palavras": resultado_wer["referencia_palavras"],
        "latencia_ms": latencia_ms,
        "custo_usd": custo_usd,
    }


def comparar_provedores(resultados: list) -> dict:
    """Agrupa resultados de `montar_resultado_transcricao()` por
    `provider` e resume WER (outliers via IQR, mesmo tratamento de
    `win_loss_rules.resumir_variavel_numerica`) + latência (reaproveita
    `observability_metrics_rules.calcular_estatisticas_latencia`) +
    custo médio. Provider sem nenhum resultado com `wer` não-`None`
    nunca aparece com WER `0`/`atinge_meta=False` por omissão — ambos
    vêm `None`."""
    por_provider: dict = {}
    for r in resultados:
        por_provider.setdefault(r["provider"], []).append(r)

    resumo = {}
    for provider, linhas in por_provider.items():
        wers = [l["wer"] for l in linhas if l["wer"] is not None]
        custos = [l["custo_usd"] for l in linhas if l.get("custo_usd") is not None]

        limites = calcular_limites_iqr(wers) if wers else None
        if limites is not None:
            inferior, superior = limites
            wers_sem_outliers = [w for w in wers if inferior <= w <= superior]
        else:
            wers_sem_outliers = wers
        outliers = detectar_outliers_iqr(wers) if wers else []

        wer_medio = round(sum(wers_sem_outliers) / len(wers_sem_outliers), 4) if wers_sem_outliers else None

        resumo[provider] = {
            "n": len(linhas),
            "wer_medio": wer_medio,
            "wer_n_outliers": len(outliers),
            "latencia": calcular_estatisticas_latencia([l.get("latencia_ms") for l in linhas]),
            "custo_medio_usd": round(sum(custos) / len(custos), 6) if custos else None,
            "atinge_meta": avaliar_meta_confiabilidade(wer_medio),
        }
    return resumo
