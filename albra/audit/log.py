"""
Audit Log - registro inmutable de operaciones.

Toda operación importante debe poder ser auditada:
- eventos
- tareas
- tools
- fuentes
- decisiones
- errores
- aprobaciones
- outputs
- cambios de estado
- memoria
- MCP/MSP
- diagnósticos Doctor
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger


class AuditLog:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.audit")
        self._path = Path(settings.audit_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Touch file
        self._path.touch(exist_ok=True)

    async def startup(self) -> None:
        self.log.info("audit.startup", path=str(self._path))

    async def shutdown(self) -> None:
        self.log.info("audit.shutdown")

    async def record(self, event_type: str, payload: Any) -> None:
        # Si el payload es un Event (u otro objeto), convertirlo
        if hasattr(payload, "as_dict") and callable(getattr(payload, "as_dict", None)):
            payload = payload.as_dict()
        elif not isinstance(payload, dict):
            try:
                payload = dict(payload)  # type: ignore[arg-type]
            except Exception:  # noqa: BLE001
                payload = {"value": str(payload)}
        entry = {
            "ts": time.time(),
            "type": event_type,
            "payload": payload,
        }
        line = json.dumps(entry, ensure_ascii=False, default=str)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        # También al log estructurado
        self.log.info("audit.record", type=event_type, payload_keys=list(payload.keys()) if isinstance(payload, dict) else [])

    def read(self, *, limit: int = 100, event_type: str | None = None) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        items: list[dict[str, Any]] = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                    if event_type and e.get("type") != event_type:
                        continue
                    items.append(e)
                except json.JSONDecodeError:
                    continue
        return items[-limit:]
