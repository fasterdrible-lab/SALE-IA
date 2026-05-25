"""Diagnostico final da reuniao do SALEIA.

Usa a memoria persistida da reuniao para sintetizar o estado final do cliente
e orientar o follow-up de forma estruturada.
"""

import json
from pathlib import Path

from api.ai_router import chamar_ia_async

PROMPT_PATH = Path(__file__).parent / "prompt_templates" / "diagnostico_final.txt"


def _carregar_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _parse_json(value, fallback):
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return fallback
    return fallback


def _limitar_texto(texto: str, limite: int = 12000) -> str:
    texto = texto or ""
    if len(texto) <= limite:
        return texto
    return texto[:limite]


def _normalizar_lista(valor) -> list:
    if not valor:
        return []
    if isinstance(valor, list):
        return [item for item in valor if item not in (None, "", [])]
    return [valor]


def _score_mais_recente(score_history: list | None) -> dict:
    score_history = score_history or []
    for item in reversed(score_history):
        if isinstance(item, dict) and item.get("valor") is not None:
            return item
    return {}


def _inferir_nivel_risco(score_valor: int | float | None, sinais_alerta: list, objecoes: list) -> str:
    if score_valor is not None and score_valor < 40:
        return "alto"
    if sinais_alerta or len(objecoes) >= 2:
        return "medio"
    return "baixo"


def _inferir_intencao(score_valor: int | float | None, sinais_compra: list, sinais_alerta: list) -> str:
    if score_valor is not None and score_valor >= 70:
        return "alta"
    if score_valor is not None and score_valor >= 45:
        return "media"
    if sinais_compra and not sinais_alerta:
        return "media"
    return "baixa"


