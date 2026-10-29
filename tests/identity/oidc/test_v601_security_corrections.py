"""V6.0.1 OIDC security corrections — functional tests.

Three surgical corrections to V6.0 OIDC, each verified by real
functional tests (no string inspection of source code):

  CORRECTION A — Role namespace fail-closed:
    - empty OIDC_ROLE_NAMESPACE → DENY at config (RoleMapping.from_env)
    - empty namespace + bare 'role' claim → DENY at resolver (defense
      in depth, even if config is bypassed)
    - explicit namespace (e.g. https://albra8.com/claims) → ACCEPT

  CORRECTION B — Audience ≠ client_id:
    - token with aud=OIDC_AUDIENCE → ACCEPT
    - token with aud=OIDC_CLIENT_ID (and not OIDC_AUDIENCE) → DENY
    - token with aud=[OIDC_CLIENT_ID, OIDC_AUDIENCE] → ACCEPT (audience
      present, client_id is harmless metadata in the array)

  CORRECTION C — OAuth scaffold disabled in production:
    - scaffold authorize/token/discovery endpoints → 200 in dev/test
    - scaffold authorize/token/discovery endpoints → 404 in production
    - a fake scaffold token cannot authenticate in production (existing
      V6.0 behavior, re-verified for V6.0.1)
"""
from __future__ import annotations

import json
import time

import pytest

from albra.identity.oidc import (
    OIDCConfig,
    OIDCPipeline,
    RoleResolutionError,
    TokenValidationError,
)
from albra.identity.oidc.identity import Identity
from albra.identity.oidc.jwks import JwksResolver
from albra.identity.oidc.role_map import RoleMapping, RoleResolver
from albra.identity.oidc.tenant_map import TenantMapping, TenantResolver
from albra.identity.oidc.validator import JWTValidator
from albra.mcp.security import validate_bearer_token
from albra.mcp.server import McpHttpServer, McpServer
from tests.identity.oidc.conftest import (
    TEST_AUDIENCE,
    TEST_CLIENT_ID,
    TEST_ISSUER,
    TestKeySet,
    compute_stable_id,
    make_jwt,
    make_tenant_map_for_identities,
)

# ===== Shared test setup =====

TEST_SUB = "sub-alice-admin"
TEST_TENANT = "tenant-A"


def _set_oidc_env(
    monkeypatch,
    *,
    role_namespace: str = "https://albra.dev",
    role_claim: str = "role",
    audience: str = TEST_AUDIENCE,
    client_id: str = TEST_CLIENT_ID,
    issuer: str = TEST_ISSUER,
    tenant_map: dict | None = None,
):
    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_ISSUER", issuer)
    monkeypatch.setenv("OIDC_AUDIENCE", audience)
    monkeypatch.setenv("OIDC_CLIENT_ID", client_id)
    monkeypatch.setenv("OIDC_JWKS_URL", "https://test-idp.albra.dev/.well-known/jwks.json")
    # V6.0.1: only set the namespace if non-empty (empty triggers a
    # different test scenario where from_env should reject).
    if role_namespace is not None:
        monkeypatch.setenv("OIDC_ROLE_NAMESPACE", role_namespace)
    else:
        monkeypatch.delenv("OIDC_ROLE_NAMESPACE", raising=False)
    monkeypatch.setenv("OIDC_ROLE_CLAIM", role_claim)
    if tenant_map is not None:
        monkeypatch.setenv("OIDC_TENANT_MAP", json.dumps(tenant_map))
    else:
        monkeypatch.delenv("OIDC_TENANT_MAP", raising=False)


