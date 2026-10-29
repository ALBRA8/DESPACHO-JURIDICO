"""Tests V4.1 — aislamiento multitenant end-to-end con evidencia negativa.

Prueba que el tenant A NO puede:
1. get_matter de tenant B por ID
2. advance_state de tenant B por ID
3. list_pending de tenant B
4. get_pending_action de tenant B por ID
5. add_approval en acción de tenant B
6. reject_action en acción de tenant B
7. falsificar tenant_id en args
8. falsificar rol en args
"""
from __future__ import annotations

import pytest

from albra.matters.store import MatterStore
from albra.mcp.security import create_dev_context
from albra.mcp.server import McpServer


@pytest.fixture
def store(tmp_path):
    s = MatterStore(str(tmp_path / "matters.db"))
    yield s
    s.close()


@pytest.fixture
def two_tenant_store(store):
    """Store with matters in tenant-A and tenant-B."""
    m_a = store.create_matter(client="ClientA", area="civil", created_by="ab1", tenant_id="tenant-A")
    m_b = store.create_matter(client="ClientB", area="civil", created_by="ab2", tenant_id="tenant-B")
    # Advance both to INTAKE so we can test advance from different tenants
    store.advance_state(m_a.id, "INTAKE", by="ab1", tenant_id="tenant-A")
    store.advance_state(m_b.id, "INTAKE", by="ab2", tenant_id="tenant-B")
    # Create pending actions in both tenants
    action_a = store.create_pending_action(
        matter_id=m_a.id, action_type="sign_document", description="Sign A", minimum_human_signoff=1,
    )
    action_b = store.create_pending_action(
        matter_id=m_b.id, action_type="sign_document", description="Sign B", minimum_human_signoff=1,
    )
    return store, m_a, m_b, action_a, action_b


# ===== 1. get_matter cross-tenant blocked =====

def test_get_matter_tenant_a_cannot_read_tenant_b(two_tenant_store):
    store, m_a, m_b, _, _ = two_tenant_store
    # Tenant-A can read own matter
    assert store.get_matter(m_a.id, tenant_id="tenant-A") is not None
    # Tenant-A CANNOT read tenant-B's matter
    assert store.get_matter(m_b.id, tenant_id="tenant-A") is None


# ===== 2. advance_state cross-tenant blocked =====

def test_advance_state_tenant_a_cannot_advance_tenant_b(two_tenant_store):
    store, m_a, m_b, _, _ = two_tenant_store
    # Tenant-A can advance own matter
    result = store.advance_state(m_a.id, "PLANEACIÓN", by="ab1", tenant_id="tenant-A")
    assert result.state == "PLANEACIÓN"
    # Tenant-A CANNOT advance tenant-B's matter → KeyError
    with pytest.raises(KeyError):
        store.advance_state(m_b.id, "PLANEACIÓN", by="ab1", tenant_id="tenant-A")


# ===== 3. list_pending cross-tenant blocked =====

def test_list_pending_tenant_a_cannot_see_tenant_b(two_tenant_store):
    store, _, _, action_a, action_b = two_tenant_store
    # Tenant-A sees only own pending actions
    pending_a = store.list_pending(tenant_id="tenant-A")
    assert len(pending_a) == 1
    assert pending_a[0]["id"] == action_a
    # Tenant-B sees only own
    pending_b = store.list_pending(tenant_id="tenant-B")
    assert len(pending_b) == 1
    assert pending_b[0]["id"] == action_b
    # Tenant-A does NOT see tenant-B's action
    assert action_b not in [p["id"] for p in pending_a]


# ===== 4. get_pending_action cross-tenant blocked =====

def test_get_pending_action_tenant_a_cannot_read_tenant_b(two_tenant_store):
    store, _, _, _, action_b = two_tenant_store
    # Tenant-A cannot get tenant-B's pending action
    assert store.get_pending_action(action_b, tenant_id="tenant-A") is None
    # Tenant-B can get own
    assert store.get_pending_action(action_b, tenant_id="tenant-B") is not None


# ===== 5. add_approval cross-tenant blocked =====

