"""V6.0 OIDC audit events.

Structured audit events for the OIDC auth pipeline. These are SAFE to
log — they never contain the bearer token, raw claims, or signature.

Categories:
    - oidc.auth.success — token validated + identity + tenant + role resolved.
    - oidc.auth.failure — token rejected at any stage.
    - oidc.invalid.issuer — issuer mismatch.
    - oidc.invalid.audience — audience mismatch.
    - oidc.expired — exp in the past (beyond skew).
    - oidc.not_yet_valid — nbf in the future (beyond skew).
    - oidc.unknown_kid — kid not in JWKS after refresh.
    - oidc.jwks.fetch_failed — JWKS endpoint unreachable.
    - oidc.tenant.denied_no_map — no tenant map configured.
    - oidc.tenant.denied_unmapped — identity not in tenant map.
    - oidc.role.denied_no_namespace — no trusted namespace claim.
    - oidc.role.denied_role_not_allowed — role value not in allowed set.
    - oidc.rbac.denied — RBAC denied the requested tool.

Each event includes:
    - request_id (correlation)
    - issuer (when known)
    - failure_category (when failure)
    - stable_id_prefix (first 8 chars only — opaque to attackers)

NEVER logged:
    - bearer token (full or partial)
    - Authorization header
    - JWT signature
    - refresh tokens
    - email (unless explicitly enabled for observability)
    - raw claims wholesale
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from albra.observability.logger import get_logger

_logger = get_logger("albra.identity.oidc.audit")


@dataclass
class AuthAuditEvent:
    """A structured OIDC auth audit event.

    The fields here are the ONLY safe-to-log information about an OIDC
    auth attempt. NEVER extend this to include the bearer token,
    signature, or raw claims.
    """
    event: str  # e.g. "oidc.auth.success", "oidc.expired"
    request_id: str
    issuer: str = ""
    stable_id_prefix: str = ""  # first 8 chars only
    failure_category: str = ""  # "expired", "invalid_issuer", etc.
    role: str = ""
    tenant_id: str = ""
    tool_name: str = ""


def log_auth_event(event: AuthAuditEvent, **extra: Any) -> None:
    """Log an OIDC audit event. Extra kwargs are passed to structlog.

    NEVER pass the bearer token, Authorization header, JWT signature,
    or raw claims as ``extra``. The caller is responsible for not
    including sensitive data.
    """
    payload: dict[str, Any] = {
        "event": event.event,
        "request_id": event.request_id,
    }
    if event.issuer:
        payload["issuer"] = event.issuer
    if event.stable_id_prefix:
        payload["stable_id_prefix"] = event.stable_id_prefix
    if event.failure_category:
        payload["failure_category"] = event.failure_category
    if event.role:
        payload["role"] = event.role
    if event.tenant_id:
        payload["tenant_id"] = event.tenant_id
    if event.tool_name:
        payload["tool_name"] = event.tool_name
    payload.update(extra)
    _logger.info("oidc.audit", **payload)
