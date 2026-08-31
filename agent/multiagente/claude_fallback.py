"""Fallback do tempo real para a conta Claude do vendedor.

Quando os 4 provedores centrais (DeepSeek/OpenAI/Anthropic/Gemini) se
esgotam, `chamar_ia`/`chamar_ia_async` (api/ai_router.py) levanta
HTTPException(503). Se o vendedor logado na extensão tiver uma conta
Claude conectada (piloto Claude Account Mode), tenta essa conta antes de
desistir — em vez de deixar o orquestrador degradar silenciosamente para
dados de fallback/cache (agent/multiagente/orquestrador.py::_safe()).
"""

import logging

from fastapi import HTTPException

from api.ai_router import chamar_ia_async

logger = logging.getLogger(__name__)


async def chamar_ia_com_fallback_claude(
    system_prompt: str,
    user_content: str,
    usuario_id: str | None,
    *,
    feature: str,
    meeting_id: str | None = None,
) -> dict:
    try:
        return await chamar_ia_async(system_prompt, user_content, feature=feature, meeting_id=meeting_id, usuario_id=usuario_id)
    except HTTPException as exc:
        if exc.status_code != 503 or not usuario_id:
            raise

        # Import tardio: agent.claude_account importa api.ai_router.
        # (_extract_json) no topo do arquivo — um import no topo deste
        # módulo criaria um ciclo import.
        from agent.claude_account import claude_account_executor, claude_pilot_habilitado
        from api.database import obter_claude_connection, registrar_evento_uso_ia

        if not claude_pilot_habilitado():
            raise

        conexao = obter_claude_connection(usuario_id)
        if not conexao or conexao["status"] != "ativo" or not conexao["oauth_token_encrypted"]:
            raise

        try:
            resultado = await claude_account_executor.execute(
                usuario_id=usuario_id,
                prompt=f"{system_prompt}\n\n{user_content}",
                timeout=45.0,
            )
        except Exception as fallback_exc:
            logger.warning(
                "[ClaudeFallback] Fallback tambem falhou para usuario_id=%s: %s",
                usuario_id, fallback_exc,
            )
            raise exc from fallback_exc

        resultado.setdefault("_provedor_ia", "claude_account")

        # Cost Intelligence Fase 1: o SDK do Claude Agent nao expõe contagem
        # de tokens de forma simples (so custo agregado) — input/output ficam
        # em 0, limitacao conhecida e documentada.
        try:
            registrar_evento_uso_ia(
                feature=feature,
                provider="claude_account",
                model=None,
                input_tokens=0,
                output_tokens=0,
                usage_source=resultado.get("_usage_source_ia", "provider"),
                cost_usd=resultado.get("_custo_real_usd", 0.0),
                success=True,
                fallback_used=True,
                meeting_id=meeting_id,
                usuario_id=usuario_id,
            )
        except Exception as registro_exc:
            logger.warning("[ClaudeFallback] Falha ao registrar evento de uso: %s", registro_exc)

        return resultado
