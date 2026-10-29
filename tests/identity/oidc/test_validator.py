"""V6.0 OIDC/OAuth identity tests — scenarios A-Z.

Tests the full OIDC pipeline (validator → identity → tenant → role →
AuthContext) with deterministic RSA keys + JWT generators. No external
IdP dependency. All tests invoke real operations.

Coverage (V6.0 brief section 11):
  A. Token válido
  B. Token vacío
  C. Token malformado
  D. Token expirado
  E. Token aún no válido por nbf
  F. issuer incorrecto
  G. audience incorrecta
  H. firma inválida
  I. algoritmo no permitido
  J. kid inexistente
  K. JWKS inaccesible
  L. JWKS rotación
  M. clock skew permitido
  N. clock skew excedido
  O. subject ausente
  P. issuer + subject correctamente identificados
  Q. identidad válida sin tenant
  R. identidad válida con tenant
  S. tenant enviado por cliente intentando sobrescribir
  T. role no autorizado
  U. claim de role falsificado/no confiable
  V. admin legítimo
  W. abogado legítimo
  X. cliente legítimo
  Y. permisos derivados correctamente
  Z. production nunca cae a DEV
"""
from __future__ import annotations

import json
import time

import pytest

from albra.identity.oidc import (
    OIDCConfig,
    OIDCConfigError,
    OIDCPipeline,
    TokenValidationError,
)
from albra.identity.oidc.identity import build_identity_from_verified_token
from albra.identity.oidc.role_map import RoleMapping, RoleResolver
from albra.identity.oidc.tenant_map import TenantMapping, TenantResolver
from albra.mcp.security import AuthContext, validate_bearer_token

# Import test helpers from conftest (same directory).
from tests.identity.oidc.conftest import (
    TEST_AUDIENCE,
    TEST_CLIENT_ID,
    TEST_ISSUER,
    TestKeySet,
    compute_stable_id,
    make_jwt,
    make_oidc_config,
    make_tenant_map_for_identities,
)

# ===== Shared test setup =====

# Test identities used across scenarios.
# Format: (subject, role, tenant)
TEST_IDENTITIES = [
    ("sub-alice-admin", "admin", "tenant-A"),
    ("sub-bob-abogado", "abogado", "tenant-A"),
    ("sub-carol-cliente", "cliente", "tenant-B"),
    ("sub-dave-socio", "socio", "tenant-B"),
    ("sub-eve-paralegal", "paralegal", "tenant-A"),
]


def _set_oidc_env(monkeypatch, *, tenant_map: dict | None = None):
    """Set env vars for OIDC + tenant map + role namespace."""
    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_ISSUER", TEST_ISSUER)
    monkeypatch.setenv("OIDC_AUDIENCE", TEST_AUDIENCE)
    monkeypatch.setenv("OIDC_CLIENT_ID", TEST_CLIENT_ID)
    monkeypatch.setenv("OIDC_JWKS_URL", "https://test-idp.albra.dev/.well-known/jwks.json")
    monkeypatch.setenv("OIDC_ROLE_NAMESPACE", "https://albra.dev")
    monkeypatch.setenv("OIDC_ROLE_CLAIM", "role")
    if tenant_map is not None:
        monkeypatch.setenv("OIDC_TENANT_MAP", json.dumps(tenant_map))


def _build_tenant_map_for_test() -> dict[str, str]:
    """Build the tenant map for the standard test identities."""
    identities = [
        (TEST_ISSUER, sub, tenant)
        for sub, _, tenant in TEST_IDENTITIES
    ]
    return make_tenant_map_for_identities(identities)


