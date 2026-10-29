"""Tests V5.1 — cross-tenant negative tests against MCP production mode.

V5.1: this suite exercises the McpServer production-mode fail-closed
behavior and the cross-tenant isolation that the existing V4.1 suite
covered only at the store layer.

All tests invoke the real McpServer.call_tool path (no mocks) and verify
the actual denial result, not signature presence.

Coverage:
  A. Production fail-closed when AuthContext.tenant_id is missing
     / empty / "default".
  B. Cross-tenant blocked through MCP production mode:
       - get_matter via verify_audit_chain
       - advance_matter
       - list_matters
  C. Same-tenant legitimate operations still succeed in production mode.
  D. Errors do not leak other tenants' data (no content, only DENIED).
  E. Client cannot forge tenant_id via args.
"""
from __future__ import annotations

import os

import pytest

from albra.matters.store import MatterStore, TenantAuthorizationError
from albra.mcp.security import AuthContext, create_dev_context
from albra.mcp.server import McpServer


@pytest.fixture
def store(tmp_path):
    """MatterStore with enforce_tenant=False so the McpServer can still
    seed data through dev-only paths (e.g. create_matter). Production
    enforcement is exercised via the McpServer's own lazy store or via
    explicit enforce_tenant=True construction below.
    """
    s = MatterStore(str(tmp_path / "matters.db"))
    yield s
    s.close()


@pytest.fixture
def two_tenant_store(store):
    """Seed two tenants with matters, audit, and pending actions."""
    m_a = store.create_matter(
        client="ClientA", area="civil", created_by="ab1", tenant_id="tenant-A",
    )
    m_b = store.create_matter(
        client="ClientB", area="civil", created_by="ab2", tenant_id="tenant-B",
    )
    store.advance_state(m_a.id, "INTAKE", by="ab1", tenant_id="tenant-A")
    store.advance_state(m_b.id, "INTAKE", by="ab2", tenant_id="tenant-B")
    action_a = store.create_pending_action(
        matter_id=m_a.id, action_type="sign_document", description="Sign A",
    )
    action_b = store.create_pending_action(
        matter_id=m_b.id, action_type="sign_document", description="Sign B",
    )
    return store, m_a, m_b, action_a, action_b


def _ctx(tenant: str, role: str = "abogado", identity: str | None = None) -> AuthContext:
    """Build a real AuthContext with the given tenant."""
    ctx = create_dev_context(role=role)
    ctx.tenant_id = tenant
    ctx.identity = identity or f"{role}-{tenant}"
    return ctx


# ===== A. Production fail-closed when tenant_id missing/empty/default =====

def test_production_list_matters_denies_default_tenant(two_tenant_store, tmp_path):
    """In production, list_matters with the default AuthContext.tenant_id
    ('default') returns DENIED — never an unfiltered list.
    """
    store, _, _, _, _ = two_tenant_store
    server = McpServer(security_mode="production", matter_store=store)
    # ctx_default has tenant_id == "default" (the AuthContext placeholder)
    ctx_default = create_dev_context(role="abogado")
    assert ctx_default.tenant_id == "default"  # sanity
    server._execution_guard.reset_dedup()
    result = server.call_tool("list_matters", {}, auth_context=ctx_default)
    assert result.get("status") == "DENIED"
    assert result.get("authorization") == "DENIED"
    assert "FAIL-CLOSED" in result.get("error", "")
    # The denial MUST NOT leak any other tenant's data
    assert "matters" not in result, (
        f"Denied list_matters must not include a matters list. Got: {result}"
    )


def test_production_list_matters_denies_none_tenant(two_tenant_store):
    """In production, list_matters with tenant_id=None (cleared by tampering)
    returns DENIED.
    """
    store, _, _, _, _ = two_tenant_store
    server = McpServer(security_mode="production", matter_store=store)
    ctx = _ctx("tenant-A")
    ctx.tenant_id = None  # tampered
    server._execution_guard.reset_dedup()
    result = server.call_tool("list_matters", {}, auth_context=ctx)
    assert result.get("status") == "DENIED"


def test_production_list_matters_denies_empty_tenant(two_tenant_store):
    """In production, list_matters with tenant_id='' returns DENIED."""
    store, _, _, _, _ = two_tenant_store
    server = McpServer(security_mode="production", matter_store=store)
    ctx = _ctx("tenant-A")
    ctx.tenant_id = ""  # tampered
    server._execution_guard.reset_dedup()
    result = server.call_tool("list_matters", {}, auth_context=ctx)
    assert result.get("status") == "DENIED"


