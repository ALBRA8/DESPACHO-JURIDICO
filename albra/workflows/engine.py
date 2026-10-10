"""
Workflow Engine - representación de tareas, subtaskas, estados.

Estados:
- pending
- running
- awaiting_approval (HITL)
- succeeded
- failed
- cancelled
"""
from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from albra.config.settings import Settings
from albra.events.bus import EventBus
from albra.observability.logger import get_logger


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING = "awaiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    name: str = ""
    status: TaskStatus = TaskStatus.PENDING
    parent_id: str | None = None
    subtasks: list[str] = field(default_factory=list)
    started_at: float = 0.0
    ended_at: float = 0.0
    result: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "parent_id": self.parent_id,
            "subtasks": self.subtasks,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }


class WorkflowEngine:
    def __init__(self, settings: Settings, *, event_bus: EventBus) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.log = get_logger("albra.workflows")
        self._tasks: dict[str, Task] = {}

    async def startup(self) -> None:
        self.log.info("workflows.startup")

    async def shutdown(self) -> None:
        self.log.info("workflows.shutdown")

    async def create_task(self, name: str, *, parent_id: str | None = None, metadata: dict[str, Any] | None = None) -> Task:
        t = Task(name=name, parent_id=parent_id, metadata=metadata or {})
        self._tasks[t.id] = t
        await self.event_bus.emit("workflow.task.created", t.as_dict())
        return t

    async def start(self, task_id: str) -> bool:
        t = self._tasks.get(task_id)
        if not t or t.status != TaskStatus.PENDING:
            return False
        t.status = TaskStatus.RUNNING
        t.started_at = time.time()
        await self.event_bus.emit("workflow.task.started", t.as_dict())
        return True

    async def set_awaiting(self, task_id: str) -> bool:
        t = self._tasks.get(task_id)
        if not t:
            return False
        t.status = TaskStatus.AWAITING
        await self.event_bus.emit("workflow.task.awaiting", t.as_dict())
        return True

    async def complete(self, task_id: str, *, result: Any = None) -> bool:
        t = self._tasks.get(task_id)
        if not t:
            return False
        t.status = TaskStatus.SUCCEEDED
        t.ended_at = time.time()
        t.result = result
        await self.event_bus.emit("workflow.task.succeeded", t.as_dict())
        return True

    async def fail(self, task_id: str, *, error: str) -> bool:
        t = self._tasks.get(task_id)
        if not t:
            return False
        t.status = TaskStatus.FAILED
        t.ended_at = time.time()
        t.error = error
        await self.event_bus.emit("workflow.task.failed", t.as_dict())
        return True

    async def cancel(self, task_id: str) -> bool:
        t = self._tasks.get(task_id)
        if not t:
            return False
        t.status = TaskStatus.CANCELLED
        t.ended_at = time.time()
        await self.event_bus.emit("workflow.task.cancelled", t.as_dict())
        return True

    async def add_subtask(self, parent_id: str, sub: Task) -> None:
        parent = self._tasks.get(parent_id)
        if parent:
            parent.subtasks.append(sub.id)
            sub.parent_id = parent_id
        self._tasks[sub.id] = sub

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def list(self, *, status: TaskStatus | None = None) -> list[dict[str, Any]]:
        items = list(self._tasks.values())
        if status:
            items = [t for t in items if t.status == status]
        return [t.as_dict() for t in items]
