"""
Self-Healing - Doctor como supervisor de los otros 29 órganos.

Patrón: el Doctor monitorea activamente. Si detecta degradación:
1. Identifica órgano afectado
2. Aplica política de recovery:
   - Fallback a proveedor alternativo
   - Cache temporal
   - Cola diferida
   - Reinicio seguro
3. Degradación elegante: si no puede recuperar, baja capacidad pero
   mantiene al agente vivo.

NO modifica código - el Constructor es el único que hace eso.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from albra.config.settings import Settings
from albra.doctor.diagnostic import Doctor
from albra.observability.logger import get_logger


@dataclass
class HealthSnapshot:
    ts: float = field(default_factory=time.time)
    organs_health: dict[str, str] = field(default_factory=dict)  # organ → ok|warn|error
    actions_taken: list[dict[str, Any]] = field(default_factory=list)


class SelfHealingSupervisor:
    """Doctor como supervisor self-healing."""

    def __init__(
        self,
        settings: Settings,
        *,
        doctor: Doctor,
        organs: dict[str, Any] | None = None,
    ) -> None:
        self.settings = settings
        self.doctor = doctor
        self.organs = organs or doctor.organs
        self.log = get_logger("albra.self_healing")
        self._snapshots: list[HealthSnapshot] = []
        self._recovery_handlers: dict[str, Callable[[], Awaitable[bool]]] = {}
        self._degraded_organs: set[str] = set()
        self._monitoring = False
        self._monitor_task: asyncio.Task | None = None

    def register_recovery(self, organ: str, handler: Callable[[], Awaitable[bool]]) -> None:
        self._recovery_handlers[organ] = handler
        self.log.info("self_healing.recovery_registered", organ=organ)

    async def check_organ(self, organ_name: str) -> str:
        """Verifica la salud de un órgano individual."""
        organ = self.organs.get(organ_name)
        if not organ:
            return "missing"
        try:
            # Si tiene método health, usarlo
            if hasattr(organ, "health"):
                h = await organ.health()  # type: ignore[attr-defined]
                return h.get("status", "ok") if isinstance(h, dict) else "ok"
            return "ok"
        except Exception:  # noqa: BLE001
            return "error"

    async def snapshot(self) -> HealthSnapshot:
        snap = HealthSnapshot()
        for name in self.organs.keys():
            snap.organs_health[name] = await self.check_organ(name)
        self._snapshots.append(snap)
        if len(self._snapshots) > 100:
            self._snapshots = self._snapshots[-100:]
        return snap

    async def try_recover(self, organ_name: str) -> bool:
        """Intenta recuperar un órgano degradado."""
        handler = self._recovery_handlers.get(organ_name)
        if handler:
            try:
                ok = await handler()
                if ok:
                    self._degraded_organs.discard(organ_name)
                    self.log.info("self_healing.recovered", organ=organ_name)
                    return True
            except Exception as e:  # noqa: BLE001
                self.log.error("self_healing.recovery_failed", organ=organ_name, error=str(e))
        # Fallback: intentar restart del órgano
        target = self.organs.get(organ_name)
        if target and hasattr(target, "startup"):
            try:
                await target.startup()  # type: ignore[attr-defined]
                self._degraded_organs.discard(organ_name)
                self.log.info("self_healing.restarted", organ=organ_name)
                return True
            except Exception as e:  # noqa: BLE001
                self.log.error("self_healing.restart_failed", organ=organ_name, error=str(e))
        self._degraded_organs.add(organ_name)
        return False

    async def monitor_loop(self, *, interval: float = 60.0) -> None:
        """Loop de monitoreo - corre en background."""
        self._monitoring = True
        self.log.info("self_healing.monitor.start", interval=interval)
        while self._monitoring:
            try:
                snap = await self.snapshot()
                error_organs = [
                    n for n, s in snap.organs_health.items() if s in ("error", "missing")
                ]
                for organ in error_organs:
                    if organ not in self._degraded_organs:
                        snap.actions_taken.append(
                            {"organ": organ, "action": "try_recover", "ts": time.time()}
                        )
                        await self.try_recover(organ)
            except Exception as e:  # noqa: BLE001
                self.log.error("self_healing.monitor.error", error=str(e))
            await asyncio.sleep(interval)

    async def start_monitoring(self, *, interval: float = 60.0) -> None:
        if self._monitor_task is None:
            self._monitor_task = asyncio.create_task(self.monitor_loop(interval=interval))

    async def stop_monitoring(self) -> None:
        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

    def stats(self) -> dict[str, Any]:
        return {
            "monitoring": self._monitoring,
            "degraded_organs": list(self._degraded_organs),
            "snapshots_count": len(self._snapshots),
            "last_snapshot": (
                self._snapshots[-1].organs_health if self._snapshots else {}
            ),
        }
