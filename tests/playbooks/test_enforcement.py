"""Tests for PlaybookLoader enforcement (HARDENING-3 Block 7).

Covers:
- validate_enforcement() for stock playbooks (all pass)
- validate_enforcement() detects missing rbac_required
- validate_enforcement() detects missing audit_required
- validate_enforcement() detects missing approval_required when sensitive
- validate_all() returns dict keyed by practice_area
"""
from __future__ import annotations

import pytest

from albra.playbooks.loader import Playbook, PlaybookLoader


@pytest.fixture
def loader() -> PlaybookLoader:
    return PlaybookLoader()


# ===== validate_enforcement on stock playbooks =====


def test_validate_enforcement_all_playbooks_pass(loader: PlaybookLoader):
    """All 5 stock playbooks have rbac, audit, approval enforced."""
    playbooks = loader.load_all()
    assert len(playbooks) == 5
    for area, pb in playbooks.items():
        result = loader.validate_enforcement(pb)
        assert result["rbac_required"] is True, f"{area} missing rbac"
        assert result["audit_required"] is True, f"{area} missing audit"
        assert result["approval_required"] is True, f"{area} missing approval"
        assert result["citation_audit_required"] is True, f"{area} missing citation audit"
        assert result["all_enforced"] is True, f"{area} not all enforced"


def test_validate_enforcement_detects_missing_rbac(loader: PlaybookLoader):
    """Playbook with rbac_required=False → all_enforced=False."""
    pb = Playbook(
        practice_area="test_missing_rbac",
        typical_matter_types=["x"],
        workflow_states=["NUEVO", "EN-ESPERA-DE-APROBACIÓN"],
        required_documents=["doc.docx"],
        deadline_types=["prescripcion"],
        citation_corpus=["Constitución Política de 1991"],
        red_flags=["red flag"],
        rbac_required=False,
    )
    result = loader.validate_enforcement(pb)
    assert result["rbac_required"] is False
    assert result["all_enforced"] is False


def test_validate_enforcement_detects_missing_audit(loader: PlaybookLoader):
    """Playbook with audit_required=False → all_enforced=False."""
    pb = Playbook(
        practice_area="test_missing_audit",
        typical_matter_types=["x"],
        workflow_states=["NUEVO", "EN-ESPERA-DE-APROBACIÓN"],
        required_documents=["doc.docx"],
        deadline_types=["prescripcion"],
        citation_corpus=["Constitución Política de 1991"],
        red_flags=["red flag"],
        audit_required=False,
    )
    result = loader.validate_enforcement(pb)
    assert result["audit_required"] is False
    assert result["all_enforced"] is False


def test_validate_enforcement_detects_missing_approval_when_sensitive(
    loader: PlaybookLoader,
):
    """Playbook with approval_required=False AND sensitive actions →
    all_enforced=False (sensitive playbooks MUST require approval)."""
    pb = Playbook(
        practice_area="test_missing_approval_sensitive",
        typical_matter_types=["x"],
        workflow_states=["NUEVO", "EN-ESPERA-DE-APROBACIÓN"],
        required_documents=["doc.docx"],
        deadline_types=["prescripcion"],
        citation_corpus=["Constitución Política de 1991"],
        red_flags=["red flag"],
        approval_required=False,  # wrong: sensitive but approval off
    )
    result = loader.validate_enforcement(pb)
    assert result["approval_required"] is False
    assert result["all_enforced"] is False


def test_validate_enforcement_approval_not_required_for_non_sensitive(
    loader: PlaybookLoader,
):
    """Non-sensitive playbook with approval_required=False → still all_enforced=True."""
    pb = Playbook(
        practice_area="test_non_sensitive",
        typical_matter_types=["intake"],
        workflow_states=["NUEVO"],  # no approval state
        required_documents=[],       # no required docs
        deadline_types=[],
        citation_corpus=[],
        red_flags=[],                # no red flags → non-sensitive
        approval_required=False,
    )
    result = loader.validate_enforcement(pb)
    assert result["approval_required"] is False
    # Non-sensitive → approval not required, so still enforced.
    assert result["all_enforced"] is True


# ===== validate_all =====


def test_validate_all_returns_dict(loader: PlaybookLoader):
    """validate_all returns dict keyed by practice_area with enforcement info."""
    results = loader.validate_all()
    assert isinstance(results, dict)
    assert set(results.keys()) == {
        "laboral",
        "civil",
        "familia",
        "constitucional",
        "corporativo",
    }
    for area, result in results.items():
        assert "rbac_required" in result
        assert "citation_audit_required" in result
        assert "approval_required" in result
        assert "audit_required" in result
        assert "all_enforced" in result
        assert result["all_enforced"] is True, f"{area} should be enforced"