def _build_pipeline(test_keyset, monkeypatch, **env_kwargs):
    """Build a wired OIDCPipeline with the given env."""
    tenant_map = env_kwargs.pop("tenant_map", None) or make_tenant_map_for_identities([
        (TEST_ISSUER, TEST_SUB, TEST_TENANT),
    ])
    _set_oidc_env(monkeypatch, tenant_map=tenant_map, **env_kwargs)
    config = OIDCConfig.from_env()
    jwks = JwksResolver(config, http_get=test_keyset.http_get())
    validator = JWTValidator(config, jwks_resolver=jwks)
    tenant_resolver = TenantResolver(TenantMapping.from_env())
    role_resolver = RoleResolver(RoleMapping.from_env())
    return OIDCPipeline(
        config=config, validator=validator,
        tenant_resolver=tenant_resolver, role_resolver=role_resolver,
    )


def _make_token(
    key, subject: str, role: str, *,
    audience=TEST_AUDIENCE, extra_claims=None,
) -> str:
    """Make a JWT with the role claim in the trusted namespace."""
    claims = {"https://albra.dev": {"role": role}}
    if extra_claims:
        claims.update(extra_claims)
    return make_jwt(
        key=key, subject=subject, audience=audience, extra_claims=claims,
    )


# =========================================================================
# CORRECTION A — Role namespace fail-closed
# =========================================================================

# ----- A1. Empty OIDC_ROLE_NAMESPACE → DENY at config -----

def test_a1_empty_namespace_rejected_by_from_env(monkeypatch):
    """RoleMapping.from_env() raises RoleResolutionError when
    OIDC_ROLE_NAMESPACE is explicitly set to empty.

    V6.0.1 Correction A: bare role claims are never trusted. An empty
    namespace would enable claims["role"] trust, which contradicts the
    V6.0 contract.
    """
    _set_oidc_env(monkeypatch, role_namespace="")
    with pytest.raises(RoleResolutionError, match="OIDC_ROLE_NAMESPACE is empty"):
        RoleMapping.from_env()


def test_a1b_whitespace_namespace_rejected_by_from_env(monkeypatch):
    """A whitespace-only OIDC_ROLE_NAMESPACE is also rejected
    (treated as empty after strip).
    """
    _set_oidc_env(monkeypatch, role_namespace="   ")
    with pytest.raises(RoleResolutionError, match="empty"):
        RoleMapping.from_env()


# ----- A2. Empty namespace + bare role claim → DENY at resolver -----

def test_a2_resolver_rejects_bare_role_with_empty_namespace(monkeypatch):
    """V6.0.1 defense in depth: even if a misconfigured RoleMapping
    with an empty namespace reaches the resolver (bypassing from_env),
    the resolver independently raises RoleResolutionError.

    The token here has a BARE 'role' claim. The V6.0 code would have
    trusted it. The V6.0.1 resolver MUST NOT.
    """
    # Construct a RoleMapping directly with empty namespace (bypass
    # from_env's validation). This simulates a future code path that
    # accidentally constructs RoleMapping without going through from_env.
    bad_mapping = RoleMapping(namespace="", claim_name="role")
    resolver = RoleResolver(bad_mapping)
    identity = Identity(
        issuer=TEST_ISSUER,
        subject=TEST_SUB,
        raw_claims={"role": "admin"},  # bare unnamespaced claim
    )
    with pytest.raises(RoleResolutionError, match="OIDC_ROLE_NAMESPACE is empty"):
        resolver.resolve(identity)


def test_a2b_resolver_rejects_bare_role_with_whitespace_namespace(monkeypatch):
    """Whitespace namespace is also rejected by the resolver
    (defense in depth).
    """
    bad_mapping = RoleMapping(namespace="  ", claim_name="role")
    resolver = RoleResolver(bad_mapping)
    identity = Identity(
        issuer=TEST_ISSUER, subject=TEST_SUB,
        raw_claims={"role": "admin"},
    )
    with pytest.raises(RoleResolutionError, match="empty"):
        resolver.resolve(identity)


# ----- A3. Empty namespace + bare role token → production DENY -----

