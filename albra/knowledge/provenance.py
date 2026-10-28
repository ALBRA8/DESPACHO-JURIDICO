"""
DOCUMENT PROVENANCE MODEL — V1.3 (real provenance).

Corpus V1.2 (commit 81a9c83) had a provenance gap: `raw_content` was actually
*reconstructed* article text (not HTML source bytes), and `content_hash` was
the SHA-256 of that reconstructed text — NOT of the source HTML. The user
flagged this as "NOT VERIFIED".

V1.3 introduces a proper provenance model that distinguishes four layers:

1. RAW_SOURCE          — bytes captured from the source (HTML, PDF, etc.)
2. NORMALIZED_SOURCE   — cleaned text (tags stripped, whitespace normalized)
3. RECONSTRUCTED_TEXT  — "ARTICULO N. <text>" concatenated for indexing
4. INDEXED_TEXT        — individual article text stored in articles[] list

Each layer carries its own SHA-256 hash so that tampering at any layer can be
detected via `DocumentProvenance.verify_integrity()`.

For V1.2 articles the original HTML bytes were discarded by Playwright after
extraction, so `raw_bytes` is NOT available retroactively — the V1.3 corpus
marks these documents with `provenance_status="PARTIAL"`. V1.4+ should
re-fetch with Playwright preserving `raw_bytes` to reach
`provenance_status="VERIFIED"`.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# Canonical labels for the four provenance layers.
LAYER_RAW_SOURCE = "RAW_SOURCE"
LAYER_NORMALIZED_SOURCE = "NORMALIZED_SOURCE"
LAYER_RECONSTRUCTED_TEXT = "RECONSTRUCTED_TEXT"
LAYER_INDEXED_TEXT = "INDEXED_TEXT"

# Sentinel hash for "we cannot verify this layer retroactively".
NOT_VERIFIED = "NOT_VERIFIED"

# Canonical provenance statuses for a document.
PROV_VERIFIED = "VERIFIED"
PROV_PARTIAL = "PARTIAL"
PROV_NOT_VERIFIED = "NOT_VERIFIED"


def _sha256_bytes(data: bytes) -> str:
    """SHA-256 hex digest of a bytes payload."""
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    """SHA-256 hex digest of a str payload (UTF-8 encoded)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_iso_utc() -> str:
    """Current UTC timestamp in ISO 8601 with 'Z' suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class SourceCapture:
    """Evidence of capture from a source.

    Captures the raw bytes returned by the source (e.g. HTML, PDF) along with
    retrieval metadata: URL, HTTP status, content-type, timestamp, method,
    and the SHA-256 of those raw bytes.
    """
    source_url: str
    source_domain: str
    retrieval_timestamp: str  # ISO 8601 UTC
    http_status: int
    content_type: str  # text/html, application/pdf, etc.
    raw_bytes: bytes  # actual source bytes
    raw_bytes_hash: str  # SHA-256 of raw_bytes
    retrieval_method: str  # "playwright", "urllib", "manual"
    retrieval_version: str  # "V2.3-E" etc.

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "source_domain": self.source_domain,
            "retrieval_timestamp": self.retrieval_timestamp,
            "http_status": self.http_status,
            "content_type": self.content_type,
            "raw_bytes_len": len(self.raw_bytes),
            "raw_bytes_hash": self.raw_bytes_hash,
            "retrieval_method": self.retrieval_method,
            "retrieval_version": self.retrieval_version,
        }


@dataclass
class NormalizedContent:
    """Normalized source — HTML tags stripped, whitespace normalized.

    This is the cleaned text derived from `raw_bytes` by a deterministic
    transformation (e.g. regex strip_tags + whitespace normalize). The
    `text_hash` is the SHA-256 of the normalized text.
    """
    text: str
    text_hash: str  # SHA-256 of normalized text
    transformation: str  # human-readable description of the transformation

    def as_dict(self) -> dict[str, Any]:
        return {
            "text_len": len(self.text),
            "text_hash": self.text_hash,
            "transformation": self.transformation,
        }


@dataclass
class DocumentProvenance:
    """Complete provenance chain for a legal document.

    Combines source capture, normalized content, and reconstructed/indexed
    text into a single tamper-evident record. Every hash is verifiable
    against its corresponding content via `verify_integrity()`.
    """
    source_capture: SourceCapture
    normalized_content: NormalizedContent
    reconstructed_text: str  # "ARTICULO N. <text>" concatenated
    reconstructed_text_hash: str  # SHA-256 of reconstructed_text
    transformation_metadata: dict[str, Any] = field(default_factory=dict)
    ingestion_timestamp: str = ""  # ISO 8601 UTC
    ingestion_version: str = "V1.3"
    corpus_version: str = "V1.3"

    def __post_init__(self) -> None:
        if not self.ingestion_timestamp:
            self.ingestion_timestamp = _now_iso_utc()

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_capture": self.source_capture.as_dict(),
            "normalized_content": self.normalized_content.as_dict(),
            "reconstructed_text_len": len(self.reconstructed_text),
            "reconstructed_text_hash": self.reconstructed_text_hash,
            "transformation_metadata": dict(self.transformation_metadata),
            "ingestion_timestamp": self.ingestion_timestamp,
            "ingestion_version": self.ingestion_version,
            "corpus_version": self.corpus_version,
        }

    def verify_integrity(self) -> dict[str, bool]:
        """Verify all hashes match their content.

        Returns a dict with one boolean per layer. A `True` value means the
        stored hash matches the recomputed hash of the current content —
        i.e. that layer has not been tampered with since ingestion.
        """
        return {
            "raw_bytes_hash_ok": (
                self.source_capture.raw_bytes_hash != NOT_VERIFIED
                and _sha256_bytes(self.source_capture.raw_bytes)
                == self.source_capture.raw_bytes_hash
            ),
            "normalized_hash_ok": _sha256_text(self.normalized_content.text)
            == self.normalized_content.text_hash,
            "reconstructed_hash_ok": _sha256_text(self.reconstructed_text)
            == self.reconstructed_text_hash,
        }

    @property
    def all_hashes_ok(self) -> bool:
        """True iff every verifiable layer's hash matches."""
        checks = self.verify_integrity()
        # NOT_VERIFIED layers count as "not ok" — caller should also check
        # provenance_status at the document level.
        return all(checks.values())


