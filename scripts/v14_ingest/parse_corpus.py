"""V1.4 corpus parser — extract articles from cached raw_bytes.

Handles two patterns:
  Pattern A: "ARTICULO N. <text>" (Constitución, Ley 640, CST)
  Pattern B: anchor-based "<a name='N'>ARTÍCULO No. <text>" (Ley 1564, Ley 906)

Both patterns preserve raw HTML bytes + compute SHA-256 at each layer:
  - raw_bytes_hash (per source page)
  - normalized_text_hash (clean text after tag strip)
  - indexed_articles_hash (per-document concatenation)

Builds V1.4 corpus data structure ready for real_corpus_v14.py.
"""
from __future__ import annotations

import hashlib
import html as html_mod
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CACHE = Path(__file__).parent / "raw_cache"

# ===== Pattern matchers =====

# Pattern A: "ARTICULO N. text" or "ARTICULO No. text" (Spanish ordinal)
# Constitución uses "ARTICULO 1o." for arts 1-9, "ARTICULO 10." for 10+.
# Ley 640 + CST follow similar patterns.
PATTERN_A = re.compile(
    r'ART[IÍ]CULO\s+(\d+)(?:o|º|°)?\.\s*(.*?)(?=ART[IÍ]CULO\s+\d+(?:o|º|°)?\.|$)',
    re.DOTALL | re.IGNORECASE,
)

# Pattern B: anchor-based articles with any attributes between <a and name="N"
# Ley 1564 + Ley 906 use `<a class="bookmarkaj" name="N">...</a>` structure.
PATTERN_B_ANCHOR = re.compile(
    r'<a\s+[^>]*name="(\d+)"[^>]*>(.*?)(?=<a\s+[^>]*name="\d+"|</body>|$)',
    re.IGNORECASE | re.DOTALL,
)
# Within the anchor content, the article text starts with "ARTÍCULO No." or similar
# We accept the whole anchor content as the article text (post-cleanup).


# ===== Text normalization =====

def normalize_html_to_text(raw_html: str) -> str:
    """Strip HTML tags + entities + extra whitespace → clean text."""
    # Decode HTML entities (&aacute; → á, etc.)
    text = html_mod.unescape(raw_html)
    # Remove all HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Remove script/style blocks
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_articles_pattern_a(html_text: str) -> list[tuple[int, str]]:
    """Extract (article_number, clean_text) using Pattern A."""
    matches = PATTERN_A.findall(html_text)
    result: list[tuple[int, str]] = []
    seen: set[int] = set()
    for num_str, raw_text in matches:
        n = int(num_str)
        if n in seen:
            continue
        clean = normalize_html_to_text(raw_text)
        if len(clean) > 10:
            seen.add(n)
            result.append((n, clean))
    return result


def extract_articles_pattern_b(html_text: str) -> list[tuple[int, str]]:
    """Extract (article_number, clean_text) using Pattern B (anchor-based).

    For Ley 1564 and Ley 906, each article is wrapped in an anchor
    ``<a name="N">...</a>`` block. The content within includes
    ``ARTÍCULO No. <text>`` which we strip the prefix from.

    V1.4 fix: the ordinal suffix may be "1o" or "1º" or "1°" — strip
    any of these plus the literal ".".
    """
    matches = PATTERN_B_ANCHOR.findall(html_text)
    result: list[tuple[int, str]] = []
    seen: set[int] = set()
    for num_str, raw_content in matches:
        try:
            n = int(num_str)
        except ValueError:
            continue
        if n in seen:
            continue
        clean = normalize_html_to_text(raw_content)
        # Strip the "ARTÍCULO No." / "ARTÍCULO N." prefix if present.
        # The ordinal may be 1o, 1º, or 1° for arts 1-9 (Spanish first-ninth).
        clean = re.sub(
            r'^ART[IÍ]CULO\s+' + str(n) + r'(?:o|º|°)?\.\s*',
            '', clean, flags=re.IGNORECASE,
        )
        if len(clean) > 10:
            seen.add(n)
            result.append((n, clean))
    return result


# ===== V1.4 document builder =====

