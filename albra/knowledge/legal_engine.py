"""
LEGAL KNOWLEDGE ENGINE - V1.0.

Orquesta el flujo jurídico soberano:

LegalQuery
  ↓
Query Understanding (LegalQueryClassifier)
  ↓
Retrieval Strategy (HybridRetriever)
  ↓
Knowledge Sources (RetrievalProvider)
  ↓
Evidence Candidates
  ↓
Verification + Conflict Detection (LegalVerifier)
  ↓
Abstention Policy (NO INVENTAR)
  ↓
EvidenceChain (con LegalProvenance)
  ↓
Legal Response (con citas)

NO inventa conocimiento jurídico.
NO acopla a Qdrant - usa RetrievalProvider abstraction.
España NO - Colombia SÍ.
"""
from __future__ import annotations

from typing import Any

from albra.knowledge.abstention import AbstentionPolicy
from albra.knowledge.citation import Citation, LegalResponse, LegalResponseBlock
from albra.knowledge.legal_provenance import build_provenance, record_evidence_with_provenance
from albra.knowledge.query_classifier import LegalQueryClassifier, QueryClassification
from albra.knowledge.retrieval import HybridRetriever, RetrievalQuery
from albra.knowledge.retrieval_providers import InMemoryRetrievalProvider
from albra.knowledge.temporal import TemporalQuery
from albra.knowledge.verification import LegalVerifier, VerificationResult
from albra.observability.logger import get_logger


