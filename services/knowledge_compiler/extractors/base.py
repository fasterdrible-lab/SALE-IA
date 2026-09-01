"""
services/knowledge_compiler/extractors/base.py — contrato comum dos
extratores determinísticos de texto (Fase 1: sem IA, LLM nunca abre o
arquivo diretamente).
"""
from abc import ABC, abstractmethod

from services.knowledge_compiler.schemas import ExtractedDocument


class DocumentExtractor(ABC):
    @abstractmethod
    def supports(self, mime_type: str, filename: str) -> bool:
        ...

    @abstractmethod
    def extract(self, conteudo: bytes) -> ExtractedDocument:
        ...
