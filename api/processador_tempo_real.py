"""
Módulo de Processamento em Tempo Real do SALEIA.

Implementa polling automático durante a reunião para fornecer
dicas ao painel do vendedor a cada 60 segundos.
"""

import logging
import os
import re
import json
from datetime import datetime, timezone
from typing import Optional

import httpx

# Padrões de ruído do Google Meet (ícones Material Icons capturados como texto)
_MEET_NOISE_RE = re.compile(
    r'^(arrow_downward|arrow_upward|expand_more|expand_less|close|mic|mic_off'
    r'|videocam|videocam_off|more_vert|chat|people|settings|call_end|thumb_up'
    r'|check|keyboard_arrow_\w+|Ir para o fim|Go to the end)\s*$',
    re.IGNORECASE | re.MULTILINE
)
# Prefixos de ícone concatenados com texto (ex: "arrow_downwardIr para o fim")
_MEET_NOISE_PREFIX_RE = re.compile(
    r'^(arrow_downward|arrow_upward|expand_more|expand_less|keyboard_arrow\w*|close|mic_off|videocam_off)',
    re.IGNORECASE
)


def _limpar_transcricao(texto: str) -> str:
    """Remove ruído de UI do Google Meet da transcrição."""
    if not texto:
        return texto
    linhas = [
        l for l in texto.splitlines()
        if not _MEET_NOISE_RE.match(l.strip())
        and not _MEET_NOISE_PREFIX_RE.match(l.strip())
    ]
    return '\n'.join(linhas)

# Configuração de logging
logger = logging.getLogger(__name__)

_MIN_NEW_CHARS = int(os.getenv("SALEIA_REALTIME_MIN_NEW_CHARS", "120"))

_FALLBACK_NBQ_QUESTION = "Me conta um pouco mais sobre o que motivou voces a buscar uma solucao agora?"

_FALLBACK_NBA: dict = {
    "type": "question",
    "category": "descoberta_dor",
    "title": "Descoberta Inicial",
    "message": _FALLBACK_NBQ_QUESTION,
    "objective": "Entender motivacao",
    "reason": "Contexto insuficiente para sugerir acao estrategica.",
    "expected_effect": "Abrir espaco para identificar a dor real",
    "risk_if_ignored": "A conversa pode nao avancar sem contexto do cliente.",
    "follow_up": None,
    "confidence": 0.5,
}

_FALLBACK_MATURITY: dict = {
    "total": 0,
    "dor_identificada": 0,
    "impacto_quantificado": 0,
    "urgencia_identificada": 0,
    "budget_identificado": 0,
    "decisores_mapeados": 0,
    "valor_verbalizado_cliente": 0,
    "proximo_passo_claro": 0,
}


def _fallback_next_best_action() -> dict:
    return dict(_FALLBACK_NBA)


def _fallback_next_best_question() -> dict:
    return {
        "question": _FALLBACK_NBQ_QUESTION,
        "category": "descoberta_dor",
        "objective": "Entender motivacao",
        "reason": "Contexto insuficiente para sugerir pergunta estrategica.",
        "expected_score_impact": "+5",
        "urgency_level": "low",
        "follow_up_question": None,
    }


def _nba_para_nbq(nba: dict) -> dict:
    """Cria alias next_best_question a partir de next_best_action para backward compat."""
    return {
        "question": nba.get("message") or _FALLBACK_NBQ_QUESTION,
        "category": nba.get("category") or "descoberta_dor",
        "objective": nba.get("objective") or "",
        "reason": nba.get("reason") or "",
        "expected_score_impact": "+10",
        "urgency_level": "high" if (nba.get("confidence") or 0) >= 0.8 else "medium",
        "follow_up_question": nba.get("follow_up"),
    }


_MIN_NEW_WORDS = int(os.getenv("SALEIA_REALTIME_MIN_NEW_WORDS", "18"))
_MIN_INTERVAL_SECONDS = int(os.getenv("SALEIA_REALTIME_MIN_INTERVAL_SECONDS", "35"))
_MAX_CONTEXT_CHARS = int(os.getenv("SALEIA_REALTIME_MAX_CONTEXT_CHARS", "6000"))

