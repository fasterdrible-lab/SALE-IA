"""
services/knowledge_compiler/schemas.py — estruturas de dados da extração
determinística do Knowledge Compiler (Fase 1, sem IA).
"""
from dataclasses import dataclass, field


@dataclass
class DocumentSection:
    id: int
    title: str
    content: str
    level: int
    order: int


@dataclass
class ExtractedDocument:
    text: str
    metadata: dict
    sections: list[DocumentSection] = field(default_factory=list)
