"""
Modulo 1 - Agente em Tempo Real.

Recebe fragmentos da transcricao a cada ciclo da extensao e retorna dicas ao
vendedor usando o roteador central de IA com fallback automatico.
"""

import json
from pathlib import Path

from agent.base_conhecimento import buscar_contexto_similar
from api.ai_router import chamar_ia_async

PROMPT_PATH = Path(__file__).parent / "prompt_templates" / "agente_tempo_real.txt"


def _carregar_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


async def analisar_fragmento(
    transcricao_parcial: str,
    historico: str = "Inicio da conversa",
    perfil_disc_atual: str = "Ainda nao identificado",
    mapa_financeiro: dict = None,
    resumo_vivo: str = "Resumo ainda nao disponivel",
    diagnostico_atual: dict = None,
    historico_scores: list = None,
    eventos: list = None,
) -> dict:
    """
    Analisa um fragmento da transcricao em tempo real e retorna insights em JSON.
    """
    template = _carregar_prompt()

    mapa_financeiro_str = (
        json.dumps(mapa_financeiro, ensure_ascii=False, indent=2)
        if mapa_financeiro
        else "Nenhum dado financeiro coletado ainda"
    )
    resumo_vivo_str = resumo_vivo or "Resumo ainda nao disponivel"
    diagnostico_atual_str = (
        json.dumps(diagnostico_atual, ensure_ascii=False, indent=2)
        if diagnostico_atual
        else "Nenhum diagnostico persistido ainda"
    )
    historico_scores_str = (
        json.dumps(historico_scores, ensure_ascii=False, indent=2)
        if historico_scores
        else "[]"
    )
    eventos_str = (
        json.dumps(eventos, ensure_ascii=False, indent=2)
        if eventos
        else "[]"
    )

    texto_para_busca = f"{transcricao_parcial} {historico}"
    contexto_base = await buscar_contexto_similar(texto_para_busca, top_k=3)
    contexto_str = f"\n\n{contexto_base}" if contexto_base else ""

    prompt = (
        template
        .replace("{transcricao_parcial}", transcricao_parcial)
        .replace("{historico}", historico)
        .replace("{perfil_disc_atual}", perfil_disc_atual)
        .replace("{mapa_financeiro}", mapa_financeiro_str)
        .replace("{resumo_vivo}", resumo_vivo_str)
        .replace("{diagnostico_atual}", diagnostico_atual_str)
        .replace("{historico_scores}", historico_scores_str)
        .replace("{eventos}", eventos_str)
    ) + contexto_str

    return await chamar_ia_async(
        (
            "Voce e um especialista em vendas consultivas respondendo SEMPRE "
            "em JSON valido, sem texto adicional antes ou depois do JSON."
        ),
        prompt,
    )
