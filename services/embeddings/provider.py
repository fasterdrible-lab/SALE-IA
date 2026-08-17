"""
services/embeddings/provider.py — Interface EmbeddingProvider

Camada de abstração para geração de embeddings. Módulos de negócio (RAG,
Sales Memory, base de conhecimento) não devem conhecer qual serviço
(Ollama, OpenAI, ...) está gerando os vetores — apenas chamam
`get_embedding_provider()` (em factory.py) e usam a interface abaixo.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger("saleia.embeddings")


class EmbeddingProviderError(Exception):
    """Erro de configuração (ex.: EMBEDDING_PROVIDER desconhecido).

    Nunca deve ser silenciado por um fallback implícito — quem chama
    get_embedding_provider() e recebe esta exceção deve tratar
    explicitamente (logar e degradar), nunca escolher outro provedor
    sem que isso tenha sido configurado.
    """


@dataclass
class EmbeddingResult:
    vector: list[float]
    provider: str
    model: str
    dimension: int


class EmbeddingProvider(ABC):
    """Interface comum a todos os provedores de embedding."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...

    @property
    @abstractmethod
    def dimension(self) -> Optional[int]:
        """Dimensão dos vetores gerados. None se ainda não foi possível
        confirmar (ex.: provedor local nunca respondeu com sucesso)."""
        ...

    @abstractmethod
    def embed(self, text: str) -> Optional[EmbeddingResult]:
        """Gera embedding de forma síncrona. Retorna None em falha
        recuperável (nunca lança para erros de rede/timeout — apenas
        para erros de configuração, que são EmbeddingProviderError)."""
        ...

    @abstractmethod
    async def embed_async(self, text: str) -> Optional[EmbeddingResult]:
        """Versão assíncrona de embed(). Mesmo contrato de retorno."""
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[Optional[EmbeddingResult]]:
        """Gera embeddings para uma lista de textos. Retorna lista do
        mesmo tamanho; falha em um item não impede os demais (item
        correspondente vem como None)."""
        ...

    @abstractmethod
    async def health_check(self, timeout: float = 5.0) -> dict:
        """Verifica conectividade e funcionamento do provedor.

        Async para poder ser chamado diretamente de um handler FastAPI
        (`await provider.health_check()`) sem bloquear o event loop —
        implementações reutilizam embed_async() internamente.

        Retorna:
            {"ok": bool, "detalhe": str, "dimension": int|None, "latency_ms": float|None}
        Nunca lança — falhas de rede/timeout viram {"ok": False, "detalhe": "..."}.
        """
        ...


def cosine_top_k(vec: np.ndarray, matrix: np.ndarray, k: int) -> list[tuple[int, float]]:
    """Retorna os índices dos k vetores de `matrix` mais similares a `vec` por cosseno.

    Consolidado a partir da implementação antes duplicada em
    agent/base_conhecimento.py e agent/sales_memory.py.
    """
    vec_norm = vec / (np.linalg.norm(vec) + 1e-9)
    mat_norm = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
    sims = mat_norm @ vec_norm
    top_indices = np.argsort(sims)[::-1][:k]
    return [(int(idx), float(sims[idx])) for idx in top_indices]


def is_dimension_compatible(query_dimension: Optional[int], cache_meta: Optional[dict]) -> bool:
    """Verifica se a dimensão do embedding de consulta é compatível com o
    cache carregado (mesma dimensão do que já está indexado).

    Retorna False (nunca lança) se:
    - query_dimension é None (provedor não confirmou dimensão)
    - cache_meta é None/vazio (nada indexado com metadados conhecidos)
    - as dimensões diferem
    """
    if not query_dimension or not cache_meta:
        return False
    cache_dim = cache_meta.get("dim")
    if not cache_dim:
        return False
    return int(cache_dim) == int(query_dimension)
