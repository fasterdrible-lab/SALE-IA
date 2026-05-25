"""
Modulo 2 - Diagnostico Financeiro Automatico.

Extrai informacoes financeiras da transcricao usando o roteador central de IA
com fallback automatico entre provedores de chat.
"""

from pathlib import Path

from api.ai_router import chamar_ia_async

PROMPT_PATH = Path(__file__).parent / "prompt_templates" / "diagnostico_financeiro.txt"


def _carregar_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


async def extrair_diagnostico_financeiro(transcricao: str) -> dict:
    template = _carregar_prompt()
    prompt = template.replace("{transcricao}", transcricao)

    return await chamar_ia_async(
        (
            "Voce e um especialista financeiro. Responda SEMPRE em JSON valido, "
            "sem texto adicional antes ou depois do JSON."
        ),
        prompt,
    )
