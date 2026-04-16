"""
Agente de Perfil DISC do SALEIA.

Identifica o perfil comportamental DISC do cliente com base na transcrição
e gera estratégias personalizadas de abordagem e tratamento de objeções.
"""

import os
from openai import AsyncOpenAI


def _get_cliente_openai() -> AsyncOpenAI:
    """Retorna o cliente OpenAI inicializado com a chave da variável de ambiente."""
    return AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Descrição dos perfis DISC para referência
PERFIS_DISC = {
    "D": {
        "nome": "Dominante",
        "caracteristicas": "Direto, objetivo, orientado a resultados, impaciente, tomador de decisão rápido",
        "como_abordar": "Seja direto, mostre ROI e resultados rápidos. Evite rodeios.",
        "gatilhos": "Exclusividade, resultados concretos, ser o primeiro",
        "evitar": "Muita conversa, detalhes desnecessários, perda de tempo",
    },
    "I": {
        "nome": "Influente",
        "caracteristicas": "Emotivo, sociável, gosta de histórias de sucesso, precisa de entusiasmo",
        "como_abordar": "Use histórias, emoção e entusiasmo. Conecte com o sonho dele.",
        "gatilhos": "Reconhecimento social, pertencimento, histórias inspiradoras",
        "evitar": "Frieza, excesso de dados técnicos, falta de entusiasmo",
    },
    "S": {
        "nome": "Estável",
        "caracteristicas": "Cauteloso, precisa de segurança e tempo para decidir, leal, avesso a riscos",
        "como_abordar": "Transmita segurança, mostre garantias e depoimentos. Não pressione.",
        "gatilhos": "Segurança, garantias, casos de sucesso comprovados",
        "evitar": "Pressão, mudanças bruscas, urgência excessiva",
    },
    "C": {
        "nome": "Consciente",
        "caracteristicas": "Analítico, detalhista, compara preços, precisa de dados e provas",
        "como_abordar": "Apresente dados, comparações e lógica. Seja preciso.",
        "gatilhos": "Dados concretos, comparações de mercado, metodologia comprovada",
        "evitar": "Generalidades, falta de embasamento, promessas vazias",
    },
}

PROMPT_DISC = """Você é um especialista em comportamento humano e metodologia DISC para vendas consultivas.

Analise a transcrição abaixo e identifique:

1. PERFIL DISC PREDOMINANTE do cliente (D, I, S ou C)
2. PERFIL DISC SECUNDÁRIO (se houver combinação)
3. SINAIS que levaram a essa conclusão (frases, comportamentos, palavras usadas)
4. NÍVEL DE ENGAJAMENTO do cliente durante a conversa
5. EXPECTATIVA PRINCIPAL do cliente (o que ele mais quer)
6. PROBLEMA PRINCIPAL que quer resolver
7. TOP 3 OBJEÇÕES PROVÁVEIS para este perfil + situação
8. COMO CONTORNAR CADA OBJEÇÃO
9. DICAS DE FECHAMENTO específicas para este perfil
10. O QUE O VENDEDOR NÃO PERCEBEU (sinais ocultos na conversa)

Responda em JSON com este formato exato:
{
  "perfil_predominante": "D/I/S/C",
  "perfil_secundario": "D/I/S/C ou null",
  "nome_perfil": "Dominante/Influente/Estável/Consciente",
  "sinais_identificados": ["sinal 1", "sinal 2", "sinal 3"],
  "nivel_engajamento": "alto/medio/baixo",
  "descricao_engajamento": "breve análise do engajamento",
  "expectativa_principal": "o que o cliente mais quer",
  "problema_principal": "dor principal identificada",
  "como_abordar": "estratégia específica de abordagem",
  "tom_recomendado": "como falar com este cliente",
  "objecoes": [
    {
      "objecao": "texto da objeção provável",
      "resposta": "como responder/contornar"
    },
    {
      "objecao": "segunda objeção",
      "resposta": "como responder"
    },
    {
      "objecao": "terceira objeção",
      "resposta": "como responder"
    }
  ],
  "estrategia_fechamento": "como fechar com este perfil",
  "sinal_oculto": "o que o vendedor provavelmente não percebeu na conversa",
  "proximos_passos_sugeridos": ["passo 1", "passo 2", "passo 3"]
}

TRANSCRIÇÃO DA REUNIÃO:
{transcript}
"""


async def perfil_disc(transcript: str) -> dict:
    """
    Analisa a transcrição e retorna o perfil DISC do cliente com estratégias.

    Args:
        transcript: Texto completo da transcrição da reunião.

    Returns:
        Dicionário com perfil DISC, objeções e estratégias de abordagem.
    """
    prompt = PROMPT_DISC.format(transcript=transcript)

    resposta = await _get_cliente_openai().chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "Você é um especialista em psicologia comportamental e metodologia DISC aplicada a vendas. "
                    "Analise com profundidade e responda sempre em JSON válido, sem markdown."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
        response_format={"type": "json_object"},
    )

    import json

    resultado = json.loads(resposta.choices[0].message.content)

    # Enriquece com os dados do perfil DISC identificado
    perfil_chave = resultado.get("perfil_predominante", "S")
    resultado["dados_perfil_disc"] = PERFIS_DISC.get(perfil_chave, PERFIS_DISC["S"])

    return resultado
