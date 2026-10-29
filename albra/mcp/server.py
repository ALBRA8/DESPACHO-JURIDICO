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

from datetime import datetime, timezone
from typing import Any

from albra.config.settings import Settings
from albra.evidence.legal_gate import LegalGate
from albra.mcp.protocol import MCPCapability, MCPRequest, MCPResponse
from albra.mcp.security import (
    AuthContext,
    McpAuditEntry,
    check_tool_permission,
    create_dev_context,
    validate_bearer_token,
)
from albra.observability.logger import get_logger
from albra.security.autonomy import AutonomyController
from albra.security.execution_guard import ExecutionGuard
from albra.security.policy_state import PolicyState


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash_dict(d: dict[str, Any]) -> str:
    import hashlib
    import json
    return hashlib.sha256(
        json.dumps(d, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _make_audit_entry(**kwargs: Any) -> McpAuditEntry:
    """Create a McpAuditEntry from kwargs."""
    return McpAuditEntry(**kwargs)


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


# =========================================================================
# V2.3-B: MCP SERVER PÚBLICO DE ALBRA (stdio transport, JSON-RPC 2.0)
# =========================================================================
# Inspiración clean-room: CourtListener MCP (stdio + Cloudflare Worker + OAuth),
# Moonlit Legal Research MCP (remote MCP), Legal-Skills-Open (discover/invoke),
# Agent Skills for Legal (marketplace de skills).
#
# V2.3-B: solo stdio transport (JSON-RPC over stdin/stdout).
# V2.4+: HTTP transport + OAuth + Cloudflare Worker.
#
# Tools expuestos (10):
# 1.  audit_citation(text)            → CitationAuditResult
# 2.  search_corpus(query, k=5)       → list[chunk]
# 3.  verify_deadline(claim_date, event_date, deadline_type) → DeadlineGuard result
# 4.  analyze_treatment(citing_text, cited_decision_id) → treatment labels
# 5.  advance_matter(matter_id, target_state, by, reason) → Matter
# 6.  verify_audit_chain(matter_id)  → hash chain verification
# 7.  list_matters(state, area)      → list[Matter]
# 8.  list_agents()                  → organigrama
# 9.  get_playbook(practice_area)    → Playbook
# 10. run_eval_suite()               → EvalSuite summary
#
# Formato: JSON-RPC 2.0 over stdio. Spec MCP:
# https://modelcontextprotocol.io/specification


import json
import sys
from typing import Callable

# JSON-RPC 2.0 error codes
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603

# Protocol version (MCP spec)
_MCP_PROTOCOL_VERSION = "2024-11-05"

_SERVER_NAME = "ALBRA-MCP"
_SERVER_VERSION = "2.3.0"


class McpServer:
    """MCP server público de ALBRA con stdio transport (JSON-RPC 2.0).

    Pure Python, no MCP SDK dependency. Expone 10 ALBRA tools:
    audit_citation, search_corpus, verify_deadline, analyze_treatment,
    advance_matter, verify_audit_chain, list_matters, list_agents,
    get_playbook, run_eval_suite.

    Las dependencias (MatterStore, MatterAudit, AgentLoader, PlaybookLoader)
    son inyectables para tests; si no se proveen, se construyen por defecto
    con paths estándar (`./data/matters.db`, `./data/matters`).
    """

    def __init__(
        self,
        *,
        matter_store: Any = None,
        matter_audit: Any = None,
        agent_loader: Any = None,
        playbook_loader: Any = None,
        security_mode: str = "dev",
        mcp_audit: Any = None,
        execution_guard: Any = None,
        policy_state: Any = None,
        autonomy_controller: Any = None,
        legal_gate: Any = None,
    ) -> None:
        self.log = get_logger("albra.mcp.server.public")
        # Security layer (V2.6 HARDENING)
        self._security_mode = security_mode  # "dev" | "test" | "production"
        self._mcp_audit = mcp_audit  # McpAuditLog or None
        # V1.6 security components (wired V2.6 HARDENING)
        self._execution_guard = execution_guard or ExecutionGuard()
        self._policy_state = policy_state or PolicyState()
        self._autonomy_controller = autonomy_controller or AutonomyController()
        self._legal_gate = legal_gate or LegalGate()
        # Dependencias inyectables (lazy init si None)
        self._matter_store: Any = matter_store
        self._matter_audit: Any = matter_audit
        self._agent_loader: Any = agent_loader
        self._playbook_loader: Any = playbook_loader
        # RAG se crea lazy (default_rag) bajo demanda
        self._rag_obj: Any = None
        # Registry: name -> {description, inputSchema, handler}
        self.tools: dict[str, dict[str, Any]] = {}
        self._register_default_tools()
        # Stdio auth context (set from initialize params, used in tools/call)
        self._stdio_auth_context: AuthContext | None = None

    # ===== Dependency injection (lazy defaults) =====

    def _store(self) -> Any:
        if self._matter_store is None:
            from albra.matters.store import MatterStore
            self._matter_store = MatterStore()
        return self._matter_store

    def _audit_chain(self) -> Any:
        if self._matter_audit is None:
            from albra.audit.matter_audit import MatterAudit
            self._matter_audit = MatterAudit()
        return self._matter_audit

    def _agents(self) -> Any:
        if self._agent_loader is None:
            from albra.agents.loader import AgentLoader
            self._agent_loader = AgentLoader()
        return self._agent_loader

    def _playbooks(self) -> Any:
        if self._playbook_loader is None:
            from albra.playbooks.loader import PlaybookLoader
            self._playbook_loader = PlaybookLoader()
        return self._playbook_loader

    def _get_rag(self) -> Any:
        if self._rag_obj is None:
            from albra.knowledge.rag_local import default_rag
            self._rag_obj = default_rag()
        return self._rag_obj

    # ===== Tool registration =====

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        """Registra una tool MCP con su name, description, inputSchema y handler."""
        self.tools[name] = {
            "description": description,
            "inputSchema": input_schema,
            "handler": handler,
        }
        self.log.info("mcp.tool.registered", tool=name)

    def _register_default_tools(self) -> None:
        """Registra las 10 tools ALBRA por defecto."""
        # 1. audit_citation
        self.register_tool(
            "audit_citation",
            (
                "Run citation audit on text. Returns revealed/blocked + "
                "verified/unverified/rejected citations against the ALBRA corpus."
            ),
            {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text to audit for citations",
                    },
                },
                "required": ["text"],
            },
            self._tool_audit_citation,
        )
        # 2. search_corpus
        self.register_tool(
            "search_corpus",
            (
                "Search ALBRA legal corpus (Constitución 1991, Ley 100/1993, "
                "Ley 80/1993) using TF-IDF + cosine similarity. Returns top-k chunks."
            ),
            {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language query in Spanish",
                    },
                    "k": {
                        "type": "integer",
                        "description": "Number of top results (default 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
            self._tool_search_corpus,
        )
        # 3. verify_deadline
        self.register_tool(
            "verify_deadline",
            (
                "Verify a Colombian procedural deadline (deterministic check). "
                "Returns ok/expired + days_elapsed/remaining + reason."
            ),
            {
                "type": "object",
                "properties": {
                    "claim_date": {
                        "type": "string",
                        "description": "ISO date (YYYY-MM-DD) when the right/obligation arose",
                    },
                    "event_date": {
                        "type": "string",
                        "description": "ISO date (YYYY-MM-DD) when the event occurred",
                    },
                    "deadline_type": {
                        "type": "string",
                        "description": (
                            "Key of COLOMBIAN_DEADLINES "
                            "(e.g. prescripcion_civil_extracontractual, "
                            "demanda_contestacion, tutela_presentacion)"
                        ),
                    },
                },
                "required": ["claim_date", "event_date", "deadline_type"],
            },
            self._tool_verify_deadline,
        )
        # 4. analyze_treatment
        self.register_tool(
            "analyze_treatment",
            (
                "Analyze how a citing decision treats a cited decision. "
                "Returns one of: followed, distinguished, doubted, overruled, "
                "per_incuriam, affirmed, reversed, cited (neutral default)."
            ),
            {
                "type": "object",
                "properties": {
                    "citing_text": {
                        "type": "string",
                        "description": "Text of the citing decision (paragraph that mentions the cited case)",
                    },
                    "cited_decision_id": {
                        "type": "string",
                        "description": "Identifier of the cited decision (e.g. 'C-251/2002')",
                    },
                },
                "required": ["citing_text", "cited_decision_id"],
            },
            self._tool_analyze_treatment,
        )
        # 5. advance_matter
        self.register_tool(
            "advance_matter",
            (
                "Advance a matter to the next state in the workflow machine "
                "(NUEVO → INTAKE → PLANEACIÓN → EJECUTANDO → BORRADOR-FINAL → "
                "EN-ESPERA-DE-APROBACIÓN → LISTO-PARA-CLIENTE → FIRMADO-Y-ENTREGADO)."
            ),
            {
                "type": "object",
                "properties": {
                    "matter_id": {"type": "string", "description": "Matter UUID"},
                    "target_state": {"type": "string", "description": "Target state name"},
                    "by": {
                        "type": "string",
                        "description": "Actor performing the transition (default 'system')",
                        "default": "system",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for the transition",
                        "default": "",
                    },
                },
                "required": ["matter_id", "target_state"],
            },
            self._tool_advance_matter,
        )
        # 6. verify_audit_chain
        self.register_tool(
            "verify_audit_chain",
            (
                "Verify the SHA-256 hash chain integrity of a matter's audit log "
                "(tamper-evident JSONL append-only log). Returns ok + total + broken_at."
            ),
            {
                "type": "object",
                "properties": {
                    "matter_id": {"type": "string", "description": "Matter UUID to verify"},
                },
                "required": ["matter_id"],
            },
            self._tool_verify_audit_chain,
        )
        # 7. list_matters
        self.register_tool(
            "list_matters",
            (
                "List matters in the store. Optional filters by state and area. "
                "Returns list of matter dicts."
            ),
            {
                "type": "object",
                "properties": {
                    "state": {
                        "type": "string",
                        "description": "Optional state filter (e.g. NUEVO, INTAKE)",
                    },
                    "area": {
                        "type": "string",
                        "description": "Optional area filter (e.g. civil, laboral)",
                    },
                },
                "required": [],
            },
            self._tool_list_matters,
        )
        # 8. list_agents
        self.register_tool(
            "list_agents",
            (
                "List the ALBRA agent organigrama (5 agents: filing, intake, "
                "research, drafting, review) with tier, reports_to, escalates_to."
            ),
            {"type": "object", "properties": {}, "required": []},
            self._tool_list_agents,
        )
        # 9. get_playbook
        self.register_tool(
            "get_playbook",
            (
                "Get a practice-area playbook (laboral, civil, constitucional, "
                "familia, corporativo) with workflow_states, deadline_types, "
                "citation_corpus, red_flags."
            ),
            {
                "type": "object",
                "properties": {
                    "practice_area": {
                        "type": "string",
                        "description": "Practice area key (e.g. laboral, civil)",
                    },
                },
                "required": ["practice_area"],
            },
            self._tool_get_playbook,
        )
        # 10. run_eval_suite
        self.register_tool(
            "run_eval_suite",
            (
                "Run the ALBRA V2.3-A eval suite: 3 drafting rubrics + "
                "100-citation phantom test (50 REAL + 50 PHANTOM). "
                "Returns summary metrics (rubric pass rate + TPR/TNR/FPR/FNR)."
            ),
            {"type": "object", "properties": {}, "required": []},
            self._tool_run_eval_suite,
        )

    # ===== Tool handlers =====

    def _tool_audit_citation(self, args: dict[str, Any]) -> dict[str, Any]:
        """Tool 1: audit_citation(text) → CitationAuditResult.as_dict()."""
        from albra.knowledge.citation_audit import CitationAuditor
        auditor = CitationAuditor()
        result = auditor.audit_response(args["text"])
        return result.as_dict()

    def _tool_search_corpus(self, args: dict[str, Any]) -> dict[str, Any]:
        """Tool 2: search_corpus(query, k=5) → {results: list[chunk], count: int}."""
        rag = self._get_rag()
        k = int(args.get("k", 5))
        chunks = rag.search(args["query"], k=k)
        return {"results": chunks, "count": len(chunks)}

    def _tool_verify_deadline(self, args: dict[str, Any]) -> dict[str, Any]:
        """Tool 3: verify_deadline(claim_date, event_date, deadline_type)."""
        from albra.security.deterministic_guard import DeadlineGuard
        claim_date = datetime.fromisoformat(args["claim_date"])
        event_date = datetime.fromisoformat(args["event_date"])
        guard = DeadlineGuard()
        return guard.check(
            claim_date=claim_date,
            event_date=event_date,
            deadline_type=args["deadline_type"],
        )

    def _tool_analyze_treatment(self, args: dict[str, Any]) -> dict[str, Any]:
        """Tool 4: analyze_treatment(citing_text, cited_decision_id)."""
        from albra.knowledge.agentic_citator import AgenticCitator
        citator = AgenticCitator()
        return citator.analyze(
            citing_text=args["citing_text"],
            cited_decision_id=args["cited_decision_id"],
        )

    def _tool_advance_matter(self, args: dict[str, Any]) -> dict[str, Any]:
        """Tool 5: advance_matter(matter_id, target_state, by, reason) → Matter.as_dict()."""
        store = self._store()
        matter = store.advance_state(
            args["matter_id"],
            args["target_state"],
            by=args.get("by", "system"),
            reason=args.get("reason", ""),
        )
        return matter.as_dict()

    def _tool_verify_audit_chain(self, args: dict[str, Any]) -> dict[str, Any]:
        """Tool 6: verify_audit_chain(matter_id) → hash chain verification."""
        audit = self._audit_chain()
        return audit.verify_chain(args["matter_id"])

    def _tool_list_matters(self, args: dict[str, Any]) -> dict[str, Any]:
        """Tool 7: list_matters(state, area) → {matters: list[Matter.as_dict()], count}."""
        store = self._store()
        kwargs: dict[str, Any] = {}
        if args.get("state"):
            kwargs["state"] = args["state"]
        if args.get("area"):
            kwargs["area"] = args["area"]
        matters = store.list_matters(**kwargs)
        return {
            "matters": [m.as_dict() for m in matters],
            "count": len(matters),
        }

    def _tool_list_agents(self, args: dict[str, Any]) -> dict[str, Any]:
        """Tool 8: list_agents() → {agents: organigrama, count}."""
        loader = self._agents()
        organigrama = loader.organigrama()
        return {"agents": organigrama, "count": len(organigrama)}

    def _tool_get_playbook(self, args: dict[str, Any]) -> dict[str, Any]:
        """Tool 9: get_playbook(practice_area) → Playbook.as_dict()."""
        loader = self._playbooks()
        pb = loader.get(args["practice_area"])
        if pb is None:
            raise ValueError(
                f"Unknown practice_area: {args['practice_area']!r}. "
                f"Valid areas: {loader.list_areas()}"
            )
        return pb.as_dict()

    def _tool_run_eval_suite(self, args: dict[str, Any]) -> dict[str, Any]:
        """Tool 10: run_eval_suite() → EvalSuite summary dict."""
        from albra.eval.runner import run_eval_suite
        return run_eval_suite()

    # ===== Public API =====

    def list_tools(self) -> list[dict[str, Any]]:
        """Devuelve la lista de tools (name, description, inputSchema)."""
        return [
            {
                "name": name,
                "description": t["description"],
                "inputSchema": t["inputSchema"],
            }
            for name, t in self.tools.items()
        ]

    def call_tool(
        self,
        name: str,
        args: dict[str, Any],
        *,
        auth_context: Any = None,
    ) -> dict[str, Any]:
        """Invoca una tool por name con args.

        V2.6 HARDENING: call chain = Auth → RBAC → Audit → Execute.

        Args:
            name: Tool name.
            args: Tool arguments.
            auth_context: AuthContext (from albra.mcp.security). If None and
                security_mode="production" → DENY. If None and security_mode="dev"
                → auto-create dev context (backward compat).

        Returns:
            dict with result or error. Denied calls return:
            {"error": "...", "status": "DENIED", "authorization": "DENIED"}
        """
        import time as _time
        start = _time.time()
        ts = _utcnow_iso()

        # Resolve auth context
        if auth_context is None:
            if self._security_mode == "production":
                # PRODUCTION: deny without auth
                entry = _make_audit_entry(
                    timestamp=ts, request_id="denied-no-auth", actor="anonymous",
                    role="anonymous", auth_method="none", tool_name=name,
                    action="mcp.tool.call", authorization_result="DENIED", denial_reason="No auth context (production mode)",
                    input_hash=_hash_dict(args), output_hash="", matter_id="", correlation_id="denied",
                    result_status="denied", error="No auth context", latency_ms=0,
                    environment=self._security_mode,
                )
                if self._mcp_audit is not None:
                    self._mcp_audit.record(entry)
                return {
                    "error": "FAIL-CLOSED: auth_context required in production mode",
                    "status": "DENIED",
                    "authorization": "DENIED",
                    "reason": "No auth context provided",
                }
            # DEV/TEST: auto-create dev context for backward compat
            auth_context = create_dev_context()

        # Check tool exists
        if name not in self.tools:
            return {"error": f"Unknown tool: {name}", "status": "NOT_FOUND"}

        # RBAC permission check
        allowed, reason = check_tool_permission(name, auth_context)
        if not allowed:
            entry = _make_audit_entry(
                timestamp=ts, request_id=auth_context.request_id, actor=auth_context.identity,
                role=auth_context.role, auth_method=auth_context.auth_method,
                tool_name=name, action="mcp.tool.call", authorization_result="DENIED", denial_reason=reason,
                input_hash=_hash_dict(args), output_hash="", matter_id="", correlation_id=auth_context.request_id if auth_context else "denied",
                result_status="denied", error=reason,
                latency_ms=(_time.time() - start) * 1000, environment=self._security_mode,
            )
            if self._mcp_audit is not None:
                self._mcp_audit.record(entry)
            return {
                "error": f"RBAC DENY: {reason}",
                "status": "DENIED",
                "authorization": "DENIED",
                "reason": reason,
            }

        # ===== ExecutionGuard + LegalGate (V2.6 HARDENING) =====
        # Chain: RBAC ALLOW → LegalGate evaluate → ExecutionGuard check → Execute
        # This ensures RBAC ALLOW does NOT automatically mean execution allowed.

        # 1. LegalGate evaluation
        legal_verdict = self._legal_gate.evaluate(
            action="tool_invocation",
            text=str(args),
            actor_role=auth_context.role,
        )

        # 2. ExecutionGuard check (fail-closed TOTAL)
        # Use auth_context.has_permission (V2.6 ROLE_PERMISSIONS) as rbac_check_fn,
        # NOT the V1.6 rbac.py has_permission (which has different role names).
        guard_verdict = self._execution_guard.check(
            action="tool_invocation",
            user_role=auth_context.role,
            policy_state=self._policy_state,
            autonomy_controller=self._autonomy_controller,
            rbac_check_fn=lambda _role, perm: auth_context.has_permission(perm),
            legal_gate_verdict=legal_verdict,
            dedup_key=f"mcp:{name}:{auth_context.identity}",
        )

        if not guard_verdict.allowed:
            guard_reason = guard_verdict.reason
            entry = _make_audit_entry(
                timestamp=ts, request_id=auth_context.request_id, actor=auth_context.identity,
                role=auth_context.role, auth_method=auth_context.auth_method,
                tool_name=name, action="mcp.tool.call", authorization_result="DENIED",
                denial_reason=f"GUARD DENY: {guard_reason}",
                input_hash=_hash_dict(args), output_hash="", matter_id="",
                correlation_id=auth_context.request_id,
                result_status="denied", error=guard_reason,
                latency_ms=(_time.time() - start) * 1000, environment=self._security_mode,
            )
            if self._mcp_audit is not None:
                self._mcp_audit.record(entry)
            return {
                "error": f"GUARD DENY: {guard_reason}",
                "status": "DENIED",
                "authorization": "DENIED",
                "reason": guard_reason,
                "guard_checks": [c.name + ":" + str(c.ok) for c in guard_verdict.checks],
            }

        # Execute tool handler
        try:
            result = self.tools[name]["handler"](args)
            latency = (_time.time() - start) * 1000
            output_hash = _hash_dict(result) if isinstance(result, dict) else ""
            matter_id = str(args.get("matter_id", "")) if isinstance(args, dict) else ""

            # Record audit entry
            entry = _make_audit_entry(
                timestamp=ts, request_id=auth_context.request_id, actor=auth_context.identity,
                role=auth_context.role, auth_method=auth_context.auth_method,
                tool_name=name, action="mcp.tool.call", authorization_result="ALLOWED", denial_reason="",
                input_hash=_hash_dict(args), output_hash=output_hash, matter_id=matter_id, correlation_id=auth_context.request_id,
                result_status="success" if "error" not in result else "error",
                error=result.get("error", ""),
                latency_ms=latency, environment=self._security_mode,
            )
            if self._mcp_audit is not None:
                self._mcp_audit.record(entry)
            return result
        except Exception as e:  # noqa: BLE001
            latency = (_time.time() - start) * 1000
            entry = _make_audit_entry(
                timestamp=ts, request_id=auth_context.request_id, actor=auth_context.identity,
                role=auth_context.role, auth_method=auth_context.auth_method,
                tool_name=name, action="mcp.tool.call", authorization_result="ALLOWED", denial_reason="",
                input_hash=_hash_dict(args), output_hash="", matter_id="", correlation_id=auth_context.request_id if auth_context else "denied",
                result_status="error", error=str(e),
                latency_ms=latency, environment=self._security_mode,
            )
            if self._mcp_audit is not None:
                self._mcp_audit.record(entry)
            self.log.error("mcp.tool.error", tool=name, error=str(e))
            return {"error": str(e), "status": "ERROR"}

    # ===== JSON-RPC 2.0 dispatch =====

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Dispatch una request JSON-RPC 2.0 y devuelve la response.

        Soporta métodos MCP:
        - initialize        → serverInfo + capabilities
        - tools/list        → list of tools
        - tools/call        → call tool by name with arguments
        - shutdown          → acknowledge shutdown
        - ping              → health echo

        Si la request es una notification (sin `id`), no se envía response
        (devuelve {} vacío en este método; el caller decide si escribir).
        """
        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {}) or {}

        def make_response(result: Any = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
            resp: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}
            if error is not None:
                resp["error"] = error
            else:
                resp["result"] = result
            return resp

        # Notifications (no id): silently ignore, return empty dict.
        if req_id is None:
            return {}

        if not isinstance(method, str) or not method:
            return make_response(error={
                "code": _INVALID_REQUEST,
                "message": "Invalid request: missing or empty 'method'.",
            })

        try:
            if method == "initialize":
                # V3.0: Extract auth from initialize params (stdio path)
                if isinstance(params, dict) and "auth" in params:
                    auth_data = params["auth"]
                    if isinstance(auth_data, dict) and auth_data.get("token"):
                        token = auth_data["token"]
                        self._stdio_auth_context = validate_bearer_token(
                            token, mode=self._security_mode
                        )
                result: dict[str, Any] = {
                    "protocolVersion": _MCP_PROTOCOL_VERSION,
                    "serverInfo": {
                        "name": _SERVER_NAME,
                        "version": _SERVER_VERSION,
                    },
                    "capabilities": {
                        "tools": {"listChanged": True},
                        "resources": {"listChanged": True},
                        "prompts": {"listChanged": True},
                    },
                }
                return make_response(result=result)
            if method == "ping":
                return make_response(result={"ok": True, "name": _SERVER_NAME})
            if method == "tools/list":
                return make_response(result={"tools": self.list_tools()})
            if method == "tools/call":
                name = params.get("name") if isinstance(params, dict) else None
                arguments = params.get("arguments", {}) if isinstance(params, dict) else {}
                if not name:
                    return make_response(error={
                        "code": _INVALID_PARAMS,
                        "message": "Missing 'name' in tools/call params.",
                    })
                if not isinstance(arguments, dict):
                    return make_response(error={
                        "code": _INVALID_PARAMS,
                        "message": "'arguments' must be an object.",
                    })
                tool_result = self.call_tool(name, arguments, auth_context=self._stdio_auth_context)
                # Si el handler devolvió un error explícito, propagar como
                # result (MCP permite tool errors como content isError).
                return make_response(result={
                    "content": [{"type": "text", "text": json.dumps(tool_result, default=str, ensure_ascii=False)}],
                    "isError": "error" in tool_result,
                })
            if method == "shutdown":
                return make_response(result={"ok": True, "shutdown": True})
            return make_response(error={
                "code": _METHOD_NOT_FOUND,
                "message": f"Method not found: {method}",
            })
        except Exception as e:  # noqa: BLE001
            self.log.error("mcp.dispatch.error", method=method, error=str(e))
            return make_response(error={
                "code": _INTERNAL_ERROR,
                "message": "Internal error",
                "data": str(e),
            })

    def run_stdio(self) -> None:
        """Run MCP server over stdio (JSON-RPC 2.0).

        Loop:
        1. Read line from stdin (JSON-RPC request).
        2. Parse + dispatch via handle_request.
        3. Write JSON-RPC response to stdout (newline-delimited).
        4. Repeat until EOF.

        Si la línea no es JSON válido → parse error response.
        Si la request es notification (no id) → no response.

        CRÍTICO: redirige los handlers de logging que usan stdout a stderr,
        porque stdout es el canal exclusivo de JSON-RPC y cualquier log
        corrompería el protocolo.
        """
        _redirect_logging_to_stderr()
        self.log.info("mcp.stdio.start", tools_count=len(self.tools))
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            # Parse request
            try:
                request = json.loads(line)
            except json.JSONDecodeError as e:
                # Parse error: response with null id
                response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": _PARSE_ERROR,
                        "message": f"Parse error: {e}",
                    },
                }
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()
                continue
            # Dispatch
            response = self.handle_request(request)
            # Notifications (no id) → no response
            if not response:
                continue
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        self.log.info("mcp.stdio.stop")


# =========================================================================
# V2.3-D: MCP HTTP transport + OAuth scaffold
# =========================================================================
# Reuses the 10 ALBRA tools registered in McpServer. Adds HTTP endpoints
# so external clients (Claude Code, ChatGPT, Cursor) can consume ALBRA over
# the network. OAuth is a V2.3-D scaffold (fake tokens); V2.6+ integrates
# a real provider (Auth0, Keycloak, GitHub OAuth App).
#
# Pure stdlib: http.server.BaseHTTPRequestHandler + json. NO FastAPI/uvicorn.
#
# Endpoints:
#   GET  /mcp/health                                  → health check
#   POST /mcp/initialize                              → server info + capabilities
#   POST /mcp/tools/list                              → list of 10 tools
#   POST /mcp/tools/call                              → invoke tool by name
#   GET  /mcp/.well-known/oauth-authorization-server  → OAuth metadata
#   GET  /mcp/oauth/authorize[?redirect_uri&state]    → issue code (scaffold)
#   POST /mcp/oauth/token                             → exchange code → token
#
# CORS headers on every response. Bearer token required on initialize /
# tools/list / tools/call when oauth_required=True.

import http.server
import secrets as _secrets_mod
import urllib.parse as _urlparse

_OAUTH_SCOPE = "mcp:tools"
_OAUTH_TOKEN_TTL_SECONDS = 3600


class McpHttpServer:
    """MCP HTTP server con OAuth scaffold (V2.3-D).

    Pure stdlib (http.server + json). Reuses the 10 ALBRA tools from
    McpServer. Adds 7 HTTP endpoints + CORS + Bearer token validation.

    OAuth V2.3-D scaffold: returns fake tokens. V2.6+ integrates real
    OAuth provider (Auth0, Keycloak, GitHub OAuth App).
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        oauth_required: bool = True,
        *,
        mcp_server: McpServer | None = None,
        auth_mode: str = "dev",
    ) -> None:
        self.host = host
        self.port = port
        self.oauth_required = oauth_required
        self._auth_mode = auth_mode  # "dev" | "test" | "production"
        self.log = get_logger("albra.mcp.http")
        # Reuse the McpServer with the 10 tools (injectable for tests)
        # Pass security_mode so call_tool uses the same auth mode
        if mcp_server is not None:
            self.mcp: McpServer = mcp_server
        else:
            self.mcp = McpServer(security_mode=auth_mode)
        # OAuth scaffold (V2.3-D): in-memory code/token store
        self._oauth_codes: dict[str, dict[str, Any]] = {}
        self._oauth_tokens: set[str] = set()

    # ===== Public dispatch =====

    # Route table: path → set of allowed HTTP methods (excl. OPTIONS preflight,
    # which is always 204).
    _ROUTES: dict[str, set[str]] = {
        "/mcp/health": {"GET"},
        "/mcp/.well-known/oauth-authorization-server": {"GET"},
        "/mcp/oauth/authorize": {"GET"},
        "/mcp/oauth/token": {"POST"},
        "/mcp/initialize": {"POST"},
        "/mcp/tools/list": {"POST"},
        "/mcp/tools/call": {"POST"},
    }
    # Endpoints that require a valid bearer token when oauth_required=True.
    _PROTECTED_PATHS: set[str] = {
        "/mcp/initialize", "/mcp/tools/list", "/mcp/tools/call",
    }

    def _handle_http_request(
        self,
        method: str,
        path: str,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> tuple[int, bytes, dict[str, str]]:
        """Dispatch una request HTTP y retorna (status, body_bytes, headers).

        Args:
            method: HTTP method (GET/POST/OPTIONS).
            path: Full path with optional query string.
            body: Raw request body bytes (POST only).
            headers: Request headers dict (case-insensitive lookup for
                Authorization).

        Returns:
            (status_code, body_bytes, response_headers_dict) — CORS headers
            always present.
        """
        headers = headers or {}
        parsed = _urlparse.urlparse(path)
        clean_path = parsed.path
        bearer = self._extract_bearer(headers)

        # OPTIONS preflight → 204 with CORS headers, no body.
        if method == "OPTIONS":
            return self._build(204, b"", {})

        # Unknown path → 404 (regardless of bearer).
        if clean_path not in self._ROUTES:
            return self._not_found(clean_path)

        # Method not allowed on this path → 405 (regardless of bearer).
        allowed = self._ROUTES[clean_path]
        if method not in allowed:
            return self._method_not_allowed(clean_path, method)

        # Protected endpoints: bearer required when oauth_required=True.
        # V3.0: validate_bearer_token resolves AuthContext from token.
        # In production mode: ALL tokens return None (requires real OAuth).
        auth_ctx: AuthContext | None = None
        if self.oauth_required and clean_path in self._PROTECTED_PATHS:
            auth_ctx = self._resolve_auth_context(bearer)
            if auth_ctx is None:
                return self._unauthorized(
                    f"Bearer token required and must be valid (auth_mode={self._auth_mode})"
                )

        # Parse JSON body for protected POST endpoints (initialize/tools/*).
        # /mcp/oauth/token accepts both JSON and form-encoded, handled inside
        # _handle_token itself.
        payload: dict[str, Any] = {}
        if method == "POST" and clean_path in self._PROTECTED_PATHS and body:
            try:
                parsed_body = json.loads(body)
                if not isinstance(parsed_body, dict):
                    return self._bad_request("Body must be a JSON object")
                payload = parsed_body
            except json.JSONDecodeError as e:
                return self._bad_request(f"Invalid JSON: {e}")

        try:
            # Public GET endpoints.
            if method == "GET" and clean_path == "/mcp/health":
                return self._build(200, self._json(self._health_payload()), {})

            if method == "GET" and clean_path == "/mcp/.well-known/oauth-authorization-server":
                return self._build(200, self._json(self._oauth_metadata()), {})

            if method == "GET" and clean_path == "/mcp/oauth/authorize":
                return self._handle_authorize(parsed.query)

            if method == "POST" and clean_path == "/mcp/oauth/token":
                return self._handle_token(body)

            # Protected POST endpoints.
            if method == "POST" and clean_path == "/mcp/initialize":
                return self._build(200, self._json(self._initialize_payload()), {})

            if method == "POST" and clean_path == "/mcp/tools/list":
                return self._build(200, self._json({"tools": self.mcp.list_tools()}), {})

            if method == "POST" and clean_path == "/mcp/tools/call":
                name = payload.get("name")
                if not name:
                    return self._bad_request("Missing 'name' in tools/call body")
                args = payload.get("arguments", {}) or {}
                if not isinstance(args, dict):
                    return self._bad_request("'arguments' must be an object")
                # V3.0: auth_ctx already resolved from bearer token above.
                # Pass it to call_tool — identity is authenticated, NOT inferred.
                result = self.mcp.call_tool(name, args, auth_context=auth_ctx)
                return self._build(
                    200,
                    self._json({
                        "content": [{
                            "type": "text",
                            "text": json.dumps(result, default=str, ensure_ascii=False),
                        }],
                        "isError": "error" in result,
                    }),
                    {},
                )

            # Should be unreachable (route table guarantees method match), but
            # keep a defensive fallback.
            return self._method_not_allowed(clean_path, method)
        except Exception as e:  # noqa: BLE001
            self.log.error("mcp.http.dispatch.error", path=clean_path, error=str(e))
            return self._internal_error(str(e))

    # ===== Payload builders =====

    def _health_payload(self) -> dict[str, Any]:
        return {
            "ok": True,
            "server": _SERVER_NAME,
            "version": _SERVER_VERSION,
            "tools_count": len(self.mcp.list_tools()),
            "oauth_required": self.oauth_required,
        }

    def _initialize_payload(self) -> dict[str, Any]:
        return {
            "protocolVersion": _MCP_PROTOCOL_VERSION,
            "serverInfo": {"name": _SERVER_NAME, "version": _SERVER_VERSION},
            "capabilities": {
                "tools": {"listChanged": True},
                "resources": {"listChanged": True},
                "prompts": {"listChanged": True},
            },
            "transport": "http",
            "oauth_required": self.oauth_required,
        }

    def _oauth_metadata(self) -> dict[str, Any]:
        base = f"http://{self.host}:{self.port}"
        return {
            "issuer": base,
            "authorization_endpoint": f"{base}/mcp/oauth/authorize",
            "token_endpoint": f"{base}/mcp/oauth/token",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "client_credentials"],
            "code_challenge_methods_supported": ["plain", "S256"],
            "token_endpoint_auth_methods_supported": ["client_secret_post"],
            "scopes_supported": [_OAUTH_SCOPE],
            "note": "V2.3-D OAuth scaffold. V2.6+: integrate real provider.",
        }

    def _handle_authorize(self, query: str) -> tuple[int, bytes, dict[str, str]]:
        """V2.3-D scaffold: issue a fake auth code and redirect.

        If `redirect_uri` is in the query → 302 redirect with ?code=...
        Otherwise → 200 with JSON body containing the code.
        """
        params = dict(_urlparse.parse_qsl(query))
        redirect_uri = params.get("redirect_uri")
        state = params.get("state", "")
        code = "albra-code-" + _secrets_mod.token_hex(8)
        self._oauth_codes[code] = {
            "issued_at": datetime.now().isoformat(),
            "used": False,
            "state": state,
            "redirect_uri": redirect_uri,
        }
        if redirect_uri:
            # OAuth spec: 302 redirect with code in query
            sep = "&" if "?" in redirect_uri else "?"
            location = f"{redirect_uri}{sep}code={code}&state={state}"
            return self._build(
                302,
                b"",
                {"Location": location, "Cache-Control": "no-store"},
            )
        # No redirect_uri → return code inline (dev/test convenience)
        return self._build(
            200,
            self._json({
                "code": code,
                "state": state,
                "note": "V2.3-D OAuth scaffold: code returned inline. "
                        "V2.6+: integrate real OAuth provider.",
            }),
            {"Cache-Control": "no-store"},
        )

    def _handle_token(self, body: bytes) -> tuple[int, bytes, dict[str, str]]:
        """V2.3-D scaffold: exchange code for a fake bearer token."""
        # Accept JSON or form-encoded body
        parsed: Any = None
        if body:
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = dict(_urlparse.parse_qsl(body.decode("utf-8", errors="replace")))
        if not isinstance(parsed, dict):
            parsed = {}
        grant_type = parsed.get("grant_type")
        code = parsed.get("code")
        if grant_type != "authorization_code":
            return self._bad_request("grant_type must be 'authorization_code'")
        if not code or code not in self._oauth_codes:
            return self._bad_request("Invalid or unknown 'code'")
        if self._oauth_codes[code]["used"]:
            return self._bad_request("Code already used")
        self._oauth_codes[code]["used"] = True
        token = "albra-token-" + _secrets_mod.token_hex(16)
        self._oauth_tokens.add(token)
        return self._build(
            200,
            self._json({
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": _OAUTH_TOKEN_TTL_SECONDS,
                "scope": _OAUTH_SCOPE,
                "note": "V2.3-D OAuth scaffold: fake token. "
                        "V2.6+: exchange for real provider token.",
            }),
            {"Cache-Control": "no-store", "Pragma": "no-cache"},
        )

    # ===== Bearer token validation =====

    @staticmethod
    def _extract_bearer(headers: dict[str, str]) -> str | None:
        """Case-insensitive Authorization header lookup."""
        for k, v in headers.items():
            if k.lower() == "authorization":
                if v.startswith("Bearer "):
                    return v[7:].strip()
                return None
        return None

    def _is_valid_bearer(self, token: str | None) -> bool:
        """Validate bearer token using security.validate_bearer_token."""
        return self._resolve_auth_context(token) is not None

    def _resolve_auth_context(self, token: str | None) -> AuthContext | None:
        """Resolve a bearer token into an AuthContext.

        In production mode: returns None for ALL tokens (requires real OAuth).
        In test mode: accepts role-prefixed test tokens (test-abogado-xxx, etc.).
        In dev mode: accepts any non-empty token (returns dev admin context).
        Scaffold-issued OAuth tokens are accepted in dev/test modes.
        """
        if not token:
            return None
        # Scaffold-issued tokens: look up the role from OAuth flow
        if token in self._oauth_tokens and self._auth_mode != "production":
            # Scaffold tokens get admin context in dev, test in test
            from albra.mcp.security import create_dev_context, create_test_context
            if self._auth_mode == "test":
                return create_test_context(role="admin")
            return create_dev_context(role="admin")
        # Use validate_bearer_token from security.py
        return validate_bearer_token(token, mode=self._auth_mode)

    # ===== Response builders =====

    def _build(
        self,
        status: int,
        body: bytes,
        headers: dict[str, str],
    ) -> tuple[int, bytes, dict[str, str]]:
        """Compose final response with CORS headers + Content-Type."""
        out_headers: dict[str, str] = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "86400",
        }
        if body:
            out_headers["Content-Type"] = "application/json; charset=utf-8"
        out_headers.update(headers)
        return status, body, out_headers

    def _json(self, payload: Any) -> bytes:
        return json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")

    def _bad_request(self, msg: str) -> tuple[int, bytes, dict[str, str]]:
        return self._build(400, self._json({"error": "bad_request", "message": msg}), {})

    def _unauthorized(self, msg: str) -> tuple[int, bytes, dict[str, str]]:
        return self._build(
            401,
            self._json({"error": "unauthorized", "message": msg}),
            {"WWW-Authenticate": 'Bearer realm="ALBRA-MCP"'},
        )

    def _method_not_allowed(self, path: str, method: str) -> tuple[int, bytes, dict[str, str]]:
        body = self._json({
            "error": "method_not_allowed",
            "message": f"Method {method} not allowed on {path}",
        })
        return self._build(
            405,
            body,
            {"Allow": self._allow_for_path(path)},
        )

    def _not_found(self, path: str) -> tuple[int, bytes, dict[str, str]]:
        return self._build(
            404,
            self._json({"error": "not_found", "message": f"Path not found: {path}"}),
            {},
        )

    def _internal_error(self, msg: str) -> tuple[int, bytes, dict[str, str]]:
        return self._build(
            500,
            self._json({"error": "internal_error", "message": msg}),
            {},
        )

    @staticmethod
    def _allow_for_path(path: str) -> str:
        if path in ("/mcp/health", "/mcp/.well-known/oauth-authorization-server", "/mcp/oauth/authorize"):
            return "GET, OPTIONS"
        if path == "/mcp/oauth/token":
            return "POST, OPTIONS"
        if path in ("/mcp/initialize", "/mcp/tools/list", "/mcp/tools/call"):
            return "POST, OPTIONS"
        return "GET, POST, OPTIONS"

    # ===== Start the HTTP server =====

    def start(self) -> None:
        """Start the HTTP server (blocking). Pure stdlib http.server."""
        srv = self

        class _Handler(http.server.BaseHTTPRequestHandler):
            server_version = "ALBRA-MCP-HTTP/2.3"

            def _read_body(self) -> bytes:
                length = int(self.headers.get("Content-Length", 0) or 0)
                if length <= 0:
                    return b""
                return self.rfile.read(length)

            def _headers_dict(self) -> dict[str, str]:
                return {k: v for k, v in self.headers.items()}

            def _write_response(self, status: int, body: bytes, headers: dict[str, str]) -> None:
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def do_OPTIONS(self) -> None:  # noqa: N802
                status, body, headers = srv._handle_http_request(
                    "OPTIONS", self.path, b"", self._headers_dict()
                )
                self._write_response(status, body, headers)

            def do_GET(self) -> None:  # noqa: N802
                status, body, headers = srv._handle_http_request(
                    "GET", self.path, b"", self._headers_dict()
                )
                self._write_response(status, body, headers)

            def do_POST(self) -> None:  # noqa: N802
                status, body, headers = srv._handle_http_request(
                    "POST", self.path, self._read_body(), self._headers_dict()
                )
                self._write_response(status, body, headers)

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                srv.log.info("mcp.http.request", line=format % args)

        httpd = http.server.ThreadingHTTPServer((self.host, self.port), _Handler)
        httpd.daemon_threads = True
        self.log.info(
            "mcp.http.start",
            host=self.host,
            port=self.port,
            oauth=self.oauth_required,
            tools=len(self.mcp.list_tools()),
        )
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            self.log.info("mcp.http.stop")
        finally:
            httpd.server_close()


