# Módulo de geração de diagnóstico pré-reunião do SALEIA
# Usa o template de prompt em /agent/prompt_templates/diagnostico.txt
# e a OpenAI API (GPT-4o) para gerar o diagnóstico personalizado do cliente.

from pathlib import Path
from typing import List

from openai import AsyncOpenAI

from api.config import OPENAI_API_KEY, OPENAI_MODEL

# Caminho para o template de prompt
_TEMPLATE_PATH = Path(__file__).parent / "prompt_templates" / "diagnostico.txt"

# Inicializa o cliente OpenAI assíncrono
_cliente = AsyncOpenAI(api_key=OPENAI_API_KEY)


def _carregar_template() -> str:
    """Carrega o template de prompt do arquivo de texto."""
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


async def gerar_diagnostico(
    nome: str,
    segmento: str,
    dores: List[str],
    objetivos: List[str],
) -> str:
    """
    Gera um diagnóstico personalizado do cliente usando GPT-4o.

    Parâmetros:
        nome: Nome do cliente
        segmento: Segmento de atuação do cliente
        dores: Lista de dores relatadas pelo cliente
        objetivos: Lista de objetivos do cliente

    Retorna:
        Texto formatado com o diagnóstico completo do cliente.
    """
    template = _carregar_template()

    # Formata as listas como texto legível
    dores_texto = ", ".join(dores)
    objetivos_texto = ", ".join(objetivos)

    # Substitui os placeholders do template
    prompt = template.format(
        nome=nome,
        segmento=segmento,
        dores=dores_texto,
        objetivos=objetivos_texto,
    )

    # Chama a API da OpenAI
    resposta = await _cliente.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
    )

    return resposta.choices[0].message.content