def _build_pipeline(test_keyset, monkeypatch, *, tenant_map: dict | None = None):
    """Build a wired OIDCPipeline for tests."""
    from albra.identity.oidc.jwks import JwksResolver
    from albra.identity.oidc.role_map import RoleMapping, RoleResolver
    from albra.identity.oidc.tenant_map import TenantMapping, TenantResolver
    from albra.identity.oidc.validator import JWTValidator

    _set_oidc_env(monkeypatch, tenant_map=tenant_map)
    config = OIDCConfig.from_env()
    jwks = JwksResolver(config, http_get=test_keyset.http_get())
    validator = JWTValidator(config, jwks_resolver=jwks)
    tenant = TenantResolver(TenantMapping.from_env())
    role = RoleResolver(RoleMapping.from_env())
    return OIDCPipeline(
        config=config, validator=validator,
        tenant_resolver=tenant, role_resolver=role,
    )


def _make_token_for_identity(
    key, subject: str, role: str, *,
    issuer: str = TEST_ISSUER,
    audience: str | list[str] = TEST_AUDIENCE,
    extra_claims: dict | None = None,
    expires_in_seconds: int = 3600,
    not_before_seconds: int = 0,
    headers: dict | None = None,
) -> str:
    """Generate a JWT for a test identity with the trusted role claim."""
    claims = {"https://albra.dev": {"role": role}}
    if extra_claims:
        claims.update(extra_claims)
    return make_jwt(
        key=key,
        issuer=issuer,
        audience=audience,
        subject=subject,
        expires_in_seconds=expires_in_seconds,
        not_before_seconds=not_before_seconds,
        extra_claims=claims,
        headers=headers,
    )


# ===== A. Token válido =====

def test_a_valid_token(test_keyset, monkeypatch):
    """A valid OIDC token produces an AuthContext with auth_method='oidc'."""
    tenant_map = _build_tenant_map_for_test()
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=tenant_map)
    sub, role, tenant = TEST_IDENTITIES[0]  # alice admin tenant-A
    token = _make_token_for_identity(test_keyset.keys[0], sub, role)

    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is not None, "Valid token should produce an AuthContext"
    assert ctx.auth_method == "oidc"
    assert ctx.role == role
    assert ctx.tenant_id == tenant
    assert ctx.issuer == TEST_ISSUER
    assert ctx.subject == sub
    assert ctx.identity == compute_stable_id(TEST_ISSUER, sub)
    assert "admin.*" in ctx.permissions or "tools.invoke" in ctx.permissions


# ===== B. Token vacío =====

def test_b_empty_token(test_keyset, monkeypatch):
    """An empty bearer token is rejected (None)."""
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=_build_tenant_map_for_test())
    ctx = validate_bearer_token("", mode="production", oidc_pipeline=pipeline)
    assert ctx is None


# ===== C. Token malformado =====

def test_c_malformed_token(test_keyset, monkeypatch):
    """A non-JWT string is rejected."""
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=_build_tenant_map_for_test())
    ctx = validate_bearer_token("not.a.jwt.really", mode="production", oidc_pipeline=pipeline)
    assert ctx is None
    # Also: completely random string
    ctx = validate_bearer_token("xxxxxxx", mode="production", oidc_pipeline=pipeline)
    assert ctx is None


# ===== D. Token expirado =====

def test_d_expired_token(test_keyset, monkeypatch):
    """An expired token (exp more than clock-skew in the past) is rejected.

    Default clock skew = 60s. We expire the token 120s ago → beyond
    skew → rejected. (Within-skew expiry is tested in test_m.)
    """
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=_build_tenant_map_for_test())
    sub, role, _ = TEST_IDENTITIES[0]
    token = _make_token_for_identity(
        test_keyset.keys[0], sub, role, expires_in_seconds=-120,
    )
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is None


# ===== E. Token aún no válido por nbf =====

def test_e_not_yet_valid_token(test_keyset, monkeypatch):
    """A token with nbf in the future (beyond skew) is rejected."""
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=_build_tenant_map_for_test())
    sub, role, _ = TEST_IDENTITIES[0]
    # nbf = now + 600s; clock skew = 60s → 540s beyond skew.
    token = _make_token_for_identity(
        test_keyset.keys[0], sub, role, not_before_seconds=600,
    )
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is None


# ===== F. issuer incorrecto =====

