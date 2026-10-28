"""
CORPUS V1.3 — REAL PROVENANCE MODEL.

V1.2 (commit 81a9c83) had a provenance gap: `raw_content` was reconstructed
text (the "ARTICULO N. <text>" concatenation), NOT HTML source bytes, and
`content_hash` was the SHA-256 of that reconstructed text — NOT of the
source HTML. The user explicitly flagged this as "NOT VERIFIED".

V1.3 introduces a proper provenance model (albra.knowledge.provenance)
that distinguishes four layers:

- RAW_SOURCE          — bytes captured from the source (HTML, PDF, etc.)
- NORMALIZED_SOURCE  — cleaned text (tags stripped, whitespace normalized)
- RECONSTRUCTED_TEXT — "ARTICULO N. <text>" concatenated for indexing
- INDEXED_TEXT        — individual article text stored in articles[] list

Each layer carries its own SHA-256 hash; tampering at any layer is
detectable via `DocumentProvenance.verify_integrity()`.

LIMITATION: raw_bytes NOT available for V1.2 articles (Playwright HTML was
discarded after extraction). `raw_bytes_hash = NOT_VERIFIED` for these.
V1.4+ should re-fetch with Playwright and preserve raw_bytes.
"""
from __future__ import annotations

import hashlib
from typing import Any

from albra.knowledge.colombia.corpus_pilot.real_corpus_v12 import (
    _CONST_ARTICLES as _V12_CONST_ARTICLES,
)
from albra.knowledge.colombia.corpus_pilot.real_corpus_v12 import (
    _CONST_SOURCE_URL as _V12_CONST_SOURCE_URL,
)
from albra.knowledge.colombia.corpus_pilot.real_corpus_v12 import (
    _LEY80_ARTICLES as _V12_LEY80_ARTICLES,
)
from albra.knowledge.colombia.corpus_pilot.real_corpus_v12 import (
    _LEY80_SOURCE_URL as _V12_LEY80_SOURCE_URL,
)
from albra.knowledge.colombia.corpus_pilot.real_corpus_v12 import (
    _LEY100_ARTICLES as _V12_LEY100_ARTICLES,
)
from albra.knowledge.colombia.corpus_pilot.real_corpus_v12 import (
    _LEY100_SOURCE_URL as _V12_LEY100_SOURCE_URL,
)
from albra.knowledge.provenance import (
    NOT_VERIFIED,
    PROV_PARTIAL,
    DocumentProvenance,
    NormalizedContent,
    SourceCapture,
    compute_provenance_status,
)

# V1.3 corpus — articles from V1.2 with provenance model applied.
# LIMITATION: raw_bytes NOT available for V1.2 articles (Playwright HTML was
# discarded after extraction). raw_bytes_hash = NOT_VERIFIED for these.
# V1.4+ should re-fetch with Playwright and preserve raw_bytes.

V13_PROVENANCE_NOTE = """
Articles in V1.3 were extracted from V1.2 (commit 81a9c83).
V1.2 articles were fetched with Playwright V2.3-E but the HTML bytes
were discarded after extraction. Only the extracted article text was stored.

V1.3 applies the DocumentProvenance model retroactively:
- source_url: VERIFIED (documented)
- raw_bytes: NOT AVAILABLE (HTML was discarded)
- raw_bytes_hash: NOT VERIFIED
- normalized_content: RECONSTRUCTED from stored articles
- reconstructed_text_hash: VERIFIED (SHA-256 of reconstructed text)
- provenance_completeness: PARTIAL

For V1.4+: re-fetch with Playwright preserving raw_bytes.
"""

_V12_FETCH_VERSION = "V2.3-E (Playwright headless Chromium)"
_V12_FETCH_TIMESTAMP = "2024-10-22T00:00:00Z"  # V1.2 fetch (commit 81a9c83)
_V13_INGESTION_VERSION = "V1.3"
_V13_CORPUS_VERSION = "V1.3"
_V13_INGESTION_TIMESTAMP = "2024-10-22T00:00:00Z"  # retroactive V1.3 stamp


def _domain_of(url: str) -> str:
    """Extract the host (domain) from a URL — simple parser, no deps."""
    if "://" not in url:
        return url.split("/", 1)[0]
    rest = url.split("://", 1)[1]
    return rest.split("/", 1)[0]


