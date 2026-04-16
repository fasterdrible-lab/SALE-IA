"""
llm_router.py — Roteador de LLMs do SALEIA

Suporta:
  - OpenAI  (GPT-4o, GPT-4o-mini, etc.)
  - Anthropic (Claude 3.5 Sonnet, etc.)
  - Google   (Gemini 1.5 Pro, etc.)

O SDK de cada provedor é importado apenas quando necessário,
evitando erros de importação caso o pacote não esteja instalado.
"""

import os


async def chamar_llm(prompt: str, model: str, provider: str, api_key: str = None) -> str:
    """
    Roteia a chamada para o provedor de LLM correto com base no parâmetro 'provider'.

    Args:
        prompt:   Texto completo a ser enviado ao modelo.
        model:    Identificador do modelo (ex: "gpt-4o", "claude-3-5-sonnet-20241022").
        provider: Provedor do modelo ("openai", "anthropic" ou "google").
        api_key:  Chave de API enviada pela extensão Chrome (sobrepõe a variável de ambiente).

    Returns:
        Resposta em texto puro gerada pelo modelo.

    Raises:
        ValueError: Se o provedor não for suportado.
    """
    if provider == "openai":
        return await chamar_openai(prompt, model, api_key)
    elif provider == "anthropic":
        return await chamar_anthropic(prompt, model, api_key)
    elif provider == "google":
        return await chamar_gemini(prompt, model, api_key)
    else:
        raise ValueError(f"Provedor desconhecido: {provider}. Use 'openai', 'anthropic' ou 'google'.")


# ─── OpenAI ──────────────────────────────────────────────────────────────────

async def chamar_openai(prompt: str, model: str, api_key: str = None) -> str:
    """Chama a API da OpenAI (GPT-4o, GPT-4o-mini, etc.)."""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        raise RuntimeError(
            "Pacote 'openai' não instalado. Execute: pip install openai"
        )

    chave = api_key or os.getenv("OPENAI_API_KEY")
    if not chave:
        raise ValueError("Chave OpenAI não configurada. Defina OPENAI_API_KEY no .env ou informe no popup.")

    client = AsyncOpenAI(api_key=chave)
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.choices[0].message.content


# ─── Anthropic ───────────────────────────────────────────────────────────────

async def chamar_anthropic(prompt: str, model: str, api_key: str = None) -> str:
    """Chama a API da Anthropic (Claude 3.5 Sonnet, etc.)."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "Pacote 'anthropic' não instalado. Execute: pip install anthropic"
        )

    chave = api_key or os.getenv("ANTHROPIC_API_KEY")
    if not chave:
        raise ValueError("Chave Anthropic não configurada. Defina ANTHROPIC_API_KEY no .env ou informe no popup.")

    client = anthropic.AsyncAnthropic(api_key=chave)
    message = await client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


# ─── Google Gemini ───────────────────────────────────────────────────────────

async def chamar_gemini(prompt: str, model: str, api_key: str = None) -> str:
    """Chama a API do Google Gemini."""
    try:
        import google.generativeai as genai
    except ImportError:
        raise RuntimeError(
            "Pacote 'google-generativeai' não instalado. Execute: pip install google-generativeai"
        )

    chave = api_key or os.getenv("GOOGLE_API_KEY")
    if not chave:
        raise ValueError("Chave Google não configurada. Defina GOOGLE_API_KEY no .env ou informe no popup.")

    genai.configure(api_key=chave)
    gemini_model = genai.GenerativeModel(model)
    response = await gemini_model.generate_content_async(prompt)
    return response.text