def compute_provenance_status(
    *,
    raw_bytes_available: bool,
    raw_bytes_hash_ok: bool,
    normalized_hash_ok: bool,
    reconstructed_hash_ok: bool,
) -> str:
    """Compute the document-level provenance status.

    - VERIFIED       — every layer present and hash matches.
    - PARTIAL        — at least one layer missing OR a non-critical layer
                       (raw_bytes) is unavailable, but normalized + reconstructed
                       layers are present and match.
    - NOT_VERIFIED   — any verifiable layer's hash mismatches, OR more than
                       the raw_bytes layer is missing.
    """
    # If any verifiable layer's hash mismatches → NOT_VERIFIED.
    if not normalized_hash_ok or not reconstructed_hash_ok:
        return PROV_NOT_VERIFIED
    if not raw_bytes_available:
        # raw_bytes missing but normalized + reconstructed OK → PARTIAL.
        return PROV_PARTIAL
    if not raw_bytes_hash_ok:
        return PROV_NOT_VERIFIED
    return PROV_VERIFIED


__all__ = [
    "LAYER_INDEXED_TEXT",
    "LAYER_NORMALIZED_SOURCE",
    "LAYER_RAW_SOURCE",
    "LAYER_RECONSTRUCTED_TEXT",
    "NOT_VERIFIED",
    "PROV_NOT_VERIFIED",
    "PROV_PARTIAL",
    "PROV_VERIFIED",
    "DocumentProvenance",
    "NormalizedContent",
    "SourceCapture",
    "compute_provenance_status",
]
