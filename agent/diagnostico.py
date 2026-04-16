"""
Agente de Diagnóstico Financeiro do SALEIA.

Analisa a transcrição da reunião e extrai informações financeiras do cliente
para recomendar o produto mais adequado.
"""

import os
from openai import AsyncOpenAI


def _get_cliente_openai() -> AsyncOpenAI:
    """Retorna o cliente OpenAI inicializado com a chave da variável de ambiente."""
    return AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Critério de recomendação de produto com base na capacidade financeira
PRODUTOS = {
    "base": {
        "nome": "Produto Base",
        "valor": "R$ 3.000 - R$ 4.000",
        "descricao": "Ideal para quem fatura pouco, está começando ou tem renda CLT baixa",
    },
    "intermediario": {
        "nome": "Produto Intermediário",
        "valor": "R$ 15.984,00",
        "descricao": "Para quem tem capacidade financeira média e quer escalar",
    },
    "completo": {
        "nome": "Produto Completo",
        "valor": "R$ 29.892,00",
        "descricao": "Para quem tem boa capacidade financeira e quer resultado máximo",
    },
}

PROMPT_DIAGNOSTICO = """Você é um especialista em diagnóstico financeiro de clientes para vendas consultivas.

Analise a transcrição abaixo e extraia as seguintes informações:

1. FATURAMENTO MENSAL: Quanto o cliente fatura ou ganha por mês (estimativa se não informado diretamente)
2. CAPACIDADE DE INVESTIMENTO: Quanto tem disponível para investir agora
3. CARTÃO DE CRÉDITO: Tem cartão? Qual o limite disponível?
4. TIPO DE RENDA: CLT, autônomo, empresário, etc.
5. ESTOQUE: Tem estoque de produtos? (indicador de micro empresário)
6. PRODUTO RECOMENDADO: Com base nos dados acima, qual produto recomendar:
   - Produto Base (R$ 3.000-4.000): Se fatura pouco, ganha pouco (CLT baixo) ou está começando
   - Produto Intermediário (R$ 15.984): Capacidade financeira média
   - Produto Completo (R$ 29.892): Boa capacidade financeira

Responda em JSON com este formato exato:
{
  "faturamento_mensal": "valor estimado ou 'não informado'",
  "capacidade_investimento": "valor disponível ou 'não informado'",
  "tem_cartao_credito": true/false,
  "limite_cartao": "valor ou 'não informado'",
  "tipo_renda": "CLT/autônomo/empresário/não informado",
  "tem_estoque": true/false,
  "produto_recomendado": "base/intermediario/completo",
  "justificativa_produto": "explicação em 1-2 frases do porquê",
  "sinais_financeiros": "outros sinais financeiros relevantes detectados na conversa",
  "nivel_urgencia": "alto/medio/baixo — baseado em sinais de urgência do cliente"
}

TRANSCRIÇÃO DA REUNIÃO:
{transcript}
"""


async def diagnostico_financeiro(transcript: str) -> dict:
    """
    Analisa a transcrição e retorna o diagnóstico financeiro do cliente.

    Args:
        transcript: Texto completo da transcrição da reunião.

    Returns:
        Dicionário com diagnóstico financeiro e produto recomendado.
    """
    prompt = PROMPT_DIAGNOSTICO.format(transcript=transcript)

    resposta = await _get_cliente_openai().chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "Você é um especialista em análise financeira de clientes para vendas. "
                    "Responda sempre em JSON válido, sem markdown."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    import json

    resultado = json.loads(resposta.choices[0].message.content)

    # Enriquece com os dados do produto recomendado
    produto_chave = resultado.get("produto_recomendado", "base")
    resultado["detalhes_produto"] = PRODUTOS.get(produto_chave, PRODUTOS["base"])

    return resultado
