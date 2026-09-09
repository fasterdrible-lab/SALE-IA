"""Big Five Agent — infere as 5 dimensoes de personalidade (Five-Factor
Model) do CLIENTE a partir do comportamento observado na conversa, sem
questionario. Mesma arquitetura do disc_agent.py (agente paralelo no
orquestrador multiagente); nunca recebe astrologia/signo como entrada —
garante por construcao que a camada simbolica nunca influencia esta
inferencia comportamental."""

import json
from pathlib import Path

from agent.multiagente.claude_fallback import chamar_ia_com_fallback_claude
from api import ai_features

_PROMPT = Path(__file__).parent.parent / "prompt_templates" / "multiagente_bigfive.txt"


async def analisar_bigfive(
    transcricao_parcial: str,
    historico: str,
    perfil_bigfive_atual: dict,
    diagnostico_atual: dict,
    usuario_id: str | None = None,
    meeting_id: str | None = None,
) -> dict:
    template = _PROMPT.read_text(encoding="utf-8")
    prompt = (
        template
        .replace("{transcricao_parcial}", transcricao_parcial)
        .replace("{historico}", historico)
        .replace("{perfil_bigfive_atual}", json.dumps(perfil_bigfive_atual or {}, ensure_ascii=False))
        .replace("{diagnostico_atual}", json.dumps(diagnostico_atual or {}, ensure_ascii=False))
    )
    return await chamar_ia_com_fallback_claude(
        "Voce e um especialista em inferencia comportamental de personalidade (Big Five). Responda SEMPRE em JSON valido, sem texto antes ou depois.",
        prompt,
        usuario_id,
        feature=ai_features.REALTIME_BIGFIVE,
        meeting_id=meeting_id,
    )
