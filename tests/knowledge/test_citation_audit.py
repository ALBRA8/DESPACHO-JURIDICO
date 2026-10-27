"""Tests del CitationAuditor — pipeline fail-closed anti-hallucination."""
from __future__ import annotations

import pytest

from albra.knowledge.citation_audit import (
    Citation,
    CitationAuditor,
    CitationAuditResult,
)


@pytest.fixture
def auditor():
    return CitationAuditor()


# ===== extract_citations =====

def test_extract_constitucion_articulo(auditor):
    text = "El artículo 13 de la Constitución Política de 1991 garantiza la igualdad."
    cits = auditor.extract_citations(text)
    assert len(cits) >= 1
    constitucionales = [c for c in cits if c.document_type == "constitucion"]
    assert len(constitucionales) >= 1
    c = constitucionales[0]
    assert c.document_name == "Constitución Política de 1991"
    assert c.article_number == "13"


def test_extract_ley_articulo(auditor):
    text = "Según la Ley 100 de 1993, artículo 3, el Estado garantiza seguridad social."
    cits = auditor.extract_citations(text)
    leyes = [c for c in cits if c.document_type == "legislacion"]
    assert len(leyes) >= 1
    c = leyes[0]
    assert c.document_name == "Ley 100 de 1993"
    assert c.article_number == "3"


def test_extract_sentencia(auditor):
    text = "La Sentencia C-251/2002 establece que..."
    cits = auditor.extract_citations(text)
    sentencias = [c for c in cits if c.document_type == "jurisprudencia"]
    assert len(sentencias) >= 1
    assert sentencias[0].document_name == "Sentencia C-251/2002"


def test_extract_multiple_citations(auditor):
    text = (
        "El artículo 13 de la Constitución Política de 1991 y la Ley 100 de 1993, "
        "artículo 3, garantizan derechos. La Sentencia T-760/2008 amplía."
    )
    cits = auditor.extract_citations(text)
    assert len(cits) >= 3
    types = {c.document_type for c in cits}
    assert "constitucion" in types
    assert "legislacion" in types
    assert "jurisprudencia" in types


def test_extract_no_citations_in_plain_text(auditor):
    text = "Esta es una frase sobre el derecho civil colombiano sin citas específicas."
    cits = auditor.extract_citations(text)
    assert len(cits) == 0


def test_extract_quote_associated_to_citation(auditor):
    text = (
        'El artículo 1 de la Constitución Política de 1991 establece '
        '"Colombia es un Estado social de derecho" como principio fundacional.'
    )
    cits = auditor.extract_citations(text)
    c = next(c for c in cits if c.document_type == "constitucion")
    assert c.article_number == "1"
    assert c.quote is not None
    assert "Estado social" in c.quote


# ===== validate_against_corpus =====

def test_validate_constitucion_in_corpus_passes(auditor):
    cits = [Citation(
        raw_text="artículo 1 de la Constitución",
        document_type="constitucion",
        document_name="Constitución Política de 1991",
        article_number="1",
    )]
    v, u, r = auditor.validate_against_corpus(cits)
    assert len(v) == 1
    assert len(u) == 0
    assert len(r) == 0


def test_validate_constitucion_wrong_article_unverified(auditor):
    """Artículo que no está en corpus V1.1 (solo 1,2,5,13,25,29 disponibles)."""
    cits = [Citation(
        raw_text="artículo 350 de la Constitución",
        document_type="constitucion",
        document_name="Constitución Política de 1991",
        article_number="350",
    )]
    v, u, r = auditor.validate_against_corpus(cits)
    assert len(v) == 0
    assert len(u) == 1
    assert len(r) == 0


def test_validate_rejected_document(auditor):
    """Sentencia C-251/2002 fue rechazada honestamente en V1.1."""
    cits = [Citation(
        raw_text="Sentencia C-251/2002",
        document_type="jurisprudencia",
        document_name="Sentencia C-251/2002",
    )]
    v, u, r = auditor.validate_against_corpus(cits)
    assert len(v) == 0
    assert len(u) == 0
    assert len(r) == 1
    assert r[0].document_name == "Sentencia C-251/2002"


def test_validate_unknown_ley_unverified(auditor):
    """Ley no en corpus V1.1 → unverified."""
    cits = [Citation(
        raw_text="Ley 9999 de 2099",
        document_type="legislacion",
        document_name="Ley 9999 de 2099",
    )]
    v, u, r = auditor.validate_against_corpus(cits)
    assert len(v) == 0
    assert len(u) == 1
    assert len(r) == 0


def test_validate_ley_80_in_corpus(auditor):
    cits = [Citation(
        raw_text="Ley 80 de 1993, artículo 24",
        document_type="legislacion",
        document_name="Ley 80 de 1993",
        article_number="24",
    )]
    v, u, r = auditor.validate_against_corpus(cits)
    assert len(v) == 1
    assert len(u) == 0
    assert len(r) == 0


