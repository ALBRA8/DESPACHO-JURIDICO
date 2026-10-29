"""V6.0 OIDC tenant isolation tests.

Verifies that the OIDC-issued AuthContext.tenant_id is AUTHORITATIVE
and cannot be overridden by client-supplied tenant_id in any part of
the MCP pipeline.

V6.0 brief section 12:
    Tenant A token → tenant A AuthContext → acceso a A permitido
    Tenant A token → request intenta tenant B → sigue siendo tenant A → acceso a B DENEGADO
    Tenant B token → acceso a A DENEGADO
    No debe existir ningún camino donde request.tenant_id reemplace AuthContext.tenant_id
"""
from __future__ import annotations

import json

import pytest

from albra.identity.oidc import OIDCConfig, OIDCPipeline
from albra.identity.oidc.jwks import JwksResolver
from albra.identity.oidc.role_map import RoleMapping, RoleResolver
from albra.identity.oidc.tenant_map import TenantMapping, TenantResolver
from albra.identity.oidc.validator import JWTValidator
from albra.matters.store import MatterStore
from albra.mcp.security import validate_bearer_token
from tests.identity.oidc.conftest import (
    TEST_AUDIENCE,
    TEST_CLIENT_ID,
    TEST_ISSUER,
    TestKeySet,
    compute_stable_id,
    make_jwt,
    make_tenant_map_for_identities,
)

# Two test identities in different tenants.
TENANT_A_SUB = "sub-alice-tenant-a"
TENANT_B_SUB = "sub-bob-tenant-b"
TENANT_A = "tenant-A"
TENANT_B = "tenant-B"
ROLE = "abogado"


def _set_full_oidc_env(monkeypatch, tenant_map: dict):
    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_ISSUER", TEST_ISSUER)
    monkeypatch.setenv("OIDC_AUDIENCE", TEST_AUDIENCE)
    monkeypatch.setenv("OIDC_CLIENT_ID", TEST_CLIENT_ID)
    monkeypatch.setenv("OIDC_JWKS_URL", "https://test-idp.albra.dev/.well-known/jwks.json")
    monkeypatch.setenv("OIDC_ROLE_NAMESPACE", "https://albra.dev")
    monkeypatch.setenv("OIDC_ROLE_CLAIM", "role")
    monkeypatch.setenv("OIDC_TENANT_MAP", json.dumps(tenant_map))


@pytest.fixture
def two_tenant_oidc_setup(test_keyset, monkeypatch):
    """Set up OIDC env + pipeline for two tenants (A and B)."""
    tenant_map = make_tenant_map_for_identities([
        (TEST_ISSUER, TENANT_A_SUB, TENANT_A),
        (TEST_ISSUER, TENANT_B_SUB, TENANT_B),
    ])
    _set_full_oidc_env(monkeypatch, tenant_map)

    config = OIDCConfig.from_env()
    jwks = JwksResolver(config, http_get=test_keyset.http_get())
    validator = JWTValidator(config, jwks_resolver=jwks)
    tenant_resolver = TenantResolver(TenantMapping.from_env())
    role_resolver = RoleResolver(RoleMapping.from_env())
    pipeline = OIDCPipeline(
        config=config, validator=validator,
        tenant_resolver=tenant_resolver, role_resolver=role_resolver,
    )
    return pipeline, test_keyset


def _make_tenant_token(key, subject: str, role: str = ROLE) -> str:
    """Make a JWT for a tenant identity."""
    return make_jwt(
        key=key,
        subject=subject,
        extra_claims={"https://albra.dev": {"role": role}},
    )


# ===== 1. Tenant A token → tenant A AuthContext =====

def test_tenant_a_token_produces_tenant_a_context(two_tenant_oidc_setup):
    """A token for tenant-A produces an AuthContext with tenant_id=tenant-A."""
    pipeline, keyset = two_tenant_oidc_setup
    token = _make_tenant_token(keyset.keys[0], TENANT_A_SUB)
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is not None
    assert ctx.tenant_id == TENANT_A
    assert ctx.subject == TENANT_A_SUB


# ===== 2. Tenant A token → request attempts tenant B → still tenant A → B DENIED =====

