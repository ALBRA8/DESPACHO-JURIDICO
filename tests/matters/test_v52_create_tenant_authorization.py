"""Tests V5.2 — cierre acotado de cobertura multitenant en operaciones
de creación y escritura del almacén.

V5.2 cierra la brecha de cobertura identificada en la auditoría
independiente de V5.1: ``MatterStore.create_matter()`` y
``MatterStore.create_pending_action()`` no aplicaban ``_require_tenant()``,
aunque el informe V5.1 declaraba que la autorización multitenant estaba
cerrada en todas las operaciones del almacén.

Adicionalmente, ``ApprovalChain.suggest()`` no propagaba ``tenant_id`` a
``create_pending_action``, y ``ApprovalChain.mark_executed()`` tenía una
escritura SQL directa que la auditoría V5.2 pidió revisar.

V5.2 closes:

  1. ``create_matter``: bajo ``enforce_tenant=True``, ``tenant_id`` es
     obligatorio y debe ser autorizado (no None/""/"default").
  2. ``create_pending_action``: bajo ``enforce_tenant=True``, ``tenant_id``
     es obligatorio Y el ``matter_id`` debe existir y pertenecer al
     tenant autorizado. La verificación ocurre ANTES de cualquier escritura
     SQL — no se persisten filas parciales.
  3. ``ApprovalChain.suggest``: propaga ``tenant_id`` al almacén.
  4. ``ApprovalChain.mark_executed``: auditado — la escritura SQL directa
     está precedida por dos verificaciones de tenant, no hay bypass.

Las pruebas invocan las operaciones reales (no inspección textual del
código) y verifican:

  - Creación de matter sin tenant → denegada en modo estricto.
  - Creación de matter con tenant válido → funciona y queda asociada
    al tenant correcto.
  - Creación de acción pendiente sin tenant válido → denegada.
  - Tenant A intenta crear acción sobre matter de B → denegado y sin
    cambios en la base de datos.
  - Tenant A no puede aprobar, rechazar ni marcar como ejecutada una
    acción de B.
  - Operaciones legítimas del mismo tenant siguen funcionando.
  - Denegaciones no revelan datos del otro tenant.
  - Rutas de producción no pueden desactivar ``enforce_tenant`` vía
    argumentos del cliente.
  - No hay escrituras parciales ni cambios persistidos tras una
    denegación.
"""
from __future__ import annotations

import pytest

from albra.matters.store import MatterStore, TenantAuthorizationError
from albra.security.approval_chain import (
    ApprovalChain,
    ApprovalChainError,
    InsufficientSignoffsError,
)


@pytest.fixture
def strict_store(tmp_path):
    """MatterStore with enforce_tenant=True (production-like)."""
    s = MatterStore(str(tmp_path / "matters.db"), enforce_tenant=True)
    yield s
    s.close()


@pytest.fixture
def legacy_store(tmp_path):
    """MatterStore with enforce_tenant=False (dev/test/CLI local)."""
    s = MatterStore(str(tmp_path / "matters.db"))
    yield s
    s.close()


# ===== 1. create_matter without tenant → denied in strict mode =====

def test_create_matter_without_tenant_denied_in_strict_mode(strict_store):
    """create_matter with no tenant_id under enforce_tenant=True → raises."""
    with pytest.raises(TenantAuthorizationError, match="Tenant authorization required"):
        strict_store.create_matter(client="X", area="civil")


def test_create_matter_with_none_tenant_denied_in_strict_mode(strict_store):
    """create_matter with tenant_id=None → raises."""
    with pytest.raises(TenantAuthorizationError):
        strict_store.create_matter(client="X", area="civil", tenant_id=None)


def test_create_matter_with_empty_tenant_denied_in_strict_mode(strict_store):
    """create_matter with tenant_id='' → raises."""
    with pytest.raises(TenantAuthorizationError):
        strict_store.create_matter(client="X", area="civil", tenant_id="")


def test_create_matter_with_default_tenant_denied_in_strict_mode(strict_store):
    """create_matter with tenant_id='default' (placeholder) → raises."""
    with pytest.raises(TenantAuthorizationError):
        strict_store.create_matter(client="X", area="civil", tenant_id="default")


# ===== 2. create_matter with valid tenant → works and is associated correctly =====

def test_create_matter_with_valid_tenant_associates_correctly(strict_store):
    """create_matter with authorized tenant_id works; matter is
    persisted with the correct tenant_id (not 'default').
    """
    m = strict_store.create_matter(
        client="Alice", area="civil", created_by="ab1", tenant_id="tenant-A",
    )
    assert m.id is not None
    # Verify the matter is actually associated with tenant-A (not default)
    fetched = strict_store.get_matter(m.id, tenant_id="tenant-A")
    assert fetched is not None
    assert fetched.client == "Alice"
    # Cross-tenant read returns None (not the matter)
    assert strict_store.get_matter(m.id, tenant_id="tenant-B") is None


