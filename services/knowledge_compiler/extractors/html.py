"""
services/knowledge_compiler/extractors/html.py — extrator HTML via
BeautifulSoup4. Seções são delimitadas por headings h1-h3.
"""
from bs4 import BeautifulSoup

from services.knowledge_compiler.extractors.base import DocumentExtractor
from services.knowledge_compiler.schemas import DocumentSection, ExtractedDocument

_HEADING_TAGS = ("h1", "h2", "h3")
_CONTEUDO_TAGS = _HEADING_TAGS + ("p", "li", "td")


class HtmlExtractor(DocumentExtractor):
    def supports(self, mime_type: str, filename: str) -> bool:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return ext in ("html", "htm") or mime_type == "text/html"

    def extract(self, conteudo: bytes) -> ExtractedDocument:
        soup = BeautifulSoup(conteudo, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()

        sections: list[DocumentSection] = []
        ordem = 0
        titulo_atual = "Documento"
        nivel_atual = 1
        buffer: list[str] = []

        def fechar_secao():
            nonlocal buffer, ordem
            texto = "\n".join(buffer).strip()
            if texto:
                sections.append(DocumentSection(
                    id=ordem, title=titulo_atual, content=texto, level=nivel_atual, order=ordem,
                ))
                ordem += 1
            buffer = []

        corpo = soup.body or soup
        for el in corpo.find_all(list(_CONTEUDO_TAGS)):
            texto_el = el.get_text(strip=True)
            if not texto_el:
                continue
            if el.name in _HEADING_TAGS:
                fechar_secao()
                titulo_atual = texto_el
                nivel_atual = int(el.name[1])
            else:
                buffer.append(texto_el)

        fechar_secao()

        texto_completo = "\n\n".join(s.content for s in sections)
        return ExtractedDocument(text=texto_completo, metadata={}, sections=sections)
