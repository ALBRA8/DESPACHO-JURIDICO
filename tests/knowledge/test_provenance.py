"""Tests del modelo de Provenance V1.3 — albra.knowledge.provenance.

Cubre:
- SourceCapture / NormalizedContent / DocumentProvenance dataclasses
- verify_integrity() detects tampering at every layer
- compute_provenance_status() PARTIAL / VERIFIED / NOT_VERIFIED transitions
- V1.3 corpus (real_corpus_v13) exposes provenance + provenance_status fields
- CitationAuditor blocks NOT_VERIFIED citations when require_provenance=True
- Core distinction: reconstructed_text_hash != raw_bytes_hash
- Field rename: V1.3 documents have NO `raw_content` key (renamed to
  `reconstructed_text` + `provenance` + `provenance_status`)
"""
from __future__ import annotations

import hashlib

import pytest

from albra.knowledge.citation_audit import CitationAuditor
from albra.knowledge.colombia.corpus_pilot.real_corpus_v13 import (
    ALL_DOCUMENTS_V13,
    CONSTITUCION_1991_V13,
    LEY_80_1993_V13,
    LEY_100_1993_V13,
    V13_PROVENANCE_NOTE,
    V13_STATS,
)
from albra.knowledge.provenance import (
    NOT_VERIFIED,
    PROV_NOT_VERIFIED,
    PROV_PARTIAL,
    PROV_VERIFIED,
    DocumentProvenance,
    NormalizedContent,
    SourceCapture,
    compute_provenance_status,
)

# ===== helpers =====


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_verified_provenance() -> DocumentProvenance:
    """Build a VERIFIED DocumentProvenance with HTML raw_bytes, normalized text,
    and reconstructed text — all hashes match their content.
    """
    raw_html = (
        b"<html><body><p>ARTICULO 1. Colombia es un Estado social de derecho.</p>"
        b"<p>ARTICULO 2. Son fines esenciales del Estado.</p></body></html>"
    )
    normalized = (
        "ARTICULO 1. Colombia es un Estado social de derecho.\n\n"
        "ARTICULO 2. Son fines esenciales del Estado."
    )
    reconstructed = (
        "ARTICULO 1. Colombia es un Estado social de derecho.\n\n"
        "ARTICULO 2. Son fines esenciales del Estado."
    )
    capture = SourceCapture(
        source_url="http://example.gov.co/constitucion.htm",
        source_domain="example.gov.co",
        retrieval_timestamp="2024-10-22T00:00:00Z",
        http_status=200,
        content_type="text/html",
        raw_bytes=raw_html,
        raw_bytes_hash=_sha(raw_html),
        retrieval_method="playwright",
        retrieval_version="V2.3-E",
    )
    norm = NormalizedContent(
        text=normalized,
        text_hash=_sha_text(normalized),
        transformation="HTML→text (regex strip_tags + whitespace normalize)",
    )
    return DocumentProvenance(
        source_capture=capture,
        normalized_content=norm,
        reconstructed_text=reconstructed,
        reconstructed_text_hash=_sha_text(reconstructed),
        transformation_metadata={"parser_version": "V2.3-E"},
        ingestion_timestamp="2024-10-22T00:00:00Z",
        ingestion_version="V1.3",
        corpus_version="V1.3",
    )


# ===== SourceCapture =====


def test_source_capture_init():
    """SourceCapture stores all fields verbatim."""
    cap = SourceCapture(
        source_url="http://example.gov.co/doc.htm",
        source_domain="example.gov.co",
        retrieval_timestamp="2024-10-22T00:00:00Z",
        http_status=200,
        content_type="text/html",
        raw_bytes=b"<html></html>",
        raw_bytes_hash=_sha(b"<html></html>"),
        retrieval_method="playwright",
        retrieval_version="V2.3-E",
    )
    assert cap.source_url == "http://example.gov.co/doc.htm"
    assert cap.source_domain == "example.gov.co"
    assert cap.http_status == 200
    assert cap.content_type == "text/html"
    assert cap.raw_bytes == b"<html></html>"
    assert cap.retrieval_method == "playwright"
    assert cap.retrieval_version == "V2.3-E"


def test_source_capture_hash_matches():
    """raw_bytes_hash matches SHA-256 of raw_bytes."""
    raw = b"<html><body>real content</body></html>"
    cap = SourceCapture(
        source_url="http://example.gov.co/",
        source_domain="example.gov.co",
        retrieval_timestamp="2024-10-22T00:00:00Z",
        http_status=200,
        content_type="text/html",
        raw_bytes=raw,
        raw_bytes_hash=_sha(raw),
        retrieval_method="playwright",
        retrieval_version="V2.3-E",
    )
    assert cap.raw_bytes_hash == hashlib.sha256(raw).hexdigest()


