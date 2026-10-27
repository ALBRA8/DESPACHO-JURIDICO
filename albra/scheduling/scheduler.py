"""
SCHEDULER — agents programados o event-driven.

Inspiración (clean-room): Claude for Legal pattern (scheduled/triggered agents).
Implementación V2.4-A: simple in-process scheduler. V2.5+: APScheduler para producción.

Triggers:
- ON_MATTER_CREATED: cuando MatterStore.create_matter() corre
- ON_STATE_CHANGE: cuando advance_state() cambia el state
- ON_DEADLINE_NEAR: cuando DeadlineGuard detecta <30 días para prescripción
- DAILY_AT(hour): ejecuta diariamente a la hora dada
- INTERVAL(seconds): ejecuta cada N segundos

Handlers registrados:
- intake_auto_start: cuando matter creado → INTAKE-AGENT arranca
- deadline_watcher: DAILY_AT 9am → check todos los matters, alerta si deadline <30 días
- review_auto_trigger: cuando state = BORRADOR-FINAL → REVIEW-AGENT arranca
- audit_chain_verifier: DAILY_AT 8am → verifica hash chain de todos los matters

V2.4-A: in-memory scheduler con heapq. NO persistente (reinicia al restart).
V2.5+: APScheduler con SQLite jobstore persistente.
"""
from __future__ import annotations

import heapq
import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from datetime import time as dtime
from typing import Any

from albra.observability.logger import get_logger

# ===== Event constants =====
ON_MATTER_CREATED = "matter_created"
ON_STATE_CHANGE = "state_change"
ON_DEADLINE_NEAR = "deadline_near"
ON_APPROVAL_PENDING = "approval_pending"

# ===== Time-based trigger type keywords =====
# register_trigger(event=TRIGGER_DAILY_AT, handler=h, hour=9)
# register_trigger(event=TRIGGER_INTERVAL, handler=h, seconds=60)
TRIGGER_DAILY_AT = "DAILY_AT"
TRIGGER_INTERVAL = "INTERVAL"

ALL_EVENTS: frozenset[str] = frozenset(
    {
        ON_MATTER_CREATED,
        ON_STATE_CHANGE,
        ON_DEADLINE_NEAR,
        ON_APPROVAL_PENDING,
    }
)

HandlerFn = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class Trigger:
    """Registro de un trigger (event-driven o time-based).

    Para event-driven (ON_MATTER_CREATED, etc.): `next_run` es None.
    Para time-based (DAILY_AT, INTERVAL): `next_run` es el timestamp del próximo fire.
    """

    trigger_id: str
    event: str
    handler: HandlerFn
    kwargs: dict[str, Any] = field(default_factory=dict)
    next_run: float | None = None
    last_run: float | None = None
    last_result: dict[str, Any] | None = None
    last_error: str | None = None
    run_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "trigger_id": self.trigger_id,
            "event": self.event,
            "kwargs": dict(self.kwargs),
            "next_run": self.next_run,
            "last_run": self.last_run,
            "last_result": self.last_result,
            "last_error": self.last_error,
            "run_count": self.run_count,
        }


def _compute_next_daily(hour: int, base: float) -> float:
    """Próximo timestamp (UNIX) para DAILY_AT(hour) empezando desde `base`.

    Si hoy a las `hour` aún no ha llegado (target_ts > base) → hoy.
    Si ya pasó → mañana a la misma hora.
    """
    dt = datetime.fromtimestamp(base)
    today_target = datetime.combine(dt.date(), dtime(hour=hour % 24, minute=0, second=0))
    target_ts = today_target.timestamp()
    if target_ts <= base:
        target_ts = (today_target + timedelta(days=1)).timestamp()
    return target_ts


def _compute_next_interval(seconds: int, base: float) -> float:
    """Próximo timestamp para INTERVAL(seconds) desde `base`."""
    return base + max(1, int(seconds))


