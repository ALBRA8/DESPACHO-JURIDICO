"""Tests de ApprovalChain con minimum_human_signoff."""
from __future__ import annotations

import pytest

from albra.matters.store import MatterStore
from albra.security.approval_chain import (
    ApprovalChain,
    ApprovalChainError,
    InsufficientSignoffsError,
    UnauthorizedRoleError,
)


@pytest.fixture
def store(tmp_path):
    s = MatterStore(str(tmp_path / "matters.db"))
    yield s
    s.close()


@pytest.fixture
def chain(store):
    return ApprovalChain(store)


@pytest.fixture
def matter_id(store):
    m = store.create_matter(client="X", area="civil", created_by="ab1")
    return m.id


# ===== suggest =====

def test_suggest_creates_pending_action(chain, matter_id):
    action_id = chain.suggest(
        matter_id=matter_id,
        action_type="publish_legal_filing",
        description="Presentar tutela ante juez 23 civil",
    )
    assert action_id
    action = chain.get_status(action_id)
    assert action["status"] == "PENDING"
    assert action["minimum_human_signoff"] == 1
    assert action["action_type"] == "publish_legal_filing"
    assert action["description"] == "Presentar tutela ante juez 23 civil"


def test_suggest_uses_default_signoffs_per_action_type(chain, matter_id):
    a1 = chain.suggest(matter_id=matter_id, action_type="sign_document", description="x")
    assert chain.get_status(a1)["minimum_human_signoff"] == 1

    a2 = chain.suggest(matter_id=matter_id, action_type="accept_contract", description="x")
    assert chain.get_status(a2)["minimum_human_signoff"] == 2

    a3 = chain.suggest(matter_id=matter_id, action_type="modify_permissions", description="x")
    assert chain.get_status(a3)["minimum_human_signoff"] == 2


def test_suggest_unknown_action_type_defaults_to_1(chain, matter_id):
    a = chain.suggest(matter_id=matter_id, action_type="unknown_action", description="x")
    assert chain.get_status(a)["minimum_human_signoff"] == 1


# ===== approve =====

def test_approve_with_abogado_for_publish_legal_filing(chain, matter_id):
    action_id = chain.suggest(
        matter_id=matter_id, action_type="publish_legal_filing",
        description="Presentar tutela",
    )
    updated = chain.approve(action_id, by="abogado1", role="abogado", comment="visto bueno")
    assert updated["status"] == "APPROVED"
    assert len(updated["approvals"]) == 1
    assert updated["approvals"][0]["by"] == "abogado1"
    assert updated["approvals"][0]["role"] == "abogado"


def test_approve_with_socio_also_works_for_filing(chain, matter_id):
    action_id = chain.suggest(
        matter_id=matter_id, action_type="publish_legal_filing", description="x"
    )
    updated = chain.approve(action_id, by="socio1", role="socio")
    assert updated["status"] == "APPROVED"


def test_approve_with_paralegal_rejected_for_filing(chain, matter_id):
    """Paralegal NO puede firmar radicación legal."""
    action_id = chain.suggest(
        matter_id=matter_id, action_type="publish_legal_filing", description="x"
    )
    with pytest.raises(UnauthorizedRoleError):
        chain.approve(action_id, by="paralegal1", role="paralegal")


def test_approve_with_cliente_rejected_for_filing(chain, matter_id):
    """Cliente NO puede firmar radicación legal."""
    action_id = chain.suggest(
        matter_id=matter_id, action_type="publish_legal_filing", description="x"
    )
    with pytest.raises(UnauthorizedRoleError):
        chain.approve(action_id, by="cliente1", role="cliente")


def test_approve_unknown_role_raises(chain, matter_id):
    action_id = chain.suggest(
        matter_id=matter_id, action_type="publish_legal_filing", description="x"
    )
    with pytest.raises(UnauthorizedRoleError):
        chain.approve(action_id, by="x", role="superadmin")


def test_approve_accept_contract_requires_2_different_signoffs(chain, matter_id):
    """accept_contract requiere 2 firmas con roles distintos (abogado + cliente)."""
    action_id = chain.suggest(
        matter_id=matter_id,
        action_type="accept_contract",
        description="Aceptar contrato de honorarios",
    )
    # Primera firma: abogado → sigue PENDING
    a1 = chain.approve(action_id, by="abogado1", role="abogado", comment="revisé")
    assert a1["status"] == "PENDING"
    # Misma persona intenta firmar otra vez → debe rechazar
    with pytest.raises(UnauthorizedRoleError):
        chain.approve(action_id, by="abogado1", role="abogado")
    # Segunda firma: cliente → APRUEBA
    a2 = chain.approve(action_id, by="cliente1", role="cliente", comment="acepto")
    assert a2["status"] == "APPROVED"


def test_approve_cannot_approve_already_decided(chain, matter_id):
    action_id = chain.suggest(
        matter_id=matter_id, action_type="publish_legal_filing", description="x"
    )
    chain.approve(action_id, by="abogado1", role="abogado")
    with pytest.raises(ApprovalChainError):
        chain.approve(action_id, by="abogado2", role="abogado")


def test_approve_nonexistent_action_raises(chain):
    with pytest.raises(ApprovalChainError):
        chain.approve("nonexistent", by="x", role="abogado")


# ===== reject =====

def test_reject_with_abogado(chain, matter_id):
    action_id = chain.suggest(
        matter_id=matter_id, action_type="publish_legal_filing", description="x"
    )
    rejected = chain.reject(action_id, by="abogado1", role="abogado", comment="rechazado")
    assert rejected["status"] == "REJECTED"


def test_reject_with_paralegal_rejected(chain, matter_id):
    action_id = chain.suggest(
        matter_id=matter_id, action_type="publish_legal_filing", description="x"
    )
    with pytest.raises(UnauthorizedRoleError):
        chain.reject(action_id, by="paralegal1", role="paralegal")