def test_create_matter_strict_mode_does_not_persist_on_deny(strict_store, tmp_path):
    """When create_matter raises TenantAuthorizationError, no row is
    persisted in the matters table.

    V5.2 brief: "Verificar que no haya escrituras parciales ni cambios
    persistidos tras una denegación."
    """
    import sqlite3
    db_path = str(strict_store.db_path)
    # Count matters before
    conn = sqlite3.connect(db_path)
    count_before = conn.execute("SELECT COUNT(*) FROM matters").fetchone()[0]
    conn.close()

    # Attempt to create without tenant → raises
    with pytest.raises(TenantAuthorizationError):
        strict_store.create_matter(client="X", area="civil")

    # Count matters after — must be unchanged
    conn = sqlite3.connect(db_path)
    count_after = conn.execute("SELECT COUNT(*) FROM matters").fetchone()[0]
    conn.close()

    assert count_after == count_before, (
        f"No matter should be persisted after a deny. "
        f"Before={count_before}, after={count_after}"
    )


# ===== 3. create_pending_action without valid tenant → denied =====

def test_create_pending_action_without_tenant_denied_in_strict_mode(strict_store):
    """create_pending_action with no tenant_id under enforce_tenant=True
    → raises. The matter_id is provided (it exists in the store) but
    the tenant_id is missing, so the guard fires before any write.
    """
    # Seed a matter with a valid tenant
    m = strict_store.create_matter(
        client="Alice", area="civil", created_by="ab1", tenant_id="tenant-A",
    )
    # Try to create pending action without tenant_id
    with pytest.raises(TenantAuthorizationError, match="Tenant authorization required"):
        strict_store.create_pending_action(
            matter_id=m.id, action_type="sign_document", description="x",
        )


def test_create_pending_action_with_default_tenant_denied(strict_store):
    """create_pending_action with tenant_id='default' → raises."""
    m = strict_store.create_matter(
        client="Alice", area="civil", created_by="ab1", tenant_id="tenant-A",
    )
    with pytest.raises(TenantAuthorizationError):
        strict_store.create_pending_action(
            matter_id=m.id, action_type="sign_document", description="x",
            tenant_id="default",
        )


# ===== 4. Tenant A creates pending action on Tenant B's matter → denied =====

def test_create_pending_action_cross_tenant_denied_and_no_db_change(strict_store, tmp_path):
    """Tenant A tries to create a pending action on Tenant B's matter_id.

    V5.2: the cross-tenant creation guard must:
      1. Raise (KeyError, not TenantAuthorizationError, because the
         tenant_id IS authorized — the matter_id just doesn't belong to
         this tenant).
      2. NOT persist any row in pending_actions.
    """
    import sqlite3
    # Seed a matter in tenant-B
    m_b = strict_store.create_matter(
        client="BobSecret", area="civil", created_by="ab2", tenant_id="tenant-B",
    )

    db_path = str(strict_store.db_path)
    conn = sqlite3.connect(db_path)
    count_before = conn.execute("SELECT COUNT(*) FROM pending_actions").fetchone()[0]
    conn.close()

    # Tenant-A tries to create a pending action on tenant-B's matter
    with pytest.raises(KeyError, match="is not in the authorized tenant"):
        strict_store.create_pending_action(
            matter_id=m_b.id, action_type="sign_document", description="evil",
            tenant_id="tenant-A",
        )

    # No row should have been persisted
    conn = sqlite3.connect(db_path)
    count_after = conn.execute("SELECT COUNT(*) FROM pending_actions").fetchone()[0]
    conn.close()
    assert count_after == count_before, (
        f"No pending action should be persisted after a cross-tenant deny. "
        f"Before={count_before}, after={count_after}"
    )


def test_create_pending_action_with_nonexistent_matter_denied(strict_store, tmp_path):
    """Under enforce_tenant=True, creating a pending action on a
    nonexistent matter_id raises KeyError (cross-tenant guard treats
    'not found' the same as 'not in tenant' to avoid leaking info).
    """
    with pytest.raises(KeyError, match="is not in the authorized tenant"):
        strict_store.create_pending_action(
            matter_id="nonexistent-matter-id",
            action_type="sign_document", description="x",
            tenant_id="tenant-A",
        )


# ===== 5. Tenant A cannot approve, reject, or mark_executed Tenant B's action =====

