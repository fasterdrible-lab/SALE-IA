"""
SALEIA — agent/signo_solar_rules.py

Camada de astrologia opcional (signo solar) para entender melhor o
comportamento do cliente numa reunião de vendas — nunca substitui DISC ou
Big Five, nunca ajusta os scores desses dois. Mesmo padrão de
`agent/propensao_rules.py`: função pura, determinística, sem chamada de
IA, sem rede, sem biblioteca de efemérides (só signo solar — dia+mês —
não mapa natal).

O dia/mês de nascimento nunca é perguntado ao cliente. Só é usado quando
surge naturalmente na conversa (ex.: papo de aniversário no rapport) e é
extraído por `PROMPT_RECAPITULACAO` (api/main.py) — se ausente, este
módulo simplesmente não é chamado para aquela reunião.
"""

from typing import Optional

DISCLAIMER_ASTROLOGIA = (
    "A astrologia é apresentada aqui como uma interpretação simbólica e "
    "tradicional, não como evidência psicométrica ou científica. Ela nunca "
    "altera os resultados de DISC ou Big Five — serve só de contexto "
    "narrativo complementar."
)

# Intervalos de data do zodíaco tropical ocidental (mês, dia) — mesmo
# padrão usado universalmente para signo solar. Cada intervalo é
# (mes_inicio, dia_inicio, mes_fim, dia_fim); Capricórnio atravessa o
# fim do ano (22/12 -> 19/01).
_INTERVALOS = [
    ("Áries",       (3, 21), (4, 19)),
    ("Touro",       (4, 20), (5, 20)),
    ("Gêmeos",      (5, 21), (6, 20)),
    ("Câncer",      (6, 21), (7, 22)),
    ("Leão",        (7, 23), (8, 22)),
    ("Virgem",      (8, 23), (9, 22)),
    ("Libra",       (9, 23), (10, 22)),
    ("Escorpião",   (10, 23), (11, 21)),
    ("Sagitário",   (11, 22), (12, 21)),
    ("Capricórnio", (12, 22), (1, 19)),
    ("Aquário",     (1, 20), (2, 18)),
    ("Peixes",      (2, 19), (3, 20)),
]

