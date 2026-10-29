"""V1.4 corpus ingestion — fetch + cache raw_bytes from official sources.

Sources:
  - Constitución 1991 (13 paginated pages, arts. 1-380)
  - Ley 1564/2012 CGP (paginated)
  - Ley 640/2001 conciliación (paginated)
  - Ley 906/2004 CPP (paginated)
  - Código Sustantivo del Trabajo (paginated)

Caches raw_bytes to disk so the V1.4 corpus file can embed hashes
without re-fetching. Each cached file preserves:
  - raw_bytes (the exact bytes returned by the server)
  - http_status
  - content_type
  - retrieval_timestamp
  - source_url
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = "http://www.secretariasenado.gov.co/senado/basedoc"
CACHE_DIR = Path(__file__).parent / "raw_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Sources to fetch: (cache_key, base_slug, expected_first_page)
SOURCES = [
    ("constitucion_1991", "constitucion_politica_1991"),
    ("ley_1564_2012", "ley_1564_2012"),
    ("ley_0640_2001", "ley_0640_2001"),
    ("ley_0906_2004", "ley_0906_2004"),
    ("codigo_sustantivo_trabajo", "codigo_sustantivo_trabajo"),
]


def fetch_page(url: str, timeout: float = 30.0) -> dict:
    """Fetch a single URL and return its metadata + raw_bytes."""
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"}
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return {
                "url": url,
                "http_status": r.status,
                "content_type": r.headers.get("Content-Type", ""),
                "raw_bytes": raw,
                "raw_bytes_hash": hashlib.sha256(raw).hexdigest(),
                "retrieval_timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "latency_ms": round((time.monotonic() - t0) * 1000, 2),
            }
    except urllib.error.HTTPError as e:
        return {
            "url": url, "http_status": e.code, "error": str(e),
            "raw_bytes": b"", "raw_bytes_hash": "",
        }
    except urllib.error.URLError as e:
        return {
            "url": url, "http_status": 0, "error": str(e.reason),
            "raw_bytes": b"", "raw_bytes_hash": "",
        }


def fetch_paginated(cache_key: str, slug: str) -> dict:
    """Fetch all pages of a paginated source.

    The main page is .htm (no suffix), subsequent pages are _prNNN.html.
    Returns a dict with: cache_key, slug, pages: list[dict].
    """
    pages: list[dict] = []
    # First page: .htm (without _prNNN)
    first_url = f"{BASE_URL}/{slug}.htm"
    p = fetch_page(first_url)
    pages.append({**p, "page_index": 0, "page_filename": f"{slug}.htm"})
    # Discover pagination links
    raw_text = p["raw_bytes"].decode("utf-8", errors="replace")
    next_links = sorted(set(re.findall(rf'href="({re.escape(slug)}_pr\d+\.html)"', raw_text)))
    print(f"  [{cache_key}] page 0: {len(p['raw_bytes'])} bytes | next={next_links}")
    # Fetch each subsequent page
    fetched = set()
    while next_links:
        link = next_links[0]
        if link in fetched:
            next_links = next_links[1:]
            continue
        fetched.add(link)
        url = f"{BASE_URL}/{link}"
        p2 = fetch_page(url)
        if p2["raw_bytes"]:
            text = p2["raw_bytes"].decode("utf-8", errors="replace")
            new_links = sorted(set(re.findall(rf'href="({re.escape(slug)}_pr\d+\.html)"', text)))
            pages.append({**p2, "page_index": len(pages), "page_filename": link})
            print(f"  [{cache_key}] page {len(pages)-1}: {len(p2['raw_bytes'])} bytes | next={new_links[:3]}")
            # Add new links not yet fetched
            for nl in new_links:
                if nl not in fetched and nl not in next_links:
                    next_links.append(nl)
        next_links = next_links[1:]
        time.sleep(0.5)  # be polite
    return {"cache_key": cache_key, "slug": slug, "pages": pages}


def cache_to_disk(source_data: dict) -> None:
    """Persist raw_bytes + metadata per page to disk."""
    cache_dir = CACHE_DIR / source_data["cache_key"]
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for page in source_data["pages"]:
        if not page["raw_bytes"]:
            continue
        page_path = cache_dir / page["page_filename"].replace("/", "_")
        page_path.write_bytes(page["raw_bytes"])
        manifest.append({
            "page_filename": page["page_filename"],
            "page_index": page["page_index"],
            "url": page["url"],
            "http_status": page["http_status"],
            "content_type": page["content_type"],
            "raw_bytes_size": len(page["raw_bytes"]),
            "raw_bytes_hash": page["raw_bytes_hash"],
            "retrieval_timestamp": page["retrieval_timestamp"],
            "latency_ms": page["latency_ms"],
            "cached_at": page_path.name,
        })
    (cache_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  [{source_data['cache_key']}] cached {len(manifest)} pages to {cache_dir}")


def main() -> None:
    print("=== V1.4 corpus ingestion ===")
    for cache_key, slug in SOURCES:
        print(f"\n--- {cache_key} ({slug}) ---")
        source_data = fetch_paginated(cache_key, slug)
        cache_to_disk(source_data)
    print("\n=== Done. Cache at:", CACHE_DIR)


if __name__ == "__main__":
    main()
