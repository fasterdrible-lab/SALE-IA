# Módulo de suporte em tempo real ao vendedor do SALEIA
# Usa o template de prompt em /agent/prompt_templates/suporte_venda.txt
# e a OpenAI API (GPT-4o) para gerar orientações imediatas durante a conversa.

import re
from pathlib import Path
from typing import Dict

from openai import AsyncOpenAI

from api.config import OPENAI_API_KEY, OPENAI_MODEL

# Caminho para o template de prompt
_TEMPLATE_PATH = Path(__file__).parent / "prompt_templates" / "suporte_venda.txt"

# Inicializa o cliente OpenAI assíncrono
_cliente = AsyncOpenAI(api_key=OPENAI_API_KEY)


def _carregar_template() -> str:
    """Carrega o template de prompt do arquivo de texto."""
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


def _extrair_secoes(texto: str) -> Dict[str, str]:
    """
    Extrai as seções do texto retornado pela IA e organiza em um dicionário.

    Seções esperadas:
        - 🎯 PRÓXIMA FALA SUGERIDA
        - 💡 GATILHO EMOCIONAL IDENTIFICADO
        - ⚠️ OBJEÇÃO DETECTADA + RESPOSTA
        - 💰 MELHOR OFERTA PARA ESTE MOMENTO
    """
    secoes = {
        "proxima_fala": "",
        "gatilho_emocional": "",
        "objecao_e_resposta": "",
        "melhor_oferta": "",
    }

    # Padrões de busca para cada seção (aceita variações de formatação)
    padroes = {
        "proxima_fala": r"🎯\s*PRÓXIMA FALA SUGERIDA\s*:?\s*(.*?)(?=💡|⚠|💰|$)",
        "gatilho_emocional": r"💡\s*GATILHO EMOCIONAL IDENTIFICADO\s*:?\s*(.*?)(?=🎯|⚠|💰|$)",
        "objecao_e_resposta": r"⚠️?\s*OBJEÇÃO DETECTADA\s*\+\s*RESPOSTA\s*:?\s*(.*?)(?=🎯|💡|💰|$)",
        "melhor_oferta": r"💰\s*MELHOR OFERTA PARA ESTE MOMENTO\s*:?\s*(.*?)(?=🎯|💡|⚠|$)",
    }

    for chave, padrao in padroes.items():
        correspondencia = re.search(padrao, texto, re.DOTALL | re.IGNORECASE)
        if correspondencia:
            secoes[chave] = correspondencia.group(1).strip()

    # Se a extração por seções falhar, retorna o texto completo na próxima fala
    # e preenche as demais seções com valor padrão explícito
    if not any(secoes.values()):
        secoes["proxima_fala"] = texto.strip()
        secoes["gatilho_emocional"] = "Não identificado"
        secoes["objecao_e_resposta"] = "Nenhuma objeção detectada"
        secoes["melhor_oferta"] = "Avaliar conforme contexto"

    # Garante que nenhum campo fique vazio após a extração parcial
    defaults = {
        "proxima_fala": "Aguarde o contexto evoluir",
        "gatilho_emocional": "Não identificado",
        "objecao_e_resposta": "Nenhuma objeção detectada",
        "melhor_oferta": "Avaliar conforme contexto",
    }
    for chave, valor_padrao in defaults.items():
        if not secoes[chave]:
            secoes[chave] = valor_padrao

    return secoes


async def gerar_suporte_venda(
    perfil_cliente: str,
    fase: str,
    ultima_fala: str,
    historico: str,
) -> Dict[str, str]:
    """
    Gera orientações em tempo real para o vendedor durante a conversa.

    Parâmetros:
        perfil_cliente: Perfil emocional e comportamental do cliente
        fase: Fase atual da conversa de vendas
        ultima_fala: Última fala registrada do cliente
        historico: Resumo do histórico da conversa

    Retorna:
        Dicionário com proxima_fala, gatilho_emocional, objecao_e_resposta e melhor_oferta.
    """
    template = _carregar_template()

    # Substitui os placeholders do template
    prompt = template.format(
        perfil_cliente=perfil_cliente,
        fase=fase,
        ultima_fala=ultima_fala,
        historico=historico,
    )

    # Chama a API da OpenAI
    resposta = await _cliente.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
    )

    texto_resposta = resposta.choices[0].message.content

    # Extrai e organiza as seções da resposta
    return _extrair_secoes(texto_resposta)