# Singleton server
_server: McpServer | None = None


def _redirect_logging_to_stderr() -> None:
    """Reapunta los StreamHandler de stdout a stderr.

    CRÍTICO para stdio mode: stdout es el canal exclusivo de JSON-RPC.
    Cualquier log que vaya a stdout corrompería el protocolo.
    Idempotente: safe llamar múltiples veces.
    """
    import logging
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and handler.stream is sys.stdout:
            handler.stream = sys.stderr


def get_mcp_server() -> McpServer:
    """Devuelve (y cachea) el singleton McpServer."""
    global _server
    if _server is None:
        _server = McpServer()
    return _server


def main() -> None:
    """CLI entrypoint: `python -m albra.mcp.server` runs stdio server."""
    # CRÍTICO: configurar logging a stdout y LUEGO redirigir a stderr,
    # antes de instanciar el server (que emite 10 logs mcp.tool.registered
    # en __init__). stdout es el canal exclusivo de JSON-RPC.
    from albra.observability.logger import setup_logging
    setup_logging()
    _redirect_logging_to_stderr()
    server = get_mcp_server()
    server.run_stdio()


def main_http() -> None:
    """CLI entrypoint: `python -m albra.mcp.server [--http|--no-auth|--port|--host]`.

    Defaults to stdio mode (legacy). With `--http` starts the HTTP transport
    + OAuth scaffold (V2.3-D). With `--no-auth` disables bearer validation
    (dev only — do NOT use in production).
    """
    import argparse

    from albra.observability.logger import setup_logging
    setup_logging()
    parser = argparse.ArgumentParser(
        prog="albra.mcp.server",
        description="ALBRA MCP server (stdio by default, HTTP with --http)",
    )
    parser.add_argument(
        "--http", action="store_true",
        help="Start HTTP server (default: stdio JSON-RPC 2.0)",
    )
    parser.add_argument(
        "--port", type=int, default=8765,
        help="HTTP listen port (default: 8765)",
    )
    parser.add_argument(
        "--host", default="0.0.0.0",
        help="HTTP listen host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--no-auth", action="store_true",
        help="Disable OAuth bearer check (DEV ONLY — never use in prod)",
    )
    args = parser.parse_args()
    if args.http:
        # HTTP mode: stdout is NOT the JSON-RPC channel, so logging stays normal.
        server = McpHttpServer(
            host=args.host,
            port=args.port,
            oauth_required=not args.no_auth,
        )
        server.start()
    else:
        # stdio mode: stdout is the JSON-RPC channel, redirect logs to stderr.
        _redirect_logging_to_stderr()
        get_mcp_server().run_stdio()


if __name__ == "__main__":
    main_http()
