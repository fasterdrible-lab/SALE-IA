"""
Agente de diagnostico financeiro do SALEIA.

Analisa a transcricao da reuniao e extrai informacoes financeiras do cliente
usando o roteador central de IA com fallback automatico.
"""

from api.ai_router import chamar_ia_async

PRODUTOS = {
    "base": {
        "nome": "Produto Base",
        "valor": "R$ 3.000 - R$ 4.000",
        "descricao": "Ideal para quem fatura pouco, esta comecando ou tem renda CLT baixa",
    },
    "intermediario": {
        "nome": "Produto Intermediario",
        "valor": "R$ 15.984,00",
        "descricao": "Para quem tem capacidade financeira media e quer escalar",
    },
    "completo": {
        "nome": "Produto Completo",
        "valor": "R$ 29.892,00",
        "descricao": "Para quem tem boa capacidade financeira e quer resultado maximo",
    },
}

PROMPT_DIAGNOSTICO = """Voce e um especialista em diagnostico financeiro de clientes para vendas consultivas.

Analise a transcricao abaixo e extraia:
1. Faturamento mensal.
2. Capacidade de investimento.
3. Cartao de credito e limite disponivel.
4. Tipo de renda.
5. Estoque ou sinais de microempresa.
6. Produto recomendado: base, intermediario ou completo.

Responda em JSON com este formato:
{
  "faturamento_mensal": "valor estimado ou 'nao informado'",
  "capacidade_investimento": "valor disponivel ou 'nao informado'",
  "tem_cartao_credito": true,
  "limite_cartao": "valor ou 'nao informado'",
  "tipo_renda": "CLT/autonomo/empresario/nao informado",
  "tem_estoque": false,
  "produto_recomendado": "base/intermediario/completo",
  "justificativa_produto": "explicacao em 1-2 frases",
  "sinais_financeiros": "outros sinais relevantes",
  "nivel_urgencia": "alto/medio/baixo"
}

TRANSCRICAO DA REUNIAO:
{transcript}
"""


async def diagnostico_financeiro(transcript: str) -> dict:
    prompt = PROMPT_DIAGNOSTICO.replace("{transcript}", transcript)
    resultado = await chamar_ia_async(
        (
            "Voce e um especialista em analise financeira de clientes para vendas. "
            "Responda sempre em JSON valido, sem markdown."
        ),
        prompt,
    )

    produto_chave = resultado.get("produto_recomendado", "base")
    resultado["detalhes_produto"] = PRODUTOS.get(produto_chave, PRODUTOS["base"])
    return resultado