# ===== retrace_quotes =====

def test_retrace_quote_exact_match_passes(auditor):
    cits = [Citation(
        raw_text="artículo 1",
        document_type="constitucion",
        document_name="Constitución Política de 1991",
        article_number="1",
        quote="Colombia es un Estado social de derecho",
    )]
    passed, failed = auditor.retrace_quotes(cits)
    assert len(passed) == 1
    assert len(failed) == 0


def test_retrace_quote_mismatch_fails(auditor):
    cits = [Citation(
        raw_text="artículo 1",
        document_type="constitucion",
        document_name="Constitución Política de 1991",
        article_number="1",
        quote="El presidente tiene potestad de disolver el congreso",
    )]
    passed, failed = auditor.retrace_quotes(cits)
    assert len(passed) == 0
    assert len(failed) == 1


def test_retrace_quote_partial_5_words_match_passes(auditor):
    cits = [Citation(
        raw_text="artículo 13",
        document_type="constitucion",
        document_name="Constitución Política de 1991",
        article_number="13",
        quote="todas las personas nacen libres e iguales ante la ley",
    )]
    passed, failed = auditor.retrace_quotes(cits)
    assert len(passed) == 1


def test_retrace_no_quote_passes(auditor):
    cits = [Citation(
        raw_text="artículo 1 de la Constitución",
        document_type="constitucion",
        document_name="Constitución Política de 1991",
        article_number="1",
        quote=None,
    )]
    passed, failed = auditor.retrace_quotes(cits)
    assert len(passed) == 1
    assert len(failed) == 0


# ===== audit_response (pipeline completo) =====

def test_audit_response_no_citations_revealed(auditor):
    text = "El derecho civil colombiano protege la autonomía de la voluntad."
    result = auditor.audit_response(text)
    assert result.revealed
    assert result.total_citations == 0
    assert "No citations" in result.reason


def test_audit_response_all_verified_revealed(auditor):
    text = (
        "El artículo 1 de la Constitución Política de 1991 establece que "
        '"Colombia es un Estado social de derecho". Adicionalmente, la Ley 100 '
        "de 1993, artículo 1, garantiza el derecho a la seguridad social."
    )
    result = auditor.audit_response(text)
    assert result.total_citations >= 2
    assert len(result.verified) >= 2
    assert result.revealed
    assert len(result.unverified) == 0


def test_audit_response_blocked_when_c251_cited(auditor):
    text = (
        "Según la Sentencia C-251/2002, el derecho a la salud está garantizado. "
        "También aplica el artículo 1 de la Constitución Política de 1991."
    )
    result = auditor.audit_response(text)
    assert not result.revealed
    assert len(result.rejected) >= 1
    assert "BLOCKED" in result.reason


def test_audit_response_blocked_when_invented_article(auditor):
    text = (
        "El artículo 350 de la Constitución Política de 1991 establece el derecho al olvido."
    )
    result = auditor.audit_response(text)
    assert not result.revealed
    assert len(result.unverified) >= 1


def test_audit_response_blocked_when_quote_invented(auditor):
    text = (
        'El artículo 1 de la Constitución Política de 1991 establece '
        '"El presidente puede disolver el congreso cuando lo considere necesario".'
    )
    result = auditor.audit_response(text)
    assert not result.revealed
    assert len(result.unverified) >= 1


def test_audit_response_mixed_verified_and_rejected_blocks(auditor):
    text = (
        "El artículo 1 de la Constitución Política de 1991 y la Sentencia C-251/2002 "
        "protegen el derecho a la salud."
    )
    result = auditor.audit_response(text)
    assert not result.revealed
    assert len(result.verified) >= 1
    assert len(result.rejected) >= 1


def test_audit_response_result_as_dict(auditor):
    text = "Sin citas."
    result = auditor.audit_response(text)
    d = result.as_dict()
    assert "revealed" in d
    assert "total_citations" in d
    assert "verified" in d
    assert "unverified" in d
    assert "rejected" in d
    assert "reason" in d


def test_audit_response_returns_citation_objects(auditor):
    text = "El artículo 13 de la Constitución Política de 1991 protege la igualdad."
    result = auditor.audit_response(text)
    for c in result.verified:
        assert isinstance(c, Citation)
        assert c.document_type
        assert c.document_name
        assert c.raw_text


# ===== Edge cases =====

def test_constitucion_1886_unverified(auditor):
    text = "La Constitución de 1886 establecía el suffrage universal."
    cits = auditor.extract_citations(text)
    constitucionales = [c for c in cits if c.document_type == "constitucion"]
    assert any("1886" in c.document_name for c in constitucionales)


def test_multiple_sentencias_rejected(auditor):
    text = "Las sentencias T-760/2008 y C-251/2002 establecen..."
    auditor.extract_citations(text)
    result = auditor.audit_response(text)
    assert len(result.rejected) >= 2
    assert not result.revealed
