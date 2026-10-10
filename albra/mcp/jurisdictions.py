"""
MCP Multi-Jurisdicción - catálogo de servers por país/provincia.

Patrón: cada jurisdicción = un MCP server. El agente puede descubrir
y consumir tools de cualquier jurisdicción sin tocar el core.

Jurisdicciones soportadas (estructura preparada - servers reales
se configuran en runtime):
- CO (Colombia) - primaria
- AR, MX, ES, BR, CL, PE, EC, US, UK (preparadas)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from albra.mcp.client import MCPClient
from albra.observability.logger import get_logger


@dataclass
class JurisdictionServer:
    jurisdiction: str  # CO, AR, MX, ...
    name: str
    url: str
    description: str = ""
    active: bool = True
    transport: str = "http"
    metadata: dict[str, Any] = field(default_factory=dict)


# Catálogo por defecto - URLs VACÍAS porque ALBRA no inventa integraciones.
# Cuando exista un server MCP legal real para una jurisdicción, se agrega aquí.
DEFAULT_CATALOG: dict[str, JurisdictionServer] = {
    "CO": JurisdictionServer(
        jurisdiction="CO",
        name="albra-mcp-colombia",
        url="",  # pendiente de implementación
        description="MCP Server para fuentes jurídicas de Colombia (Constitución, Códigos, Jurisprudencia)",
    ),
    "AR": JurisdictionServer(
        jurisdiction="AR",
        name="albra-mcp-argentina",
        url="",
        description="MCP Server para fuentes jurídicas de Argentina",
    ),
    "MX": JurisdictionServer(
        jurisdiction="MX",
        name="albra-mcp-mexico",
        url="",
        description="MCP Server para fuentes jurídicas de México",
    ),
    "ES": JurisdictionServer(
        jurisdiction="ES",
        name="albra-mcp-espana",
        url="",
        description="MCP Server para fuentes jurídicas de España (BOE, CGPJ)",
    ),
    "BR": JurisdictionServer(
        jurisdiction="BR",
        name="albra-mcp-brasil",
        url="",
        description="MCP Server para fuentes jurídicas de Brasil",
    ),
}


class JurisdictionCatalog:
    """Catálogo de servers MCP por jurisdicción."""

    def __init__(self, *, mcp_client: MCPClient | None = None) -> None:
        self.log = get_logger("albra.mcp.catalog")
        self.mcp_client = mcp_client
        self._servers: dict[str, JurisdictionServer] = dict(DEFAULT_CATALOG)

    def get(self, jurisdiction: str) -> JurisdictionServer | None:
        return self._servers.get(jurisdiction.upper())

    def list(self) -> list[dict[str, Any]]:
        return [
            {
                "jurisdiction": s.jurisdiction,
                "name": s.name,
                "url": s.url or "(pendiente)",
                "active": s.active,
                "description": s.description,
            }
            for s in self._servers.values()
        ]

    def register(self, server: JurisdictionServer) -> None:
        self._servers[server.jurisdiction.upper()] = server
        if self.mcp_client and server.url:
            self.mcp_client.register_server(server.name, server.url, transport=server.transport)
        self.log.info(
            "catalog.registered",
            jurisdiction=server.jurisdiction,
            url=server.url or "(none)",
        )

    async def discover_tools(self, jurisdiction: str) -> dict[str, Any]:
        """Descubre tools disponibles en el server de una jurisdicción."""
        server = self.get(jurisdiction)
        if not server or not server.url:
            return {
                "ok": False,
                "error": f"No hay URL configurada para jurisdicción '{jurisdiction}'",
                "tools": [],
            }
        if not self.mcp_client:
            return {"ok": False, "error": "MCP Client no cableado", "tools": []}
        return await self.mcp_client.discover_tools(server.name)