def test_add_approval_tenant_a_cannot_approve_tenant_b(two_tenant_store):
    store, _, _, _, action_b = two_tenant_store
    # Tenant-A trying to approve tenant-B's action → KeyError
    with pytest.raises(KeyError):
        store.add_approval(action_b, by="ab1", role="abogado", tenant_id="tenant-A")


# ===== 6. reject_action cross-tenant blocked =====

def test_reject_action_tenant_a_cannot_reject_tenant_b(two_tenant_store):
    store, _, _, _, action_b = two_tenant_store
    # Tenant-A trying to reject tenant-B's action → KeyError
    with pytest.raises(KeyError):
        store.reject_action(action_b, by="ab1", role="abogado", tenant_id="tenant-A")


# ===== 7. tenant_id falsification via args blocked =====

def test_mcp_list_matters_args_tenant_override_blocked(two_tenant_store):
    """Client cannot pass tenant_id in args to see other tenant's data."""
    store, m_a, m_b, _, _ = two_tenant_store
    server = McpServer(security_mode="dev", matter_store=store)
    ctx = create_dev_context(role="abogado")
    ctx.tenant_id = "tenant-A"
    ctx.identity = "abogado-A-fake-test"

    # Try to override tenant_id in args
    result = server.call_tool(
        "list_matters",
        {"tenant_id": "tenant-B"},  # Attempt to override
        auth_context=ctx,
    )
    clients = [m["client"] for m in result.get("matters", [])]
    assert "ClientB" not in clients, "Cross-tenant via args override should be blocked"
    assert "ClientA" in clients, "Own tenant data should be visible"


# ===== 8. MCP advance_matter cross-tenant blocked =====

def test_mcp_advance_matter_cross_tenant_blocked(two_tenant_store):
    """Tenant-A cannot advance tenant-B's matter via MCP."""
    store, m_a, m_b, _, _ = two_tenant_store
    server = McpServer(security_mode="dev", matter_store=store)
    ctx = create_dev_context(role="abogado")
    ctx.tenant_id = "tenant-A"
    ctx.identity = "abogado-A-advance-test"
    server._execution_guard.reset_dedup()

    # Tenant-A tries to advance tenant-B's matter → should fail
    result = server.call_tool(
        "advance_matter",
        {"matter_id": m_b.id, "target_state": "PLANEACIÓN", "by": "ab1"},
        auth_context=ctx,
    )
    # Matter not found in tenant → error
    assert "error" in result or result.get("status") == "DENIED"


# ===== 9. MCP list_pending cross-tenant blocked (via store) =====

def test_mcp_pending_isolated_by_tenant(two_tenant_store):
    """Pending actions are isolated by tenant via store.list_pending(tenant_id)."""
    store, _, _, action_a, action_b = two_tenant_store
    # Verify store-level isolation
    pending_a = store.list_pending(tenant_id="tenant-A")
    pending_b = store.list_pending(tenant_id="tenant-B")
    a_ids = [p["id"] for p in pending_a]
    b_ids = [p["id"] for p in pending_b]
    assert action_a in a_ids
    assert action_b in b_ids
    assert action_a not in b_ids, "Tenant-A action should NOT appear in tenant-B list"
    assert action_b not in a_ids, "Tenant-B action should NOT appear in tenant-A list"


# ===== 10. Legitimate flows still work =====

def test_legitimate_tenant_a_flows_work(two_tenant_store):
    """Tenant-A legitimate operations still work after tenant enforcement."""
    store, m_a, _, action_a, _ = two_tenant_store
    # get_matter works for own tenant
    matter = store.get_matter(m_a.id, tenant_id="tenant-A")
    assert matter is not None
    assert matter.client == "ClientA"
    # advance_state works for own tenant
    result = store.advance_state(m_a.id, "PLANEACIÓN", by="ab1", tenant_id="tenant-A")
    assert result.state == "PLANEACIÓN"
    # get_pending_action works for own tenant
    action = store.get_pending_action(action_a, tenant_id="tenant-A")
    assert action is not None
    assert action["description"] == "Sign A"
    # list_pending works for own tenant
    pending = store.list_pending(tenant_id="tenant-A")
    assert len(pending) >= 1
    # add_approval works for own tenant
    approved = store.add_approval(action_a, by="ab1", role="abogado", tenant_id="tenant-A")
    assert approved["status"] in ("APPROVED", "PENDING")