def test_tenant_a_cannot_approve_tenant_b_action(strict_store):
    """Tenant A tries to approve Tenant B's pending action → ApprovalChainError."""
    # Seed tenant-B matter + pending action
    m_b = strict_store.create_matter(
        client="BobSecret", area="civil", created_by="ab2", tenant_id="tenant-B",
    )
    action_b = strict_store.create_pending_action(
        matter_id=m_b.id, action_type="sign_document", description="x",
        tenant_id="tenant-B",
    )
    chain = ApprovalChain(strict_store)
    # Tenant-A tries to approve
    with pytest.raises(ApprovalChainError):
        chain.approve(action_b, by="attacker", role="abogado", tenant_id="tenant-A")
    # Tenant-B's action status must remain PENDING (not APPROVED)
    action = strict_store.get_pending_action(action_b, tenant_id="tenant-B")
    assert action["status"] == "PENDING"


def test_tenant_a_cannot_reject_tenant_b_action(strict_store):
    """Tenant A tries to reject Tenant B's pending action → ApprovalChainError."""
    m_b = strict_store.create_matter(
        client="BobSecret", area="civil", created_by="ab2", tenant_id="tenant-B",
    )
    action_b = strict_store.create_pending_action(
        matter_id=m_b.id, action_type="sign_document", description="x",
        tenant_id="tenant-B",
    )
    chain = ApprovalChain(strict_store)
    with pytest.raises(ApprovalChainError):
        chain.reject(action_b, by="attacker", role="abogado", tenant_id="tenant-A")
    action = strict_store.get_pending_action(action_b, tenant_id="tenant-B")
    assert action["status"] == "PENDING"


def test_tenant_a_cannot_mark_executed_tenant_b_action(strict_store):
    """Tenant A tries to mark_executed Tenant B's action → ApprovalChainError.

    V5.2 audit: this test exercises the direct-SQL-write path of
    ApprovalChain.mark_executed. The audit verified that the write is
    preceded by two tenant checks (get_pending_action + can_execute),
    so cross-tenant mark_executed is blocked before the SQL UPDATE.
    """
    m_b = strict_store.create_matter(
        client="BobSecret", area="civil", created_by="ab2", tenant_id="tenant-B",
    )
    action_b = strict_store.create_pending_action(
        matter_id=m_b.id, action_type="sign_document", description="x",
        tenant_id="tenant-B",
    )
    # Tenant-B approves the action first
    chain = ApprovalChain(strict_store)
    chain.approve(action_b, by="ab2", role="abogado", tenant_id="tenant-B")
    # Verify it's APPROVED
    action = strict_store.get_pending_action(action_b, tenant_id="tenant-B")
    assert action["status"] == "APPROVED"

    # Tenant-A tries to mark_executed → ApprovalChainError (action not
    # found from tenant-A's perspective).
    with pytest.raises(ApprovalChainError, match="Pending action not found"):
        chain.mark_executed(action_b, by="attacker", tenant_id="tenant-A")

    # The status must NOT have changed — still APPROVED, not EXECUTED.
    action_after = strict_store.get_pending_action(action_b, tenant_id="tenant-B")
    assert action_after["status"] == "APPROVED", (
        f"Cross-tenant mark_executed must not mutate status. "
        f"Expected APPROVED, got {action_after['status']}"
    )


# ===== 6. Same-tenant legitimate operations still work =====

def test_same_tenant_create_pending_action_works(strict_store):
    """Tenant-A creates a pending action on Tenant-A's own matter → works."""
    m = strict_store.create_matter(
        client="Alice", area="civil", created_by="ab1", tenant_id="tenant-A",
    )
    action_id = strict_store.create_pending_action(
        matter_id=m.id, action_type="sign_document", description="legit",
        tenant_id="tenant-A",
    )
    action = strict_store.get_pending_action(action_id, tenant_id="tenant-A")
    assert action is not None
    assert action["description"] == "legit"
    assert action["status"] == "PENDING"


def test_same_tenant_approve_and_mark_executed_works(strict_store):
    """Full approval chain in the same tenant works end-to-end."""
    m = strict_store.create_matter(
        client="Alice", area="civil", created_by="ab1", tenant_id="tenant-A",
    )
    action_id = strict_store.create_pending_action(
        matter_id=m.id, action_type="sign_document", description="x",
        tenant_id="tenant-A",
    )
    chain = ApprovalChain(strict_store)
    # Approve
    approved = chain.approve(action_id, by="ab1", role="abogado", tenant_id="tenant-A")
    assert approved["status"] == "APPROVED"
    # Mark executed
    executed = chain.mark_executed(action_id, by="ab1", tenant_id="tenant-A")
    assert executed["status"] == "EXECUTED"