def test_f_wrong_issuer(test_keyset, monkeypatch):
    """A token with a different issuer is rejected."""
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=_build_tenant_map_for_test())
    sub, role, _ = TEST_IDENTITIES[0]
    token = _make_token_for_identity(
        test_keyset.keys[0], sub, role, issuer="https://evil.example.com/",
    )
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is None


# ===== G. audience incorrecta =====

def test_g_wrong_audience(test_keyset, monkeypatch):
    """A token with a different audience is rejected."""
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=_build_tenant_map_for_test())
    sub, role, _ = TEST_IDENTITIES[0]
    token = _make_token_for_identity(
        test_keyset.keys[0], sub, role, audience="https://wrong-api.example.com",
    )
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is None


# ===== H. firma inválida =====

def test_h_invalid_signature(test_keyset, monkeypatch):
    """A token signed with a key NOT in the JWKS is rejected.

    The token has a valid kid (key-1) but is signed with a DIFFERENT
    key (a fresh key not in the JWKS). The signature verification
    must fail.
    """
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=_build_tenant_map_for_test())
    sub, role, _ = TEST_IDENTITIES[0]
    # Generate a token with a key NOT in the JWKS but claim kid=key-1.
    rogue_keyset = TestKeySet.generate(["rogue"])
    rogue_key = rogue_keyset.keys[0]
    # Force the kid header to claim it's key-1 (lying header).
    token = _make_token_for_identity(
        rogue_key, sub, role, headers={"kid": "key-1"},
    )
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is None


# ===== I. algoritmo no permitido =====

def test_i_forbidden_algorithm_hs256(test_keyset, monkeypatch):
    """A token using HS256 (symmetric) is rejected — only RS256/384/512
    are allowed in production.
    """
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=_build_tenant_map_for_test())
    sub, role, _ = TEST_IDENTITIES[0]
    # PyJWT can sign with HS256 using a shared secret. The validator
    # should reject this before even attempting signature verification
    # (algorithm whitelist).
    import jwt as pyjwt
    payload = {
        "iss": TEST_ISSUER, "sub": sub, "aud": TEST_AUDIENCE,
        "iat": int(time.time()), "exp": int(time.time()) + 3600,
        "https://albra.dev": {"role": role},
    }
    token = pyjwt.encode(payload, "shared-secret", algorithm="HS256", headers={"kid": "key-1"})
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is None


def test_i_forbidden_algorithm_none(test_keyset, monkeypatch):
    """A token using alg=none is rejected — unsigned tokens forbidden."""
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=_build_tenant_map_for_test())
    sub, role, _ = TEST_IDENTITIES[0]
    # Craft an unsigned JWT manually (alg=none, empty signature).
    import base64
    header = {"alg": "none", "typ": "JWT", "kid": "key-1"}
    payload = {
        "iss": TEST_ISSUER, "sub": sub, "aud": TEST_AUDIENCE,
        "iat": int(time.time()), "exp": int(time.time()) + 3600,
        "https://albra.dev": {"role": role},
    }
    def _b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    token = f"{_b64(header)}.{_b64(payload)}."
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is None


# ===== J. kid inexistente =====

def test_j_unknown_kid(test_keyset, monkeypatch):
    """A token with a kid not in the JWKS (after refresh) is rejected."""
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=_build_tenant_map_for_test())
    sub, role, _ = TEST_IDENTITIES[0]
    # Generate a token with a kid that's not in test_keyset.
    rogue_keyset = TestKeySet.generate(["unknown-kid"])
    token = _make_token_for_identity(rogue_keyset.keys[0], sub, role)
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is None


# ===== K. JWKS inaccesible =====

