"""
MCP SECURITY LAYER — AuthContext, RBAC, ExecutionGuard wiring, audit trail.

Separates concerns:
  Transport (HTTP/stdio)
    → Authentication (bearer/api_key/dev/none)
      → Authorization (RBAC permission check)
        → ExecutionGuard (fail-closed policy)
          → Tool Registry (execute handler)
            → Audit (record event)
              → Response

V2.6 HARDENING: closes the "RBAC/ExecutionGuard/audit trail = NOT VERIFIED" gap.

Deny-by-default: if no AuthContext is provided and security is enabled → DENY.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from albra.observability.logger import get_logger


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash_dict(d: dict[str, Any]) -> str:
    """SHA-256 of a dict (sorted JSON). Used for input/output audit hashing."""
    return hashlib.sha256(
        json.dumps(d, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


# ===== AuthContext =====

@dataclass
class AuthContext:
    """Identity + permissions for a tool call request.

    Created by the Authentication layer from a bearer token, API key,
    or dev/test context. Passed through the call chain.
    """
    identity: str  # user_id, "anonymous", "dev", "test"
    role: str  # paralegal, abogado, socio, cliente, admin
    permissions: set[str] = field(default_factory=set)
    auth_method: str = "none"  # bearer, api_key, dev, test, none
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    tenant_id: str = "default"

    def has_permission(self, perm: str) -> bool:
        return perm in self.permissions or "admin.*" in self.permissions

    def as_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "role": self.role,
            "permissions": sorted(self.permissions),
            "auth_method": self.auth_method,
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
        }


# ===== Tool Permission Map =====

TOOL_PERMISSIONS: dict[str, str] = {
    "audit_citation": "tools.invoke",
    "search_corpus": "tools.invoke",
    "verify_deadline": "tools.invoke",
    "analyze_treatment": "tools.invoke",
    "advance_matter": "matters.advance",
    "verify_audit_chain": "audit.read",
    "list_matters": "matters.read",
    "list_agents": "agents.read",
    "get_playbook": "playbooks.read",
    "run_eval_suite": "eval.run",
}

# ===== RBAC: role → permissions =====

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "paralegal": {"tools.invoke", "matters.read", "agents.read", "playbooks.read", "audit.read"},
    "abogado": {
        "tools.invoke", "matters.read", "matters.advance",
        "agents.read", "playbooks.read", "audit.read",
    },
    "socio": {
        "tools.invoke", "matters.read", "matters.advance",
        "agents.read", "playbooks.read", "audit.read", "eval.run",
    },
    "cliente": {"tools.invoke", "matters.read"},
    "admin": {"admin.*"},  # wildcard — all permissions
    "anonymous": set(),  # deny-by-default
}

# ===== Auth modes =====

AUTH_MODES = ("dev", "test", "production")


def create_auth_context(
    *,
    identity: str,
    role: str,
    auth_method: str = "dev",
    tenant_id: str = "default",
    request_id: str | None = None,
) -> AuthContext:
    """Create an AuthContext with permissions derived from role."""
    if role not in ROLE_PERMISSIONS:
        raise ValueError(f"Unknown role: {role!r}. Valid: {sorted(ROLE_PERMISSIONS)}")
    perms = ROLE_PERMISSIONS[role].copy()
    return AuthContext(
        identity=identity,
        role=role,
        permissions=perms,
        auth_method=auth_method,
        request_id=request_id or uuid.uuid4().hex[:16],
        tenant_id=tenant_id,
    )


def create_dev_context(role: str = "admin") -> AuthContext:
    """DEV auth: no token required, full permissions for local development."""
    return create_auth_context(
        identity="dev-user",
        role=role,
        auth_method="dev",
    )


def create_test_context(role: str = "abogado") -> AuthContext:
    """TEST auth: for integration tests, with specified role."""
    return create_auth_context(
        identity="test-user",
        role=role,
        auth_method="test",
    )


def create_anonymous_context() -> AuthContext:
    """Anonymous: no permissions (deny-by-default)."""
    return AuthContext(
        identity="anonymous",
        role="anonymous",
        permissions=set(),
        auth_method="none",
    )


# ===== Audit Entry for MCP tool calls =====

@dataclass
class McpAuditEntry:
    """Audit entry for a single MCP tool call."""
    timestamp: str
    request_id: str
    actor: str  # identity from AuthContext
    role: str
    auth_method: str
    tool_name: str
    action: str  # "mcp.tool.call"
    authorization_result: str  # "ALLOWED" | "DENIED"
    denial_reason: str  # "" if allowed
    input_hash: str  # SHA-256 of args
    output_hash: str  # SHA-256 of result ("" if denied)
    matter_id: str  # "" if not applicable
    correlation_id: str  # same as request_id
    result_status: str  # "success" | "error" | "denied"
    error: str  # "" if no error
    latency_ms: float
    environment: str  # "dev" | "test" | "production"

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "request_id": self.request_id,
            "actor": self.actor,
            "role": self.role,
            "auth_method": self.auth_method,
            "tool_name": self.tool_name,
            "action": self.action,
            "authorization_result": self.authorization_result,
            "denial_reason": self.denial_reason,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "matter_id": self.matter_id,
            "correlation_id": self.correlation_id,
            "result_status": self.result_status,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "environment": self.environment,
        }


# ===== MCP Audit Log (JSONL append-only) =====

class McpAuditLog:
    """JSONL append-only audit log for MCP tool calls.

    NOT hash-chained (that's MatterAudit's job for matter-scoped events).
    This is the MCP-level audit: every tool call, allowed or denied.
    """

    def __init__(self, log_path: str = "./data/mcp_audit.jsonl") -> None:
        from pathlib import Path
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.touch(exist_ok=True)
        self._log = get_logger("albra.mcp.audit")

    def record(self, entry: McpAuditEntry) -> None:
        """Append an audit entry."""
        line = json.dumps(entry.as_dict(), ensure_ascii=False, default=str)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        self._log.info(
            "mcp.audit.record",
            request_id=entry.request_id,
            tool=entry.tool_name,
            result=entry.authorization_result,
            actor=entry.actor,
        )

    def read(self, *, limit: int = 100, tool_name: str | None = None) -> list[dict[str, Any]]:
        """Read recent audit entries."""
        entries: list[dict[str, Any]] = []
        with open(self.log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    if tool_name and e.get("tool_name") != tool_name:
                        continue
                    entries.append(e)
                except json.JSONDecodeError:
                    continue
        return entries[-limit:] if limit else entries

    def count(self) -> int:
        with open(self.log_path, encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())


# ===== Security check helpers =====

def check_tool_permission(
    tool_name: str,
    auth_ctx: AuthContext,
) -> tuple[bool, str]:
    """Check if auth_ctx has permission to invoke tool_name.

    Tools not in TOOL_PERMISSIONS default to "tools.invoke" (any authenticated user).
    This allows custom tools to work while still requiring authentication.

    Returns:
        (allowed, reason) — reason is "" if allowed, explanation if denied.
    """
    required_perm = TOOL_PERMISSIONS.get(tool_name, "tools.invoke")

    if auth_ctx.has_permission(required_perm):
        return True, ""

    return False, (
        f"Role {auth_ctx.role!r} lacks permission {required_perm!r} "
        f"required for tool {tool_name!r}"
    )


def validate_bearer_token(
    token: str,
    *,
    valid_tokens: set[str] | None = None,
    mode: str = "dev",
) -> AuthContext | None:
    """Validate a bearer token and return AuthContext.

    Args:
        token: The bearer token string (without "Bearer " prefix).
        valid_tokens: Set of valid tokens (for TEST mode). None = accept any non-empty.
        mode: "dev" (accept any), "test" (check valid_tokens), "production" (always None — needs real OAuth).

    Returns:
        AuthContext if valid, None if invalid.
    """
    if not token:
        return None

    if mode == "production":
        # PRODUCTION: requires real OAuth provider — NOT implemented yet.
        # V2.6+: integrate Auth0/Keycloak/GitHub OAuth App.
        return None

    if mode == "test":
        if valid_tokens and token not in valid_tokens:
            return None
        # Test tokens map to specific roles
        if token.startswith("test-admin-"):
            return create_test_context(role="admin")
        elif token.startswith("test-socio-"):
            return create_test_context(role="socio")
        elif token.startswith("test-abogado-"):
            return create_test_context(role="abogado")
        elif token.startswith("test-paralegal-"):
            return create_test_context(role="paralegal")
        elif token.startswith("test-client-"):
            return create_test_context(role="cliente")
        return create_test_context(role="abogado")  # default test role

    # DEV mode: accept any non-empty token
    if token.startswith("dev-admin-"):
        return create_dev_context(role="admin")
    elif token.startswith("dev-socio-"):
        return create_dev_context(role="socio")
    return create_dev_context(role="admin")  # default dev role
