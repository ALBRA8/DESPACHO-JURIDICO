"""
MCP Client ALBRA.

Permite al agente CONSUMIR capacidades de servers MCP externos.
Diseñado para ser agnóstico al transporte (HTTP, stdio, SSE).

NO simula integraciones - solo hace las llamadas si hay un endpoint real.
Si no hay endpoint configurado, devuelve error explícito.
"""
from __future__ import annotations

from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger
from albra.mcp.protocol import MCPRequest, MCPResponse


class MCPClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.mcp.client")
        self._servers: dict[str, dict[str, Any]] = {}  # name -> {url, transport}

    def register_server(self, name: str, url: str, transport: str = "http") -> None:
        self._servers[name] = {"url": url, "transport": transport}
        self.log.info("mcp.client.server_registered", name=name, url=url, transport=transport)

    def list_servers(self) -> list[str]:
        return list(self._servers.keys())

    async def call(
        self,
        server: str,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float = 30.0,
    ) -> MCPResponse:
        """Llama a un método en un server MCP externo."""
        if server not in self._servers:
            return MCPResponse(
                error={
                    "code": -32602,
                    "message": f"Server MCP '{server}' no está registrado. "
                    "Configúralo antes de usarlo. ALBRA NO inventa integraciones.",
                }
            )
        cfg = self._servers[server]
        # Intentar HTTP si hay httpx disponible
        try:
            import httpx  # type: ignore[import]
        except ImportError:
            return MCPResponse(
                error={
                    "code": -32603,
                    "message": "httpx no instalado. Instala con: pip install httpx",
                }
            )

        req = MCPRequest(method=method, params=params or {})
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(cfg["url"], json=req.as_dict())
                r.raise_for_status()
                data = r.json()
                return MCPResponse(
                    id=data.get("id", req.id),
                    result=data.get("result"),
                    error=data.get("error"),
                )
        except Exception as e:  # noqa: BLE001
            self.log.error("mcp.client.call.error", server=server, error=str(e))
            return MCPResponse(
                error={"code": -32603, "message": str(e)}
            )

    async def discover_tools(self, server: str) -> dict[str, Any]:
        """Descubre tools disponibles en un server MCP."""
        resp = await self.call(server, "tools/list")
        if resp.error:
            return {"ok": False, "error": resp.error, "tools": []}
        tools = (resp.result or {}).get("tools", [])
        return {"ok": True, "tools": tools}

    async def startup(self) -> None:
        self.log.info("mcp.client.startup", servers=list(self._servers.keys()))

    async def shutdown(self) -> None:
        self.log.info("mcp.client.shutdown")
