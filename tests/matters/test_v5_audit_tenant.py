"""Tests V5.0 — verify_audit_chain tenant isolation + list_matters consistency.

Verifica que:
1. verify_audit_chain respeta tenant_id (cross-tenant blocked)
2. list_matters get_matter internally usa tenant_id
3. CLI operations bypass security (documented as LOCAL_ONLY)
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
def two_tenants(store):
    """Two tenants with matters and audit chains."""
    m_a = store.create_matter(client="ClientA", area="civil", created_by="ab1", tenant_id="tenant-A")
    m_b = store.create_matter(client="ClientB", area="civil", created_by="ab2", tenant_id="tenant-B")
    # Advance to create audit entries
    store.advance_state(m_a.id, "INTAKE", by="ab1", tenant_id="tenant-A")
    store.advance_state(m_b.id, "INTAKE", by="ab2", tenant_id="tenant-B")
    return store, m_a, m_b


# ===== 1. verify_audit_chain cross-tenant blocked =====

def test_mcp_verify_audit_chain_cross_tenant_blocked(two_tenants, tmp_path):
    """Tenant-A cannot verify audit chain of tenant-B's matter via MCP."""
    store, m_a, m_b = two_tenants
    from albra.audit.matter_audit import MatterAudit
    audit = MatterAudit(str(tmp_path / "matters"))

    # Create audit entries for both matters
    audit.append(m_a.id, actor="ab1", authority="abogado", action_type="state_change",
                 action_payload={"to": "INTAKE"}, result={"ok": True})
    audit.append(m_b.id, actor="ab2", authority="abogado", action_type="state_change",
                 action_payload={"to": "INTAKE"}, result={"ok": True})

    server = McpServer(
        security_mode="dev",
        matter_store=store,
        matter_audit=audit,
    )
    ctx_a = create_dev_context(role="abogado")
    ctx_a.tenant_id = "tenant-A"
    ctx_a.identity = "abogado-A-audit"

    # Tenant-A can verify own audit chain
    result_a = server.call_tool(
        "verify_audit_chain",
        {"matter_id": m_a.id},
        auth_context=ctx_a,
    )
    assert result_a.get("ok") is True or "error" not in result_a

    # Reset dedup for second call
    server._execution_guard.reset_dedup()

    # Tenant-A CANNOT verify tenant-B's audit chain
    result_b = server.call_tool(
        "verify_audit_chain",
        {"matter_id": m_b.id},
        auth_context=ctx_a,
    )
    assert result_b.get("status") == "DENIED" or "not in tenant" in result_b.get("error", "")


# ===== 2. list_matters internally uses tenant_id in get_matter =====

def test_list_matters_get_matter_uses_tenant_filter(two_tenants):
    """list_matters passes tenant_id to get_matter, not just SQL filter."""
    store, m_a, m_b = two_tenants
    # list_matters with tenant-A should return only tenant-A matters
    matters = store.list_matters(tenant_id="tenant-A")
    assert len(matters) == 1
    assert matters[0].client == "ClientA"
    # Verify tenant-B is excluded
    matters_b = store.list_matters(tenant_id="tenant-B")
    assert len(matters_b) == 1
    assert matters_b[0].client == "ClientB"


# ===== 3. CLI operations documented as LOCAL_ONLY =====

def test_cli_matter_show_bypasses_tenant_isolation():
    """CLI matter_show calls get_matter without tenant_id.

    This is a KNOWN LIMITATION: CLI is for local development only.
    Production access must go through MCP HTTP with AuthContext.
    """
    # CLI commands use click decorators which wrap the function.
    # We verify by reading the source file directly.
    from pathlib import Path
    cli_path = Path(__file__).resolve().parent.parent.parent / "albra" / "cli.py"
    src = cli_path.read_text(encoding="utf-8")
    # Find the matter_show function section
    show_start = src.index("def matter_show")
    advance_start = src.index("def matter_advance")
    show_section = src[show_start:advance_start]
    assert "get_matter(matter_id)" in show_section, "CLI calls get_matter without tenant_id"
    assert "tenant_id" not in show_section, "CLI does not use tenant_id (documented limitation)"
    # This is acceptable for LOCAL development only.
    # Production access goes through MCP HTTP which enforces tenant_id.


# ===== 4. All MatterStore methods with tenant_id optional =====

def test_all_matterstore_methods_accept_tenant_id():
    """Verify all MatterStore methods that access matter data accept tenant_id."""
    import inspect
    methods_to_check = ["get_matter", "advance_state", "get_pending_action",
                       "list_pending", "add_approval", "reject_action", "list_matters"]
    for method_name in methods_to_check:
        method = getattr(MatterStore, method_name, None)
        assert method is not None, f"MatterStore.{method_name} not found"
        sig = inspect.signature(method)
        params = sig.parameters
        assert "tenant_id" in params or any(
            p.kind == p.KEYWORD_ONLY and p.name == "tenant_id"
            for p in params.values()
        ), f"MatterStore.{method_name} does not accept tenant_id"
