"""
services/observability/provider.py — Interface ObservabilityProvider

Camada de abstração para rastreamento de trace/span da análise em tempo
real (Sprint 1 — Langfuse). Módulos de negócio (AI Router, orquestrador
multiagente, Skill Resolver) não devem conhecer qual backend
(Langfuse, NoOp, ...) está recebendo as observações — apenas chamam
`get_observability_provider()` (em factory.py) e usam a interface abaixo.

Paralelo, não substituto, do Cost Intelligence (api/cost_engine.py,
api/database.py::AiUsageEvent) — esta camada nunca calcula custo, só lê
valores que api/ai_router.py::chamar_ia já computou, para visualização
em trace no Langfuse.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Optional, Union

logger = logging.getLogger("saleia.observability")


class ObservabilityProviderError(Exception):
    """Erro de configuração (ex.: OBSERVABILITY_PROVIDER desconhecido,
    chaves do Langfuse ausentes).

    Nunca deve ser levantado para falha de rede/runtime — apenas para
    configuração inválida, detectável na criação do provider.
    """


@dataclass
class TraceHandle:
    id: str
    provider: str
    _native: Any = None
    _token: Optional[Token] = field(default=None, repr=False)


@dataclass
class SpanHandle:
    id: str
    provider: str
    trace_id: Optional[str] = None
    parent_id: Optional[str] = None
    _native: Any = None
    _token: Optional[Token] = field(default=None, repr=False)


Observation = Union[TraceHandle, SpanHandle]

# ContextVar própria (não do SDK do Langfuse) — carrega a "observação
# atual" através de fronteiras async: asyncio.gather cria uma Task por
# coroutine (cada uma com cópia própria do contexto) e asyncio.to_thread
# também copia o contexto pro worker thread, então um span iniciado
# dentro de cada agente (Coach/DISC/Finance/Closer) fica isolado por
# task, sem vazar entre eles nem exigir mudar assinatura de chamar_ia.
_current_observation: ContextVar[Optional[Observation]] = ContextVar(
    "saleia_observability_current", default=None
)


def get_current_observation() -> Optional[Observation]:
    return _current_observation.get()


def _push_observation(observation: Observation) -> None:
    observation._token = _current_observation.set(observation)


def _pop_observation(observation: Observation) -> None:
    if observation._token is not None:
        try:
            _current_observation.reset(observation._token)
        except Exception:
            pass


class ObservabilityProvider(ABC):
    """Interface comum a todos os backends de observabilidade."""

    @abstractmethod
    def start_trace(
        self,
        *,
        name: str,
        meeting_id: Optional[str] = None,
        usuario_id: Optional[str] = None,
        input: Optional[dict] = None,
        metadata: Optional[dict] = None,
    ) -> TraceHandle:
        """Inicia uma trace raiz (um ciclo de análise em tempo real).
        Nunca lança — falha interna deve devolver um handle inerte."""
        ...

    @abstractmethod
    def end_trace(
        self,
        trace: TraceHandle,
        *,
        output: Optional[dict] = None,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        ...

    @abstractmethod
    def start_span(
        self,
        *,
        name: str,
        parent: Optional[Observation] = None,
        meeting_id: Optional[str] = None,
        input: Optional[dict] = None,
        metadata: Optional[dict] = None,
    ) -> SpanHandle:
        """`parent` default = get_current_observation() se omitido."""
        ...

    @abstractmethod
    def end_span(
        self,
        span: SpanHandle,
        *,
        output: Optional[dict] = None,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        ...

    @abstractmethod
    def record_generation(
        self,
        *,
        feature: str,
        provider: str,
        model: Optional[str],
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
        latency_ms: Optional[int] = None,
        success: bool,
        error: Optional[str] = None,
        fallback_used: bool = False,
        cache_hit: bool = False,
        meeting_id: Optional[str] = None,
        usuario_id: Optional[str] = None,
    ) -> None:
        """Observação-folha (start+end em uma chamada) para uma chamada
        de IA já concluída — nunca recalcula custo, só reporta valores
        que api/ai_router.py::chamar_ia já tem em escopo."""
        ...

    @abstractmethod
    def record_retrieval(
        self,
        *,
        source: str,
        query: str,
        result_count: int,
        preview: Optional[str] = None,
        meeting_id: Optional[str] = None,
    ) -> None:
        ...

    @abstractmethod
    def record_score(
        self,
        *,
        name: str,
        value: float,
        comment: Optional[str] = None,
        meeting_id: Optional[str] = None,
    ) -> None:
        ...