def _fallback_final_diagnosis(
    accumulated_summary: str,
    current_diagnosis: dict | str | None,
    key_moments: list | None,
    score_history: list | None,
    transcript_full: str,
    events: list | None,
    diagnostico_financeiro: dict | None,
    perfil_disc: dict | None,
    recapitulacao: dict | None,
) -> dict:
    current_diagnosis = _parse_json(current_diagnosis, {})
    key_moments = key_moments or []
    score_history = score_history or []
    events = events or []
    diagnostico_financeiro = diagnostico_financeiro or {}
    perfil_disc = perfil_disc or {}
    recapitulacao = recapitulacao or {}

    latest_score = _score_mais_recente(score_history)
    score_valor = latest_score.get("valor")

    buying_signals = [
        item.get("quote") or item.get("type")
        for item in key_moments + events
        if isinstance(item, dict) and item.get("type") in {"buying_signal", "closing_signal"}
    ]
    alerta_signals = [
        item.get("quote") or item.get("type")
        for item in key_moments + events
        if isinstance(item, dict) and item.get("type") in {"pricing_resistance", "objection_detected", "competitor_mention"}
    ]
    objecoes = [
        item.get("quote") or item.get("type")
        for item in key_moments + events
        if isinstance(item, dict) and item.get("type") in {"pricing_resistance", "objection_detected"}
    ]

    mapa_financeiro = {}
    if isinstance(current_diagnosis, dict):
        mapa_financeiro = current_diagnosis.get("mapa_financeiro") or {}
    if not isinstance(mapa_financeiro, dict):
        mapa_financeiro = {}

    produto_indicado = mapa_financeiro.get("produto_indicado")
    if not isinstance(produto_indicado, dict):
        produto_indicado = (
            diagnostico_financeiro.get("produto_recomendado")
            or diagnostico_financeiro.get("produto_indicado")
            or {}
        )
        if not isinstance(produto_indicado, dict):
            produto_indicado = {}

    nivel_intencao = _inferir_intencao(score_valor, buying_signals, alerta_signals)
    nivel_risco = _inferir_nivel_risco(score_valor, alerta_signals, objecoes)

    perfil_local = (
        perfil_disc.get("tipo")
        or (current_diagnosis.get("perfil_disc") or {}).get("tipo")
        or (diagnostico_financeiro.get("perfil_disc") or {}).get("tipo")
        or "S"
    )
    confianca_perfil = (
        perfil_disc.get("confianca")
        or (current_diagnosis.get("perfil_disc") or {}).get("confianca")
        or "media"
    )

    produto_nome = produto_indicado.get("nome") or mapa_financeiro.get("produto_indicado_nome") or "Nao definido"
    produto_valor = produto_indicado.get("valor") or diagnostico_financeiro.get("produto_recomendado_valor") or "Nao definido"
    capacidade_nivel = "media"
    faturamento = mapa_financeiro.get("faturamento_mensal") or diagnostico_financeiro.get("faturamento_mensal")
    if produto_nome.lower().find("completo") >= 0:
        capacidade_nivel = "alta"
    elif produto_nome.lower().find("base") >= 0:
        capacidade_nivel = "baixa"

    dores = _normalizar_lista(
        current_diagnosis.get("dores")
        or current_diagnosis.get("pain_points")
        or [
            item.get("quote")
            for item in key_moments
            if isinstance(item, dict) and item.get("type") in {"pricing_resistance", "objection_detected"}
        ]
    )
    if not dores and recapitulacao.get("recapitulacao_estrategica"):
        dores = _normalizar_lista(recapitulacao["recapitulacao_estrategica"].get("dores_identificadas"))

    proximos_passos = _normalizar_lista(
        current_diagnosis.get("proximos_passos")
        or recapitulacao.get("proximos_passos")
        or [
            "Confirmar a dor principal e o impacto real.",
            "Validar capacidade financeira e decisor final.",
            "Agendar o proximo passo ou follow-up.",
        ]
    )

    follow_up = (
        recapitulacao.get("script_follow_up")
        or current_diagnosis.get("mensagem_follow_up")
        or "Oi, fiquei com alguns pontos importantes da nossa conversa e queria validar o melhor proximo passo."
    )

    resumo_executivo = (
        recapitulacao.get("resumo_executivo")
        or current_diagnosis.get("resumo_executivo")
        or accumulated_summary
        or "Resumo executivo nao disponivel."
    )

    diagnostico_cliente = (
        current_diagnosis.get("diagnostico_cliente")
        or recapitulacao.get("diagnostico_cliente")
        or (
            f"Cliente com intencao {nivel_intencao}, perfil {perfil_local}, "
            f"capacidade {capacidade_nivel} e risco {nivel_risco}."
        )
    )

    sinais_compra = _normalizar_lista(
        current_diagnosis.get("sinais_compra")
        or buying_signals
        or recapitulacao.get("sinais_compra")
    )
    sinais_alerta = _normalizar_lista(
        current_diagnosis.get("sinais_alerta")
        or alerta_signals
        or recapitulacao.get("sinais_alerta")
    )

    return {
        "status": "fallback",
        "resumo_executivo": resumo_executivo,
        "diagnostico_cliente": diagnostico_cliente,
        "dores": dores,
        "objecoes": _normalizar_lista(objecoes),
        "intencao_compra": {
            "nivel": nivel_intencao,
            "evidencias": _normalizar_lista(sinais_compra or buying_signals),
            "justificativa": (
                f"Score mais recente em {score_valor}" if score_valor is not None else "Score nao informado"
            ),
        },
        "perfil_disc": {
            "tipo": perfil_local,
            "confianca": confianca_perfil,
            "evidencia": (
                perfil_disc.get("evidencia")
                or (current_diagnosis.get("perfil_disc") or {}).get("evidencia")
                or "Leitura inferida a partir da memoria da reuniao"
            ),
            "como_abordar": (
                perfil_disc.get("como_abordar")
                or (current_diagnosis.get("perfil_disc") or {}).get("como_abordar")
                or "Manter abordagem clara, objetiva e alinhada ao contexto do cliente."
            ),
        },
        "capacidade_financeira": {
            "nivel": capacidade_nivel,
            "evidencias": _normalizar_lista(
                [
                    faturamento,
                    mapa_financeiro.get("capacidade_investimento"),
                    diagnostico_financeiro.get("capacidade_investimento"),
                    diagnostico_financeiro.get("sinais_financeiros"),
                ]
            ),
            "produto_indicado": {
                "nome": produto_nome,
                "valor": produto_valor,
                "justificativa": (
                    produto_indicado.get("justificativa")
                    or diagnostico_financeiro.get("justificativa_produto")
                    or "Inferido com base na memoria financeira e no contexto da reuniao."
                ),
            },
        },
        "risco_perda": {
            "nivel": nivel_risco,
            "motivos": _normalizar_lista(
                [
                    *sinais_alerta,
                    current_diagnosis.get("alerta_urgente"),
                    recapitulacao.get("sinal_oculto"),
                ]
            ),
        },
        "proximos_passos": proximos_passos,
        "mensagem_follow_up": follow_up,
        "score_final": {
            "valor": score_valor if score_valor is not None else 50,
            "justificativa": (
                latest_score.get("justificativa")
                or "Baseado no historico de score e nos eventos finais da reuniao."
            ),
        },
        "sinais_compra": _normalizar_lista(sinais_compra or buying_signals),
        "sinais_alerta": _normalizar_lista(sinais_alerta or alerta_signals),
        "oportunidades_nao_exploradas": _normalizar_lista(
            current_diagnosis.get("oportunidades_nao_exploradas")
            or recapitulacao.get("sinal_oculto")
            or []
        ),
        "transcript_usado": _limitar_texto(transcript_full, 12000),
    }