# ===== NormalizedContent =====


def test_normalized_content_hash():
    """text_hash matches SHA-256 of normalized text."""
    text = "ARTICULO 1. Colombia es un Estado social de derecho."
    norm = NormalizedContent(
        text=text,
        text_hash=_sha_text(text),
        transformation="HTML→text (regex strip_tags)",
    )
    assert norm.text_hash == hashlib.sha256(text.encode("utf-8")).hexdigest()


# ===== DocumentProvenance.verify_integrity =====


def test_document_provenance_verify_integrity_all_ok():
    """When all hashes match, verify_integrity returns True everywhere."""
    prov = _build_verified_provenance()
    checks = prov.verify_integrity()
    assert checks["raw_bytes_hash_ok"] is True
    assert checks["normalized_hash_ok"] is True
    assert checks["reconstructed_hash_ok"] is True
    assert prov.all_hashes_ok is True


def test_document_provenance_detects_raw_bytes_tampering():
    """Tampering raw_bytes flips raw_bytes_hash_ok to False."""
    prov = _build_verified_provenance()
    # Tamper: append bytes after construction.
    prov.source_capture.raw_bytes += b"<tampered/>"
    checks = prov.verify_integrity()
    assert checks["raw_bytes_hash_ok"] is False
    # Other layers unaffected.
    assert checks["normalized_hash_ok"] is True
    assert checks["reconstructed_hash_ok"] is True


def test_document_provenance_detects_normalized_tampering():
    """Tampering normalized_content.text flips normalized_hash_ok to False."""
    prov = _build_verified_provenance()
    prov.normalized_content.text += " TAMPERED"
    checks = prov.verify_integrity()
    assert checks["normalized_hash_ok"] is False
    assert checks["raw_bytes_hash_ok"] is True
    assert checks["reconstructed_hash_ok"] is True


def test_document_provenance_detects_reconstructed_tampering():
    """Tampering reconstructed_text flips reconstructed_hash_ok to False."""
    prov = _build_verified_provenance()
    prov.reconstructed_text += " TAMPERED"
    checks = prov.verify_integrity()
    assert checks["reconstructed_hash_ok"] is False
    assert checks["raw_bytes_hash_ok"] is True
    assert checks["normalized_hash_ok"] is True


# ===== compute_provenance_status =====


def test_provenance_status_partial_when_raw_bytes_missing():
    """When raw_bytes is unavailable (NOT_VERIFIED) but normalized +
    reconstructed hashes match, status is PARTIAL.
    """
    prov = _build_verified_provenance()
    # Simulate V1.2 retroactive: raw_bytes discarded.
    prov.source_capture.raw_bytes = b""
    prov.source_capture.raw_bytes_hash = NOT_VERIFIED
    integrity = prov.verify_integrity()
    status = compute_provenance_status(
        raw_bytes_available=False,
        raw_bytes_hash_ok=integrity["raw_bytes_hash_ok"],
        normalized_hash_ok=integrity["normalized_hash_ok"],
        reconstructed_hash_ok=integrity["reconstructed_hash_ok"],
    )
    assert status == PROV_PARTIAL


def test_provenance_status_verified_when_all_present():
    """When raw_bytes is present and all hashes match, status is VERIFIED."""
    prov = _build_verified_provenance()
    integrity = prov.verify_integrity()
    status = compute_provenance_status(
        raw_bytes_available=True,
        raw_bytes_hash_ok=integrity["raw_bytes_hash_ok"],
        normalized_hash_ok=integrity["normalized_hash_ok"],
        reconstructed_hash_ok=integrity["reconstructed_hash_ok"],
    )
    assert status == PROV_VERIFIED


# ===== CitationAuditor provenance enforcement =====


@pytest.fixture
def auditor_v11() -> CitationAuditor:
    """A v11 auditor (smaller corpus) we can mutate for provenance tests."""
    return CitationAuditor(corpus_version="v11")


def _inject_not_verified_doc(auditor: CitationAuditor, name: str = "Ley 9999 de 2099") -> None:
    """Inject a NOT_VERIFIED document into the auditor's index."""
    auditor._index[name] = {
        "document_type": "legislacion",
        "articles": {"1": "Foo bar baz."},
        "raw_text": "ARTICULO 1. Foo bar baz.",
        "source_url": "http://example.gov.co/ley_9999_2099.html",
        "provenance_status": PROV_NOT_VERIFIED,
        "provenance": None,
    }


