"""
Human-in-the-Loop Gate ALBRA.

Para acciones sensibles, irreversibles, externas, financieras,
comunicaciones oficiales, publicación, envío de documentos,
cambios de config críticos, modificaciones de permisos.

El agente PREPARA la acción, NO la ejecuta hasta recibir aprobación.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger


@dataclass
class ApprovalRequest:
    id: str
    user: str
    action: str
    resource: str
    risk: str
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending | approved | denied | expired
    requested_at: float = field(default_factory=time.time)
    decided_at: float | None = None
    decided_by: str | None = None
    reason: str = ""

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
        }


class HITLGate:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.hitl")
        self._requests: dict[str, ApprovalRequest] = {}

    async def request_approval(
        self,
        *,
        user: str,
        action: str,
        resource: str = "",
        risk: str = "medium",
        payload: dict[str, Any] | None = None,
    ) -> ApprovalRequest:
        rid = uuid.uuid4().hex[:12]
        req = ApprovalRequest(
            id=rid,
            user=user,
            action=action,
            resource=resource,
            risk=risk,
            payload=payload or {},
        )
        self._requests[rid] = req
        self.log.info(
            "hitl.requested",
            id=rid,
            action=action,
            risk=risk,
            user=user,
        )
        return req

    async def approve(self, request_id: str, *, by: str, reason: str = "") -> bool:
        req = self._requests.get(request_id)
        if not req:
            return False
        if req.status != "pending":
            return False
        req.status = "approved"
        req.decided_at = time.time()
        req.decided_by = by
        req.reason = reason
        self.log.info("hitl.approved", id=request_id, by=by)
        return True

    async def deny(self, request_id: str, *, by: str, reason: str = "") -> bool:
        req = self._requests.get(request_id)
        if not req:
            return False
        req.status = "denied"
        req.decided_at = time.time()
        req.decided_by = by
        req.reason = reason
        self.log.info("hitl.denied", id=request_id, by=by, reason=reason)
        return True

    def status(self, request_id: str) -> str | None:
        req = self._requests.get(request_id)
        return req.status if req else None

    def pending(self) -> list[ApprovalRequest]:
        return [r for r in self._requests.values() if r.status == "pending"]
