"""
CIRCUIT BREAKER ALBRA - protección contra fallos en cascada.

Cuando un provider/organ/tool falla repetidamente, el breaker lo abre
y deja de invocarlo por un tiempo. Después de cool-off, prueba
semi-open: si funciona, cierra; si no, abre de nuevo.

Estados:
- CLOSED: flujo normal, todo pasa
- OPEN: bloquea todo (devuelve error inmediato)
- HALF_OPEN: deja pasar 1 request de prueba
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from albra.observability.logger import get_logger


@dataclass
class BreakerState:
    name: str
    failure_count: int = 0
    success_count: int = 0
    state: str = "CLOSED"  # CLOSED | OPEN | HALF_OPEN
    opened_at: float = 0.0
    last_failure: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class CircuitBreaker:
    """Breaker por clave (provider/organ/tool)."""

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        cool_off_seconds: float = 60.0,
    ) -> None:
        self.log = get_logger("albra.circuit_breaker")
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.cool_off_seconds = cool_off_seconds
        self._states: dict[str, BreakerState] = {}

    def _get(self, name: str) -> BreakerState:
        if name not in self._states:
            self._states[name] = BreakerState(name=name)
        return self._states[name]

    def can_pass(self, name: str) -> bool:
        s = self._get(name)
        if s.state == "CLOSED":
            return True
        if s.state == "OPEN":
            # Verificar si pasó el cool-off
            if time.time() - s.opened_at > self.cool_off_seconds:
                s.state = "HALF_OPEN"
                self.log.info("breaker.half_open", name=name)
                return True
            return False
        if s.state == "HALF_OPEN":
            # En semi-open, solo dejamos pasar 1 (implicito por la llamada)
            return True
        return False

    def record_success(self, name: str) -> None:
        s = self._get(name)
        s.success_count += 1
        if s.state == "HALF_OPEN":
            if s.success_count >= self.success_threshold:
                s.state = "CLOSED"
                s.failure_count = 0
                self.log.info("breaker.closed", name=name, reason="recovered")
        elif s.state == "OPEN":
            # No debería pasar, pero por si acaso
            s.state = "HALF_OPEN"
            s.success_count = 1

    def record_failure(self, name: str) -> None:
        s = self._get(name)
        s.failure_count += 1
        s.last_failure = time.time()
        if s.state == "HALF_OPEN":
            # Fallo durante semi-open → vuelve a OPEN
            s.state = "OPEN"
            s.opened_at = time.time()
            s.success_count = 0
            self.log.warning("breaker.reopened", name=name)
        elif s.state == "CLOSED":
            if s.failure_count >= self.failure_threshold:
                s.state = "OPEN"
                s.opened_at = time.time()
                self.log.warning("breaker.opened", name=name, failures=s.failure_count)

    def force_open(self, name: str, *, reason: str = "manual") -> None:
        s = self._get(name)
        s.state = "OPEN"
        s.opened_at = time.time()
        s.metadata["force_reason"] = reason
        self.log.warning("breaker.force_open", name=name, reason=reason)

    def force_close(self, name: str) -> None:
        s = self._get(name)
        s.state = "CLOSED"
        s.failure_count = 0
        s.success_count = 0
        self.log.info("breaker.force_closed", name=name)

    def status(self) -> dict[str, Any]:
        return {
            name: {
                "state": s.state,
                "failures": s.failure_count,
                "successes": s.success_count,
                "opened_at": s.opened_at,
                "last_failure": s.last_failure,
            }
            for name, s in self._states.items()
        }