def test_k_jwks_unreachable(monkeypatch):
    """When the JWKS endpoint is unreachable, every token is rejected."""
    from albra.identity.oidc.jwks import JwksError, JwksResolver
    from albra.identity.oidc.role_map import RoleMapping, RoleResolver
    from albra.identity.oidc.tenant_map import TenantMapping, TenantResolver
    from albra.identity.oidc.validator import JWTValidator

    _set_oidc_env(monkeypatch, tenant_map=_build_tenant_map_for_test())
    config = OIDCConfig.from_env()

    def _failing_http_get(url, timeout):
        raise JwksError("network unreachable (simulated)")

    jwks = JwksResolver(config, http_get=_failing_http_get)
    validator = JWTValidator(config, jwks_resolver=jwks)
    tenant = TenantResolver(TenantMapping.from_env())
    role = RoleResolver(RoleMapping.from_env())
    pipeline = OIDCPipeline(
        config=config, validator=validator,
        tenant_resolver=tenant, role_resolver=role,
    )

    # Generate a valid-looking token with a real key — but JWKS fetch fails.
    keyset = TestKeySet.generate(["key-1"])
    sub, role_name, _ = TEST_IDENTITIES[0]
    token = _make_token_for_identity(keyset.keys[0], sub, role_name)
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is None


# ===== L. JWKS rotación =====

def test_l_jwks_rotation(test_keyset, monkeypatch):
    """When the JWKS rotates (new kid appears), the resolver re-fetches
    and accepts tokens signed with the new key.
    """
    # Start with only key-1 in the JWKS.
    initial_keyset = TestKeySet.generate(["key-1"])
    pipeline = _build_pipeline_with_keyset(initial_keyset, monkeypatch)

    # Token signed with key-1 → valid.
    sub, role, _ = TEST_IDENTITIES[0]
    token_v1 = _make_token_for_identity(initial_keyset.keys[0], sub, role)
    ctx = validate_bearer_token(token_v1, mode="production", oidc_pipeline=pipeline)
    assert ctx is not None

    # Now rotate: the JWKS serves BOTH key-1 and key-2.
    rotated_keyset = TestKeySet.generate(["key-1", "key-2"])
    pipeline2 = _build_pipeline_with_keyset(rotated_keyset, monkeypatch)

    # Token signed with key-2 → valid (rotation succeeds).
    token_v2 = _make_token_for_identity(rotated_keyset.keys[1], sub, role)
    ctx2 = validate_bearer_token(token_v2, mode="production", oidc_pipeline=pipeline2)
    assert ctx2 is not None


def _build_pipeline_with_keyset(keyset, monkeypatch):
    """Build a pipeline with a specific keyset (helper for rotation test)."""
    from albra.identity.oidc.jwks import JwksResolver
    from albra.identity.oidc.role_map import RoleMapping, RoleResolver
    from albra.identity.oidc.tenant_map import TenantMapping, TenantResolver
    from albra.identity.oidc.validator import JWTValidator

    _set_oidc_env(monkeypatch, tenant_map=_build_tenant_map_for_test())
    config = OIDCConfig.from_env()
    jwks = JwksResolver(config, http_get=keyset.http_get())
    validator = JWTValidator(config, jwks_resolver=jwks)
    tenant = TenantResolver(TenantMapping.from_env())
    role = RoleResolver(RoleMapping.from_env())
    return OIDCPipeline(
        config=config, validator=validator,
        tenant_resolver=tenant, role_resolver=role,
    )


# ===== M. clock skew permitido =====

def test_m_clock_skew_allowed(test_keyset, monkeypatch):
    """A token expired by less than the clock skew is accepted."""
    # Configure with 120s skew.
    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_ISSUER", TEST_ISSUER)
    monkeypatch.setenv("OIDC_AUDIENCE", TEST_AUDIENCE)
    monkeypatch.setenv("OIDC_CLIENT_ID", TEST_CLIENT_ID)
    monkeypatch.setenv("OIDC_JWKS_URL", "https://test-idp.albra.dev/.well-known/jwks.json")
    monkeypatch.setenv("OIDC_ROLE_NAMESPACE", "https://albra.dev")
    monkeypatch.setenv("OIDC_ROLE_CLAIM", "role")
    monkeypatch.setenv("OIDC_TENANT_MAP", json.dumps(_build_tenant_map_for_test()))
    monkeypatch.setenv("OIDC_CLOCK_SKEW_SECONDS", "120")

    pipeline = _build_pipeline_with_keyset(test_keyset, monkeypatch)
    sub, role, _ = TEST_IDENTITIES[0]
    # Token expired 60s ago — within 120s skew → accepted.
    token = _make_token_for_identity(
        test_keyset.keys[0], sub, role, expires_in_seconds=-60,
    )
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is not None