class LegalKnowledgeEngine:
    """Engine soberano de conocimiento jurídico colombiano.

    Pipeline:
    LegalQuery → Query Understanding → Retrieval → Verification →
    Abstention → EvidenceChain → Legal Response
    """

    def __init__(
        self,
        *,
        retriever: HybridRetriever | None = None,
        evidence_chain: Any | None = None,
    ) -> None:
        self.log = get_logger("albra.legal_engine")
        self.retriever = retriever or HybridRetriever(
            provider=InMemoryRetrievalProvider()
        )
        self.evidence_chain = evidence_chain
        self.classifier = LegalQueryClassifier()
        self.verifier = LegalVerifier()
        self.abstention_policy = AbstentionPolicy()

    async def startup(self) -> None:
        await self.retriever.provider.startup()
        self.log.info("legal_engine.startup")

    async def shutdown(self) -> None:
        await self.retriever.provider.shutdown()
        self.log.info("legal_engine.shutdown")

    async def query(self, query_text: str, *, user_role: str = "anon") -> LegalResponse:
        """Ejecuta una consulta jurídica completa."""
        # 1. Query Understanding
        classification = self.classifier.classify(query_text)

        # 2. Si necesita aclaración → pedir
        if classification.needs_clarification:
            return LegalResponse(
                query=query_text,
                query_type=classification.query_type,
                abstention=True,
                abstention_reason=classification.clarification_question,
                needs_clarification=True,
                clarification_question=classification.clarification_question,
            )

        # 3. Retrieval Strategy
        retrieval_query = self._build_retrieval_query(query_text, classification)

        # 4. Retrieval
        result = await self.retriever.retrieve(retrieval_query)

        # 5. Verification + Conflict Detection
        verification = self.verifier.verify(result)

        # 6. Abstention policy
        abstention = self.abstention_policy.evaluate(
            result=result,
            verification=verification,
            query_classification=classification,
        )

        # 7. Build response
        if abstention.abstain:
            return LegalResponse(
                query=query_text,
                query_type=classification.query_type,
                abstention=True,
                abstention_reason=abstention.reason_text,
                needs_clarification=(abstention.reason_code == "ambiguous_query"),
                clarification_question=abstention.reason_text if abstention.reason_code == "ambiguous_query" else "",
                conflicts=[c.as_dict() for c in verification.conflicts if hasattr(c, "as_dict")] if verification.conflicts else [],
                needs_hitl=(abstention.fallback_action == "hitl"),
            )

        # 8. Build citations from evidence
        citations = self._build_citations(verification)

        # 9. Record evidence with legal provenance
        if self.evidence_chain and verification.primary_evidence_id:
            primary_candidate = next(
                (c for c in verification.candidates if c.source_id == verification.primary_evidence_id),
                None,
            )
            if primary_candidate:
                prov = build_provenance(
                    source_url=primary_candidate.provenance.get("source_url", ""),
                    source_tier=primary_candidate.source_tier.name,
                    authority=primary_candidate.authority,
                    document_id=primary_candidate.document_id,
                    document_type=primary_candidate.document_type,
                    citation_text=primary_candidate.citation,
                    content_hash=primary_candidate.provenance.get("content_hash", ""),
                    fragment_used=primary_candidate.snippet[:200],
                    version=str(primary_candidate.provenance.get("version", "")),
                    effective_at=str(primary_candidate.provenance.get("effective_from", "")),
                )
                await record_evidence_with_provenance(
                    self.evidence_chain,
                    kind="legal_evidence",
                    content=primary_candidate.snippet,
                    source=primary_candidate.provenance.get("source_url") or primary_candidate.authority,
                    legal_provenance=prov,
                    metadata={
                        "query": query_text,
                        "query_type": classification.query_type,
                        "is_current": primary_candidate.is_current,
                        "score": primary_candidate.score,
                    },
                )

        # 10. Build response blocks
        blocks = self._build_response_blocks(
            query_text, classification, verification, citations
        )

        return LegalResponse(
            query=query_text,
            query_type=classification.query_type,
            blocks=blocks,
            abstention=False,
            conflicts=[
                {"kind": c.kind, "description": c.description, "severity": c.severity}
                for c in verification.conflicts
            ] if verification.conflicts else [],
            needs_hitl=verification.needs_hitl,
        )

    def _build_retrieval_query(
        self,
        query_text: str,
        classification: QueryClassification,
    ) -> RetrievalQuery:
        """Construye la query de retrieval según el tipo de consulta."""
        # Default: hybrid
        query_type = "hybrid"
        if classification.query_type == "consulta_articulo_especifico":
            query_type = "exact"
        elif classification.query_type == "consulta_jurisprudencial":
            query_type = "semantic"

        # Temporal
        temporal = None
        if classification.temporal_hint == "current":
            temporal = TemporalQuery(query_type="current")
        elif classification.temporal_hint == "historical":
            temporal = TemporalQuery(query_type="historical")
        elif classification.temporal_hint.startswith("as_of:"):
            from datetime import date
            date_str = classification.temporal_hint[6:]
            try:
                as_of = date.fromisoformat(date_str)
                temporal = TemporalQuery(query_type="as_of", as_of=as_of)
            except ValueError:
                temporal = None

        return RetrievalQuery(
            query_text=query_text,
            query_type=query_type,
            norm_number=classification.detected_norm,
            article_number=classification.detected_article.replace("artículo ", "").replace("articulo ", "") if classification.detected_article else "",
            file_number=classification.detected_norm if classification.detected_norm and "/" in classification.detected_norm else "",
            document_type="",
            jurisdiction=classification.detected_jurisdiction,
            authority=classification.detected_authority,
            temporal=temporal,
            top_k=10,
            min_score=0.1,
        )

    def _build_citations(self, verification: VerificationResult) -> list[Citation]:
        """Construye citas formales de la evidencia verificada."""
        citations: list[Citation] = []
        for c in verification.candidates:
            citations.append(Citation(
                document_id=c.document_id,
                source_tier=c.source_tier.name,
                authority=c.authority,
                document_type=c.document_type,
                citation_text=c.citation,
                snippet=c.snippet[:300],
                effective_from=str(c.provenance.get("effective_from", "")) or None,
                effective_until=str(c.provenance.get("effective_until", "")) or None,
                status=c.provenance.get("status", "vigente"),
                source_url=c.provenance.get("source_url", ""),
                is_current=c.is_current,
            ))
        return citations

    def _build_response_blocks(
        self,
        query_text: str,
        classification: QueryClassification,
        verification: VerificationResult,
        citations: list[Citation],
    ) -> list[LegalResponseBlock]:
        """Construye bloques de respuesta tipados."""
        blocks: list[LegalResponseBlock] = []

        if not verification.candidates:
            # Should have been caught by abstention
            blocks.append(LegalResponseBlock(
                content_type="abstencion",
                text="No se encontró evidencia jurídica suficiente para esta afirmación.",
                confidence=0.0,
            ))
            return blocks

        # Primary evidence - literal text
        primary = verification.candidates[0]
        blocks.append(LegalResponseBlock(
            content_type="texto_normativo" if primary.document_type in ("ley", "decreto", "codigo", "estatuto", "constitucion") else "jurisprudencia" if primary.document_type in ("sentencia", "auto") else "doctrina",
            text=primary.snippet,
            citations=[c for c in citations if c.document_id == primary.document_id],
            confidence=min(1.0, primary.score + 0.3),
        ))

        # If conflicts, mention them
        if verification.conflicts:
            for conflict in verification.conflicts:
                blocks.append(LegalResponseBlock(
                    content_type="interpretacion",
                    text=f"Conflicto detectado: {conflict.description}",
                    confidence=0.5,
                    needs_review=True,
                ))

        return blocks

    def stats(self) -> dict[str, Any]:
        return {
            "retriever": self.retriever.provider.stats(),
            "engine": "LegalKnowledgeEngine V1.0",
            "jurisdiction": "CO",
            "abstention_threshold": self.abstention_policy.CONFIDENCE_THRESHOLD,
        }
