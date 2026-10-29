"""V6.0 MCP HTTP end-to-end OIDC integration tests.

Tests the full production pipeline:
    HTTP request → Bearer → OIDC validator → AuthContext → RBAC →
    tenant enforcement → tool

These tests exercise McpHttpServer in production mode with a real
OIDC pipeline wired to deterministic test JWKS. They DON'T touch the
network — the JWKS is served from a test fixture.
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
from albra.mcp.server import McpHttpServer, McpServer
from tests.identity.oidc.conftest import (
    TEST_AUDIENCE,
    TEST_CLIENT_ID,
    TEST_ISSUER,
    compute_stable_id,
    make_jwt,
    make_tenant_map_for_identities,
)

# Test identity: alice abogado tenant-A.
TEST_SUB = "sub-alice-abogado"
TEST_TENANT = "tenant-A"
TEST_ROLE = "abogado"


def _set_oidc_env(monkeypatch, tenant_map: dict):
    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_ISSUER", TEST_ISSUER)
    monkeypatch.setenv("OIDC_AUDIENCE", TEST_AUDIENCE)
    monkeypatch.setenv("OIDC_CLIENT_ID", TEST_CLIENT_ID)
    monkeypatch.setenv("OIDC_JWKS_URL", "https://test-idp.albra.dev/.well-known/jwks.json")
    monkeypatch.setenv("OIDC_ROLE_NAMESPACE", "https://albra.dev")
    monkeypatch.setenv("OIDC_ROLE_CLAIM", "role")
    monkeypatch.setenv("OIDC_TENANT_MAP", json.dumps(tenant_map))


def _make_bearer(key, subject=TEST_SUB, role=TEST_ROLE) -> str:
    """Make a valid OIDC bearer token for the test identity."""
    return make_jwt(
        key=key,
        subject=subject,
        extra_claims={"https://albra.dev": {"role": role}},
    )


def _make_http_request(
    method: str,
    path: str,
    body: dict | None = None,
    bearer: str | None = None,
):
    """Build HTTP request args for McpHttpServer._handle_http_request."""
    body_bytes = json.dumps(body or {}).encode("utf-8") if body else b""
    headers = {}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    return method, path, body_bytes, headers


def _parse_response(status: int, body: bytes, headers: dict) -> dict:
    """Parse the JSON response body."""
    try:
        return json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"_raw": body[:200]}


@pytest.fixture
def production_oidc_setup(test_keyset, monkeypatch, tmp_path):
    """Wire a McpHttpServer in production mode with real OIDC."""
    tenant_map = make_tenant_map_for_identities([
        (TEST_ISSUER, TEST_SUB, TEST_TENANT),
    ])
    _set_oidc_env(monkeypatch, tenant_map)

    config = OIDCConfig.from_env()
    jwks = JwksResolver(config, http_get=test_keyset.http_get())
    validator = JWTValidator(config, jwks_resolver=jwks)
    tenant_resolver = TenantResolver(TenantMapping.from_env())
    role_resolver = RoleResolver(RoleMapping.from_env())
    pipeline = OIDCPipeline(
        config=config, validator=validator,
        tenant_resolver=tenant_resolver, role_resolver=role_resolver,
    )

    # Set up a MatterStore with enforce_tenant=True (production-like).
    db_path = tmp_path / "matters.db"
    monkeypatch.setenv("ALBRA_MATTER_DB_PATH", str(db_path))
    monkeypatch.setenv("ALBRA_MATTER_DATA_DIR", str(tmp_path / "matters"))
    store = MatterStore(str(db_path), enforce_tenant=True)

    # Seed a matter in tenant-A.
    matter = store.create_matter(
        client="Alice Client", area="civil", created_by="ab1",
        tenant_id=TEST_TENANT,
    )

    # Build McpServer + McpHttpServer.
    mcp = McpServer(security_mode="production", matter_store=store)
    http = McpHttpServer(
        auth_mode="production", oauth_required=True,
        mcp_server=mcp, oidc_pipeline=pipeline,
    )

    yield pipeline, http, store, matter, test_keyset

    store.close()


# ===== 1. Valid Bearer → list_matters allowed =====

def test_http_valid_bearer_list_matters_allowed(production_oidc_setup):
    """HTTP request with a valid OIDC bearer → list_matters succeeds
    and returns the tenant-A matter.
    """
    pipeline, http, store, matter, keyset = production_oidc_setup
    bearer = _make_bearer(keyset.keys[0])

    status, body, hdrs = http._handle_http_request(
        *_make_http_request(
            "POST", "/mcp/tools/call",
            body={"name": "list_matters", "arguments": {}},
            bearer=bearer,
        )
    )
    assert status == 200, f"Expected 200, got {status}"
    result = _parse_response(status, body, hdrs)
    content = result.get("content", [])
    assert content, "Response should have content"
    inner = json.loads(content[0]["text"])
    assert inner.get("count") == 1
    assert inner["matters"][0]["client"] == "Alice Client"


# ===== 2. Missing Bearer → 401 =====

def test_http_missing_bearer_unauthorized(production_oidc_setup):
    """HTTP request without Authorization header → 401."""
    pipeline, http, store, matter, keyset = production_oidc_setup

    status, body, hdrs = http._handle_http_request(
        *_make_http_request(
            "POST", "/mcp/tools/call",
            body={"name": "list_matters", "arguments": {}},
            bearer=None,
        )
    )
    assert status == 401
    result = _parse_response(status, body, hdrs)
    assert "unauthorized" in result.get("error", "")


# ===== 3. Invalid Bearer (expired token) → 401 =====

def test_http_expired_bearer_unauthorized(production_oidc_setup):
    """HTTP request with an expired OIDC bearer → 401."""
    pipeline, http, store, matter, keyset = production_oidc_setup
    bearer = make_jwt(
        key=keyset.keys[0],
        subject=TEST_SUB,
        expires_in_seconds=-120,  # expired
        extra_claims={"https://albra.dev": {"role": TEST_ROLE}},
    )

    status, body, hdrs = http._handle_http_request(
        *_make_http_request(
            "POST", "/mcp/tools/call",
            body={"name": "list_matters", "arguments": {}},
            bearer=bearer,
        )
    )
    assert status == 401


# ===== 4. Wrong issuer → 401 =====

def test_http_wrong_issuer_bearer_unauthorized(production_oidc_setup):
    """HTTP request with a token from a different issuer → 401."""
    pipeline, http, store, matter, keyset = production_oidc_setup
    bearer = make_jwt(
        key=keyset.keys[0],
        subject=TEST_SUB,
        issuer="https://evil.example.com/",
        extra_claims={"https://albra.dev": {"role": TEST_ROLE}},
    )

    status, body, hdrs = http._handle_http_request(
        *_make_http_request(
            "POST", "/mcp/tools/call",
            body={"name": "list_matters", "arguments": {}},
            bearer=bearer,
        )
    )
    assert status == 401


# ===== 5. Wrong audience → 401 =====

def test_http_wrong_audience_bearer_unauthorized(production_oidc_setup):
    """HTTP request with a token for a different audience → 401."""
    pipeline, http, store, matter, keyset = production_oidc_setup
    bearer = make_jwt(
        key=keyset.keys[0],
        subject=TEST_SUB,
        audience="https://wrong-api.example.com",
        extra_claims={"https://albra.dev": {"role": TEST_ROLE}},
    )

    status, body, hdrs = http._handle_http_request(
        *_make_http_request(
            "POST", "/mcp/tools/call",
            body={"name": "list_matters", "arguments": {}},
            bearer=bearer,
        )
    )
    assert status == 401


# ===== 6. Forged role claim (unnamespaced) → 401 =====

def test_http_forged_role_claim_unauthorized(production_oidc_setup):
    """HTTP request with a bare 'role' claim (no namespace) → 401.

    V6.0 brief U: "claim de role falsificado/no confiable".
    """
    pipeline, http, store, matter, keyset = production_oidc_setup
    # Token has a bare 'role' claim — not in the trusted namespace.
    bearer = make_jwt(
        key=keyset.keys[0],
        subject=TEST_SUB,
        extra_claims={"role": "admin"},  # bare, unnamespaced
    )

    status, body, hdrs = http._handle_http_request(
        *_make_http_request(
            "POST", "/mcp/tools/call",
            body={"name": "list_matters", "arguments": {}},
            bearer=bearer,
        )
    )
    assert status == 401


# ===== 7. Valid Bearer + RBAC insufficient role → DENIED =====

def test_http_valid_bearer_insufficient_role_denied(production_oidc_setup, monkeypatch, tmp_path):
    """A valid OIDC bearer for a 'cliente' role trying to call
    'advance_matter' (requires matters.advance) → DENIED.

    cliente role lacks matters.advance per ROLE_PERMISSIONS.
    """
    pipeline, http, store, matter, keyset = production_oidc_setup
    # Add a cliente identity to the tenant map.
    cliente_sub = "sub-carol-cliente"
    new_map = make_tenant_map_for_identities([
        (TEST_ISSUER, TEST_SUB, TEST_TENANT),
        (TEST_ISSUER, cliente_sub, TEST_TENANT),
    ])
    _set_oidc_env(monkeypatch, new_map)

    # Rebuild pipeline with new tenant map.
    config = OIDCConfig.from_env()
    jwks = JwksResolver(config, http_get=keyset.http_get())
    pipeline2 = OIDCPipeline(
        config=config,
        validator=JWTValidator(config, jwks_resolver=jwks),
        tenant_resolver=TenantResolver(TenantMapping.from_env()),
        role_resolver=RoleResolver(RoleMapping.from_env()),
    )
    http._oidc_pipeline = pipeline2

    bearer = make_jwt(
        key=keyset.keys[0],
        subject=cliente_sub,
        extra_claims={"https://albra.dev": {"role": "cliente"}},
    )

    status, body, hdrs = http._handle_http_request(
        *_make_http_request(
            "POST", "/mcp/tools/call",
            body={"name": "advance_matter",
                  "arguments": {"matter_id": matter.id, "target_state": "PLANEACIÓN"}},
            bearer=bearer,
        )
    )
    assert status == 200  # HTTP OK; the tool call returns DENIED inside
    result = _parse_response(status, body, hdrs)
    content = result.get("content", [])
    inner = json.loads(content[0]["text"])
    assert inner.get("status") == "DENIED"
    assert inner.get("authorization") == "DENIED"


# ===== 8. Cross-tenant access DENIED =====

def test_http_cross_tenant_access_denied(production_oidc_setup, monkeypatch):
    """Tenant-A token tries to call list_matters but the request args
    include tenant_id="tenant-B". The OIDC AuthContext is authoritative;
    the args override is ignored, and only tenant-A matters are returned.

    V6.0 brief S: "tenant enviado por cliente intentando sobrescribir
    tenant autenticado".
    """
    pipeline, http, store, matter, keyset = production_oidc_setup
    # Seed a matter in tenant-B too.
    store.create_matter(
        client="Bob Secret", area="civil", created_by="ab2",
        tenant_id="tenant-B",
    )

    bearer = _make_bearer(keyset.keys[0])  # tenant-A abogado

    status, body, hdrs = http._handle_http_request(
        *_make_http_request(
            "POST", "/mcp/tools/call",
            body={"name": "list_matters",
                  "arguments": {"tenant_id": "tenant-B"}},  # attempt override
            bearer=bearer,
        )
    )
    assert status == 200
    result = _parse_response(status, body, hdrs)
    content = result.get("content", [])
    inner = json.loads(content[0]["text"])
    # Only tenant-A's matter is returned — tenant-B is invisible.
    clients = [m["client"] for m in inner.get("matters", [])]
    assert "Alice Client" in clients
    assert "Bob Secret" not in clients


# ===== 9. Production never falls back to dev =====

def test_http_production_no_dev_fallback(monkeypatch, test_keyset, tmp_path):
    """When OIDC is DISABLED in production mode, every bearer is 401.
    Production NEVER silently falls back to dev.
    """
    monkeypatch.setenv("OIDC_ENABLED", "false")
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    monkeypatch.delenv("OIDC_AUDIENCE", raising=False)
    monkeypatch.setenv("ALBRA_MATTER_DB_PATH", str(tmp_path / "matters.db"))
    monkeypatch.setenv("ALBRA_MATTER_DATA_DIR", str(tmp_path / "matters"))

    mcp = McpServer(security_mode="production")
    http = McpHttpServer(auth_mode="production", mcp_server=mcp)

    # Even a "dev-admin-..." token must be 401 in production.
    status, body, hdrs = http._handle_http_request(
        *_make_http_request(
            "POST", "/mcp/tools/call",
            body={"name": "list_matters", "arguments": {}},
            bearer="dev-admin-anything",
        )
    )
    assert status == 401


# ===== 10. tools/list works with valid bearer =====

def test_http_tools_list_with_valid_bearer(production_oidc_setup):
    """The /mcp/tools/list endpoint requires a valid bearer in
    production mode and returns the 10 ALBRA tools.
    """
    pipeline, http, store, matter, keyset = production_oidc_setup
    bearer = _make_bearer(keyset.keys[0])

    status, body, hdrs = http._handle_http_request(
        *_make_http_request(
            "POST", "/mcp/tools/list",
            body={},
            bearer=bearer,
        )
    )
    assert status == 200
    result = _parse_response(status, body, hdrs)
    tools = result.get("tools", [])
    assert len(tools) == 10


# ===== 11. tools/list without bearer → 401 =====

def test_http_tools_list_without_bearer_unauthorized(production_oidc_setup):
    """tools/list without bearer → 401 in production."""
    pipeline, http, store, matter, keyset = production_oidc_setup

    status, body, hdrs = http._handle_http_request(
        *_make_http_request("POST", "/mcp/tools/list", body={}, bearer=None)
    )
    assert status == 401


# ===== 12. Health endpoint is public (no bearer required) =====

def test_http_health_public(production_oidc_setup):
    """/mcp/health is public — no bearer required even in production."""
    pipeline, http, store, matter, keyset = production_oidc_setup

    status, body, hdrs = http._handle_http_request(
        *_make_http_request("GET", "/mcp/health", bearer=None)
    )
    assert status == 200
    result = _parse_response(status, body, hdrs)
    assert result.get("ok") is True
