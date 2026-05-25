"""
Agente de recapitulacao completa do SALEIA.

Usa o roteador central de IA para manter fallback automatico entre provedores.
"""

import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from api.ai_router import chamar_ia_async

RECAP_TRIGGER_PHRASES = (
    "vamos recapitular",
    "deixa eu ver se entendi",
    "pelo que voce me falou",
    "foi isso que eu colhi",
    "so para confirmar",
)
RECAP_TRIGGER_COOLDOWN_SECONDS = int(os.getenv("SALEIA_RECAP_TRIGGER_COOLDOWN_SECONDS", "180"))
PROMPT_LIVE_RECAP_PATH = Path(__file__).parent / "prompt_templates" / "recapitulacao_viva.txt"

PROMPT_RECAPITULACAO = """Voce e um coach de vendas especializado que analisa reunioes de consultoria.

Com base na transcricao da reuniao e nos diagnosticos abaixo, gere uma recapitulacao
completa e acionavel para o vendedor.

DADOS DO DIAGNOSTICO FINANCEIRO:
{financeiro}

DADOS DO PERFIL DISC:
{disc}

Gere a recapitulacao completa em JSON com este formato:
{
  "resumo_executivo": "Resumo em 3 linhas do que aconteceu na reuniao e proximo passo",
  "recapitulacao_emocional": {
    "estado_emocional": "Como o cliente estava emocionalmente durante a reuniao",
    "momentos_chave": ["Momento 1", "Momento 2", "Momento 3"],
    "nivel_confianca": "alto/medio/baixo",
    "motivacao_principal": "O que realmente motiva este cliente a agir"
  },
  "recapitulacao_estrategica": {
    "situacao_atual": "Situacao atual do cliente em detalhes",
    "dor_principal": "Principal dor ou problema que quer resolver",
    "expectativa_crescimento": "O que espera conquistar com o produto",
    "capacidade_decisao": "alto/medio/baixo",
    "prazo_decisao": "Estimativa de quando vai decidir"
  },
  "produto_recomendado": {
    "nome": "Nome do produto recomendado",
    "valor": "Valor do produto",
    "justificativa": "Por que este produto e o ideal para este cliente especifico",
    "forma_pagamento_ideal": "Forma de pagamento mais adequada"
  },
  "perfil_comportamental": {
    "perfil_disc": "D/I/S/C",
    "como_abordar": "Como abordar nas proximas interacoes",
    "linguagem_ideal": "Que tipo de linguagem e tom usar",
    "o_que_evitar": "O que nao fazer com este cliente"
  },
  "top_objecoes": [
    {"objecao": "Objecao mais provavel", "resposta_sugerida": "Como responder"},
    {"objecao": "Segunda objecao", "resposta_sugerida": "Como responder"},
    {"objecao": "Terceira objecao", "resposta_sugerida": "Como responder"}
  ],
  "sinal_oculto": "O que o vendedor provavelmente nao percebeu",
  "proximos_passos": [
    "Acao especifica para as proximas 24 horas",
    "Acao para os proximos 3 dias",
    "Acao para o fechamento"
  ],
  "script_follow_up": "Mensagem sugerida para WhatsApp"
}

TRANSCRICAO DA REUNIAO:
{transcript}
"""

PROMPT_DICAS_TEMPO_REAL = """Voce e um coach de vendas especializado que acompanha reunioes em tempo real.

Analise a transcricao parcial abaixo e gere dicas imediatas para o vendedor.
Foque em sinais que o vendedor provavelmente nao percebeu.

Responda em JSON:
{{
  "dica_principal": "A dica mais importante neste momento",
  "perfil_disc_parcial": "D/I/S/C",
  "nivel_engajamento": "alto/medio/baixo",
  "sinais_positivos": ["Sinal positivo 1", "Sinal positivo 2"],
  "alertas": ["Alerta que o vendedor deve observar"],
  "proxima_pergunta_sugerida": "Qual pergunta fazer agora para avancar na venda",
  "produto_provavel": "base/intermediario/completo",
  "tom_recomendado": "Como o vendedor deve se comunicar agora"
}}

TRANSCRICAO PARCIAL:
{transcript}
"""


