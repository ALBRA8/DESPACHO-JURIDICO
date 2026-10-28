"""Tests del MCP HTTP server + OAuth scaffold (V2.3-D).

Cobertura (16 tests):
- McpHttpServer init (defaults + custom port)
- GET /mcp/health → 200
- POST /mcp/initialize → server info + capabilities
- POST /mcp/tools/list → 10 tools
- POST /mcp/tools/call (audit_citation) → content[0].text JSON
- POST /mcp/tools/call (unknown tool) → isError=True
- GET /mcp/.well-known/oauth-authorization-server → metadata
- GET /mcp/oauth/authorize?redirect_uri=... → 302 redirect
- POST /mcp/oauth/token (with code) → access_token
- Bearer required when oauth_required=True (401 if missing)
- Bearer validation accepts any non-empty token (V2.3-D scaffold)
- CORS headers present on every response
- 405 method not allowed on known path
- 404 path not found
- --no-auth skips bearer check
"""
from __future__ import annotations

import json

import pytest

from albra.mcp.server import McpHttpServer, McpServer

# ===== Fixtures =====


@pytest.fixture
def strong_secrets(monkeypatch):
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-ephemeral-jwt-secret-32-chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-ephemeral-pass-1234")


@pytest.fixture
def store(strong_secrets, tmp_path):
    from albra.matters.store import MatterStore
    s = MatterStore(str(tmp_path / "matters.db"))
    yield s
    s.close()


@pytest.fixture
def audit(strong_secrets, tmp_path):
    from albra.audit.matter_audit import MatterAudit
    return MatterAudit(str(tmp_path / "matters"))


@pytest.fixture
def mcp_server(strong_secrets, store, audit):
    """McpServer with the 10 ALBRA tools + injected store/audit."""
    return McpServer(matter_store=store, matter_audit=audit)


@pytest.fixture
def http_server(mcp_server):
    """McpHttpServer wrapping the McpServer (oauth_required=True by default)."""
    return McpHttpServer(mcp_server=mcp_server)


@pytest.fixture
def http_no_auth(mcp_server):
    """McpHttpServer with oauth_required=False (--no-auth dev mode)."""
    return McpHttpServer(mcp_server=mcp_server, oauth_required=False)


def _bearer_headers(token: str = "test-bearer-xyz") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _decode(body: bytes) -> dict:
    return json.loads(body.decode("utf-8"))


# ===== Init =====


def test_http_server_init_defaults(strong_secrets, mcp_server):
    """Defaults: host='0.0.0.0', port=8765, oauth_required=True."""
    srv = McpHttpServer(mcp_server=mcp_server)
    assert srv.host == "0.0.0.0"
    assert srv.port == 8765
    assert srv.oauth_required is True
    # Reuses the McpServer with 10 tools
    assert len(srv.mcp.list_tools()) == 10


def test_http_server_init_custom_port(strong_secrets, mcp_server):
    """Custom port + host + oauth_required=False."""
    srv = McpHttpServer(
        host="127.0.0.1", port=9999, oauth_required=False, mcp_server=mcp_server
    )
    assert srv.host == "127.0.0.1"
    assert srv.port == 9999
    assert srv.oauth_required is False


# ===== Health =====


def test_http_health_check_returns_200(http_server):
    """GET /mcp/health → 200 + {ok, server, version, tools_count}."""
    status, body, headers = http_server._handle_http_request(
        "GET", "/mcp/health", b"", {}
    )
    assert status == 200
    payload = _decode(body)
    assert payload["ok"] is True
    assert payload["server"] == "ALBRA-MCP"
    assert payload["version"]
    assert payload["tools_count"] == 10
    assert payload["oauth_required"] is True
    assert "Content-Type" in headers


# ===== Initialize =====


