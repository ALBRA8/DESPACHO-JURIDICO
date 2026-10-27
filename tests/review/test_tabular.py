"""Tests del TabularReview (comparación N-documentos × M-cláusulas)."""
from __future__ import annotations

import pytest

from albra.review.tabular import (
    CLAUSE_PATTERNS,
    ClauseComparison,
    TabularReview,
)


@pytest.fixture
def documents():
    """3 documentos de ejemplo con cláusulas variadas."""
    return [
        {
            "id": "doc-1",
            "name": "Contrato Cliente A",
            "clauses": [
                {"name": "jurisdiccion", "text": "Las partes se someten a la jurisdicción de Bogotá D.C."},
                {"name": "precio", "text": "El precio total del contrato es de USD 50,000."},
                {"name": "confidencialidad", "text": "Las partes acuerdan mantener confidencialidad de la información."},
            ],
        },
        {
            "id": "doc-2",
            "name": "Contrato Cliente B",
            "clauses": [
                {"name": "jurisdiccion", "text": "Las partes se someten a la jurisdicción de Medellín."},
                {"name": "precio", "text": "El precio total es de USD 75,000."},
                # No tiene confidencialidad
            ],
        },
        {
            "id": "doc-3",
            "name": "Contrato Cliente C",
            "clauses": [
                {"name": "jurisdiccion", "text": "Las partes se someten a la jurisdicción de Bogotá D.C."},
                {"name": "precio", "text": "El precio total del contrato es de USD 50,000."},
                {"name": "confidencialidad", "text": "Información confidencial será protegida."},
            ],
        },
    ]


@pytest.fixture
def review(documents):
    return TabularReview(documents=documents)


# ===== Init + add_document =====

def test_init_with_documents(documents):
    review = TabularReview(documents=documents)
    assert len(review.documents) == 3


def test_init_empty():
    review = TabularReview()
    assert review.documents == []


def test_add_document_appends():
    review = TabularReview()
    review.add_document({
        "id": "d1", "name": "Test",
        "clauses": [{"name": "precio", "text": "Precio: USD 100"}],
    })
    assert len(review.documents) == 1
    assert review.documents[0]["name"] == "Test"


def test_add_document_auto_generates_id():
    review = TabularReview()
    review.add_document({"name": "Test", "clauses": []})
    assert review.documents[0]["id"]


def test_add_document_with_full_text_extracts_clauses():
    """Si se pasa full_text, extrae cláusulas via regex."""
    full_text = """Cláusula de jurisdicción: Las partes se someten a la jurisdicción de Bogotá.

Cláusula de precio: El precio total es USD 100,000.

Esta es una cláusula sin patrón reconocido."""
    review = TabularReview()
    review.add_document({"name": "Test", "full_text": full_text})
    assert len(review.documents[0]["clauses"]) == 2  # jurisdiccion + precio
    clause_names = {c["name"] for c in review.documents[0]["clauses"]}
    assert "jurisdiccion" in clause_names
    assert "precio" in clause_names


# ===== Extract clause =====

def test_extract_clause_returns_text(documents):
    review = TabularReview(documents=documents)
    text = review.extract_clause(review.documents[0], "jurisdiccion")
    assert text is not None
    assert "Bogotá" in text


def test_extract_clause_returns_none_if_absent(documents):
    review = TabularReview(documents=documents)
    # doc-2 no tiene confidencialidad
    text = review.extract_clause(review.documents[1], "confidencialidad")
    assert text is None


def test_extract_clause_unknown_clause_raises(review):
    with pytest.raises(ValueError):
        review.extract_clause(review.documents[0], "nonexistent_clause")


# ===== Compare clauses =====

def test_compare_clauses_returns_rows(review):
    comp = review.compare_clauses("jurisdiccion")
    assert isinstance(comp, ClauseComparison)
    assert comp.clause_name == "jurisdiccion"
    assert len(comp.rows) == 3


def test_compare_present_count(review):
    comp = review.compare_clauses("confidencialidad")
    # doc-1: present, doc-2: absent, doc-3: present
    assert comp.present_count == 2
    assert comp.absent_count == 1


def test_compare_divergence_score_zero_when_all_identical():
    docs = [
        {"id": "d1", "name": "A", "clauses": [{"name": "x", "text": "Mismo texto"}]},
        {"id": "d2", "name": "B", "clauses": [{"name": "x", "text": "Mismo texto"}]},
        {"id": "d3", "name": "C", "clauses": [{"name": "x", "text": "Mismo texto"}]},
    ]
    # Override pattern to match any "Mismo texto"
    comp = ClauseComparison(clause_name="x", rows=[
        {"doc_id": d["id"], "doc_name": d["name"],
         "clause_text": d["clauses"][0]["text"], "present": True}
        for d in docs
    ])
    assert comp.divergence_score == 0.0


def test_compare_divergence_score_high_when_all_different():
    docs = [
        {"id": "d1", "name": "A", "clauses": [{"name": "x", "text": "Texto 1"}]},
        {"id": "d2", "name": "B", "clauses": [{"name": "x", "text": "Texto 2"}]},
        {"id": "d3", "name": "C", "clauses": [{"name": "x", "text": "Texto 3"}]},
    ]
    comp = ClauseComparison(clause_name="x", rows=[
        {"doc_id": d["id"], "doc_name": d["name"],
         "clause_text": d["clauses"][0]["text"], "present": True}
        for d in docs
    ])
    assert comp.divergence_score == 1.0