def test_a3_empty_namespace_production_bare_role_denied(
    test_keyset, monkeypatch,
):
    """End-to-end: with OIDC_ROLE_NAMESPACE="" set in env, the production
    validate_bearer_token pipeline fails closed. A token with a bare
    'role: admin' claim MUST NOT authenticate.
    """
    _set_oidc_env(monkeypatch, role_namespace="")
    # RoleMapping.from_env() will raise; the validate_bearer_token
    # pipeline catches this and returns None (fail-closed).
    # Build a token with a BARE role claim.
    token = make_jwt(
        key=test_keyset.keys[0],
        subject=TEST_SUB,
        extra_claims={"role": "admin"},  # bare unnamespaced
    )
    ctx = validate_bearer_token(token, mode="production")
    assert ctx is None, (
        "Production must NOT authenticate a bare 'role' claim, even when "
        "OIDC_ROLE_NAMESPACE is set to empty."
    )


# ----- A4. Bare role claim → NEVER trusted, regardless of namespace -----

def test_a4_bare_role_claim_never_trusted(test_keyset, monkeypatch):
    """V6.0 contract preserved: a bare 'role' claim (no namespace) is
    NEVER trusted, regardless of the OIDC_ROLE_NAMESPACE configuration.
    """
    pipeline = _build_pipeline(test_keyset, monkeypatch)
    token = make_jwt(
        key=test_keyset.keys[0],
        subject=TEST_SUB,
        extra_claims={"role": "admin"},  # bare unnamespaced
    )
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is None, "Bare role claim must never authenticate."


# ----- A5. Explicit namespace → ACCEPT (positive regression) -----

def test_a5_explicit_namespace_works(test_keyset, monkeypatch):
    """V6.0.1 does NOT break legitimate explicit namespaces. A token
    with the role claim in the trusted namespace authenticates normally.
    """
    pipeline = _build_pipeline(test_keyset, monkeypatch)
    token = _make_token(test_keyset.keys[0], TEST_SUB, "admin")
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is not None
    assert ctx.role == "admin"
    assert ctx.auth_method == "oidc"


def test_a5b_custom_namespace_https_albra8_com_claims_works(test_keyset, monkeypatch):
    """V6.0.1 explicitly allows custom namespaces like
    https://albra8.com/claims. The brief mentions this example as
    legitimate.
    """
    custom_namespace = "https://albra8.com/claims"
    _set_oidc_env(
        monkeypatch,
        role_namespace=custom_namespace,
        tenant_map=make_tenant_map_for_identities([
            (TEST_ISSUER, TEST_SUB, TEST_TENANT),
        ]),
    )
    config = OIDCConfig.from_env()
    jwks = JwksResolver(config, http_get=test_keyset.http_get())
    pipeline = OIDCPipeline(
        config=config,
        validator=JWTValidator(config, jwks_resolver=jwks),
        tenant_resolver=TenantResolver(TenantMapping.from_env()),
        role_resolver=RoleResolver(RoleMapping.from_env()),
    )
    token = make_jwt(
        key=test_keyset.keys[0],
        subject=TEST_SUB,
        extra_claims={custom_namespace: {"role": "abogado"}},
    )
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is not None
    assert ctx.role == "abogado"


# =========================================================================
# CORRECTION B — Audience ≠ client_id
# =========================================================================

# ----- B1. Token with aud=OIDC_AUDIENCE → ACCEPT -----

def test_b1_audience_equal_oidc_audience_accepted(test_keyset, monkeypatch):
    """A token whose aud is OIDC_AUDIENCE is accepted (positive baseline)."""
    pipeline = _build_pipeline(test_keyset, monkeypatch)
    token = _make_token(
        test_keyset.keys[0], TEST_SUB, "admin",
        audience=TEST_AUDIENCE,
    )
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is not None
    assert ctx.role == "admin"


# ----- B2. Token with aud=OIDC_CLIENT_ID (no OIDC_AUDIENCE) → DENY -----

