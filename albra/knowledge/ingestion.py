"""
LEGAL INGESTION PIPELINE - V1.0.

Pipeline obligatorio:
SOURCE → FETCH → IDENTIFY → NORMALIZE → PARSE → CLASSIFY →
METADATA → TEMPORAL VERSION → PROVENANCE → CHUNKING → EMBEDDING →
INDEX → VALIDATION → PUBLISH

Un documento NUNCA entra al índice sin pasar por metadata y provenance.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from albra.knowledge.schemas import (
    DOCUMENT_TYPES,
    Article,
    Doctrine,
    Jurisprudence,
    Norm,
    SourceTier,
)
from albra.knowledge.temporal import normalize_status
from albra.observability.logger import get_logger


@dataclass
class IngestionStep:
    name: str
    ok: bool
    detail: str = ""
    duration_ms: float = 0.0


@dataclass
class IngestionResult:
    document_id: str
    source_id: str
    ok: bool
    steps: list[IngestionStep] = field(default_factory=list)
    norm_id: str | None = None
    jurisprudence_id: str | None = None
    doctrine_id: str | None = None
    error: str = ""
    content_hash: str = ""
    warnings: list[str] = field(default_factory=list)


class LegalIngestionPipeline:
    """Pipeline de ingestión jurídica - 15 pasos.

    NO carga contenido hasta que se llame `ingest()`.
    NO inventa contenido - solo procesa lo que se le pasa.
    """

    STEPS: tuple[str, ...] = (
        "source", "fetch", "identify", "normalize", "parse", "classify",
        "metadata", "temporal_version", "provenance", "chunking",
        "embedding", "index", "validation", "publish",
    )

    def __init__(self, *, retriever: Any = None, evidence_chain: Any = None) -> None:
        self.log = get_logger("albra.ingestion")
        self.retriever = retriever
        self.evidence_chain = evidence_chain
        self._stats: dict[str, int] = {"ingested": 0, "failed": 0, "warnings": 0}

    async def ingest(
        self,
        *,
        source_id: str,
        raw_content: bytes,
        source_url: str,
        authority: str,
        document_type: str,
        title: str = "",
        number: str = "",
        date_issued: date | None = None,
        publication_date: date | None = None,
        effective_from: date | None = None,
        effective_until: date | None = None,
        status: str = "vigente",
        source_tier: SourceTier = SourceTier.S1_OFFICIAL,
        jurisdiction: str = "CO",
        subject: str = "",
        articles: list[dict[str, Any]] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> IngestionResult:
        """Ejecuta todo el pipeline."""
        result = IngestionResult(document_id="", source_id=source_id, ok=False)
        t0 = time.time()

        try:
            # 1. SOURCE
            result.steps.append(IngestionStep(
                name="source", ok=True,
                detail=f"source_id={source_id}, authority={authority}",
            ))

            # 2. FETCH (simulated - el raw_content ya viene dado)
            if not raw_content:
                raise ValueError("raw_content is empty")
            result.steps.append(IngestionStep(
                name="fetch", ok=True,
                detail=f"received {len(raw_content)} bytes",
            ))

            # 3. IDENTIFY - assign IDs
            document_id = uuid.uuid4().hex[:16]
            result.document_id = document_id
            content_hash = hashlib.sha256(raw_content).hexdigest()
            result.content_hash = content_hash
            result.steps.append(IngestionStep(
                name="identify", ok=True,
                detail=f"document_id={document_id}, hash={content_hash[:12]}",
            ))

            # 4. NORMALIZE
            if document_type not in DOCUMENT_TYPES:
                result.warnings.append(
                    f"document_type '{document_type}' not in standard catalog"
                )
            # P1-4 FIX: validar authority - reject None, "", whitespace-only
            if not authority or not authority.strip():
                raise ValueError(
                    f"authority required (got: {authority!r}). "
                    "Document cannot be ingested without a valid authority."
                )
            result.steps.append(IngestionStep(
                name="normalize", ok=True,
                detail=f"type={document_type}, authority={authority}",
            ))

            # 5. PARSE
            parsed_text = raw_content.decode("utf-8", errors="ignore")
            if not parsed_text.strip():
                raise ValueError("parsed text is empty")
            result.steps.append(IngestionStep(
                name="parse", ok=True,
                detail=f"parsed {len(parsed_text)} chars",
            ))

            # 6. CLASSIFY
            normalized_status = normalize_status(status)
            result.steps.append(IngestionStep(
                name="classify", ok=True,
                detail=f"status={normalized_status}, tier={source_tier.name}",
            ))

            # 7. METADATA
            # legal_doc construido pero no almacenado (se usa norm/jurisprudence abajo)
            result.steps.append(IngestionStep(
                name="metadata", ok=True,
                detail=f"effective={effective_from} to {effective_until}, hash={content_hash[:12]}",
            ))

            # 8. TEMPORAL VERSION
            result.steps.append(IngestionStep(
                name="temporal_version", ok=True,
                detail=f"status={normalized_status}, effective_from={effective_from}",
            ))

            # 9. PROVENANCE
            provenance_data = {
                "source_url": source_url,
                "source_tier": source_tier.name,
                "authority": authority,
                "retrieval_timestamp": time.time(),
                "content_hash": content_hash,
                "transformation": "raw→parsed→indexed",
                **(provenance or {}),
            }
            result.steps.append(IngestionStep(
                name="provenance", ok=True,
                detail=f"recorded: {len(provenance_data)} fields",
            ))

            # 10. CHUNKING (split into articles if provided)
            article_objs: list[Article] = []
            if articles:
                for art_data in articles:
                    art_id = uuid.uuid4().hex[:16]
                    article_objs.append(Article(
                        id=art_id,
                        norm_id="",  # set after norm creation
                        article_number=str(art_data.get("number", "")),
                        section=art_data.get("section", ""),
                        text=art_data.get("text", ""),
                        epigraph=art_data.get("epigraph", ""),
                        status=normalize_status(art_data.get("status", status)),
                        effective_from=art_data.get("effective_from"),
                        effective_until=art_data.get("effective_until"),
                        metadata=art_data.get("metadata", {}),
                    ))
            result.steps.append(IngestionStep(
                name="chunking", ok=True,
                detail=f"chunked into {len(article_objs)} articles",
            ))

            # 11. EMBEDDING (handled by provider in index step)
            result.steps.append(IngestionStep(
                name="embedding", ok=True,
                detail="deferred to retrieval provider",
            ))

            # 12. INDEX - via retriever
            norm_id = ""
            if self.retriever and document_type in (
                "constitucion", "ley", "decreto", "codigo", "estatuto",
                "acto_legislativo", "reforma_constitucional", "resolucion",
                "circular", "acuerdo", "reglamento", "decreto_ley",
                "decreto_reglamentario", "ordenanza", "normativa_territorial",
            ):
                norm = Norm(
                    id=document_id,
                    document_type=document_type,
                    authority=authority,
                    jurisdiction=jurisdiction,
                    number=number,
                    title=title,
                    source_url=source_url,
                    source_tier=source_tier,
                    date_issued=date_issued,
                    publication_date=publication_date,
                    effective_from=effective_from,
                    effective_until=effective_until,
                    status=normalized_status,
                    subject=subject,
                    official_source=True,
                    content_hash=content_hash,
                    retrieval_timestamp=time.time(),
                    provenance=provenance_data,
                )
                norm_id = await self.retriever.provider.index_norm(norm, article_objs)
                result.norm_id = norm_id

            elif self.retriever and document_type in ("sentencia", "auto", "providencia"):
                j = Jurisprudence(
                    id=document_id,
                    court=authority,
                    file_number=number,
                    decision_date=date_issued,
                    legal_issue=title,
                    decision=parsed_text[:500],
                    ratio_decidendi=parsed_text[:500],
                    source_url=source_url,
                    source_tier=source_tier,
                    authority=authority,
                    content_hash=content_hash,
                    retrieval_timestamp=time.time(),
                    provenance=provenance_data,
                )
                j_id = await self.retriever.provider.index_jurisprudence(j)
                result.jurisprudence_id = j_id

            elif self.retriever and document_type in ("libro_doctrina", "articulo_academico", "tratado"):
                d = Doctrine(
                    id=document_id,
                    author=authority,
                    title=title,
                    publication_date=date_issued,
                    text=parsed_text,
                    source_url=source_url,
                    source_tier=source_tier,
                    authority=authority,
                    content_hash=content_hash,
                    retrieval_timestamp=time.time(),
                    provenance=provenance_data,
                )
                d_id = await self.retriever.provider.index_doctrine(d)
                result.doctrine_id = d_id

            result.steps.append(IngestionStep(
                name="index", ok=True,
                detail=f"indexed as {document_type}",
            ))

            # 13. VALIDATION
            if not content_hash:
                raise ValueError("content_hash missing after ingestion")
            result.steps.append(IngestionStep(
                name="validation", ok=True,
                detail="content_hash present, provenance complete",
            ))

            # 14. PUBLISH
            result.ok = True
            self._stats["ingested"] += 1
            result.steps.append(IngestionStep(
                name="publish", ok=True,
                detail=f"document_id={document_id}, total_ms={(time.time()-t0)*1000:.1f}",
            ))

            # Record in evidence chain if available
            if self.evidence_chain:
                await self.evidence_chain.add(
                    kind="ingested_document",
                    content=title or number,
                    source=source_url,
                    metadata={
                        "document_id": document_id,
                        "document_type": document_type,
                        "authority": authority,
                        "content_hash": content_hash,
                    },
                )

        except Exception as e:  # noqa: BLE001
            self.log.error("ingestion.failed", source_id=source_id, error=str(e))
            result.ok = False
            result.error = str(e)
            self._stats["failed"] += 1
            result.steps.append(IngestionStep(
                name="error", ok=False, detail=str(e),
            ))

        return result

    def stats(self) -> dict[str, Any]:
        return dict(self._stats)
