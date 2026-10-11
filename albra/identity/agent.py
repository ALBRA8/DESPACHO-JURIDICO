"""
AGENTE BASE ALBRA - V1.6 FINAL.

Runtime SOBERANO. Agent.process() es solo una FACHADA que delega a Runtime.execute().
NO existe una segunda pipeline.

El Agente:
- bootea los órganos
- los conecta al Runtime
- expone process() como fachada pública
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from albra.audit.tamper_evident import TamperEvidentAudit
from albra.config.settings import Settings
from albra.identity.manifest import AGENT_MANIFEST, AgentIdentity
from albra.observability.execution_trace import ExecutionTrace
from albra.observability.logger import get_logger


@dataclass
class Agent:
    """El agente ALBRA V1.6 FINAL — fachada sobre Runtime soberano."""

    identity: AgentIdentity = field(default_factory=lambda: AGENT_MANIFEST)
    settings: Settings = field(default_factory=Settings)
    _booted: bool = False
    _organs: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.log = get_logger("albra.agent")
        self.execution_trace = ExecutionTrace()
        # Tamper-evident audit - ópt-in para eventos críticos
        self.tamper_audit = TamperEvidentAudit(self.settings.audit_path + ".chain")

    async def boot(self) -> None:
        if self._booted:
            return
        self.log.info("albra.boot.start", agent=self.identity.codename, version="1.6.0")

        # Imports diferidos para evitar circular
        from albra.audit.log import AuditLog
        from albra.capabilities.registry import CapabilityRegistry
        from albra.comms.router import CommRouter
        from albra.doctor.diagnostic import Doctor
        from albra.doctor.self_improve import SelfImprove
        from albra.events.bus import EventBus
        from albra.evidence.chain import EvidenceChain
        from albra.evidence.legal_gate import LegalGate
        from albra.files.tracker import FileTracker
        from albra.knowledge.specialists import list_specialists
        from albra.mcp.server import MCPServer
        from albra.memory.interface import MemoryInterface
        from albra.providers.registry import ProviderRegistry
        from albra.providers.router import ProviderRouter
        from albra.reasoning.engine import ReasoningEngine
        from albra.research.engine import ResearchEngine
        from albra.resilience.circuit_breaker import CircuitBreaker
        from albra.resilience.recovery import RecoveryManager
        from albra.runtime.engine import Runtime
        from albra.security.auth import SecurityGate
        from albra.security.autonomy import AutonomyController
        from albra.security.classification import classify as _classify
        from albra.security.execution_guard import ExecutionGuard
        from albra.security.policy_state import PolicyEngineState
        from albra.security.rbac import has_permission
        from albra.tools.registry import ToolRegistry
        from albra.workflows.engine import WorkflowEngine

        # --- Memoria unificada (P0.5) ---
        memory_interface = MemoryInterface(
            backend=self.settings.memory_backend,
            db_path=self.settings.memory_path,
            vector_dim=self.settings.memory_vector_dim,
        )

        # --- Providers + Router ---
        provider_registry = ProviderRegistry(self.settings)
        provider_router = ProviderRouter(self.settings, providers={})
        for name in provider_registry.list():
            provider_router.providers[name] = provider_registry.get(name)

        # --- Reasoning wired con ProviderRouter ---
        reasoning = ReasoningEngine(self.settings)
        reasoning.wire(provider_router=provider_router, provider_registry=provider_registry)

        tool_registry = ToolRegistry(self.settings)

        # --- Órganos ---
        runtime = Runtime(self.settings)
        self._organs["runtime"] = runtime
        self._organs["reasoning"] = reasoning
        self._organs["tools"] = tool_registry
        self._organs["capabilities"] = CapabilityRegistry(self.settings, tool_registry=tool_registry)
        self._organs["mcp_server"] = MCPServer(self.settings)
        self._organs["memory"] = memory_interface
        self._organs["memory_interface"] = memory_interface
        self._organs["doctor"] = Doctor(self.settings, organs=self._organs)
        self._organs["events"] = EventBus(self.settings)
        self._organs["workflows"] = WorkflowEngine(self.settings, event_bus=self._organs["events"])
        self._organs["providers"] = provider_registry
        self._organs["provider_router"] = provider_router
        self._organs["security"] = SecurityGate(self.settings)
        self._organs["audit"] = AuditLog(self.settings)
        self._organs["research"] = ResearchEngine(self.settings)
        self._organs["evidence"] = EvidenceChain(self.settings)
        self._organs["files"] = FileTracker(self.settings)
        self._organs["comms"] = CommRouter(self.settings)
        self._organs["resilience"] = RecoveryManager(self.settings)

        # V1.5+ órganos
        self._organs["execution_trace"] = self.execution_trace
        self._organs["autonomy"] = AutonomyController()
        self._organs["self_improve"] = SelfImprove()
        self._organs["policy_state"] = PolicyEngineState()
        self._organs["circuit_breaker"] = CircuitBreaker()
        self._organs["legal_gate"] = LegalGate()
        self._organs["execution_guard"] = ExecutionGuard()
        self._organs["tamper_audit"] = self.tamper_audit
        self._organs["classify"] = _classify
        self._organs["has_permission"] = has_permission
        self._organs["specialists"] = list_specialists()

        # Wire Runtime con TODOS los órganos (single source of truth)
        runtime.wire(self._organs)

        # Wire MCP server con security perimeter
        self._organs["mcp_server"].wire(
            tool_registry=tool_registry,
            capability_registry=self._organs["capabilities"],
            execution_guard=self._organs["execution_guard"],
            audit=self._organs["audit"],
            policy_state=self._organs["policy_state"],
            autonomy_controller=self._organs["autonomy"],
            rbac_check_fn=has_permission,
            legal_gate=self._organs["legal_gate"],
        )

        # Wire research con evidence
        self._organs["research"].wire(evidence_chain=self._organs["evidence"])

        # Init async
        for name, organ in self._organs.items():
            if hasattr(organ, "startup") and not isinstance(organ, type):
                try:
                    await organ.startup()  # type: ignore[attr-defined]
                except Exception as e:  # noqa: BLE001
                    self.log.warning("albra.boot.organ_failed", organ=name, error=str(e))

        self._booted = True
        self.log.info("albra.boot.done", organs=list(self._organs.keys()), count=len(self._organs))

    @property
    def organs(self) -> dict[str, Any]:
        return self._organs

    def organ(self, name: str) -> Any:
        if name not in self._organs:
            raise KeyError(f"Órgano '{name}' no inicializado")
        return self._organs[name]

    async def process(
        self,
        message: str,
        *,
        channel: str = "text",
        user: str = "anon",
        user_role: str = "anon",
    ) -> dict[str, Any]:
        """FACHADA pública. Delega a Runtime.execute() - NO es pipeline paralela."""
        if not self._booted:
            await self.boot()
        # Single source of truth: Runtime.execute()
        runtime: Any = self._organs["runtime"]
        return await runtime.execute(
            message, channel=channel, user=user, user_role=user_role,
        )

    async def shutdown(self) -> None:
        for name, organ in self._organs.items():
            if hasattr(organ, "shutdown") and not isinstance(organ, type):
                try:
                    await organ.shutdown()  # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001
                    pass
        self.execution_trace.close()
        self._booted = False
        self.log.info("albra.shutdown.done")


def get_agent() -> Agent:
    return Agent()
