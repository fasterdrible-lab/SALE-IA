"""
services/knowledge_compiler/sanitizer.py

Sanitização de texto extraído de documentos de terceiros antes de ele
circular pelo resto do Knowledge Compiler. O texto de um documento é DADO,
nunca instrução: este módulo remove só ruído técnico inequívoco (unicode
invisível/controle) e MARCA — nunca apaga — trechos que parecem tentativa
de prompt injection, para que fases futuras bloqueiem isso de virar
instrução de sistema sem revisão humana.

Detecção de injection (Tarefa 18.2 do "PROMPT MESTRE — SALE-IA V2")
reaproveitada de `agent/prompt_injection_rules.py` — mesmo detector usado
para transcrições em tempo real, nunca duplicado aqui.
"""
import unicodedata

from agent.prompt_injection_rules import INJECTION_FLAG, contem_tentativa_injection

_PRESERVAR = ("\n", "\t", "\r")


def sanitize_document_text(text: str) -> tuple[str, list[str]]:
    """Remove caracteres de controle/formatação invisíveis (categorias
    Unicode "C*": Cc, Cf, Co, Cs) e sinaliza trechos que parecem prompt
    injection, sem removê-los.

    Returns:
        (texto_limpo, flags) — flags contém INJECTION_FLAG se algum padrão
        suspeito foi encontrado em qualquer lugar do texto.
    """
    if not text:
        return "", []

    limpo = "".join(
        ch for ch in text
        if ch in _PRESERVAR or not unicodedata.category(ch).startswith("C")
    )

    flags: list[str] = [INJECTION_FLAG] if contem_tentativa_injection(limpo) else []

    return limpo, flags
