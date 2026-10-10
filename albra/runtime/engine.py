"""
Runtime - el corazón operativo del agente ALBRA.

Responsable de:
- ejecutar el loop de razonamiento-acción
- hacer cumplir timeouts y max-iter
- propagar contexto
- emitir eventos
- invocar doctor ante fallos
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
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.runtime")
        self.metrics = get_metrics()
        self._started = False

    async def startup(self) -> None:
        self._started = True
        self.log.info("runtime.startup")

    async def shutdown(self) -> None:
        self._started = False
        self.log.info("runtime.shutdown")

    async def run(
        self,
        task: str,
        *,
        ctx: RunContext | None = None,
        plan_fn: Any = None,
        act_fn: Any = None,
    ) -> dict[str, Any]:
        """
        Loop AGENTE: plan → act → observe → repeat (hasta done o max_iter).
        """
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