def test_http_initialize_returns_server_info(http_server):
    """POST /mcp/initialize → 200 + serverInfo + capabilities + transport=http."""
    status, body, _ = http_server._handle_http_request(
        "POST", "/mcp/initialize", b"{}", _bearer_headers()
    )
    assert status == 200
    payload = _decode(body)
    assert payload["protocolVersion"] == "2024-11-05"
    assert payload["serverInfo"]["name"] == "ALBRA-MCP"
    assert payload["serverInfo"]["version"]
    assert "tools" in payload["capabilities"]
    assert payload["transport"] == "http"
    assert payload["oauth_required"] is True


# ===== Tools list =====


def test_http_tools_list_returns_10_tools(http_server):
    """POST /mcp/tools/list → 200 + tools array of 10 dicts."""
    status, body, _ = http_server._handle_http_request(
        "POST", "/mcp/tools/list", b"{}", _bearer_headers()
    )
    assert status == 200
    payload = _decode(body)
    assert "tools" in payload
    assert len(payload["tools"]) == 10
    expected = {
        "audit_citation", "search_corpus", "verify_deadline",
        "analyze_treatment", "advance_matter", "verify_audit_chain",
        "list_matters", "list_agents", "get_playbook", "run_eval_suite",
    }
    actual = {t["name"] for t in payload["tools"]}
    assert actual == expected
    for t in payload["tools"]:
        assert "description" in t
        assert "inputSchema" in t


# ===== Tools call =====


def test_http_tools_call_audit_citation(http_server):
    """POST /mcp/tools/call audit_citation → 200 + content[0].text JSON."""
    request_body = json.dumps({
        "name": "audit_citation",
        "arguments": {
            "text": "El artículo 13 de la Constitución Política de 1991 garantiza la igualdad.",
        },
    }).encode("utf-8")
    status, body, _ = http_server._handle_http_request(
        "POST", "/mcp/tools/call", request_body, _bearer_headers()
    )
    assert status == 200
    payload = _decode(body)
    assert "content" in payload
    assert len(payload["content"]) == 1
    content = payload["content"][0]
    assert content["type"] == "text"
    inner = json.loads(content["text"])
    assert inner["revealed"] is True
    assert inner["verified_count"] >= 1
    assert payload["isError"] is False


def test_http_tools_call_unknown_returns_error(http_server):
    """POST /mcp/tools/call unknown tool → 200 + isError=True + error in content."""
    request_body = json.dumps({
        "name": "nonexistent_tool_xyz",
        "arguments": {},
    }).encode("utf-8")
    status, body, _ = http_server._handle_http_request(
        "POST", "/mcp/tools/call", request_body, _bearer_headers()
    )
    assert status == 200
    payload = _decode(body)
    assert payload["isError"] is True
    inner = json.loads(payload["content"][0]["text"])
    assert "error" in inner
    assert "nonexistent_tool_xyz" in inner["error"]


# ===== OAuth scaffold =====


def test_http_oauth_metadata_endpoint(http_server):
    """GET /mcp/.well-known/oauth-authorization-server → 200 + metadata."""
    status, body, _ = http_server._handle_http_request(
        "GET", "/mcp/.well-known/oauth-authorization-server", b"", {}
    )
    assert status == 200
    payload = _decode(body)
    assert "issuer" in payload
    assert payload["authorization_endpoint"].endswith("/mcp/oauth/authorize")
    assert payload["token_endpoint"].endswith("/mcp/oauth/token")
    assert "code" in payload["response_types_supported"]
    assert "authorization_code" in payload["grant_types_supported"]
    assert "mcp:tools" in payload["scopes_supported"]


def test_http_oauth_authorize_redirect(http_server):
    """GET /mcp/oauth/authorize?redirect_uri=...&state=xyz → 302 + Location header."""
    path = "/mcp/oauth/authorize?redirect_uri=https://client.example/cb&state=xyz123"
    status, body, headers = http_server._handle_http_request(
        "GET", path, b"", {}
    )
    assert status == 302
    location = headers.get("Location", "")
    assert "https://client.example/cb" in location
    assert "code=albra-code-" in location
    assert "state=xyz123" in location
    # Body is empty for redirect
    assert body == b""
    assert headers.get("Cache-Control") == "no-store"


