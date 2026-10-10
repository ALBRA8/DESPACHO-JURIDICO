"""
MCP Server ALBRA.

Expone las tools del agente via protocolo MCP (JSON-RPC 2.0).
Endpoint HTTP/stdio preparado (no se acopla a un transporte específico).

Métodos expuestos:
- initialize
- list_tools (→ tools/list)
- call_tool (→ tools/call)
- list_capabilities (→ capabilities/list) - extensión ALBRA
- health
"""
from __future__ import annotations

from typing import Any

from albra.config.settings import Settings
from albra.mcp.protocol import MCPCapability, MCPRequest, MCPResponse
from albra.observability.logger import get_logger


class MCPServer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.mcp.server")
        self._tool_registry: Any = None
        self._cap_registry: Any = None
        # P1: security perimeter - NUNCA bypass
        self._execution_guard: Any = None
        self._audit: Any = None
        self._policy_state: Any = None
        self._autonomy_controller: Any = None
        self._rbac_check_fn: Any = None
        self._legal_gate: Any = None

    def wire(
        self,
        *,
        tool_registry: Any,
        capability_registry: Any,
        execution_guard: Any = None,
        audit: Any = None,
        policy_state: Any = None,
        autonomy_controller: Any = None,
        rbac_check_fn: Any = None,
        legal_gate: Any = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._cap_registry = capability_registry
        self._execution_guard = execution_guard
        self._audit = audit
        self._policy_state = policy_state
        self._autonomy_controller = autonomy_controller
        self._rbac_check_fn = rbac_check_fn
        self._legal_gate = legal_gate
        self.log.info(
            "mcp.wired",
            guard=execution_guard is not None,
            rbac=rbac_check_fn is not None,
            policy=policy_state is not None,
            autonomy=autonomy_controller is not None,
            legal=legal_gate is not None,
        )

    async def startup(self) -> None:
        self.log.info("mcp.server.startup")

    async def shutdown(self) -> None:
        self.log.info("mcp.server.shutdown")

    async def handle(self, request: MCPRequest) -> MCPResponse:
        """Maneja una request MCP entrante."""
        method = request.method
        self.log.info("mcp.handle", method=method, id=request.id)
        try:
            handler = getattr(self, f"_m_{method.replace('/', '_')}", None)
            if handler is None:
                return MCPResponse(
                    id=request.id,
                    error={"code": -32601, "message": f"Method not found: {method}"},
                )
            result = await handler(request.params) if not isinstance(handler, dict) else handler
            # Si handler es estático (tools/list), response directo
            if isinstance(handler, dict):
                result = handler
            return MCPResponse(id=request.id, result=result)
        except Exception as e:  # noqa: BLE001
            self.log.error("mcp.handle.error", method=method, error=str(e))
            return MCPResponse(
                id=request.id,
                error={"code": -32603, "message": "Internal error", "data": str(e)},
            )

    # --- Métodos MCP ---

    async def _m_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": "ALBRA-MCP",
                "version": "1.0.0",
            },
            "capabilities": {
                "tools": {"listChanged": True},
                "resources": {"listChanged": True},
                "prompts": {"listChanged": True},
            },
        }

    @property
    def _m_tools_list(self) -> dict[str, Any]:  # type: ignore[override]
        if not self._tool_registry:
            return {"tools": []}
        return {"tools": self._tool_registry.list()}

    @property
    def _m_capabilities_list(self) -> dict[str, Any]:  # type: ignore[override]
        if not self._cap_registry:
            return {"capabilities": []}
        return {"capabilities": self._cap_registry.list()}

    async def _m_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        """P1: TODO tool call vía ExecutionGuard - NUNCA bypass.

        Si execution_guard no está cableado → DENY explícito.
        """
        if not self._tool_registry:
            return {"ok": False, "error": "tool registry no cableada"}

        name = params.get("name")
        args = params.get("arguments", {})
        user = params.get("user", "mcp_client")
        user_role = params.get("role", "anon")

        # P1: si no hay ExecutionGuard cableado → DENY
        if self._execution_guard is None:
            return {
                "ok": False,
                "error": "FAIL-CLOSED: ExecutionGuard no cableado a MCP",
                "status": "DENIED",
            }

        # Evaluar legal gate para la action
        legal_verdict = None
        if self._legal_gate is not None:
            legal_verdict = self._legal_gate.evaluate(
                "tool_invocation",
                text=str(args),
                actor_role=user_role,
            )

        # Pasar por ExecutionGuard (fail-closed TOTAL)
        guard_verdict = self._execution_guard.check(
            action="tool_invocation",
            user_role=user_role,
            policy_state=self._policy_state.get_state() if self._policy_state else None,
            autonomy_controller=self._autonomy_controller,
            rbac_check_fn=self._rbac_check_fn or (lambda *_: False),
            legal_gate_verdict=legal_verdict,
            dedup_key=f"mcp:{name}:{user}",
        )

        if not guard_verdict.allowed:
            if self._audit is not None:
                await self._audit.record("mcp.guard.deny", guard_verdict.as_dict())
            return {
                "ok": False,
                "error": f"Guard deny: {guard_verdict.reason}",
                "status": "DENIED",
                "guard": guard_verdict.as_dict(),
            }

        # Solo si pasa el guard → invocar tool
        try:
            result = await self._tool_registry.invoke(name, args, user=user)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e), "status": "FAILURE"}

        if self._audit is not None:
            await self._audit.record("mcp.tool.invoke", {
                "tool": name, "user": user, "ok": result.get("ok", False),
            })

        return result

    async def _m_health(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "tools_count": len(self._tool_registry.list()) if self._tool_registry else 0,
            "capabilities_count": (
                len(self._cap_registry.list()) if self._cap_registry else 0
            ),
        }

    def expose_capabilities(self) -> list[MCPCapability]:
        """Devuelve la lista de capabilities como objetos MCP."""
        if not self._tool_registry:
            return []
        caps: list[MCPCapability] = []
        for t_dict in self._tool_registry.list():
            caps.append(
                MCPCapability(
                    name=t_dict["name"],
                    description=t_dict["description"],
                    input_schema=t_dict.get("input_schema", {}),
                    risk=t_dict.get("risk", "low"),
                    required_permission=t_dict.get("required_permission", "tools.invoke"),
                )
            )
        return caps
