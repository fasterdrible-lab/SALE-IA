"""
services/knowledge_compiler/extractors/pdf.py — extrator de PDF.

Estratégia: pypdf primeiro (rápido, cobre a maioria dos PDFs textuais). Se
o rendimento de texto for muito baixo (indício de PDF escaneado/imagem, ou
de um encoding de fonte que o pypdf não decodifica bem), tenta pdfplumber
como segunda tentativa.

Seções: tentamos detectar headings por tamanho de fonte via pdfplumber
(linhas cuja fonte é visivelmente maior que a mediana do documento viram
título de seção nova). Quando isso não é possível (documento sem essa
variação, ou pdfplumber indisponível), cada página do PDF vira 1 seção —
pior que headings reais, mas ainda assim dá chunking melhor que
"documento inteiro = 1 seção" para um livro de centenas de páginas.
"""
import io
import statistics

from services.knowledge_compiler.extractors.base import DocumentExtractor
from services.knowledge_compiler.schemas import DocumentSection, ExtractedDocument

_MIN_CHARS_POR_PAGINA_OK = 20


class PdfExtractor(DocumentExtractor):
    def supports(self, mime_type: str, filename: str) -> bool:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return ext == "pdf" or mime_type == "application/pdf"

    def extract(self, conteudo: bytes) -> ExtractedDocument:
        paginas = _extrair_com_pypdf(conteudo)
        media_chars = (sum(len(p) for p in paginas) / len(paginas)) if paginas else 0
        extrator_usado = "pypdf"

        if media_chars < _MIN_CHARS_POR_PAGINA_OK:
            paginas_plumber = _extrair_com_pdfplumber(conteudo)
            if sum(len(p) for p in paginas_plumber) > sum(len(p) for p in paginas):
                paginas = paginas_plumber
                extrator_usado = "pdfplumber"

        sections = _secoes_por_fonte(conteudo) or _secoes_por_pagina(paginas)
        texto = "\n\n".join(paginas)

        return ExtractedDocument(
            text=texto,
            metadata={
                "paginas": len(paginas),
                "extrator": extrator_usado,
                "possivelmente_escaneado": not texto.strip(),
            },
            sections=sections,
        )


def _extrair_com_pypdf(conteudo: bytes) -> list[str]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(conteudo))
        return [(page.extract_text() or "") for page in reader.pages]
    except Exception:
        return []


def _extrair_com_pdfplumber(conteudo: bytes) -> list[str]:
    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
            return [(page.extract_text() or "") for page in pdf.pages]
    except Exception:
        return []


def _secoes_por_pagina(paginas: list[str]) -> list[DocumentSection]:
    sections = []
    for i, texto in enumerate(paginas):
        texto = texto.strip()
        if texto:
            sections.append(DocumentSection(id=i, title=f"Página {i + 1}", content=texto, level=1, order=i))
    return sections


def _agrupar_linhas(chars: list[dict]) -> list[tuple[str, float]]:
    """Agrupa caracteres de uma página do pdfplumber em linhas (mesma
    coordenada 'top', arredondada) e retorna [(texto_da_linha, tamanho_medio)]."""
    if not chars:
        return []
    linhas: dict[int, list[dict]] = {}
    for c in chars:
        linhas.setdefault(round(c["top"]), []).append(c)

    resultado = []
    for chave in sorted(linhas.keys()):
        grupo = sorted(linhas[chave], key=lambda c: c["x0"])
        texto = "".join(c["text"] for c in grupo).strip()
        if texto:
            resultado.append((texto, statistics.mean(c["size"] for c in grupo)))
    return resultado


def _secoes_por_fonte(conteudo: bytes) -> list[DocumentSection] | None:
    try:
        import pdfplumber
    except ImportError:
        return None

    try:
        with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
            tamanhos = [round(c["size"]) for page in pdf.pages for c in page.chars]
            if not tamanhos:
                return None
            limiar_heading = statistics.median(tamanhos) + 2

            sections: list[DocumentSection] = []
            ordem = 0
            titulo_atual = "Documento"
            buffer: list[str] = []

            def fechar_secao():
                nonlocal buffer, ordem, titulo_atual
                texto = "\n".join(buffer).strip()
                if texto:
                    sections.append(DocumentSection(
                        id=ordem, title=titulo_atual, content=texto, level=1, order=ordem,
                    ))
                    ordem += 1
                buffer = []

            for page in pdf.pages:
                for linha_texto, tamanho_medio in _agrupar_linhas(page.chars):
                    if tamanho_medio >= limiar_heading and len(linha_texto) < 120:
                        fechar_secao()
                        titulo_atual = linha_texto
                    else:
                        buffer.append(linha_texto)

            fechar_secao()
        return sections or None
    except Exception:
        return None