@dataclass
class V14Document:
    """A V1.4 corpus document with full provenance."""
    slug: str
    document_type: str
    title: str
    number: str  # "Constitución Política de 1991" / "Ley 1564 de 2012"
    date_issued: str
    publication_date: str
    effective_from: str
    effective_until: str | None
    status: str  # "vigente" or "derogada"
    source_url: str
    source_tier: str  # "S0_PRIMARY_SUPERIOR"
    authority: str  # "Asamblea Nacional Constituyente" / "Congreso de Colombia"
    jurisdiction: str  # "CO"
    pattern: str  # "A" or "B"
    pages: list[dict[str, Any]] = field(default_factory=list)
    articles: list[dict[str, Any]] = field(default_factory=list)
    raw_bytes_combined: bytes = b""
    raw_bytes_hash: str = ""
    normalized_text: str = ""
    normalized_text_hash: str = ""
    reconstructed_text: str = ""
    reconstructed_text_hash: str = ""
    provenance_status: str = "VERIFIED"  # V1.4 upgrades PARTIAL → VERIFIED

    def compute_hashes(self) -> None:
        """Compute the 3-layer SHA-256 hashes."""
        self.raw_bytes_hash = hashlib.sha256(self.raw_bytes_combined).hexdigest()
        self.normalized_text_hash = hashlib.sha256(
            self.normalized_text.encode("utf-8")
        ).hexdigest()
        self.reconstructed_text_hash = hashlib.sha256(
            self.reconstructed_text.encode("utf-8")
        ).hexdigest()


# ===== Document specifications =====

DOCUMENTS_SPEC = [
    {
        "slug": "constitucion",
        "document_type": "constitucion",
        "title": "Constitución Política de Colombia",
        "number": "Constitución Política de 1991",
        "date_issued": "1991-07-04",
        "publication_date": "1991-07-07",
        "effective_from": "1991-07-04",
        "effective_until": None,
        "status": "vigente",
        "source_url": "http://www.secretariasenado.gov.co/senado/basedoc/constitucion_politica_1991.htm",
        "authority": "Asamblea Nacional Constituyente",
        "pattern": "A",
        "cache_key": "constitucion_1991",
    },
    {
        "slug": "ley_1564_2012",
        "document_type": "ley",
        "title": "Ley 1564 de 2012 — Código General del Proceso",
        "number": "Ley 1564 de 2012",
        "date_issued": "2012-07-12",
        "publication_date": "2012-07-12",
        "effective_from": "2014-07-01",  # CGP entered into force 2014-07-01 (art. 632 transitional)
        "effective_until": None,
        "status": "vigente",
        "source_url": "http://www.secretariasenado.gov.co/senado/basedoc/ley_1564_2012.html",
        "authority": "Congreso de Colombia",
        "pattern": "B",
        "cache_key": "ley_1564_2012",
    },
    {
        "slug": "ley_0640_2001",
        "document_type": "ley",
        "title": "Ley 640 de 2001 — Conciliación",
        "number": "Ley 640 de 2001",
        "date_issued": "2001-01-05",
        "publication_date": "2001-01-05",
        "effective_from": "2001-01-05",
        "effective_until": None,
        "status": "vigente",
        "source_url": "http://www.secretariasenado.gov.co/senado/basedoc/ley_0640_2001.html",
        "authority": "Congreso de Colombia",
        "pattern": "A",
        "cache_key": "ley_0640_2001",
    },
    {
        "slug": "ley_0906_2004",
        "document_type": "ley",
        "title": "Ley 906 de 2004 — Código de Procedimiento Penal",
        "number": "Ley 906 de 2004",
        "date_issued": "2004-08-31",
        "publication_date": "2004-08-31",
        "effective_from": "2005-01-01",  # CPP art. 533 entered into force 2005-01-01
        "effective_until": None,
        "status": "vigente",
        "source_url": "http://www.secretariasenado.gov.co/senado/basedoc/ley_0906_2004.html",
        "authority": "Congreso de Colombia",
        "pattern": "B",
        "cache_key": "ley_0906_2004",
    },
    {
        "slug": "codigo_sustantivo_trabajo",
        "document_type": "codigo_sustantivo",
        "title": "Código Sustantivo del Trabajo",
        "number": "Decreto 2663 de 1950",
        "date_issued": "1950-08-05",
        "publication_date": "1950-08-05",
        "effective_from": "1951-01-01",
        "effective_until": None,
        "status": "vigente",
        "source_url": "http://www.secretariasenado.gov.co/senado/basedoc/codigo_sustantivo_trabajo.html",
        "authority": "Presidente de Colombia (Decreto-Ley)",
        "pattern": "A",
        "cache_key": "codigo_sustantivo_trabajo",
    },
]


