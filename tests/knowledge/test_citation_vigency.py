"""Tests for CitationAuditor vigency (HARDENING-3 Block 6).

Covers:
- check_vigency() for Constitución 1991, Ley 100/1993, Ley 80/1993
- check_vigency() for unknown documents
- Citation.vigency_status field populated by audit_response()
- Vigency info surfaces in audit result dict (verified[0])
"""
from __future__ import annotations

import pytest

from albra.knowledge.citation_audit import Citation, CitationAuditor


@pytest.fixture
def auditor() -> CitationAuditor:
    return CitationAuditor()


# ===== check_vigency =====


def test_vigency_constitucion_vigente(auditor: CitationAuditor):
    """Constitución 1991 status='vigente' → VIGENTE, no derogation date."""
    v = auditor.check_vigency("Constitución Política de 1991")
    assert v["status"] == "VIGENTE"
    assert v["effective_date"]  # non-empty ISO date
    assert v["derogation_date"] is None


def test_vigency_ley_100_vigente(auditor: CitationAuditor):
    """Ley 100/1993 status='modificada' → still VIGENTE (in force)."""
    v = auditor.check_vigency("Ley 100 de 1993")
    assert v["status"] == "VIGENTE"
    assert v["effective_date"]  # non-empty
    assert v["derogation_date"] is None


def test_vigency_ley_80_vigente(auditor: CitationAuditor):
    """Ley 80/1993 status='modificada' → still VIGENTE."""
    v = auditor.check_vigency("Ley 80 de 1993")
    assert v["status"] == "VIGENTE"
    assert v["effective_date"]
    assert v["derogation_date"] is None


def test_vigency_unknown_document(auditor: CitationAuditor):
    """Document not in corpus → UNKNOWN."""
    v = auditor.check_vigency("Ley 9999 de 2099")
    assert v["status"] == "UNKNOWN"
    assert v["effective_date"] == ""
    assert v["derogation_date"] is None


def test_vigency_unknown_sentencia(auditor: CitationAuditor):
    """Sentencia C-251/2002 is REJECTED (not in corpus index) → UNKNOWN."""
    v = auditor.check_vigency("Sentencia C-251/2002")
    assert v["status"] == "UNKNOWN"


# ===== Citation.vigency_status field =====


def test_citation_includes_vigency_info():
    """Citation dataclass has a vigency_status field, default empty string."""
    c = Citation(
        raw_text="artículo 13 de la Constitución",
        document_type="constitucion",
        document_name="Constitución Política de 1991",
        article_number="13",
    )
    assert c.vigency_status == ""
    d = c.as_dict()
    assert "vigency_status" in d
    assert d["vigency_status"] == ""


# ===== Vigency surfaced by audit_response =====


def test_vigency_status_in_audit_result(auditor: CitationAuditor):
    """audit_response populates vigency_status on verified citations."""
    text = (
        "El artículo 1 de la Constitución Política de 1991 establece que "
        '"Colombia es un Estado social de derecho". Adicionalmente, la Ley 100 '
        "de 1993, artículo 1, garantiza el derecho a la seguridad social."
    )
    result = auditor.audit_response(text)
    assert result.revealed
    assert len(result.verified) >= 2
    for c in result.verified:
        assert c.vigency_status == "VIGENTE"
    # Also surfaces in as_dict() output.
    for c_dict in result.as_dict()["verified"]:
        assert c_dict["vigency_status"] == "VIGENTE"


def test_vigency_not_set_for_unverified(auditor: CitationAuditor):
    """audit_response leaves vigency_status='' for unverified citations
    (since they are by definition not in the corpus)."""
    text = "El artículo 350 de la Constitución Política de 1991 protege el olvido."
    result = auditor.audit_response(text)
    assert len(result.unverified) >= 1
    for c in result.unverified:
        assert c.vigency_status == ""


def test_vigency_check_returns_dict_shape(auditor: CitationAuditor):
    """check_vigency always returns dict with required keys."""
    for name in (
        "Constitución Política de 1991",
        "Ley 100 de 1993",
        "Ley 80 de 1993",
        "Ley 9999 de 2099",
        "",
    ):
        v = auditor.check_vigency(name)
        assert set(v.keys()) == {"status", "effective_date", "derogation_date"}
        assert v["status"] in ("VIGENTE", "DEROGADO", "UNKNOWN")
