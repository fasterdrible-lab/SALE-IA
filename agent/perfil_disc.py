"""
Módulo 3 — Perfil DISC + Gestão de Objeções
Identifica o perfil comportamental DISC do cliente a partir da transcrição
e gera um plano personalizado de objeções com respostas prontas.

Perfis DISC:
  D (Dominante):   direto, quer resultados, decidido
  I (Influente):   emotivo, empolgado, relacional
  S (Estável):     cauteloso, precisa de segurança, leal
  C (Consciente):  analítico, quer dados, detalhista
"""

import json
import os
from pathlib import Path

from openai import AsyncOpenAI

# Caminho para o template de prompt
PROMPT_PATH = Path(__file__).parent / "prompt_templates" / "perfil_disc.txt"


def _get_client() -> AsyncOpenAI:
    """Cria o cliente OpenAI com a chave definida na variável de ambiente."""
    return AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def _carregar_prompt() -> str:
    """Carrega o template de prompt do arquivo .txt."""
    return PROMPT_PATH.read_text(encoding="utf-8")


async def identificar_perfil_disc(transcricao: str) -> dict:
    """
    Analisa a transcrição e identifica o perfil DISC dominante do cliente.
    Gera as top 3 objeções previstas com respostas personalizadas para o perfil.

    Parâmetros:
        transcricao: Transcrição completa ou parcial da reunião

    Retorno:
        Dicionário com perfil primário/secundário, objeções previstas e frase de fechamento
    """
    template = _carregar_prompt()
    prompt = template.format(transcricao=transcricao)

    resposta = await _get_client().chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "Você é especialista em DISC respondendo SEMPRE em JSON válido, "
                    "sem texto adicional antes ou depois do JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    conteudo = resposta.choices[0].message.content
    return json.loads(conteudo)