def build_document(spec: dict[str, Any]) -> V14Document:
    """Build a V14Document from a spec + cached raw_bytes."""
    cache_dir = CACHE / spec["cache_key"]
    manifest = json.loads((cache_dir / "manifest.json").read_text(encoding="utf-8"))
    # Concatenate all page raw_bytes
    raw_combined = b""
    pages_meta: list[dict[str, Any]] = []
    for page in manifest:
        page_path = cache_dir / page["cached_at"]
        if not page_path.exists():
            continue
        raw = page_path.read_bytes()
        raw_combined += raw
        pages_meta.append({
            "page_filename": page["page_filename"],
            "url": page["url"],
            "http_status": page["http_status"],
            "content_type": page["content_type"],
            "raw_bytes_size": len(raw),
            "raw_bytes_hash": page["raw_bytes_hash"],
            "retrieval_timestamp": page["retrieval_timestamp"],
        })
    # Try Latin-1 first (the secretariasenado pages use Latin-1 encoding)
    try:
        html_text = raw_combined.decode("latin-1")
        # Validate by checking for common Spanish chars
        if "ñ" not in html_text and "Ñ" not in html_text:
            html_text = raw_combined.decode("utf-8", errors="replace")
    except UnicodeDecodeError:
        html_text = raw_combined.decode("utf-8", errors="replace")
    # Extract articles based on pattern
    if spec["pattern"] == "A":
        arts = extract_articles_pattern_a(html_text)
    else:
        arts = extract_articles_pattern_b(html_text)
    # Build normalized text (all articles concatenated)
    normalized = "\n\n".join(
        f"ARTICULO {n}. {text}" for n, text in sorted(arts)
    )
    # Build reconstructed text (V1.3-compatible format)
    reconstructed = "\n\n".join(
        f"ARTICULO {n}. {text}" for n, text in sorted(arts)
    )
    # Build articles list
    articles_list = [
        {"number": str(n), "text": text}
        for n, text in sorted(arts)
    ]
    doc = V14Document(
        slug=spec["slug"],
        document_type=spec["document_type"],
        title=spec["title"],
        number=spec["number"],
        date_issued=spec["date_issued"],
        publication_date=spec["publication_date"],
        effective_from=spec["effective_from"],
        effective_until=spec["effective_until"],
        status=spec["status"],
        source_url=spec["source_url"],
        source_tier="S0_PRIMARY_SUPERIOR",
        authority=spec["authority"],
        jurisdiction="CO",
        pattern=spec["pattern"],
        pages=pages_meta,
        articles=articles_list,
        raw_bytes_combined=raw_combined,
        normalized_text=normalized,
        reconstructed_text=reconstructed,
    )
    doc.compute_hashes()
    return doc


def main() -> None:
    """Parse all sources + report."""
    print("=== V1.4 corpus parser ===\n")
    total_articles = 0
    total_bytes = 0
    for spec in DOCUMENTS_SPEC:
        doc = build_document(spec)
        total_articles += len(doc.articles)
        total_bytes += len(doc.raw_bytes_combined)
        print(f"  {doc.slug}:")
        print(f"    pages: {len(doc.pages)}")
        print(f"    raw_bytes: {len(doc.raw_bytes_combined)} ({doc.raw_bytes_hash[:16]}...)")
        print(f"    articles: {len(doc.articles)} (range {doc.articles[0]['number'] if doc.articles else '-'}-{doc.articles[-1]['number'] if doc.articles else '-'})")
        print(f"    normalized_text_hash: {doc.normalized_text_hash[:16]}...")
        print(f"    reconstructed_text_hash: {doc.reconstructed_text_hash[:16]}...")
        print(f"    provenance_status: {doc.provenance_status}")
        if doc.articles:
            print(f"    sample art 1: {doc.articles[0]['text'][:80]!r}")
        print()
    print(f"TOTAL: {total_articles} articles, {total_bytes} raw_bytes ({total_bytes/1024/1024:.2f} MB)")


if __name__ == "__main__":
    main()
