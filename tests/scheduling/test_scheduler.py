"""Tests del Scheduler V2.4-A.

Cobertura (15 tests):
- Registro / unregister / list_triggers
- fire_event: runs handlers, returns results list, unknown event → empty
- Multiple handlers same event all run
- Handler exception does not block others
- Payload passed to handler
- 4 event constants: ON_MATTER_CREATED, ON_STATE_CHANGE, ON_DEADLINE_NEAR,
  ON_APPROVAL_PENDING
- tick: no scheduled jobs returns empty
- INTERVAL trigger can be advanced via tick (clock override)
"""
from __future__ import annotations

import pytest

from albra.scheduling.scheduler import (
    ON_APPROVAL_PENDING,
    ON_DEADLINE_NEAR,
    ON_MATTER_CREATED,
    ON_STATE_CHANGE,
    TRIGGER_INTERVAL,
    Scheduler,
)

# ===== Fixtures =====


@pytest.fixture
def strong_secrets(monkeypatch):
    """ALBRA requires strong JWT secret + admin password at import time."""
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-ephemeral-jwt-secret-32-chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-ephemeral-pass-1234")


@pytest.fixture
def sched(strong_secrets):
    return Scheduler()


# ===== Registration / list / unregister =====


def test_register_trigger_returns_id(sched):
    """register_trigger devuelve un id string no vacío."""

    def handler(payload):
        return {"ok": True}

    tid = sched.register_trigger(ON_MATTER_CREATED, handler)
    assert isinstance(tid, str)
    assert len(tid) > 0
    ids = {t["trigger_id"] for t in sched.list_triggers()}
    assert tid in ids


def test_unregister_trigger(sched):
    """unregister_trigger retorna True si existía, False si no."""

    def handler(payload):
        return {}

    tid = sched.register_trigger(ON_MATTER_CREATED, handler)
    assert sched.unregister_trigger(tid) is True
    # Segunda vez — ya no existe
    assert sched.unregister_trigger(tid) is False
    assert sched.list_triggers() == []


# ===== fire_event =====


def test_fire_event_runs_handlers(sched):
    """fire_event invoca el handler registrado para el evento."""
    called: list[dict] = []

    def handler(payload):
        called.append(payload)
        return {"done": True}

    sched.register_trigger(ON_MATTER_CREATED, handler)
    results = sched.fire_event(ON_MATTER_CREATED, {"matter_id": "M1"})
    assert len(called) == 1
    assert called[0]["matter_id"] == "M1"
    assert len(results) == 1
    assert results[0]["ok"] is True


def test_fire_event_returns_results_list(sched):
    """fire_event retorna una lista de dicts con {trigger_id, ok, result|error}."""

    def handler(payload):
        return {"echo": payload.get("x")}

    sched.register_trigger(ON_STATE_CHANGE, handler)
    results = sched.fire_event(ON_STATE_CHANGE, {"x": 42})
    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0]["ok"] is True
    assert results[0]["result"] == {"echo": 42}
    assert "trigger_id" in results[0]


def test_fire_event_unknown_returns_empty(sched):
    """Disparar un evento sin handlers retorna lista vacía (no error)."""
    assert sched.fire_event("nonexistent_event") == []
    assert sched.fire_event("nonexistent_event", {"a": 1}) == []


def test_multiple_handlers_same_event_all_run(sched):
    """Multiple handlers registrados para el mismo evento — todos corren en orden."""
    log: list[str] = []

    def h1(payload):
        log.append("h1")
        return {"id": 1}

    def h2(payload):
        log.append("h2")
        return {"id": 2}

    def h3(payload):
        log.append("h3")
        return {"id": 3}

    sched.register_trigger(ON_DEADLINE_NEAR, h1)
    sched.register_trigger(ON_DEADLINE_NEAR, h2)
    sched.register_trigger(ON_DEADLINE_NEAR, h3)
    results = sched.fire_event(ON_DEADLINE_NEAR, {"days_left": 25})
    assert log == ["h1", "h2", "h3"]
    assert len(results) == 3
    ids = [r["result"]["id"] for r in results]
    assert ids == [1, 2, 3]


def test_handler_exception_does_not_block_others(sched):
    """Si un handler levanta excepción, los demás handlers siguen corriendo."""
    log: list[str] = []

    def bad(payload):
        raise RuntimeError("boom")

    def good(payload):
        log.append("good")
        return {"ok": True}

    sched.register_trigger(ON_APPROVAL_PENDING, bad)
    sched.register_trigger(ON_APPROVAL_PENDING, good)
    results = sched.fire_event(ON_APPROVAL_PENDING, {"action_id": "A1"})
    assert len(results) == 2
    assert results[0]["ok"] is False
    assert "boom" in results[0]["error"]
    assert results[1]["ok"] is True
    assert results[1]["result"] == {"ok": True}
    assert log == ["good"]


