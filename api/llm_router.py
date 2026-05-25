"""
Compatibility wrapper for legacy LLM calls.

New code should use `api.ai_router.chamar_ia` or `chamar_ia_async` directly.
This wrapper keeps the old `chamar_llm(...) -> str` contract while routing
through the backend-owned fallback layer. It intentionally ignores per-request
API keys so secrets stay only in server-side environment variables.
"""

import json
import logging

from api.ai_router import chamar_ia_async

logger = logging.getLogger("saleia.ai.legacy")


async def chamar_llm(prompt: str, model: str = "", provider: str = "", api_key: str = None) -> str:
    if api_key:
        logger.warning("Ignoring per-request api_key in legacy chamar_llm; use backend env vars.")

    system_prompt = (
        "Responda ao usuario em JSON valido, sem markdown, no formato: "
        '{"resposta": "texto da resposta"}.'
    )
    resultado = await chamar_ia_async(system_prompt, prompt)
    resposta = resultado.get("resposta")
    if resposta is not None:
        return str(resposta)
    return json.dumps(resultado, ensure_ascii=False)