def test_b2_audience_equal_client_id_only_denied(test_keyset, monkeypatch):
    """V6.0.1 Correction B: a token whose aud is ONLY OIDC_CLIENT_ID
    (the OAuth client identifier) — and NOT OIDC_AUDIENCE (the protected
    API) — is REJECTED.

    OIDC_CLIENT_ID represents "who the token was issued TO". It is NOT
    an audience authorized for this API. V6.0 mistakenly added
    client_id to the accepted audiences list. V6.0.1 fixes this.
    """
    pipeline = _build_pipeline(test_keyset, monkeypatch)
    # Token with aud = OIDC_CLIENT_ID (not OIDC_AUDIENCE).
    token = _make_token(
        test_keyset.keys[0], TEST_SUB, "admin",
        audience=TEST_CLIENT_ID,
    )
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is None, (
        "Token whose aud is only OIDC_CLIENT_ID (not OIDC_AUDIENCE) "
        "must NOT authenticate. OIDC_CLIENT_ID is not an authorized "
        "audience for this API."
    )


# ----- B3. Token with aud=[OIDC_CLIENT_ID, OIDC_AUDIENCE] → ACCEPT -----

def test_b3_audience_includes_oidc_audience_accepted(test_keyset, monkeypatch):
    """A token whose aud is a list that INCLUDES OIDC_AUDIENCE is
    accepted. The presence of OIDC_CLIENT_ID in the same list is
    harmless metadata (it just means the IdP listed both).
    """
    pipeline = _build_pipeline(test_keyset, monkeypatch)
    token = _make_token(
        test_keyset.keys[0], TEST_SUB, "admin",
        audience=[TEST_CLIENT_ID, TEST_AUDIENCE],
    )
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is not None
    assert ctx.role == "admin"


# ----- B4. Token with aud=OIDC_CLIENT_ID via HTTP → 401 -----

def test_b4_http_request_with_client_id_only_audience_401(test_keyset, monkeypatch, tmp_path):
    """End-to-end HTTP: a request with a bearer whose aud is only
    OIDC_CLIENT_ID returns 401.
    """
    pipeline = _build_pipeline(test_keyset, monkeypatch)
    monkeypatch.setenv("ALBRA_MATTER_DB_PATH", str(tmp_path / "matters.db"))
    monkeypatch.setenv("ALBRA_MATTER_DATA_DIR", str(tmp_path / "matters"))
    from albra.matters.store import MatterStore
    store = MatterStore(str(tmp_path / "matters.db"), enforce_tenant=True)
    store.create_matter(
        client="Alice", area="civil", created_by="ab1",
        tenant_id=TEST_TENANT,
    )
    mcp = McpServer(security_mode="production", matter_store=store)
    http = McpHttpServer(
        auth_mode="production", mcp_server=mcp, oidc_pipeline=pipeline,
    )

    token = _make_token(
        test_keyset.keys[0], TEST_SUB, "admin",
        audience=TEST_CLIENT_ID,  # only client_id, not OIDC_AUDIENCE
    )
    status, body, hdrs = http._handle_http_request(
        "POST", "/mcp/tools/call",
        json.dumps({"name": "list_matters", "arguments": {}}).encode(),
        {"Authorization": f"Bearer {token}"},
    )
    assert status == 401, (
        f"Token with aud=OIDC_CLIENT_ID only must be 401. Got {status}."
    )
    store.close()


# =========================================================================
# CORRECTION C — OAuth scaffold disabled in production
# =========================================================================

# ----- C1. Scaffold discovery endpoint → 200 in dev/test -----

