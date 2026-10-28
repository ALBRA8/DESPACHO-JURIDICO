"""
INGESTION PIPELINE — formal, idempotent, fail-closed, auditable.

Block 3 of HARDENING-2. A standalone, synchronous pipeline orchestrator that
complements `albra.knowledge.ingestion.LegalIngestionPipeline` (which is async
and tightly coupled to schemas + retriever providers). This module focuses on
the *control flow* of the chain itself:

    SOURCE → FETCH → VALIDATE → RAW → NORMALIZE → EXTRACT → METADATA →
    HASH → PROVENANCE → INDEX → VERIFY

Properties enforced:
- Idempotent  : re-ingesting the same `source_url` with unchanged content
                is a no-op (detected by content hash). Re-ingesting with
                *changed* content is flagged via `detected_change=True` and the
                new version supersedes the previous entry in the registry.
- Fail-closed : any stage raising -> pipeline stops, returns ok=False with
                the error and the partial pipeline_log.
- Auditable   : every stage appends a structured entry to `pipeline_log`,
                which is returned on the IngestionResult.

The pipeline is PURE PYTHON and synchronous to keep it deterministic and
unit-testable without async fixtures. Pluggable hooks (`fetcher`, `validator`,
`normalizer`, `extractor`, `indexer`) let callers wire real I/O; default
implementations are conservative in-memory stubs.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from albra.observability.logger import get_logger

# ---------------------------------------------------------------------------
# Pipeline result + log
# ---------------------------------------------------------------------------


@dataclass
class PipelineLogEntry:
    """One row in the pipeline execution log."""

    stage: str
    order: int
    ok: bool
    detail: str = ""
    duration_ms: float = 0.0
    ts: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "order": self.order,
            "ok": self.ok,
            "detail": self.detail,
            "duration_ms": round(self.duration_ms, 3),
            "ts": self.ts,
        }


@dataclass
class IngestionResult:
    """Outcome of running the pipeline for one source_url."""

    source_url: str
    ok: bool = False
    content_hash: str = ""
    document_id: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)
    pipeline_log: list[PipelineLogEntry] = field(default_factory=list)
    error: str = ""
    skipped: bool = False           # True when idempotent skip fired
    detected_change: bool = False   # True when re-ingest detected content change
    metadata: dict[str, Any] = field(default_factory=dict)

    def stage_names_in_order(self) -> list[str]:
        """Return the ordered list of executed stage names (for assertions)."""
        return [e.stage for e in self.pipeline_log]


# ---------------------------------------------------------------------------
# Hook protocols (Callable aliases for clarity)
# ---------------------------------------------------------------------------

Fetcher = Callable[[str], tuple[int, bytes]]
"""Returns (http_status, raw_bytes). Raise to simulate fetch failure."""

Validator = Callable[[bytes], bool]
"""Returns True if raw_bytes are acceptable; False to fail-closed."""

Normalizer = Callable[[bytes], str]
"""Convert raw bytes to a normalized text string."""

Extractor = Callable[[str], dict[str, Any]]
"""Extract structured fields (title, type, articles) from normalized text."""

Indexer = Callable[[dict[str, Any]], str]
"""Index the metadata+content; return an opaque index handle/id."""


# ---------------------------------------------------------------------------
# Default in-memory hooks (stubs — production wires real ones)
# ---------------------------------------------------------------------------


def _default_fetcher(url: str) -> tuple[int, bytes]:
    """Default fetcher: returns 404 + empty body.

    Production must inject a real fetcher. Returning empty body causes the
    VALIDATE stage to fail-closed — safe default.
    """
    return (404, b"")


def _default_validator(raw: bytes) -> bool:
    """Default validator: reject empty or absurdly large payloads."""
    if not raw:
        return False
    if len(raw) > 50 * 1024 * 1024:  # 50 MB hard cap
        return False
    return True


def _default_normalizer(raw: bytes) -> str:
    """Default normalizer: UTF-8 decode + whitespace strip."""
    return raw.decode("utf-8", errors="ignore").strip()


def _default_extractor(text: str) -> dict[str, Any]:
    """Default extractor: returns the raw text as the document body."""
    return {
        "title": text.splitlines()[0][:200] if text else "",
        "document_type": "unknown",
        "text": text,
        "article_count": text.count("ARTICULO"),
    }


def _default_indexer(meta: dict[str, Any]) -> str:
    """Default indexer: returns a synthetic id; no real storage."""
    return uuid.uuid4().hex[:16]


# ---------------------------------------------------------------------------
# Registry — tracks ingested source_url -> content_hash for idempotency
# ---------------------------------------------------------------------------


class _IngestionRegistry:
    """In-memory registry of ingested URLs.

    Keys: source_url. Values: dict with content_hash, document_id, ingested_at,
    and the index handle returned by the indexer.
    """

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []  # preserve insertion order

    def get(self, source_url: str) -> dict[str, Any] | None:
        return self._entries.get(source_url)

    def upsert(self, source_url: str, entry: dict[str, Any]) -> None:
        if source_url not in self._entries:
            self._order.append(source_url)
        self._entries[source_url] = entry

    def __len__(self) -> int:
        return len(self._entries)

    def all_entries(self) -> list[dict[str, Any]]:
        return [self._entries[u] for u in self._order]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class IngestionPipeline:
    """Formal ingestion pipeline.

    Stages (in order):
        SOURCE → FETCH → VALIDATE → RAW → NORMALIZE → EXTRACT →
        METADATA → HASH → PROVENANCE → INDEX → VERIFY
    """

    STAGES: tuple[str, ...] = (
        "source",
        "fetch",
        "validate",
        "raw",
        "normalize",
        "extract",
        "metadata",
        "hash",
        "provenance",
        "index",
        "verify",
    )

    def __init__(
        self,
        *,
        fetcher: Fetcher | None = None,
        validator: Validator | None = None,
        normalizer: Normalizer | None = None,
        extractor: Extractor | None = None,
        indexer: Indexer | None = None,
        registry: _IngestionRegistry | None = None,
    ) -> None:
        self.log = get_logger("albra.ingestion_pipeline")
        self.fetcher = fetcher or _default_fetcher
        self.validator = validator or _default_validator
        self.normalizer = normalizer or _default_normalizer
        self.extractor = extractor or _default_extractor
        self.indexer = indexer or _default_indexer
        self.registry = registry or _IngestionRegistry()

    # ----- public API -----------------------------------------------------

    def run(self, source_url: str) -> IngestionResult:
        """Run the full chain for `source_url`.

        Idempotent: if `source_url` was already ingested AND the fetched
        content's hash matches the registry's recorded hash, the pipeline
        returns `skipped=True` and `ok=True` without re-indexing.
        """
        result = IngestionResult(source_url=source_url)

        # ----- 1. SOURCE -----
        self._stage_source(result, source_url)
        if not result.pipeline_log[-1].ok:
            return result  # fail-closed

        # ----- 2. FETCH -----
        raw_bytes, http_status = self._stage_fetch(result, source_url)
        if not result.pipeline_log[-1].ok:
            return result  # fail-closed

        # ----- Idempotency short-circuit (requires hash, so compute early) -----
        early_hash = hashlib.sha256(raw_bytes).hexdigest()
        prior = self.registry.get(source_url)
        if prior is not None:
            if prior.get("content_hash") == early_hash:
                # Same URL, same content -> idempotent skip.
                self._log(result, "verify", ok=True, detail="idempotent skip — content unchanged")
                result.ok = True
                result.skipped = True
                result.content_hash = early_hash
                result.document_id = prior.get("document_id", "")
                result.provenance = prior.get("provenance", {})
                return result
            # Same URL, DIFFERENT content -> flag change, continue ingestion.
            result.detected_change = True
            self.log.warning(
                "ingestion_pipeline.changed_source",
                source_url=source_url,
                old_hash=str(prior.get("content_hash"))[:12],
                new_hash=early_hash[:12],
            )

        # ----- 3. VALIDATE -----
        if not self._stage_validate(result, raw_bytes):
            return result

        # ----- 4. RAW (record hash + size) -----
        self._stage_raw(result, raw_bytes, early_hash)

        # ----- 5. NORMALIZE -----
        normalized = self._stage_normalize(result, raw_bytes)
        if not result.pipeline_log[-1].ok:
            return result

        # ----- 6. EXTRACT -----
        extracted = self._stage_extract(result, normalized)
        if not result.pipeline_log[-1].ok:
            return result

        # ----- 7. METADATA -----
        metadata = self._stage_metadata(result, source_url, http_status, extracted)
        if not result.pipeline_log[-1].ok:
            return result

        # ----- 8. HASH (already computed; record formally) -----
        self._stage_hash(result, early_hash)

        # ----- 9. PROVENANCE -----
        provenance = self._stage_provenance(
            result,
            source_url=source_url,
            content_hash=early_hash,
            http_status=http_status,
            metadata=metadata,
        )

        # ----- 10. INDEX -----
        document_id = self._stage_index(result, metadata, provenance)
        if not result.pipeline_log[-1].ok:
            return result

        # ----- 11. VERIFY -----
        self._stage_verify(result, early_hash, document_id, provenance)
        if not result.pipeline_log[-1].ok:
            return result

        # ----- commit to registry -----
        result.ok = True
        result.document_id = document_id
        result.content_hash = early_hash
        result.provenance = provenance
        self.registry.upsert(source_url, {
            "content_hash": early_hash,
            "document_id": document_id,
            "ingested_at": time.time(),
            "provenance": provenance,
            "metadata": metadata,
            "index_handle": document_id,
        })
        return result

    # ----- per-stage methods ---------------------------------------------

    def _log(
        self,
        result: IngestionResult,
        stage: str,
        *,
        ok: bool,
        detail: str = "",
        duration_ms: float = 0.0,
    ) -> None:
        order = len(result.pipeline_log)  # 0-based, but order in tuple dictates canonical order
        entry = PipelineLogEntry(
            stage=stage,
            order=order,
            ok=ok,
            detail=detail,
            duration_ms=duration_ms,
        )
        result.pipeline_log.append(entry)
        # Also emit a structured log line for the observability stack.
        if ok:
            self.log.info("pipeline.stage.ok", stage=stage, detail=detail[:200])
        else:
            self.log.error("pipeline.stage.fail", stage=stage, detail=detail[:200])

    # -- Stage implementations --

    def _stage_source(self, result: IngestionResult, source_url: str) -> None:
        t0 = time.perf_counter()
        if not source_url or not source_url.strip():
            self._log(
                result, "source", ok=False,
                detail="source_url is empty",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
            result.error = "source_url is empty"
            return
        if not (source_url.startswith("http://") or source_url.startswith("https://")):
            self._log(
                result, "source", ok=False,
                detail=f"source_url must be http(s): {source_url[:80]}",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
            result.error = "invalid source_url scheme"
            return
        self._log(
            result, "source", ok=True,
            detail=f"source_url={source_url[:120]}",
            duration_ms=(time.perf_counter() - t0) * 1000,
        )

    def _stage_fetch(self, result: IngestionResult, source_url: str) -> tuple[bytes, int]:
        t0 = time.perf_counter()
        try:
            http_status, raw = self.fetcher(source_url)
        except Exception as exc:  # noqa: BLE001 — fail-closed, we record the error
            self._log(
                result, "fetch", ok=False,
                detail=f"fetcher raised: {exc!s}",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
            result.error = f"fetch failed: {exc!s}"
            return (b"", 0)
        if not isinstance(http_status, int) or http_status < 200 or http_status >= 400:
            self._log(
                result, "fetch", ok=False,
                detail=f"http_status={http_status}",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
            result.error = f"fetch returned non-2xx status {http_status}"
            return (b"", http_status)
        self._log(
            result, "fetch", ok=True,
            detail=f"http_status={http_status}, bytes={len(raw)}",
            duration_ms=(time.perf_counter() - t0) * 1000,
        )
        return (raw, http_status)

    def _stage_validate(self, result: IngestionResult, raw: bytes) -> bool:
        t0 = time.perf_counter()
        try:
            ok = bool(self.validator(raw))
        except Exception as exc:  # noqa: BLE001
            self._log(
                result, "validate", ok=False,
                detail=f"validator raised: {exc!s}",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
            result.error = f"validate failed: {exc!s}"
            return False
        if not ok:
            self._log(
                result, "validate", ok=False,
                detail="validator rejected payload (empty or too large)",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
            result.error = "validate rejected payload"
            return False
        self._log(
            result, "validate", ok=True,
            detail=f"bytes={len(raw)} accepted",
            duration_ms=(time.perf_counter() - t0) * 1000,
        )
        return True

    def _stage_raw(self, result: IngestionResult, raw: bytes, content_hash: str) -> None:
        t0 = time.perf_counter()
        self._log(
            result, "raw", ok=True,
            detail=f"bytes={len(raw)}, sha256={content_hash[:12]}",
            duration_ms=(time.perf_counter() - t0) * 1000,
        )

    def _stage_normalize(self, result: IngestionResult, raw: bytes) -> str:
        t0 = time.perf_counter()
        try:
            normalized = self.normalizer(raw)
        except Exception as exc:  # noqa: BLE001
            self._log(
                result, "normalize", ok=False,
                detail=f"normalizer raised: {exc!s}",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
            result.error = f"normalize failed: {exc!s}"
            return ""
        if not normalized:
            self._log(
                result, "normalize", ok=False,
                detail="normalized text is empty",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
            result.error = "normalize produced empty text"
            return ""
        self._log(
            result, "normalize", ok=True,
            detail=f"chars={len(normalized)}",
            duration_ms=(time.perf_counter() - t0) * 1000,
        )
        return normalized

    def _stage_extract(self, result: IngestionResult, text: str) -> dict[str, Any]:
        t0 = time.perf_counter()
        try:
            extracted = self.extractor(text) or {}
        except Exception as exc:  # noqa: BLE001
            self._log(
                result, "extract", ok=False,
                detail=f"extractor raised: {exc!s}",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
            result.error = f"extract failed: {exc!s}"
            return {}
        if not isinstance(extracted, dict):
            self._log(
                result, "extract", ok=False,
                detail=f"extractor returned non-dict: {type(extracted).__name__}",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
            result.error = "extract returned non-dict"
            return {}
        self._log(
            result, "extract", ok=True,
            detail=f"fields={sorted(extracted.keys())}",
            duration_ms=(time.perf_counter() - t0) * 1000,
        )
        return extracted

    def _stage_metadata(
        self,
        result: IngestionResult,
        source_url: str,
        http_status: int,
        extracted: dict[str, Any],
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        metadata = {
            "source_url": source_url,
            "http_status": http_status,
            "title": extracted.get("title", ""),
            "document_type": extracted.get("document_type", "unknown"),
            "article_count": extracted.get("article_count", 0),
            "ingested_at": time.time(),
        }
        self._log(
            result, "metadata", ok=True,
            detail=f"type={metadata['document_type']}, articles={metadata['article_count']}",
            duration_ms=(time.perf_counter() - t0) * 1000,
        )
        result.metadata = metadata
        return metadata

    def _stage_hash(self, result: IngestionResult, content_hash: str) -> None:
        t0 = time.perf_counter()
        self._log(
            result, "hash", ok=True,
            detail=f"sha256={content_hash[:12]}",
            duration_ms=(time.perf_counter() - t0) * 1000,
        )

    def _stage_provenance(
        self,
        result: IngestionResult,
        *,
        source_url: str,
        content_hash: str,
        http_status: int,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        provenance = {
            "source_url": source_url,
            "source_url_format_valid": source_url.startswith(("http://", "https://")),
            "source_url_accessible": 200 <= http_status < 400,
            "source_tier": "S1_OFFICIAL",  # default tier for pipeline-level ingestion
            "authority": metadata.get("document_type", "unknown"),
            "retrieval_timestamp": time.time(),
            "content_hash": content_hash,
            "transformation_chain": ["raw", "normalized", "extracted", "indexed"],
        }
        self._log(
            result, "provenance", ok=True,
            detail=f"fields={len(provenance)}",
            duration_ms=(time.perf_counter() - t0) * 1000,
        )
        return provenance

    def _stage_index(
        self,
        result: IngestionResult,
        metadata: dict[str, Any],
        provenance: dict[str, Any],
    ) -> str:
        t0 = time.perf_counter()
        index_payload = {**metadata, "provenance": provenance}
        try:
            index_handle = self.indexer(index_payload)
        except Exception as exc:  # noqa: BLE001
            self._log(
                result, "index", ok=False,
                detail=f"indexer raised: {exc!s}",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
            result.error = f"index failed: {exc!s}"
            return ""
        if not index_handle:
            self._log(
                result, "index", ok=False,
                detail="indexer returned empty handle",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
            result.error = "index returned empty handle"
            return ""
        self._log(
            result, "index", ok=True,
            detail=f"handle={index_handle}",
            duration_ms=(time.perf_counter() - t0) * 1000,
        )
        return index_handle

    def _stage_verify(
        self,
        result: IngestionResult,
        content_hash: str,
        document_id: str,
        provenance: dict[str, Any],
    ) -> None:
        t0 = time.perf_counter()
        # Verify the post-conditions the pipeline promises.
        if not content_hash:
            self._log(result, "verify", ok=False, detail="content_hash missing")
            result.error = "verify: content_hash missing"
            return
        if not document_id:
            self._log(result, "verify", ok=False, detail="document_id missing")
            result.error = "verify: document_id missing"
            return
        if not provenance.get("source_url"):
            self._log(result, "verify", ok=False, detail="provenance.source_url missing")
            result.error = "verify: provenance.source_url missing"
            return
        self._log(
            result, "verify", ok=True,
            detail=f"document_id={document_id}, hash={content_hash[:12]}",
            duration_ms=(time.perf_counter() - t0) * 1000,
        )

    # ----- introspection --------------------------------------------------

    def stats(self) -> dict[str, Any]:
        return {
            "stages": list(self.STAGES),
            "ingested_urls": len(self.registry),
        }
