"""
AGENTE BASE ALBRA

El organismo completo: orquesta identidad, runtime, reasoning, tools,
memoria, MCP, doctor, comms, multimodalidad, investigación, evidencia,
seguridad, eventos, workflows, providers, observabilidad y auditoría.

NO incluye subagentes jurídicos especializados (se agregan después).
NO incluye conocimiento jurídico cargado (se enseña después).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from albra.identity.manifest import AgentIdentity, AGENT_MANIFEST
from albra.config.settings import Settings
from albra.observability.logger import get_logger


@dataclass
class Agent:
    """
    El agente ALBRA.

    Compone todos los órganos del ADN. Inicializa cada subsistema de forma
    perezosa para que el agente "nazca" sin requerir credenciales externas.

    Uso:
        agent = Agent()
        await agent.boot()
        result = await agent.process(message)
    """

    identity: AgentIdentity = field(default_factory=lambda: AGENT_MANIFEST)
    settings: Settings = field(default_factory=Settings)
    _booted: bool = False
    _organs: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.log = get_logger("albra.agent")

    async def boot(self) -> None:
        """Despierta todos los órganos del organismo."""
        if self._booted:
            return
        self.log.info("albra.boot.start", agent=self.identity.codename, version=self.identity.version)

        # Inicialización perezosa de órganos
        from albra.runtime.engine import Runtime
        from albra.reasoning.engine import ReasoningEngine
        from albra.tools.registry import ToolRegistry
        from albra.capabilities.registry import CapabilityRegistry
        from albra.mcp.server import MCPServer
        from albra.memory.store import MemoryDV
        from albra.doctor.diagnostic import Doctor
        from albra.events.bus import EventBus
        from albra.workflows.engine import WorkflowEngine
        from albra.providers.registry import ProviderRegistry
        from albra.security.auth import SecurityGate
        from albra.audit.log import AuditLog
        from albra.research.engine import ResearchEngine
        from albra.evidence.chain import EvidenceChain
        from albra.files.tracker import FileTracker
        from albra.comms.router import CommRouter
        from albra.resilience.recovery import RecoveryManager

        self._organs["runtime"] = Runtime(self.settings)
        self._organs["reasoning"] = ReasoningEngine(self.settings)
        self._organs["tools"] = ToolRegistry(self.settings)
        self._organs["capabilities"] = CapabilityRegistry(self.settings, tool_registry=self._organs["tools"])
        self._organs["mcp_server"] = MCPServer(self.settings)
        self._organs["memory"] = MemoryDV(self.settings)
        self._organs["doctor"] = Doctor(self.settings, organs=self._organs)
        self._organs["events"] = EventBus(self.settings)
        self._organs["workflows"] = WorkflowEngine(self.settings, event_bus=self._organs["events"])
        self._organs["providers"] = ProviderRegistry(self.settings)
        self._organs["security"] = SecurityGate(self.settings)
        self._organs["audit"] = AuditLog(self.settings)
        self._organs["research"] = ResearchEngine(self.settings)
        self._organs["evidence"] = EvidenceChain(self.settings)
        self._organs["files"] = FileTracker(self.settings)
        self._organs["comms"] = CommRouter(self.settings)
        self._organs["resilience"] = RecoveryManager(self.settings)

        # Inicializar cada órgano que soporte async init
        for name, organ in self._organs.items():
            if hasattr(organ, "startup"):
                try:
                    await organ.startup()  # type: ignore[attr-defined]
                except Exception as e:  # noqa: BLE001
                    self.log.warning("albra.boot.organ_failed", organ=name, error=str(e))

        self._booted = True
        self.log.info("albra.boot.done", organs=list(self._organs.keys()))

    @property
    def organs(self) -> dict[str, Any]:
        return self._organs

    def organ(self, name: str) -> Any:
        if name not in self._organs:
            raise KeyError(f"Órgano '{name}' no inicializado")
        return self._organs[name]

    async def process(self, message: str, *, channel: str = "text", user: str = "anon") -> dict[str, Any]:
        """
        Procesa un mensaje entrante a través del organismo completo.

        Pipeline:
        intake → security.check → reasoning.plan → tools.invoke (if needed)
        → memory.retrieve → reasoning.respond → audit.record → outtake
        """
        if not self._booted:
            await self.boot()

        audit = self._organs["audit"]
        events = self._organs["events"]
        security = self._organs["security"]
        reasoning = self._organs["reasoning"]
        memory = self._organs["memory"]
        tools = self._organs["tools"]

        # 1. Intake
        intake_event = await events.emit("intake", {"channel": channel, "user": user, "message": message})
        await audit.record("intake", intake_event)

        # 2. Security gate (rate-limit, blacklist, etc.)
        authz = await security.authorize(user, action="chat", resource="agent")
        if not authz.metadata.get("allowed", False):
            await audit.record("authz.deny", {"user": user, "reason": authz.metadata.get("reason", "unknown")})
            return {"reply": "No autorizado para usar este agente.", "authorized": False}

        # 3. Reasoning: plan
        plan = await reasoning.plan(message, context={"user": user, "channel": channel})

        # 4. Memory retrieval
        retrieved = await memory.retrieve(message, top_k=5)
        plan["memory_hits"] = retrieved

        # 5. Tool invocation (if reasoning decides)
        tool_results: list[dict[str, Any]] = []
        for step in plan.get("steps", []):
            if step.get("type") == "tool_call" and step.get("tool"):
                tool_name = step["tool"]
                tool_input = step.get("input", {})
                result = await tools.invoke(tool_name, tool_input, user=user)
                tool_results.append({"tool": tool_name, "result": result})
                await audit.record("tool.invoke", {"tool": tool_name, "input": tool_input, "result": result})

        # 6. Reasoning: produce response
        response = await reasoning.respond(message, plan=plan, tool_results=tool_results)

        # 7. Memory write
        await memory.write(
            text=f"H: {message}\nA: {response['text']}",
            category="conversational",
            metadata={"user": user, "channel": channel},
        )

        # 8. Audit + Outtake
        await audit.record("outtake", {"response": response, "user": user, "channel": channel})

        return {
            "reply": response["text"],
            "authorized": True,
            "plan": plan.get("summary", ""),
            "tools_used": [r["tool"] for r in tool_results],
            "memory_used": len(retrieved),
        }

    async def shutdown(self) -> None:
        for name, organ in self._organs.items():
            if hasattr(organ, "shutdown"):
                try:
                    await organ.shutdown()  # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001
                    pass
        self._booted = False
        self.log.info("albra.shutdown.done")


def get_agent() -> Agent:
    """Factory simple - devuelve una instancia nueva (sin boot)."""
    return Agent()