def _sort_key(item: tuple[str, str]) -> tuple[int, int | str]:
    k = item[0]
    try:
        return (0, int(k))
    except (ValueError, TypeError):
        return (1, k)


def _build_reconstructed_text(articles_dict: dict[str, str]) -> str:
    """Build 'ARTICULO N. <text>' concatenation from articles dict, sorted."""
    return "\n\n".join(
        f"ARTICULO {num}. {text}"
        for num, text in sorted(articles_dict.items(), key=_sort_key)
    )


def _build_articles_list(articles_dict: dict[str, str]) -> list[dict[str, str]]:
    """Build the indexed articles list, sorted by numeric article number."""
    return [
        {"number": num, "text": text}
        for num, text in sorted(articles_dict.items(), key=_sort_key)
    ]


def _build_partial_provenance(
    *,
    source_url: str,
    reconstructed_text: str,
) -> DocumentProvenance:
    """Build a DocumentProvenance with PARTIAL status for V1.2 retroactive articles.

    raw_bytes is NOT available (HTML was discarded by the V1.2 Playwright run).
    raw_bytes_hash is the sentinel NOT_VERIFIED. normalized_content.text is set
    equal to the reconstructed text, because V1.2 did not preserve a separate
    normalized layer.
    """
    reconstructed_hash = hashlib.sha256(reconstructed_text.encode("utf-8")).hexdigest()
    capture = SourceCapture(
        source_url=source_url,
        source_domain=_domain_of(source_url),
        retrieval_timestamp=_V12_FETCH_TIMESTAMP,
        http_status=200,
        content_type="text/html",
        raw_bytes=b"",  # NOT AVAILABLE — V1.2 discarded HTML after extraction
        raw_bytes_hash=NOT_VERIFIED,
        retrieval_method="playwright",
        retrieval_version=_V12_FETCH_VERSION,
    )
    normalized = NormalizedContent(
        text=reconstructed_text,
        text_hash=reconstructed_hash,
        transformation=(
            "V1.2 HTML→text (Playwright V2.3-E + regex strip_tags + whitespace "
            "normalize). NOTE: V1.2 discarded HTML after extraction, so this "
            "normalized layer is RECONSTRUCTED from stored articles, not derived "
            "from preserved raw_bytes."
        ),
    )
    return DocumentProvenance(
        source_capture=capture,
        normalized_content=normalized,
        reconstructed_text=reconstructed_text,
        reconstructed_text_hash=reconstructed_hash,
        transformation_metadata={
            "parser_version": _V12_FETCH_VERSION,
            "extraction_params": "regex ARTICULO N. + cleanup 'o.' prefix",
            "v13_limitation": (
                "raw_bytes not preserved from V1.2 fetch; HTML discarded after "
                "extraction. V1.4+ should re-fetch with Playwright preserving raw_bytes."
            ),
            "v13_provenance_status": PROV_PARTIAL,
        },
        ingestion_timestamp=_V13_INGESTION_TIMESTAMP,
        ingestion_version=_V13_INGESTION_VERSION,
        corpus_version=_V13_CORPUS_VERSION,
    )


def _build_v13_document(
    *,
    source_id: str,
    source_url: str,
    source_tier: str,
    authority: str,
    jurisdiction: str,
    document_type: str,
    title: str,
    number: str,
    date_issued: str,
    publication_date: str,
    effective_from: str,
    status: str,
    articles_dict: dict[str, str],
) -> dict[str, Any]:
    """Build a V1.3 document dict with the provenance model applied."""
    reconstructed_text = _build_reconstructed_text(articles_dict)
    provenance = _build_partial_provenance(
        source_url=source_url,
        reconstructed_text=reconstructed_text,
    )
    integrity = provenance.verify_integrity()
    status_flag = compute_provenance_status(
        raw_bytes_available=False,  # V1.2 retroactive — HTML discarded
        raw_bytes_hash_ok=integrity["raw_bytes_hash_ok"],
        normalized_hash_ok=integrity["normalized_hash_ok"],
        reconstructed_hash_ok=integrity["reconstructed_hash_ok"],
    )
    return {
        "source_id": source_id,
        "source_url": source_url,
        "source_tier": source_tier,
        "authority": authority,
        "jurisdiction": jurisdiction,
        "document_type": document_type,
        "title": title,
        "number": number,
        "date_issued": date_issued,
        "publication_date": publication_date,
        "effective_from": effective_from,
        "effective_until": None,
        "status": status,
        # V1.3 provenance model — replaces V1.2's raw_content + content_hash.
        "provenance": provenance,
        "provenance_status": status_flag,
        # Indexed articles (kept for retrieval & citation audit).
        "articles": _build_articles_list(articles_dict),
        # Backward-compat fields for V1.2 consumers (e.g. CitationAuditor).
        "reconstructed_text": reconstructed_text,
        "reconstructed_text_hash": provenance.reconstructed_text_hash,
        "transformation": provenance.normalized_content.transformation,
    }


