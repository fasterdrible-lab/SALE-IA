"""Fase 23 do "PROMPT MESTRE — SALE-IA V2" — Teste em Shadow Mode.

"Antes de permitir que o novo Sales Reasoning Engine influencie
vendedores reais: executá-lo silenciosamente. Modelo atual continua
recomendando; novo modelo analisa silenciosamente. Comparar resultados.
Medir: agreement, disagreement, latency, errors, cost, quality. Só
liberar após avaliação."

Função pura — zero IA/banco — que monta o registro de uma comparação
entre a recomendação real (`agent/multiagente/orquestrador.py`, os 4-5
agentes já em produção) e a recomendação silenciosa do
`agent/sales_reasoning_engine.py::raciocinar_async()` (Fase 7). Quem
chama a IA e persiste o registro é `orquestrador.py`/`api/database.py`
— este módulo só decide o que os campos significam.

**Concordância estrutural, não semântica**: o único sinal comparável
sem chamar IA de novo é binário — os dois modelos recomendam uma
PERGUNTA ao cliente agora, ou não? O modelo atual expõe isso via
`next_best_action.type` (vocabulário fechado `question|insight|
warning|next_step`, `agent/prompt_templates/multiagente_coach.txt`); o
modelo novo via `next_best_question` (presente ou `None`,
`agent/sales_reasoning_engine.py`). **Nunca tenta mapear** a `category`
do modelo atual (12 valores de vocabulário livre da IA) para o
`recommended_framework` do modelo novo (9 valores de vocabulário
fechado) — nenhuma função traduz um formato pro outro, mesmo princípio
já usado em `agent/opportunity_intelligence_rules.py` (SPIN/MEDDPICC
vs. categorias de `OpportunityMemory`): inventar esse mapeamento seria
fabricar concordância, não medi-la.

`quality` (a recomendação nova é de fato BOA, não só estruturalmente
comparável) fica como gap explícito — exigiria um LLM-judge (mesmo
mecanismo de `evals/promptfooconfig.*.yaml`, `llm-rubric`), custo real
de IA por comparação, decisão de produto separada desta rodada.
"""

SHADOW_MODE_METRICAS = ("agreement", "latency_ms", "cost_usd", "errors", "quality")

QUALITY_NAO_DISPONIVEL = {
    "disponivel": False,
    "motivo": (
        "Avaliar se a recomendação do modelo novo é de fato boa (não só "
        "estruturalmente comparável à do modelo atual) exigiria um "
        "LLM-judge (mesmo mecanismo de evals/promptfooconfig.*.yaml, "
        "llm-rubric) — custo real de IA por comparação, decisão de "
        "produto separada, nunca rodada nesta rodada."
    ),
}


def avaliar_concordancia_estrutural(recomendacao_atual: dict | None, recomendacao_nova: dict | None) -> dict:
    """Único sinal de concordância calculado hoje, sem IA: os dois
    modelos recomendam uma pergunta ao cliente agora, ou não?
    `recomendacao_nova=None` (o modelo novo falhou/não rodou) sempre
    retorna `concordancia=None` — erro nunca é discordância."""
    if recomendacao_nova is None:
        return {"concordancia": None, "atual_e_pergunta": None, "novo_e_pergunta": None}

    atual_e_pergunta = (recomendacao_atual or {}).get("type") == "question"
    novo_e_pergunta = bool((recomendacao_nova.get("next_best_question") or "").strip())
    return {
        "concordancia": atual_e_pergunta == novo_e_pergunta,
        "atual_e_pergunta": atual_e_pergunta,
        "novo_e_pergunta": novo_e_pergunta,
    }


def montar_registro_shadow(
    recomendacao_atual: dict | None,
    recomendacao_nova: dict | None,
    latency_ms: int | None,
    cost_usd: float | None,
    erro: str | None,
) -> dict:
    """Monta o registro completo de uma comparação Shadow Mode — pronto
    pra `api/database.py::criar_shadow_mode_comparison()` persistir.
    Nunca acessa banco ou chama IA."""
    concordancia = avaliar_concordancia_estrutural(recomendacao_atual, recomendacao_nova)
    return {
        "recomendacao_atual": recomendacao_atual or {},
        "recomendacao_nova": recomendacao_nova,
        "concordancia": concordancia["concordancia"],
        "atual_e_pergunta": concordancia["atual_e_pergunta"],
        "novo_e_pergunta": concordancia["novo_e_pergunta"],
        "latency_ms": latency_ms,
        "cost_usd": cost_usd,
        "erro": erro,
        "quality": dict(QUALITY_NAO_DISPONIVEL),
    }