def _normalizar_diagnostico_final(resultado: dict | str | None) -> dict:
    if isinstance(resultado, str):
        try:
            resultado = json.loads(resultado)
        except Exception:
            resultado = {"raw_response": resultado}

    if not isinstance(resultado, dict):
        resultado = {}

    resultado["status"] = resultado.get("status") or "generated"
    resultado["resumo_executivo"] = resultado.get("resumo_executivo") or resultado.get("summary") or ""
    resultado["diagnostico_cliente"] = resultado.get("diagnostico_cliente") or resultado.get("diagnostico") or ""
    resultado["dores"] = _normalizar_lista(resultado.get("dores"))
    resultado["objecoes"] = _normalizar_lista(resultado.get("objecoes"))
    resultado["sinais_compra"] = _normalizar_lista(resultado.get("sinais_compra"))
    resultado["sinais_alerta"] = _normalizar_lista(resultado.get("sinais_alerta"))
    resultado["oportunidades_nao_exploradas"] = _normalizar_lista(resultado.get("oportunidades_nao_exploradas"))
    resultado["proximos_passos"] = _normalizar_lista(resultado.get("proximos_passos"))

    intencao = resultado.get("intencao_compra") or {}
    if not isinstance(intencao, dict):
        intencao = {"nivel": str(intencao), "evidencias": [], "justificativa": ""}
    intencao["nivel"] = intencao.get("nivel") or "media"
    intencao["evidencias"] = _normalizar_lista(intencao.get("evidencias"))
    intencao["justificativa"] = intencao.get("justificativa") or intencao.get("observacao") or ""
    resultado["intencao_compra"] = intencao

    perfil = resultado.get("perfil_disc") or {}
    if not isinstance(perfil, dict):
        perfil = {"tipo": str(perfil), "confianca": "media", "evidencia": "", "como_abordar": ""}
    perfil["tipo"] = perfil.get("tipo") or "S"
    perfil["confianca"] = perfil.get("confianca") or "media"
    perfil["evidencia"] = perfil.get("evidencia") or ""
    perfil["como_abordar"] = perfil.get("como_abordar") or ""
    resultado["perfil_disc"] = perfil

    capacidade = resultado.get("capacidade_financeira") or {}
    if not isinstance(capacidade, dict):
        capacidade = {"nivel": str(capacidade), "evidencias": [], "produto_indicado": {}}
    capacidade["nivel"] = capacidade.get("nivel") or "media"
    capacidade["evidencias"] = _normalizar_lista(capacidade.get("evidencias"))
    produto = capacidade.get("produto_indicado") or {}
    if not isinstance(produto, dict):
        produto = {"nome": str(produto), "valor": "", "justificativa": ""}
    produto["nome"] = produto.get("nome") or ""
    produto["valor"] = produto.get("valor") or ""
    produto["justificativa"] = produto.get("justificativa") or ""
    capacidade["produto_indicado"] = produto
    resultado["capacidade_financeira"] = capacidade

    risco = resultado.get("risco_perda") or {}
    if not isinstance(risco, dict):
        risco = {"nivel": str(risco), "motivos": []}
    risco["nivel"] = risco.get("nivel") or "medio"
    risco["motivos"] = _normalizar_lista(risco.get("motivos"))
    resultado["risco_perda"] = risco

    score = resultado.get("score_final") or {}
    if not isinstance(score, dict):
        score = {"valor": score, "justificativa": ""}
    try:
        score["valor"] = int(float(score.get("valor")))
    except Exception:
        score["valor"] = 50
    score["justificativa"] = score.get("justificativa") or ""
    resultado["score_final"] = score

    return resultado


