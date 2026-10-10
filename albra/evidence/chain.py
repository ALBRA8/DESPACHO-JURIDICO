"""
Cadena de evidencia y provenance ALBRA.

Pipeline:
SOURCE → INGESTION → EXTRACTION → EVIDENCE → PROVENANCE → ANALYSIS → CONCLUSION → ACTION

Cada item de evidencia:
- id
- kind (research_finding | document_extract | user_input | tool_output | ...)
- content
- source (url, file, channel)
- obtained_at (timestamp)
- version (qué versión existía)
- transformation (qué transformaciones sufrió)
- depends_on (otros evidence_ids)
- metadata
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger


class EvidenceItem:
    def __init__(
        self,
        *,
        id: str,
        kind: str,
        content: str,
        source: str,
        obtained_at: float,
        version: str | None = None,
        transformation: str | None = None,
        depends_on: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.id = id
        self.kind = kind
        self.content = content
        self.source = source
        self.obtained_at = obtained_at
        self.version = version
        self.transformation = transformation
        self.depends_on = depends_on or []
        self.metadata = metadata or {}

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "content": self.content,
            "source": self.source,
            "obtained_at": self.obtained_at,
            "version": self.version,
            "transformation": self.transformation,
            "depends_on": self.depends_on,
            "metadata": self.metadata,
        }


class EvidenceChain:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.evidence")
        self._items: dict[str, EvidenceItem] = {}
        # SQLite persistente opcional
        self._db_path = Path(settings.audit_path).parent / "evidence.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evidence (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT,
                obtained_at REAL NOT NULL,
                version TEXT,
                transformation TEXT,
                depends_on TEXT,
                metadata TEXT
            )
            """
        )
        self._conn.commit()

    async def startup(self) -> None:
        """Rehidrata estado desde sqlite tras restart (P1)."""
        self.log.info("evidence.startup", db=str(self._db_path))
        await self._rehydrate()

    async def _rehydrate(self) -> None:
        """Carga items desde sqlite a memoria para acceso rápido."""
        if not self._conn:
            return
        cur = self._conn.execute(
            "SELECT id, kind, content, source, obtained_at, version, "
            "transformation, depends_on, metadata FROM evidence"
        )
        rows = cur.fetchall()
        for r in rows:
            eid = r[0]
            self._items[eid] = EvidenceItem(
                id=eid,
                kind=r[1],
                content=r[2],
                source=r[3] or "",
                obtained_at=r[4],
                version=r[5],
                transformation=r[6],
                depends_on=json.loads(r[7]) if r[7] else [],
                metadata=json.loads(r[8]) if r[8] else {},
            )
        self.log.info("evidence.rehydrated", items=len(self._items))

    async def shutdown(self) -> None:
        if self._conn:
            self._conn.close()

    async def add(
        self,
        *,
        kind: str,
        content: str,
        source: str,
        version: str | None = None,
        transformation: str | None = None,
        depends_on: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        eid = uuid.uuid4().hex[:16]
        item = EvidenceItem(
            id=eid,
            kind=kind,
            content=content,
            source=source,
            obtained_at=time.time(),
            version=version,
            transformation=transformation,
            depends_on=depends_on,
            metadata=metadata,
        )
        self._items[eid] = item
        self._conn.execute(
            "INSERT INTO evidence (id, kind, content, source, obtained_at, version, "
            "transformation, depends_on, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                eid,
                kind,
                content,
                source,
                item.obtained_at,
                version,
                transformation,
                json.dumps(depends_on or []),
                json.dumps(metadata or {}),
            ),
        )
        self._conn.commit()
        self.log.info("evidence.add", id=eid, kind=kind, source=source)
        return eid

    def get(self, eid: str) -> EvidenceItem | None:
        return self._items.get(eid)

    def trace(self, eid: str, *, depth: int = 10) -> dict[str, Any]:
        """Reconstruye el árbol de procedencia de una evidencia."""
        item = self.get(eid)
        if not item:
            return {"id": eid, "error": "not_found"}
        node = item.as_dict()
        if depth > 0 and item.depends_on:
            node["depends_on_items"] = [
                self.trace(dep, depth=depth - 1) for dep in item.depends_on
            ]
        return node

    def list(self, *, kind: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        items = list(self._items.values())
        if kind:
            items = [i for i in items if i.kind == kind]
        return [i.as_dict() for i in items[:limit]]

    def stats(self) -> dict[str, int]:
        from collections import Counter
        c = Counter(i.kind for i in self._items.values())
        return dict(c)
