"""
Audit con hash encadenado - tamper-evident.

Cada entrada incluye:
- prev_hash (hash de la entrada anterior)
- this_hash (hash de la entrada actual + prev_hash)

Si alguien modifica una entrada, el chain se rompe y verify_chain() lo detecta.

Esto permite demostrar ante un perito/juez que el log no fue manipulado.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from albra.observability.logger import get_logger


class TamperEvidentAudit:
    """Audit log con hash encadenado tipo blockchain."""

    GENESIS_HASH = "0" * 64

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self.log = get_logger("albra.audit.tamper_evident")
        # Cargar último hash
        self._prev_hash = self._load_last_hash()

    def _load_last_hash(self) -> str:
        """Lee el último hash del archivo."""
        last = self.GENESIS_HASH
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        last = entry.get("this_hash", last)
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            pass
        return last

    async def append(self, event_type: str, payload: dict[str, Any]) -> str:
        """Append una entrada con hash encadenado."""
        ts = time.time()
        block = {
            "ts": ts,
            "type": event_type,
            "payload": payload,
            "prev_hash": self._prev_hash,
        }
        block_str = json.dumps(block, sort_keys=True, ensure_ascii=False, default=str)
        this_hash = hashlib.sha256(block_str.encode("utf-8")).hexdigest()
        block["this_hash"] = this_hash
        line = json.dumps(block, ensure_ascii=False, default=str)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        self._prev_hash = this_hash
        self.log.debug("audit.append", type=event_type, hash=this_hash[:12])
        return this_hash

    def verify_chain(self) -> dict[str, Any]:
        """Verifica integridad del hash chain. Devuelve ok=True si no fue manipulado."""
        prev = self.GENESIS_HASH
        total = 0
        broken_at: list[int] = []
        try:
            with open(self.path, encoding="utf-8") as f:
                for i, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        broken_at.append(i)
                        continue
                    expected_prev = entry.get("prev_hash")
                    this_hash = entry.get("this_hash")
                    # Verificar prev_hash
                    if expected_prev != prev:
                        broken_at.append(i)
                        prev = this_hash or prev
                        continue
                    # Verificar this_hash
                    block_copy = {k: v for k, v in entry.items() if k != "this_hash"}
                    block_str = json.dumps(block_copy, sort_keys=True, ensure_ascii=False, default=str)
                    expected_hash = hashlib.sha256(block_str.encode("utf-8")).hexdigest()
                    if expected_hash != this_hash:
                        broken_at.append(i)
                    prev = this_hash or prev
                    total += 1
        except FileNotFoundError:
            return {"ok": True, "total": 0, "broken_at": []}
        return {
            "ok": len(broken_at) == 0,
            "total": total,
            "broken_at": broken_at,
        }

    def read(self, *, limit: int = 50, event_type: str | None = None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                    if event_type and e.get("type") != event_type:
                        continue
                    items.append(e)
                except json.JSONDecodeError:
                    continue
        return items[-limit:]

    def fingerprint(self) -> str:
        """Hash del estado actual del chain - útil para comparar con backups."""
        h = hashlib.sha256()
        with open(self.path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