def test_compare_divergence_score_partial():
    """3 docs: 2 con mismo texto, 1 con texto diferente → 0.5"""
    docs = [
        {"id": "d1", "name": "A", "clauses": [{"name": "x", "text": "Texto X"}]},
        {"id": "d2", "name": "B", "clauses": [{"name": "x", "text": "Texto X"}]},
        {"id": "d3", "name": "C", "clauses": [{"name": "x", "text": "Texto Y"}]},
    ]
    comp = ClauseComparison(clause_name="x", rows=[
        {"doc_id": d["id"], "doc_name": d["name"],
         "clause_text": d["clauses"][0]["text"], "present": True}
        for d in docs
    ])
    assert 0 < comp.divergence_score < 1
    assert comp.divergence_score == 0.5  # (2 unique - 1) / (3 - 1) = 0.5


def test_compare_divergence_score_one_when_all_absent():
    """Si todos absent → divergence_score = 1.0 (max)."""
    docs = [
        {"id": "d1", "name": "A", "clauses": []},
        {"id": "d2", "name": "B", "clauses": []},
    ]
    review = TabularReview(documents=docs)
    comp = review.compare_clauses("jurisdiccion")
    assert comp.present_count == 0
    assert comp.divergence_score == 1.0


# ===== Export =====

def test_export_markdown_table(review):
    md = review.export_markdown_table("jurisdiccion")
    assert "Tabular Review: jurisdiccion" in md
    assert "| Documento |" in md
    assert "Contrato Cliente A" in md
    assert "Presentes:" in md
    assert "Divergencia:" in md


def test_export_csv(review):
    csv_output = review.export_csv("jurisdiccion")
    assert "doc_id" in csv_output
    assert "doc_name" in csv_output
    assert "present" in csv_output
    assert "clause_text" in csv_output
    assert "Contrato Cliente A" in csv_output


# ===== Divergence report =====

def test_divergence_report_with_all_clauses(review):
    report = review.divergence_report()
    assert "clauses" in report
    assert report["total_documents"] == 3
    assert len(report["clauses"]) == len(CLAUSE_PATTERNS)
    # Each clause has expected fields
    for c in report["clauses"]:
        assert "clause_name" in c
        assert "present_count" in c
        assert "absent_count" in c
        assert "divergence_score" in c


def test_divergence_report_with_specific_clauses(review):
    report = review.divergence_report(clause_names=["jurisdiccion", "precio"])
    assert len(report["clauses"]) == 2


def test_divergence_report_high_divergence_clauses(review):
    report = review.divergence_report()
    # jurisdiccion: 3 presentes, 2 textos diferentes → score = 0.5
    # Debe estar en high_divergence_clauses
    assert "jurisdiccion" in report["high_divergence_clauses"]


def test_divergence_report_uniform_clauses(review):
    """precio: doc-1 y doc-3 tienen mismo texto; doc-2 diferente. No es uniform."""
    # Para uniform: present_count > 0 AND divergence_score == 0
    # precio en nuestros docs: doc-1 "USD 50,000", doc-2 "USD 75,000", doc-3 "USD 50,000"
    # → 2 unique texts → score = (2-1)/(3-1) = 0.5, NOT uniform
    report = review.divergence_report()
    assert "precio" not in report["uniform_clauses"]


def test_divergence_report_absent_clauses():
    """Si ningún doc tiene una cláusula, aparece en absent_clauses."""
    docs = [{"id": "d1", "name": "A", "clauses": []}]
    review = TabularReview(documents=docs)
    report = review.divergence_report()
    # Todas las cláusulas están absent
    assert len(report["absent_clauses"]) == len(CLAUSE_PATTERNS)


# ===== Stats + list =====

def test_stats(review):
    stats = review.stats()
    assert stats["total_documents"] == 3
    assert stats["supported_clauses_count"] == len(CLAUSE_PATTERNS)


def test_list_supported_clause_names(review):
    names = review.list_supported_clause_names()
    assert "jurisdiccion" in names
    assert "precio" in names
    assert "confidencialidad" in names
    assert names == sorted(names)


# ===== ClauseComparison as_dict =====

def test_clause_comparison_as_dict():
    comp = ClauseComparison(
        clause_name="test",
        rows=[{"doc_id": "d1", "doc_name": "A", "clause_text": "T", "present": True}],
    )
    d = comp.as_dict()
    assert d["clause_name"] == "test"
    assert d["present_count"] == 1
    assert d["absent_count"] == 0
    assert d["rows"] == comp.rows


# ===== Clause patterns sanity =====

def test_clause_patterns_support_9_clauses():
    """V2.4-D soporta 9 tipos de cláusula."""
    assert len(CLAUSE_PATTERNS) == 9


def test_clause_patterns_match_with_accents():
    """Los patterns deben matchear con tildes (jurisdicción con ó)."""
    pattern = CLAUSE_PATTERNS["jurisdiccion"]
    assert pattern.search("Cláusula de jurisdicción: Bogotá")
    assert pattern.search("JURISDICCION: Medellín")
