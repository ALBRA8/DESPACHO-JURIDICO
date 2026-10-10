"""Recovery Manager - recuperación ante fallos."""
from __future__ import annotations

import asyncio
from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger


class RecoveryManager:
    """Maneja timeouts, pérdida de conexión, tools no disponibles,
    fuentes inaccesibles, respuestas incompletas, fallos de memoria,
    fallos de proveedores, interrupciones.

    Mantiene estados consistentes y previene duplicaciones.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.resilience")
        self._task_locks: dict[str, asyncio.Lock] = {}
        self._failed_tasks: dict[str, dict[str, Any]] = {}

    async def startup(self) -> None:
        self.log.info("resilience.startup")

    async def shutdown(self) -> None:
        self.log.info("resilience.shutdown")

    def lock_for(self, task_id: str) -> asyncio.Lock:
        if task_id not in self._task_locks:
            self._task_locks[task_id] = asyncio.Lock()
        return self._task_locks[task_id]

    def record_failure(self, task_id: str, error: str) -> None:
        if task_id not in self._failed_tasks:
            self._failed_tasks[task_id] = {"attempts": 0, "errors": []}
        self._failed_tasks[task_id]["attempts"] += 1
        self._failed_tasks[task_id]["errors"].append(error)

    def clear_failure(self, task_id: str) -> None:
        self._failed_tasks.pop(task_id, None)

    def stats(self) -> dict[str, Any]:
        return {
            "active_locks": len(self._task_locks),
            "failed_tasks": len(self._failed_tasks),
            "failures": dict(self._failed_tasks),
        }
