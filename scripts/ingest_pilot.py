"""
CORPUS PILOT INGESTION SCRIPT.

Ingesta el corpus piloto colombiano via LegalIngestionPipeline existente.
NO crea sistema paralelo. USA las abstracciones existentes.

Documentos ingeridos:
1. Constitución Política 1991 (10 artículos) - S0 CO
2. Ley 100 de 1993 (4 artículos) - S0 CO, modificada
3. Ley 80 de 1993 (3 artículos) - S0 CO, modificada
4. Ley 1480 de 2011 (2 artículos) - S0 CO, vigente
5. Sentencia C-251/2002 CC - S0 CO, erga_omnes+vinculante
6. Sentencia T-760/2008 CC - S0 CO, erga_omnes+vinculante
7. Sentencia Argentina AR-001/2020 - S1 AR (NO CO, aislamiento)
8. Doctrina Temis - S3 CO (jerarquia)
"""
from __future__ import annotations

import asyncio
from datetime import date

# V1.1: REAL corpus from verified official sources
from albra.knowledge.colombia.corpus_pilot.real_corpus_v11 import (
    ALL_DOCUMENTS as REAL_DOCUMENTS,
)
from albra.knowledge.ingestion import LegalIngestionPipeline
from albra.knowledge.retrieval import HybridRetriever
from albra.knowledge.retrieval_providers import InMemoryRetrievalProvider
from albra.knowledge.schemas import SourceTier
from albra.observability.logger import get_logger

log = get_logger("albra.corpus_pilot")

# All documents to ingest (V1.1: only REAL verified content)
ALL_DOCUMENTS = REAL_DOCUMENTS


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _parse_tier(s: str) -> SourceTier:
    return SourceTier[s]


async def ingest_pilot():
    """Ingest all pilot documents via existing pipeline."""
    # Setup
    provider = InMemoryRetrievalProvider()
    retriever = HybridRetriever(provider=provider)
    pipeline = LegalIngestionPipeline(retriever=retriever)

    await provider.startup()

    results = []
    ingested = 0
    rejected = 0

    for category, doc in ALL_DOCUMENTS:
        log.info("corpus_pilot.ingesting", category=category, source_id=doc["source_id"])

        result = await pipeline.ingest(
            source_id=doc["source_id"],
            raw_content=doc["raw_content"],
            source_url=doc["source_url"],
            authority=doc["authority"],
            document_type=doc["document_type"],
            title=doc.get("title", ""),
            number=doc.get("number", ""),
            date_issued=_parse_date(doc.get("date_issued")),
            publication_date=_parse_date(doc.get("publication_date")),
            effective_from=_parse_date(doc.get("effective_from")),
            effective_until=_parse_date(doc.get("effective_until")),
            status=doc.get("status", "vigente"),
            source_tier=_parse_tier(doc["source_tier"]),
            jurisdiction=doc.get("jurisdiction", "CO"),
            articles=doc.get("articles"),
            reach=doc.get("reach"),
            force=doc.get("force"),
        )

        results.append({
            "source_id": doc["source_id"],
            "category": category,
            "ok": result.ok,
            "error": result.error,
            "content_hash": result.content_hash,
            "warnings": result.warnings,
            "jurisdiction": doc.get("jurisdiction", "CO"),
            "source_tier": doc["source_tier"],
            "authority": doc["authority"],
            "document_type": doc["document_type"],
        })

        if result.ok:
            ingested += 1
        else:
            rejected += 1

    stats = provider.stats()
    log.info("corpus_pilot.complete", ingested=ingested, rejected=rejected, stats=stats)

    await provider.shutdown()

    return {
        "ingested": ingested,
        "rejected": rejected,
        "results": results,
        "retriever_stats": stats,
    }


def get_pilot_retriever():
    """Returns a retriever with the pilot corpus loaded (for tests)."""
    return asyncio.run(_build_pilot_retriever())


async def _build_pilot_retriever():
    provider = InMemoryRetrievalProvider()
    retriever = HybridRetriever(provider=provider)
    pipeline = LegalIngestionPipeline(retriever=retriever)

    await provider.startup()

    for category, doc in ALL_DOCUMENTS:
        await pipeline.ingest(
            source_id=doc["source_id"],
            raw_content=doc["raw_content"],
            source_url=doc["source_url"],
            authority=doc["authority"],
            document_type=doc["document_type"],
            title=doc.get("title", ""),
            number=doc.get("number", ""),
            date_issued=_parse_date(doc.get("date_issued")),
            publication_date=_parse_date(doc.get("publication_date")),
            effective_from=_parse_date(doc.get("effective_from")),
            effective_until=_parse_date(doc.get("effective_until")),
            status=doc.get("status", "vigente"),
            source_tier=_parse_tier(doc["source_tier"]),
            jurisdiction=doc.get("jurisdiction", "CO"),
            articles=doc.get("articles"),
            reach=doc.get("reach"),
            force=doc.get("force"),
        )

    return retriever


if __name__ == "__main__":
    result = asyncio.run(ingest_pilot())
    print("\n=== CORPUS PILOT INGESTION ===")
    print(f"Ingested: {result['ingested']}")
    print(f"Rejected: {result['rejected']}")
    print(f"Stats: {result['retriever_stats']}")
    for r in result["results"]:
        status = "OK" if r["ok"] else "REJECTED"
        print(f"  [{status}] {r['source_id']} ({r['jurisdiction']}, {r['source_tier']}) - {r['document_type']}")