def resumir_comparacoes(comparacoes: list[dict]) -> dict:
    """Agrega uma lista de comparações já persistidas (formato de
    `api/database.py::listar_shadow_mode_comparisons()`) nas métricas
    literais da Fase 23: agreement/disagreement (%), latency (média),
    errors (taxa), cost (total). `quality` continua gap explícito —
    agregado nenhum resolve a ausência do LLM-judge."""
    total = len(comparacoes)
    com_erro = [c for c in comparacoes if c.get("erro")]
    comparaveis = [c for c in comparacoes if c.get("concordancia") is not None]
    concordantes = [c for c in comparaveis if c["concordancia"] is True]
    latencias = [c["latency_ms"] for c in comparacoes if isinstance(c.get("latency_ms"), (int, float))]
    custos = [c["cost_usd"] for c in comparacoes if isinstance(c.get("cost_usd"), (int, float))]

    return {
        "total_comparacoes": total,
        "comparaveis": len(comparaveis),
        "agreement_rate": (len(concordantes) / len(comparaveis)) if comparaveis else None,
        "disagreement_rate": (1 - len(concordantes) / len(comparaveis)) if comparaveis else None,
        "error_rate": (len(com_erro) / total) if total else None,
        "latency_ms_media": (sum(latencias) / len(latencias)) if latencias else None,
        "cost_usd_total": round(sum(custos), 6) if custos else 0.0,
        "quality": dict(QUALITY_NAO_DISPONIVEL),
    }


# ── Tarefa C3 (docs/tasks-prompt-mestre-v2-restante.md) — avaliação ──
# Relatório completo do Shadow Mode para decidir se o Piloto (C6) pode
# começar. Os limites abaixo são PROPOSTA desta tarefa, não decisão: o
# prompt mestre só diz "só liberar após avaliação". Quem decide é o
# usuário, na C6.

# Mensagem do `_FALLBACK_NBA` de `agent/multiagente/orquestrador.py`:
# quando o modelo atual cai no fallback, ele não recomendou nada de
# verdade, então concordar ou discordar dele não diz nada.
MENSAGEM_FALLBACK_ATUAL = "Me conta um pouco mais sobre o que motivou voces a buscar uma solucao agora?"

# Features de IA que só rodam no caminho Shadow/Piloto (os extratores
# + o motor), em `agent/multiagente/orquestrador.py::_rodar_shadow_mode`.
FEATURES_CAMINHO_SHADOW = (
    "sales_reasoning.raciocinio",
    "objection.categoria_classificacao",
    "objection.causa_raiz_investigacao",
    "spin.extracao_fatos",
    "behavioral_signal.extracao",
    "buyer_motivation.extracao",
    "meddpicc.extracao",
    "sales_event.extracao",
)

PILOTO_MIN_COMPARAVEIS = 100
PILOTO_MIN_REUNIOES = 5
PILOTO_MAX_ERROR_RATE = 0.05
PILOTO_MAX_LATENCIA_P95_MS = 20000

_MAX_AMOSTRAS = 10


def _percentil(valores: list[float], p: float) -> float | None:
    """Percentil por posição mais próxima (sem interpolação) — basta para
    p50/p95 de latência, sem dependência nova."""
    if not valores:
        return None
    ordenados = sorted(valores)
    indice = max(0, min(len(ordenados) - 1, int(round(p * (len(ordenados) - 1)))))
    return ordenados[indice]


def _atual_e_fallback(comparacao: dict) -> bool:
    mensagem = ((comparacao.get("recomendacao_atual") or {}).get("message") or "").strip()
    return mensagem == MENSAGEM_FALLBACK_ATUAL


def _tipo_de_erro(erro: str) -> str:
    """`"TimeoutError: ..."` → `"TimeoutError"`. Agrupa sem depender do
    texto variável da mensagem."""
    return erro.split(":", 1)[0].strip()[:80] or "desconhecido"


