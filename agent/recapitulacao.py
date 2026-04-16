# Módulo de recapitulação pós-reunião do SALEIA
# Usa o template de prompt em /agent/prompt_templates/recapitulacao.txt
# e a OpenAI API (GPT-4o) para gerar a recapitulação emocional e estratégica.

from pathlib import Path

from openai import AsyncOpenAI

from api.config import OPENAI_API_KEY, OPENAI_MODEL

# Caminho para o template de prompt
_TEMPLATE_PATH = Path(__file__).parent / "prompt_templates" / "recapitulacao.txt"

# Inicializa o cliente OpenAI assíncrono
_cliente = AsyncOpenAI(api_key=OPENAI_API_KEY)


def _carregar_template() -> str:
    """Carrega o template de prompt do arquivo de texto."""
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


async def gerar_recapitulacao(transcricao: str) -> str:
    """
    Gera a recapitulação emocional e estratégica da reunião de vendas.

    Parâmetros:
        transcricao: Texto com a transcrição completa da reunião

    Retorna:
        Texto formatado com recapitulação emocional, estratégica e próximos passos.
    """
    template = _carregar_template()

    # Substitui o placeholder com a transcrição
    prompt = template.format(transcricao=transcricao)

    # Chama a API da OpenAI
    resposta = await _cliente.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
    )

    return resposta.choices[0].message.content