def test_list_triggers(sched):
    """list_triggers retorna una lista de dicts con todos los campos esperados."""
    sched.register_trigger(ON_MATTER_CREATED, lambda p: {})
    sched.register_trigger(ON_STATE_CHANGE, lambda p: {})
    triggers = sched.list_triggers()
    assert isinstance(triggers, list)
    assert len(triggers) == 2
    for t in triggers:
        assert "trigger_id" in t
        assert "event" in t
        assert "kwargs" in t
        assert "next_run" in t
        assert "last_run" in t
        assert "last_result" in t
        assert "last_error" in t
        assert "run_count" in t
    events = {t["event"] for t in triggers}
    assert events == {ON_MATTER_CREATED, ON_STATE_CHANGE}


def test_payload_passed_to_handler(sched):
    """El payload dict pasado a fire_event se entrega íntegro al handler."""
    received: list[dict] = []

    def handler(payload):
        received.append(payload)
        return {}

    sched.register_trigger(ON_MATTER_CREATED, handler)
    payload = {"matter_id": "M-abc", "client": "Juan Pérez", "area": "civil"}
    sched.fire_event(ON_MATTER_CREATED, payload)
    assert received == [payload]


# ===== Event constant tests =====


def test_on_matter_created_event(sched):
    """ON_MATTER_CREATED evento dispara handlers con matter_id en payload."""
    seen: list[str] = []

    def handler(payload):
        seen.append(payload["matter_id"])
        return {"ok": True}

    sched.register_trigger(ON_MATTER_CREATED, handler)
    results = sched.fire_event(
        ON_MATTER_CREATED,
        {"matter_id": "M1", "client": "X", "area": "civil"},
    )
    assert seen == ["M1"]
    assert len(results) == 1
    assert results[0]["ok"] is True


def test_on_state_change_event(sched):
    """ON_STATE_CHANGE evento entrega from/to al handler."""
    seen: list[tuple] = []

    def handler(payload):
        seen.append((payload["matter_id"], payload["from"], payload["to"]))
        return {}

    sched.register_trigger(ON_STATE_CHANGE, handler)
    sched.fire_event(
        ON_STATE_CHANGE,
        {"matter_id": "M1", "from": "NUEVO", "to": "INTAKE"},
    )
    assert seen == [("M1", "NUEVO", "INTAKE")]


def test_on_deadline_near_event(sched):
    """ON_DEADLINE_NEAR evento entrega days_left y deadline_type al handler."""
    seen: list[dict] = []

    def handler(payload):
        seen.append(payload)
        return {}

    sched.register_trigger(ON_DEADLINE_NEAR, handler)
    sched.fire_event(
        ON_DEADLINE_NEAR,
        {"matter_id": "M1", "days_left": 28, "deadline_type": "prescripcion"},
    )
    assert seen == [
        {
            "matter_id": "M1",
            "days_left": 28,
            "deadline_type": "prescripcion",
        }
    ]


def test_on_approval_pending_event(sched):
    """ON_APPROVAL_PENDING evento entrega action_id al handler."""
    seen: list[str] = []

    def handler(payload):
        seen.append(payload["action_id"])
        return {}

    sched.register_trigger(ON_APPROVAL_PENDING, handler)
    sched.fire_event(
        ON_APPROVAL_PENDING,
        {"action_id": "A1", "matter_id": "M1"},
    )
    assert seen == ["A1"]


# ===== tick / time-based triggers =====


def test_tick_no_scheduled_jobs_returns_empty(sched):
    """tick() con ningún DAILY_AT/INTERVAL registrado retorna lista vacía."""
    assert sched.tick() == []


def test_interval_trigger_can_be_advanced(sched):
    """tick() avanza el scheduler y corre INTERVAL triggers cuando su next_run llegó.

    El scheduler usa self._clock() (default: time.time). Para testear sin
    esperar segundos reales, se sobreescribe _clock con un counter mutable.
    """
    calls: list[dict] = []
    state = {"t": 0.0}
    sched._clock = lambda: state["t"]
    sched.register_trigger(
        TRIGGER_INTERVAL,
        lambda p: calls.append(p) or {"ran": True},
        seconds=10,
    )
    # En t=0: next_run = 0 + 10 = 10 → tick no corre nada.
    assert sched.tick() == []
    assert calls == []
    # En t=5: todavía antes del next_run=10 → no corre nada.
    state["t"] = 5
    assert sched.tick() == []
    assert calls == []
    # En t=15: next_run=10 ya llegó → corre handler, next_run actualiza a 25.
    state["t"] = 15
    r1 = sched.tick()
    assert len(r1) == 1
    assert r1[0]["ok"] is True
    assert r1[0]["result"] == {"ran": True}
    assert len(calls) == 1
    # En t=20: todavía antes del next_run=25 → no corre nada.
    state["t"] = 20
    assert sched.tick() == []
    assert len(calls) == 1
    # En t=30: next_run=25 llegó → corre de nuevo, next_run actualiza a 40.
    state["t"] = 30
    r2 = sched.tick()
    assert len(r2) == 1
    assert len(calls) == 2
