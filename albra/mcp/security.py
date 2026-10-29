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

    V6.0: extended with optional ``issuer``, ``subject``, ``email``,
    and ``display_name`` fields. These default to empty strings for
    backward compat with dev/test contexts. The OIDC pipeline sets
    them on production contexts for audit visibility.

    The ``identity`` field is the SECURITY identity — for OIDC, it's
    the SHA-256(issuer||subject) stable opaque ID, NOT the raw ``sub``
    (which is provider-scoped). For dev/test, it's a stable label.
    """
    identity: str  # user_id, "anonymous", "dev", "test", or stable_id
    role: str  # paralegal, abogado, socio, cliente, admin
    permissions: set[str] = field(default_factory=set)
    auth_method: str = "none"  # bearer, api_key, dev, test, none, oidc
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    tenant_id: str = "default"
    # V6.0 OIDC fields (default empty for backward compat with dev/test).
    issuer: str = ""
    subject: str = ""
    email: str = ""
    display_name: str = ""

    def has_permission(self, perm: str) -> bool:
        return perm in self.permissions or "admin.*" in self.permissions

    def as_dict(self) -> dict[str, Any]:
        d = {
            "identity": self.identity,
            "role": self.role,
            "permissions": sorted(self.permissions),
            "auth_method": self.auth_method,
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
        }
        # V6.0: include OIDC fields when set. Empty strings are
        # omitted to keep dev/test contexts unchanged in audit output.
        if self.issuer:
            d["issuer"] = self.issuer
        if self.subject:
            d["subject"] = self.subject
        if self.email:
            d["email"] = self.email
        if self.display_name:
            d["display_name"] = self.display_name
        return d


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
    oidc_pipeline: Any = None,
    request_id: str | None = None,
) -> AuthContext | None:
    """Validate a bearer token and return AuthContext.

    Args:
        token: The bearer token string (without "Bearer " prefix).
        valid_tokens: Set of valid tokens (for TEST mode). None = accept any non-empty.
        mode: "dev" (accept any), "test" (check valid_tokens),
            "production" (OIDC validation — see below).
        oidc_pipeline: Optional OIDCPipeline instance for production
            mode. If None and mode="production", the pipeline is
            constructed lazily from env vars. If OIDC is not enabled
            in env, production returns None for every token (preserves
            V5.2 fail-closed behavior).
        request_id: Optional correlation ID. Auto-generated if absent.

    Returns:
        AuthContext if valid, None if invalid.

    V6.0 PRODUCTION BEHAVIOR:
        - If OIDC is disabled (OIDC_ENABLED != true) → None for every
          token (V5.2 fail-closed preserved).
        - If OIDC is enabled but config is invalid → None (fail-closed).
        - If OIDC is enabled and config is valid → JWT validator runs:
            * Token malformed → None.
            * Signature invalid → None.
            * Issuer/audience/exp/nbf/kid failure → None.
            * Identity verified but no tenant mapping → None.
            * Identity verified but role claim untrusted → None.
            * Everything verified → AuthContext with auth_method="oidc".

        PRODUCTION NEVER falls back to DEV. A single failure → None.
    """
    if not token:
        return None

    if mode == "production":
        # V6.0: real OIDC validation.
        return _validate_production_bearer(token, oidc_pipeline, request_id)

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


def _validate_production_bearer(
    token: str,
    oidc_pipeline: Any = None,
    request_id: str | None = None,
) -> AuthContext | None:
    """V6.0 production bearer validation via OIDC.

    Returns None on ANY failure (fail-closed). Returns an OIDC
    AuthContext only when the entire pipeline succeeds:
    JWT signature → iss → aud → exp → nbf → kid → identity →
    tenant → role → AuthContext.
    """
    import uuid as _uuid
    rid = request_id or _uuid.uuid4().hex[:16]

    try:
        from albra.identity.oidc import (
            OIDCConfig,
            OIDCConfigError,
            RoleResolutionError,
            TenantResolutionError,
            TokenValidationError,
        )
        from albra.identity.oidc.audit_events import AuthAuditEvent, log_auth_event
        from albra.identity.oidc.context import build_auth_context_from_oidc
        from albra.identity.oidc.identity import build_identity_from_verified_token
        from albra.identity.oidc.role_map import RoleMapping, RoleResolver
        from albra.identity.oidc.tenant_map import TenantMapping, TenantResolver
        from albra.identity.oidc.validator import JWTValidator
    except ImportError:
        # PyJWT/cryptography not installed → fail-closed.
        # Don't log the import error detail (could leak deps).
        return None

    # 1. Load OIDC config. If disabled or invalid → fail-closed.
    try:
        if oidc_pipeline is not None and hasattr(oidc_pipeline, "config"):
            config = oidc_pipeline.config
        else:
            config = OIDCConfig.from_env()
    except OIDCConfigError:
        # Misconfigured production → fail-closed. Don't expose details.
        log_auth_event(AuthAuditEvent(
            event="oidc.auth.failure",
            request_id=rid,
            failure_category="misconfigured",
        ))
        return None

    if not config.is_production_ready():
        # OIDC not enabled or missing required fields → fail-closed.
        # This preserves the V5.2 behavior: production without a real
        # provider denies every token.
        return None

    # 2. Validate the JWT (signature, iss, aud, exp, nbf, kid, alg).
    try:
        if oidc_pipeline is not None and hasattr(oidc_pipeline, "validator"):
            validator = oidc_pipeline.validator
        else:
            validator = JWTValidator(config)
        verified = validator.validate(token)
    except TokenValidationError as e:
        # Map to a safe failure category for audit.
        msg = str(e).lower()
        if "expired" in msg:
            category = "expired"
        elif "invalid issuer" in msg or "issuer mismatch" in msg:
            category = "invalid_issuer"
        elif "invalid audience" in msg or "audience" in msg:
            category = "invalid_audience"
        elif "not yet valid" in msg or "nbf" in msg:
            category = "not_yet_valid"
        elif "unknown kid" in msg or "jwks" in msg:
            category = "unknown_kid"
        elif "algorithm" in msg:
            category = "invalid_algorithm"
        elif "malformed" in msg:
            category = "malformed"
        elif "signature" in msg:
            category = "invalid_signature"
        else:
            category = "other"
        log_auth_event(AuthAuditEvent(
            event="oidc.auth.failure",
            request_id=rid,
            failure_category=category,
        ))
        return None

    # 3. Build stable identity.
    identity = build_identity_from_verified_token(verified)

    # 4. Resolve tenant (server-side trusted mapping).
    try:
        if oidc_pipeline is not None and hasattr(oidc_pipeline, "tenant_resolver"):
            tenant_resolver = oidc_pipeline.tenant_resolver
        else:
            tenant_resolver = TenantResolver(TenantMapping.from_env())
        tenant_id = tenant_resolver.resolve(identity)
    except TenantResolutionError as e:
        msg = str(e).lower()
        if "no tenant map" in msg:
            category = "tenant_no_map"
        else:
            category = "tenant_unmapped"
        log_auth_event(AuthAuditEvent(
            event="oidc.auth.failure",
            request_id=rid,
            issuer=identity.issuer,
            stable_id_prefix=identity.stable_id[:8],
            failure_category=category,
        ))
        return None

    # 5. Resolve role (trusted namespace claim).
    try:
        if oidc_pipeline is not None and hasattr(oidc_pipeline, "role_resolver"):
            role_resolver = oidc_pipeline.role_resolver
        else:
            role_resolver = RoleResolver(RoleMapping.from_env())
        role = role_resolver.resolve(identity)
    except RoleResolutionError as e:
        msg = str(e).lower()
        if "namespace" in msg:
            category = "role_no_namespace"
        elif "not in the allowed" in msg:
            category = "role_not_allowed"
        else:
            category = "role_other"
        log_auth_event(AuthAuditEvent(
            event="oidc.auth.failure",
            request_id=rid,
            issuer=identity.issuer,
            stable_id_prefix=identity.stable_id[:8],
            failure_category=category,
        ))
        return None

    # 6. Build AuthContext.
    ctx = build_auth_context_from_oidc(
        identity=identity,
        tenant_id=tenant_id,
        role=role,
        request_id=rid,
    )
    log_auth_event(AuthAuditEvent(
        event="oidc.auth.success",
        request_id=rid,
        issuer=identity.issuer,
        stable_id_prefix=identity.stable_id[:8],
        role=role,
        tenant_id=tenant_id,
    ))
    return ctx
