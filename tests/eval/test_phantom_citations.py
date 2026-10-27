"""Tests del Legal Phantom Citation Test (V2.3-A)."""
from __future__ import annotations

import pytest

from albra.eval.phantom_citations import (
    PHANTOM_CITATIONS,
    REAL_CITATIONS,
    run_phantom_test,
    run_phantom_test_detailed,
)


@pytest.fixture
def strong_secrets(monkeypatch):
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-ephemeral-jwt-secret-32-chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-ephemeral-pass-1234")


# ===== Dataset shape =====

def test_real_citations_has_50_entries(strong_secrets):
    assert len(REAL_CITATIONS) == 50


def test_phantom_citations_has_50_entries(strong_secrets):
    assert len(PHANTOM_CITATIONS) == 50


def test_real_citations_all_non_empty_strings(strong_secrets):
    for c in REAL_CITATIONS:
        assert isinstance(c, str)
        assert len(c) >= 20


def test_phantom_citations_all_non_empty_strings(strong_secrets):
    for c in PHANTOM_CITATIONS:
        assert isinstance(c, str)
        assert len(c) >= 20


def test_real_and_phantom_no_overlap(strong_secrets):
    """Ningún REAL debe ser igual a un PHANTOM."""
    intersection = set(REAL_CITATIONS) & set(PHANTOM_CITATIONS)
    assert intersection == set()


# ===== Metrics =====

def test_run_phantom_test_returns_metrics_dict(strong_secrets):
    m = run_phantom_test()
    for key in (
        "real_total",
        "phantom_total",
        "true_positives",
        "true_negatives",
        "false_positives",
        "false_negatives",
        "true_positive_rate",
        "true_negative_rate",
        "false_positive_rate",
        "false_negative_rate",
        "total",
    ):
        assert key in m, f"missing key: {key}"
    assert m["total"] == 100
    assert m["real_total"] == 50
    assert m["phantom_total"] == 50


def test_real_citations_all_revealed(strong_secrets):
    """TRUE_POSITIVE_RATE debe ser 1.0 — todos los REAL deben revelarse."""
    m = run_phantom_test()
    assert m["true_positive_rate"] == 1.0
    assert m["false_negatives"] == 0


def test_phantom_citations_all_blocked(strong_secrets):
    """TRUE_NEGATIVE_RATE debe ser 1.0 — todos los PHANTOM deben bloquearse."""
    m = run_phantom_test()
    assert m["true_negative_rate"] == 1.0
    assert m["false_positives"] == 0


def test_no_false_positives(strong_secrets):
    """FALSE_POSITIVE_RATE debe ser 0.0 — ningún PHANTOM revelado."""
    m = run_phantom_test()
    assert m["false_positive_rate"] == 0.0
    assert m["false_positives"] == 0


def test_no_false_negatives(strong_secrets):
    """FALSE_NEGATIVE_RATE debe ser 0.0 — ningún REAL bloqueado."""
    m = run_phantom_test()
    assert m["false_negative_rate"] == 0.0
    assert m["false_negatives"] == 0


# ===== Detailed =====

def test_run_phantom_test_detailed_returns_per_citation(strong_secrets):
    rows = run_phantom_test_detailed()
    assert len(rows) == 100
    labels = {r["label"] for r in rows}
    assert labels == {"REAL", "PHANTOM"}
    real_rows = [r for r in rows if r["label"] == "REAL"]
    phantom_rows = [r for r in rows if r["label"] == "PHANTOM"]
    assert len(real_rows) == 50
    assert len(phantom_rows) == 50


def test_run_phantom_test_detailed_row_shape(strong_secrets):
    rows = run_phantom_test_detailed()
    r = rows[0]
    for key in (
        "label",
        "text",
        "revealed",
        "blocked",
        "verified_count",
        "unverified_count",
        "rejected_count",
        "reason",
    ):
        assert key in r, f"missing key: {key}"
    # Invariantes del dict
    assert r["blocked"] == (not r["revealed"])


def test_run_phantom_test_detailed_reals_all_revealed(strong_secrets):
    rows = run_phantom_test_detailed()
    real_rows = [r for r in rows if r["label"] == "REAL"]
    assert all(r["revealed"] for r in real_rows)


def test_run_phantom_test_detailed_phantoms_all_blocked(strong_secrets):
    rows = run_phantom_test_detailed()
    phantom_rows = [r for r in rows if r["label"] == "PHANTOM"]
    assert all(not r["revealed"] for r in phantom_rows)


def test_phantom_citations_cover_three_categories(strong_secrets):
    """Los PHANTOM deben cubrir al menos: Constitución wrong article, Ley wrong,
    Sentencia invented/rejected."""
    text_joined = " | ".join(PHANTOM_CITATIONS).lower()
    # Constitución con artículo inexistente
    has_const_wrong = "artículo 350" in text_joined or "artículo 400" in text_joined
    # Ley con número o año erróneo
    has_ley_wrong = "ley 9999" in text_joined or "ley 100 de 2099" in text_joined
    # Sentencia inventada o rechazada
    has_sentencia = "xyz-999" in text_joined or "c-251/2002" in text_joined
    assert has_const_wrong, "no Constitución wrong article in PHANTOM set"
    assert has_ley_wrong, "no Ley wrong in PHANTOM set"
    assert has_sentencia, "no invented/rejected Sentencia in PHANTOM set"