# Armazenamento em memória das transcrições parciais por reunião
# Em produção, substituir por Redis ou banco de dados
_cache_transcricoes: dict[str, dict] = {}


def _get_cache_reuniao(meeting_id: str) -> dict:
    """Retorna ou inicializa o cache de uma reunião."""
    if meeting_id not in _cache_transcricoes:
        _cache_transcricoes[meeting_id] = {
            "transcript": "",
            "ultima_atualizacao": None,
            "dicas": None,
            "mapa_financeiro": {},
        }
    return _cache_transcricoes[meeting_id]


def atualizar_transcript_parcial(meeting_id: str, transcript: str) -> None:
    """
    Atualiza a transcrição parcial de uma reunião em andamento.
    Chamado pelo webhook quando Tactiq envia atualizações parciais.
    """
    from datetime import datetime, timezone

    cache = _get_cache_reuniao(meeting_id)
    cache["transcript"] = transcript
    cache["ultima_atualizacao"] = datetime.now(timezone.utc).isoformat()
    logger.info(f"📝 Transcrição parcial atualizada para reunião {meeting_id}")


def limpar_cache_reuniao(meeting_id: str) -> None:
    """Remove a reunião do cache após o processamento final."""
    if meeting_id in _cache_transcricoes:
        del _cache_transcricoes[meeting_id]
        logger.info(f"🗑️ Cache da reunião {meeting_id} removido")


def _contar_palavras(texto: str) -> int:
    texto = (texto or "").strip()
    if not texto:
        return 0
    return len([p for p in re.split(r"\s+", texto) if p])


