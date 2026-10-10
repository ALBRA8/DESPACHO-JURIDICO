"""
Handoff Transport ALBRA - separación Protocol vs Transport.

P1: HandoffProtocol define el envelope.
Transport = cómo se entrega el envelope entre agentes.

Transports:
- InProcessTransport (default, mismo proceso)
- MockTransport (testing - registra envíos sin enviar)
- HTTPTransport (futuro - requiere server receptor)
- QueueTransport (futuro - requiere message queue)

Sin transporte real configurado → in-process con mock.
NO inventamos endpoints HTTP ni credenciales.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from albra.observability.logger import get_logger


class HandoffTransport(ABC):
    """Interface para transportar envelopes entre agentes."""

    name: str = "abstract"

    @abstractmethod
    async def send(self, envelope: HandoffEnvelope) -> dict[str, Any]:
        """Envía envelope. Returns: {"ok": bool, "transport_id": str, ...}"""

    @abstractmethod
    async def receive(self, timeout: float = 5.0) -> list[HandoffEnvelope]:
        """Recibe envelopes pendientes."""

    async def startup(self) -> None: ...
    async def shutdown(self) -> None: ...


@dataclass
class HandoffEnvelope:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    task_id: str = ""
    from_agent: str = ""
    to_agent: str = ""
    intent: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    permissions: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    audit_trail: list[dict[str, Any]] = field(default_factory=list)
    status: str = "sent"  # sent | received | in_progress | returned | failed
    created_at: float = field(default_factory=time.time)
    received_at: float | None = None
    execution_id: str | None = None
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "intent": self.intent,
            "context": self.context,
            "permissions": self.permissions,
            "evidence_ids": self.evidence_ids,
            "audit_trail": self.audit_trail,
            "status": self.status,
            "created_at": self.created_at,
            "received_at": self.received_at,
            "execution_id": self.execution_id,
            "confidence": self.confidence,
            "warnings": list(self.warnings),
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), default=str)

    @classmethod
    def from_json(cls, s: str) -> HandoffEnvelope:
        d = json.loads(s)
        return cls(**d)


class InProcessTransport(HandoffTransport):
    """In-process transport - cola en memoria."""

    name = "in_process"

    def __init__(self) -> None:
        self.log = get_logger("albra.handoff.in_process")
        self._queue: list[HandoffEnvelope] = []
        self._replies: dict[str, HandoffEnvelope] = {}

    async def send(self, envelope: HandoffEnvelope) -> dict[str, Any]:
        self._queue.append(envelope)
        self.log.info(
            "handoff.sent",
            envelope_id=envelope.id,
            from_agent=envelope.from_agent,
            to_agent=envelope.to_agent,
        )
        return {
            "ok": True,
            "transport": self.name,
            "envelope_id": envelope.id,
            "queued": True,
        }

    async def receive(self, timeout: float = 5.0) -> list[HandoffEnvelope]:
        # Si no hay items, esperar hasta timeout
        deadline = time.time() + timeout
        while not self._queue and time.time() < deadline:
            await asyncio.sleep(0.05)
        items = list(self._queue)
        self._queue.clear()
        return items

    def reply(self, envelope_id: str, reply: HandoffEnvelope) -> None:
        reply.status = "returned"
        reply.received_at = time.time()
        self._replies[envelope_id] = reply

    def get_reply(self, envelope_id: str) -> HandoffEnvelope | None:
        return self._replies.get(envelope_id)


class MockTransport(HandoffTransport):
    """Mock transport - registra envíos sin entregar."""

    name = "mock"

    def __init__(self) -> None:
        self.log = get_logger("albra.handoff.mock")
        self.sent: list[HandoffEnvelope] = []
        self.fail_on_send = False

    async def send(self, envelope: HandoffEnvelope) -> dict[str, Any]:
        if self.fail_on_send:
            return {"ok": False, "error": "mock_fail_configured"}
        self.sent.append(envelope)
        return {"ok": True, "transport": self.name, "envelope_id": envelope.id}

    async def receive(self, timeout: float = 5.0) -> list[HandoffEnvelope]:
        return []


class HandoffProtocol:
    """Protocol - usa Transport para enviar/recibir envelopes."""

    def __init__(self, *, transport: HandoffTransport | None = None) -> None:
        self.transport = transport or InProcessTransport()
        self.log = get_logger("albra.handoff.protocol")
        self._envelopes: dict[str, HandoffEnvelope] = {}

    def prepare(
        self,
        *,
        task_id: str,
        from_agent: str,
        to_agent: str,
        intent: str,
        context: dict[str, Any] | None = None,
        permissions: list[str] | None = None,
        evidence_ids: list[str] | None = None,
        execution_id: str | None = None,
        confidence: float = 0.0,
        warnings: list[str] | None = None,
    ) -> HandoffEnvelope:
        env = HandoffEnvelope(
            task_id=task_id,
            from_agent=from_agent,
            to_agent=to_agent,
            intent=intent,
            context=context or {},
            permissions=permissions or [],
            evidence_ids=evidence_ids or [],
            execution_id=execution_id,
            confidence=confidence,
            warnings=list(warnings or []),
        )
        self._envelopes[env.id] = env
        return env

    async def send(self, envelope: HandoffEnvelope) -> dict[str, Any]:
        """Envía via transport."""
        envelope.status = "sent"
        return await self.transport.send(envelope)

    async def receive(self, timeout: float = 5.0) -> list[HandoffEnvelope]:
        return await self.transport.receive(timeout=timeout)

    def get(self, envelope_id: str) -> HandoffEnvelope | None:
        return self._envelopes.get(envelope_id)

    def queued_handoffs(self) -> list[HandoffEnvelope]:
        if hasattr(self.transport, "_queue"):
            return list(self.transport._queue)
        return []

    async def startup(self) -> None:
        await self.transport.startup()

    async def shutdown(self) -> None:
        await self.transport.shutdown()
