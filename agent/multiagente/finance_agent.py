"""T5.3 — Finance Agent: capacidade financeira, potencial de compra, objeção de preço."""

import json
from pathlib import Path

from agent.multiagente.claude_fallback import chamar_ia_com_fallback_claude

_PROMPT = Path(__file__).parent.parent / "prompt_templates" / "multiagente_finance.txt"


async def analisar_finance(
    transcricao_parcial: str,
    historico: str,
    mapa_financeiro: dict,
    usuario_id: str | None = None,
) -> dict:
    template = _PROMPT.read_text(encoding="utf-8")
    prompt = (
        template
        .replace("{transcricao_parcial}", transcricao_parcial)
        .replace("{historico}", historico)
        .replace("{mapa_financeiro}", json.dumps(mapa_financeiro or {}, ensure_ascii=False))
    )
    return await chamar_ia_com_fallback_claude(
        "Voce e um especialista em diagnostico financeiro de vendas. Responda SEMPRE em JSON valido, sem texto antes ou depois.",
        prompt,
        usuario_id,
    )
