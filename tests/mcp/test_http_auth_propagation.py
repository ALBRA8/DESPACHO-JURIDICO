"""Tests de propagación de AuthContext en MCP HTTP (V3.0).

Verifica que el bearer token se convierte en AuthContext real y se pasa
a call_tool. NO más DEV auto-context para HTTP requests.

Escenarios:
1. Token test-abogado → AuthContext role=abogado (no admin)
2. Token test-paralegal → AuthContext role=paralegal
3. Sin token + oauth_required → 401
4. Token vacío → 401
5. Production mode → 401 para todo token (fail-closed)
6. test-abogado intentando eval.run → DENIED (abogado lacks eval.run)
7. test-socio intentando eval.run → ALLOWED
8. Audit entry registra el rol del token (no DEV admin)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from albra.mcp.security import McpAuditLog
from albra.mcp.server import McpHttpServer, McpServer


def _make_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    bearer: str | None = None,
) -> tuple[str, str, bytes, dict[str, str]]:
    """Build HTTP request args for _handle_http_request."""
    body_bytes = json.dumps(body or {}).encode("utf-8") if body else b""
    headers = {}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    return method, path, body_bytes, headers


def _parse_result(status: int, body: bytes, headers: dict) -> dict[str, Any]:
    """Parse the JSON response body."""
    try:
        return json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"_raw": body[:200]}


# ===== 1. Token test-abogado → AuthContext role=abogado =====

def test_http_test_abogado_token_passes_abogado_role(tmp_path):
    """test-abogado token → call_tool receives role=abogado, NOT admin."""
    audit_log = McpAuditLog(str(tmp_path / "mcp_audit.jsonl"))
    # Create a mock McpServer to capture the auth_context
    mock_mcp = MagicMock(spec=McpServer)
    mock_mcp.tools = {}
    mock_mcp._security_mode = "test"
    mock_mcp._mcp_audit = audit_log
    mock_mcp.call_tool.return_value = {"ok": True}

    server = McpHttpServer(
        oauth_required=True,
        mcp_server=mock_mcp,
        auth_mode="test",
    )

    status, body, hdrs = server._handle_http_request(
        *_make_request("POST", "/mcp/tools/call",
                       body={"name": "audit_citation", "arguments": {"text": "test"}},
                       bearer="test-abogado-token-123")
    )

    assert status == 200
    # call_tool was called with auth_context
    call_args = mock_mcp.call_tool.call_args
    assert call_args.kwargs.get("auth_context") is not None
    ctx = call_args.kwargs["auth_context"]
    assert ctx.role == "abogado"
    assert ctx.auth_method == "test"
    assert ctx.identity == "test-user"


# ===== 2. Token test-paralegal → AuthContext role=paralegal =====

def test_http_test_paralegal_token_passes_paralegal_role(tmp_path):
    """test-paralegal token → call_tool receives role=paralegal."""
    mock_mcp = MagicMock(spec=McpServer)
    mock_mcp.tools = {}
    mock_mcp._security_mode = "test"
    mock_mcp._mcp_audit = None
    mock_mcp.call_tool.return_value = {"ok": True}

    server = McpHttpServer(
        oauth_required=True,
        mcp_server=mock_mcp,
        auth_mode="test",
    )

    status, body, hdrs = server._handle_http_request(
        *_make_request("POST", "/mcp/tools/call",
                       body={"name": "audit_citation", "arguments": {"text": "test"}},
                       bearer="test-paralegal-token-456")
    )

    assert status == 200
    ctx = mock_mcp.call_tool.call_args.kwargs["auth_context"]
    assert ctx.role == "paralegal"


# ===== 3. Sin token + oauth_required → 401 =====

def test_http_no_token_returns_401_when_oauth_required():
    """No bearer token + oauth_required=True → 401 Unauthorized."""
    server = McpHttpServer(oauth_required=True, auth_mode="test")
    status, body, hdrs = server._handle_http_request(
        *_make_request("POST", "/mcp/tools/call",
                       body={"name": "audit_citation", "arguments": {"text": "test"}},
                       bearer=None)
    )
    assert status == 401


# ===== 4. Token vacío → 401 =====

def test_http_empty_token_returns_401():
    """Empty bearer token → 401."""
    server = McpHttpServer(oauth_required=True, auth_mode="test")
    status, body, hdrs = server._handle_http_request(
        *_make_request("POST", "/mcp/tools/call",
                       body={"name": "audit_citation", "arguments": {"text": "test"}},
                       bearer="")
    )
    assert status == 401


# ===== 5. Production mode → 401 for all tokens =====

def test_http_production_mode_denies_all_tokens():
    """Production mode: validate_bearer_token returns None for ALL tokens."""
    server = McpHttpServer(oauth_required=True, auth_mode="production")
    status, body, hdrs = server._handle_http_request(
        *_make_request("POST", "/mcp/tools/call",
                       body={"name": "audit_citation", "arguments": {"text": "test"}},
                       bearer="any-token-here")
    )
    assert status == 401


def test_http_production_mode_denies_even_scaffold_tokens():
    """Production mode: even scaffold-issued tokens are rejected."""
    server = McpHttpServer(oauth_required=True, auth_mode="production")
    # Manually add a scaffold token
    server._oauth_tokens.add("scaffold-token-123")
    status, body, hdrs = server._handle_http_request(
        *_make_request("POST", "/mcp/tools/call",
                       body={"name": "audit_citation", "arguments": {"text": "test"}},
                       bearer="scaffold-token-123")
    )
    assert status == 401


# ===== 6. test-abogado intentando eval.run → DENIED =====

def test_http_abogado_denied_for_eval_run(tmp_path):
    """test-abogado token + run_eval_suite → DENIED (abogado lacks eval.run)."""
    # Use a real McpServer (not mock) to test the full chain
    server = McpHttpServer(
        oauth_required=True,
        auth_mode="test",
    )

    status, body, hdrs = server._handle_http_request(
        *_make_request("POST", "/mcp/tools/call",
                       body={"name": "run_eval_suite", "arguments": {}},
                       bearer="test-abogado-token-789")
    )

    result = _parse_result(status, body, hdrs)
    content = result.get("content", [{}])
    if content:
        inner = json.loads(content[0].get("text", "{}"))
        assert inner.get("status") == "DENIED" or inner.get("authorization") == "DENIED"


# ===== 7. test-socio intentando eval.run → ALLOWED =====

def test_http_socio_allowed_for_eval_run(tmp_path):
    """test-socio token + run_eval_suite → ALLOWED (socio has eval.run)."""
    server = McpHttpServer(
        oauth_required=True,
        auth_mode="test",
    )

    status, body, hdrs = server._handle_http_request(
        *_make_request("POST", "/mcp/tools/call",
                       body={"name": "run_eval_suite", "arguments": {}},
                       bearer="test-socio-token-999")
    )

    assert status == 200
    result = _parse_result(status, body, hdrs)
    content = result.get("content", [{}])
    if content:
        inner = json.loads(content[0].get("text", "{}"))
        # Should NOT be DENIED
        assert inner.get("status") != "DENIED"
        assert inner.get("authorization") != "DENIED"


# ===== 8. Audit entry registra el rol del token (no DEV admin) =====

def test_http_audit_entry_records_token_role(tmp_path):
    """Audit entry records the role from the token, not DEV admin."""
    audit_log = McpAuditLog(str(tmp_path / "mcp_audit.jsonl"))
    server = McpHttpServer(
        oauth_required=True,
        auth_mode="test",
        mcp_server=McpServer(security_mode="test", mcp_audit=audit_log),
    )

    server._handle_http_request(
        *_make_request("POST", "/mcp/tools/call",
                       body={"name": "audit_citation", "arguments": {"text": "test"}},
                       bearer="test-paralegal-token-000")
    )

    entries = audit_log.read()
    assert len(entries) >= 1
    entry = entries[-1]
    # The role should be "paralegal" (from the token), NOT "dev-user" or "admin"
    assert entry["role"] == "paralegal"
    assert entry["actor"] == "test-user"
    assert entry["auth_method"] == "test"


# ===== 9. No privilege escalation via tool arguments =====

def test_http_no_role_override_via_arguments(tmp_path):
    """Tool arguments cannot override the role from the token."""
    server = McpHttpServer(
        oauth_required=True,
        auth_mode="test",
        mcp_server=McpServer(security_mode="test", mcp_audit=McpAuditLog(str(tmp_path / "audit.jsonl"))),
    )

    # Try to pass "role": "admin" in the tool arguments
    server._handle_http_request(
        *_make_request("POST", "/mcp/tools/call",
                       body={"name": "audit_citation",
                             "arguments": {"text": "test", "role": "admin"}},
                       bearer="test-paralegal-token-111")
    )

    entries = McpAuditLog(str(tmp_path / "audit.jsonl")).read()
    entry = entries[-1]
    # Role should still be "paralegal" from the token, NOT "admin" from args
    assert entry["role"] == "paralegal"


# ===== 10. Dev mode still works (backward compat) =====

def test_http_dev_mode_accepts_any_token(tmp_path):
    """Dev mode: any non-empty token is accepted (backward compat)."""
    server = McpHttpServer(
        oauth_required=True,
        auth_mode="dev",
        mcp_server=McpServer(security_mode="dev"),
    )

    status, body, hdrs = server._handle_http_request(
        *_make_request("POST", "/mcp/tools/call",
                       body={"name": "audit_citation", "arguments": {"text": "test"}},
                       bearer="any-random-token")
    )

    assert status == 200