def test_production_advance_matter_denies_default_tenant(two_tenant_store):
    """In production, advance_matter with default tenant returns DENIED —
    never writes anything.
    """
    store, m_a, _, _, _ = two_tenant_store
    server = McpServer(security_mode="production", matter_store=store)
    ctx_default = create_dev_context(role="abogado")
    server._execution_guard.reset_dedup()
    result = server.call_tool(
        "advance_matter",
        {"matter_id": m_a.id, "target_state": "PLANEACIÓN", "by": "ab1"},
        auth_context=ctx_default,
    )
    assert result.get("status") == "DENIED"
    # The matter state MUST NOT have changed
    fresh = store.get_matter(m_a.id, tenant_id="tenant-A")
    assert fresh.state == "INTAKE", (
        "Production DENY must not mutate the matter. State should still "
        "be INTAKE."
    )


def test_production_verify_audit_chain_denies_default_tenant(two_tenant_store, tmp_path):
    """In production, verify_audit_chain with default tenant returns DENIED
    — never reads the audit chain.
    """
    from albra.audit.matter_audit import MatterAudit
    store, m_a, _, _, _ = two_tenant_store
    audit = MatterAudit(str(tmp_path / "matters"))
    audit.append(m_a.id, actor="ab1", authority="abogado", action_type="state_change",
                action_payload={"to": "INTAKE"}, result={"ok": True})

    server = McpServer(
        security_mode="production", matter_store=store, matter_audit=audit,
    )
    ctx_default = create_dev_context(role="abogado")
    server._execution_guard.reset_dedup()
    result = server.call_tool(
        "verify_audit_chain",
        {"matter_id": m_a.id},
        auth_context=ctx_default,
    )
    assert result.get("status") == "DENIED"
    # No audit chain contents may leak
    assert "ok" not in result, "Denied verify_audit_chain must not leak chain ok/total."


# ===== B. Cross-tenant blocked through MCP production mode =====

def test_production_cross_tenant_list_matters(two_tenant_store):
    """Tenant-A's call_tool('list_matters') in production mode does NOT
    see tenant-B's matters.
    """
    store, m_a, m_b, _, _ = two_tenant_store
    server = McpServer(security_mode="production", matter_store=store)
    ctx_a = _ctx("tenant-A", identity="abogado-prod-list-A")
    server._execution_guard.reset_dedup()
    result = server.call_tool("list_matters", {}, auth_context=ctx_a)
    # Production ctx_a has a real tenant → not denied at the gate
    assert result.get("status") != "DENIED", (
        f"Tenant-A legitimate list_matters should not be denied in production. "
        f"Got: {result}"
    )
    matter_ids = {m["id"] for m in result.get("matters", [])}
    assert m_a.id in matter_ids
    assert m_b.id not in matter_ids, (
        "Tenant-A must not see tenant-B's matter via production list_matters."
    )


def test_production_cross_tenant_advance_matter(two_tenant_store):
    """Tenant-A cannot advance tenant-B's matter via production MCP."""
    store, _, m_b, _, _ = two_tenant_store
    server = McpServer(security_mode="production", matter_store=store)
    ctx_a = _ctx("tenant-A", identity="abogado-prod-advance-A")
    server._execution_guard.reset_dedup()
    result = server.call_tool(
        "advance_matter",
        {"matter_id": m_b.id, "target_state": "PLANEACIÓN", "by": "ab1"},
        auth_context=ctx_a,
    )
    # The matter doesn't exist in tenant-A → KeyError becomes ERROR result
    assert "error" in result, (
        "Cross-tenant advance must produce an error result (KeyError → ERROR)."
    )
    # The matter state MUST NOT have changed in tenant-B
    fresh = store.get_matter(m_b.id, tenant_id="tenant-B")
    assert fresh.state == "INTAKE", (
        "Cross-tenant advance must not mutate tenant-B's matter."
    )


