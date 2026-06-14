"""T5.1 — Coach Agent: condução, rapport, próxima ação, estágio da conversa."""

import json
from pathlib import Path

from api.ai_router import chamar_ia_async

_PROMPT = Path(__file__).parent.parent / "prompt_templates" / "multiagente_coach.txt"


async def analisar_coach(
    transcricao_parcial: str,
    historico: str,
    resumo_vivo: str,
    diagnostico_atual: dict,
    eventos: list,
    skill_context: str = "",
    client_context: str = "",
) -> dict:
    template = _PROMPT.read_text(encoding="utf-8")
    prompt = (
        template
        .replace("{transcricao_parcial}", transcricao_parcial)
        .replace("{historico}", historico)
        .replace("{resumo_vivo}", resumo_vivo)
        .replace("{diagnostico_atual}", json.dumps(diagnostico_atual, ensure_ascii=False))
        .replace("{eventos}", json.dumps(eventos, ensure_ascii=False))
        .replace("{client_context}", client_context or "")
        .replace("{skill_context}", skill_context or "")
    )
    return await chamar_ia_async(
        "Voce e um Coach de vendas consultivas. Responda SEMPRE em JSON valido, sem texto antes ou depois.",
        prompt,
    )
