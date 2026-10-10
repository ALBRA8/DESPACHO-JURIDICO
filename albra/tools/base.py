"""
Base de Tool ALBRA.

Cada tool debe:
- declarar nombre, descripción, schema de input, riesgo, permiso requerido
- ser aislada del razonamiento (no accede al cerebro)
- mantener trazabilidad (devuelve ToolResult con metadata)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass
class ToolResult:
    """Resultado estándar de toda tool."""

    ok: bool
    value: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "value": self.value,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass
class Tool:
    """Definición de una herramienta."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Awaitable[ToolResult]]
    risk: str = "low"  # low | medium | high | critical
    required_permission: str = "tools.invoke"
    category: str = "general"
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "risk": self.risk,
            "required_permission": self.required_permission,
            "category": self.category,
            "metadata": self.metadata,
        }
