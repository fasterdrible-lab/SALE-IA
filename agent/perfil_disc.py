"""
Agente de Perfil DISC do SALEIA.

Identifica o perfil comportamental DISC usando o roteador central de IA com
fallback automatico entre provedores de chat.
"""

from api.ai_router import chamar_ia_async

PERFIS_DISC = {
    "D": {
        "nome": "Dominante",
        "caracteristicas": "Direto, objetivo, orientado a resultados e impaciente",
        "como_abordar": "Seja direto, mostre ROI e resultados rapidos. Evite rodeios.",
        "gatilhos": "Exclusividade, resultados concretos, ser o primeiro",
        "evitar": "Muita conversa, detalhes desnecessarios, perda de tempo",
    },
    "I": {
        "nome": "Influente",
        "caracteristicas": "Emotivo, sociavel, gosta de historias de sucesso",
        "como_abordar": "Use historias, emocao e entusiasmo. Conecte com o sonho dele.",
        "gatilhos": "Reconhecimento social, pertencimento, historias inspiradoras",
        "evitar": "Frieza, excesso de dados tecnicos, falta de entusiasmo",
    },
    "S": {
        "nome": "Estavel",
        "caracteristicas": "Cauteloso, precisa de seguranca e tempo para decidir",
        "como_abordar": "Transmita seguranca, mostre garantias e depoimentos. Nao pressione.",
        "gatilhos": "Seguranca, garantias, casos de sucesso comprovados",
        "evitar": "Pressao, mudancas bruscas, urgencia excessiva",
    },
    "C": {
        "nome": "Consciente",
        "caracteristicas": "Analitico, detalhista, compara precos e precisa de provas",
        "como_abordar": "Apresente dados, comparacoes e logica. Seja preciso.",
        "gatilhos": "Dados concretos, metodologia comprovada, comparacoes de mercado",
        "evitar": "Generalidades, falta de embasamento, promessas vagas",
    },
}

PROMPT_DISC = """Voce e um especialista em comportamento humano e metodologia DISC para vendas consultivas.

Analise a transcricao abaixo e identifique:
1. Perfil DISC predominante.
2. Perfil secundario, se houver.
3. Sinais que levaram a conclusao.
4. Nivel de engajamento.
5. Expectativa principal.
6. Problema principal.
7. Top 3 objecoes provaveis.
8. Como contornar cada objecao.
9. Estrategia de fechamento.
10. Sinal oculto que o vendedor pode nao ter percebido.

Responda em JSON com este formato:
{
  "perfil_predominante": "D/I/S/C",
  "perfil_secundario": "D/I/S/C ou null",
  "nome_perfil": "Dominante/Influente/Estavel/Consciente",
  "sinais_identificados": ["sinal 1", "sinal 2", "sinal 3"],
  "nivel_engajamento": "alto/medio/baixo",
  "descricao_engajamento": "breve analise do engajamento",
  "expectativa_principal": "o que o cliente mais quer",
  "problema_principal": "dor principal identificada",
  "como_abordar": "estrategia especifica",
  "tom_recomendado": "como falar com este cliente",
  "objecoes": [
    {"objecao": "objecao provavel", "resposta": "como responder"},
    {"objecao": "segunda objecao", "resposta": "como responder"},
    {"objecao": "terceira objecao", "resposta": "como responder"}
  ],
  "estrategia_fechamento": "como fechar com este perfil",
  "sinal_oculto": "o que o vendedor provavelmente nao percebeu",
  "proximos_passos_sugeridos": ["passo 1", "passo 2", "passo 3"]
}

TRANSCRICAO DA REUNIAO:
{transcript}
"""


async def perfil_disc(transcript: str) -> dict:
    prompt = PROMPT_DISC.replace("{transcript}", transcript)
    resultado = await chamar_ia_async(
        (
            "Voce e um especialista em psicologia comportamental e metodologia DISC "
            "aplicada a vendas. Responda sempre em JSON valido, sem markdown."
        ),
        prompt,
    )

    perfil_chave = resultado.get("perfil_predominante", "S")
    resultado["dados_perfil_disc"] = PERFIS_DISC.get(perfil_chave, PERFIS_DISC["S"])
    return resultado
