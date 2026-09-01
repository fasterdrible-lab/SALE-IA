"""
services/knowledge_compiler — Knowledge Compiler (Fase 1: extração
determinística de documentos + sanitização, sem IA).

Fluxo desta fase: documento bruto -> extractor determinístico -> texto +
seções -> sanitize_document_text(). Nenhuma chamada de IA acontece aqui —
compilação em conhecimento estruturado (frameworks/objeções/scripts) é a
Fase 2, ainda não implementada.
"""
from services.knowledge_compiler.extractors.base import DocumentExtractor
from services.knowledge_compiler.extractors.docx import DocxExtractor
from services.knowledge_compiler.extractors.html import HtmlExtractor
from services.knowledge_compiler.extractors.pdf import PdfExtractor
from services.knowledge_compiler.extractors.text import TextExtractor
from services.knowledge_compiler.sanitizer import INJECTION_FLAG, sanitize_document_text
from services.knowledge_compiler.schemas import DocumentSection, ExtractedDocument

_EXTRATORES: list[DocumentExtractor] = [
    PdfExtractor(),
    DocxExtractor(),
    HtmlExtractor(),
    TextExtractor(),
]


class ExtractorNotFoundError(Exception):
    pass


def get_extractor(mime_type: str, filename: str) -> DocumentExtractor:
    for extrator in _EXTRATORES:
        if extrator.supports(mime_type or "", filename or ""):
            return extrator
    raise ExtractorNotFoundError(f"Nenhum extrator suporta '{filename}' ({mime_type}).")


__all__ = [
    "DocumentExtractor",
    "DocumentSection",
    "ExtractedDocument",
    "ExtractorNotFoundError",
    "INJECTION_FLAG",
    "get_extractor",
    "sanitize_document_text",
]
