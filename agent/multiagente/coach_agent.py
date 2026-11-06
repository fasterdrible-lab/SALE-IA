"""T5.1 — Coach Agent: condução, rapport, próxima ação, estágio da conversa."""

import json
from pathlib import Path

from agent.contexto_ia_rules import MAX_CHARS_EVENTOS, MAX_CHARS_SCORES, dividir_prompt, limitar_diagnostico, limitar_lista
from agent.multiagente.claude_fallback import chamar_ia_com_fallback_claude
from api import ai_features

_PROMPT = Path(__file__).parent.parent / "prompt_templates" / "multiagente_coach.txt"


async def analisar_coach(
    transcricao_parcial: str,
    historico: str,
    resumo_vivo: str,
    diagnostico_atual: dict,
    eventos: list,
    skill_context: str = "",
    client_context: str = "",
    usuario_id: str | None = None,
    meeting_id: str | None = None,
) -> dict:
    template = _PROMPT.read_text(encoding="utf-8")
    prompt = (
        template
        .replace("{transcricao_parcial}", transcricao_parcial)
        .replace("{historico}", historico)
        .replace("{resumo_vivo}", resumo_vivo)
        .replace("{diagnostico_atual}", json.dumps(limitar_diagnostico(diagnostico_atual), ensure_ascii=False))
        .replace("{eventos}", json.dumps(limitar_lista(eventos, MAX_CHARS_EVENTOS), ensure_ascii=False))
        .replace("{client_context}", client_context or "")
        .replace("{skill_context}", skill_context or "")
    )
    regras, dados = dividir_prompt(prompt)
    return await chamar_ia_com_fallback_claude(
        "Voce e um Coach de vendas consultivas. Responda SEMPRE em JSON valido, sem texto antes ou depois." + "\n\n" + regras,
        dados,
        usuario_id,
        feature=ai_features.REALTIME_COACH,
        meeting_id=meeting_id,
    )
