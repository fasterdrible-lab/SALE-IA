"""
SALEIA — agent/claude_account.py

Executor da conta Claude individual do usuário (piloto "Claude Account Mode").

IMPORTANTE — este módulo foi criado exclusivamente para validação controlada
do produto (piloto). Não deve ser utilizado como backend compartilhado de
produção. O sistema deve permitir futura substituição do executor sem
reescrever os módulos de reunião — por isso toda chamada ao Claude Agent SDK
fica concentrada aqui, atrás da interface única `ClaudeAccountExecutor.execute()`.

Cada usuário usa exclusivamente a própria assinatura Claude (Pro/Max), conectada
via `claude setup-token` rodado por ele na própria máquina — não existe conta
Claude central nem fallback para a conta de outro usuário/administrador.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

from api.ai_router import _extract_json
from api.database import (
    marcar_status_claude_connection,
    obter_claude_connection,
    registrar_uso_claude_connection,
)

load_dotenv()

logger = logging.getLogger("saleia.claude_account")

DEFAULT_TIMEOUT_SECONDS = 90.0

MSG_LOGIN_REQUIRED = "Conecte sua conta Claude antes de analisar esta reunião."
MSG_AUTH_REQUIRED = "Sua sessão Claude expirou. Reconecte sua conta Claude para continuar."
MSG_USAGE_LIMIT = (
    "O limite da sua conta Claude foi atingido. A SALEIA não realizará uma "
    "nova análise até que sua conta esteja novamente disponível."
)
MSG_GENERIC_ERROR = "Não foi possível concluir a análise com sua conta Claude. Tente novamente em instantes."
MSG_CLI_MISSING = (
    "O ambiente do servidor ainda não está pronto para o piloto Claude "
    "(CLI não encontrado). Avise o administrador."
)

# Padrões observados em mensagens do Claude Code CLI/SDK — heurística de
# classificação, não é uma lista fechada garantida pela Anthropic.
_PADROES_LIMITE = re.compile(
    r"usage limit|rate limit|quota|too many requests|429|resource_exhausted|overloaded",
    re.IGNORECASE,
)
_PADROES_AUTH = re.compile(
    r"unauthorized|authentication|invalid.*(token|api.?key|credential)|"
    r"not authenticated|please (run|login)|expired|401|forbidden|403",
    re.IGNORECASE,
)

PROMPT_ANALISE_CLAUDE_ACCOUNT = """Você é um analista de vendas sênior da SALEIA. Analise a transcrição de reunião
de vendas abaixo e responda SOMENTE com um objeto JSON válido (sem markdown, sem texto fora do JSON),
com exatamente esta estrutura:

{
  "dores": ["..."],
  "metas": ["..."],
  "objecoes": ["..."],
  "decisores": ["..."],
  "riscos": ["..."],
  "recapitulacao": "texto corrido resumindo a reunião",
  "proxima_acao_sugerida": "texto curto e acionável"
}

