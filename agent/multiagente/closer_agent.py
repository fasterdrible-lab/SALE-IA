"""T5.4 — Closer Agent: score, maturidade, próximos passos, timing de fechamento."""

import json
from pathlib import Path

from agent.multiagente.claude_fallback import chamar_ia_com_fallback_claude

_PROMPT = Path(__file__).parent.parent / "prompt_templates" / "multiagente_closer.txt"


async def analisar_closer(
    transcricao_parcial: str,
    resumo_vivo: str,
    historico_scores: list,
    diagnostico_atual: dict,
    usuario_id: str | None = None,
) -> dict:
    template = _PROMPT.read_text(encoding="utf-8")
    prompt = (
        template
        .replace("{transcricao_parcial}", transcricao_parcial)
        .replace("{resumo_vivo}", resumo_vivo)
        .replace("{historico_scores}", json.dumps(historico_scores or [], ensure_ascii=False))
        .replace("{diagnostico_atual}", json.dumps(diagnostico_atual or {}, ensure_ascii=False))
    )
    return await chamar_ia_com_fallback_claude(
        "Voce e um especialista em fechamento consultivo. Responda SEMPRE em JSON valido, sem texto antes ou depois.",
        prompt,
        usuario_id,
    )