SIGNOS = {
    "Áries": {
        "simbolo": "♈", "periodo": "21 mar — 19 abr",
        "elemento": "Fogo", "modalidade": "Cardinal", "polaridade": "Yang/ativa",
        "regente": "Marte", "arquetipo": "O Iniciador",
        "temas": ["início", "ação", "iniciativa", "independência", "competição", "coragem"],
        "comunicacao": "direta, rápida, objetiva, espontânea",
        "decisao": "tende a decidir rapidamente e partir para a ação",
        "motivadores": ["desafios", "autonomia", "conquista", "novidade", "competição"],
        "lideranca": "tende a assumir iniciativa",
        "sob_pressao": ["impaciência", "impulsividade", "confrontação direta"],
        "pontos_fortes": ["iniciativa", "coragem", "energia", "capacidade de começar projetos"],
        "pontos_atencao": ["pressa", "dificuldade com espera", "abandonar algo após a fase inicial"],
    },
    "Touro": {
        "simbolo": "♉", "periodo": "20 abr — 20 mai",
        "elemento": "Terra", "modalidade": "Fixo", "polaridade": "Yin/receptiva",
        "regente": "Vênus", "arquetipo": "O Construtor",
        "temas": ["estabilidade", "segurança", "permanência", "recursos", "prazer", "consistência"],
        "comunicacao": "calma, concreta, ponderada",
        "decisao": "cuidadosa; prefere segurança antes da mudança",
        "motivadores": ["estabilidade", "conforto", "segurança", "resultados concretos", "previsibilidade"],
        "lideranca": "lidera pelo exemplo e pela consistência",
        "sob_pressao": ["resistência à mudança", "rigidez", "dificuldade em abandonar decisões"],
        "pontos_fortes": ["persistência", "paciência", "lealdade", "consistência"],
        "pontos_atencao": ["teimosia", "resistência a mudar de curso mesmo quando necessário"],
    },
    "Gêmeos": {
        "simbolo": "♊", "periodo": "21 mai — 20 jun",
        "elemento": "Ar", "modalidade": "Mutável", "polaridade": "Yang/ativa",
        "regente": "Mercúrio", "arquetipo": "O Comunicador",
        "temas": ["comunicação", "informação", "curiosidade", "movimento", "aprendizagem"],
        "comunicacao": "rápida, verbal, curiosa, adaptável",
        "decisao": "avalia várias opções ao mesmo tempo antes de decidir",
        "motivadores": ["informação", "novidades", "variedade", "conversas", "aprendizagem"],
        "lideranca": "lidera trocando ideias e conectando pessoas",
        "sob_pressao": ["dispersão", "excesso de estímulos", "mudança constante de foco"],
        "pontos_fortes": ["adaptação", "comunicação", "capacidade de conectar informações"],
        "pontos_atencao": ["dispersão", "dificuldade em aprofundar um único assunto"],
    },
    "Câncer": {
        "simbolo": "♋", "periodo": "21 jun — 22 jul",
        "elemento": "Água", "modalidade": "Cardinal", "polaridade": "Yin/receptiva",
        "regente": "Lua", "arquetipo": "O Protetor",
        "temas": ["cuidado", "proteção", "vínculo", "memória", "pertencimento"],
        "comunicacao": "emocional, cuidadosa, contextual",
        "decisao": "guiada pela intuição e pelo impacto emocional da escolha",
        "motivadores": ["segurança emocional", "pertencimento", "família", "conexão"],
        "lideranca": "lidera cuidando e protegendo o grupo",
        "sob_pressao": ["retraimento", "defensividade", "sensibilidade aumentada"],
        "pontos_fortes": ["empatia", "proteção", "percepção emocional"],
        "pontos_atencao": ["fechar-se diante de críticas", "dificuldade em separar trabalho de emoção"],
    },
    "Leão": {
        "simbolo": "♌", "periodo": "23 jul — 22 ago",
        "elemento": "Fogo", "modalidade": "Fixo", "polaridade": "Yang/ativa",
        "regente": "Sol", "arquetipo": "O Protagonista",
        "temas": ["expressão", "identidade", "criatividade", "reconhecimento", "liderança"],
        "comunicacao": "expressiva, calorosa, confiante",
        "decisao": "decide com confiança, guiado por convicção pessoal",
        "motivadores": ["reconhecimento", "impacto", "criatividade", "liderança"],
        "lideranca": "tende a assumir protagonismo naturalmente",
        "sob_pressao": ["orgulho", "sensibilidade a críticas", "necessidade excessiva de reconhecimento"],
        "pontos_fortes": ["entusiasmo", "carisma", "capacidade de mobilizar pessoas"],
        "pontos_atencao": ["dificuldade em dividir os holofotes", "reação forte a críticas públicas"],
    },
    "Virgem": {
        "simbolo": "♍", "periodo": "23 ago — 22 set",
        "elemento": "Terra", "modalidade": "Mutável", "polaridade": "Yin/receptiva",
        "regente": "Mercúrio", "arquetipo": "O Analista",
        "temas": ["análise", "método", "aperfeiçoamento", "organização", "serviço"],
        "comunicacao": "objetiva, detalhada, analítica",
        "decisao": "analisa detalhes antes de decidir, evita decisões precipitadas",
        "motivadores": ["organização", "eficiência", "precisão", "melhoria"],
        "lideranca": "lidera pelo exemplo de método e cuidado com o detalhe",
        "sob_pressao": ["perfeccionismo", "excesso de crítica", "preocupação com erros"],
        "pontos_fortes": ["análise", "planejamento", "atenção aos detalhes"],
        "pontos_atencao": ["autocrítica excessiva", "dificuldade em avançar sem todos os dados"],
    },
    "Libra": {
        "simbolo": "♎", "periodo": "23 set — 22 out",
        "elemento": "Ar", "modalidade": "Cardinal", "polaridade": "Yang/ativa",
        "regente": "Vênus", "arquetipo": "O Diplomata",
        "temas": ["equilíbrio", "relacionamento", "negociação", "harmonia", "reciprocidade"],
        "comunicacao": "diplomática, conciliadora, social",
        "decisao": "pesa múltiplas perspectivas antes de decidir, busca consenso",
        "motivadores": ["cooperação", "equilíbrio", "reconhecimento social", "harmonia"],
        "lideranca": "lidera buscando consenso e equilíbrio entre partes",
        "sob_pressao": ["indecisão", "tentativa excessiva de evitar conflitos"],
        "pontos_fortes": ["negociação", "mediação", "compreensão de diferentes perspectivas"],
        "pontos_atencao": ["adiar decisões difíceis", "dificuldade em tomar posição firme"],
    },
    "Escorpião": {
        "simbolo": "♏", "periodo": "23 out — 21 nov",
        "elemento": "Água", "modalidade": "Fixo", "polaridade": "Yin/receptiva",
        "regente": "Marte (tradicional) / Plutão (moderno)", "arquetipo": "O Estrategista",
        "temas": ["intensidade", "transformação", "estratégia", "profundidade", "confiança"],
        "comunicacao": "seletiva, investigativa, intensa",
        "decisao": "decide após avaliar profundamente, com forte convicção",
        "motivadores": ["profundidade", "confiança", "autonomia", "transformação"],
        "lideranca": "lidera com estratégia e discrição",
        "sob_pressao": ["desconfiança", "controle", "dificuldade de exposição"],
        "pontos_fortes": ["concentração", "investigação", "persistência", "leitura estratégica"],
        "pontos_atencao": ["desconfiança excessiva", "dificuldade em abrir informação livremente"],
    },
    "Sagitário": {
        "simbolo": "♐", "periodo": "22 nov — 21 dez",
        "elemento": "Fogo", "modalidade": "Mutável", "polaridade": "Yang/ativa",
        "regente": "Júpiter", "arquetipo": "O Explorador",
        "temas": ["expansão", "exploração", "conhecimento", "liberdade", "sentido"],
        "comunicacao": "aberta, espontânea, entusiasmada",
        "decisao": "decide rápido, guiado por visão de possibilidades",
        "motivadores": ["liberdade", "novas experiências", "conhecimento", "exploração"],
        "lideranca": "lidera inspirando visão e possibilidade",
        "sob_pressao": ["inquietação", "excesso de franqueza", "dificuldade com limitações"],
        "pontos_fortes": ["visão ampla", "otimismo", "capacidade de explorar possibilidades"],
        "pontos_atencao": ["prometer mais do que consegue entregar", "impaciência com detalhes"],
    },
    "Capricórnio": {
        "simbolo": "♑", "periodo": "22 dez — 19 jan",
        "elemento": "Terra", "modalidade": "Cardinal", "polaridade": "Yin/receptiva",
        "regente": "Saturno", "arquetipo": "O Estrategista de Longo Prazo",
        "temas": ["estrutura", "responsabilidade", "realização", "disciplina", "longo prazo"],
        "comunicacao": "objetiva, séria, pragmática",
        "decisao": "decide de forma calculada, pensando em resultado de longo prazo",
        "motivadores": ["progresso", "competência", "reconhecimento por resultados", "construção de legado"],
        "lideranca": "lidera com disciplina e senso de responsabilidade",
        "sob_pressao": ["rigidez", "excesso de responsabilidade", "autocobrança"],
        "pontos_fortes": ["disciplina", "planejamento", "perseverança"],
        "pontos_atencao": ["dificuldade em relaxar exigência", "pode parecer excessivamente sério"],
    },
    "Aquário": {
        "simbolo": "♒", "periodo": "20 jan — 18 fev",
        "elemento": "Ar", "modalidade": "Fixo", "polaridade": "Yang/ativa",
        "regente": "Saturno (tradicional) / Urano (moderno)", "arquetipo": "O Inovador",
        "temas": ["inovação", "coletividade", "independência", "ideias", "futuro"],
        "comunicacao": "conceitual, racional, original",
        "decisao": "decide de forma independente, guiado por lógica própria",
        "motivadores": ["autonomia intelectual", "inovação", "mudança", "propósito coletivo"],
        "lideranca": "lidera com visão sistêmica e ideias originais",
        "sob_pressao": ["distanciamento", "rigidez intelectual", "resistência a controle externo"],
        "pontos_fortes": ["pensamento independente", "inovação", "visão sistêmica"],
        "pontos_atencao": ["parecer distante", "resistência a seguir processos padronizados"],
    },
    "Peixes": {
        "simbolo": "♓", "periodo": "19 fev — 20 mar",
        "elemento": "Água", "modalidade": "Mutável", "polaridade": "Yin/receptiva",
        "regente": "Júpiter (tradicional) / Netuno (moderno)", "arquetipo": "O Sensível",
        "temas": ["imaginação", "sensibilidade", "empatia", "integração", "simbolismo"],
        "comunicacao": "intuitiva, sensível, contextual",
        "decisao": "guiada por intuição e percepção do todo, pode demorar a se fechar",
        "motivadores": ["significado", "conexão", "criatividade", "ajudar pessoas"],
        "lideranca": "lidera inspirando pelo exemplo emocional/criativo",
        "sob_pressao": ["fuga de conflitos", "dificuldade de limites", "idealização"],
        "pontos_fortes": ["imaginação", "empatia", "percepção emocional"],
        "pontos_atencao": ["evitar confrontos necessários", "dificuldade em estabelecer limites claros"],
    },
}

