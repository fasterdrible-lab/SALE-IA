"""
services/knowledge_compiler/sanitizer.py

Sanitização de texto extraído de documentos de terceiros antes de ele
circular pelo resto do Knowledge Compiler. O texto de um documento é DADO,
nunca instrução: este módulo remove só ruído técnico inequívoco (unicode
invisível/controle) e MARCA — nunca apaga — trechos que parecem tentativa
de prompt injection, para que fases futuras bloqueiem isso de virar
instrução de sistema sem revisão humana.
"""
import re
import unicodedata

INJECTION_FLAG = "potential_instruction_injection"

_INJECTION_PATTERNS = [
    re.compile(r"ignor[ae].{0,30}(instru|instruc)", re.IGNORECASE),
    re.compile(r"^\s*system\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*assistant\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*developer\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"you are now", re.IGNORECASE),
    re.compile(r"voc[eê]\s+agora\s+[eé]", re.IGNORECASE),
]

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

    flags: list[str] = []
    if any(padrao.search(limpo) for padrao in _INJECTION_PATTERNS):
        flags.append(INJECTION_FLAG)

    return limpo, flags
