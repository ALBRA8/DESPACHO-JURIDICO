"""
AGENTE BASE ALBRA - V1.6 INTEGRATION COMPLETE.

Pipeline soberano delega al Runtime.
Memoria unificada vía MemoryInterface (no MemoryDV directo).
Reasoning usa ProviderRouter real (con fallback).
ExecutionGuard fail-closed TOTAL integrado en cada tool_call.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from albra.config.settings import Settings
from albra.identity.manifest import AGENT_MANIFEST, AgentIdentity
from albra.observability.execution_trace import ExecutionTrace
from albra.observability.logger import get_logger


@dataclass
class Agent:
    """El agente ALBRA V1.6 — Integration Complete."""

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
        # Memoria权威 = MemoryInterface. No usamos MemoryDV directo en pipeline.
        memory_interface = MemoryInterface(
            backend=self.settings.memory_backend,
            db_path=self.settings.memory_path,
            vector_dim=self.settings.memory_vector_dim,
        )

        # --- Providers + Router (P0.1) ---
        provider_registry = ProviderRegistry(self.settings)
        provider_router = ProviderRouter(self.settings, providers={})
        # sincronizar providers registrados
        for name in provider_registry.list():
            provider_router.providers[name] = provider_registry.get(name)

        # --- Reasoning wired con ProviderRouter ---
        reasoning = ReasoningEngine(self.settings)
        reasoning.wire(provider_router=provider_router, provider_registry=provider_registry)

        # --- ToolRegistry ---
        tool_registry = ToolRegistry(self.settings)

        # --- Órganos ---
        self._organs["runtime"] = Runtime(self.settings)
        self._organs["reasoning"] = reasoning
        self._organs["tools"] = tool_registry
        self._organs["capabilities"] = CapabilityRegistry(self.settings, tool_registry=tool_registry)
        self._organs["mcp_server"] = MCPServer(self.settings)
        self._organs["memory"] = memory_interface  # P0.5: solo MemoryInterface
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

        # V1.5 órganos
        self._organs["execution_trace"] = self.execution_trace
        self._organs["autonomy"] = AutonomyController()
        self._organs["self_improve"] = SelfImprove()
        self._organs["policy_state"] = PolicyEngineState()
        self._organs["circuit_breaker"] = CircuitBreaker()
        self._organs["legal_gate"] = LegalGate()
        self._organs["execution_guard"] = ExecutionGuard()
        self._organs["classify"] = _classify
        self._organs["has_permission"] = has_permission
        self._organs["specialists"] = list_specialists()

        # Wire MCP server con tool_registry, capability_registry, execution_guard, audit (P1)
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

        # Init async de cada órgano
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
        """Pipeline completo fail-closed con ExecutionGuard en cada tool_call.

        Arquitectura:
        INPUT → CLASSIFICATION → POLICY → MEMORY CONTEXT →
        REASONING (con provider) → TOOL CALLS (vía guard) →
        LEGAL GATE → MEMORY WRITE → AUDIT → TRACE → OUTPUT
        """
        if not self._booted:
            await self.boot()

        # 0. Start execution trace
        exec_id = self.execution_trace.start(
            agent_id=self.identity.codename,
            task=message,
            requester=user,
            inputs={"channel": channel, "user": user, "role": user_role},
        )

        audit = self._organs["audit"]
        events = self._organs["events"]
        reasoning = self._organs["reasoning"]
        memory = self._organs["memory"]  # MemoryInterface (P0.5)
        tools = self._organs["tools"]
        autonomy = self._organs["autonomy"]
        policy = self._organs["policy_state"]
        classify_fn = self._organs["classify"]
        has_perm = self._organs["has_permission"]
        legal_gate = self._organs["legal_gate"]
        self_improve = self._organs["self_improve"]
        circuit_breaker = self._organs["circuit_breaker"]
        execution_guard = self._organs["execution_guard"]

        # 1. Intake
        intake_event = await events.emit("intake", {
            "channel": channel, "user": user, "message": message,
            "execution_id": exec_id,
        })
        await audit.record("intake", intake_event.as_dict())

        # 2. CLASSIFICATION
        classification = classify_fn(message)
        await audit.record("data.classification", classification.as_dict())

        # 3. POLICY + kill switch
        policy_state = policy.get_state()
        if policy_state.kill_switch:
            self.execution_trace.finish(
                exec_id, status="aborted",
                errors=[f"kill_switch: {policy_state.kill_reason}"],
            )
            await audit.record("process.aborted", {"reason": "kill_switch"})
            return {
                "reply": "Sistema en kill switch. Operación bloqueada.",
                "authorized": False, "execution_id": exec_id,
                "classification": classification.classification.name,
            }

        # 4. RBAC + Autonomía para chat (L0_OBSERVE)
        if not has_perm(user_role, "tools.invoke_low"):
            self.execution_trace.finish(
                exec_id, status="aborted", errors=["rbac_deny"],
            )
            await audit.record("process.aborted", {"reason": "rbac_deny", "role": user_role})
            return {
                "reply": "No autorizado.", "authorized": False,
                "execution_id": exec_id,
                "classification": classification.classification.name,
            }

        auto_decision = autonomy.assert_allowed(
            requested_level="L0_OBSERVE", action="chat", external=False,
        )
        if not auto_decision.allowed:
            self.execution_trace.finish(
                exec_id, status="aborted", errors=[auto_decision.reason],
            )
            await audit.record("process.aborted", {"reason": "autonomy", "decision": auto_decision.as_dict()})
            return {
                "reply": "No autorizado por autonomía.", "authorized": False,
                "execution_id": exec_id,
                "classification": classification.classification.name,
            }

        # 5. REASONING: plan (sin provider todavía)
        plan = await reasoning.plan(message, context={
            "user": user, "channel": channel, "execution_id": exec_id,
        })
        self.execution_trace.append_tool_call(
            exec_id, name="reasoning.plan", args={"message": message},
            ok=True, result=plan.get("summary", ""),
        )

        # 6. MEMORY CONTEXT (vía MemoryInterface)
        retrieved = await memory.retrieve(message, top_k=5)
        plan["memory_hits"] = retrieved

        # 7. TOOL CALLS (cada uno vía ExecutionGuard fail-closed)
        tool_results: list[dict[str, Any]] = []
        for step in plan.get("steps", []):
            if step.get("type") != "tool_call" or not step.get("tool"):
                continue

            tool_name = step["tool"]
            tool_input = step.get("input", {})

            # Map tool_name → action for LegalGate (P1 semántico)
            tool_to_action = {
                "clock": "internal_research",
                "calculator": "internal_research",
                "echo": "internal_research",
                "memory_lookup": "memory.read",
                "contract_analyzer": "internal_research",
            }
            action_for_guard = tool_to_action.get(tool_name, "tool_invocation")

            # Evaluate LegalGate for this action
            legal_verdict = legal_gate.evaluate(
                action_for_guard,
                text=str(tool_input) + " " + message,
                actor_role=user_role,
                live_authorized=False,
            )

            # ExecutionGuard check - FAIL-CLOSED
            guard = execution_guard.check(
                action=action_for_guard,
                user_role=user_role,
                policy_state=policy_state,
                autonomy_controller=autonomy,
                rbac_check_fn=has_perm,
                legal_gate_verdict=legal_verdict,
                live_authorized=False,
                hitl_approved=False,
                data_classification=classification,
                circuit_breaker=circuit_breaker,
                provider_name=self.settings.default_provider,
                dedup_key=f"{exec_id}:{tool_name}",
            )

            if not guard.allowed:
                # P0.4: NO acceder a result que no existe
                fail_result = {
                    "ok": False, "error": f"Guard: {guard.reason}",
                    "guard_verdict": guard.as_dict(),
                }
                tool_results.append({"tool": tool_name, "result": fail_result})
                await audit.record("guard.deny", guard.as_dict())
                self.execution_trace.append_tool_call(
                    exec_id, name=tool_name, args=tool_input,
                    ok=False, error=guard.reason,
                )
                continue

            # Tool invocation - P0.4: capturar resultado SIEMPRE
            result: dict[str, Any]
            try:
                result = await tools.invoke(tool_name, tool_input, user=user)
            except asyncio.TimeoutError as e:
                result = {"ok": False, "error": f"timeout: {e}", "status": "TIMEOUT"}
                self_improve.capture_error(tool_name=tool_name, error=e)
                circuit_breaker.record_failure(self.settings.default_provider)
            except Exception as e:  # noqa: BLE001
                result = {"ok": False, "error": str(e), "status": "FAILURE"}
                self_improve.capture_error(tool_name=tool_name, error=e)
                circuit_breaker.record_failure(self.settings.default_provider)
            else:
                if result.get("ok"):
                    circuit_breaker.record_success(self.settings.default_provider)
                else:
                    self_improve.capture_error(
                        tool_name=tool_name,
                        error=result.get("error", "unknown"),
                    )
                    circuit_breaker.record_failure(self.settings.default_provider)

            tool_results.append({"tool": tool_name, "result": result})
            self.execution_trace.append_tool_call(
                exec_id, name=tool_name, args=tool_input,
                ok=result.get("ok", False),
                result=result.get("value"),
                error=result.get("error"),
            )
            await audit.record("tool.invoke", {
                "tool": tool_name, "input": tool_input,
                "ok": result.get("ok", False),
                "error": result.get("error"),
            })

        # 8. REASONING: respond (con provider via ProviderRouter - P0.1)
        response = await reasoning.respond(
            message, plan=plan, tool_results=tool_results,
            classification=classification,
        )
        self.execution_trace.append_provider(
            exec_id, provider=response.get("provider", "unknown"),
            prompt_size=len(message), response_size=len(response.get("text", "")),
        )

        # 9. LEGAL GATE final sobre la respuesta
        final_verdict = legal_gate.evaluate(
            "internal_research",
            text=response["text"], actor_role=user_role,
        )
        if final_verdict.verdict == "BLOCKED":
            response["text"] = (
                "Respuesta bloqueada por Legal Gate: "
                + final_verdict.reason
            )

        # 10. MEMORY WRITE (vía MemoryInterface)
        await memory.write(
            text=f"H: {message}\nA: {response['text']}",
            category="conversational",
            truth_level="OBSERVED",  # conversación observada
            provenance="USER_INPUT",
            metadata={
                "user": user, "channel": channel,
                "execution_id": exec_id,
            },
        )

        # 11. AUDIT + FINISH TRACE
        await audit.record("outtake", {
            "response": response["text"][:200],
            "user": user, "channel": channel,
            "execution_id": exec_id,
        })
        self.execution_trace.finish(
            exec_id, status="completed",
            outputs={"reply": response["text"]},
            decisions=[{
                "intent": plan.get("intent", {}).get("name"),
                "provider": response.get("provider"),
                "legal_verdict": final_verdict.verdict,
            }],
        )

        return {
            "reply": response["text"],
            "authorized": True,
            "execution_id": exec_id,
            "plan": plan.get("summary", ""),
            "tools_used": [r["tool"] for r in tool_results],
            "memory_used": len(retrieved),
            "classification": classification.classification.name,
            "legal_verdict": final_verdict.verdict,
            "provider_used": response.get("provider"),
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
