"""
services/observability/noop_provider.py — ObservabilityProvider inerte.

Usado quando OBSERVABILITY_ENABLED=false (padrao) — a aplicacao chama a
mesma interface, sem nenhum `if habilitado:` espalhado pelo codigo, e
nada acontece. Nunca importa `langfuse`.
"""
from __future__ import annotations

from typing import Optional

from .provider import (
    Observation,
    ObservabilityProvider,
    SpanHandle,
    TraceHandle,
    _pop_observation,
    _push_observation,
    get_current_observation,
)

_COUNTER = 0


def _next_id(prefix: str) -> str:
    global _COUNTER
    _COUNTER += 1
    return f"{prefix}_noop_{_COUNTER}"


class NoOpObservabilityProvider(ObservabilityProvider):
    def start_trace(self, *, name: str, meeting_id=None, usuario_id=None, input=None, metadata=None) -> TraceHandle:
        trace = TraceHandle(id=_next_id("trace"), provider="noop")
        _push_observation(trace)
        return trace

    def end_trace(self, trace: TraceHandle, *, output=None, success: bool = True, error=None) -> None:
        _pop_observation(trace)

    def start_span(self, *, name: str, parent: Optional[Observation] = None, meeting_id=None, input=None, metadata=None) -> SpanHandle:
        parent = parent or get_current_observation()
        span = SpanHandle(
            id=_next_id("span"),
            provider="noop",
            trace_id=getattr(parent, "trace_id", None) or getattr(parent, "id", None),
            parent_id=getattr(parent, "id", None),
        )
        _push_observation(span)
        return span

    def end_span(self, span: SpanHandle, *, output=None, success: bool = True, error=None) -> None:
        _pop_observation(span)

    def record_generation(self, *, feature: str, provider: str, model, prompt_tokens: int = 0,
                           completion_tokens: int = 0, cost_usd: float = 0.0, latency_ms=None,
                           success: bool, error=None, fallback_used: bool = False,
                           cache_hit: bool = False, meeting_id=None, usuario_id=None) -> None:
        pass

    def record_retrieval(self, *, source: str, query: str, result_count: int, preview=None, meeting_id=None) -> None:
        pass

    def record_score(self, *, name: str, value: float, comment=None, meeting_id=None) -> None:
        pass