# ===== can_execute =====

def test_can_execute_returns_false_when_pending(chain, matter_id):
    action_id = chain.suggest(
        matter_id=matter_id, action_type="publish_legal_filing", description="x"
    )
    can, reason = chain.can_execute(action_id)
    assert not can
    assert "pending" in reason.lower()


def test_can_execute_returns_true_when_approved(chain, matter_id):
    action_id = chain.suggest(
        matter_id=matter_id, action_type="publish_legal_filing", description="x"
    )
    chain.approve(action_id, by="abogado1", role="abogado")
    can, reason = chain.can_execute(action_id)
    assert can
    assert "All approvals" in reason


def test_can_execute_returns_false_when_rejected(chain, matter_id):
    action_id = chain.suggest(
        matter_id=matter_id, action_type="publish_legal_filing", description="x"
    )
    chain.reject(action_id, by="abogado1", role="abogado")
    can, reason = chain.can_execute(action_id)
    assert not can
    assert "rejected" in reason.lower()


def test_can_execute_returns_false_for_nonexistent(chain):
    can, reason = chain.can_execute("nonexistent")
    assert not can
    assert "not found" in reason.lower()


# ===== mark_executed =====

def test_mark_executed_after_approval(chain, matter_id):
    action_id = chain.suggest(
        matter_id=matter_id, action_type="publish_legal_filing", description="x"
    )
    chain.approve(action_id, by="abogado1", role="abogado")
    executed = chain.mark_executed(action_id, by="system")
    assert executed["status"] == "EXECUTED"


def test_mark_executed_without_approval_raises(chain, matter_id):
    action_id = chain.suggest(
        matter_id=matter_id, action_type="publish_legal_filing", description="x"
    )
    with pytest.raises(InsufficientSignoffsError):
        chain.mark_executed(action_id, by="system")


def test_mark_executed_after_rejection_raises(chain, matter_id):
    action_id = chain.suggest(
        matter_id=matter_id, action_type="publish_legal_filing", description="x"
    )
    chain.reject(action_id, by="abogado1", role="abogado")
    with pytest.raises(InsufficientSignoffsError):
        chain.mark_executed(action_id, by="system")


def test_mark_executed_idempotent_fails_second_time(chain, matter_id):
    action_id = chain.suggest(
        matter_id=matter_id, action_type="publish_legal_filing", description="x"
    )
    chain.approve(action_id, by="abogado1", role="abogado")
    chain.mark_executed(action_id, by="system")
    with pytest.raises(InsufficientSignoffsError):
        chain.mark_executed(action_id, by="system")


# ===== Workflow completo =====

def test_full_workflow_suggest_approve_execute(chain, matter_id):
    """Flujo completo: Suggest → Approve → Execute."""
    action_id = chain.suggest(
        matter_id=matter_id,
        action_type="sign_document",
        description="Firmar contrato de honorarios cliente X",
    )
    chain.approve(action_id, by="abogado1", role="abogado", comment="revisé cláusulas")
    chain.mark_executed(action_id, by="system")
    final = chain.get_status(action_id)
    assert final["status"] == "EXECUTED"
    assert len(final["approvals"]) == 1
    assert final["decided_by"] == "system"


def test_full_workflow_accept_contract_with_two_signoffs(chain, matter_id):
    """accept_contract requiere 2 firmas (abogado + cliente)."""
    action_id = chain.suggest(
        matter_id=matter_id,
        action_type="accept_contract",
        description="Aceptar contrato M&A",
    )
    chain.approve(action_id, by="abogado1", role="abogado", comment="revisé términos")
    can, _ = chain.can_execute(action_id)
    assert not can
    chain.approve(action_id, by="cliente1", role="cliente", comment="acepto en mi nombre")
    can, _ = chain.can_execute(action_id)
    assert can
    chain.mark_executed(action_id, by="system")


# ===== list_pending =====

def test_list_pending_for_matter(chain, matter_id, store):
    a1 = chain.suggest(matter_id=matter_id, action_type="sign_document", description="x")
    a2 = chain.suggest(matter_id=matter_id, action_type="publish_legal_filing", description="y")
    pending = chain.list_pending_for_matter(matter_id)
    assert len(pending) == 2
    chain.approve(a1, by="abogado1", role="abogado")
    pending = chain.list_pending_for_matter(matter_id)
    assert len(pending) == 1
    assert pending[0]["id"] == a2


def test_list_all_pending(chain, store):
    m1 = store.create_matter(client="A", area="civil", created_by="ab1")
    m2 = store.create_matter(client="B", area="civil", created_by="ab1")
    chain.suggest(matter_id=m1.id, action_type="sign_document", description="x")
    chain.suggest(matter_id=m2.id, action_type="publish_legal_filing", description="y")
    pending = chain.list_all_pending()
    assert len(pending) == 2


# ===== Edge cases =====

def test_agent_cannot_bypass_signoff(chain, matter_id):
    """El agente NO puede ejecutar sin firmas (anti-autonomía total)."""
    action_id = chain.suggest(
        matter_id=matter_id,
        action_type="publish_legal_filing",
        description="Presentar tutela",
    )
    with pytest.raises(InsufficientSignoffsError):
        chain.mark_executed(action_id, by="agent-ALBRA")


def test_minimum_human_signoff_zero_default_rejected_at_suggest(chain, matter_id):
    """Aún si se intenta crear acción con signoff=0, el sistema fuerza ≥1."""
    action_id = chain.suggest(
        matter_id=matter_id, action_type="unknown_type", description="x"
    )
    assert chain.get_status(action_id)["minimum_human_signoff"] >= 1
