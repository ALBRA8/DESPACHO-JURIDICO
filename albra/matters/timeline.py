"""
MATTER TIMELINE — JSONL append-only por matter.

Cada evento queda en ``data/matters/<matter_id>/timeline.jsonl`` con:
- ts (timestamp ISO 8601 UTC)
- actor (user_id o agent_name)
- event_type (created | state_change | approval | draft_added | review_added | file_added | citation_audit_blocked | citation_audit_passed | comment)
- description
- attachments (paths relativos a la carpeta del matter)

Sin hash chain (eso vive en audit.jsonl). Timeline es para navegación humana;
audit es para cumplimiento profesional.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MatterTimeline:
    """Timeline JSONL append-only por matter."""

    def __init__(self, matters_dir: str = "./data/matters") -> None:
        self.matters_dir = Path(matters_dir)
        self.matters_dir.mkdir(parents=True, exist_ok=True)

    def _matter_dir(self, matter_id: str) -> Path:
        d = self.matters_dir / matter_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _timeline_path(self, matter_id: str) -> Path:
        return self._matter_dir(matter_id) / "timeline.jsonl"

    def append(
        self,
        matter_id: str,
        *,
        actor: str,
        event_type: str,
        description: str,
        attachments: list[str] | None = None,
    ) -> dict[str, Any]:
        event = {
            "ts": _utcnow_iso(),
            "actor": actor,
            "event_type": event_type,
            "description": description,
            "attachments": attachments or [],
        }
        path = self._timeline_path(matter_id)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        return event

    def read(
        self,
        matter_id: str,
        *,
        event_type: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        path = self._timeline_path(matter_id)
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    if event_type and e.get("event_type") != event_type:
                        continue
                    events.append(e)
                except json.JSONDecodeError:
                    continue
        if limit:
            events = events[-limit:]
        return events

    def count(self, matter_id: str) -> int:
        path = self._timeline_path(matter_id)
        if not path.exists():
            return 0
        c = 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    c += 1
        return c
