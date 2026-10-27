"""Tests del PaidAgentMatrix (X402 paid-agent matrix con USDC settlement)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from albra.marketplace.paid_agent_matrix import (
    BillingCycle,
    PaidAgentMatrix,
    ServiceMatrix,
    UsageRecord,
)


@pytest.fixture
def matrix(tmp_path):
    m = PaidAgentMatrix(str(tmp_path / "paid.db"))
    yield m
    m.close()


# ===== Service matrix =====

def test_set_pricing_returns_service_matrix(matrix):
    sm = matrix.set_pricing(
        skill_id="citation-auditor",
        price_per_call_usd=0.05,
        price_per_month_usd=10.0,
        free_tier_calls_per_month=100,
    )
    assert isinstance(sm, ServiceMatrix)
    assert sm.skill_id == "citation-auditor"
    assert sm.price_per_call_usd == 0.05
    assert sm.price_per_month_usd == 10.0
    assert sm.free_tier_calls_per_month == 100


def test_set_pricing_idempotent(matrix):
    matrix.set_pricing(skill_id="x", price_per_call_usd=0.01)
    matrix.set_pricing(skill_id="x", price_per_call_usd=0.05)  # update
    sm = matrix.get_pricing("x")
    assert sm.price_per_call_usd == 0.05


def test_get_pricing_nonexistent_returns_none(matrix):
    assert matrix.get_pricing("nonexistent") is None


def test_deactivate_pricing(matrix):
    matrix.set_pricing(skill_id="x")
    assert matrix.deactivate_pricing("x") is True
    sm = matrix.get_pricing("x")
    assert sm.active is False


def test_deactivate_nonexistent_returns_false(matrix):
    assert matrix.deactivate_pricing("nonexistent") is False


# ===== Usage recording =====

def test_record_usage_returns_usage_record(matrix):
    matrix.set_pricing(skill_id="x", price_per_call_usd=0.10, free_tier_calls_per_month=5)
    record = matrix.record_usage(tenant_id="t1", skill_id="x")
    assert isinstance(record, UsageRecord)
    assert record.tenant_id == "t1"
    assert record.skill_id == "x"
    # Free tier (1 of 5 used) → amount=0
    assert record.amount_usd == 0.0
    assert record.billed is False
    assert record.status == "pending"


def test_record_usage_charges_after_free_tier(matrix):
    """Después de free_tier_calls_per_month, cobra price_per_call."""
    matrix.set_pricing(skill_id="x", price_per_call_usd=0.10, free_tier_calls_per_month=2)
    # First 2 calls free
    r1 = matrix.record_usage(tenant_id="t1", skill_id="x")
    r2 = matrix.record_usage(tenant_id="t1", skill_id="x")
    assert r1.amount_usd == 0.0
    assert r2.amount_usd == 0.0
    # 3rd call → billed
    r3 = matrix.record_usage(tenant_id="t1", skill_id="x")
    assert r3.amount_usd == 0.10


def test_record_usage_no_pricing_is_free(matrix):
    """Skill sin pricing → uso gratis."""
    record = matrix.record_usage(tenant_id="t1", skill_id="nonexistent_skill")
    assert record.amount_usd == 0.0
    assert record.billed is False


def test_record_usage_inactive_pricing_is_free(matrix):
    matrix.set_pricing(skill_id="x", price_per_call_usd=1.0, active=False)
    record = matrix.record_usage(tenant_id="t1", skill_id="x")
    assert record.amount_usd == 0.0


def test_record_usage_separates_tenants(matrix):
    """Cada tenant tiene su propio free_tier."""
    matrix.set_pricing(skill_id="x", price_per_call_usd=0.10, free_tier_calls_per_month=1)
    r1 = matrix.record_usage(tenant_id="t1", skill_id="x")  # t1 free
    r2 = matrix.record_usage(tenant_id="t2", skill_id="x")  # t2 free
    r3 = matrix.record_usage(tenant_id="t1", skill_id="x")  # t1 billed
    assert r1.amount_usd == 0.0
    assert r2.amount_usd == 0.0
    assert r3.amount_usd == 0.10


# ===== List usage =====

def test_list_usage_filter_by_tenant(matrix):
    matrix.record_usage(tenant_id="t1", skill_id="x")
    matrix.record_usage(tenant_id="t2", skill_id="x")
    matrix.record_usage(tenant_id="t1", skill_id="x")
    t1 = matrix.list_usage(tenant_id="t1")
    t2 = matrix.list_usage(tenant_id="t2")
    assert len(t1) == 2
    assert len(t2) == 1


def test_list_usage_filter_by_skill(matrix):
    matrix.record_usage(tenant_id="t1", skill_id="x")
    matrix.record_usage(tenant_id="t1", skill_id="y")
    x_usage = matrix.list_usage(skill_id="x")
    y_usage = matrix.list_usage(skill_id="y")
    assert len(x_usage) == 1
    assert len(y_usage) == 1


def test_list_usage_filter_by_status(matrix):
    matrix.record_usage(tenant_id="t1", skill_id="x")
    # All pending initially
    pending = matrix.list_usage(status="pending")
    assert len(pending) == 1


# ===== Billing cycles =====

def test_get_or_create_billing_cycle_creates_new(matrix):
    cycle = matrix.get_or_create_billing_cycle(tenant_id="t1")
    assert isinstance(cycle, BillingCycle)
    assert cycle.tenant_id == "t1"
    assert cycle.status == "open"
    assert cycle.total_usd == 0.0


def test_get_or_create_billing_cycle_idempotent(matrix):
    c1 = matrix.get_or_create_billing_cycle(tenant_id="t1")
    c2 = matrix.get_or_create_billing_cycle(tenant_id="t1")
    assert c1.id == c2.id


def test_close_billing_cycle_sums_pending_usage(matrix):
    matrix.set_pricing(skill_id="x", price_per_call_usd=0.50, free_tier_calls_per_month=0)
    # 3 calls × 0.50 = 1.50
    matrix.record_usage(tenant_id="t1", skill_id="x")
    matrix.record_usage(tenant_id="t1", skill_id="x")
    matrix.record_usage(tenant_id="t1", skill_id="x")

    cycle = matrix.get_or_create_billing_cycle(tenant_id="t1")
    closed = matrix.close_billing_cycle(cycle.id)
    assert closed.total_usd == 1.50
    assert closed.status == "invoiced"

    # Verify usage records marked as billed
    billed = matrix.list_usage(status="billed")
    assert len(billed) == 3


def test_mark_paid_changes_status(matrix):
    matrix.set_pricing(skill_id="x", price_per_call_usd=1.0, free_tier_calls_per_month=0)
    matrix.record_usage(tenant_id="t1", skill_id="x")
    cycle = matrix.get_or_create_billing_cycle(tenant_id="t1")
    matrix.close_billing_cycle(cycle.id)
    paid = matrix.mark_paid(cycle.id, invoice_url="https://pay.example/invoice/123")
    assert paid.status == "paid"
    assert paid.invoice_url == "https://pay.example/invoice/123"

    paid_usage = matrix.list_usage(status="paid")
    assert len(paid_usage) == 1


def test_close_billing_cycle_nonexistent_raises(matrix):
    with pytest.raises(KeyError):
        matrix.close_billing_cycle("nonexistent")


# ===== Stats =====

def test_stats_returns_counts(matrix):
    matrix.set_pricing(skill_id="x")
    matrix.record_usage(tenant_id="t1", skill_id="x")
    matrix.get_or_create_billing_cycle(tenant_id="t1")
    stats = matrix.stats()
    assert stats["total_priced_skills"] == 1
    assert stats["total_usage_records"] == 1
    assert stats["total_billing_cycles"] == 1
    assert stats["total_revenue_paid_usd"] == 0.0  # nothing paid yet
    assert "total_pending_usd" in stats


def test_stats_revenue_calculates_paid_only(matrix):
    matrix.set_pricing(skill_id="x", price_per_call_usd=1.0, free_tier_calls_per_month=0)
    matrix.record_usage(tenant_id="t1", skill_id="x")
    cycle = matrix.get_or_create_billing_cycle(tenant_id="t1")
    matrix.close_billing_cycle(cycle.id)
    # Cycle is invoiced but not paid
    stats = matrix.stats()
    assert stats["total_revenue_paid_usd"] == 0.0  # not paid yet
    matrix.mark_paid(cycle.id)
    stats2 = matrix.stats()
    assert stats2["total_revenue_paid_usd"] == 1.0


# ===== Persistence =====

def test_persistence_across_connections(tmp_path):
    db = tmp_path / "paid.db"
    m1 = PaidAgentMatrix(str(db))
    m1.set_pricing(skill_id="x", price_per_call_usd=0.10)
    m1.record_usage(tenant_id="t1", skill_id="x")
    m1.close()
    m2 = PaidAgentMatrix(str(db))
    sm = m2.get_pricing("x")
    assert sm is not None
    assert sm.price_per_call_usd == 0.10
    usage = m2.list_usage(tenant_id="t1")
    assert len(usage) == 1
    m2.close()


# ===== as_dict =====

def test_service_matrix_as_dict(matrix):
    sm = matrix.set_pricing(
        skill_id="x", price_per_call_usd=0.10, price_per_month_usd=5.0,
        free_tier_calls_per_month=50, payment_address_usdc="0xabc123",
    )
    d = sm.as_dict()
    assert d["skill_id"] == "x"
    assert d["price_per_call_usd"] == 0.10
    assert d["price_per_month_usd"] == 5.0
    assert d["free_tier_calls_per_month"] == 50
    assert d["payment_address_usdc"] == "0xabc123"
    assert d["active"] is True


def test_usage_record_as_dict(matrix):
    record = matrix.record_usage(tenant_id="t1", skill_id="x")
    d = record.as_dict()
    assert d["tenant_id"] == "t1"
    assert d["skill_id"] == "x"
    assert "called_at" in d
    assert d["status"] == "pending"


def test_billing_cycle_as_dict(matrix):
    cycle = matrix.get_or_create_billing_cycle(tenant_id="t1")
    d = cycle.as_dict()
    assert d["tenant_id"] == "t1"
    assert d["status"] == "open"
    assert d["total_usd"] == 0.0