def test_production_cross_tenant_verify_audit_chain(two_tenant_store, tmp_path):
    """Tenant-A cannot verify tenant-B's audit chain via production MCP."""
    from albra.audit.matter_audit import MatterAudit
    store, _, m_b, _, _ = two_tenant_store
    audit = MatterAudit(str(tmp_path / "matters"))
    audit.append(m_b.id, actor="ab2", authority="abogado", action_type="state_change",
                action_payload={"to": "INTAKE"}, result={"ok": True})
    server = McpServer(
        security_mode="production", matter_store=store, matter_audit=audit,
    )
    ctx_a = _ctx("tenant-A", identity="abogado-prod-verify-A")
    server._execution_guard.reset_dedup()
    result = server.call_tool(
        "verify_audit_chain",
        {"matter_id": m_b.id},
        auth_context=ctx_a,
    )
    assert result.get("status") == "DENIED", (
        "Cross-tenant verify_audit_chain must be DENIED."
    )
    assert "ok" not in result


# ===== C. Same-tenant legitimate operations still succeed =====

def test_production_same_tenant_list_matters_succeeds(two_tenant_store):
    """Tenant-A's legitimate list_matters works in production mode."""
    store, m_a, _, _, _ = two_tenant_store
    server = McpServer(security_mode="production", matter_store=store)
    ctx_a = _ctx("tenant-A", identity="abogado-prod-list-A-legit")
    server._execution_guard.reset_dedup()
    result = server.call_tool("list_matters", {}, auth_context=ctx_a)
    assert result.get("status") != "DENIED"
    assert result.get("count") == 1
    assert result["matters"][0]["client"] == "ClientA"


def test_production_same_tenant_advance_matter_succeeds(two_tenant_store):
    """Tenant-A's legitimate advance_matter works in production mode."""
    store, m_a, _, _, _ = two_tenant_store
    server = McpServer(security_mode="production", matter_store=store)
    ctx_a = _ctx("tenant-A", identity="abogado-prod-advance-A-legit")
    server._execution_guard.reset_dedup()
    result = server.call_tool(
        "advance_matter",
        {"matter_id": m_a.id, "target_state": "PLANEACIÓN", "by": "ab1"},
        auth_context=ctx_a,
    )
    # Either success (state=PLANEACIÓN) or a deterministic state machine
    # rejection — but NOT a DENIED status (authorization passed).
    assert result.get("status") != "DENIED", (
        f"Same-tenant advance_matter in production must not be denied. Got: {result}"
    )
    if "error" not in result:
        assert result["state"] == "PLANEACIÓN"


def test_production_same_tenant_verify_audit_chain_succeeds(two_tenant_store, tmp_path):
    """Tenant-A's legitimate verify_audit_chain works in production mode."""
    from albra.audit.matter_audit import MatterAudit
    store, m_a, _, _, _ = two_tenant_store
    audit = MatterAudit(str(tmp_path / "matters"))
    audit.append(m_a.id, actor="ab1", authority="abogado", action_type="state_change",
                action_payload={"to": "INTAKE"}, result={"ok": True})
    server = McpServer(
        security_mode="production", matter_store=store, matter_audit=audit,
    )
    ctx_a = _ctx("tenant-A", identity="abogado-prod-verify-A-legit")
    server._execution_guard.reset_dedup()
    result = server.call_tool(
        "verify_audit_chain",
        {"matter_id": m_a.id},
        auth_context=ctx_a,
    )
    assert result.get("ok") is True, (
        f"Same-tenant verify_audit_chain in production must succeed. Got: {result}"
    )


# ===== D. Errors do not leak other tenants' data =====

def test_production_cross_tenant_error_does_not_leak_data(two_tenant_store):
    """When tenant-A tries to advance tenant-B's matter, the error message
    must not mention tenant-B's client name or other identifying info.
    """
    store, _, m_b, _, _ = two_tenant_store
    server = McpServer(security_mode="production", matter_store=store)
    ctx_a = _ctx("tenant-A", identity="abogado-prod-leak-A")
    server._execution_guard.reset_dedup()
    result = server.call_tool(
        "advance_matter",
        {"matter_id": m_b.id, "target_state": "PLANEACIÓN", "by": "ab1"},
        auth_context=ctx_a,
    )
    error_text = str(result)
    # Must not leak tenant-B's client identifier
    assert "ClientB" not in error_text, (
        f"Error must not leak tenant-B's client name. Got: {error_text}"
    )
    assert "tenant-B" not in error_text, (
        f"Error must not leak tenant-B's identifier. Got: {error_text}"
    )


# ===== E. Client cannot forge tenant_id via args =====

