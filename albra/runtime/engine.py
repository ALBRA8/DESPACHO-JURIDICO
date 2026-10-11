"""
RUNTIME SOBERANO - V1.6 FINAL.

UNA SOLA autoridad de ejecución. NO existe una segunda pipeline en Agent.process.
Agent.process() es solo una fachada que delega a Runtime.execute().

Pipeline ( Runtime ejecuta TODO):
USER REQUEST
   ↓
Identity (caller role)
   ↓
Classification
   ↓
Policy (kill_switch check)
   ↓
RBAC (basic tools.invoke_low)
   ↓
Autonomy (L0 for chat)
   ↓
Memory context (retrieve)
   ↓
Reasoning.plan (intent + steps)
   ↓
For each step: ExecutionGuard fail-closed → tools.invoke
   ↓
Reasoning.respond (vía ProviderRouter)
   ↓
LegalGate final
   ↓
Memory write (truth_level=OBSERVED)
   ↓
Audit + ExecutionTrace + (TamperEvidence cuando aplica)
   ↓
Response

Si policy cambia, SOLO se cambia aquí.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger
from albra.observability.metrics import get_metrics
from albra.runtime.context import RunContext


class Runtime:
    """Runtime soberano. Única autoridad de ejecución."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.runtime")
        self.metrics = get_metrics()
        self._started = False
        # Órganos - wired por Agent.boot()
        self.organs: dict[str, Any] = {}

    def wire(self, organs: dict[str, Any]) -> None:
        """Recibe referencia a los órganos del agente (sin duplicar instancias)."""
        self.organs = organs

    async def startup(self) -> None:
        self._started = True
        self.log.info("runtime.startup")

    async def shutdown(self) -> None:
        self._started = False
        self.log.info("runtime.shutdown")

    async def execute(
        self,
        message: str,
        *,
        channel: str = "text",
        user: str = "anon",
        user_role: str = "anon",
    ) -> dict[str, Any]:
        """UNA SOLA pipeline. Agent.process() delega aquí."""
        if not self.organs:
            raise RuntimeError("Runtime no wired - llama Agent.boot() primero")

        # Órganos
        audit = self.organs["audit"]
        events = self.organs["events"]
        reasoning = self.organs["reasoning"]
        memory = self.organs["memory"]
        tools = self.organs["tools"]
        autonomy = self.organs["autonomy"]
        policy = self.organs["policy_state"]
        classify_fn = self.organs["classify"]
        has_perm = self.organs["has_permission"]
        legal_gate = self.organs["legal_gate"]
        self_improve = self.organs["self_improve"]
        circuit_breaker = self.organs["circuit_breaker"]
        execution_guard = self.organs["execution_guard"]
        execution_trace = self.organs["execution_trace"]
        tamper_audit = self.organs.get("tamper_audit")

        # RunContext
        ctx = RunContext(
            user=user,
            channel=channel,
            max_iterations=self.settings.runtime_loop_max_iter,
        )

        # 0. Start execution trace
        exec_id = execution_trace.start(
            agent_id="ALBRA-BASE-V1",
            task=message,
            requester=user,
            inputs={"channel": channel, "user": user, "role": user_role},
        )
        ctx.metadata["execution_id"] = exec_id

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
            execution_trace.finish(
                exec_id, status="aborted",
                errors=[f"kill_switch: {policy_state.kill_reason}"],
            )
            await audit.record("process.aborted", {"reason": "kill_switch"})
            if tamper_audit:
                await tamper_audit.append("process.aborted", {"reason": "kill_switch", "exec_id": exec_id})
            return {
                "reply": "Sistema en kill switch. Operación bloqueada.",
                "authorized": False, "execution_id": exec_id,
                "classification": classification.classification.name,
            }

        # 4. RBAC
        if not has_perm(user_role, "tools.invoke_low"):
            execution_trace.finish(
                exec_id, status="aborted", errors=["rbac_deny"],
            )
            await audit.record("process.aborted", {"reason": "rbac_deny", "role": user_role})
            return {
                "reply": "No autorizado.", "authorized": False,
                "execution_id": exec_id,
                "classification": classification.classification.name,
            }

        # 5. AUTONOMY (L0 for chat)
        auto_decision = autonomy.assert_allowed(
            requested_level="L0_OBSERVE", action="chat", external=False,
        )
        if not auto_decision.allowed:
            execution_trace.finish(
                exec_id, status="aborted", errors=[auto_decision.reason],
            )
            await audit.record("process.aborted", {"reason": "autonomy", "decision": auto_decision.as_dict()})
            return {
                "reply": "No autorizado por autonomía.", "authorized": False,
                "execution_id": exec_id,
                "classification": classification.classification.name,
            }

        # 6. REASONING: plan
        plan = await reasoning.plan(message, context={
            "user": user, "channel": channel, "execution_id": exec_id,
        })
        execution_trace.append_tool_call(
            exec_id, name="reasoning.plan", args={"message": message},
            ok=True, result=plan.get("summary", ""),
        )

        # 7. MEMORY CONTEXT
        retrieved = await memory.retrieve(message, top_k=5)
        plan["memory_hits"] = retrieved

        # 8. SELF-IMPROVE: recuperar lecciones promovidas (P1.F reuse)
        promoted_lessons = self_improve.get_promoted_lessons()
        if promoted_lessons:
            plan["promoted_lessons"] = [
                {"pattern": lesson.get("pattern_key", ""), "text": lesson.get("lesson_text", "")}
                for lesson in promoted_lessons[:3]
            ]

        # 9. TOOL CALLS (vía ExecutionGuard fail-closed)
        tool_results: list[dict[str, Any]] = []
        for step in plan.get("steps", []):
            if step.get("type") != "tool_call" or not step.get("tool"):
                continue

            tool_name = step["tool"]
            tool_input = step.get("input", {})

            # Map tool_name → action for LegalGate (semántico)
            tool_to_action = {
                "clock": "internal_research",
                "calculator": "internal_research",
                "echo": "internal_research",
                "memory_lookup": "internal_research",
                "contract_analyzer": "internal_research",
            }
            action_for_guard = tool_to_action.get(tool_name, "tool_invocation")

            legal_verdict = legal_gate.evaluate(
                action_for_guard,
                text=str(tool_input) + " " + message,
                actor_role=user_role,
                live_authorized=False,
            )

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
                fail_result = {
                    "ok": False, "error": f"Guard: {guard.reason}",
                    "guard_verdict": guard.as_dict(),
                }
                tool_results.append({"tool": tool_name, "result": fail_result})
                await audit.record("guard.deny", guard.as_dict())
                execution_trace.append_tool_call(
                    exec_id, name=tool_name, args=tool_input,
                    ok=False, error=guard.reason,
                )
                if tamper_audit:
                    await tamper_audit.append("guard.deny", {
                        "exec_id": exec_id, "tool": tool_name, "reason": guard.reason,
                    })
                continue

            # Tool invocation - result SIEMPRE definido (P0.4)
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
            execution_trace.append_tool_call(
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

        # 10. REASONING: respond (con ProviderRouter)
        response = await reasoning.respond(
            message, plan=plan, tool_results=tool_results,
            classification=classification,
        )
        execution_trace.append_provider(
            exec_id, provider=response.get("provider", "unknown"),
            prompt_size=len(message), response_size=len(response.get("text", "")),
        )

        # 11. LEGAL GATE final
        final_verdict = legal_gate.evaluate(
            "internal_research",
            text=response["text"], actor_role=user_role,
        )
        if final_verdict.verdict == "BLOCKED":
            response["text"] = "Respuesta bloqueada por Legal Gate: " + final_verdict.reason

        # 12. MEMORY WRITE
        await memory.write(
            text=f"H: {message}\nA: {response['text']}",
            category="conversational",
            truth_level="OBSERVED",
            provenance="USER_INPUT",
            metadata={
                "user": user, "channel": channel,
                "execution_id": exec_id,
            },
        )

        # 13. AUDIT + FINISH TRACE + TAMPER-EVIDENT
        await audit.record("outtake", {
            "response": response["text"][:200],
            "user": user, "channel": channel,
            "execution_id": exec_id,
        })
        execution_trace.finish(
            exec_id, status="completed",
            outputs={"reply": response["text"]},
            decisions=[{
                "intent": plan.get("intent", {}).get("name"),
                "provider": response.get("provider"),
                "legal_verdict": final_verdict.verdict,
            }],
        )
        if tamper_audit:
            await tamper_audit.append("process.completed", {
                "exec_id": exec_id, "user": user,
                "provider": response.get("provider"),
                "legal_verdict": final_verdict.verdict,
            })

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
            "promoted_lessons_used": len(plan.get("promoted_lessons", [])),
        }

    async def run(
        self,
        task: str,
        *,
        ctx: RunContext | None = None,
        plan_fn: Any = None,
        act_fn: Any = None,
    ) -> dict[str, Any]:
        """Legacy loop API - mantiene compatibilidad."""
        ctx = ctx or RunContext(max_iterations=self.settings.runtime_loop_max_iter)
        self.log.info("runtime.run.start", task=task, task_id=ctx.task_id)

        result: dict[str, Any] = {"task_id": ctx.task_id, "ok": False, "iterations": 0, "history": []}
        timeout = self.settings.runtime_timeout_seconds
        t0 = time.time()

        try:
            while ctx.iteration < ctx.max_iterations:
                if (time.time() - t0) > timeout:
                    raise TimeoutError(f"Runtime timeout after {timeout}s")
                ctx.step("loop.start")

                plan = await plan_fn(task, ctx) if plan_fn else {"done": True}
                if plan.get("done"):
                    result["ok"] = True
                    break

                for action in plan.get("actions", []):
                    ctx.step("action", action=action)
                    if act_fn:
                        await act_fn(action, ctx)

                result["iterations"] = ctx.iteration

        except asyncio.TimeoutError:
            self.log.warning("runtime.timeout", task_id=ctx.task_id)
            result["error"] = "timeout"
        except Exception as e:  # noqa: BLE001
            self.log.error("runtime.error", error=str(e), task_id=ctx.task_id)
            result["error"] = str(e)

        result["history"] = ctx.history
        result["duration_s"] = time.time() - t0
        self.metrics.observe("runtime.run.duration_s", result["duration_s"])
        self.log.info("runtime.run.end", task_id=ctx.task_id, ok=result["ok"], iters=result["iterations"])
        return result
