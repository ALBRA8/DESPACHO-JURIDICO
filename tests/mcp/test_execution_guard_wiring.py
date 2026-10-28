"""Tests adversariales: ExecutionGuard wiring al MCP call_tool chain.

Prueba los 5 escenarios requeridos:
1. RBAC DENY — usuario sin permiso → DENIED
2. RBAC ALLOW + GUARD DENY — RBAC pasa pero kill_switch → DENIED
3. RBAC ALLOW + GUARD ALLOW — todo OK → ALLOWED
4. LEGAL GATE DENY — action con verdict BLOCKED → DENIED
5. AUTHORIZED EXECUTION — full chain passes → tool executes
"""
from __future__ import annotations

import pytest

from albra.mcp.security import (
    AuthContext,
    McpAuditLog,
    create_anonymous_context,
    create_dev_context,
    create_test_context,
)
from albra.mcp.server import McpServer
from albra.security.policy_state import PolicyState

# ===== 1. RBAC DENY =====

def test_rbac_deny_blocks_before_guard():
    """Usuario sin permiso → DENIED at RBAC layer (guard never reached)."""
    server = McpServer(security_mode="dev")
    ctx = create_test_context(role="cliente")  # cliente lacks eval.run
    result = server.call_tool("run_eval_suite", {}, auth_context=ctx)
    assert result["status"] == "DENIED"
    assert result["authorization"] == "DENIED"
    assert "RBAC DENY" in result["error"]
    # Guard was NOT reached (no guard_checks in response)
    assert "guard_checks" not in result


# ===== 2. RBAC ALLOW + GUARD DENY (kill_switch) =====

def test_rbac_allow_but_guard_deny_with_kill_switch(tmp_path):
    """RBAC pasa pero kill_switch=True → guard DENIES."""
    audit_log = McpAuditLog(str(tmp_path / "mcp_audit.jsonl"))
    # PolicyState with kill_switch ON
    policy = PolicyState(kill_switch=True, kill_reason="Emergency shutdown")
    server = McpServer(
        security_mode="dev",
        mcp_audit=audit_log,
        policy_state=policy,
    )
    ctx = create_dev_context(role="admin")  # admin has all permissions
    result = server.call_tool("audit_citation", {"text": "test"}, auth_context=ctx)
    assert result["status"] == "DENIED"
    assert result["authorization"] == "DENIED"
    assert "GUARD DENY" in result["error"]
    assert "guard_checks" in result
    # Audit entry records the denial
    entries = audit_log.read()
    assert any(e["authorization_result"] == "DENIED" for e in entries)


# ===== 3. RBAC ALLOW + GUARD ALLOW =====

def test_rbac_allow_and_guard_allow(tmp_path):
    """RBAC pasa + guard permite → tool executes."""
    audit_log = McpAuditLog(str(tmp_path / "mcp_audit.jsonl"))
    policy = PolicyState()  # default: kill_switch=False
    server = McpServer(
        security_mode="dev",
        mcp_audit=audit_log,
        policy_state=policy,
    )
    ctx = create_dev_context(role="admin")
    result = server.call_tool("audit_citation", {"text": "test"}, auth_context=ctx)
    assert result.get("status") != "DENIED"
    assert result.get("authorization") != "DENIED"
    # Tool executed (not denied)
    assert "error" not in result or result.get("status") != "DENIED"
    # Audit entry records the allowance
    entries = audit_log.read()
    assert any(e["authorization_result"] == "ALLOWED" for e in entries)


# ===== 4. LEGAL GATE DENY =====

def test_legal_gate_blocked_denies_execution(tmp_path):
    """LegalGate verdict BLOCKED → ExecutionGuard DENIES (guard catches it)."""
    from albra.evidence.legal_gate import LegalGate, LegalGateVerdict

    audit_log = McpAuditLog(str(tmp_path / "mcp_audit.jsonl"))

    # Create a LegalGate that always returns BLOCKED
    class BlockingLegalGate(LegalGate):
        def evaluate(self, action, **kwargs):
            return LegalGateVerdict(
                verdict="BLOCKED",
                action=action,
                reason="Test: all actions blocked",
            )

    server = McpServer(
        security_mode="dev",
        mcp_audit=audit_log,
        legal_gate=BlockingLegalGate(),
    )
    ctx = create_dev_context(role="admin")
    result = server.call_tool("audit_citation", {"text": "test"}, auth_context=ctx)
    assert result["status"] == "DENIED"
    assert result["authorization"] == "DENIED"
    # Guard catches the BLOCKED verdict and denies
    assert "GUARD DENY" in result["error"]
    assert "guard_checks" in result


# ===== 5. AUTHORIZED EXECUTION (full chain) =====

def test_authorized_execution_full_chain(tmp_path):
    """Full chain: AUTH → RBAC → LEGALGATE → GUARD → EXECUTE → AUDIT."""
    audit_log = McpAuditLog(str(tmp_path / "mcp_audit.jsonl"))
    server = McpServer(
        security_mode="dev",
        mcp_audit=audit_log,
    )
    ctx = create_dev_context(role="abogado")
    result = server.call_tool(
        "audit_citation",
        {"text": "El artículo 1 de la Constitución Política de 1991"},
        auth_context=ctx,
    )
    # Tool executed successfully
    assert result.get("status") != "DENIED"
    assert result.get("authorization") != "DENIED"
    # Audit trail has the full chain
    entries = audit_log.read()
    assert len(entries) >= 1
    entry = entries[-1]
    assert entry["authorization_result"] == "ALLOWED"
    assert entry["actor"] == "dev-user"
    assert entry["role"] == "abogado"  # from auth_context
    assert entry["tool_name"] == "audit_citation"
    assert entry["action"] == "mcp.tool.call"
    assert entry["input_hash"]
    assert entry["output_hash"]
    assert entry["request_id"] == ctx.request_id


# ===== Additional: RBAC ALLOW does NOT imply guard ALLOW =====

def test_rbac_allow_does_not_imply_execution():
    """Proves that RBAC ALLOW is necessary but NOT sufficient.
    The ExecutionGuard can still deny based on policy/autonomy/legal."""
    # With kill_switch on, even admin gets denied
    policy = PolicyState(kill_switch=True, kill_reason="Test")
    server = McpServer(security_mode="dev", policy_state=policy)
    ctx = create_dev_context(role="admin")
    result = server.call_tool("audit_citation", {"text": "test"}, auth_context=ctx)
    # RBAC passed (admin has all perms), but guard denied (kill_switch)
    assert result["status"] == "DENIED"
    assert "GUARD DENY" in result["error"]
    assert result["authorization"] == "DENIED"


def test_anonymous_denied_at_rbac_not_guard():
    """Anonymous user denied at RBAC layer — guard never reached."""
    server = McpServer(security_mode="dev")
    ctx = create_anonymous_context()
    result = server.call_tool("audit_citation", {"text": "test"}, auth_context=ctx)
    assert result["status"] == "DENIED"
    assert "RBAC DENY" in result["error"]
    # No guard_checks (guard wasn't reached)
    assert "guard_checks" not in result


def test_production_mode_deny_without_auth():
    """Production mode without auth_context → DENIED before RBAC."""
    server = McpServer(security_mode="production")
    result = server.call_tool("audit_citation", {"text": "test"})
    assert result["status"] == "DENIED"
    assert result["authorization"] == "DENIED"
    assert "auth_context required" in result["error"]