def test_http_oauth_token_exchange(http_server):
    """POST /mcp/oauth/token with code → 200 + access_token (V2.3-D scaffold)."""
    # Step 1: get a code (no redirect → inline JSON)
    status, body, _ = http_server._handle_http_request(
        "GET", "/mcp/oauth/authorize", b"", {}
    )
    assert status == 200
    code = _decode(body)["code"]
    assert code.startswith("albra-code-")
    # Step 2: exchange code for token
    token_body = json.dumps({
        "grant_type": "authorization_code",
        "code": code,
    }).encode("utf-8")
    status, body, _ = http_server._handle_http_request(
        "POST", "/mcp/oauth/token", token_body, {}
    )
    assert status == 200
    payload = _decode(body)
    assert payload["access_token"].startswith("albra-token-")
    assert payload["token_type"] == "Bearer"
    assert payload["expires_in"] == 3600
    assert payload["scope"] == "mcp:tools"
    # Token should be valid as a bearer now
    assert http_server._is_valid_bearer(payload["access_token"]) is True


def test_http_oauth_token_exchange_form_encoded(http_server):
    """POST /mcp/oauth/token accepts form-encoded body too (OAuth spec)."""
    # Get a code
    _, body, _ = http_server._handle_http_request(
        "GET", "/mcp/oauth/authorize", b"", {}
    )
    code = _decode(body)["code"]
    # Send form-encoded
    form_body = f"grant_type=authorization_code&code={code}".encode("utf-8")
    status, body, _ = http_server._handle_http_request(
        "POST", "/mcp/oauth/token", form_body, {
            "Content-Type": "application/x-www-form-urlencoded",
        }
    )
    assert status == 200
    payload = _decode(body)
    assert payload["access_token"].startswith("albra-token-")


def test_http_oauth_token_rejects_invalid_code(http_server):
    """POST /mcp/oauth/token with unknown code → 400."""
    token_body = json.dumps({
        "grant_type": "authorization_code",
        "code": "albra-code-nonexistent",
    }).encode("utf-8")
    status, body, _ = http_server._handle_http_request(
        "POST", "/mcp/oauth/token", token_body, {}
    )
    assert status == 400
    payload = _decode(body)
    assert "error" in payload


def test_http_oauth_token_rejects_wrong_grant_type(http_server):
    """POST /mcp/oauth/token with grant_type=client_credentials → 400 (scaffold)."""
    token_body = json.dumps({
        "grant_type": "client_credentials",
    }).encode("utf-8")
    status, _, _ = http_server._handle_http_request(
        "POST", "/mcp/oauth/token", token_body, {}
    )
    assert status == 400


# ===== Bearer token validation =====


def test_http_bearer_token_required_when_oauth_enabled(http_server):
    """POST /mcp/initialize without bearer → 401 (oauth_required=True)."""
    status, body, headers = http_server._handle_http_request(
        "POST", "/mcp/initialize", b"{}", {}
    )
    assert status == 401
    payload = _decode(body)
    assert payload["error"] == "unauthorized"
    # WWW-Authenticate header present (OAuth spec)
    assert headers.get("WWW-Authenticate", "").startswith("Bearer")


def test_http_bearer_token_validation_accepts_any_non_empty_v2_3_d(http_server):
    """V2.3-D: any non-empty bearer token is accepted for protected endpoints."""
    # tools/list without bearer → 401
    status_no_bearer, _, _ = http_server._handle_http_request(
        "POST", "/mcp/tools/list", b"{}", {}
    )
    assert status_no_bearer == 401
    # tools/list with non-empty bearer → 200
    status_with_bearer, body, _ = http_server._handle_http_request(
        "POST", "/mcp/tools/list", b"{}", _bearer_headers("any-non-empty-string")
    )
    assert status_with_bearer == 200
    payload = _decode(body)
    assert len(payload["tools"]) == 10