def test_c1_scaffold_discovery_200_in_dev(monkeypatch):
    """V6.0.1: in dev mode, the OAuth scaffold discovery endpoint is
    available (preserves dev/test compatibility).
    """
    monkeypatch.setenv("ALBRA_ENVIRONMENT", "development")
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-jwt-secret-not-for-prod-32chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-admin-pass-1234")
    mcp = McpServer(security_mode="dev")
    http = McpHttpServer(auth_mode="dev", mcp_server=mcp)

    status, body, hdrs = http._handle_http_request(
        "GET", "/mcp/.well-known/oauth-authorization-server", b"", {},
    )
    assert status == 200


# ----- C2. Scaffold discovery endpoint → 404 in production -----

def test_c2_scaffold_discovery_404_in_production(monkeypatch, tmp_path):
    """V6.0.1: in production, the OAuth scaffold discovery endpoint is
    disabled and returns 404.
    """
    monkeypatch.setenv("ALBRA_ENVIRONMENT", "production")
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-jwt-secret-not-for-prod-32chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-admin-pass-1234")
    monkeypatch.setenv("ALBRA_MATTER_DB_PATH", str(tmp_path / "matters.db"))
    monkeypatch.setenv("ALBRA_MATTER_DATA_DIR", str(tmp_path / "matters"))
    mcp = McpServer(security_mode="production")
    http = McpHttpServer(auth_mode="production", mcp_server=mcp)

    status, body, hdrs = http._handle_http_request(
        "GET", "/mcp/.well-known/oauth-authorization-server", b"", {},
    )
    assert status == 404
    result = json.loads(body.decode())
    assert result["error"] == "scaffold_disabled"


# ----- C3. Scaffold authorize endpoint → 404 in production -----

def test_c3_scaffold_authorize_404_in_production(monkeypatch, tmp_path):
    """V6.0.1: in production, /mcp/oauth/authorize returns 404."""
    monkeypatch.setenv("ALBRA_ENVIRONMENT", "production")
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-jwt-secret-not-for-prod-32chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-admin-pass-1234")
    monkeypatch.setenv("ALBRA_MATTER_DB_PATH", str(tmp_path / "matters.db"))
    mcp = McpServer(security_mode="production")
    http = McpHttpServer(auth_mode="production", mcp_server=mcp)

    status, body, hdrs = http._handle_http_request(
        "GET", "/mcp/oauth/authorize?redirect_uri=x&state=y", b"", {},
    )
    assert status == 404


# ----- C4. Scaffold token endpoint → 404 in production -----

def test_c4_scaffold_token_404_in_production(monkeypatch, tmp_path):
    """V6.0.1: in production, /mcp/oauth/token returns 404 — the fake
    token minter is disabled.
    """
    monkeypatch.setenv("ALBRA_ENVIRONMENT", "production")
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-jwt-secret-not-for-prod-32chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-admin-pass-1234")
    monkeypatch.setenv("ALBRA_MATTER_DB_PATH", str(tmp_path / "matters.db"))
    mcp = McpServer(security_mode="production")
    http = McpHttpServer(auth_mode="production", mcp_server=mcp)

    # Try to mint a fake token via the scaffold flow.
    body = json.dumps({
        "grant_type": "authorization_code",
        "code": "albra-code-fake",
    }).encode()
    status, resp_body, hdrs = http._handle_http_request(
        "POST", "/mcp/oauth/token", body, {"Content-Type": "application/json"},
    )
    assert status == 404


# ----- C5. Fake scaffold token → DENY in production (end-to-end) -----