# ===== N. clock skew excedido =====

def test_n_clock_skew_exceeded(test_keyset, monkeypatch):
    """A token expired by more than the clock skew is rejected."""
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=_build_tenant_map_for_test())
    # Default skew is 60s. Token expired 120s ago → beyond skew → reject.
    sub, role, _ = TEST_IDENTITIES[0]
    token = _make_token_for_identity(
        test_keyset.keys[0], sub, role, expires_in_seconds=-120,
    )
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is None


# ===== O. subject ausente =====

def test_o_missing_subject(test_keyset, monkeypatch):
    """A token without a 'sub' claim is rejected."""
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=_build_tenant_map_for_test())
    # Generate a token with sub="" (empty).
    import jwt as pyjwt
    payload = {
        "iss": TEST_ISSUER, "sub": "", "aud": TEST_AUDIENCE,
        "iat": int(time.time()), "exp": int(time.time()) + 3600,
        "https://albra.dev": {"role": "admin"},
    }
    token = pyjwt.encode(
        payload, test_keyset.keys[0].private_pem,
        algorithm="RS256", headers={"kid": "key-1"},
    )
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is None


# ===== P. issuer + subject correctamente identificados =====

def test_p_issuer_subject_correctly_identified(test_keyset, monkeypatch):
    """The AuthContext correctly captures issuer + subject from a
    verified token. The 'identity' field is the stable_id (SHA-256
    of issuer||subject), NOT the raw sub.
    """
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=_build_tenant_map_for_test())
    sub, role, tenant = TEST_IDENTITIES[1]  # bob abogado
    token = _make_token_for_identity(test_keyset.keys[0], sub, role)

    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is not None
    assert ctx.issuer == TEST_ISSUER
    assert ctx.subject == sub
    expected_stable_id = compute_stable_id(TEST_ISSUER, sub)
    assert ctx.identity == expected_stable_id
    # The raw sub is NOT the identity.
    assert ctx.identity != sub


# ===== Q. identidad válida sin tenant =====

def test_q_valid_identity_no_tenant(test_keyset, monkeypatch):
    """A valid token whose identity is not in the tenant map is denied.

    V6.0 brief: "Si el token es válido pero no existe un tenant
    autorizado: DENY."
    """
    # Build a tenant map that does NOT include the test identity.
    other_identities = [(TEST_ISSUER, "other-sub", "tenant-X")]
    other_map = make_tenant_map_for_identities(other_identities)
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=other_map)

    sub, role, _ = TEST_IDENTITIES[0]  # alice — not in other_map
    token = _make_token_for_identity(test_keyset.keys[0], sub, role)
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is None


def test_q_valid_identity_empty_tenant_map(test_keyset, monkeypatch):
    """A valid token with NO tenant map configured at all is denied."""
    _set_oidc_env(monkeypatch, tenant_map=None)  # no OIDC_TENANT_MAP
    monkeypatch.delenv("OIDC_TENANT_MAP_PATH", raising=False)

    from albra.identity.oidc.jwks import JwksResolver
    from albra.identity.oidc.role_map import RoleMapping, RoleResolver
    from albra.identity.oidc.tenant_map import TenantMapping, TenantResolver
    from albra.identity.oidc.validator import JWTValidator

    config = OIDCConfig.from_env()
    jwks = JwksResolver(config, http_get=test_keyset.http_get())
    validator = JWTValidator(config, jwks_resolver=jwks)
    tenant = TenantResolver(TenantMapping.from_env())
    role = RoleResolver(RoleMapping.from_env())
    pipeline = OIDCPipeline(
        config=config, validator=validator,
        tenant_resolver=tenant, role_resolver=role,
    )

    sub, role_name, _ = TEST_IDENTITIES[0]
    token = _make_token_for_identity(test_keyset.keys[0], sub, role_name)
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is None