def test_same_tenant_reject_works(strict_store):
    """Tenant-A rejects its own pending action → works."""
    m = strict_store.create_matter(
        client="Alice", area="civil", created_by="ab1", tenant_id="tenant-A",
    )
    action_id = strict_store.create_pending_action(
        matter_id=m.id, action_type="sign_document", description="x",
        tenant_id="tenant-A",
    )
    chain = ApprovalChain(strict_store)
    rejected = chain.reject(
        action_id, by="ab1", role="abogado", tenant_id="tenant-A",
        comment="bad",
    )
    assert rejected["status"] == "REJECTED"


# ===== 7. Denials do not leak other tenants' data =====

def test_cross_tenant_create_pending_action_error_does_not_leak(strict_store):
    """When Tenant A tries to create a pending action on Tenant B's
    matter, the error message must NOT reveal Tenant B's client name
    or tenant identifier.

    V5.2 brief: "Las denegaciones no revelan datos del otro tenant."
    """
    m_b = strict_store.create_matter(
        client="SECRET_BOB_CLIENT", area="civil", created_by="ab2",
        tenant_id="tenant-SECRET-B",
    )
    try:
        strict_store.create_pending_action(
            matter_id=m_b.id, action_type="sign_document", description="x",
            tenant_id="tenant-A",
        )
        raise AssertionError("Should have raised KeyError on cross-tenant create")
    except KeyError as e:
        msg = str(e)
        # Must not leak tenant-B's client name or tenant identifier
        assert "SECRET_BOB_CLIENT" not in msg, (
            f"Error must not leak tenant-B's client name. Got: {msg}"
        )
        assert "tenant-SECRET-B" not in msg, (
            f"Error must not leak tenant-B's identifier. Got: {msg}"
        )


# ===== 8. Client cannot disable enforce_tenant via args =====

def test_client_cannot_disable_enforce_tenant_via_args(strict_store):
    """The enforce_tenant flag is set at MatterStore construction time
    and CANNOT be toggled by the client via args.

    V5.2 brief: "Verificar que las rutas de producción no puedan
    seleccionar o desactivar enforce_tenant mediante argumentos del
    cliente."
    """
    # The store has enforce_tenant=True (set in __init__). There's no
    # public API to toggle it. Verify the attribute is read-only-ish
    # (we can't stop someone from setting _enforce_tenant directly via
    # Python reflection, but no legitimate API path exposes it).
    assert strict_store._enforce_tenant is True

    # Calling create_matter without tenant_id raises — proving the
    # flag is still active.
    with pytest.raises(TenantAuthorizationError):
        strict_store.create_matter(client="X", area="civil")

    # Even if a client tries to pass an "enforce_tenant=False" kwarg
    # to create_matter (which would be ignored anyway since it's not
    # a parameter), the guard still fires.
    with pytest.raises(TypeError):
        # create_matter doesn't accept enforce_tenant kwarg → TypeError
        strict_store.create_matter(
            client="X", area="civil", enforce_tenant=False,
        )


def test_client_cannot_pass_tenant_id_in_unexpected_args(strict_store):
    """A client cannot smuggle a tenant_id into create_pending_action
    via an unexpected kwarg name (e.g. '_tenant_id', 'tenant', etc.).

    The only accepted parameter name is 'tenant_id'. Any other name
    raises TypeError, which means the guard still fires for the
    missing real 'tenant_id'.
    """
    m = strict_store.create_matter(
        client="X", area="civil", created_by="ab1", tenant_id="tenant-A",
    )
    # Smuggling via 'tenant' (not the real param name) → TypeError
    with pytest.raises(TypeError):
        strict_store.create_pending_action(
            matter_id=m.id, action_type="sign_document", description="x",
            tenant="tenant-A",  # wrong name
        )


# ===== 9. No partial writes after a denial =====

def test_no_partial_matter_after_deny(strict_store, tmp_path):
    """If create_matter raises (e.g. tenant_id missing), the matters
    table must NOT have a partial row.

    V5.2 brief: "Verificar que no haya escrituras parciales ni cambios
    persistidos tras una denegación."
    """
    import sqlite3
    db_path = str(strict_store.db_path)

    conn = sqlite3.connect(db_path)
    count_before = conn.execute("SELECT COUNT(*) FROM matters").fetchone()[0]
    conn.close()

    with pytest.raises(TenantAuthorizationError):
        strict_store.create_matter(client="Ghost", area="civil")

    conn = sqlite3.connect(db_path)
    count_after = conn.execute("SELECT COUNT(*) FROM matters").fetchone()[0]
    # Also verify no party rows leaked
    parties_after = conn.execute("SELECT COUNT(*) FROM parties").fetchone()[0]
    conn.close()

    assert count_after == count_before, (
        f"Partial matter row leaked. Before={count_before}, after={count_after}"
    )
    assert parties_after == 0, "No party rows should exist after a deny"