def _carregar_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalizar_texto(texto: str) -> str:
    texto = texto or ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", texto).strip().lower()


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def detectRecapTrigger(texto: str, memoria: dict | None = None, cooldown_seconds: int | None = None) -> dict:
    """Detecta deixas verbais de recapitulação e respeita cooldown."""
    texto_normalizado = _normalizar_texto(texto)
    cooldown = cooldown_seconds if cooldown_seconds is not None else RECAP_TRIGGER_COOLDOWN_SECONDS
    memoria = memoria or {}
    agora = datetime.now(timezone.utc)

    last_recap = _parse_iso_datetime(memoria.get("last_recap_trigger_at"))
    if last_recap:
        elapsed = (agora - last_recap).total_seconds()
        if elapsed < cooldown:
            return {
                "triggered": False,
                "reason": "cooldown",
                "cooldown_seconds": cooldown,
                "remaining_cooldown_seconds": int(max(0, cooldown - elapsed)),
                "trigger_phrase": None,
                "confidence": "high",
                "fact_or_inference": "fact",
                "timestamp": agora.isoformat(),
            }

    for phrase in RECAP_TRIGGER_PHRASES:
        if _normalizar_texto(phrase) in texto_normalizado:
            return {
                "triggered": True,
                "reason": "matched_phrase",
                "cooldown_seconds": cooldown,
                "remaining_cooldown_seconds": 0,
                "trigger_phrase": phrase,
                "confidence": "high",
                "fact_or_inference": "fact",
                "timestamp": agora.isoformat(),
            }

    return {
        "triggered": False,
        "reason": "no_match",
        "cooldown_seconds": cooldown,
        "remaining_cooldown_seconds": 0,
        "trigger_phrase": None,
        "confidence": "low",
        "fact_or_inference": "inference",
        "timestamp": agora.isoformat(),
    }


def _fallback_live_recap(
    transcricao_recente: str,
    resumo_vivo: str,
    diagnostico_atual: dict | None,
    score_history: list | None,
    key_moments: list | None,
    events: list | None,
    trigger: dict | None,
) -> dict:
    diagnostico_atual = diagnostico_atual or {}
    objecao = diagnostico_atual.get("objecao_detectada") or {}
    mapa_financeiro = diagnostico_atual.get("mapa_financeiro") or {}
    temperatura = diagnostico_atual.get("temperatura") or {}
    score_history = score_history or []
    key_moments = key_moments or []
    events = events or []

    dor = ""
    if isinstance(objecao, dict) and objecao.get("objecao"):
        dor = objecao.get("objecao")
    elif resumo_vivo:
        dor = resumo_vivo.split(".")[0][:120]

    impacto = temperatura.get("sinal") or diagnostico_atual.get("alerta_urgente") or "Precisamos organizar a recapitulação para avançar."
    objetivo = diagnostico_atual.get("proxima_fala") or diagnostico_atual.get("proxima_acao") or "Alinhar o próximo passo."
    objecoes = []
    if isinstance(objecao, dict) and objecao.get("objecao"):
        objecoes.append(objecao.get("objecao"))

    oportunidades = []
    produto = mapa_financeiro.get("produto_indicado") or {}
    if isinstance(produto, dict) and produto.get("nome"):
        oportunidades.append(f"Adequar a proposta para {produto['nome']}.")
    if score_history:
        oportunidades.append("O score historico indica evolucao recente.")
    if any(item.get("type") == "buying_signal" for item in (key_moments + events)):
        oportunidades.append("Ha sinal claro de interesse de compra.")

    pergunta = diagnostico_atual.get("proxima_pergunta") or "Essa leitura faz sentido para voce?"
    fala = f"A principal prioridade que apareceu agora e {dor or 'alinhar a dor principal'}."
    perguntas_faltantes = []
    if not diagnostico_atual.get("mapa_financeiro"):
        perguntas_faltantes.append("Validar faixa de investimento")
    if not objecoes:
        perguntas_faltantes.append("Confirmar a principal objeção")
    if not diagnostico_atual.get("proxima_acao"):
        perguntas_faltantes.append("Fechar o próximo passo")

    return {
        "status": "fallback",
        "trigger": trigger or {},
        "resumo_curto": resumo_vivo[:240],
        "texto_falavel": fala,
        "pergunta_confirmacao": pergunta,
        "perguntas_faltantes": perguntas_faltantes,
        "dica_vendedor": "Use a recapitulação para validar o entendimento e conduzir ao próximo passo.",
        "mapa_mental": {
            "dor_principal": dor or "Nao identificado",
            "impacto": impacto,
            "objetivo": objetivo,
            "objecoes": objecoes or ["Nao identificada"],
            "oportunidades": oportunidades or ["Buscar mais clareza antes de avançar"],
            "proximo_passo": diagnostico_atual.get("proxima_acao") or "Confirmar alinhamento e avançar",
        },
    }


