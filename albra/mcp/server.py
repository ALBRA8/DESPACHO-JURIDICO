"""
MCP Server ALBRA.

Expone las tools del agente via protocolo MCP (JSON-RPC 2.0).
Endpoint HTTP/stdio preparado (no se acopla a un transporte específico).

Métodos expuestos:
- initialize
- list_tools (→ tools/list)
- call_tool (→ tools/call)
- list_capabilities (→ capabilities/list) - extensión ALBRA
- health
"""
from __future__ import annotations

from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger
from albra.mcp.protocol import MCPRequest, MCPResponse, MCPCapability


class MCPServer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.mcp.server")
        self._tool_registry: Any = None  # se inyecta en runtime
        self._cap_registry: Any = None

    def wire(self, *, tool_registry: Any, capability_registry: Any) -> None:
        self._tool_registry = tool_registry
        self._cap_registry = capability_registry

    async def startup(self) -> None:
        self.log.info("mcp.server.startup")

    async def shutdown(self) -> None:
        self.log.info("mcp.server.shutdown")

    async def handle(self, request: MCPRequest) -> MCPResponse:
        """Maneja una request MCP entrante."""
        method = request.method
        self.log.info("mcp.handle", method=method, id=request.id)
        try:
            handler = getattr(self, f"_m_{method.replace('/', '_')}", None)
            if handler is None:
                return MCPResponse(
                    id=request.id,
                    error={"code": -32601, "message": f"Method not found: {method}"},
                )
            result = await handler(request.params) if not isinstance(handler, dict) else handler
            # Si handler es estático (tools/list), response directo
            if isinstance(handler, dict):
                result = handler
            return MCPResponse(id=request.id, result=result)
        except Exception as e:  # noqa: BLE001
            self.log.error("mcp.handle.error", method=method, error=str(e))
            return MCPResponse(
                id=request.id,
                error={"code": -32603, "message": "Internal error", "data": str(e)},
            )

    # --- Métodos MCP ---

    async def _m_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": "ALBRA-MCP",
                "version": "1.0.0",
            },
            "capabilities": {
                "tools": {"listChanged": True},
                "resources": {"listChanged": True},
                "prompts": {"listChanged": True},
            },
        }

    @property
    def _m_tools_list(self) -> dict[str, Any]:  # type: ignore[override]
        if not self._tool_registry:
            return {"tools": []}
        return {"tools": self._tool_registry.list()}

    @property
    def _m_capabilities_list(self) -> dict[str, Any]:  # type: ignore[override]
        if not self._cap_registry:
            return {"capabilities": []}
        return {"capabilities": self._cap_registry.list()}

    async def _m_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        if not self._tool_registry:
            return {"ok": False, "error": "tool registry no cableada"}
        name = params.get("name")
        args = params.get("arguments", {})
        user = params.get("user", "mcp_client")
        return await self._tool_registry.invoke(name, args, user=user)

    async def _m_health(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "tools_count": len(self._tool_registry.list()) if self._tool_registry else 0,
            "capabilities_count": (
                len(self._cap_registry.list()) if self._cap_registry else 0
            ),
        }

    def expose_capabilities(self) -> list[MCPCapability]:
        """Devuelve la lista de capabilities como objetos MCP."""
        if not self._tool_registry:
            return []
        caps: list[MCPCapability] = []
        for t_dict in self._tool_registry.list():
            caps.append(
                MCPCapability(
                    name=t_dict["name"],
                    description=t_dict["description"],
                    input_schema=t_dict.get("input_schema", {}),
                    risk=t_dict.get("risk", "low"),
                    required_permission=t_dict.get("required_permission", "tools.invoke"),
                )
            )
        return caps
