"""Tests adversariales del MCP security layer (V2.6 HARDENING).

Demuestra:
1. usuario sin identidad → DENIED
2. identidad sin permiso → DENIED
3. permiso incorrecto → DENIED
4. herramienta no permitida → DENIED
5. input inválido → DENIED
6. operación peligrosa → DENIED
7. operación autorizada → ALLOWED
8. todo acceso queda registrado en audit
"""
from __future__ import annotations

import json
import os
import tempfile

import pytest

from albra.mcp.security import (
    AUTH_MODES,
    ROLE_PERMISSIONS,
    TOOL_PERMISSIONS,
    AuthContext,
    McpAuditEntry,
    McpAuditLog,
    check_tool_permission,
    create_anonymous_context,
    create_auth_context,
    create_dev_context,
    create_test_context,
    validate_bearer_token,
)

# ===== AuthContext tests =====

def test_anonymous_context_has_no_permissions():
    ctx = create_anonymous_context()
    assert ctx.role == "anonymous"
    assert ctx.permissions == set()
    assert ctx.auth_method == "none"


def test_dev_context_has_admin_permissions():
    ctx = create_dev_context()
    assert ctx.role == "admin"
    assert "admin.*" in ctx.permissions
    assert ctx.auth_method == "dev"
    assert ctx.has_permission("anything")  # wildcard


def test_test_context_role_specific():
    ctx = create_test_context(role="abogado")
    assert ctx.role == "abogado"
    assert "matters.advance" in ctx.permissions
    assert not ctx.has_permission("eval.run")


def test_create_auth_context_unknown_role_raises():
    with pytest.raises(ValueError):
        create_auth_context(identity="x", role="superadmin")


# ===== 1. usuario sin identidad → DENIED =====

def test_anonymous_denied_for_all_tools():
    ctx = create_anonymous_context()
    for tool_name in TOOL_PERMISSIONS:
        allowed, reason = check_tool_permission(tool_name, ctx)
        assert not allowed, f"{tool_name} should be denied for anonymous"
        assert "lacks permission" in reason


# ===== 2. identidad sin permiso → DENIED =====

def test_paralegal_denied_for_eval_suite():
    """eval.run requires socio+ — paralegal should be denied."""
    ctx = create_test_context(role="paralegal")
    allowed, reason = check_tool_permission("run_eval_suite", ctx)
    assert not allowed
    assert "eval.run" in reason


def test_cliente_denied_for_advance_matter():
    """matters.advance requires abogado+ — cliente should be denied."""
    ctx = create_test_context(role="cliente")
    allowed, reason = check_tool_permission("advance_matter", ctx)
    assert not allowed
    assert "matters.advance" in reason


# ===== 3. permiso incorrecto → DENIED =====

def test_wrong_permission_denied():
    """A context with only 'tools.invoke' cannot run eval."""
    ctx = AuthContext(
        identity="limited-user",
        role="custom",
        permissions={"tools.invoke"},
        auth_method="test",
    )
    allowed, reason = check_tool_permission("run_eval_suite", ctx)
    assert not allowed
    assert "eval.run" in reason


# ===== 4. herramienta no permitida → DENIED =====

def test_custom_tool_defaults_to_tools_invoke():
    """Tools not in TOOL_PERMISSIONS default to 'tools.invoke'."""
    ctx = create_test_context(role="paralegal")
    allowed, reason = check_tool_permission("some_custom_tool", ctx)
    assert allowed  # paralegal has tools.invoke
    assert reason == ""


def test_anonymous_denied_for_custom_tool():
    """Anonymous (no permissions) cannot call even custom tools."""
    ctx = create_anonymous_context()
    allowed, reason = check_tool_permission("some_custom_tool", ctx)
    assert not allowed
    assert "lacks permission" in reason


# ===== 5. input inválido → DENIED =====

def test_mcp_server_denies_production_without_auth_context():
    """In production mode, call_tool without auth_context → DENY."""
    from albra.mcp.server import McpServer
    server = McpServer(security_mode="production")
    result = server.call_tool("audit_citation", {"text": "test"})
    assert result["status"] == "DENIED"
    assert result["authorization"] == "DENIED"
    assert "auth_context required" in result["error"]


def test_mcp_server_denies_unknown_tool():
    from albra.mcp.server import McpServer
    server = McpServer(security_mode="dev")
    result = server.call_tool("nonexistent_tool", {})
    assert "error" in result
    assert result.get("status") == "NOT_FOUND"