class Scheduler:
    """In-process scheduler — event-driven handlers + heap-based timed jobs.

    Event-driven (ON_MATTER_CREATED, etc.): handlers corren en `fire_event(event, payload)`.
    Time-based (DAILY_AT, INTERVAL): handlers corren en `tick()` (manual) o en el
    background loop de `start()`.

    NO persistente: el estado se reinicia al restart del proceso.
    """

    def __init__(self) -> None:
        self.log = get_logger("albra.scheduling")
        # trigger_id → Trigger
        self._triggers: dict[str, Trigger] = {}
        # event → [trigger_id, ...]  (event-driven dispatch)
        self._event_handlers: dict[str, list[str]] = defaultdict(list)
        # heap of (next_run, seq, trigger_id) para DAILY_AT/INTERVAL
        self._heap: list[tuple[float, int, str]] = []
        self._seq = 0
        # Overrideable clock para testing (default: real time.time).
        self._clock: Callable[[], float] = time.time
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._started = False

    # ===== internal helpers =====

    def _now(self) -> float:
        return self._clock()

    def _heap_push(self, ts: float, trigger_id: str) -> None:
        with self._lock:
            heapq.heappush(self._heap, (ts, self._seq, trigger_id))
            self._seq += 1

    # ===== registration =====

    def register_trigger(self, event: str, handler: HandlerFn, **kwargs: Any) -> str:
        """Registra un handler para `event`.

        - Event-driven (ON_MATTER_CREATED, ON_STATE_CHANGE, ON_DEADLINE_NEAR,
          ON_APPROVAL_PENDING): el handler corre cuando se llama `fire_event(event, payload)`.
        - TRIGGER_DAILY_AT: requiere `hour` (0-23). Corre diariamente a esa hora.
          Avanza por `tick()` o background loop de `start()`.
        - TRIGGER_INTERVAL: requiere `seconds` (≥1). Corre cada N segundos.

        Returns: trigger_id (16 hex chars).
        """
        trigger_id = uuid.uuid4().hex[:16]
        trig = Trigger(
            trigger_id=trigger_id,
            event=event,
            handler=handler,
            kwargs=dict(kwargs),
        )

        if event == TRIGGER_DAILY_AT:
            hour = int(kwargs.get("hour", 9))
            trig.next_run = _compute_next_daily(hour, base=self._now())
            self._heap_push(trig.next_run, trigger_id)
        elif event == TRIGGER_INTERVAL:
            seconds = int(kwargs.get("seconds", 60))
            trig.next_run = _compute_next_interval(seconds, base=self._now())
            self._heap_push(trig.next_run, trigger_id)
        else:
            # event-driven
            self._event_handlers[event].append(trigger_id)

        self._triggers[trigger_id] = trig
        self.log.info(
            "scheduler.register",
            trigger_id=trigger_id,
            event=event,
            kwargs=dict(kwargs),
        )
        return trigger_id

    def unregister_trigger(self, trigger_id: str) -> bool:
        """Elimina un trigger. Returns True si existía, False si no."""
        trig = self._triggers.pop(trigger_id, None)
        if not trig:
            return False
        # Eliminar de event_handlers si está (event-driven)
        if trig.event in self._event_handlers:
            self._event_handlers[trig.event] = [
                t for t in self._event_handlers[trig.event] if t != trigger_id
            ]
            if not self._event_handlers[trig.event]:
                del self._event_handlers[trig.event]
        # Time-based: lazy delete — la entry queda en el heap pero se filtra
        # en tick() cuando _triggers.get(tid) retorna None.
        self.log.info("scheduler.unregister", trigger_id=trigger_id)
        return True

    def list_triggers(self) -> list[dict[str, Any]]:
        """Lista todos los triggers registrados como dicts."""
        return [t.as_dict() for t in self._triggers.values()]

    # ===== event dispatch =====

    def fire_event(self, event: str, payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Dispara `event` con `payload` a todos los handlers registrados.

        Returns: lista de results dicts ({trigger_id, ok, result|error}) en orden
        de registro. Si un handler levanta excepción, no bloquea a los demás.
        """
        payload = payload or {}
        results: list[dict[str, Any]] = []
        trigger_ids = list(self._event_handlers.get(event, []))
        for tid in trigger_ids:
            trig = self._triggers.get(tid)
            if not trig:
                continue
            res = self._run_handler(trig, payload)
            results.append(res)
        self.log.info(
            "scheduler.fire_event",
            event=event,
            handlers_run=len(results),
        )
        return results

    def _run_handler(self, trig: Trigger, payload: dict[str, Any]) -> dict[str, Any]:
        """Ejecuta un handler, captura excepciones, actualiza last_* y run_count."""
        try:
            result = trig.handler(payload)
            if not isinstance(result, dict):
                result = {"value": result}
            trig.last_run = self._now()
            trig.last_result = result
            trig.last_error = None
            trig.run_count += 1
            return {"trigger_id": trig.trigger_id, "ok": True, "result": result}
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
            trig.last_run = self._now()
            trig.last_error = err
            trig.run_count += 1
            self.log.error(
                "scheduler.handler.error",
                trigger_id=trig.trigger_id,
                event=trig.event,
                error=err,
            )
            return {"trigger_id": trig.trigger_id, "ok": False, "error": err}

    # ===== time-based tick =====

    def tick(self, now: float | None = None) -> list[dict[str, Any]]:
        """Avanza el scheduler: corre todos los timed jobs cuyo next_run <= now.

        Para testing. `now` defaults a `self._clock()`. Actualiza next_run de cada
        job corrido (DAILY_AT → mañana a la hora; INTERVAL → now + seconds).

        Returns: lista de results dicts (uno por job corrido).
        """
        now = self._now() if now is None else now
        results: list[dict[str, Any]] = []
        while True:
            trig: Trigger | None = None
            with self._lock:
                if not self._heap:
                    break
                peek = self._heap[0]
                next_run, _seq, tid = peek
                if next_run > now:
                    break
                heapq.heappop(self._heap)
                trig = self._triggers.get(tid)
                if not trig:
                    # lazy delete: trigger fue unregistered
                    continue
                # Re-queue el próximo run ANTES de correr el handler
                if trig.event == TRIGGER_DAILY_AT:
                    hour = int(trig.kwargs.get("hour", 9))
                    trig.next_run = _compute_next_daily(hour, base=now)
                elif trig.event == TRIGGER_INTERVAL:
                    seconds = int(trig.kwargs.get("seconds", 60))
                    trig.next_run = _compute_next_interval(seconds, base=now)
                else:
                    trig.next_run = None
                if trig.next_run is not None:
                    heapq.heappush(self._heap, (trig.next_run, self._seq, tid))
                    self._seq += 1
            # Corre el handler FUERA del lock para evitar deadlock
            # si el handler llama de vuelta al scheduler.
            assert trig is not None
            res = self._run_handler(trig, payload={})
            results.append(res)
        return results

    # ===== background loop =====

    def start(self) -> None:
        """Arranca el background thread que corre `tick()` cada 500ms."""
        if self._started:
            return
        self._started = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="albra-scheduler"
        )
        self._thread.start()
        self.log.info("scheduler.start")

    def stop(self) -> None:
        """Detiene el background thread."""
        if not self._started:
            return
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        self._started = False
        self.log.info("scheduler.stop")

    def _loop(self) -> None:
        """Loop del background thread: tick + wait 500ms (interrumpible)."""
        while not self._stop_event.is_set():
            self.tick()
            self._stop_event.wait(0.5)
