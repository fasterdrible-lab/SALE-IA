"""
Módulo 2 — Diagnóstico Financeiro Automático
Extrai automaticamente da transcrição todas as informações financeiras do cliente:
faturamento, salário CLT, limite de cartão, estoque, capacidade de investimento
e recomenda o produto ideal com base na tabela de preços.
"""

import json
import os
from pathlib import Path

from openai import AsyncOpenAI

# Caminho para o template de prompt
PROMPT_PATH = Path(__file__).parent / "prompt_templates" / "diagnostico_financeiro.txt"


def _get_client() -> AsyncOpenAI:
    """Cria o cliente OpenAI com a chave definida na variável de ambiente."""
    return AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def _carregar_prompt() -> str:
    """Carrega o template de prompt do arquivo .txt."""
    return PROMPT_PATH.read_text(encoding="utf-8")


async def extrair_diagnostico_financeiro(transcricao: str) -> dict:
    """
    Analisa a transcrição completa e extrai todas as informações financeiras do cliente.

    Tabela de produtos utilizada na recomendação:
      - Produto Base:         R$ 3.000 – R$ 4.000  (cliente com baixo faturamento ou estoque)
      - Produto Intermediário: R$ 15.984,00
      - Produto Completo:      R$ 29.892,00

    Parâmetros:
        transcricao: Transcrição completa ou parcial da reunião

    Retorno:
        Dicionário com perfil financeiro, produto recomendado e estratégia de pagamento
    """
    template = _carregar_prompt()
    prompt = template.format(transcricao=transcricao)

    resposta = await _get_client().chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "Você é um especialista financeiro respondendo SEMPRE em JSON válido, "
                    "sem texto adicional antes ou depois do JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,  # Muito baixo para extração precisa de dados
        response_format={"type": "json_object"},
    )

    conteudo = resposta.choices[0].message.content
    return json.loads(conteudo)