def test_no_partial_pending_action_after_cross_tenant_deny(strict_store, tmp_path):
    """If create_pending_action raises (cross-tenant), the
    pending_actions table must NOT have a partial row."""
    import sqlite3
    m_b = strict_store.create_matter(
        client="Bob", area="civil", created_by="ab2", tenant_id="tenant-B",
    )
    db_path = str(strict_store.db_path)

    conn = sqlite3.connect(db_path)
    count_before = conn.execute("SELECT COUNT(*) FROM pending_actions").fetchone()[0]
    conn.close()

    with pytest.raises(KeyError):
        strict_store.create_pending_action(
            matter_id=m_b.id, action_type="sign_document", description="evil",
            tenant_id="tenant-A",
        )

    conn = sqlite3.connect(db_path)
    count_after = conn.execute("SELECT COUNT(*) FROM pending_actions").fetchone()[0]
    conn.close()
    assert count_after == count_before


# ===== 10. ApprovalChain.suggest threads tenant_id =====

def test_approval_chain_suggest_without_tenant_denied_in_strict_mode(strict_store):
    """ApprovalChain.suggest without tenant_id under enforce_tenant=True
    raises TenantAuthorizationError (threaded from create_pending_action).
    """
    m = strict_store.create_matter(
        client="X", area="civil", created_by="ab1", tenant_id="tenant-A",
    )
    chain = ApprovalChain(strict_store)
    with pytest.raises(TenantAuthorizationError):
        chain.suggest(
            matter_id=m.id, action_type="sign_document", description="x",
        )


def test_approval_chain_suggest_cross_tenant_denied(strict_store):
    """ApprovalChain.suggest with tenant-A but matter_id belonging to
    tenant-B → raises KeyError (no DB write).
    """
    m_b = strict_store.create_matter(
        client="Bob", area="civil", created_by="ab2", tenant_id="tenant-B",
    )
    chain = ApprovalChain(strict_store)
    with pytest.raises(KeyError):
        chain.suggest(
            matter_id=m_b.id, action_type="sign_document", description="evil",
            tenant_id="tenant-A",
        )


def test_approval_chain_suggest_same_tenant_works(strict_store):
    """ApprovalChain.suggest with same tenant works end-to-end."""
    m = strict_store.create_matter(
        client="Alice", area="civil", created_by="ab1", tenant_id="tenant-A",
    )
    chain = ApprovalChain(strict_store)
    action_id = chain.suggest(
        matter_id=m.id, action_type="sign_document", description="legit",
        tenant_id="tenant-A",
    )
    assert action_id is not None
    action = strict_store.get_pending_action(action_id, tenant_id="tenant-A")
    assert action is not None


# ===== 11. Legacy mode (enforce_tenant=False) preserves behavior =====

def test_legacy_create_matter_without_tenant_uses_default(legacy_store):
    """V5.2 regression: under enforce_tenant=False, create_matter
    without tenant_id defaults to 'default' (legacy dev behavior).
    """
    m = legacy_store.create_matter(client="X", area="civil")
    # The matter is in the 'default' tenant (legacy behavior preserved)
    fetched = legacy_store.get_matter(m.id)  # no tenant_id → finds it
    assert fetched is not None
    assert fetched.client == "X"


def test_legacy_create_pending_action_without_tenant_works(legacy_store):
    """V5.2 regression: under enforce_tenant=False, create_pending_action
    without tenant_id works (no cross-tenant check).
    """
    m = legacy_store.create_matter(client="X", area="civil")
    action_id = legacy_store.create_pending_action(
        matter_id=m.id, action_type="sign_document", description="x",
    )
    assert action_id is not None
    action = legacy_store.get_pending_action(action_id)
    assert action is not None


def test_legacy_approval_chain_suggest_without_tenant_works(legacy_store):
    """V5.2 regression: ApprovalChain.suggest under enforce_tenant=False
    preserves the V5.1 dev-mode behavior.
    """
    m = legacy_store.create_matter(client="X", area="civil")
    chain = ApprovalChain(legacy_store)
    action_id = chain.suggest(
        matter_id=m.id, action_type="sign_document", description="x",
    )
    assert action_id is not None