def _amostra(comparacao: dict) -> dict:
    atual = comparacao.get("recomendacao_atual") or {}
    nova = comparacao.get("recomendacao_nova") or {}
    return {
        "id": comparacao.get("id"),
        "criado_em": comparacao.get("criado_em"),
        "meeting_id": comparacao.get("meeting_id"),
        "atual": {
            "type": atual.get("type"),
            "category": atual.get("category"),
            "message": atual.get("message"),
        },
        "nova": {
            "current_state": nova.get("current_state"),
            "recommended_framework": nova.get("recommended_framework"),
            "next_best_action": nova.get("next_best_action"),
            "next_best_question": nova.get("next_best_question"),
            "confidence": nova.get("confidence"),
        },
    }


def _resumo_por_chave(comparacoes: list[dict], chave) -> list[dict]:
    grupos: dict[str, list[dict]] = {}
    for c in comparacoes:
        grupos.setdefault(chave(c), []).append(c)
    linhas = []
    for valor, grupo in grupos.items():
        resumo = resumir_comparacoes(grupo)
        datas = sorted(c["criado_em"] for c in grupo if c.get("criado_em"))
        linhas.append({
            "chave": valor,
            "total": resumo["total_comparacoes"],
            "comparaveis": resumo["comparaveis"],
            "agreement_rate": resumo["agreement_rate"],
            "error_rate": resumo["error_rate"],
            "com_vendedor": sum(1 for c in grupo if c.get("usuario_id")),
            "primeira": datas[0] if datas else None,
            "ultima": datas[-1] if datas else None,
        })
    return sorted(linhas, key=lambda linha: linha["primeira"] or "")


def _avaliar_origem(comparacoes: list[dict]) -> dict:
    resumo = resumir_comparacoes(comparacoes)
    comparaveis = [c for c in comparacoes if c.get("concordancia") is not None]
    sem_fallback = [c for c in comparaveis if not _atual_e_fallback(c)]
    concordantes_sem_fallback = [c for c in sem_fallback if c["concordancia"] is True]
    latencias = [c["latency_ms"] for c in comparacoes if isinstance(c.get("latency_ms"), (int, float))]
    latencias_ok = [c["latency_ms"] for c in comparacoes
                    if not c.get("erro") and isinstance(c.get("latency_ms"), (int, float))]

    matriz = {"ambos_pergunta": 0, "so_atual_pergunta": 0, "so_novo_pergunta": 0, "nenhum_pergunta": 0}
    for c in comparaveis:
        atual, novo = bool(c.get("atual_e_pergunta")), bool(c.get("novo_e_pergunta"))
        if atual and novo:
            matriz["ambos_pergunta"] += 1
        elif atual:
            matriz["so_atual_pergunta"] += 1
        elif novo:
            matriz["so_novo_pergunta"] += 1
        else:
            matriz["nenhum_pergunta"] += 1

    erros_por_tipo: dict[str, int] = {}
    for c in comparacoes:
        if c.get("erro"):
            tipo = _tipo_de_erro(c["erro"])
            erros_por_tipo[tipo] = erros_por_tipo.get(tipo, 0) + 1

    frameworks: dict[str, int] = {}
    for c in comparacoes:
        framework = (c.get("recomendacao_nova") or {}).get("recommended_framework")
        if framework:
            frameworks[str(framework)] = frameworks.get(str(framework), 0) + 1

    discordantes = [c for c in sem_fallback if c["concordancia"] is False]
    concordantes = [c for c in sem_fallback if c["concordancia"] is True]
    return {
        **resumo,
        "atual_em_fallback": len(comparaveis) - len(sem_fallback),
        "agreement_rate_sem_fallback": (
            len(concordantes_sem_fallback) / len(sem_fallback) if sem_fallback else None
        ),
        "matriz_pergunta": matriz,
        "latency_ms_p50": _percentil(latencias, 0.50),
        "latency_ms_p95": _percentil(latencias, 0.95),
        "latency_ms_p95_sem_erro": _percentil(latencias_ok, 0.95),
        "erros_por_tipo": dict(sorted(erros_por_tipo.items(), key=lambda kv: -kv[1])),
        "recommended_framework": dict(sorted(frameworks.items(), key=lambda kv: -kv[1])),
        "reunioes": len({c.get("meeting_id") for c in comparacoes if c.get("meeting_id")}),
        "com_vendedor": sum(1 for c in comparacoes if c.get("usuario_id")),
        "por_reuniao": _resumo_por_chave(comparacoes, lambda c: c.get("meeting_id") or "(sem meeting_id)"),
        "por_dia": _resumo_por_chave(comparacoes, lambda c: (c.get("criado_em") or "")[:10] or "(sem data)"),
        "amostras_discordancia": [_amostra(c) for c in discordantes[:_MAX_AMOSTRAS]],
        "amostras_concordancia": [_amostra(c) for c in concordantes[:_MAX_AMOSTRAS]],
    }


