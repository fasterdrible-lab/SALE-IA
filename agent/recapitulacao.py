"""
Módulo 4 — Recapitulação Completa Automática
Substitui o processo manual de copiar a transcrição do Tactiq e jogar no Claude.
Gera automaticamente o relatório completo de vendas após a reunião.
"""

import os
from pathlib import Path

from openai import AsyncOpenAI

# Caminho para o template de prompt
PROMPT_PATH = Path(__file__).parent / "prompt_templates" / "recapitulacao_completa.txt"


def _get_client() -> AsyncOpenAI:
    """Cria o cliente OpenAI com a chave definida na variável de ambiente."""
    return AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def _carregar_prompt() -> str:
    """Carrega o template de prompt do arquivo .txt."""
    return PROMPT_PATH.read_text(encoding="utf-8")


async def gerar_recapitulacao_completa(
    transcricao: str,
    diagnostico_financeiro: dict,
    perfil_disc: dict,
) -> str:
    """
    Gera o relatório completo de vendas com base na transcrição e nos diagnósticos.

    Parâmetros:
        transcricao: Transcrição completa da reunião
        diagnostico_financeiro: Resultado do módulo diagnostico_financeiro
        perfil_disc: Resultado do módulo perfil_disc

    Retorno:
        String formatada com o relatório completo (emocional + estratégico + próximos passos)
    """
    import json

    template = _carregar_prompt()
    prompt = template.format(
        transcricao=transcricao,
        diagnostico_financeiro=json.dumps(diagnostico_financeiro, ensure_ascii=False, indent=2),
        perfil_disc=json.dumps(perfil_disc, ensure_ascii=False, indent=2),
    )

    resposta = await _get_client().chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "Você é o agente SALEIA. Gere relatórios de vendas completos e precisos "
                    "em português brasileiro. Seja específico, prático e orientado à ação."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.5,
        max_tokens=4096,
    )

    return resposta.choices[0].message.content
