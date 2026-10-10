"""
Plugin System ALBRA.

Permite extender el agente sin tocar el core. Cada plugin:
- Tiene manifest (nombre, versión, dependencias, permisos)
- Puede registrar tools, capabilities, providers, organs
- Es aislado (no puede modificar código del core)
- Es auditable

Casos de uso:
- Plugin "colombia_civil_code" → carga código civil como conocimiento
- Plugin "whatsapp_business" → integra WhatsApp Business API
- Plugin "contract_redlining" → análisis de cláusulas con CUAD
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from albra.capabilities.registry import Capability
from albra.observability.logger import get_logger
from albra.tools.base import Tool, ToolResult


@dataclass
class PluginManifest:
    name: str
    version: str
    description: str
    author: str = "ALBRA"
    requires: list[str] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    entry_point: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "requires": self.requires,
            "provides": self.provides,
            "permissions": self.permissions,
            "entry_point": self.entry_point,
        }


@dataclass
class PluginInstance:
    manifest: PluginManifest
    register: Callable[[PluginContext], Awaitable[dict[str, Any]]]
    unregister: Callable[[PluginContext], Awaitable[dict[str, Any]]] | None = None
    state: dict[str, Any] = field(default_factory=dict)


class PluginContext:
    def __init__(self, *, agent: Any = None) -> None:
        self._agent = agent
        self._registered_tools: list[str] = []
        self._registered_caps: list[str] = []
        self._registered_providers: list[str] = []

    def register_tool(self, tool: Tool) -> str:
        if self._agent:
            tr = self._agent.organs.get("tools")
            if tr:
                tr.register(tool)
                self._registered_tools.append(tool.name)
                return tool.name
        return ""

    def register_capability(self, cap: Capability) -> str:
        if self._agent:
            cr = self._agent.organs.get("capabilities")
            if cr:
                cr.register(cap)
                self._registered_caps.append(cap.name)
                return cap.name
        return ""

    def register_provider(self, name: str, provider: Any) -> str:
        if self._agent:
            pr = self._agent.organs.get("providers")
            if pr:
                pr.register(name, provider)
                self._registered_providers.append(name)
                return name
        return ""

    def get_organ(self, name: str) -> Any:
        if self._agent:
            return self._agent.organs.get(name)
        return None

    def cleanup_targets(self) -> dict[str, list[str]]:
        return {
            "tools": list(self._registered_tools),
            "capabilities": list(self._registered_caps),
            "providers": list(self._registered_providers),
        }


class PluginManager:
    def __init__(self) -> None:
        self.log = get_logger("albra.plugins")
        self._plugins: dict[str, PluginInstance] = {}
        self._contexts: dict[str, PluginContext] = {}

    async def register(self, plugin: PluginInstance, *, agent: Any = None) -> dict[str, Any]:
        """Versión async - usar desde un loop async."""
        if plugin.manifest.name in self._plugins:
            raise ValueError(f"Plugin '{plugin.manifest.name}' ya está registrado")
        for req in plugin.manifest.requires:
            if req not in self._plugins:
                raise ValueError(f"Plugin requiere '{req}' que no está cargado")
        ctx = PluginContext(agent=agent)
        self._contexts[plugin.manifest.name] = ctx
        result = await plugin.register(ctx)
        self._plugins[plugin.manifest.name] = plugin
        self.log.info(
            "plugin.registered",
            name=plugin.manifest.name,
            version=plugin.manifest.version,
            tools=ctx._registered_tools,
            capabilities=ctx._registered_caps,
        )
        return result

    def register_sync(self, plugin: PluginInstance, *, agent: Any = None) -> dict[str, Any]:
        """Versión sync - crea un loop nuevo."""
        return asyncio.run(self.register(plugin, agent=agent))

    async def unregister(self, name: str) -> dict[str, Any]:
        if name not in self._plugins:
            return {"ok": False, "error": f"Plugin '{name}' no encontrado"}
        plugin = self._plugins[name]
        ctx = self._contexts.get(name)
        if plugin.unregister and ctx:
            await plugin.unregister(ctx)
        del self._plugins[name]
        if name in self._contexts:
            del self._contexts[name]
        self.log.info("plugin.unregistered", name=name)
        return {"ok": True, "unregistered": name}

    def list(self) -> list[dict[str, Any]]:
        return [p.manifest.as_dict() for p in self._plugins.values()]

    def get(self, name: str) -> PluginInstance | None:
        return self._plugins.get(name)


# --- Patrones de cláusulas de riesgo (CUAD-based, simplificado) ---

RISK_PATTERNS: dict[str, list[str]] = {
    "indemnidad_amplia": [
        "indemnizará por cualquier",
        "hold harmless",
        "indemnidad amplia",
    ],
    "no_responsabilidad": [
        "no será responsable",
        "no asume responsabilidad",
        "exonera de responsabilidad",
    ],
    "terminacion_unilateral": [
        "podrá dar por terminado",
        "resolución unilateral",
        "a su sola discreción",
    ],
    "confidencialidad_perpetua": [
        "perpetuamente confidencial",
        "nunca podrá divulgar",
    ],
    "renuncia_derechos": [
        "renuncia expresamente",
        "renuncia a cualquier acción",
        "renuncia al derecho de",
    ],
    "arbitraje_uneven": [
        "arbitraje en",
        "sede única",
        "tribunal designado por",
    ],
}


def _detect_risk_clauses(text: str) -> list[dict[str, Any]]:
    text_l = text.lower()
    risks: list[dict[str, Any]] = []
    for kind, patterns in RISK_PATTERNS.items():
        for p in patterns:
            if p in text_l:
                idx = text_l.find(p)
                start = max(0, idx - 50)
                end = min(len(text), idx + 200)
                snippet = text[start:end].replace("\n", " ").strip()
                risks.append({
                    "kind": kind,
                    "pattern": p,
                    "snippet": snippet,
                    "severity": "high" if kind in ("renuncia_derechos", "no_responsabilidad") else "medium",
                })
                break
    return risks


async def _register_redline(ctx: PluginContext) -> dict[str, Any]:
    async def _analyze_contract(input_data, *, user):
        text = input_data.get("text", "")
        if not text:
            return ToolResult(ok=False, error="Falta parámetro 'text'")
        risks = _detect_risk_clauses(text)
        return ToolResult(
            ok=True,
            value={"risks": risks, "count": len(risks)},
            metadata={"user": user, "analyzer": "cuad_rules_v0.1"},
        )

    tool = Tool(
        name="contract_analyzer",
        description="Analiza un contrato y detecta cláusulas de riesgo (CUAD-based).",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        handler=_analyze_contract,
        risk="medium",
        required_permission="tools.invoke",
        category="legal",
    )
    ctx.register_tool(tool)
    return {"registered_tool": tool.name}


CONTRACT_REDLINE_PLUGIN = PluginInstance(
    manifest=PluginManifest(
        name="contract_redlining",
        version="0.1.0",
        description="Detección de cláusulas de riesgo en contratos (basado en CUAD dataset)",
        author="ALBRA",
        provides=["contract_analysis"],
        permissions=["files.read", "files.write"],
    ),
    register=_register_redline,
)
