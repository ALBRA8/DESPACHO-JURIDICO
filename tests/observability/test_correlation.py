"""Tests for albra.observability.correlation (HARDENING-2 Block 4)."""
from __future__ import annotations

import threading
from typing import Any

import pytest

from albra.observability.correlation import (
    CorrelationContext,
    clear_current_context,
    correlation_in_audit_entry,
    generate_request_id,
    get_current_context,
    propagate_context,
    set_current_context,
)

# ---------------------------------------------------------------------------
# Setup/teardown — ensure thread-local is clean before and after each test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_thread_local():
    clear_current_context()
    yield
    clear_current_context()


# ---------------------------------------------------------------------------
# generate_request_id
# ---------------------------------------------------------------------------


def test_generate_request_id_unique():
    """Two calls return distinct IDs (UUID hex, 32 chars, no dashes)."""
    a = generate_request_id()
    b = generate_request_id()
    assert a != b
    assert len(a) == 32
    assert "-" not in a
    # Must be hex.
    int(a, 16)  # raises ValueError if not hex


def test_generate_request_id_returns_hex_string():
    """request_id is a valid hex string."""
    rid = generate_request_id()
    assert isinstance(rid, str)
    assert all(c in "0123456789abcdef" for c in rid)


# ---------------------------------------------------------------------------
# propagate_context
# ---------------------------------------------------------------------------


def test_propagate_context_inherits_parent():
    """Child inherits parent's correlation_id/matter_id/agent_id/tool_id; new request_id."""
    parent = CorrelationContext(
        request_id="parent-request-id",
        correlation_id="corr-123",
        matter_id="M-001",
        agent_id="intake-agent",
        tool_id="lookup",
    )
    child = propagate_context(parent)
    assert child.request_id != "parent-request-id"
    assert child.request_id != ""
    assert child.correlation_id == "corr-123"
    assert child.matter_id == "M-001"
    assert child.agent_id == "intake-agent"
    assert child.tool_id == "lookup"


def test_propagate_context_overrides_matter_id():
    """Caller can override individual fields; others inherit from parent."""
    parent = CorrelationContext(
        request_id="parent-req",
        correlation_id="corr-root",
        matter_id="M-001",
        agent_id="intake-agent",
        tool_id="",
    )
    child = propagate_context(parent, matter_id="M-002", tool_id="draft-tool")
    assert child.matter_id == "M-002"
    assert child.tool_id == "draft-tool"
    # Un-overridden fields still inherited.
    assert child.correlation_id == "corr-root"
    assert child.agent_id == "intake-agent"


def test_propagate_context_bootstraps_correlation_id_when_empty():
    """If parent has no correlation_id, child's request_id becomes the correlation_id."""
    parent = CorrelationContext(
        request_id="parent-req",
        correlation_id="",
        matter_id="",
        agent_id="",
        tool_id="",
    )
    child = propagate_context(parent)
    assert child.correlation_id != ""
    assert child.correlation_id == child.request_id


def test_propagate_context_explicit_request_id_is_respected():
    """Caller can force a specific request_id through overrides."""
    parent = CorrelationContext(
        request_id="parent-req",
        correlation_id="corr-root",
    )
    child = propagate_context(parent, request_id="forced-req-id")
    assert child.request_id == "forced-req-id"
    assert child.correlation_id == "corr-root"


# ---------------------------------------------------------------------------
# Thread-local storage
# ---------------------------------------------------------------------------


def test_thread_local_storage():
    """Each thread has its own current context."""
    child_results: dict[str, Any] = {}

    def _worker(thread_label: str) -> None:
        ctx = CorrelationContext(
            request_id=f"req-{thread_label}",
            correlation_id=f"corr-{thread_label}",
            matter_id=f"M-{thread_label}",
        )
        set_current_context(ctx)
        # Simulate some work.
        import time as _t
        _t.sleep(0.01)
        current = get_current_context()
        child_results[thread_label] = current

    threads = [
        threading.Thread(target=_worker, args=(label,))
        for label in ("A", "B", "C")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Each thread should have observed its OWN context, not another's.
    assert child_results["A"].request_id == "req-A"
    assert child_results["B"].request_id == "req-B"
    assert child_results["C"].request_id == "req-C"
    # Main thread should still have None (we never set it).
    assert get_current_context() is None


def test_get_current_context_none_when_not_set():
    """No context set in this thread -> None."""
    assert get_current_context() is None


def test_set_and_clear_current_context():
    """set_current_context then clear_current_context round-trips."""
    ctx = CorrelationContext(
        request_id="round-trip-req",
        correlation_id="round-trip-corr",
        matter_id="M-RT",
    )
    set_current_context(ctx)
    current = get_current_context()
    assert current is not None
    assert current.request_id == "round-trip-req"
    assert current.correlation_id == "round-trip-corr"
    assert current.matter_id == "M-RT"
    clear_current_context()
    assert get_current_context() is None


# ---------------------------------------------------------------------------
# Audit entry stamping
# ---------------------------------------------------------------------------


def test_correlation_in_audit_entry_with_explicit_ctx():
    """Passing an explicit ctx stamps a copy of the entry; original untouched."""
    ctx = CorrelationContext(
        request_id="req-1",
        correlation_id="corr-1",
        matter_id="M-1",
        agent_id="intake-agent",
        tool_id="lookup",
    )
    entry = {"event": "tool_invoked", "ok": True}
    stamped = correlation_in_audit_entry(entry, ctx)
    assert stamped["event"] == "tool_invoked"
    assert stamped["ok"] is True
    assert stamped["request_id"] == "req-1"
    assert stamped["correlation_id"] == "corr-1"
    assert stamped["matter_id"] == "M-1"
    assert stamped["agent_id"] == "intake-agent"
    assert stamped["tool_id"] == "lookup"
    # Original entry must NOT be mutated.
    assert "request_id" not in entry
    assert "correlation_id" not in entry


def test_correlation_in_audit_entry_uses_thread_local_when_ctx_none():
    """When ctx=None, falls back to current thread context."""
    ctx = CorrelationContext(
        request_id="thread-req",
        correlation_id="thread-corr",
        matter_id="M-T",
    )
    set_current_context(ctx)
    entry = {"event": "matter_opened"}
    stamped = correlation_in_audit_entry(entry, ctx=None)
    assert stamped["request_id"] == "thread-req"
    assert stamped["correlation_id"] == "thread-corr"
    assert stamped["matter_id"] == "M-T"


def test_correlation_in_audit_entry_returns_copy_when_no_ctx():
    """When no ctx (explicit or thread-local), returns a copy of entry unchanged."""
    entry = {"event": "no_context"}
    stamped = correlation_in_audit_entry(entry)
    assert stamped == {"event": "no_context"}
    # Different object — caller can mutate safely.
    stamped["event"] = "mutated"
    assert entry["event"] == "no_context"


# ---------------------------------------------------------------------------
# Frozen dataclass property
# ---------------------------------------------------------------------------


def test_correlation_context_is_immutable():
    """frozen=True -> cannot mutate fields after construction."""
    ctx = CorrelationContext(request_id="r1", correlation_id="c1")
    with pytest.raises(Exception):  # noqa: B017 — FrozenInstanceError subclasses Exception
        ctx.request_id = "r2"  # type: ignore[misc]