# ===== 6. operación peligrosa → DENIED =====

def test_dangerous_operation_denied_for_low_role():
    """advance_matter is 'matters.advance' — requires abogado+."""
    from albra.mcp.server import McpServer
    server = McpServer(security_mode="dev")
    ctx = create_test_context(role="cliente")  # cliente lacks matters.advance
    result = server.call_tool("advance_matter", {"matter_id": "x", "target": "INTAKE"}, auth_context=ctx)
    assert result["status"] == "DENIED"
    assert result["authorization"] == "DENIED"
    assert "matters.advance" in result["reason"]


# ===== 7. operación autorizada → ALLOWED =====

def test_authorized_operation_allowed():
    from albra.mcp.server import McpServer
    server = McpServer(security_mode="dev")
    ctx = create_test_context(role="abogado")  # abogado has matters.advance
    # advance_matter will fail because no real MatterStore, but should NOT be DENIED
    result = server.call_tool("advance_matter", {"matter_id": "nonexistent", "target": "INTAKE"}, auth_context=ctx)
    assert result.get("status") != "DENIED"
    assert result.get("authorization") != "DENIED"


def test_admin_allowed_for_all_tools():
    """Admin (wildcard) can access any tool."""
    ctx = create_dev_context(role="admin")
    for tool_name in TOOL_PERMISSIONS:
        allowed, _ = check_tool_permission(tool_name, ctx)
        assert allowed, f"Admin should be allowed for {tool_name}"


# ===== 8. todo acceso queda registrado en audit =====

def test_audit_log_records_allowed_call(tmp_path):
    """Allowed tool calls generate audit entries."""
    from albra.mcp.server import McpServer
    audit_log = McpAuditLog(str(tmp_path / "mcp_audit.jsonl"))
    server = McpServer(security_mode="dev", mcp_audit=audit_log)
    ctx = create_dev_context(role="admin")
    server.call_tool("audit_citation", {"text": "test"}, auth_context=ctx)
    entries = audit_log.read()
    assert len(entries) >= 1
    entry = entries[-1]
    assert entry["authorization_result"] == "ALLOWED"
    assert entry["actor"] == "dev-user"
    assert entry["tool_name"] == "audit_citation"
    assert entry["input_hash"]
    assert entry["output_hash"]


def test_audit_log_records_denied_call(tmp_path):
    """Denied tool calls ALSO generate audit entries."""
    from albra.mcp.server import McpServer
    audit_log = McpAuditLog(str(tmp_path / "mcp_audit.jsonl"))
    server = McpServer(security_mode="dev", mcp_audit=audit_log)
    ctx = create_test_context(role="cliente")  # lacks matters.advance
    server.call_tool("advance_matter", {"matter_id": "x"}, auth_context=ctx)
    entries = audit_log.read()
    assert len(entries) >= 1
    entry = entries[-1]
    assert entry["authorization_result"] == "DENIED"
    assert entry["denial_reason"]
    assert entry["result_status"] == "denied"


def test_audit_log_records_production_deny(tmp_path):
    """Production-mode deny (no auth) is also audited."""
    from albra.mcp.server import McpServer
    audit_log = McpAuditLog(str(tmp_path / "mcp_audit.jsonl"))
    server = McpServer(security_mode="production", mcp_audit=audit_log)
    server.call_tool("audit_citation", {"text": "test"})
    entries = audit_log.read()
    assert len(entries) >= 1
    entry = entries[-1]
    assert entry["authorization_result"] == "DENIED"
    assert entry["actor"] == "anonymous"


def test_audit_entry_no_secrets_stored(tmp_path):
    """Audit entries must NOT store secrets, tokens, or passwords."""
    from albra.mcp.server import McpServer
    audit_log = McpAuditLog(str(tmp_path / "mcp_audit.jsonl"))
    server = McpServer(security_mode="dev", mcp_audit=audit_log)
    ctx = create_dev_context(role="admin")
    # Call with args that look like they might contain secrets
    server.call_tool("audit_citation", {"text": "some text with ghp_secret123"}, auth_context=ctx)
    entries = audit_log.read()
    entry_str = json.dumps(entries[-1])
    # The audit entry stores input_hash (SHA-256), NOT the raw input
    assert "ghp_secret123" not in entry_str
    assert "password" not in entry_str.lower()
    assert "token" not in entry_str.lower()


