"""Tests for albra.knowledge.ingestion_pipeline (HARDENING-2 Block 3).

Covers:
- All 11 stages called in canonical order (with mock fetcher)
- Idempotency: same URL + same content -> skipped, no re-index
- Fail-closed on fetch error (non-2xx, exception)
- Fail-closed on invalid content (validator rejects)
- Provenance generation (all required fields populated)
- Changed-source detection (same URL, different bytes -> detected_change=True)
"""
from __future__ import annotations

from typing import Any

import pytest

from albra.knowledge.ingestion_pipeline import (
    IngestionPipeline,
    IngestionResult,
    PipelineLogEntry,
)

# ---------------------------------------------------------------------------
# Mock fetcher
# ---------------------------------------------------------------------------


class MockFetcher:
    """Mock fetcher: returns canned (status, bytes) per URL."""

    def __init__(self, responses: dict[str, tuple[int, bytes]] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[str] = []

    def __call__(self, url: str) -> tuple[int, bytes]:
        self.calls.append(url)
        return self.responses.get(url, (404, b""))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fetcher() -> MockFetcher:
    return MockFetcher({
        "https://example.gov.co/ley-100.html": (
            200,
            b"<html><body>ARTICULO 1. Colombia es un Estado social de derecho.</body></html>",
        ),
    })


@pytest.fixture
def pipeline(fetcher: MockFetcher) -> IngestionPipeline:
    return IngestionPipeline(fetcher=fetcher)


# ---------------------------------------------------------------------------
# Stage ordering
# ---------------------------------------------------------------------------


def test_pipeline_stages_called_in_order(pipeline: IngestionPipeline):
    """All 11 stages must execute in canonical order on a successful run."""
    result = pipeline.run("https://example.gov.co/ley-100.html")
    assert isinstance(result, IngestionResult)
    assert result.ok is True, f"expected ok, got error: {result.error}"
    names = result.stage_names_in_order()
    # The pipeline may append a 12th entry ("verify" idempotency skip path),
    # but on a fresh ingest the canonical 11 stages should all be present in order.
    expected = list(IngestionPipeline.STAGES)
    assert names == expected, (
        f"stages not in canonical order.\nexpected: {expected}\ngot: {names}"
    )
    # Every entry must be ok=True on a successful run.
    for entry in result.pipeline_log:
        assert isinstance(entry, PipelineLogEntry)
        assert entry.ok is True, f"stage {entry.stage} was not ok: {entry.detail}"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_pipeline_idempotent_same_url(pipeline: IngestionPipeline, fetcher: MockFetcher):
    """Same URL + same content -> second run skipped, no re-index.

    Note: the pipeline MUST fetch on every run because content equality is
    judged by content hash, not URL alone (a URL's bytes can change at any
    time). The idempotency contract is therefore:
      * `skipped=True`
      * `document_id` matches the first run
      * no `index` stage executed (no re-index)
      * `detected_change=False`
    """
    url = "https://example.gov.co/ley-100.html"
    r1 = pipeline.run(url)
    assert r1.ok is True
    assert r1.skipped is False
    first_doc_id = r1.document_id
    assert first_doc_id, "first run must produce a document_id"

    # Reset fetcher call list so we can verify idempotency path on second run.
    fetcher.calls.clear()
    r2 = pipeline.run(url)
    assert r2.ok is True
    assert r2.skipped is True, "second run with identical content must be skipped"
    assert r2.detected_change is False
    assert r2.document_id == first_doc_id, (
        "idempotent run must return the same document_id as the first run"
    )
    # Same content hash.
    assert r1.content_hash == r2.content_hash
    assert r1.content_hash != ""
    # Idempotent path must NOT execute the `index` stage (no re-index).
    stage_names_r2 = r2.stage_names_in_order()
    assert "index" not in stage_names_r2, (
        f"idempotent run must not reach index stage, got: {stage_names_r2}"
    )
    # And the last stage must be `verify` (the idempotency short-circuit logs
    # a single `verify` entry on skip).
    assert stage_names_r2 == ["source", "fetch", "verify"], (
        f"idempotent run should execute source+fetch+verify only, got: {stage_names_r2}"
    )


# ---------------------------------------------------------------------------
# Fail-closed: fetch
# ---------------------------------------------------------------------------


def test_pipeline_fail_closed_on_fetch_error():
    """Non-2xx HTTP status -> fail-closed at fetch stage."""
    fetcher = MockFetcher({
        "https://example.gov.co/missing.html": (503, b""),
    })
    p = IngestionPipeline(fetcher=fetcher)
    r = p.run("https://example.gov.co/missing.html")
    assert r.ok is False
    assert r.error != ""
    assert "503" in r.error or "non-2xx" in r.error
    # Stages that ran: source + fetch only.
    names = r.stage_names_in_order()
    assert names == ["source", "fetch"]
    assert names[-1] == "fetch"
    assert r.pipeline_log[-1].ok is False


def test_pipeline_fail_closed_on_fetch_exception():
    """Fetcher raising -> fail-closed at fetch stage."""
    class ExplodingFetcher:
        def __call__(self, url: str) -> tuple[int, bytes]:
            raise ConnectionError("boom")

    p = IngestionPipeline(fetcher=ExplodingFetcher())
    r = p.run("https://example.gov.co/explode.html")
    assert r.ok is False
    assert "boom" in r.error or "fetch failed" in r.error
    names = r.stage_names_in_order()
    assert names == ["source", "fetch"]


# ---------------------------------------------------------------------------
# Fail-closed: validation
# ---------------------------------------------------------------------------


def test_pipeline_fail_closed_on_invalid_content():
    """Validator returning False -> fail-closed at validate stage."""
    fetcher = MockFetcher({
        "https://example.gov.co/empty.html": (200, b""),
    })
    p = IngestionPipeline(fetcher=fetcher)
    r = p.run("https://example.gov.co/empty.html")
    assert r.ok is False
    assert r.error != ""
    names = r.stage_names_in_order()
    assert names == ["source", "fetch", "validate"]
    assert names[-1] == "validate"
    assert r.pipeline_log[-1].ok is False


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_pipeline_generates_provenance(pipeline: IngestionPipeline):
    """Provenance dict must contain all required fields."""
    r = pipeline.run("https://example.gov.co/ley-100.html")
    assert r.ok is True
    prov = r.provenance
    assert isinstance(prov, dict)
    required = {
        "source_url",
        "source_url_format_valid",
        "source_url_accessible",
        "source_tier",
        "authority",
        "retrieval_timestamp",
        "content_hash",
        "transformation_chain",
    }
    assert required.issubset(prov.keys()), (
        f"missing provenance fields: {required - set(prov.keys())}"
    )
    assert prov["source_url"] == "https://example.gov.co/ley-100.html"
    assert prov["source_url_format_valid"] is True
    assert prov["source_url_accessible"] is True
    assert prov["source_tier"] == "S1_OFFICIAL"
    assert prov["content_hash"] == r.content_hash
    assert prov["transformation_chain"] == ["raw", "normalized", "extracted", "indexed"]


# ---------------------------------------------------------------------------
# Changed source detection
# ---------------------------------------------------------------------------


def test_pipeline_detects_changed_source():
    """Same URL with different bytes -> detected_change=True, re-indexed."""
    url = "https://example.gov.co/mutable.html"
    responses_v1: dict[str, tuple[int, bytes]] = {url: (200, b"<html>v1</html>")}
    responses_v2: dict[str, tuple[int, bytes]] = {
        url: (200, "<html>v2 amended</html>".encode("utf-8")),
    }

    # First fetcher returns v1.
    f1 = MockFetcher(responses_v1)
    p1 = IngestionPipeline(fetcher=f1)
    r1 = p1.run(url)
    assert r1.ok is True
    assert r1.detected_change is False
    hash_v1 = r1.content_hash
    doc_v1 = r1.document_id
    assert hash_v1 != ""

    # Second pipeline shares the SAME registry as p1 (via explicit injection)
    # so the idempotency check sees the prior entry. Switching the fetcher to v2
    # content should trigger the "changed source" branch.
    shared_registry = p1.registry
    f2 = MockFetcher(responses_v2)
    p2 = IngestionPipeline(fetcher=f2, registry=shared_registry)
    r2 = p2.run(url)
    assert r2.ok is True
    assert r2.skipped is False, "changed content must NOT be skipped"
    assert r2.detected_change is True, "changed content must set detected_change=True"
    assert r2.content_hash != hash_v1, "re-ingest must compute a NEW hash"
    assert r2.document_id != doc_v1, (
        "re-ingest of changed content must produce a NEW document_id"
    )


# ---------------------------------------------------------------------------
# Bonus: empty / invalid source_url fail-closed
# ---------------------------------------------------------------------------


def test_pipeline_fail_closed_on_empty_source_url(pipeline: IngestionPipeline):
    """Empty source_url -> fail-closed at source stage."""
    r = pipeline.run("")
    assert r.ok is False
    assert "source_url" in r.error or "empty" in r.error
    names = r.stage_names_in_order()
    assert names == ["source"]


def test_pipeline_fail_closed_on_bad_scheme(pipeline: IngestionPipeline):
    """Non-http(s) source_url -> fail-closed at source stage."""
    r = pipeline.run("ftp://example.gov.co/whatever")
    assert r.ok is False
    assert "scheme" in r.error or "http" in r.error
    names = r.stage_names_in_order()
    assert names == ["source"]


# ---------------------------------------------------------------------------
# Bonus: pipeline_log is fully populated + auditable
# ---------------------------------------------------------------------------


def test_pipeline_log_entries_have_timestamps_and_durations(pipeline: IngestionPipeline):
    """Every pipeline_log entry must have ts and duration_ms set."""
    r = pipeline.run("https://example.gov.co/ley-100.html")
    assert r.ok is True
    assert len(r.pipeline_log) == len(IngestionPipeline.STAGES)
    for entry in r.pipeline_log:
        assert entry.ts > 0
        assert entry.duration_ms >= 0.0
        assert entry.stage in IngestionPipeline.STAGES
