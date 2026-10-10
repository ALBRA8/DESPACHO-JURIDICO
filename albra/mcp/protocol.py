"""
Protocolo MCP/MSP ALBRA.

MCP = Model Context Protocol (estándar abierto Anthropic).
MSP = Multi-Service Protocol ALBRA (extensión interna).

Definimos mensajes, capabilities y respuestas.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCPRequest:
    """Petición MCP estándar."""

    jsonrpc: str = "2.0"
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    method: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {
            "jsonrpc": self.jsonrpc,
            "id": self.id,
            "method": self.method,
            "params": self.params,
            "ts": self.ts,
        }


@dataclass
class MCPResponse:
    """Respuesta MCP estándar."""

    jsonrpc: str = "2.0"
    id: str = ""
    result: Any = None
    error: dict[str, Any] | None = None
    ts: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "jsonrpc": self.jsonrpc,
            "id": self.id,
            "ts": self.ts,
        }
        if self.error is not None:
            out["error"] = self.error
        else:
            out["result"] = self.result
        return out


@dataclass
class MCPCapability:
    """Capability expuesta por MCP."""

    name: str
    description: str
    input_schema: dict[str, Any]
    risk: str = "low"
    required_permission: str = "tools.invoke"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "risk": self.risk,
            "required_permission": self.required_permission,
        }