async def generateFinalDiagnosis(
    accumulated_summary: str,
    current_diagnosis: dict | str | None,
    key_moments: list | None,
    score_history: list | None,
    transcript_full: str = "",
    events: list | None = None,
    diagnostico_financeiro: dict | None = None,
    perfil_disc: dict | None = None,
    recapitulacao: dict | None = None,
) -> dict:
    """Gera o diagnostico final completo da reuniao em JSON estruturado."""
    template = _carregar_prompt()
    prompt = (
        template
        .replace("{accumulated_summary}", accumulated_summary or "")
        .replace("{current_diagnosis}", json.dumps(current_diagnosis or {}, ensure_ascii=False, indent=2))
        .replace("{key_moments}", json.dumps(key_moments or [], ensure_ascii=False, indent=2))
        .replace("{score_history}", json.dumps(score_history or [], ensure_ascii=False, indent=2))
        .replace("{events}", json.dumps(events or [], ensure_ascii=False, indent=2))
        .replace("{transcript_full}", _limitar_texto(transcript_full or "", 12000))
        .replace("{diagnostico_financeiro}", json.dumps(diagnostico_financeiro or {}, ensure_ascii=False, indent=2))
        .replace("{perfil_disc}", json.dumps(perfil_disc or {}, ensure_ascii=False, indent=2))
        .replace("{recapitulacao}", json.dumps(recapitulacao or {}, ensure_ascii=False, indent=2))
    )

    system_prompt = (
        "Voce e um analista comercial de fechamento. Responda apenas com JSON valido, "
        "sem markdown e sem texto adicional."
    )

    try:
        resposta = await chamar_ia_async(system_prompt, prompt)
    except Exception:
        return _fallback_final_diagnosis(
            accumulated_summary=accumulated_summary,
            current_diagnosis=current_diagnosis,
            key_moments=key_moments,
            score_history=score_history,
            transcript_full=transcript_full,
            events=events,
            diagnostico_financeiro=diagnostico_financeiro,
            perfil_disc=perfil_disc,
            recapitulacao=recapitulacao,
        )

    resposta = _normalizar_diagnostico_final(resposta)
    if not resposta.get("resumo_executivo"):
        resposta["resumo_executivo"] = accumulated_summary or ""
    if not resposta.get("diagnostico_cliente"):
        resposta["diagnostico_cliente"] = _fallback_final_diagnosis(
            accumulated_summary=accumulated_summary,
            current_diagnosis=current_diagnosis,
            key_moments=key_moments,
            score_history=score_history,
            transcript_full=transcript_full,
            events=events,
            diagnostico_financeiro=diagnostico_financeiro,
            perfil_disc=perfil_disc,
            recapitulacao=recapitulacao,
        )["diagnostico_cliente"]

    return resposta
