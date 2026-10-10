"""
Contexto de ejecución - mantiene el estado de una tarea/conversación.

Atributos clave:
- task_id: identificador único de la tarea actual
- session_id: sesión conversacional
- user: identidad del usuario
- history: historial de pasos
- memory_pointer: referencia a memoria relevante
- approvals_pending: acciones que requieren HITL
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunContext:
    """Contexto vivo de una ejecución del agente."""

    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    user: str = "anon"
    channel: str = "text"
    started_at: float = field(default_factory=time.time)
    iteration: int = 0
    max_iterations: int = 20
    history: list[dict[str, Any]] = field(default_factory=list)
    pending_approvals: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def step(self, name: str, **kwargs: Any) -> None:
        self.iteration += 1
        self.history.append(
            {"step": name, "iter": self.iteration, "ts": time.time(), **kwargs}
        )

    def request_approval(self, action: str, payload: dict[str, Any]) -> str:
        approval_id = uuid.uuid4().hex[:12]
        self.pending_approvals.append(
            {
                "id": approval_id,
                "action": action,
                "payload": payload,
                "ts": time.time(),
                "status": "pending",
            }
        )
        return approval_id

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "user": self.user,
            "channel": self.channel,
            "iteration": self.iteration,
            "history_len": len(self.history),
            "pending_approvals": len(self.pending_approvals),
            "metadata": self.metadata,
        }
