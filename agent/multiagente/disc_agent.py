"""T5.2 — DISC Agent: perfil comportamental, KARE, temperatura emocional."""

import json
from pathlib import Path

from api.ai_router import chamar_ia_async

_PROMPT = Path(__file__).parent.parent / "prompt_templates" / "multiagente_disc.txt"


async def analisar_disc(
    transcricao_parcial: str,
    historico: str,
    perfil_disc_atual: str,
    diagnostico_atual: dict,
) -> dict:
    template = _PROMPT.read_text(encoding="utf-8")
    prompt = (
        template
        .replace("{transcricao_parcial}", transcricao_parcial)
        .replace("{historico}", historico)
        .replace("{perfil_disc_atual}", perfil_disc_atual)
        .replace("{diagnostico_atual}", json.dumps(diagnostico_atual, ensure_ascii=False))
    )
    return await chamar_ia_async(
        "Voce e um especialista em perfil comportamental DISC. Responda SEMPRE em JSON valido, sem texto antes ou depois.",
        prompt,
    )