def test_citation_auditor_blocks_unprovenanced_when_required(auditor_v11):
    """When require_provenance=True, citations from NOT_VERIFIED docs are BLOCKED."""
    _inject_not_verified_doc(auditor_v11)
    text = "La Ley 9999 de 2099, artículo 1, establece que foo es bar."
    result = auditor_v11.audit_response(text, require_provenance=True)
    assert not result.revealed
    assert "BLOCKED" in result.reason
    assert any(c.document_name == "Ley 9999 de 2099" for c in result.unverified)


def test_citation_auditor_allows_unprovenanced_when_not_required(auditor_v11):
    """When require_provenance=False (default), NOT_VERIFIED docs are allowed."""
    _inject_not_verified_doc(auditor_v11)
    text = "La Ley 9999 de 2099, artículo 1, establece que foo es bar."
    result = auditor_v11.audit_response(text)  # default: require_provenance=False
    assert result.revealed
    assert len(result.verified) >= 1


# ===== V1.3 corpus =====


def test_v13_corpus_has_provenance_status_partial():
    """Every V1.3 document has provenance_status='PARTIAL' (raw_bytes missing)."""
    assert len(ALL_DOCUMENTS_V13) == 3
    for _kind, doc in ALL_DOCUMENTS_V13:
        assert doc["provenance_status"] == PROV_PARTIAL, (
            f"document {doc['number']} should be PARTIAL, "
            f"got {doc['provenance_status']}"
        )
        assert doc["provenance"] is not None
        # Integrity check: raw_bytes NOT_VERIFIED, normalized + reconstructed OK.
        checks = doc["provenance"].verify_integrity()
        assert checks["raw_bytes_hash_ok"] is False  # NOT_VERIFIED → False
        assert checks["normalized_hash_ok"] is True
        assert checks["reconstructed_hash_ok"] is True


def test_v13_corpus_articles_match_v12_count():
    """V1.3 corpus preserves the V1.2 article count: 125 total
    (Constitución 32 + Ley 100 45 + Ley 80 48).
    """
    total = sum(len(doc["articles"]) for _, doc in ALL_DOCUMENTS_V13)
    assert total == 125
    assert V13_STATS["v13_total_articles"] == 125
    assert V13_STATS["v12_total_articles"] == 125
    # Per-document counts.
    assert len(CONSTITUCION_1991_V13["articles"]) == 32
    assert len(LEY_100_1993_V13["articles"]) == 45
    assert len(LEY_80_1993_V13["articles"]) == 48


def test_reconstructed_text_hash_differs_from_raw_bytes_hash():
    """The CORE distinction: SHA-256 of reconstructed text is NOT the same as
    SHA-256 of raw source bytes. V1.2 conflated these (raw_content_hash ==
    reconstructed text hash). V1.3 must distinguish them.
    """
    prov = _build_verified_provenance()
    raw_hash = prov.source_capture.raw_bytes_hash
    reconstructed_hash = prov.reconstructed_text_hash
    assert raw_hash != reconstructed_hash, (
        "raw_bytes_hash and reconstructed_text_hash must differ — this is the "
        "core provenance distinction V1.2 was missing."
    )
    # Also confirm both are real SHA-256 hex digests (64 hex chars).
    assert len(raw_hash) == 64
    assert len(reconstructed_hash) == 64
    # And verify_integrity confirms both match their content.
    checks = prov.verify_integrity()
    assert checks["raw_bytes_hash_ok"] is True
    assert checks["reconstructed_hash_ok"] is True


def test_raw_content_not_named_raw_content():
    """Verify the V1.2 field name `raw_content` was removed in V1.3 documents.
    V1.3 documents expose `provenance` (DocumentProvenance) and
    `provenance_status` instead.
    """
    for _kind, doc in ALL_DOCUMENTS_V13:
        assert "raw_content" not in doc, (
            f"V1.3 document {doc['number']} must NOT have `raw_content` field "
            "(that was the V1.2 misnomer — V1.3 uses provenance.reconstructed_text)"
        )
        assert "content_hash" not in doc, (
            f"V1.3 document {doc['number']} must NOT have `content_hash` field "
            "(that was the V1.2 misnomer)"
        )
        assert "provenance" in doc
        assert "provenance_status" in doc
        assert isinstance(doc["provenance"], DocumentProvenance)


# ===== V13_PROVENANCE_NOTE sanity =====


def test_v13_provenance_note_documents_limitation():
    """The V13_PROVENANCE_NOTE string explicitly documents the V1.2 limitation."""
    assert "NOT VERIFIED" in V13_PROVENANCE_NOTE
    assert "raw_bytes" in V13_PROVENANCE_NOTE
    assert "PARTIAL" in V13_PROVENANCE_NOTE
    assert "V1.4+" in V13_PROVENANCE_NOTE
