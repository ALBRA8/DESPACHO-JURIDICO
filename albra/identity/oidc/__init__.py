"""V6.0 OIDC/OAuth 2.0 identity layer for ALBRA.

Provider-neutral abstraction over an OIDC/OAuth 2.0 Identity Provider.

Pipeline:

    Bearer access token (JWT)
        ↓ albra.identity.oidc.validator.JWTValidator
    cryptographic signature (RS256/384/512) via JWKS
        ↓ albra.identity.oidc.jwks.JwksResolver
    issuer / audience / exp / nbf / kid verified
        ↓ albra.identity.oidc.identity.Identity
    stable logical identity = (issuer, sub)
        ↓ albra.identity.oidc.tenant_map.TenantResolver
    authorized tenant (server-side trusted mapping, NOT client-supplied)
        ↓ albra.identity.oidc.role_map.RoleResolver
    ALBRA role (paralegal / abogado / socio / cliente / admin)
        ↓ albra.identity.oidc.context.build_auth_context_from_oidc
    AuthContext with auth_method="oidc"

The MCP HTTP route consumes this AuthContext via the existing
``validate_bearer_token(mode="production")`` entry point. Dev/test
modes are unchanged (preserves V5.2 behavior).

Reference provider documented: Auth0. Architecture is provider-neutral;
swapping to Keycloak or any OIDC-compatible IdP requires only changing
the env vars (OIDC_ISSUER, OIDC_AUDIENCE, OIDC_JWKS_URL).
"""
from __future__ import annotations

from albra.identity.oidc.audit_events import AuthAuditEvent, log_auth_event
from albra.identity.oidc.config import OIDCConfig, OIDCConfigError
from albra.identity.oidc.context import build_auth_context_from_oidc
from albra.identity.oidc.identity import Identity
from albra.identity.oidc.jwks import JwksError, JwksResolver
from albra.identity.oidc.pipeline import OIDCPipeline
from albra.identity.oidc.role_map import (
    RoleMapping,
    RoleResolutionError,
    RoleResolver,
)
from albra.identity.oidc.tenant_map import (
    TenantMapping,
    TenantResolutionError,
    TenantResolver,
)
from albra.identity.oidc.validator import (
    JWTValidator,
    TokenValidationError,
    VerifiedToken,
)

__all__ = [
    "OIDCConfig",
    "OIDCConfigError",
    "OIDCPipeline",
    "Identity",
    "JwksResolver",
    "JwksError",
    "JWTValidator",
    "TokenValidationError",
    "VerifiedToken",
    "TenantResolver",
    "TenantResolutionError",
    "TenantMapping",
    "RoleResolver",
    "RoleResolutionError",
    "RoleMapping",
    "build_auth_context_from_oidc",
    "AuthAuditEvent",
    "log_auth_event",
]