def _resumir_custo(custos_por_feature: list[dict] | None) -> dict:
    """`custos_por_feature` no formato de `api/database.py::custos_resumo()
    ["por_feature"]` (`feature`, `eventos`, `total_usd`)."""
    linhas = custos_por_feature or []
    shadow = [linha for linha in linhas if linha.get("feature") in FEATURES_CAMINHO_SHADOW]
    tempo_real = [linha for linha in linhas if str(linha.get("feature", "")).startswith("realtime.")]
    total_shadow = round(sum(linha.get("total_usd") or 0.0 for linha in shadow), 6)
    total_tempo_real = round(sum(linha.get("total_usd") or 0.0 for linha in tempo_real), 6)
    return {
        "caminho_shadow_usd": total_shadow,
        "caminho_shadow_chamadas": sum(linha.get("eventos") or 0 for linha in shadow),
        "caminho_shadow_por_feature": sorted(shadow, key=lambda linha: -(linha.get("total_usd") or 0.0)),
        "tempo_real_usd": total_tempo_real,
        "shadow_sobre_tempo_real": (total_shadow / total_tempo_real) if total_tempo_real else None,
    }


def _prontidao_piloto(shadow: dict) -> dict:
    """Checagens objetivas para a C6. `quality` sempre bloqueia enquanto
    não houver LLM-judge ou rotulagem humana (C4) — concordância
    estrutural (pergunta sim/não) não diz se a recomendação é boa."""
    checagens = [
        {
            "criterio": f"amostra >= {PILOTO_MIN_COMPARAVEIS} comparações comparáveis",
            "valor": shadow["comparaveis"],
            "ok": shadow["comparaveis"] >= PILOTO_MIN_COMPARAVEIS,
        },
        {
            "criterio": f"reuniões distintas >= {PILOTO_MIN_REUNIOES}",
            "valor": shadow["reunioes"],
            "ok": shadow["reunioes"] >= PILOTO_MIN_REUNIOES,
        },
        {
            "criterio": f"error_rate <= {PILOTO_MAX_ERROR_RATE:.0%}",
            "valor": shadow["error_rate"],
            "ok": shadow["error_rate"] is not None and shadow["error_rate"] <= PILOTO_MAX_ERROR_RATE,
        },
        {
            "criterio": f"latência p95 <= {PILOTO_MAX_LATENCIA_P95_MS} ms",
            "valor": shadow["latency_ms_p95"],
            "ok": shadow["latency_ms_p95"] is not None and shadow["latency_ms_p95"] <= PILOTO_MAX_LATENCIA_P95_MS,
        },
        {
            "criterio": "quality medida (LLM-judge ou rótulo humano, C4)",
            "valor": None,
            "ok": False,
        },
    ]
    return {
        "pode_iniciar": all(c["ok"] for c in checagens),
        "checagens": checagens,
        "observacao": (
            "Limites são proposta da C3; a decisão de iniciar o Piloto é "
            "do usuário (C6). Concordância estrutural só compara 'é pergunta "
            "ou não', nunca o conteúdo."
        ),
    }


def avaliar_shadow_mode(comparacoes: list[dict], custos_por_feature: list[dict] | None = None) -> dict:
    """Tarefa C3: relatório completo do Shadow Mode, separado por origem
    (`shadow` x `piloto` nunca se misturam), com latência p50/p95, erros
    por tipo, matriz pergunta x pergunta, recortes por reunião e por dia,
    amostras, custo real do caminho Shadow (todas as chamadas, não só a
    do motor) e checagens de prontidão do Piloto. Função pura."""
    por_origem: dict[str, list[dict]] = {}
    for c in comparacoes:
        por_origem.setdefault(c.get("origem") or "shadow", []).append(c)

    avaliacao = {origem: _avaliar_origem(grupo) for origem, grupo in sorted(por_origem.items())}
    shadow = avaliacao.get("shadow") or _avaliar_origem([])
    return {
        "por_origem": avaliacao,
        "custo": _resumir_custo(custos_por_feature),
        "prontidao_piloto": _prontidao_piloto(shadow),
    }
