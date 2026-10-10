"""
Herramientas builtin de ALBRA.

Cada tool es deliberadamente simple - el organismo crece agregando tools,
no agregando código en el núcleo.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any

from albra.tools.base import Tool, ToolResult
from albra.tools.registry import ToolRegistry


async def _clock_handler(input_data: dict[str, Any], *, user: str) -> ToolResult:
    now = dt.datetime.now(dt.UTC)
    return ToolResult(
        ok=True,
        value={
            "iso": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "tz": "UTC",
        },
        metadata={"user": user},
    )


async def _calculator_handler(input_data: dict[str, Any], *, user: str) -> ToolResult:
    expr = str(input_data.get("expression", ""))
    if not expr:
        return ToolResult(ok=False, error="Falta parámetro 'expression'")
    # Solo caracteres matemáticos permitidos - no ejecutar código
    allowed = set("0123456789+-*/().,%^ ")
    safe = "".join(c for c in expr if c in allowed).replace("^", "**")
    if not safe:
        return ToolResult(ok=False, error="Expresión vacía tras sanitización")
    try:
        # Eval controlado - sin builtins
        value = eval(safe, {"__builtins__": {}}, {"math": math})
    except Exception as e:  # noqa: BLE001
        return ToolResult(ok=False, error=f"No pude calcular: {e}")
    return ToolResult(ok=True, value=value, metadata={"expression": expr})


async def _echo_handler(input_data: dict[str, Any], *, user: str) -> ToolResult:
    return ToolResult(
        ok=True,
        value=input_data.get("message", ""),
        metadata={"user": user, "echo": True},
    )


async def _memory_lookup_handler(input_data: dict[str, Any], *, user: str) -> ToolResult:
    """Placeholder - el handler real se conecta al MemoryDV en runtime."""
    return ToolResult(
        ok=True,
        value=[],
        metadata={"note": "memory lookup wired at agent boot"},
    )


def register_builtin_tools(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            name="clock",
            description="Devuelve la fecha y hora UTC actual.",
            input_schema={"type": "object", "properties": {}},
            handler=_clock_handler,
            risk="low",
            category="system",
        )
    )
    registry.register(
        Tool(
            name="calculator",
            description="Calcula expresión matemática segura (sin funciones peligrosas).",
            input_schema={
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
            handler=_calculator_handler,
            risk="low",
            category="utility",
        )
    )
    registry.register(
        Tool(
            name="echo",
            description="Devuelve el mensaje recibido - útil para diagnóstico.",
            input_schema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
            handler=_echo_handler,
            risk="low",
            category="debug",
        )
    )
    registry.register(
        Tool(
            name="memory_lookup",
            description="Busca en la memoria del agente (memorydv).",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
            handler=_memory_lookup_handler,
            risk="low",
            required_permission="memory.read",
            category="memory",
        )
    )
