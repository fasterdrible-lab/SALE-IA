"""
Modulo de suporte em tempo real ao vendedor do SALEIA.

Usa o template em `agent/prompt_templates/suporte_venda.txt` e o roteador
central de IA para manter fallback automatico entre provedores de chat.
"""

from pathlib import Path
from typing import Dict

from api.ai_router import chamar_ia_async

_TEMPLATE_PATH = Path(__file__).parent / "prompt_templates" / "suporte_venda.txt"


def _carregar_template() -> str:
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


def _normalizar_resposta(resultado: dict) -> Dict[str, str]:
    defaults = {
        "proxima_fala": "Aguarde o contexto evoluir",
        "gatilho_emocional": "Nao identificado",
        "objecao_e_resposta": "Nenhuma objecao detectada",
        "melhor_oferta": "Avaliar conforme contexto",
    }

    normalizado = {}
    for chave, valor_padrao in defaults.items():
        valor = resultado.get(chave) or valor_padrao
        normalizado[chave] = str(valor)

    for chave in ("_provedor_ia", "_modelo_ia", "_tentativas_ia"):
        if chave in resultado:
            normalizado[chave] = resultado[chave]

    return normalizado


async def gerar_suporte_venda(
    perfil_cliente: str,
    fase: str,
    ultima_fala: str,
    historico: str,
) -> Dict[str, str]:
    template = _carregar_template()
    prompt = (
        template
        .replace("{perfil_cliente}", perfil_cliente)
        .replace("{fase}", fase)
        .replace("{ultima_fala}", ultima_fala)
        .replace("{historico}", historico)
    )

    resultado = await chamar_ia_async(
        (
            "Voce e um especialista em vendas consultivas ao vivo. "
            "Responda apenas em JSON valido com as chaves: proxima_fala, "
            "gatilho_emocional, objecao_e_resposta e melhor_oferta."
        ),
        prompt,
    )
    return _normalizar_resposta(resultado)
