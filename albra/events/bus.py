"""
Event Bus - arquitectura orientada a eventos.

Eventos:
- intake: llega mensaje
- reasoning.plan: planeación
- tool.invoke: invocación
- memory.write / retrieve
- approval.requested / approved / denied
- workflow.step / done / failed
- doctor.diagnostic
- comms.in / out
- audit.record
"""
from __future__ import annotations

import time
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger


@dataclass
class Event:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    source: str = "albra"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "ts": self.ts,
            "source": self.source,
        }


HandlerFn = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.events")
        self._handlers: dict[str, list[HandlerFn]] = defaultdict(list)
        self._history: list[Event] = []
        self._max_history = 1000

    async def startup(self) -> None:
        self.log.info("events.startup")

    async def shutdown(self) -> None:
        self.log.info("events.shutdown")

    def subscribe(self, event_type: str, handler: HandlerFn) -> None:
        self._handlers[event_type].append(handler)
        self.log.info("events.subscribe", type=event_type)

    async def emit(self, event_type: str, payload: dict[str, Any]) -> Event:
        ev = Event(type=event_type, payload=payload)
        self._history.append(ev)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]
        # Notificar handlers
        for handler in self._handlers.get(event_type, []):
            try:
                await handler(ev)
            except Exception as e:  # noqa: BLE001
                self.log.error("events.handler.error", type=event_type, error=str(e))
        # Wildcard handlers
        for handler in self._handlers.get("*", []):
            try:
                await handler(ev)
            except Exception:  # noqa: BLE001
                pass
        return ev

    def history(self, *, event_type: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        items = self._history
        if event_type:
            items = [e for e in items if e.type == event_type]
        return [e.as_dict() for e in items[-limit:]]