def test_production_client_cannot_forge_tenant_via_args(two_tenant_store):
    """Client passes tenant_id='tenant-B' in args, but the production
    McpServer ignores client-supplied tenant_id and uses the AuthContext's
    tenant_id. The result must reflect tenant-A only.
    """
    store, m_a, m_b, _, _ = two_tenant_store
    server = McpServer(security_mode="production", matter_store=store)
    ctx_a = _ctx("tenant-A", identity="abogado-prod-forge-A")
    server._execution_guard.reset_dedup()
    # Attacker includes tenant_id in args
    result = server.call_tool(
        "list_matters",
        {"tenant_id": "tenant-B"},  # attempt to forge
        auth_context=ctx_a,
    )
    matter_ids = {m["id"] for m in result.get("matters", [])}
    assert m_a.id in matter_ids, "Own tenant data should be visible"
    assert m_b.id not in matter_ids, (
        "Forged tenant_id in args must be ignored; tenant-B's data must not leak."
    )


def test_production_client_cannot_forge_tenant_via_metadata(two_tenant_store):
    """Client passes _auth metadata in args; the production McpServer must
    still use the AuthContext resolved by the security layer, not the
    client-supplied _auth.
    """
    store, m_a, m_b, _, _ = two_tenant_store
    server = McpServer(security_mode="production", matter_store=store)
    ctx_a = _ctx("tenant-A", identity="abogado-prod-forge-meta-A")
    server._execution_guard.reset_dedup()
    # Attacker includes _auth.tenant_id in args
    result = server.call_tool(
        "list_matters",
        {"_auth": {"tenant_id": "tenant-B", "identity": "evil", "role": "admin"}},
        auth_context=ctx_a,
    )
    # The injected _auth.tenant_id is replaced by call_tool (not merged), so
    # tenant-B's data must not leak.
    matter_ids = {m["id"] for m in result.get("matters", [])}
    assert m_a.id in matter_ids, "Own tenant data should be visible"
    assert m_b.id not in matter_ids, (
        "Client-supplied _auth.tenant_id must not override AuthContext."
    )


# ===== F. ApprovalChain tenant isolation (defense in depth) =====

def test_approval_chain_cross_tenant_approve_blocked(two_tenant_store):
    """ApprovalChain.approve with tenant_id='tenant-A' cannot approve
    tenant-B's action.
    """
    from albra.security.approval_chain import ApprovalChain, ApprovalChainError
    store, _, _, _, action_b = two_tenant_store
    chain = ApprovalChain(store)
    # Tenant-A tries to approve tenant-B's action → ApprovalChainError
    with pytest.raises(ApprovalChainError):
        chain.approve(
            action_b, by="ab1", role="abogado", tenant_id="tenant-A",
        )


def test_approval_chain_cross_tenant_reject_blocked(two_tenant_store):
    """ApprovalChain.reject with tenant_id='tenant-A' cannot reject
    tenant-B's action.
    """
    from albra.security.approval_chain import ApprovalChain, ApprovalChainError
    store, _, _, _, action_b = two_tenant_store
    chain = ApprovalChain(store)
    with pytest.raises(ApprovalChainError):
        chain.reject(
            action_b, by="ab1", role="abogado", tenant_id="tenant-A",
        )


def test_approval_chain_cross_tenant_get_status_blocked(two_tenant_store):
    """ApprovalChain.get_status with tenant_id='tenant-A' returns None for
    tenant-B's action (not the action itself).
    """
    from albra.security.approval_chain import ApprovalChain
    store, _, _, _, action_b = two_tenant_store
    chain = ApprovalChain(store)
    # Tenant-A asking for tenant-B's action → None (not found from this tenant)
    assert chain.get_status(action_b, tenant_id="tenant-A") is None
    # Tenant-B asking for own action → present
    assert chain.get_status(action_b, tenant_id="tenant-B") is not None


def test_approval_chain_same_tenant_approve_succeeds(two_tenant_store):
    """ApprovalChain.approve with the correct tenant_id succeeds (regression)."""
    from albra.security.approval_chain import ApprovalChain
    store, _, _, action_a, _ = two_tenant_store
    chain = ApprovalChain(store)
    updated = chain.approve(
        action_a, by="ab1", role="abogado", tenant_id="tenant-A",
    )
    assert updated["status"] == "APPROVED"
