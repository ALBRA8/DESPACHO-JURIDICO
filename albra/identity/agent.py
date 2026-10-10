"""
AGENTE BASE ALBRA - V1.5 con paridad holding.

Integra los nuevos órganos del ADN maestro:
- ExecutionTrace (persistido en sqlite)
- AutonomyController (L0-L5)
- SelfImprove (lessons, capture, dedupe, reflexión, promoción, triage)
- PolicyEngineState (modes DRAFT/LIVE + events append-only)
- DataClassification (8 niveles)
- RBAC granular (<recurso>.<acción>)
- CircuitBreaker (provider/organ)
- LegalGate (5 verdicts)
- MemoryInterface (abstraction layer)
- ExecutionGuard (fail-closed TOTAL)
- SpecialistCatalog (placeholders para subagentes)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from albra.identity.manifest import AgentIdentity, AGENT_MANIFEST
from albra.config.settings import Settings
from albra.observability.logger import get_logger
from albra.observability.execution_trace import ExecutionTrace


@dataclass
class Agent:
    """El agente ALBRA V1.5 - con paridad completa con el holding."""

    identity: AgentIdentity = field(default_factory=lambda: AGENT_MANIFEST)
    settings: Settings = field(default_factory=Settings)
    _booted: bool = False
    _organs: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.log = get_logger("albra.agent")
        self.execution_trace = ExecutionTrace()

    async def boot(self) -> None:
        if self._booted:
            return
        self.log.info("albra.boot.start", agent=self.identity.codename, version="1.5.0")

        # Órganos V1.0 (ya existentes)
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

        # Órganos V1.5 (NUEVOS - paridad holding)
        from albra.observability.execution_trace import ExecutionTrace
        from albra.security.autonomy import AutonomyController
        from albra.doctor.self_improve import SelfImprove
        from albra.security.policy_state import PolicyEngineState
        from albra.security.classification import classify as _classify
        from albra.security.rbac import has_permission
        from albra.resilience.circuit_breaker import CircuitBreaker
        from albra.evidence.legal_gate import LegalGate
        from albra.memory.interface import MemoryInterface
        from albra.security.execution_guard import ExecutionGuard
        from albra.knowledge.specialists import list_specialists

        self._organs["runtime"] = Runtime(self.settings)
        self._organs["reasoning"] = ReasoningEngine(self.settings)
        self._organs["tools"] = ToolRegistry(self.settings)
        self._organs["capabilities"] = CapabilityRegistry(self.settings, tool_registry=self._organs["tools"])
        self._organs["mcp_server"] = MCPServer(self.settings)
        self._organs["mcp_server"].wire(
            tool_registry=self._organs["tools"],
            capability_registry=self._organs["capabilities"],
        )
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

        # V1.5 órganos nuevos
        self._organs["execution_trace"] = self.execution_trace
        self._organs["autonomy"] = AutonomyController()
        self._organs["self_improve"] = SelfImprove()
        self._organs["policy_state"] = PolicyEngineState()
        self._organs["circuit_breaker"] = CircuitBreaker()
        self._organs["legal_gate"] = LegalGate()
        self._organs["memory_interface"] = MemoryInterface(
            backend=self.settings.memory_backend,
            db_path=self.settings.memory_path,
            vector_dim=self.settings.memory_vector_dim,
        )
        self._organs["execution_guard"] = ExecutionGuard()
        self._organs["classify"] = _classify
        self._organs["has_permission"] = has_permission
        self._organs["specialists"] = list_specialists()

        # Wire comms adapter to call agent
        # Inicializar cada órgano que soporte async init
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

    async def process(self, message: str, *, channel: str = "text", user: str = "anon", user_role: str = "anon") -> dict[str, Any]:
        """Pipeline completo con execution_trace + autonomy + RBAC + LegalGate."""
        if not self._booted:
            await self.boot()

        # Start execution trace
        exec_id = self.execution_trace.start(
            agent_id=self.identity.codename,
            task=message,
            requester=user,
            inputs={"channel": channel, "user": user, "role": user_role},
        )

        audit = self._organs["audit"]
        events = self._organs["events"]
        security = self._organs["security"]
        reasoning = self._organs["reasoning"]
        memory = self._organs["memory"]
        tools = self._organs["tools"]
        autonomy = self._organs["autonomy"]
        policy = self._organs["policy_state"]
        classify_fn = self._organs["classify"]
        has_perm = self._organs["has_permission"]
        legal_gate = self._organs["legal_gate"]
        self_improve = self._organs["self_improve"]

        # 1. Intake
        intake_event = await events.emit("intake", {"channel": channel, "user": user, "message": message})
        await audit.record("intake", intake_event)

        # 2. Data classification
        classification = classify_fn(message)
        await audit.record("data.classification", classification.as_dict())

        # 3. Policy + Autonomy check
        policy_state = policy.get_state()
        if policy_state.kill_switch:
            self.execution_trace.finish(exec_id, status="aborted", errors=["kill_switch_active"])
            return {"reply": "Sistema en kill switch. Operación bloqueada.", "authorized": False, "execution_id": exec_id}

        # 4. RBAC
        if not has_perm(user_role, "tools.invoke_low"):
            self.execution_trace.finish(exec_id, status="aborted", errors=["rbac_deny"])
            return {"reply": "No autorizado.", "authorized": False, "execution_id": exec_id}

        # 5. Autonomy - chat básico = L0_OBSERVE
        auto_decision = autonomy.assert_allowed(
            requested_level="L0_OBSERVE",
            action="chat",
            external=False,
        )
        if not auto_decision.allowed:
            self.execution_trace.finish(exec_id, status="aborted", errors=[auto_decision.reason])
            return {"reply": "No autorizado por autonomía.", "authorized": False, "execution_id": exec_id}

        # 6. Reasoning: plan
        plan = await reasoning.plan(message, context={"user": user, "channel": channel})
        self.execution_trace.append_tool_call(
            exec_id, name="reasoning.plan", args={"message": message}, ok=True, result=plan.get("summary", "")
        )

        # 7. Memory retrieval
        retrieved = await memory.retrieve(message, top_k=5)
        plan["memory_hits"] = retrieved

        # 8. Tool invocation (with circuit breaker + execution guard)
        tool_results: list[dict[str, Any]] = []
        for step in plan.get("steps", []):
            if step.get("type") == "tool_call" and step.get("tool"):
                tool_name = step["tool"]
                tool_input = step.get("input", {})

                # Execution Guard check
                guard = self._organs["execution_guard"].check(
                    action="internal_research",  # default
                    user_role=user_role,
                    live_authorized=False,
                    policy_state=policy_state,
                    autonomy_controller=autonomy,
                    rbac_check_fn=has_perm,
                    legal_gate_verdict=legal_gate.evaluate(
                        "internal_research", text=message, actor_role=user_role
                    ),
                    data_classification=classification,
                    circuit_breaker=self._organs["circuit_breaker"],
                    provider_name=self.settings.default_provider,
                )
                if not guard.allowed:
                    await audit.record("guard.deny", guard.as_dict())
                    tool_results.append({"tool": tool_name, "result": {"ok": False, "error": guard.reason}})
                    continue

                try:
                    result = await tools.invoke(tool_name, tool_input, user=user)
                    tool_results.append({"tool": tool_name, "result": result})
                    self.execution_trace.append_tool_call(
                        exec_id, name=tool_name, args=tool_input, ok=result.get("ok", False),
                        result=result.get("value"), error=result.get("error"),
                    )
                    # Self-improve: capture errors
                    if not result.get("ok"):
                        self_improve.capture_error(
                            tool_name=tool_name,
                            error=result.get("error", "unknown"),
                        )
                        self._organs["circuit_breaker"].record_failure(self.settings.default_provider)
                    else:
                        self._organs["circuit_breaker"].record_success(self.settings.default_provider)
                except Exception as e:  # noqa: BLE001
                    self_improve.capture_error(tool_name=tool_name, error=e)
                    self._organs["circuit_breaker"].record_failure(self.settings.default_provider)
                    tool_results.append({"tool": tool_name, "result": {"ok": False, "error": str(e)}})

                await audit.record("tool.invoke", {"tool": tool_name, "input": tool_input, "result": result})

        # 9. Reasoning: respond
        response = await reasoning.respond(message, plan=plan, tool_results=tool_results)

        # 10. Legal Gate para respuesta (si parece afirmación legal)
        legal_verdict = legal_gate.evaluate(
            "internal_research" if not legal_gate.evaluate("publish_content", text=response["text"], actor_role=user_role).verdict == "BLOCKED" else "publish_content",
            text=response["text"],
            actor_role=user_role,
        )
        if legal_verdict.verdict == "BLOCKED":
            response["text"] = "Respuesta bloqueada por Legal Gate: " + legal_verdict.reason

        # 11. Memory write
        await memory.write(
            text=f"H: {message}\nA: {response['text']}",
            category="conversational",
            metadata={"user": user, "channel": channel, "execution_id": exec_id},
        )

        # 12. Audit + Finish trace
        await audit.record("outtake", {"response": response, "user": user, "channel": channel})
        self.execution_trace.finish(
            exec_id,
            status="completed",
            outputs={"reply": response["text"]},
            decisions=[{"intent": plan.get("intent", {}).get("name")}],
        )

        return {
            "reply": response["text"],
            "authorized": True,
            "execution_id": exec_id,
            "plan": plan.get("summary", ""),
            "tools_used": [r["tool"] for r in tool_results],
            "memory_used": len(retrieved),
            "classification": classification.classification.name,
            "legal_verdict": legal_verdict.verdict,
        }

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
