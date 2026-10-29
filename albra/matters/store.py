"""
MATTER STORE — SQLite WAL para matters + parties + pending_actions.

Índice en DB; contenido (drafts, evidencia) en filesystem.

Por qué SQLite:
- Búsquedas rápidas por estado, área, cliente.
- WAL mode → lectores no bloquean escritor.
- Embedded — sin servidor que mantener.

Por qué WAL:
- Concurrente con CLI y API.
- Single-writer, multi-reader — suficiente para despacho pequeño.

Schema:
    matters
      id TEXT PRIMARY KEY
      client TEXT NOT NULL
      area TEXT NOT NULL
      state TEXT NOT NULL
      created_by TEXT
      created_at TEXT NOT NULL
      updated_at TEXT NOT NULL
      state_history_json TEXT
      deadlines_json TEXT
      metadata_json TEXT

    parties
      id TEXT PRIMARY KEY
      matter_id TEXT NOT NULL REFERENCES matters(id) ON DELETE CASCADE
      name TEXT NOT NULL
      role TEXT
      created_at TEXT

    pending_actions
      id TEXT PRIMARY KEY
      matter_id TEXT NOT NULL REFERENCES matters(id)
      action_type TEXT NOT NULL
      description TEXT
      minimum_human_signoff INTEGER DEFAULT 1
      approvals_json TEXT
      status TEXT NOT NULL
      created_at TEXT NOT NULL
      decided_at TEXT
      decided_by TEXT
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from albra.matters.matter import (
    MATTER_STATES,
    Matter,
)
from albra.observability.logger import get_logger


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MatterStore:
    """Persistencia de matters en SQLite WAL."""

    def __init__(self, db_path: str = "./data/matters.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log = get_logger("albra.matters.store")
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        # WAL mode: lectores no bloquean escritor
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS matters (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                client TEXT NOT NULL,
                area TEXT NOT NULL,
                state TEXT NOT NULL,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                state_history_json TEXT NOT NULL DEFAULT '[]',
                deadlines_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_matters_tenant ON matters(tenant_id);

            CREATE TABLE IF NOT EXISTS parties (
                id TEXT PRIMARY KEY,
                matter_id TEXT NOT NULL REFERENCES matters(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                role TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pending_actions (
                id TEXT PRIMARY KEY,
                matter_id TEXT NOT NULL REFERENCES matters(id) ON DELETE CASCADE,
                action_type TEXT NOT NULL,
                description TEXT,
                minimum_human_signoff INTEGER NOT NULL DEFAULT 1,
                approvals_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TEXT NOT NULL,
                decided_at TEXT,
                decided_by TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_matters_state ON matters(state);
            CREATE INDEX IF NOT EXISTS idx_matters_area ON matters(area);
            CREATE INDEX IF NOT EXISTS idx_matters_client ON matters(client);
            CREATE INDEX IF NOT EXISTS idx_parties_matter ON parties(matter_id);
            CREATE INDEX IF NOT EXISTS idx_pending_matter ON pending_actions(matter_id);
            CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_actions(status);
            """
        )
        self._conn.commit()

    # ===== CRUD: matters =====

    def create_matter(
        self,
        *,
        client: str,
        area: str,
        parties: list[str] | None = None,
        created_by: str = "cli",
        deadlines: list[dict[str, str]] | None = None,
        metadata: dict[str, Any] | None = None,
        tenant_id: str = "default",
    ) -> Matter:
        matter = Matter(
            client=client,
            area=area,
            parties=parties or [],
            created_by=created_by,
            deadlines=deadlines or [],
            metadata=metadata or {},
        )
        self._conn.execute(
            """
            INSERT INTO matters
            (id, tenant_id, client, area, state, created_by, created_at, updated_at,
             state_history_json, deadlines_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                matter.id, tenant_id, matter.client, matter.area, matter.state,
                matter.created_by, matter.created_at, matter.updated_at,
                json.dumps(matter.state_history, ensure_ascii=False),
                json.dumps(matter.deadlines, ensure_ascii=False),
                json.dumps(matter.metadata, ensure_ascii=False, default=str),
            ),
        )
        # Parties
        for name in matter.parties:
            self._conn.execute(
                "INSERT INTO parties (id, matter_id, name, role, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, matter.id, name, "", matter.created_at),
            )
        self._conn.commit()
        self.log.info("matter.create", matter_id=matter.id, client=client, area=area)
        return matter

    def get_matter(self, matter_id: str) -> Matter | None:
        cur = self._conn.execute(
            "SELECT id, client, area, state, created_by, created_at, updated_at, "
            "state_history_json, deadlines_json, metadata_json "
            "FROM matters WHERE id = ?",
            (matter_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        # Parties
        pcur = self._conn.execute(
            "SELECT name, role FROM parties WHERE matter_id = ? ORDER BY created_at",
            (matter_id,),
        )
        parties = [{"name": r[0], "role": r[1]} for r in pcur.fetchall()]
        return Matter(
            id=row[0], client=row[1], area=row[2], state=row[3],
            created_by=row[4] or "", created_at=row[5], updated_at=row[6],
            state_history=json.loads(row[7]),
            deadlines=json.loads(row[8]),
            metadata=json.loads(row[9]),
            parties=[p["name"] for p in parties],
        )

    def list_matters(
        self,
        *,
        state: str | None = None,
        area: str | None = None,
        client: str | None = None,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> list[Matter]:
        q = "SELECT id FROM matters WHERE 1=1"
        args: list[Any] = []
        if tenant_id:
            q += " AND tenant_id = ?"
            args.append(tenant_id)
        if state:
            q += " AND state = ?"
            args.append(state)
        if area:
            q += " AND area = ?"
            args.append(area)
        if client:
            q += " AND client LIKE ?"
            args.append(f"%{client}%")
        q += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        cur = self._conn.execute(q, args)
        return [m for (mid,) in cur.fetchall() if (m := self.get_matter(mid)) is not None]

    def advance_state(
        self,
        matter_id: str,
        target: str,
        *,
        by: str = "system",
        reason: str = "",
    ) -> Matter:
        """Avanza el state machine del matter. Lanza InvalidTransitionError si inválida."""
        matter = self.get_matter(matter_id)
        if not matter:
            raise KeyError(f"Matter not found: {matter_id}")
        if target not in MATTER_STATES:
            raise ValueError(f"Estado inválido: {target!r}")
        matter.transition_to(target, by=by, reason=reason)
        self._conn.execute(
            "UPDATE matters SET state = ?, updated_at = ?, state_history_json = ? "
            "WHERE id = ?",
            (
                matter.state, matter.updated_at,
                json.dumps(matter.state_history, ensure_ascii=False),
                matter.id,
            ),
        )
        self._conn.commit()
        self.log.info(
            "matter.advance", matter_id=matter_id, to=target, by=by, reason=reason
        )
        return matter

    # ===== CRUD: pending_actions =====

    def create_pending_action(
        self,
        *,
        matter_id: str,
        action_type: str,
        description: str = "",
        minimum_human_signoff: int = 1,
    ) -> str:
        action_id = uuid.uuid4().hex
        now = _utcnow_iso()
        self._conn.execute(
            """
            INSERT INTO pending_actions
            (id, matter_id, action_type, description, minimum_human_signoff,
             approvals_json, status, created_at)
            VALUES (?, ?, ?, ?, ?, '[]', 'PENDING', ?)
            """,
            (action_id, matter_id, action_type, description, minimum_human_signoff, now),
        )
        self._conn.commit()
        self.log.info(
            "pending.create", action_id=action_id, matter_id=matter_id,
            action_type=action_type, minimum_signoff=minimum_human_signoff,
        )
        return action_id

    def get_pending_action(self, action_id: str) -> dict[str, Any] | None:
        cur = self._conn.execute(
            "SELECT id, matter_id, action_type, description, minimum_human_signoff, "
            "approvals_json, status, created_at, decided_at, decided_by "
            "FROM pending_actions WHERE id = ?",
            (action_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0], "matter_id": row[1], "action_type": row[2],
            "description": row[3] or "", "minimum_human_signoff": row[4],
            "approvals": json.loads(row[5]),
            "status": row[6], "created_at": row[7],
            "decided_at": row[8], "decided_by": row[9],
        }

    def list_pending(self, matter_id: str | None = None) -> list[dict[str, Any]]:
        q = ("SELECT id FROM pending_actions WHERE status = 'PENDING' "
             "ORDER BY created_at ASC")
        args: list[Any] = []
        if matter_id:
            q = ("SELECT id FROM pending_actions WHERE status = 'PENDING' "
                 "AND matter_id = ? ORDER BY created_at ASC")
            args = [matter_id]
        cur = self._conn.execute(q, args)
        return [a for (aid,) in cur.fetchall() if (a := self.get_pending_action(aid)) is not None]

    def add_approval(
        self,
        action_id: str,
        *,
        by: str,
        role: str,
        comment: str = "",
    ) -> dict[str, Any]:
        """Añade una firma a la acción pendiente.

        Returns the updated action dict. Status becomes APPROVED when
        approvals count >= minimum_human_signoff.
        """
        action = self.get_pending_action(action_id)
        if not action:
            raise KeyError(f"Pending action not found: {action_id}")
        if action["status"] != "PENDING":
            raise ValueError(f"Action {action_id} status={action['status']} (not PENDING)")

        approval = {
            "by": by,
            "role": role,
            "ts": _utcnow_iso(),
            "comment": comment,
        }
        approvals = action["approvals"] + [approval]
        signoffs_needed = action["minimum_human_signoff"]
        now_approved = len(approvals) >= signoffs_needed

        self._conn.execute(
            "UPDATE pending_actions SET approvals_json = ?, "
            "status = ?, decided_at = ?, decided_by = ? WHERE id = ?",
            (
                json.dumps(approvals, ensure_ascii=False),
                "APPROVED" if now_approved else "PENDING",
                _utcnow_iso() if now_approved else None,
                by if now_approved else None,
                action_id,
            ),
        )
        self._conn.commit()
        self.log.info(
            "pending.approve", action_id=action_id, by=by, role=role,
            approved_count=len(approvals), needed=signoffs_needed,
            now_approved=now_approved,
        )
        updated = self.get_pending_action(action_id)
        return updated or action

    def reject_action(
        self,
        action_id: str,
        *,
        by: str,
        role: str,
        comment: str = "",
    ) -> dict[str, Any]:
        action = self.get_pending_action(action_id)
        if not action:
            raise KeyError(f"Pending action not found: {action_id}")
        if action["status"] != "PENDING":
            raise ValueError(f"Action {action_id} status={action['status']} (not PENDING)")

        self._conn.execute(
            "UPDATE pending_actions SET status = 'REJECTED', decided_at = ?, decided_by = ? "
            "WHERE id = ?",
            (_utcnow_iso(), by, action_id),
        )
        self._conn.commit()
        self.log.info(
            "pending.reject", action_id=action_id, by=by, role=role, comment=comment
        )
        return self.get_pending_action(action_id) or action

    def close(self) -> None:
        if self._conn:
            self._conn.close()