def test_http_no_auth_mode_skips_bearer_check(http_no_auth):
    """With oauth_required=False, protected endpoints skip bearer check."""
    # No Authorization header → still 200 (not 401)
    status, body, _ = http_no_auth._handle_http_request(
        "POST", "/mcp/initialize", b"{}", {}
    )
    assert status == 200
    payload = _decode(body)
    assert payload["oauth_required"] is False


# ===== CORS =====


def test_http_cors_headers_present(http_server):
    """Every response has CORS headers (Allow-Origin, Methods, Headers)."""
    status, _, headers = http_server._handle_http_request(
        "GET", "/mcp/health", b"", {}
    )
    assert status == 200
    assert headers.get("Access-Control-Allow-Origin") == "*"
    assert "GET" in headers.get("Access-Control-Allow-Methods", "")
    assert "POST" in headers.get("Access-Control-Allow-Methods", "")
    assert "OPTIONS" in headers.get("Access-Control-Allow-Methods", "")
    assert "Authorization" in headers.get("Access-Control-Allow-Headers", "")
    assert "Content-Type" in headers.get("Access-Control-Allow-Headers", "")
    assert headers.get("Access-Control-Max-Age") == "86400"


def test_http_options_preflight_returns_204(http_server):
    """OPTIONS preflight → 204 with CORS headers (no body)."""
    status, body, headers = http_server._handle_http_request(
        "OPTIONS", "/mcp/tools/list", b"", {}
    )
    assert status == 204
    assert body == b""
    assert headers.get("Access-Control-Allow-Origin") == "*"


# ===== Errors =====


def test_http_method_not_allowed(http_server):
    """GET on POST-only path → 405 + Allow header."""
    status, body, headers = http_server._handle_http_request(
        "GET", "/mcp/initialize", b"", {}
    )
    assert status == 405
    payload = _decode(body)
    assert payload["error"] == "method_not_allowed"
    assert "GET" in payload["message"]
    assert "/mcp/initialize" in payload["message"]
    # Allow header tells client which methods are valid
    allow = headers.get("Allow", "")
    assert "POST" in allow
    assert "OPTIONS" in allow


def test_http_method_not_allowed_on_health(http_server):
    """POST on GET-only path /mcp/health → 405."""
    # No bearer needed because /mcp/health is public, but the path
    # only supports GET, so POST → 405.
    status, body, _ = http_server._handle_http_request(
        "POST", "/mcp/health", b"{}", {}
    )
    assert status == 405
    payload = _decode(body)
    assert payload["error"] == "method_not_allowed"


def test_http_path_not_found_returns_404(http_server):
    """Unknown path → 404."""
    status, body, _ = http_server._handle_http_request(
        "GET", "/mcp/nonexistent-path", b"", {}
    )
    assert status == 404
    payload = _decode(body)
    assert payload["error"] == "not_found"
    assert "/mcp/nonexistent-path" in payload["message"]


def test_http_invalid_json_body_returns_400(http_server):
    """POST /mcp/tools/call with malformed JSON → 400."""
    status, body, _ = http_server._handle_http_request(
        "POST", "/mcp/tools/call", b"{not valid json", _bearer_headers()
    )
    assert status == 400
    payload = _decode(body)
    assert payload["error"] == "bad_request"


def test_http_tools_call_missing_name_returns_400(http_server):
    """POST /mcp/tools/call without 'name' field → 400."""
    request_body = json.dumps({"arguments": {}}).encode("utf-8")
    status, body, _ = http_server._handle_http_request(
        "POST", "/mcp/tools/call", request_body, _bearer_headers()
    )
    assert status == 400
    payload = _decode(body)
    assert payload["error"] == "bad_request"
    assert "name" in payload["message"]
