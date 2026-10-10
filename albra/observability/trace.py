"""
Tracer simple - soporta spans anidados para trazabilidad de tareas.
"""
from __future__ import annotations

import time
import uuid
from contextvars import ContextVar
from typing import Any

_current_trace: ContextVar[dict[str, Any] | None] = ContextVar("albra_trace", default=None)


class Span:
    def __init__(self, name: str, parent_id: str | None = None, **attrs: Any) -> None:
        self.span_id = uuid.uuid4().hex[:16]
        self.parent_id = parent_id
        self.name = name
        self.attrs = attrs
        self.start = time.time()
        self.end: float | None = None
        self.events: list[dict[str, Any]] = []

    def add_event(self, name: str, **attrs: Any) -> None:
        self.events.append({"name": name, "ts": time.time(), **attrs})

    def finish(self) -> None:
        self.end = time.time()

    def as_dict(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "attrs": self.attrs,
            "start": self.start,
            "end": self.end,
            "duration_s": (self.end - self.start) if self.end else None,
            "events": self.events,
        }


class Tracer:
    """Tracer en memoria - guardar traces en archivo para audit."""

    def __init__(self) -> None:
        self._spans: list[Span] = []

    def span(self, name: str, **attrs: Any) -> span:  # type: ignore[name-defined]
        parent = _current_trace.get()
        parent_id = parent["span_id"] if parent else None
        sp = Span(name, parent_id=parent_id, **attrs)
        self._spans.append(sp)

        import contextlib

        @contextlib.contextmanager
        def _ctx():
            token = _current_trace.set({"span_id": sp.span_id})
            try:
                yield sp
            finally:
                sp.finish()
                _current_trace.reset(token)

        return _ctx()

    def all_spans(self) -> list[dict[str, Any]]:
        return [s.as_dict() for s in self._spans]

    def clear(self) -> None:
        self._spans.clear()


_tracer: Tracer | None = None


def get_tracer() -> Tracer:
    global _tracer
    if _tracer is None:
        _tracer = Tracer()
    return _tracer


def span(name: str, **attrs: Any):
    """Decorator/context manager para crear un span."""
    return get_tracer().span(name, **attrs)
