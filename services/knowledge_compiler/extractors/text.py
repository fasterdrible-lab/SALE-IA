"""
services/knowledge_compiler/extractors/text.py — extrator para TXT e
Markdown. Em Markdown, seções são delimitadas por headings (# / ## / ###);
em TXT puro (sem headings), o documento inteiro vira uma única seção.
"""
import re

from services.knowledge_compiler.extractors.base import DocumentExtractor
from services.knowledge_compiler.schemas import DocumentSection, ExtractedDocument

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)


class TextExtractor(DocumentExtractor):
    def supports(self, mime_type: str, filename: str) -> bool:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return ext in ("txt", "md", "markdown") or mime_type in ("text/plain", "text/markdown")

    def extract(self, conteudo: bytes) -> ExtractedDocument:
        texto = conteudo.decode("utf-8", errors="replace")
        if _HEADING_RE.search(texto):
            sections = _dividir_por_headings(texto)
        else:
            sections = _secao_unica(texto)
        return ExtractedDocument(text=texto, metadata={}, sections=sections)


def _dividir_por_headings(texto: str) -> list[DocumentSection]:
    matches = list(_HEADING_RE.finditer(texto))
    sections: list[DocumentSection] = []
    for i, m in enumerate(matches):
        inicio = m.end()
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(texto)
        sections.append(DocumentSection(
            id=i, title=m.group(2).strip(), content=texto[inicio:fim].strip(),
            level=len(m.group(1)), order=i,
        ))
    return sections


def _secao_unica(texto: str) -> list[DocumentSection]:
    if not texto.strip():
        return []
    return [DocumentSection(id=0, title="Documento", content=texto.strip(), level=1, order=0)]
