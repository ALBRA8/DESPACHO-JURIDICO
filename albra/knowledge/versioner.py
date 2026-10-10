"""Versioner de conocimiento - control de vigencia."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class KnowledgeVersion:
    id: str
    kind: str
    jurisdiction: str
    source: str
    title: str
    effective_from: date | None = None
    effective_to: date | None = None
    superseded_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_active_at(self, when: date) -> bool:
        if self.effective_from and when < self.effective_from:
            return False
        if self.effective_to and when > self.effective_to:
            return False
        if self.superseded_by:
            return False
        return True


class KnowledgeVersioner:
    def __init__(self) -> None:
        self._versions: dict[str, list[KnowledgeVersion]] = {}

    def register(self, v: KnowledgeVersion) -> None:
        self._versions.setdefault(v.kind, []).append(v)

    def history_of(self, kind: str) -> list[dict[str, Any]]:
        items = self._versions.get(kind, [])
        return [
            {
                "id": v.id,
                "kind": v.kind,
                "jurisdiction": v.jurisdiction,
                "title": v.title,
                "effective_from": str(v.effective_from) if v.effective_from else None,
                "effective_to": str(v.effective_to) if v.effective_to else None,
                "superseded_by": v.superseded_by,
            }
            for v in items
        ]

    def active_at(self, kind: str, when: date | None = None) -> list[KnowledgeVersion]:
        when = when or date.today()
        return [v for v in self._versions.get(kind, []) if v.is_active_at(when)]
