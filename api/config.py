# Configuração das variáveis de ambiente do SALEIA
# Carrega o arquivo .env com python-dotenv

import os
from dotenv import load_dotenv

# Carrega as variáveis definidas no arquivo .env
load_dotenv()

# Chave de API da OpenAI (obrigatória)
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

# Modelo da OpenAI a ser utilizado (padrão: gpt-4o)
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

# Fallback de IA generativa (chat/JSON). As chaves permanecem somente no backend.
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
AI_PROVIDER_ORDER: str = os.getenv("AI_PROVIDER_ORDER", "deepseek,openai,anthropic,gemini")
AI_PROVIDER_TIMEOUT_SECONDS: int = int(os.getenv("AI_PROVIDER_TIMEOUT_SECONDS", "30"))

# Configurações da aplicação
APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
APP_ENV: str = os.getenv("APP_ENV", "development")