# === CONSTITUCIÓN 1991 (32 articles) — V1.3 with provenance model ===
CONSTITUCION_1991_V13: dict[str, Any] = _build_v13_document(
    source_id="const_1991_real_v13",
    source_url=_V12_CONST_SOURCE_URL,
    source_tier="S0_PRIMARY_SUPERIOR",
    authority="Asamblea Nacional Constituyente",
    jurisdiction="CO",
    document_type="constitucion",
    title="Constitución Política de Colombia",
    number="Constitución Política de 1991",
    date_issued="1991-07-04",
    publication_date="1991-07-07",
    effective_from="1991-07-04",
    status="vigente",
    articles_dict=_V12_CONST_ARTICLES,
)

# === LEY 100 DE 1993 (45 articles) — V1.3 with provenance model ===
LEY_100_1993_V13: dict[str, Any] = _build_v13_document(
    source_id="ley_100_1993_real_v13",
    source_url=_V12_LEY100_SOURCE_URL,
    source_tier="S0_PRIMARY_SUPERIOR",
    authority="Congreso de la República",
    jurisdiction="CO",
    document_type="ley",
    title=(
        "Por la cual se crea el sistema de seguridad social integral y se dictan "
        "otras disposiciones"
    ),
    number="Ley 100 de 1993",
    date_issued="1993-12-23",
    publication_date="1993-12-30",
    effective_from="1993-12-30",
    status="modificada",
    articles_dict=_V12_LEY100_ARTICLES,
)

# === LEY 80 DE 1993 (48 articles) — V1.3 with provenance model ===
LEY_80_1993_V13: dict[str, Any] = _build_v13_document(
    source_id="ley_80_1993_real_v13",
    source_url=_V12_LEY80_SOURCE_URL,
    source_tier="S0_PRIMARY_SUPERIOR",
    authority="Congreso de la República",
    jurisdiction="CO",
    document_type="ley",
    title=(
        "Por la cual se expide el Estatuto General de Contratación de la "
        "Administración Pública"
    ),
    number="Ley 80 de 1993",
    date_issued="1993-10-28",
    publication_date="1993-11-04",
    effective_from="1993-11-04",
    status="modificada",
    articles_dict=_V12_LEY80_ARTICLES,
)

# === ALL DOCUMENTS V1.3 ===
ALL_DOCUMENTS_V13: list[tuple[str, dict[str, Any]]] = [
    ("constitucion", CONSTITUCION_1991_V13),
    ("ley", LEY_100_1993_V13),
    ("ley", LEY_80_1993_V13),
]

V13_STATS: dict[str, Any] = {
    "v12_total_articles": 125,
    "v13_total_articles": sum(len(d["articles"]) for _, d in ALL_DOCUMENTS_V13),
    "v13_documents": len(ALL_DOCUMENTS_V13),
    "v13_provenance_model": (
        "DocumentProvenance (RAW_SOURCE / NORMALIZED_SOURCE / "
        "RECONSTRUCTED_TEXT / INDEXED_TEXT)"
    ),
    "v13_provenance_status_default": PROV_PARTIAL,
    "v13_limitation": "raw_bytes NOT available for V1.2 retroactive articles",
    "v13_ingestion_version": _V13_INGESTION_VERSION,
    "v13_corpus_version": _V13_CORPUS_VERSION,
}

__all__ = [
    "ALL_DOCUMENTS_V13",
    "CONSTITUCION_1991_V13",
    "LEY_100_1993_V13",
    "LEY_80_1993_V13",
    "V13_PROVENANCE_NOTE",
    "V13_STATS",
]
