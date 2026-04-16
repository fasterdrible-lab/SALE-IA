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

# Configurações da aplicação
APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
APP_ENV: str = os.getenv("APP_ENV", "development")
