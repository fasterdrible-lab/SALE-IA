"""
Módulo 1 — Agente em Tempo Real
Recebe fragmentos da transcrição a cada 60 segundos e retorna dicas ao vendedor
sobre o que ele ainda não percebeu durante a reunião com o cliente.
"""

import json
import os
from pathlib import Path

from openai import AsyncOpenAI

# Caminho para o template de prompt
PROMPT_PATH = Path(__file__).parent / "prompt_templates" / "agente_tempo_real.txt"


def _get_client() -> AsyncOpenAI:
    """Cria o cliente OpenAI com a chave definida na variável de ambiente."""
    return AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def _carregar_prompt() -> str:
    """Carrega o template de prompt do arquivo .txt."""
    return PROMPT_PATH.read_text(encoding="utf-8")


async def analisar_fragmento(
    transcricao_parcial: str,
    historico: str = "Início da conversa",
    perfil_disc_atual: str = "Ainda não identificado",
    mapa_financeiro: dict = None,
) -> dict:
    """
    Analisa um fragmento da transcrição em tempo real e retorna insights para o vendedor.

    Parâmetros:
        transcricao_parcial: Trecho mais recente da conversa (últimos 30-60 segundos)
        historico: Resumo do que foi discutido até agora
        perfil_disc_atual: Perfil DISC identificado nas análises anteriores
        mapa_financeiro: Mapa financeiro acumulado das análises anteriores

    Retorno:
        Dicionário com alertas, perfil DISC, mapa financeiro, temperatura e próxima fala
    """
    template = _carregar_prompt()

    mapa_financeiro_str = (
        json.dumps(mapa_financeiro, ensure_ascii=False, indent=2)
        if mapa_financeiro
        else "Nenhum dado financeiro coletado ainda"
    )

    # Preenche o template com os dados da conversa atual
    prompt = template.format(
        transcricao_parcial=transcricao_parcial,
        historico=historico,
        perfil_disc_atual=perfil_disc_atual,
        mapa_financeiro=mapa_financeiro_str,
    )

    resposta = await _get_client().chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "Você é um especialista em vendas consultivas respondendo SEMPRE "
                    "em JSON válido, sem texto adicional antes ou depois do JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,  # Baixo para respostas consistentes e factuais
        response_format={"type": "json_object"},
    )

    conteudo = resposta.choices[0].message.content
    return json.loads(conteudo)
