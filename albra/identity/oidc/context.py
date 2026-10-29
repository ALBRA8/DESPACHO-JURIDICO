"""V6.0 AuthContext builder for OIDC-verified identities.

Bridges the OIDC pipeline output (Identity + tenant + role) into the
existing :class:`albra.mcp.security.AuthContext`. The resulting
AuthContext is the SINGLE source of identity for the rest of the MCP
chain — RBAC, ExecutionGuard, MatterStore, audit.

The AuthContext is extended (V6.0) with optional ``issuer`` and
``subject`` fields. These default to empty strings for backward
compatibility with dev/test contexts.
"""
from __future__ import annotations

from albra.identity.oidc.identity import Identity
from albra.mcp.security import (
    AuthContext,
    create_auth_context,
)


def build_auth_context_from_oidc(
    *,
    identity: Identity,
    tenant_id: str,
    role: str,
    request_id: str | None = None,
) -> AuthContext:
    """Build an AuthContext from a verified OIDC identity.

    Args:
        identity: Verified Identity (issuer + sub).
        tenant_id: The authorized tenant (resolved server-side).
        role: The ALBRA role (resolved from trusted namespace claim).
        request_id: Optional request ID; auto-generated if absent.

    Returns:
        AuthContext with auth_method="oidc", issuer, subject, tenant_id,
        role, and the role's permissions from ROLE_PERMISSIONS.

    Raises:
        ValueError: if role is not in ROLE_PERMISSIONS.
    """
    ctx = create_auth_context(
        identity=identity.stable_id,  # use stable opaque ID as identity
        role=role,
        auth_method="oidc",
        tenant_id=tenant_id,
        request_id=request_id,
    )
    # V6.0: extend with issuer + subject for audit visibility.
    ctx.issuer = identity.issuer
    ctx.subject = identity.subject
    # Stash a few useful metadata fields. These are NOT used by RBAC;
    # they're for audit logging and observability.
    ctx.email = identity.email
    ctx.display_name = identity.name
    return ctx


def extend_auth_context_fields() -> None:
    """Register the V6.0 optional fields on AuthContext if not present.

    This is called at import time of this module. It's idempotent —
    calling it multiple times is safe. The fields default to empty
    strings for backward compat with dev/test contexts created via
    create_dev_context / create_test_context.

    We add fields dynamically rather than modifying the AuthContext
    dataclass definition in security.py because the latter would
    break backward compat with existing serialized contexts. Instead
    we use setattr with default attributes.

    Wait — actually the cleanest approach is to subclass AuthContext.
    But the existing pipeline passes AuthContext around, and the OIDC
    layer needs to inject issuer/subject. The minimal-churn approach
    is to ADD the fields to AuthContext itself with default "" values,
    which preserves backward compat. That's what we do via the patch
    below.

    Actually, the cleanest is to modify security.AuthContext directly
    to add issuer/subject/email/display_name fields with defaults.
    That's a clean V6.0 extension, not a hack. We do that in
    security.py (see the V6.0 edits there). This function is a no-op
    kept for future hooks.
    """
    # No-op: the fields are added directly to AuthContext in security.py.
    return None