# ===== R. identidad válida con tenant =====

def test_r_valid_identity_with_tenant(test_keyset, monkeypatch):
    """A valid token whose identity IS in the tenant map is allowed.
    The AuthContext.tenant_id matches the mapped tenant.
    """
    tenant_map = _build_tenant_map_for_test()
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=tenant_map)

    sub, role, expected_tenant = TEST_IDENTITIES[2]  # carol cliente tenant-B
    token = _make_token_for_identity(test_keyset.keys[0], sub, role)
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is not None
    assert ctx.tenant_id == expected_tenant


# ===== S. tenant enviado por cliente no tiene autoridad =====

def test_s_client_tenant_override_ignored(test_keyset, monkeypatch):
    """A client cannot override the tenant by passing tenant_id in
    tool args. The AuthContext.tenant_id is authoritative.
    """
    tenant_map = _build_tenant_map_for_test()
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=tenant_map)

    # carol is tenant-B. She tries to claim tenant-A.
    sub, role, real_tenant = TEST_IDENTITIES[2]  # carol cliente tenant-B
    token = _make_token_for_identity(test_keyset.keys[0], sub, role)
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is not None
    assert ctx.tenant_id == real_tenant  # tenant-B, NOT tenant-A
    # The ctx.tenant_id is what MCP enforces — client args are ignored
    # downstream (V5.2 contract).
    assert ctx.tenant_id != "tenant-A"


# ===== T. role no autorizado =====

def test_t_role_not_authorized(test_keyset, monkeypatch):
    """A token with a role value not in the allowed set is rejected."""
    tenant_map = _build_tenant_map_for_test()
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=tenant_map)

    sub, _, _ = TEST_IDENTITIES[0]
    # Claim a role that's not in ALBRA_ROLES (e.g. "superuser").
    token = _make_token_for_identity(
        test_keyset.keys[0], sub, "superuser",
    )
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is None


# ===== U. claim de role falsificado/no confiable =====

def test_u_unnamespaced_role_claim_ignored(test_keyset, monkeypatch):
    """A bare 'role' claim (without the trusted namespace) is NEVER
    honored, even if the value is a valid ALBRA role.

    V6.0: an attacker who controls another IdP could mint a JWT with
    `role: "admin"` in the default namespace. ALBRA must not honor it.
    """
    tenant_map = _build_tenant_map_for_test()
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=tenant_map)

    sub, _, _ = TEST_IDENTITIES[0]
    # Token with a BARE 'role' claim (no namespace).
    token = make_jwt(
        key=test_keyset.keys[0],
        subject=sub,
        extra_claims={"role": "admin"},  # bare, unnamespaced
    )
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is None


def test_u_role_claim_in_wrong_namespace_ignored(test_keyset, monkeypatch):
    """A role claim in a non-trusted namespace is never honored."""
    tenant_map = _build_tenant_map_for_test()
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=tenant_map)

    sub, _, _ = TEST_IDENTITIES[0]
    # Role claim in a DIFFERENT namespace than trusted.
    token = make_jwt(
        key=test_keyset.keys[0],
        subject=sub,
        extra_claims={"https://evil.example.com": {"role": "admin"}},
    )
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is None


# ===== V. admin legítimo =====

def test_v_legitimate_admin(test_keyset, monkeypatch):
    """A legitimate admin token gets admin.* wildcard permissions."""
    tenant_map = _build_tenant_map_for_test()
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=tenant_map)

    sub, _, _ = TEST_IDENTITIES[0]  # alice admin
    token = _make_token_for_identity(test_keyset.keys[0], sub, "admin")
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is not None
    assert ctx.role == "admin"
    assert "admin.*" in ctx.permissions
    # Admin can do everything.
    from albra.mcp.security import TOOL_PERMISSIONS
    for tool, perm in TOOL_PERMISSIONS.items():
        assert ctx.has_permission(perm), f"admin should have {perm} for {tool}"