# ===== McpAuditLog tests =====

def test_audit_log_read_filter_by_tool(tmp_path):
    log = McpAuditLog(str(tmp_path / "audit.jsonl"))
    entry1 = McpAuditEntry(
        timestamp="2026-01-01T00:00:00Z", request_id="r1", actor="user1",
        role="abogado", auth_method="test", tool_name="audit_citation",
        action="mcp.tool.call", authorization_result="ALLOWED", denial_reason="",
        input_hash="abc", output_hash="def", matter_id="", correlation_id="r1",
        result_status="success", error="", latency_ms=10.0, environment="test",
    )
    entry2 = McpAuditEntry(
        timestamp="2026-01-01T00:00:01Z", request_id="r2", actor="user2",
        role="cliente", auth_method="test", tool_name="advance_matter",
        action="mcp.tool.call", authorization_result="DENIED", denial_reason="no perm",
        input_hash="ghi", output_hash="", matter_id="m1", correlation_id="r2",
        result_status="denied", error="no perm", latency_ms=5.0, environment="test",
    )
    log.record(entry1)
    log.record(entry2)
    all_entries = log.read()
    assert len(all_entries) == 2
    filtered = log.read(tool_name="audit_citation")
    assert len(filtered) == 1
    assert filtered[0]["tool_name"] == "audit_citation"


def test_audit_log_count(tmp_path):
    log = McpAuditLog(str(tmp_path / "audit.jsonl"))
    assert log.count() == 0
    for i in range(5):
        entry = McpAuditEntry(
            timestamp=f"2026-01-01T00:00:0{i}Z", request_id=f"r{i}", actor="x",
            role="admin", auth_method="dev", tool_name="test",
            action="mcp.tool.call", authorization_result="ALLOWED", denial_reason="",
            input_hash="h", output_hash="h", matter_id="", correlation_id=f"r{i}",
            result_status="success", error="", latency_ms=1.0, environment="dev",
        )
        log.record(entry)
    assert log.count() == 5


# ===== validate_bearer_token tests =====

def test_validate_bearer_dev_mode_accepts_any_non_empty():
    ctx = validate_bearer_token("any-token-here", mode="dev")
    assert ctx is not None
    assert ctx.auth_method == "dev"


def test_validate_bearer_dev_mode_with_prefix():
    ctx = validate_bearer_token("dev-admin-my-token", mode="dev")
    assert ctx is not None
    assert ctx.role == "admin"


def test_validate_bearer_test_mode_with_role_prefix():
    ctx = validate_bearer_token("test-socio-abc", mode="test")
    assert ctx is not None
    assert ctx.role == "socio"


def test_validate_bearer_production_mode_returns_none():
    """Production mode requires real OAuth — not implemented → None."""
    ctx = validate_bearer_token("any-token", mode="production")
    assert ctx is None


def test_validate_bearer_empty_token_returns_none():
    ctx = validate_bearer_token("", mode="dev")
    assert ctx is None


def test_validate_bearer_test_mode_with_valid_tokens_set():
    ctx = validate_bearer_token("my-secret-token", valid_tokens={"my-secret-token"}, mode="test")
    assert ctx is not None


def test_validate_bearer_test_mode_rejects_unknown_token():
    ctx = validate_bearer_token("wrong-token", valid_tokens={"correct-token"}, mode="test")
    assert ctx is None


# ===== ROLE_PERMISSIONS sanity =====

def test_all_roles_have_expected_permissions():
    assert "tools.invoke" in ROLE_PERMISSIONS["paralegal"]
    assert "matters.advance" in ROLE_PERMISSIONS["abogado"]
    assert "eval.run" in ROLE_PERMISSIONS["socio"]
    assert ROLE_PERMISSIONS["anonymous"] == set()
    assert "admin.*" in ROLE_PERMISSIONS["admin"]


def test_auth_modes_has_dev_test_production():
    assert "dev" in AUTH_MODES
    assert "test" in AUTH_MODES
    assert "production" in AUTH_MODES


# ===== TOOL_PERMISSIONS sanity =====

def test_all_10_tools_have_permission_mapping():
    expected_tools = {
        "audit_citation", "search_corpus", "verify_deadline", "analyze_treatment",
        "advance_matter", "verify_audit_chain", "list_matters", "list_agents",
        "get_playbook", "run_eval_suite",
    }
    assert set(TOOL_PERMISSIONS.keys()) == expected_tools
