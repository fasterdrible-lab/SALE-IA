"""
services/observability/langfuse_provider.py — ObservabilityProvider via
Langfuse Cloud (Sprint 1).

`langfuse` (SDK v4) so e importado dentro deste arquivo — nunca em
__init__.py/factory.py — para que a ausencia do pacote ou de config
nunca quebre o app quando OBSERVABILITY_ENABLED=false (NoOp e usado).

Escopo desta sprint: so o ciclo /tempo-real gera trace. Chamadas de
record_generation/record_retrieval/record_score sem uma observacao atual
no contexto (get_current_observation() -> None) sao ignoradas de
proposito — nao fabricam uma trace solta fora do ciclo instrumentado.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from .provider import (
    Observation,
    ObservabilityProvider,
    ObservabilityProviderError,
    SpanHandle,
    TraceHandle,
    _pop_observation,
    _push_observation,
    get_current_observation,
)

logger = logging.getLogger("saleia.observability")


class LangfuseObservabilityProvider(ObservabilityProvider):
    def __init__(self) -> None:
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
        secret_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
        if not public_key or not secret_key:
            raise ObservabilityProviderError(
                "LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY nao configuradas."
            )
        host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com").strip()

        from langfuse import Langfuse  # import tardio de proposito

        self._client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)

    def _propagate(self, *, usuario_id: Optional[str], meeting_id: Optional[str], metadata: Optional[dict]):
        from langfuse import propagate_attributes

        return propagate_attributes(
            user_id=usuario_id or None,
            session_id=meeting_id or None,
            metadata=metadata or {},
        )

    # ── Trace ──

    def start_trace(self, *, name: str, meeting_id=None, usuario_id=None, input=None, metadata=None) -> TraceHandle:
        try:
            with self._propagate(usuario_id=usuario_id, meeting_id=meeting_id, metadata=metadata):
                native = self._client.start_observation(name=name, as_type="span", input=input or {})
            trace = TraceHandle(id=str(getattr(native, "id", name)), provider="langfuse", _native=native)
            _push_observation(trace)
            return trace
        except Exception as exc:
            logger.debug("[Observability/Langfuse] start_trace falhou: %s", exc)
            trace = TraceHandle(id="err", provider="langfuse", _native=None)
            _push_observation(trace)
            return trace

    def end_trace(self, trace: TraceHandle, *, output=None, success: bool = True, error=None) -> None:
        try:
            if trace._native is not None:
                trace._native.update(output=output or {}, level="DEFAULT" if success else "ERROR",
                                      status_message=error)
                trace._native.end()
        except Exception as exc:
            logger.debug("[Observability/Langfuse] end_trace falhou: %s", exc)
        finally:
            _pop_observation(trace)

    # ── Span ──

    def start_span(self, *, name: str, parent: Optional[Observation] = None, meeting_id=None, input=None, metadata=None) -> SpanHandle:
        parent = parent or get_current_observation()
        try:
            parent_native = getattr(parent, "_native", None)
            base = parent_native if parent_native is not None else self._client
            native = base.start_observation(name=name, as_type="span", input=input or {}, metadata=metadata or {})
            span = SpanHandle(
                id=str(getattr(native, "id", name)), provider="langfuse", _native=native,
                trace_id=getattr(parent, "trace_id", None) or getattr(parent, "id", None),
                parent_id=getattr(parent, "id", None),
            )
            _push_observation(span)
            return span
        except Exception as exc:
            logger.debug("[Observability/Langfuse] start_span falhou (%s): %s", name, exc)
            span = SpanHandle(id="err", provider="langfuse", _native=None)
            _push_observation(span)
            return span

    def end_span(self, span: SpanHandle, *, output=None, success: bool = True, error=None) -> None:
        try:
            if span._native is not None:
                span._native.update(output=output or {}, level="DEFAULT" if success else "ERROR",
                                     status_message=error)
                span._native.end()
        except Exception as exc:
            logger.debug("[Observability/Langfuse] end_span falhou: %s", exc)
        finally:
            _pop_observation(span)

    # ── Generation (leaf) ──

    def record_generation(self, *, feature: str, provider: str, model, prompt_tokens: int = 0,
                           completion_tokens: int = 0, cost_usd: float = 0.0, latency_ms=None,
                           success: bool, error=None, fallback_used: bool = False,
                           cache_hit: bool = False, meeting_id=None, usuario_id=None) -> None:
        parent = get_current_observation()
        parent_native = getattr(parent, "_native", None)
        if parent_native is None:
            return  # fora do ciclo instrumentado — nao fabrica trace solta
        try:
            gen = parent_native.start_observation(
                name=f"generation.{feature}", as_type="generation", model=model,
                metadata={"feature": feature, "provider": provider, "fallback_used": fallback_used,
                          "cache_hit": cache_hit, "latency_ms": latency_ms},
            )
            gen.update(
                usage_details={"input": prompt_tokens, "output": completion_tokens},
                cost_details={"input": cost_usd if completion_tokens == 0 else 0.0,
                              "output": 0.0, "total": cost_usd},
                level="DEFAULT" if success else "ERROR",
                status_message=error,
            )
            gen.end()
        except Exception as exc:
            logger.debug("[Observability/Langfuse] record_generation falhou (%s): %s", feature, exc)

    # ── Retrieval / score (leaf) ──

    def record_retrieval(self, *, source: str, query: str, result_count: int, preview=None, meeting_id=None) -> None:
        parent = get_current_observation()
        parent_native = getattr(parent, "_native", None)
        if parent_native is None:
            return
        try:
            span = parent_native.start_observation(
                name=f"retrieval.{source}", as_type="span",
                input={"query_chars": len(query or "")},
                metadata={"source": source, "result_count": result_count,
                          "preview": (preview or "")[:500]},
            )
            span.end()
        except Exception as exc:
            logger.debug("[Observability/Langfuse] record_retrieval falhou (%s): %s", source, exc)

    def record_score(self, *, name: str, value: float, comment=None, meeting_id=None) -> None:
        parent = get_current_observation()
        parent_native = getattr(parent, "_native", None)
        if parent_native is None:
            return
        try:
            parent_native.score(name=name, value=value, comment=comment)
        except Exception as exc:
            logger.debug("[Observability/Langfuse] record_score falhou (%s): %s", name, exc)