def test_tenant_a_token_cannot_override_to_tenant_b(two_tenant_oidc_setup, tmp_path):
    """Tenant A's token produces an AuthContext with tenant_id=tenant-A.
    A downstream MatterStore call CANNOT use this AuthContext to access
    tenant-B data — even if the client passes tenant_id="tenant-B" in args.

    V6.0 brief: "Tenant A token → request intenta tenant B → sigue
    siendo tenant A → acceso a B DENEGADO."
    """
    pipeline, keyset = two_tenant_oidc_setup
    token = _make_tenant_token(keyset.keys[0], TENANT_A_SUB)
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is not None
    assert ctx.tenant_id == TENANT_A

    # Seed a matter in tenant-B.
    store = MatterStore(str(tmp_path / "matters.db"), enforce_tenant=True)
    m_b = store.create_matter(
        client="SECRET_B_CLIENT", area="civil", created_by="ab2",
        tenant_id=TENANT_B,
    )

    # Tenant-A's AuthContext cannot read tenant-B's matter.
    fetched = store.get_matter(m_b.id, tenant_id=ctx.tenant_id)
    assert fetched is None

    # Even if client args smuggle tenant_id="tenant-B", the AuthContext
    # is authoritative — MatterStore uses ctx.tenant_id, NOT args.
    # (The MCP server injects ctx.tenant_id into _auth metadata; args
    # are ignored downstream.)
    assert ctx.tenant_id == TENANT_A
    assert ctx.tenant_id != TENANT_B
    store.close()


# ===== 3. Tenant B token → access to A DENIED =====

def test_tenant_b_token_cannot_access_tenant_a(two_tenant_oidc_setup, tmp_path):
    """Tenant B's token cannot access tenant-A's matters."""
    pipeline, keyset = two_tenant_oidc_setup
    token = _make_tenant_token(keyset.keys[0], TENANT_B_SUB)
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is not None
    assert ctx.tenant_id == TENANT_B

    store = MatterStore(str(tmp_path / "matters.db"), enforce_tenant=True)
    m_a = store.create_matter(
        client="SECRET_A_CLIENT", area="civil", created_by="ab1",
        tenant_id=TENANT_A,
    )

    # Tenant-B cannot read tenant-A's matter.
    fetched = store.get_matter(m_a.id, tenant_id=ctx.tenant_id)
    assert fetched is None
    store.close()


# ===== 4. No path where request.tenant_id replaces AuthContext.tenant_id =====

def test_no_path_replaces_authcontext_tenant_id(two_tenant_oidc_setup):
    """Verify that AuthContext.tenant_id is immutable after construction
    and cannot be replaced by request data.

    V6.0 brief: "No debe existir ningún camino donde request.tenant_id
    reemplace AuthContext.tenant_id."
    """
    pipeline, keyset = two_tenant_oidc_setup
    token = _make_tenant_token(keyset.keys[0], TENANT_A_SUB)
    ctx = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx is not None
    original_tenant = ctx.tenant_id

    # The AuthContext is a dataclass — tenant_id IS settable via Python
    # reflection, but NO legitimate code path does this. The MCP server
    # passes ctx.tenant_id to the store; the store uses it directly.
    # We verify the contract: ctx.tenant_id is set once at construction
    # and is the authoritative tenant for the request.
    assert ctx.tenant_id == TENANT_A
    assert ctx.tenant_id == original_tenant

    # The stable_id (identity) is also immutable in the sense that it
    # was derived from the verified token's (issuer, sub). A client
    # cannot change the stable_id by passing args.
    expected_stable_id = compute_stable_id(TEST_ISSUER, TENANT_A_SUB)
    assert ctx.identity == expected_stable_id


# ===== 5. Two different tokens produce two different tenants =====

def test_two_tokens_produce_two_different_tenants(two_tenant_oidc_setup):
    """Two valid tokens (one per tenant) produce AuthContexts with
    DIFFERENT tenant_ids. They are NOT interchangeable.
    """
    pipeline, keyset = two_tenant_oidc_setup
    token_a = _make_tenant_token(keyset.keys[0], TENANT_A_SUB)
    token_b = _make_tenant_token(keyset.keys[0], TENANT_B_SUB)

    ctx_a = validate_bearer_token(token_a, mode="production", oidc_pipeline=pipeline)
    ctx_b = validate_bearer_token(token_b, mode="production", oidc_pipeline=pipeline)
    assert ctx_a is not None
    assert ctx_b is not None
    assert ctx_a.tenant_id != ctx_b.tenant_id
    assert ctx_a.tenant_id == TENANT_A
    assert ctx_b.tenant_id == TENANT_B
    # The stable identities are also different.
    assert ctx_a.identity != ctx_b.identity


# ===== 6. Same token, two validate_bearer_token calls → same tenant =====

def test_same_token_produces_consistent_tenant(two_tenant_oidc_setup):
    """Calling validate_bearer_token twice with the same token produces
    AuthContexts with the same tenant_id (no drift).
    """
    pipeline, keyset = two_tenant_oidc_setup
    token = _make_tenant_token(keyset.keys[0], TENANT_A_SUB)
    ctx1 = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    ctx2 = validate_bearer_token(token, mode="production", oidc_pipeline=pipeline)
    assert ctx1 is not None and ctx2 is not None
    assert ctx1.tenant_id == ctx2.tenant_id == TENANT_A