Não inclua nenhum campo além desses sete. Seja específico e baseie-se apenas no que está na transcrição."""


class ClaudeAccountError(Exception):
    """Erro classificado do piloto Claude Account Mode.

    `code` é um dos: LOGIN_REQUIRED, AUTH_REQUIRED, USAGE_LIMIT_REACHED, GENERIC_ERROR
    `message` já é a mensagem em PT-BR pronta para exibir ao usuário.
    """

    def __init__(self, code: str, message: str, detalhe: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detalhe = detalhe


def claude_pilot_habilitado() -> bool:
    """Feature flag do piloto (Tarefa 21). Se desativada, a funcionalidade fica indisponível."""
    return os.getenv("CLAUDE_ACCOUNT_PILOT", "false").strip().lower() in ("1", "true", "yes")


def sanitizar_erro_claude(texto: Optional[str]) -> str:
    """Redige qualquer coisa que pareça token/credencial antes de logar ou persistir (Tarefa 17)."""
    valor = str(texto or "")
    valor = re.sub(r"sk-ant-oat[A-Za-z0-9_\-]+", "[REDACTED]", valor)
    valor = re.sub(r"sk-ant-[A-Za-z0-9_\-]+", "[REDACTED]", valor)
    # "Authorization: Bearer <token>" / "Authorization Bearer <token>" / "Bearer <token>" —
    # captura o par inteiro (não só a palavra-chave) para não deixar o token vazar depois dela.
    valor = re.sub(
        r"(?i)(?:authorization\s*:?\s*)?bearer\s+[A-Za-z0-9_\-.=]+",
        "Authorization Bearer [REDACTED]",
        valor,
    )
    valor = re.sub(r"(?i)authorization\s*:?\s*[A-Za-z0-9_\-.=]+", "Authorization [REDACTED]", valor)
    valor = re.sub(r"(?i)(api[_-]?key|token|password|secret|credential[s]?)\s*[:=]\s*\S+", r"\1=[REDACTED]", valor)
    if len(valor) > 400:
        valor = valor[:400] + "..."
    return valor


def _chave_fernet() -> Fernet:
    chave = os.getenv("CLAUDE_TOKEN_ENC_KEY")
    if not chave:
        raise RuntimeError(
            "CLAUDE_TOKEN_ENC_KEY não configurada no .env — necessária para criptografar o "
            "token da conta Claude do piloto. Gere uma com Fernet.generate_key()."
        )
    return Fernet(chave.encode() if isinstance(chave, str) else chave)


def criptografar_token(token: str) -> str:
    return _chave_fernet().encrypt(token.strip().encode()).decode()


def descriptografar_token(valor: str) -> str:
    try:
        return _chave_fernet().decrypt(valor.encode()).decode()
    except InvalidToken as exc:
        raise ClaudeAccountError("AUTH_REQUIRED", MSG_AUTH_REQUIRED) from exc


class ClaudeAccountExecutor:
    """Ponto único de execução do Claude via conta individual do usuário (Tarefa 13).

    Nenhum outro módulo deve chamar o Claude Agent SDK diretamente — sempre
    passar por `execute()`.
    """

    async def execute(
        self,
        *,
        usuario_id: str,
        prompt: str,
        context: str = "",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> dict:
        conexao = obter_claude_connection(usuario_id)
        if not conexao or conexao["status"] != "ativo" or not conexao["oauth_token_encrypted"]:
            raise ClaudeAccountError("LOGIN_REQUIRED", MSG_LOGIN_REQUIRED)

        token = descriptografar_token(conexao["oauth_token_encrypted"])
        prompt_completo = f"{prompt}\n\n--- TRANSCRIÇÃO ---\n{context}" if context else prompt

        resultado_texto = await self._executar_query(usuario_id, prompt_completo, token, timeout)

        try:
            resultado = _extract_json(resultado_texto)
        except Exception as exc:
            raise ClaudeAccountError(
                "GENERIC_ERROR", MSG_GENERIC_ERROR, detalhe=sanitizar_erro_claude(str(exc))
            ) from exc

        registrar_uso_claude_connection(usuario_id)
        return resultado

    async def _executar_query(self, usuario_id: str, prompt: str, token: str, timeout: float) -> str:
        # Import tardio: mantém o app subindo mesmo em ambientes onde o CLI
        # @anthropic-ai/claude-code / o pacote claude-agent-sdk ainda não
        # foram instalados (o piloto fica indisponível via feature flag).
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            CLINotFoundError,
            ProcessError,
            RateLimitEvent,
            ResultMessage,
            TextBlock,
            query,
        )

        options = ClaudeAgentOptions(
            system_prompt=None,
            allowed_tools=[],
            max_turns=1,
            env={"CLAUDE_CODE_OAUTH_TOKEN": token},
            # Serviços systemd costumam ter PATH restrito e podem não achar o
            # binário `claude` instalado via npm global — permite apontar um
            # caminho absoluto pelo .env sem precisar mexer no unit file.
            cli_path=os.getenv("CLAUDE_CLI_PATH") or None,
        )

        texto_final: Optional[str] = None
        custo_usd = 0.0
        limite_atingido = False

        try:
            async with asyncio.timeout(timeout):
                async for mensagem in query(prompt=prompt, options=options):
                    if isinstance(mensagem, RateLimitEvent):
                        if mensagem.rate_limit_info and mensagem.rate_limit_info.status == "rejected":
                            limite_atingido = True
                    elif isinstance(mensagem, AssistantMessage):
                        for bloco in mensagem.content:
                            if isinstance(bloco, TextBlock):
                                texto_final = (texto_final or "") + bloco.text
                    elif isinstance(mensagem, ResultMessage):
                        custo_usd = mensagem.total_cost_usd or 0.0
                        if mensagem.result:
                            texto_final = mensagem.result
                        if mensagem.is_error:
                            detalhe = sanitizar_erro_claude(str(mensagem.result or mensagem.subtype or ""))
                            self._levantar_erro_classificado(usuario_id, detalhe, limite_atingido)
        except TimeoutError as exc:
            raise ClaudeAccountError("GENERIC_ERROR", "A análise excedeu o tempo limite. Tente novamente.") from exc
        except CLINotFoundError as exc:
            logger.error("[ClaudeAccount] CLI do Claude Code não encontrado no servidor: %s", exc)
            raise ClaudeAccountError("GENERIC_ERROR", MSG_CLI_MISSING) from exc
        except ProcessError as exc:
            detalhe = sanitizar_erro_claude(exc.stderr or str(exc))
            self._levantar_erro_classificado(usuario_id, detalhe, limite_atingido)
        except ClaudeAccountError:
            raise
        except Exception as exc:
            detalhe = sanitizar_erro_claude(str(exc))
            logger.warning("[ClaudeAccount] Falha inesperada para usuario_id=%s: %s", usuario_id, detalhe)
            raise ClaudeAccountError("GENERIC_ERROR", MSG_GENERIC_ERROR, detalhe=detalhe) from exc

        if limite_atingido and not texto_final:
            raise ClaudeAccountError("USAGE_LIMIT_REACHED", MSG_USAGE_LIMIT)
        if not texto_final:
            raise ClaudeAccountError("GENERIC_ERROR", MSG_GENERIC_ERROR, detalhe="Resposta vazia do Claude.")

        logger.info(
            "[ClaudeAccount] Análise concluída para usuario_id=%s (custo estimado: US$ %.4f).",
            usuario_id,
            custo_usd,
        )
        return texto_final

    @staticmethod
    def _levantar_erro_classificado(usuario_id: str, detalhe: str, limite_atingido: bool) -> None:
        if limite_atingido or _PADROES_LIMITE.search(detalhe):
            raise ClaudeAccountError("USAGE_LIMIT_REACHED", MSG_USAGE_LIMIT, detalhe=detalhe)
        if _PADROES_AUTH.search(detalhe):
            marcar_status_claude_connection(usuario_id, "expirado")
            raise ClaudeAccountError("AUTH_REQUIRED", MSG_AUTH_REQUIRED, detalhe=detalhe)
        raise ClaudeAccountError("GENERIC_ERROR", MSG_GENERIC_ERROR, detalhe=detalhe)


claude_account_executor = ClaudeAccountExecutor()