async def generateLiveRecapMindMap(
    transcricao_recente: str,
    resumo_vivo: str,
    diagnostico_atual: dict | None,
    score_history: list | None,
    key_moments: list | None,
    events: list | None,
    trigger: dict | None,
) -> dict:
    """Gera uma recapitulação guiada com mapa mental e fala pronta."""
    prompt_template = _carregar_prompt(PROMPT_LIVE_RECAP_PATH)
    payload = (
        prompt_template
        .replace("{transcricao_recente}", transcricao_recente or "")
        .replace("{resumo_vivo}", resumo_vivo or "")
        .replace("{diagnostico_atual}", json.dumps(diagnostico_atual or {}, ensure_ascii=False, indent=2))
        .replace("{historico_scores}", json.dumps(score_history or [], ensure_ascii=False, indent=2))
        .replace("{key_moments}", json.dumps(key_moments or [], ensure_ascii=False, indent=2))
        .replace("{events}", json.dumps(events or [], ensure_ascii=False, indent=2))
        .replace("{trigger}", json.dumps(trigger or {}, ensure_ascii=False, indent=2))
    )

    system_prompt = (
        "Voce e um coach de vendas que cria recapitulação guiada em JSON valido. "
        "Nao invente fatos, nao repita a transcricao inteira e responda apenas com JSON. "
        "Nao use as frases: deixa eu ver se entendi, pelo que voce me falou, "
        "foi isso que eu colhi ou so para confirmar."
    )

    try:
        resposta = await chamar_ia_async(system_prompt, payload)
    except Exception:
        return _fallback_live_recap(
            transcricao_recente=transcricao_recente,
            resumo_vivo=resumo_vivo,
            diagnostico_atual=diagnostico_atual,
            score_history=score_history,
            key_moments=key_moments,
            events=events,
            trigger=trigger,
        )

    if isinstance(resposta, str):
        try:
            resposta = json.loads(resposta)
        except Exception:
            resposta = {}
    if not isinstance(resposta, dict):
        resposta = {}

    mapa_mental = resposta.get("mapa_mental") or resposta.get("mind_map") or {}
    if not isinstance(mapa_mental, dict):
        mapa_mental = {}

    perguntas_faltantes = resposta.get("perguntas_faltantes") or resposta.get("perguntas_em_aberto") or []
    if not isinstance(perguntas_faltantes, list):
        perguntas_faltantes = [perguntas_faltantes] if perguntas_faltantes else []

    texto_falavel = (
        resposta.get("texto_falavel")
        or resposta.get("fala_pronta")
        or resposta.get("proxima_fala")
        or resposta.get("resumo_executivo")
        or ""
    )
    pergunta_confirmacao = (
        resposta.get("pergunta_confirmacao")
        or resposta.get("pergunta_sugerida")
        or resposta.get("pergunta")
        or ""
    )
    dica_vendedor = resposta.get("dica_vendedor") or resposta.get("dica_principal") or ""

    if not texto_falavel:
        texto_falavel = _fallback_live_recap(
            transcricao_recente=transcricao_recente,
            resumo_vivo=resumo_vivo,
            diagnostico_atual=diagnostico_atual,
            score_history=score_history,
            key_moments=key_moments,
            events=events,
            trigger=trigger,
        )["texto_falavel"]

    if not pergunta_confirmacao:
        pergunta_confirmacao = _fallback_live_recap(
            transcricao_recente=transcricao_recente,
            resumo_vivo=resumo_vivo,
            diagnostico_atual=diagnostico_atual,
            score_history=score_history,
            key_moments=key_moments,
            events=events,
            trigger=trigger,
        )["pergunta_confirmacao"]

    if not dica_vendedor:
        dica_vendedor = _fallback_live_recap(
            transcricao_recente=transcricao_recente,
            resumo_vivo=resumo_vivo,
            diagnostico_atual=diagnostico_atual,
            score_history=score_history,
            key_moments=key_moments,
            events=events,
            trigger=trigger,
        )["dica_vendedor"]

    return {
        "status": resposta.get("status") or "generated",
        "trigger": trigger or {},
        "resumo_curto": resposta.get("resumo_curto") or resposta.get("resumo_executivo") or resumo_vivo[:240],
        "texto_falavel": texto_falavel,
        "pergunta_confirmacao": pergunta_confirmacao,
        "perguntas_faltantes": perguntas_faltantes,
        "dica_vendedor": dica_vendedor,
        "mapa_mental": mapa_mental,
        "raw_response": resposta,
    }


async def recapitulacao_completa(transcript: str, financeiro: dict, disc: dict) -> dict:
    prompt = (
        PROMPT_RECAPITULACAO
        .replace("{transcript}", transcript)
        .replace("{financeiro}", json.dumps(financeiro, ensure_ascii=False, indent=2))
        .replace("{disc}", json.dumps(disc, ensure_ascii=False, indent=2))
    )

    return await chamar_ia_async(
        (
            "Voce e um coach de vendas de alto nivel especializado em vendas consultivas. "
            "Sua recapitulacao deve ser precisa, acionavel e focada no fechamento. "
            "Responda sempre em JSON valido, sem markdown."
        ),
        prompt,
    )


async def dicas_tempo_real(transcript: str) -> dict:
    prompt = PROMPT_DICAS_TEMPO_REAL.format(transcript=transcript)

    return await chamar_ia_async(
        (
            "Voce e um coach de vendas especializado em vendas consultivas ao vivo. "
            "Gere dicas praticas e imediatas. Responda em JSON valido, sem markdown."
        ),
        prompt,
    )
