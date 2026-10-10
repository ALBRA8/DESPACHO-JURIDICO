"""
Human-in-the-Loop Gate ALBRA - V1.6.

P1: HITL state persiste en sqlite para sobrevivir restart.
P1: Una denegación NUNCA puede convertirse en ejecución.

Estados de un ApprovalRequest:
- pending: esperando decisión
- approved: humano lo aprobó
- denied: humano lo rechazó - bloquea ejecución
- expired: timeout pasado sin decisión
- cancelled: requester canceló
- resumed: acción retomada tras approval (no re-ejecutable)
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger

# Timeout default: 24h
DEFAULT_TIMEOUT_SECONDS = 86400


@dataclass
class ApprovalRequest:
    id: str
    user: str
    action: str
    resource: str
    risk: str
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    requested_at: float = field(default_factory=time.time)
    decided_at: float | None = None
    decided_by: str | None = None
    reason: str = ""
    expires_at: float = 0.0  # 0 = no expira

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user": self.user,
            "action": self.action,
            "resource": self.resource,
            "risk": self.risk,
            "payload": self.payload,
            "status": self.status,
            "requested_at": self.requested_at,
            "decided_at": self.decided_at,
            "decided_by": self.decided_by,
            "reason": self.reason,
            "expires_at": self.expires_at,
        }


class HITLGate:
    def __init__(self, settings: Settings, *, db_path: str | None = None) -> None:
        self.settings = settings
        self.log = get_logger("albra.hitl")
        self._db_path = db_path or str(Path(settings.audit_path).parent / "hitl.db")
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS approval_requests (
                id TEXT PRIMARY KEY,
                user TEXT NOT NULL,
                action TEXT NOT NULL,
                resource TEXT,
                risk TEXT,
                payload_json TEXT DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending',
                requested_at REAL NOT NULL,
                decided_at REAL,
                decided_by TEXT,
                reason TEXT DEFAULT '',
                expires_at REAL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_hitl_status ON approval_requests(status);
            CREATE INDEX IF NOT EXISTS idx_hitl_user ON approval_requests(user);
            """
        )
        self._conn.commit()

    async def startup(self) -> None:
        """Rehidrata pending approvals tras restart."""
        cur = self._conn.execute("SELECT COUNT(*) FROM approval_requests WHERE status='pending'")
        count = cur.fetchone()[0]
        self.log.info("hitl.startup", pending=count, db=self._db_path)

    async def shutdown(self) -> None:
        if self._conn:
            self._conn.close()

    async def request_approval(
        self,
        *,
        user: str,
        action: str,
        resource: str = "",
        risk: str = "medium",
        payload: dict[str, Any] | None = None,
        expires_in_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> ApprovalRequest:
        rid = uuid.uuid4().hex[:12]
        now = time.time()
        expires_at = now + expires_in_seconds if expires_in_seconds > 0 else 0
        req = ApprovalRequest(
            id=rid, user=user, action=action, resource=resource, risk=risk,
            payload=payload or {}, expires_at=expires_at,
        )
        self._conn.execute(
            "INSERT INTO approval_requests (id, user, action, resource, risk, payload_json, "
            "status, requested_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
            (rid, user, action, resource, risk, json.dumps(payload or {}),
             now, expires_at),
        )
        self._conn.commit()
        self.log.info("hitl.requested", id=rid, action=action, risk=risk, user=user)
        return req

    async def approve(self, request_id: str, *, by: str, reason: str = "") -> bool:
        req = self._get(request_id)
        if not req:
            return False
        if req.status != "pending":
            self.log.warning("hitl.approve.already_decided", id=request_id, status=req.status)
            return False
        # Check expiry
        if self._is_expired(req):
            await self._expire(request_id)
            return False
        self._conn.execute(
            "UPDATE approval_requests SET status='approved', decided_at=?, decided_by=?, reason=? WHERE id=?",
            (time.time(), by, reason, request_id),
        )
        self._conn.commit()
        self.log.info("hitl.approved", id=request_id, by=by)
        return True

    async def deny(self, request_id: str, *, by: str, reason: str = "") -> bool:
        """Denegación PERMANENTE - no puede re-ejecutarse."""
        req = self._get(request_id)
        if not req:
            return False
        if req.status != "pending":
            return False
        self._conn.execute(
            "UPDATE approval_requests SET status='denied', decided_at=?, decided_by=?, reason=? WHERE id=?",
            (time.time(), by, reason, request_id),
        )
        self._conn.commit()
        self.log.info("hitl.denied", id=request_id, by=by, reason=reason)
        return True

    async def cancel(self, request_id: str, *, by: str) -> bool:
        req = self._get(request_id)
        if not req or req.status != "pending":
            return False
        self._conn.execute(
            "UPDATE approval_requests SET status='cancelled', decided_at=?, decided_by=? WHERE id=?",
            (time.time(), by, request_id),
        )
        self._conn.commit()
        return True

    async def resume(self, request_id: str) -> dict[str, Any]:
        """Reanudar tras approval. Si denied/expired → rechazo."""
        req = self._get(request_id)
        if not req:
            return {"ok": False, "reason": "not_found"}
        if req.status == "denied":
            return {"ok": False, "reason": "denied", "permanent": True}
        if req.status == "expired":
            return {"ok": False, "reason": "expired"}
        if req.status == "cancelled":
            return {"ok": False, "reason": "cancelled"}
        if req.status == "approved":
            # Mark as resumed (idempotente - segunda vez no re-ejecuta)
            self._conn.execute(
                "UPDATE approval_requests SET status='resumed' WHERE id=? AND status='approved'",
                (request_id,),
            )
            self._conn.commit()
            return {"ok": True, "reason": "resumed"}
        if req.status == "resumed":
            return {"ok": False, "reason": "already_resumed", "permanent": True}
        # pending
        if self._is_expired(req):
            await self._expire(request_id)
            return {"ok": False, "reason": "expired"}
        return {"ok": False, "reason": "still_pending"}

    def _get(self, request_id: str) -> ApprovalRequest | None:
        cur = self._conn.execute(
            "SELECT id, user, action, resource, risk, payload_json, status, "
            "requested_at, decided_at, decided_by, reason, expires_at "
            "FROM approval_requests WHERE id=?",
            (request_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return ApprovalRequest(
            id=row[0], user=row[1], action=row[2], resource=row[3] or "", risk=row[4] or "medium",
            payload=json.loads(row[5]) if row[5] else {},
            status=row[6], requested_at=row[7], decided_at=row[8],
            decided_by=row[9], reason=row[10] or "", expires_at=row[11] or 0,
        )

    def _is_expired(self, req: ApprovalRequest) -> bool:
        if req.expires_at == 0:
            return False
        return time.time() > req.expires_at

    async def _expire(self, request_id: str) -> None:
        self._conn.execute(
            "UPDATE approval_requests SET status='expired', decided_at=? WHERE id=? AND status='pending'",
            (time.time(), request_id),
        )
        self._conn.commit()

    def status(self, request_id: str) -> str | None:
        req = self._get(request_id)
        return req.status if req else None

    def pending(self) -> list[ApprovalRequest]:
        cur = self._conn.execute(
            "SELECT id FROM approval_requests WHERE status='pending' ORDER BY requested_at DESC"
        )
        return [self._get(r[0]) for r in cur.fetchall() if r[0]]

    async def cleanup_expired(self) -> int:
        """Limpia approvals expirados."""
        now = time.time()
        cur = self._conn.execute(
            "UPDATE approval_requests SET status='expired', decided_at=? "
            "WHERE status='pending' AND expires_at > 0 AND expires_at < ?",
            (now, now),
        )
        self._conn.commit()
        return cur.rowcount
