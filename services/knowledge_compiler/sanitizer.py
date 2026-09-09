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
    # Instrução para ignorar/desconsiderar regras — PT e EN, com variações
    re.compile(r"ignor[ae].{0,30}(instru|instruc)", re.IGNORECASE),
    re.compile(r"desconsider[ae].{0,30}(instru|regra)", re.IGNORECASE),
    re.compile(r"esque[çc]a.{0,30}(instru|regra)", re.IGNORECASE),
    re.compile(r"disregard.{0,30}(instruction|rule|previous)", re.IGNORECASE),
    re.compile(r"forget.{0,30}(previous|above|instruction)", re.IGNORECASE),
    # Marcadores de papel/role — inclui "user" além de system/assistant/developer
    re.compile(r"^\s*system\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*assistant\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*developer\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*user\s*:", re.IGNORECASE | re.MULTILINE),
    # Troca de persona/identidade do modelo
    re.compile(r"you are now", re.IGNORECASE),
    re.compile(r"from now on you (are|will)", re.IGNORECASE),
    re.compile(r"voc[eê]\s+agora\s+[eé]", re.IGNORECASE),
    re.compile(r"a partir de agora,?\s+voc[eê]\s+(é|e|vai|deve)", re.IGNORECASE),
    re.compile(r"new instructions?\s*:", re.IGNORECASE),
    re.compile(r"novas?\s+instru[çc][õo]es\s*:", re.IGNORECASE),
    # Tentativa de exfiltrar o prompt de sistema real
    re.compile(r"reveal (your |the )?(system )?prompt", re.IGNORECASE),
    re.compile(r"revele\s+(seu|o)\s+prompt", re.IGNORECASE),
    re.compile(r"print (your |the )?system prompt", re.IGNORECASE),
    # Marcadores de formato usados em jailbreaks/templates de chat
    re.compile(r"\[/?INST\]"),
    re.compile(r"<\|im_(start|end)\|>"),
    re.compile(r"-{5,}\s*BEGIN\s+(SYSTEM|PROMPT)", re.IGNORECASE),
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
