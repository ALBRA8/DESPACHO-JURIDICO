"""
FileTracker - I/O con sandbox workspace (P1).

REGLA: NUNCA acceder fuera del workspace configurado.
Bloquea: ../, symlinks, absolute paths fuera del workspace.

Workspace root configurable via ALBRA_WORKSPACE_ROOT (default ./data/workspace).
"""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger


class FileTracker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.files")
        self._registry: dict[str, dict[str, Any]] = {}
        # Workspace sandbox root
        ws_root = os.environ.get("ALBRA_WORKSPACE_ROOT", "./data/workspace")
        self._workspace_root = Path(ws_root).resolve()
        self._workspace_root.mkdir(parents=True, exist_ok=True)
        self.log.info("files.workspace", root=str(self._workspace_root))

    def _validate_path(self, path: str) -> Path:
        """Valida que path esté dentro del workspace root (P1 sandbox).

        Raises:
            PermissionError: si el path escapa del workspace.
        """
        # Resolver absolute path
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self._workspace_root / candidate
        candidate = candidate.resolve()

        # Bloquear path traversal: debe empezar con workspace_root
        try:
            candidate.relative_to(self._workspace_root)
        except ValueError as e:
            raise PermissionError(
                f"SANDBOX VIOLATION: path '{path}' escapa del workspace "
                f"({self._workspace_root})."
            ) from e

        # Bloquear symlinks que apunten fuera
        if candidate.is_symlink():
            target = candidate.resolve()
            try:
                target.relative_to(self._workspace_root)
            except ValueError:
                raise PermissionError(
                    f"SANDBOX VIOLATION: symlink '{path}' apunta fuera del workspace."
                )

        return candidate

    async def startup(self) -> None:
        self.log.info("files.startup", workspace=str(self._workspace_root))

    async def shutdown(self) -> None:
        self.log.info("files.shutdown")

    async def read(self, path: str, *, user: str = "anon") -> dict[str, Any]:
        try:
            p = self._validate_path(path)
        except PermissionError as e:
            self.log.warning("files.read.sandbox", path=path, error=str(e))
            return {"ok": False, "error": str(e), "status": "DENIED"}
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
        try:
            p = self._validate_path(path)
        except PermissionError as e:
            self.log.warning("files.write.sandbox", path=path, error=str(e))
            return {"ok": False, "error": str(e), "status": "DENIED"}
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
