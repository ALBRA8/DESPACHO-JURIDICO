"""
INSTALL LOG — registro auditable de skills instaladas.

Inspiración clean-room: Claude for Legal pattern (install log: un registro
auditable de lo que se instala, desde dónde, bajo qué licencia, con qué
veredicto de revisión). Extiende V2.0 MatterAudit con entries tipo
skill_installed, skill_uninstalled, skill_updated.

V2.5-D: standalone audit log para skill installations. NO reemplaza
MatterAudit (per-matter); es un log separado para el sistema global
de skills del despacho.

Formato: JSONL append-only con hash chain (igual patrón tamper-evident
que MatterAudit V2.0 y audit/tamper_evident.py).

Cada entry incluye:
- ts (ISO 8601 UTC)
- event_type (skill_installed | skill_uninstalled | skill_updated |
               skill_activated | skill_deactivated)
- skill_id
- version
- source (marketplace | manual | git_url)
- license (Apache-2.0 | MIT | AGPL-3.0 | proprietary | unknown)
- review_verdict (approved | rejected | pending)
- reviewer (user_id que aprobó, o "system" si auto-installed)
- payload (metadata adicional)
- prev_hash, this_hash (SHA-256 hash chain)
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from albra.observability.logger import get_logger


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Event types soportados
EVENT_TYPES: frozenset[str] = frozenset({
    "skill_installed",
    "skill_uninstalled",
    "skill_updated",
    "skill_activated",
    "skill_deactivated",
    "skill_reviewed",
})

# Verdicts soportados
VERDICTS: frozenset[str] = frozenset({
    "approved", "rejected", "pending",
})

# Sources soportados
SOURCES: frozenset[str] = frozenset({
    "marketplace", "manual", "git_url", "internal",
})


@dataclass
class InstallLogEntry:
    """Una entrada del install log."""
    ts: str
    event_type: str
    skill_id: str
    version: str = ""
    source: str = "internal"
    license: str = "unknown"
    review_verdict: str = "pending"
    reviewer: str = "system"
    payload: dict[str, Any] = field(default_factory=dict)
    prev_hash: str = ""
    this_hash: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "event_type": self.event_type,
            "skill_id": self.skill_id,
            "version": self.version,
            "source": self.source,
            "license": self.license,
            "review_verdict": self.review_verdict,
            "reviewer": self.reviewer,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "this_hash": self.this_hash,
        }


class InstallLog:
    """Audit log JSONL append-only con hash chain para skill installations."""

    GENESIS_HASH = "0" * 64

    def __init__(self, log_path: str = "./data/install_audit.jsonl") -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.touch(exist_ok=True)
        self.log = get_logger("albra.audit.install_log")
        self._prev_hash = self._load_last_hash()

    def _load_last_hash(self) -> str:
        last = self.GENESIS_HASH
        try:
            with open(self.log_path, encoding="utf-8") as f:
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

    def append(
        self,
        *,
        event_type: str,
        skill_id: str,
        version: str = "",
        source: str = "internal",
        license: str = "unknown",
        review_verdict: str = "pending",
        reviewer: str = "system",
        payload: dict[str, Any] | None = None,
    ) -> InstallLogEntry:
        """Append entry con hash chain. Validates event_type, source, verdict."""
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Unknown event_type: {event_type!r}. Valid: {sorted(EVENT_TYPES)}")
        if source not in SOURCES:
            raise ValueError(f"Unknown source: {source!r}. Valid: {sorted(SOURCES)}")
        if review_verdict not in VERDICTS:
            raise ValueError(f"Unknown verdict: {review_verdict!r}. Valid: {sorted(VERDICTS)}")

        ts = _utcnow_iso()
        block = {
            "ts": ts,
            "event_type": event_type,
            "skill_id": skill_id,
            "version": version,
            "source": source,
            "license": license,
            "review_verdict": review_verdict,
            "reviewer": reviewer,
            "payload": payload or {},
            "prev_hash": self._prev_hash,
        }
        block_str = json.dumps(block, sort_keys=True, ensure_ascii=False, default=str)
        this_hash = hashlib.sha256(block_str.encode("utf-8")).hexdigest()
        block["this_hash"] = this_hash

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(block, ensure_ascii=False, default=str) + "\n")

        self._prev_hash = this_hash
        self.log.info(
            "install_log.append", event_type=event_type, skill_id=skill_id,
            hash=this_hash[:12],
        )
        return InstallLogEntry(**block)

    def verify_chain(self) -> dict[str, Any]:
        """Verifica integridad del hash chain. Devuelve ok=True si no fue manipulado."""
        prev = self.GENESIS_HASH
        total = 0
        broken_at: list[int] = []
        try:
            with open(self.log_path, encoding="utf-8") as f:
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
                    if expected_prev != prev:
                        broken_at.append(i)
                        prev = this_hash or prev
                        continue
                    block_copy = {k: v for k, v in entry.items() if k != "this_hash"}
                    block_str = json.dumps(
                        block_copy, sort_keys=True, ensure_ascii=False, default=str
                    )
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

    def read(
        self,
        *,
        event_type: str | None = None,
        skill_id: str | None = None,
        limit: int | None = None,
    ) -> list[InstallLogEntry]:
        """Lee entries del install log."""
        entries: list[InstallLogEntry] = []
        with open(self.log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    if event_type and e.get("event_type") != event_type:
                        continue
                    if skill_id and e.get("skill_id") != skill_id:
                        continue
                    entries.append(InstallLogEntry(**e))
                except (json.JSONDecodeError, TypeError):
                    continue
        if limit:
            entries = entries[-limit:]
        return entries

    def count(self) -> int:
        c = 0
        with open(self.log_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    c += 1
        return c

    def fingerprint(self) -> str:
        """Hash del archivo completo para comparar con backups."""
        h = hashlib.sha256()
        with open(self.log_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def get_install_history(self, skill_id: str) -> list[InstallLogEntry]:
        """Devuelve la historia de un skill específico (todos sus events)."""
        return self.read(skill_id=skill_id)

    def list_installed_skills(self) -> list[str]:
        """Lista IDs únicos de skills que han sido instalados (event_type=skill_installed)."""
        installed: list[str] = []
        seen: set[str] = set()
        for entry in self.read(event_type="skill_installed"):
            if entry.skill_id not in seen:
                seen.add(entry.skill_id)
                installed.append(entry.skill_id)
        return installed

    def stats(self) -> dict[str, Any]:
        """Estadísticas del install log."""
        all_entries = self.read()
        by_event_type: dict[str, int] = {}
        by_skill: dict[str, int] = {}
        by_verdict: dict[str, int] = {}
        for e in all_entries:
            by_event_type[e.event_type] = by_event_type.get(e.event_type, 0) + 1
            by_skill[e.skill_id] = by_skill.get(e.skill_id, 0) + 1
            by_verdict[e.review_verdict] = by_verdict.get(e.review_verdict, 0) + 1
        return {
            "total_entries": len(all_entries),
            "total_skills_installed": len(self.list_installed_skills()),
            "by_event_type": by_event_type,
            "by_skill": by_skill,
            "by_verdict": by_verdict,
            "log_path": str(self.log_path),
            "fingerprint": self.fingerprint(),
        }
