"""FileTracker - lectura/escritura con trazabilidad."""
from __future__ import annotations

import hashlib
import os
import time
import uuid
from pathlib import Path
from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger


class FileTracker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.files")
        self._registry: dict[str, dict[str, Any]] = {}

    async def startup(self) -> None:
        self.log.info("files.startup")

    async def shutdown(self) -> None:
        self.log.info("files.shutdown")

    async def read(self, path: str, *, user: str = "anon") -> dict[str, Any]:
        p = Path(path)
        if not p.exists():
            return {"ok": False, "error": f"Archivo no existe: {path}"}
        if not p.is_file():
            return {"ok": False, "error": f"No es archivo: {path}"}
        data = p.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        file_id = f"file_{sha[:12]}"
        self._registry[file_id] = {
            "path": str(p),
            "bytes": len(data),
            "sha256": sha,
            "user": user,
            "ts": time.time(),
            "operation": "read",
        }
        self.log.info("files.read", path=path, bytes=len(data), sha=sha[:12], user=user)
        return {
            "ok": True,
            "file_id": file_id,
            "bytes": len(data),
            "sha256": sha,
            "path": str(p),
        }

    async def write(self, path: str, content: bytes, *, user: str = "anon") -> dict[str, Any]:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        sha = hashlib.sha256(content).hexdigest()
        file_id = f"file_{sha[:12]}"
        self._registry[file_id] = {
            "path": str(p),
            "bytes": len(content),
            "sha256": sha,
            "user": user,
            "ts": time.time(),
            "operation": "write",
        }
        self.log.info("files.write", path=path, bytes=len(content), sha=sha[:12], user=user)
        return {
            "ok": True,
            "file_id": file_id,
            "path": str(p),
            "sha256": sha,
        }

    def registry(self) -> list[dict[str, Any]]:
        return [dict(v, file_id=k) for k, v in self._registry.items()]
