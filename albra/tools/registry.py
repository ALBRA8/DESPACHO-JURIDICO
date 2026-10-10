"""
Registry de herramientas ALBRA.

Maneja:
- registro de tools
- lookup
- invocación con autorización y trazabilidad
"""
from __future__ import annotations

import uuid
from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger
from albra.observability.metrics import get_metrics
from albra.tools.base import Tool, ToolResult


class ToolRegistry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.tools")
        self.metrics = get_metrics()
        self._tools: dict[str, Tool] = {}

        # Autoregistro de tools builtin
        from albra.tools.builtin import register_builtin_tools
        register_builtin_tools(self)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' ya está registrada")
        self._tools[tool.name] = tool
        self.log.info("tool.registered", name=tool.name, risk=tool.risk)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self) -> list[dict[str, Any]]:
        return [t.as_dict() for t in self._tools.values()]

    async def invoke(self, name: str, input_data: dict[str, Any], *, user: str = "anon") -> dict[str, Any]:
        tool = self.get(name)
        if not tool:
            return {"ok": False, "error": f"Tool '{name}' no encontrada", "value": None}

        invocation_id = uuid.uuid4().hex[:12]
        self.log.info(
            "tool.invoke.start",
            invocation_id=invocation_id,
            tool=name,
            user=user,
            input=input_data,
        )

        with self.metrics.time_call(f"tool.{name}"):
            try:
                result: ToolResult = await tool.handler(input_data, user=user)
            except Exception as e:  # noqa: BLE001
                self.log.error("tool.invoke.exception", tool=name, error=str(e))
                result = ToolResult(ok=False, error=str(e))
                self.metrics.inc(f"tool.{name}.errors")

        if not result.ok:
            self.metrics.inc(f"tool.{name}.failures")

        self.log.info(
            "tool.invoke.end",
            invocation_id=invocation_id,
            tool=name,
            ok=result.ok,
        )
        return result.as_dict() | {"invocation_id": invocation_id, "tool": name}

    async def startup(self) -> None:
        self.log.info("tools.startup", count=len(self._tools))

    async def shutdown(self) -> None:
        self.log.info("tools.shutdown")