def test_c5_fake_scaffold_token_denied_in_production(monkeypatch, tmp_path, test_keyset):
    """V6.0.1 end-to-end: an attacker who somehow obtains an
    'albra-token-...' string (e.g. from a leaked dev log) cannot use
    it to authenticate in production. Even calling the protected
    /mcp/tools/call endpoint with such a token returns 401.

    This is the V6.0 contract (scaffold tokens are checked with
    `if token in self._oauth_tokens and self._auth_mode != "production"`),
    re-verified end-to-end for V6.0.1.
    """
    # Set up production mode with OIDC enabled.
    _set_oidc_env(
        monkeypatch,
        tenant_map=make_tenant_map_for_identities([
            (TEST_ISSUER, TEST_SUB, TEST_TENANT),
        ]),
    )
    monkeypatch.setenv("ALBRA_ENVIRONMENT", "production")
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-jwt-secret-not-for-prod-32chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-admin-pass-1234")
    monkeypatch.setenv("ALBRA_MATTER_DB_PATH", str(tmp_path / "matters.db"))
    monkeypatch.setenv("ALBRA_MATTER_DATA_DIR", str(tmp_path / "matters"))

    config = OIDCConfig.from_env()
    jwks = JwksResolver(config, http_get=test_keyset.http_get())
    pipeline = OIDCPipeline(
        config=config,
        validator=JWTValidator(config, jwks_resolver=jwks),
        tenant_resolver=TenantResolver(TenantMapping.from_env()),
        role_resolver=RoleResolver(RoleMapping.from_env()),
    )
    from albra.matters.store import MatterStore
    store = MatterStore(str(tmp_path / "matters.db"), enforce_tenant=True)
    mcp = McpServer(security_mode="production", matter_store=store)
    http = McpHttpServer(
        auth_mode="production", mcp_server=mcp, oidc_pipeline=pipeline,
    )

    # The fake scaffold token format. Note: we never actually minted
    # this via /mcp/oauth/token (that endpoint is disabled in prod). We
    # just craft the string an attacker might have.
    fake_token = "albra-token-" + "a" * 32

    status, body, hdrs = http._handle_http_request(
        "POST", "/mcp/tools/call",
        json.dumps({"name": "list_matters", "arguments": {}}).encode(),
        {"Authorization": f"Bearer {fake_token}"},
    )
    assert status == 401, (
        f"Fake scaffold token must NOT authenticate in production. Got {status}."
    )
    store.close()


# ----- C6. Health endpoint remains public in production -----

def test_c6_health_endpoint_public_in_production(monkeypatch, tmp_path):
    """V6.0.1: /mcp/health remains public even in production —
    the scaffold disable does NOT affect health checks.
    """
    monkeypatch.setenv("ALBRA_ENVIRONMENT", "production")
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-jwt-secret-not-for-prod-32chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-admin-pass-1234")
    monkeypatch.setenv("ALBRA_MATTER_DB_PATH", str(tmp_path / "matters.db"))
    mcp = McpServer(security_mode="production")
    http = McpHttpServer(auth_mode="production", mcp_server=mcp)

    status, body, hdrs = http._handle_http_request(
        "GET", "/mcp/health", b"", {},
    )
    assert status == 200
    result = json.loads(body.decode())
    assert result["ok"] is True


# =========================================================================
# Regression — full OIDC pipeline still works after corrections
# =========================================================================

def test_z1_full_oidc_pipeline_still_works(test_keyset, monkeypatch):
    """Regression: a fully valid token still authenticates end-to-end
    through the OIDC pipeline after V6.0.1 corrections.
    """
    pipeline = _build_pipeline(test_keyset, monkeypatch)
    token = _make_token(test_keyset.keys[0], TEST_SUB, "abogado")
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is not None
    assert ctx.auth_method == "oidc"
    assert ctx.role == "abogado"
    assert ctx.tenant_id == TEST_TENANT
    assert ctx.issuer == TEST_ISSUER
    assert ctx.subject == TEST_SUB
    assert ctx.identity == compute_stable_id(TEST_ISSUER, TEST_SUB)


def test_z2_production_never_falls_back_to_dev(monkeypatch):
    """Regression: production without OIDC configured still rejects
    every token. V6.0.1 does not change this V6.0 contract.
    """
    monkeypatch.setenv("OIDC_ENABLED", "false")
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    monkeypatch.delenv("OIDC_AUDIENCE", raising=False)
    ctx = validate_bearer_token("any-token", mode="production")
    assert ctx is None
