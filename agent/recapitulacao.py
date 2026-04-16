"""
Agente de Recapitulação Completa do SALEIA.

Gera a recapitulação final da reunião combinando diagnóstico financeiro
e perfil DISC para produzir um relatório completo e acionável para o vendedor.
"""

import os
from openai import AsyncOpenAI


def _get_cliente_openai() -> AsyncOpenAI:
    """Retorna o cliente OpenAI inicializado com a chave da variável de ambiente."""
    return AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

PROMPT_RECAPITULACAO = """Você é um coach de vendas especializado que analisa reuniões de consultoria.

Com base na transcrição da reunião e nos diagnósticos abaixo, gere uma recapitulação
completa e acionável para o vendedor.

DADOS DO DIAGNÓSTICO FINANCEIRO:
{financeiro}

DADOS DO PERFIL DISC:
{disc}

Gere a recapitulação completa em JSON com este formato:
{{
  "resumo_executivo": "Resumo em 3 linhas do que aconteceu na reunião e próximo passo",

  "recapitulacao_emocional": {{
    "estado_emocional": "Como o cliente estava emocionalmente durante a reunião",
    "momentos_chave": ["Momento 1 que teve impacto emocional", "Momento 2", "Momento 3"],
    "nivel_confianca": "alto/medio/baixo — nível de confiança demonstrado no vendedor",
    "motivacao_principal": "O que realmente motiva este cliente a agir"
  }},

  "recapitulacao_estrategica": {{
    "situacao_atual": "Situação atual do cliente em detalhes",
    "dor_principal": "Principal dor ou problema que quer resolver",
    "expectativa_crescimento": "O que espera conquistar com o produto",
    "capacidade_decisao": "alto/medio/baixo — capacidade do cliente de tomar decisão agora",
    "prazo_decisao": "Estimativa de quando vai decidir"
  }},

  "produto_recomendado": {{
    "nome": "Nome do produto recomendado",
    "valor": "Valor do produto",
    "justificativa": "Por que este produto é o ideal para este cliente específico",
    "forma_pagamento_ideal": "Forma de pagamento mais adequada para o perfil financeiro"
  }},

  "perfil_comportamental": {{
    "perfil_disc": "D/I/S/C — Dominante/Influente/Estável/Consciente",
    "como_abordar": "Como abordar nas próximas interações",
    "linguagem_ideal": "Que tipo de linguagem e tom usar",
    "o_que_evitar": "O que NÃO fazer com este cliente"
  }},

  "top_objecoes": [
    {{
      "objecao": "Objeção mais provável",
      "resposta_sugerida": "Como responder de forma eficaz"
    }},
    {{
      "objecao": "Segunda objeção",
      "resposta_sugerida": "Como responder"
    }},
    {{
      "objecao": "Terceira objeção",
      "resposta_sugerida": "Como responder"
    }}
  ],

  "sinal_oculto": "O que o vendedor provavelmente NÃO percebeu — insight valioso da conversa",

  "proximos_passos": [
    "Ação específica para as próximas 24 horas",
    "Ação para os próximos 3 dias",
    "Ação para o fechamento"
  ],

  "script_follow_up": "Mensagem sugerida para o follow-up após a reunião (WhatsApp)"
}}

TRANSCRIÇÃO DA REUNIÃO:
{transcript}
"""

PROMPT_DICAS_TEMPO_REAL = """Você é um coach de vendas especializado que acompanha reuniões em tempo real.

Analise a transcrição parcial abaixo e gere DICAS IMEDIATAS para o vendedor.
Foque em sinais que o vendedor provavelmente NÃO percebeu.

Responda em JSON:
{{
  "dica_principal": "A dica mais importante neste momento",
  "perfil_disc_parcial": "D/I/S/C — melhor estimativa até agora",
  "nivel_engajamento": "alto/medio/baixo",
  "sinais_positivos": ["Sinal positivo 1", "Sinal positivo 2"],
  "alertas": ["Alerta 1 — algo que o vendedor deve prestar atenção"],
  "proxima_pergunta_sugerida": "Qual pergunta fazer agora para avançar na venda",
  "produto_provavel": "base/intermediario/completo — estimativa do produto ideal",
  "tom_recomendado": "Como o vendedor deve se comunicar agora"
}}

TRANSCRIÇÃO PARCIAL:
{transcript}
"""


async def recapitulacao_completa(
    transcript: str, financeiro: dict, disc: dict
) -> dict:
    """
    Gera a recapitulação completa combinando diagnóstico financeiro e perfil DISC.

    Args:
        transcript: Texto completo da transcrição da reunião.
        financeiro: Resultado do diagnóstico financeiro.
        disc: Resultado da análise de perfil DISC.

    Returns:
        Dicionário com recapitulação completa e acionável.
    """
    import json

    prompt = PROMPT_RECAPITULACAO.format(
        transcript=transcript,
        financeiro=json.dumps(financeiro, ensure_ascii=False, indent=2),
        disc=json.dumps(disc, ensure_ascii=False, indent=2),
    )

    resposta = await _get_cliente_openai().chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "Você é um coach de vendas de alto nível especializado em vendas consultivas. "
                    "Sua recapitulação deve ser precisa, acionável e focada no fechamento. "
                    "Responda sempre em JSON válido, sem markdown."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.5,
        response_format={"type": "json_object"},
    )

    resultado = json.loads(resposta.choices[0].message.content)
    return resultado


async def dicas_tempo_real(transcript: str) -> dict:
    """
    Gera dicas em tempo real durante a reunião com base na transcrição parcial.

    Args:
        transcript: Texto parcial da transcrição até o momento.

    Returns:
        Dicionário com dicas e orientações para o vendedor agir imediatamente.
    """
    import json

    prompt = PROMPT_DICAS_TEMPO_REAL.format(transcript=transcript)

    resposta = await _get_cliente_openai().chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "Você é um coach de vendas especializado em vendas consultivas ao vivo. "
                    "Gere dicas práticas e imediatas. Responda em JSON válido, sem markdown."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
        response_format={"type": "json_object"},
    )

    resultado = json.loads(resposta.choices[0].message.content)
    return resultado
