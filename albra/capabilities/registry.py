"""
Capability System ALBRA.

Cada capability define:
- nombre
- descripción
- permisos requeridos
- tools necesarias
- inputs / outputs
- riesgos
- dependencias
- estado (active | prepared | planned)
- auditoría
- si requiere aprobación humana
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger


@dataclass
class Capability:
    name: str
    description: str
    required_permissions: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    inputs: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    risks: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    state: str = "prepared"  # active | prepared | planned
    requires_human_approval: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "required_permissions": self.required_permissions,
            "required_tools": self.required_tools,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "risks": self.risks,
            "dependencies": self.dependencies,
            "state": self.state,
            "requires_human_approval": self.requires_human_approval,
        }


class CapabilityRegistry:
    def __init__(self, settings: Settings, *, tool_registry: Any = None) -> None:
        self.settings = settings
        self.tool_registry = tool_registry
        self.log = get_logger("albra.capabilities")
        self._caps: dict[str, Capability] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        defaults = [
            Capability(
                name="conversation",
                description="Conversación general con el usuario.",
                required_permissions=["chat"],
                inputs={"message": "str"},
                outputs={"reply": "str"},
                state="active",
                risks=["ninguno significativo"],
            ),
            Capability(
                name="tool_invocation",
                description="Invocación de herramientas registradas.",
                required_permissions=["tools.invoke"],
                required_tools=[],
                inputs={"tool": "str", "input": "dict"},
                outputs={"result": "ToolResult"},
                state="active",
                risks=["depender de la tool invocada"],
            ),
            Capability(
                name="document_reading",
                description="Lectura de documentos para extracción de información.",
                required_permissions=["files.read"],
                required_tools=[],
                inputs={"file": "path"},
                outputs={"text": "str", "metadata": "dict"},
                state="prepared",
                risks=["manipulación de contenido sensible"],
            ),
            Capability(
                name="document_generation",
                description="Generación de documentos legales (CUANDO EL CONOCIMIENTO JURÍDICO ESTÉ CARGADO).",
                required_permissions=["files.write", "documents.generate"],
                inputs={"template": "str", "data": "dict"},
                outputs={"file": "path"},
                state="prepared",
                requires_human_approval=True,
                risks=["documento legal sin revisión humana"],
            ),
            Capability(
                name="legal_research",
                description="Investigación jurídica con trazabilidad a fuentes oficiales.",
                required_permissions=["research.run"],
                inputs={"query": "str", "jurisdiction": "str"},
                outputs={"findings": "list", "evidence": "list"},
                state="prepared",
                risks=["información desactualizada, fuente no autorizada"],
            ),
            Capability(
                name="external_communication",
                description="Envío de comunicaciones a canales externos (WhatsApp/Telegram).",
                required_permissions=["comms.send"],
                required_tools=[],
                inputs={"channel": "str", "to": "str", "message": "str"},
                outputs={"status": "str"},
                state="prepared",
                requires_human_approval=True,
                risks=["comunicación oficial no autorizada"],
            ),
            Capability(
                name="health_diagnostic",
                description="Diagnóstico de salud del agente vía Doctor.",
                required_permissions=["doctor.run"],
                required_tools=[],
                inputs={"scope": "str"},
                outputs={"report": "dict"},
                state="active",
                risks=["ninguno significativo"],
            ),
            Capability(
                name="memory_search",
                description="Búsqueda en memoria memorydv.",
                required_permissions=["memory.read"],
                inputs={"query": "str", "top_k": "int"},
                outputs={"results": "list"},
                state="active",
            ),
            Capability(
                name="knowledge_load",
                description="Carga de conocimiento jurídico versionado (futura).",
                required_permissions=["knowledge.write"],
                inputs={"source": "path", "type": "str"},
                outputs={"items_loaded": "int"},
                state="prepared",
                requires_human_approval=True,
                risks=["conocimiento no verificado"],
            ),
        ]
        for cap in defaults:
            self._caps[cap.name] = cap
        self.log.info("capabilities.registered", count=len(self._caps))

    def register(self, cap: Capability) -> None:
        if cap.name in self._caps:
            raise ValueError(f"Capability '{cap.name}' ya existe")
        self._caps[cap.name] = cap
        self.log.info("capability.added", name=cap.name, state=cap.state)

    def get(self, name: str) -> Capability | None:
        return self._caps.get(name)

    def list(self) -> list[dict[str, Any]]:
        return [c.as_dict() for c in self._caps.values()]

    def list_active(self) -> list[dict[str, Any]]:
        return [c.as_dict() for c in self._caps.values() if c.state == "active"]

    def list_prepared(self) -> list[dict[str, Any]]:
        return [c.as_dict() for c in self._caps.values() if c.state == "prepared"]

    async def startup(self) -> None:
        self.log.info(
            "capabilities.startup",
            active=len([c for c in self._caps.values() if c.state == "active"]),
            prepared=len([c for c in self._caps.values() if c.state == "prepared"]),
        )

    async def shutdown(self) -> None:
        self.log.info("capabilities.shutdown")
