"""
Handoff Protocol ALBRA.

Permite al agente base ENTREGAR y RECIBIR tareas de otros agentes
ALBRA en el futuro (especialistas jurídicos como constitucional, civil,
penal, etc.).

NO se construyen los especialistas ahora - solo el protocolo.

Envelope:
- task_id
- from_agent (codename del agente origen)
- to_agent (codename del destino - ej. "ALBRA-CIVIL-V1")
- context (resumen, evidencia_ids, memoria_pointers)
- permissions (heredados / delegados)
- evidence_ids (lista de evidencia relevante)
- audit_trail (eventos relevantes)
- status
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HandoffEnvelope:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    task_id: str = ""
    from_agent: str = ""
    to_agent: str = ""
    intent: str = ""  # qué se quiere que haga el receptor
    context: dict[str, Any] = field(default_factory=dict)
    permissions: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    audit_trail: list[dict[str, Any]] = field(default_factory=list)
    status: str = "sent"  # sent | received | in_progress | returned | failed
    created_at: float = field(default_factory=time.time)
    received_at: float | None = None

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
        }


class HandoffProtocol:
    """Protocolo para delegar tareas entre agentes ALBRA.

    Implementación mínima: el agente base puede preparar handoffs
    pero como no hay especialistas todavía, los handoffs quedan en
    estado 'queued' (en cola esperando receptores).
    """

    def __init__(self) -> None:
        self._queue: list[HandoffEnvelope] = []
        self._replies: dict[str, HandoffEnvelope] = {}

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
    ) -> HandoffEnvelope:
        env = HandoffEnvelope(
            task_id=task_id,
            from_agent=from_agent,
            to_agent=to_agent,
            intent=intent,
            context=context or {},
            permissions=permissions or [],
            evidence_ids=evidence_ids or [],
        )
        self._queue.append(env)
        return env

    def queued_handoffs(self) -> list[HandoffEnvelope]:
        return [e for e in self._queue if e.status == "sent"]

    def receive_reply(self, envelope: HandoffEnvelope) -> None:
        envelope.status = "returned"
        envelope.received_at = time.time()
        self._replies[envelope.id] = envelope

    def get_reply(self, envelope_id: str) -> HandoffEnvelope | None:
        return self._replies.get(envelope_id)