def _parse_iso_datetime(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _textos_minimos_suficientes(fragmento: str) -> bool:
    fragmento = (fragmento or "").strip()
    if not fragmento:
        return False
    return len(fragmento) >= _MIN_NEW_CHARS or _contar_palavras(fragmento) >= _MIN_NEW_WORDS


def _limitar_contexto_ia(texto: str) -> str:
    texto = (texto or "").strip()
    if len(texto) <= _MAX_CONTEXT_CHARS:
        return texto
    return texto[-_MAX_CONTEXT_CHARS:]


def _pode_chamar_ia(meeting_id: str, fragmento: str, memoria: Optional[dict]) -> tuple[bool, str]:
    if not _textos_minimos_suficientes(fragmento):
        return False, "texto_novo_insuficiente"

    if not memoria:
        return True, "primeira_analise"

    last_ai_at = _parse_iso_datetime(memoria.get("last_ai_at"))
    if not last_ai_at:
        return True, "sem_tempo_anterior"

    agora = datetime.now(timezone.utc)
    delta = (agora - last_ai_at).total_seconds()
    if delta < _MIN_INTERVAL_SECONDS:
        return False, f"intervalo_curto_{int(delta)}s"

    return True, "intervalo_ok"


def _extrair_ultima_analise_memoria(memoria: Optional[dict], cache: dict) -> dict:
    memoria = memoria or {}
    resposta = {}

    raw = memoria.get("current_diagnosis")
    if isinstance(raw, str) and raw.strip():
        try:
            resposta = json.loads(raw)
        except Exception:
            resposta = {}
    elif isinstance(raw, dict):
        resposta = dict(raw)

    if not isinstance(resposta, dict):
        resposta = {}

    resumo = memoria.get("accumulated_summary") or resposta.get("resumo_vivo") or resposta.get("recapitulacao")
    if resumo:
        resposta.setdefault("resumo_vivo", resumo)
        resposta.setdefault("recapitulacao", resumo)

    resposta.setdefault("status", "cached")
    resposta.setdefault("alerta_urgente", None)
    resposta.setdefault("dica_vendedor", resposta.get("dica_principal") or resposta.get("proxima_acao"))
    resposta.setdefault("proxima_pergunta", resposta.get("proxima_pergunta") or resposta.get("pergunta_sugerida"))
    resposta.setdefault("acao_recomendada", resposta.get("acao_recomendada") or resposta.get("proxima_acao"))
    resposta.setdefault("proxima_acao", resposta.get("proxima_acao") or resposta.get("acao_recomendada"))
    resposta.setdefault("proxima_fala", resposta.get("proxima_fala") or resposta.get("texto_falavel") or resposta.get("acao_recomendada"))
    resposta.setdefault("texto_falavel", resposta.get("texto_falavel") or resposta.get("proxima_fala"))
    resposta.setdefault("current_diagnosis", resposta.get("current_diagnosis") or {})
    resposta.setdefault("next_best_action", _fallback_next_best_action())
    resposta.setdefault("next_best_question", _nba_para_nbq(resposta["next_best_action"]))
    resposta.setdefault("conversation_stage", "abertura")
    resposta.setdefault("kare_type", "attain")
    resposta.setdefault("maturity_score", dict(_FALLBACK_MATURITY))

    if memoria.get("score_history"):
        score_history = memoria.get("score_history") or []
        resposta.setdefault("score_history", score_history)
        if not resposta.get("score_compra") and score_history:
            ultimo_score = score_history[-1]
            resposta["score_compra"] = {
                "valor": ultimo_score.get("valor"),
                "justificativa": ultimo_score.get("justificativa"),
            }

    if memoria.get("key_moments"):
        resposta.setdefault("key_moments", memoria.get("key_moments"))
    if memoria.get("events"):
        resposta.setdefault("eventos", memoria.get("events"))

    resposta["mapa_financeiro"] = dict(cache.get("mapa_financeiro") or {})
    resposta["historico_resumido"] = resumo or resposta.get("historico_resumido") or ""
    resposta.setdefault("perfil_disc", resposta.get("perfil_disc") or {})
    resposta.setdefault("temperatura", resposta.get("temperatura") or {})
    resposta.setdefault("objecao_detectada", resposta.get("objecao_detectada") or {})
    resposta.setdefault("dado_esquecido", resposta.get("dado_esquecido"))
    resposta.setdefault("score_compra", resposta.get("score_compra") or {"valor": None, "justificativa": None})
    resposta["analysis_status"] = "cached"
    resposta["analysis_reason"] = "using_persisted_memory"
    return resposta


async def buscar_transcript_tactiq(meeting_id: str) -> Optional[str]:
    """
    Busca a transcrição parcial mais recente via API do Tactiq.

    Nota: Disponível apenas em planos pagos do Tactiq.
    Se não disponível, retorna None e o sistema usa a transcrição do cache.

    Args:
        meeting_id: ID da reunião no Tactiq.

    Returns:
        Texto da transcrição parcial ou None se não disponível.
    """
    tactiq_api_key = os.getenv("TACTIQ_API_KEY")

    if not tactiq_api_key:
        logger.debug("TACTIQ_API_KEY não configurada. API em tempo real indisponível.")
        return None

    # Endpoint da API do Tactiq (verificar documentação do plano)
    url = f"https://api.tactiq.io/v1/meetings/{meeting_id}/transcript"
    headers = {"Authorization": f"Bearer {tactiq_api_key}"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resposta = await client.get(url, headers=headers)
            if resposta.status_code == 200:
                dados = resposta.json()
                return dados.get("transcript", "")
            elif resposta.status_code == 404:
                logger.debug(f"Reunião {meeting_id} não encontrada na API do Tactiq")
                return None
            else:
                logger.warning(
                    f"Erro ao buscar transcrição Tactiq: {resposta.status_code}"
                )
                return None
    except httpx.TimeoutException:
        logger.warning("Timeout ao buscar transcrição do Tactiq")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado ao acessar API do Tactiq: {e}")
        return None


def _normalizar_resposta_realtime(resultado: dict | str | None, memoria: Optional[dict], cache: dict) -> dict:
    if isinstance(resultado, str):
        try:
            resultado = json.loads(resultado)
        except Exception:
            resultado = {"raw_response": resultado}

    if not isinstance(resultado, dict):
        resultado = {}

    if resultado.get("recapitulacao") and not resultado.get("resumo_vivo"):
        resultado["resumo_vivo"] = resultado["recapitulacao"]
    if resultado.get("resumo_vivo") and not resultado.get("recapitulacao"):
        resultado["recapitulacao"] = resultado["resumo_vivo"]

    if not resultado.get("dica_vendedor"):
        resultado["dica_vendedor"] = resultado.get("dica_principal") or resultado.get("proxima_acao")
    if not resultado.get("proxima_acao"):
        resultado["proxima_acao"] = resultado.get("acao_recomendada") or resultado.get("dica_vendedor")
    if not resultado.get("acao_recomendada"):
        resultado["acao_recomendada"] = resultado.get("proxima_acao") or resultado.get("dica_vendedor")
    if not resultado.get("proxima_fala"):
        resultado["proxima_fala"] = (
            resultado.get("texto_falavel")
            or resultado.get("acao_recomendada")
            or resultado.get("dica_vendedor")
            or resultado.get("proxima_acao")
        )
    if not resultado.get("texto_falavel"):
        resultado["texto_falavel"] = resultado.get("proxima_fala")
    if not resultado.get("proxima_pergunta"):
        resultado["proxima_pergunta"] = resultado.get("pergunta_sugerida") or resultado.get("pergunta_confirmacao")

    # next_best_action — campo primário
    if not resultado.get("next_best_action") or not isinstance(resultado["next_best_action"], dict):
        resultado["next_best_action"] = _fallback_next_best_action()
    elif not resultado["next_best_action"].get("message"):
        resultado["next_best_action"]["message"] = _FALLBACK_NBQ_QUESTION
    # next_best_question — alias backward-compat gerado a partir do next_best_action
    resultado["next_best_question"] = _nba_para_nbq(resultado["next_best_action"])
    # novos campos
    resultado.setdefault("conversation_stage", "abertura")
    resultado.setdefault("kare_type", "attain")
    if not resultado.get("maturity_score") or not isinstance(resultado.get("maturity_score"), dict):
        resultado["maturity_score"] = dict(_FALLBACK_MATURITY)
    else:
        for k in _FALLBACK_MATURITY:
            resultado["maturity_score"].setdefault(k, 0)
        if not resultado["maturity_score"].get("total"):
            resultado["maturity_score"]["total"] = sum(
                v for k, v in resultado["maturity_score"].items() if k != "total"
            )

    if not resultado.get("current_diagnosis"):
        resultado["current_diagnosis"] = {
            "alerta_urgente": resultado.get("alerta_urgente"),
            "perfil_disc": resultado.get("perfil_disc"),
            "mapa_financeiro": resultado.get("mapa_financeiro"),
            "temperatura": resultado.get("temperatura"),
            "proxima_fala": resultado.get("proxima_fala"),
            "objecao_detectada": resultado.get("objecao_detectada"),
            "dado_esquecido": resultado.get("dado_esquecido"),
            "score_compra": resultado.get("score_compra"),
        }

    if memoria and memoria.get("score_history") and not resultado.get("score_history"):
        resultado["score_history"] = list(memoria.get("score_history") or [])
    if memoria and memoria.get("key_moments") and not resultado.get("key_moments"):
        resultado["key_moments"] = list(memoria.get("key_moments") or [])
    if memoria and memoria.get("events") and not resultado.get("eventos"):
        resultado["eventos"] = list(memoria.get("events") or [])
    if resultado.get("eventos") and not resultado.get("events"):
        resultado["events"] = list(resultado.get("eventos") or [])
    if resultado.get("events") and not resultado.get("eventos"):
        resultado["eventos"] = list(resultado.get("events") or [])

    mapa_merged = dict(cache.get("mapa_financeiro") or {})
    mapa_resultado = resultado.get("mapa_financeiro") or {}
    if isinstance(mapa_resultado, dict):
        for campo, valor in mapa_resultado.items():
            if campo == "produto_indicado":
                if isinstance(valor, dict):
                    mapa_merged.setdefault("produto_indicado", {})
                    for k, v in valor.items():
                        if v is not None and v != "":
                            mapa_merged["produto_indicado"][k] = v
                continue
            if valor is not None and valor != "":
                mapa_merged[campo] = valor
    resultado["mapa_financeiro"] = mapa_merged
    resultado["historico_resumido"] = resultado.get("resumo_vivo") or resultado.get("historico_resumido") or ""
    resultado.setdefault("perfil_disc", resultado.get("perfil_disc") or {})
    resultado.setdefault("temperatura", resultado.get("temperatura") or {})
    resultado.setdefault("objecao_detectada", resultado.get("objecao_detectada") or {})
    resultado.setdefault("dado_esquecido", resultado.get("dado_esquecido"))
    resultado.setdefault("score_compra", resultado.get("score_compra") or {"valor": None, "justificativa": None})
    return resultado


def _normalizar_recapitulacao_viva(recap: dict | str | None, trigger: dict | None) -> dict:
    if isinstance(recap, str):
        try:
            recap = json.loads(recap)
        except Exception:
            recap = {"raw_response": recap}

    if not isinstance(recap, dict):
        recap = {}

    mapa_mental = recap.get("mapa_mental") or recap.get("mind_map") or {}
    if not isinstance(mapa_mental, dict):
        mapa_mental = {}

    perguntas_faltantes = recap.get("perguntas_faltantes") or recap.get("perguntas_em_aberto") or []
    if not isinstance(perguntas_faltantes, list):
        perguntas_faltantes = [perguntas_faltantes] if perguntas_faltantes else []

    recap["mapa_mental"] = mapa_mental
    recap["texto_falavel"] = (
        recap.get("texto_falavel")
        or recap.get("fala_pronta")
        or recap.get("proxima_fala")
        or recap.get("resumo_executivo")
        or ""
    )
    recap["pergunta_confirmacao"] = (
        recap.get("pergunta_confirmacao")
        or recap.get("pergunta_sugerida")
        or recap.get("pergunta")
        or ""
    )
    recap["perguntas_faltantes"] = perguntas_faltantes
    recap["dica_vendedor"] = recap.get("dica_vendedor") or recap.get("dica_principal") or ""
    recap["resumo_curto"] = recap.get("resumo_curto") or recap.get("resumo_executivo") or ""
    recap["trigger"] = trigger or recap.get("trigger") or {}
    return recap


async def analyzeRealtimeMeeting(
    transcricao_parcial: str,
    historico: str = "",
    perfil_disc_atual: str = "",
    mapa_financeiro: dict = None,
    meeting_id: str = "default",
    transcricao_nova: str = "",
) -> dict:
    from api.database import (
        obter_meeting_memory,
        registrar_analise_meeting,
        registrar_transcricao_meeting,
    )

    cache = _get_cache_reuniao(meeting_id)

    if mapa_financeiro:
        for campo, valor in mapa_financeiro.items():
            if valor is not None and valor != "" and campo != "produto_indicado":
                cache["mapa_financeiro"][campo] = valor
        if isinstance(mapa_financeiro.get("produto_indicado"), dict):
            prod = mapa_financeiro["produto_indicado"]
            cache["mapa_financeiro"].setdefault("produto_indicado", {})
            for k, v in prod.items():
                if v is not None and v != "":
                    cache["mapa_financeiro"]["produto_indicado"][k] = v

    fragmento_para_memoria = _limpar_transcricao((transcricao_nova or transcricao_parcial or "").strip())
    if fragmento_para_memoria:
        try:
            registrar_transcricao_meeting(meeting_id, fragmento_para_memoria, substituir=False)
        except Exception as _e:
            logger.warning("[MeetingMemory] Nao foi possivel salvar transcript: %s", _e)

    memoria_atual = None
    try:
        memoria_atual = obter_meeting_memory(meeting_id)
    except Exception as _e:
        logger.warning("[MeetingMemory] Nao foi possivel carregar memoria: %s", _e)

    pode_chamar_ia, motivo = _pode_chamar_ia(meeting_id, fragmento_para_memoria, memoria_atual)
    if not pode_chamar_ia:
        resultado_capturado = _extrair_ultima_analise_memoria(memoria_atual, cache)
        resultado_capturado["analysis_status"] = "skipped"
        resultado_capturado["analysis_reason"] = motivo
        return resultado_capturado

    resumo_vivo = (memoria_atual or {}).get("accumulated_summary") or ""
    diagnostico_atual = {}
    if memoria_atual:
        raw_diagnostico = memoria_atual.get("current_diagnosis")
        if isinstance(raw_diagnostico, str) and raw_diagnostico.strip():
            try:
                diagnostico_atual = json.loads(raw_diagnostico)
            except Exception:
                diagnostico_atual = {}
        elif isinstance(raw_diagnostico, dict):
            diagnostico_atual = dict(raw_diagnostico)

    # Restaura mapa_financeiro do banco se este worker ainda não tem cache para a reunião.
    # Com 2 workers uvicorn, _cache_transcricoes é por-processo; se o fragmento anterior
    # foi atendido por outro worker, o mapa acumulado lá só existe no current_diagnosis do banco.
    if not cache["mapa_financeiro"] and isinstance(diagnostico_atual.get("mapa_financeiro"), dict):
        cache["mapa_financeiro"] = dict(diagnostico_atual["mapa_financeiro"])

    # Resolve skill e client context (injetados no multiagente)
    skill_context = ""
    try:
        from agent.skill_resolver import resolver_skill_context
        ultimo_score = 50.0
        ultimo_stage = "abertura"
        if memoria_atual:
            scores_hist = json.loads(memoria_atual.get("score_history_json") or "[]")
            if scores_hist:
                last = scores_hist[-1]
                ultimo_score = float(last.get("valor") or last.get("score") or 50)
            diag_raw = memoria_atual.get("current_diagnosis") or "{}"
            if isinstance(diag_raw, str):
                try:
                    diag_raw = json.loads(diag_raw)
                except Exception:
                    diag_raw = {}
            ultimo_stage = (diag_raw if isinstance(diag_raw, dict) else {}).get("conversation_stage") or "abertura"
        skill_context = resolver_skill_context(
            disc_profile=perfil_disc_atual or "",
            score=ultimo_score,
            conversation_stage=ultimo_stage,
        )
    except Exception as _se:
        logger.debug("[Skills] Nao foi possivel resolver skill: %s", _se)

    client_context = ""
    try:
        from agent.client_intelligence import buscar_resumo_cliente_para_reuniao
        client_context = buscar_resumo_cliente_para_reuniao(meeting_id)
    except Exception as _ce:
        logger.debug("[Clientes] Nao foi possivel buscar contexto do cliente: %s", _ce)

    try:
        from agent.multiagente.orquestrador import analisar_fragmento_multi
        resultado = await analisar_fragmento_multi(
            transcricao_parcial=_limitar_contexto_ia(transcricao_parcial),
            historico=_limitar_contexto_ia(historico or "Inicio da conversa"),
            perfil_disc_atual=perfil_disc_atual or "Ainda nao identificado",
            mapa_financeiro=cache["mapa_financeiro"] if cache["mapa_financeiro"] else None,
            resumo_vivo=resumo_vivo or "Resumo ainda nao disponivel",
            diagnostico_atual=diagnostico_atual or {},
            historico_scores=(memoria_atual or {}).get("score_history") or [],
            eventos=(memoria_atual or {}).get("events") or [],
            skill_context=skill_context,
            client_context=client_context,
        )
    except Exception as _e:
        logger.exception("[TempoReal] Falha ao analisar fragmento: %s", _e)
        fallback = _extrair_ultima_analise_memoria(memoria_atual, cache)
        fallback["analysis_status"] = "error"
        fallback["analysis_reason"] = f"ai_error_{type(_e).__name__}"
        return fallback

    resultado = _normalizar_resposta_realtime(resultado, memoria_atual, cache)

    trigger_recap = None
    try:
        from agent.recapitulacao import detectRecapTrigger, generateLiveRecapMindMap

        trigger_recap = detectRecapTrigger(fragmento_para_memoria, memoria_atual)
        if trigger_recap.get("triggered"):
            contexto_recap = {
                "alerta_urgente": resultado.get("alerta_urgente"),
                "perfil_disc": resultado.get("perfil_disc"),
                "mapa_financeiro": resultado.get("mapa_financeiro"),
                "temperatura": resultado.get("temperatura"),
                "proxima_fala": resultado.get("proxima_fala"),
                "proxima_acao": resultado.get("proxima_acao"),
                "objecao_detectada": resultado.get("objecao_detectada"),
                "dado_esquecido": resultado.get("dado_esquecido"),
            }
            recap_viva = await generateLiveRecapMindMap(
                transcricao_recente=fragmento_para_memoria,
                resumo_vivo=resultado.get("resumo_vivo") or resumo_vivo or "",
                diagnostico_atual=contexto_recap,
                score_history=resultado.get("score_history") or (memoria_atual or {}).get("score_history") or [],
                key_moments=resultado.get("key_moments") or (memoria_atual or {}).get("key_moments") or [],
                events=resultado.get("eventos") or resultado.get("events") or (memoria_atual or {}).get("events") or [],
                trigger=trigger_recap,
            )
            resultado["recapitulacao_viva"] = _normalizar_recapitulacao_viva(recap_viva, trigger_recap)
            resultado["live_recap"] = resultado["recapitulacao_viva"]
            if resultado["recapitulacao_viva"].get("texto_falavel"):
                resultado.setdefault("texto_falavel", resultado["recapitulacao_viva"]["texto_falavel"])
            if resultado["recapitulacao_viva"].get("pergunta_confirmacao"):
                resultado.setdefault("pergunta_confirmacao", resultado["recapitulacao_viva"]["pergunta_confirmacao"])
            if resultado["recapitulacao_viva"].get("dica_vendedor"):
                resultado.setdefault("dica_vendedor_recap", resultado["recapitulacao_viva"]["dica_vendedor"])
            if resultado["recapitulacao_viva"].get("mapa_mental"):
                resultado.setdefault("mapa_mental_recap", resultado["recapitulacao_viva"]["mapa_mental"])
            evento_recap = {
                "type": "recap_trigger",
                "quote": trigger_recap.get("trigger_phrase"),
                "speaker": "cliente",
                "timestamp": trigger_recap.get("timestamp"),
                "importance": "high",
                "confidence": trigger_recap.get("confidence", "high"),
                "fact_or_inference": trigger_recap.get("fact_or_inference", "fact"),
                "source": "detected",
            }
            eventos_atual = list(resultado.get("eventos") or resultado.get("events") or [])
            key_moments_atual = list(resultado.get("key_moments") or [])
            eventos_atual.append(evento_recap)
            key_moments_atual.append(dict(evento_recap))
            resultado["eventos"] = eventos_atual
            resultado["events"] = list(eventos_atual)
            resultado["key_moments"] = key_moments_atual
            resultado["recap_trigger"] = trigger_recap
    except Exception as _e:
        logger.warning("[TempoReal] Nao foi possivel gerar recapitulacao viva: %s", _e)

    # T7: Adiciona next_best_question como key_moment para aparecer no relatório
    nbq = resultado.get("next_best_question") or {}
    if nbq.get("question") and nbq["question"] != _FALLBACK_NBQ_QUESTION:
        nbq_moment = {
            "type": "next_best_question",
            "quote": nbq["question"],
            "speaker": "vendedor",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "importance": "high" if nbq.get("urgency_level") == "high" else "medium",
            "confidence": "high",
            "fact_or_inference": "inference",
            "category": nbq.get("category"),
            "objective": nbq.get("objective"),
            "reason": nbq.get("reason"),
            "expected_score_impact": nbq.get("expected_score_impact"),
        }
        key_moments_atual = list(resultado.get("key_moments") or [])
        key_moments_atual.append(nbq_moment)
        resultado["key_moments"] = key_moments_atual

    try:
        from agent.sessao_manager import salvar_analise

        salvar_analise(meeting_id, _limpar_transcricao(transcricao_parcial), resultado)
    except Exception as _e:
        logger.warning("[Sessoes] Nao foi possivel salvar sessao: %s", _e)

    try:
        registrar_analise_meeting(meeting_id, resultado)
    except Exception as _e:
        logger.warning("[MeetingMemory] Nao foi possivel registrar analise: %s", _e)

    novo_mapa = resultado.get("mapa_financeiro") or {}
    for campo, valor in novo_mapa.items():
        if campo == "produto_indicado":
            continue
        if valor is not None and valor != "":
            cache["mapa_financeiro"][campo] = valor
    if isinstance(novo_mapa.get("produto_indicado"), dict):
        prod = novo_mapa["produto_indicado"]
        cache["mapa_financeiro"].setdefault("produto_indicado", {})
        for k, v in prod.items():
            if v is not None and v != "":
                cache["mapa_financeiro"]["produto_indicado"][k] = v

    resultado["mapa_financeiro"] = dict(cache["mapa_financeiro"])
    resultado["analysis_status"] = "updated"
    resultado["analysis_reason"] = motivo
    return resultado


processar_fragmento_tempo_real = analyzeRealtimeMeeting


async def processar_status_reuniao(meeting_id: str) -> dict:
    """
    Processa o status atual de uma reunião em andamento.
    Retorna dicas para o painel do vendedor.

    Fluxo:
    1. Tenta buscar transcrição parcial via API do Tactiq
    2. Se não disponível, usa transcrição do cache (colada manualmente)
    3. Processa com IA e retorna dicas
    4. Se nenhuma transcrição disponível, retorna instrução para colar manualmente

    Args:
        meeting_id: Identificador único da reunião.

    Returns:
        Dicionário com status e dicas para o vendedor.
    """
    from agent.recapitulacao import dicas_tempo_real

    # Tenta buscar via API do Tactiq
    transcript_tactiq = await buscar_transcript_tactiq(meeting_id)

    # Fallback: usa cache local
    cache = _get_cache_reuniao(meeting_id)
    transcript = transcript_tactiq or cache.get("transcript", "")

    # Sem transcrição disponível
    if not transcript or len(transcript.strip()) < 100:
        return {
            "meeting_id": meeting_id,
            "status": "aguardando_transcricao",
            "api_tactiq_disponivel": transcript_tactiq is not None,
            "instrucao": (
                "Cole a transcrição parcial do Tactiq neste campo para receber dicas em tempo real."
            ),
            "dicas": None,
            "ultima_atualizacao": cache.get("ultima_atualizacao"),
        }

    # Processa com IA para gerar dicas
    try:
        dicas = await dicas_tempo_real(transcript)
        cache["dicas"] = dicas

        return {
            "meeting_id": meeting_id,
            "status": "em_andamento",
            "api_tactiq_disponivel": transcript_tactiq is not None,
            "dicas": dicas,
            "tamanho_transcript": len(transcript),
            "ultima_atualizacao": cache.get("ultima_atualizacao"),
        }
    except Exception as e:
        logger.error(f"Erro ao processar dicas em tempo real: {e}")
        return {
            "meeting_id": meeting_id,
            "status": "erro_processamento",
            "api_tactiq_disponivel": transcript_tactiq is not None,
            "erro": "Erro ao processar transcrição. Tente novamente.",
            "dicas": cache.get("dicas"),  # Retorna última dica válida se houver
        }
