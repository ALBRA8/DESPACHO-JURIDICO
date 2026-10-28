"""
CORRELATION CONTEXT — request-scoped tracing IDs for end-to-end observability.

Block 4 of HARDENING-2. Provides a small, dependency-free correlation primitive
that travels with every request and is embedded in audit + log entries:

    CorrelationContext
        request_id      — per-request, freshly generated
        correlation_id  — stable across a logical conversation / matter
        matter_id       — optional, the legal matter this request belongs to
        agent_id        — optional, the agent that handled the request
        tool_id         — optional, the tool that was invoked

The current context is stored in thread-local storage (threading.local) so
synchronous code can read it without passing it through every function
signature. We use thread-local (not contextvars) deliberately to keep the
behavior predictable in plain synchronous test runs; contextvars would also
work, but thread-local is the lowest-common-denominator and the module exposes
a clean API that can be backed by either in the future.

Key design rules:
- generate_request_id() returns a 32-char UUID hex string (no dashes).
- propagate_context(parent, **overrides) inherits every field from parent,
  then applies overrides. request_id is ALWAYS regenerated on propagation
  (a child request is a new request, even if it shares the correlation_id).
- get_current_context() returns None when no context has been set in the
  current thread.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorrelationContext:
    """Per-request correlation identifiers.

    `frozen=True` so a context, once published, cannot be mutated by callers —
    propagation creates a new instance rather than editing in place. This is a
    security/audit hygiene property: the IDs that were stamped on a log line
    cannot be retroactively changed by a downstream component.
    """

    request_id: str = field(default_factory=lambda: generate_request_id())
    correlation_id: str = ""
    matter_id: str = ""
    agent_id: str = ""
    tool_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a dict suitable for embedding in audit/log entries.

        Empty fields are still emitted so downstream consumers can distinguish
        "field explicitly empty" from "field absent".
        """
        return asdict(self)

    def with_request_id(self, request_id: str) -> "CorrelationContext":
        """Return a copy with a new request_id (used by propagate_context)."""
        return CorrelationContext(
            request_id=request_id,
            correlation_id=self.correlation_id,
            matter_id=self.matter_id,
            agent_id=self.agent_id,
            tool_id=self.tool_id,
        )


# ---------------------------------------------------------------------------
# Generators + propagation
# ---------------------------------------------------------------------------


def generate_request_id() -> str:
    """Generate a fresh request_id (32-char UUID hex, no dashes)."""
    return uuid.uuid4().hex


def propagate_context(
    parent: CorrelationContext,
    **overrides: str,
) -> CorrelationContext:
    """Create a child context from `parent`, applying overrides.

    Rules:
    - `request_id` is ALWAYS regenerated unless the caller explicitly passes
      `request_id=...` in overrides. A child operation is a new request.
    - `correlation_id` is inherited from parent UNLESS the parent's
      correlation_id is empty AND the caller did not pass one — in which case
      the child's request_id is promoted to correlation_id (bootstraps a new
      correlation chain).
    - `matter_id`, `agent_id`, `tool_id` are inherited from parent unless
      overridden.
    """
    # Start from parent's values.
    new_request_id = overrides.pop("request_id", None) or generate_request_id()
    correlation_id = overrides.pop("correlation_id", parent.correlation_id)
    if not correlation_id:
        # Bootstrap: a child without an inherited correlation_id adopts its
        # own request_id as the correlation_id so the chain has a stable root.
        correlation_id = new_request_id
    matter_id = overrides.pop("matter_id", parent.matter_id)
    agent_id = overrides.pop("agent_id", parent.agent_id)
    tool_id = overrides.pop("tool_id", parent.tool_id)

    # Any leftover overrides are ignored silently — callers should only pass
    # the documented fields. We don't raise to keep propagation forgiving.
    # (If a typo'd key were to crash propagation, an entire request would fail
    # for a logging-only concern — not acceptable.)

    return CorrelationContext(
        request_id=new_request_id,
        correlation_id=correlation_id,
        matter_id=matter_id,
        agent_id=agent_id,
        tool_id=tool_id,
    )


# ---------------------------------------------------------------------------
# Thread-local storage
# ---------------------------------------------------------------------------


_thread_local = threading.local()


def set_current_context(ctx: CorrelationContext | None) -> None:
    """Set the current thread's correlation context.

    Passing None clears the context for this thread.
    """
    _thread_local.ctx = ctx


def get_current_context() -> CorrelationContext | None:
    """Return this thread's current correlation context, or None if unset."""
    return getattr(_thread_local, "ctx", None)


def clear_current_context() -> None:
    """Clear the current thread's correlation context (test helper)."""
    _thread_local.ctx = None


# ---------------------------------------------------------------------------
# Audit-entry helper
# ---------------------------------------------------------------------------


def correlation_in_audit_entry(
    entry: dict[str, Any],
    ctx: CorrelationContext | None = None,
) -> dict[str, Any]:
    """Stamp a copy of `entry` with the correlation IDs from `ctx`.

    If `ctx` is None, the current thread's context is used; if that is also
    None, the entry is returned unchanged (we don't invent IDs — fail-open for
    observability, never block an audit write on missing correlation).

    The returned dict is a SHALLOW copy of `entry` with the correlation fields
    merged in. We don't deep-copy: audit entries are typically flat.
    """
    actual_ctx = ctx if ctx is not None else get_current_context()
    if actual_ctx is None:
        return dict(entry)
    stamped = dict(entry)
    stamped.update(actual_ctx.as_dict())
    return stamped