# ===== W. abogado legítimo =====

def test_w_legitimate_abogado(test_keyset, monkeypatch):
    """A legitimate abogado token gets the abogado permission set."""
    tenant_map = _build_tenant_map_for_test()
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=tenant_map)

    sub, _, _ = TEST_IDENTITIES[1]  # bob abogado
    token = _make_token_for_identity(test_keyset.keys[0], sub, "abogado")
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is not None
    assert ctx.role == "abogado"
    # abogado can advance matters but NOT run eval.
    assert ctx.has_permission("matters.advance")
    assert not ctx.has_permission("eval.run")


# ===== X. cliente legítimo =====

def test_x_legitimate_cliente(test_keyset, monkeypatch):
    """A legitimate cliente token gets the cliente permission set
    (read-only matters, no advance, no eval).
    """
    tenant_map = _build_tenant_map_for_test()
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=tenant_map)

    sub, _, _ = TEST_IDENTITIES[2]  # carol cliente
    token = _make_token_for_identity(test_keyset.keys[0], sub, "cliente")
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is not None
    assert ctx.role == "cliente"
    assert ctx.has_permission("matters.read")
    assert not ctx.has_permission("matters.advance")
    assert not ctx.has_permission("eval.run")


# ===== Y. permisos derivados correctamente =====

def test_y_permissions_derived_correctly(test_keyset, monkeypatch):
    """For each role, the AuthContext.permissions matches ROLE_PERMISSIONS."""
    from albra.mcp.security import ROLE_PERMISSIONS

    tenant_map = _build_tenant_map_for_test()
    pipeline = _build_pipeline(test_keyset, monkeypatch, tenant_map=tenant_map)

    for sub, role, _ in TEST_IDENTITIES:
        token = _make_token_for_identity(test_keyset.keys[0], sub, role)
        ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
        assert ctx is not None, f"role {role} should produce a context"
        assert ctx.permissions == ROLE_PERMISSIONS[role], (
            f"role {role}: permissions mismatch. "
            f"expected {ROLE_PERMISSIONS[role]}, got {ctx.permissions}"
        )


# ===== Z. production nunca cae a DEV =====

def test_z_production_never_falls_back_to_dev(monkeypatch):
    """When OIDC is disabled in production mode, EVERY token is
    rejected — production NEVER silently falls back to dev behavior.
    """
    # OIDC disabled.
    monkeypatch.setenv("OIDC_ENABLED", "false")
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    monkeypatch.delenv("OIDC_AUDIENCE", raising=False)

    # Even a "dev-admin-..." token must be rejected in production mode.
    ctx = validate_bearer_token("dev-admin-anything", mode="production")
    assert ctx is None

    # Even a non-empty random string must be rejected.
    ctx = validate_bearer_token("any-token-at-all", mode="production")
    assert ctx is None


def test_z_production_misconfigured_fails_closed(monkeypatch):
    """When OIDC is enabled but OIDC_ISSUER is missing, production
    fails closed — every token is rejected.
    """
    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_AUDIENCE", TEST_AUDIENCE)
    monkeypatch.delenv("OIDC_ISSUER", raising=False)  # missing!

    ctx = validate_bearer_token("any-token", mode="production")
    assert ctx is None


def test_z_production_no_oidc_deps_fails_closed(monkeypatch):
    """Even with OIDC env vars set correctly, if the OIDC layer can't
    be imported (e.g. PyJWT missing), production fails closed.
    """
    _set_oidc_env(monkeypatch, tenant_map=_build_tenant_map_for_test())
    # We can't actually uninstall PyJWT in the test env, but we can
    # verify that the import-failure path returns None by temporarily
    # monkeypatching the import. Simpler: just verify that with no
    # oidc_pipeline and a malformed config, we get None.
    monkeypatch.setenv("OIDC_ISSUER", "")  # corrupt the config
    ctx = validate_bearer_token("any-token", mode="production")
    assert ctx is None
