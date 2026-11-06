"""T5.4 — Closer Agent: score, maturidade, próximos passos, timing de fechamento."""

import json
from pathlib import Path

from agent.contexto_ia_rules import MAX_CHARS_EVENTOS, MAX_CHARS_SCORES, dividir_prompt, limitar_diagnostico, limitar_lista
from agent.multiagente.claude_fallback import chamar_ia_com_fallback_claude
from api import ai_features

_PROMPT = Path(__file__).parent.parent / "prompt_templates" / "multiagente_closer.txt"


async def analisar_closer(
    transcricao_parcial: str,
    resumo_vivo: str,
    historico_scores: list,
    diagnostico_atual: dict,
    usuario_id: str | None = None,
    meeting_id: str | None = None,
) -> dict:
    template = _PROMPT.read_text(encoding="utf-8")
    prompt = (
        template
        .replace("{transcricao_parcial}", transcricao_parcial)
        .replace("{resumo_vivo}", resumo_vivo)
        .replace("{historico_scores}", json.dumps(limitar_lista(historico_scores, MAX_CHARS_SCORES), ensure_ascii=False))
        .replace("{diagnostico_atual}", json.dumps(limitar_diagnostico(diagnostico_atual), ensure_ascii=False))
    )
    regras, dados = dividir_prompt(prompt)
    return await chamar_ia_com_fallback_claude(
        "Voce e um especialista em fechamento consultivo. Responda SEMPRE em JSON valido, sem texto antes ou depois." + "\n\n" + regras,
        dados,
        usuario_id,
        feature=ai_features.REALTIME_CLOSER,
        meeting_id=meeting_id,
    )