ELEMENTOS = {
    "Fogo":  {"emoji": "🔥", "associado_a": ["ação", "entusiasmo", "expressão", "energia", "iniciativa"]},
    "Terra": {"emoji": "🌍", "associado_a": ["concretização", "estabilidade", "organização", "pragmatismo"]},
    "Ar":    {"emoji": "🌬", "associado_a": ["comunicação", "ideias", "relações", "pensamento"]},
    "Água":  {"emoji": "💧", "associado_a": ["sensibilidade", "emoção", "percepção", "vínculo"]},
}

MODALIDADES = {
    "Cardinal": {"arquetipo": "iniciar"},
    "Fixo":     {"arquetipo": "sustentar"},
    "Mutável":  {"arquetipo": "adaptar"},
}


def calcular_signo(dia: Optional[int], mes: Optional[int]) -> Optional[str]:
    """Retorna o nome do signo solar a partir de dia+mês de nascimento, ou
    None se dia/mês ausentes ou inválidos. Função pura — sem IA, sem rede,
    sem biblioteca de efemérides (só zodíaco tropical, signo solar)."""
    if dia is None or mes is None:
        return None
    try:
        dia = int(dia)
        mes = int(mes)
    except (TypeError, ValueError):
        return None
    if not (1 <= mes <= 12) or not (1 <= dia <= 31):
        return None

    for nome, (ini_mes, ini_dia), (fim_mes, fim_dia) in _INTERVALOS:
        if ini_mes == fim_mes:
            if mes == ini_mes and ini_dia <= dia <= fim_dia:
                return nome
        elif ini_mes < fim_mes:
            if (mes == ini_mes and dia >= ini_dia) or (mes == fim_mes and dia <= fim_dia) or (ini_mes < mes < fim_mes):
                return nome
        else:  # atravessa o fim do ano (Capricórnio: 22/12 -> 19/01)
            if (mes == ini_mes and dia >= ini_dia) or (mes == fim_mes and dia <= fim_dia):
                return nome
    return None


def obter_perfil_signo(nome_signo: Optional[str]) -> Optional[dict]:
    """Retorna o dict estruturado do signo (ver SIGNOS), incluindo dados de
    elemento/modalidade resolvidos e o disclaimer fixo, ou None se o nome
    não for reconhecido."""
    dados = SIGNOS.get(nome_signo)
    if not dados:
        return None
    perfil = dict(dados)
    perfil["nome"] = nome_signo
    perfil["elemento_info"] = ELEMENTOS.get(dados["elemento"], {})
    perfil["modalidade_info"] = MODALIDADES.get(dados["modalidade"], {})
    perfil["disclaimer"] = DISCLAIMER_ASTROLOGIA
    return perfil
