"""COLOMBIA LEGAL KNOWLEDGE & RESEARCH LAYER V1.0."""
from albra.knowledge.abstention import AbstentionDecision, AbstentionPolicy
from albra.knowledge.citation import (
    CONTENT_TYPES,
    Citation,
    LegalResponse,
    LegalResponseBlock,
)
from albra.knowledge.ingestion import IngestionResult, LegalIngestionPipeline
from albra.knowledge.legal_engine import LegalKnowledgeEngine
from albra.knowledge.legal_provenance import (
    LegalProvenance,
    build_provenance,
    record_evidence_with_provenance,
)

# Existing modules (kept for compatibility)
from albra.knowledge.loader import KnowledgeLoader
from albra.knowledge.query_classifier import (
    ALL_QUERY_TYPES,
    ArticleResolver,
    LegalQueryClassifier,
    QueryClassification,
)
from albra.knowledge.retrieval import (
    HybridRetriever,
    RetrievalProvider,
    RetrievalQuery,
    RetrievalResult,
)
from albra.knowledge.retrieval_providers import InMemoryRetrievalProvider
from albra.knowledge.schemas import (
    COLOMBIA_AUTHORITIES,
    DOCUMENT_TYPES,
    TIER_LABELS,
    VALIDITY_STATUS,
    Article,
    Doctrine,
    DocumentType,
    EvidenceCandidate,
    Jurisprudence,
    LegalDocument,
    Norm,
    SourceTier,
)
from albra.knowledge.sources import (
    COLOMBIA_OFFICIAL_SOURCES,
    OfficialSource,
    authority_for_source,
    can_back_compliance,
    compare_tier,
    get_source,
    list_sources_by_tier,
    tier_label,
)
from albra.knowledge.specialists import get_specialist, list_specialists
from albra.knowledge.temporal import (
    TemporalQuery,
    TemporalState,
    VersionHistory,
    is_currently_vigente,
    is_historical,
    is_vigente,
    normalize_status,
)
from albra.knowledge.triage import KnowledgeTriage
from albra.knowledge.verification import Conflict, LegalVerifier, VerificationResult
from albra.knowledge.versioner import KnowledgeVersioner
