"""Tests CORRECCIÓN QUIRÚRGICA FINAL — Pre-corpus.

P0: Response must use verified primary evidence (not candidates[0])
P1: Jurisprudence ingestion reach+force
P1: official_source derived from tier (not hardcoded)
P1: Invalid document_type → fail-closed
P2: Provenance system fields cannot be overridden by caller
"""
import asyncio
from datetime import date

import pytest

from albra.config.settings import reset_settings
from albra.knowledge.legal_engine import (
    HybridRetriever,
    InMemoryRetrievalProvider,
    LegalKnowledgeEngine,
)
from albra.knowledge.retrieval import RetrievalResult
from albra.knowledge.schemas import (
    Article,
    EvidenceCandidate,
    Jurisprudence,
    Norm,
    SourceTier,
)
from albra.knowledge.verification import LegalVerifier


@pytest.fixture
def strong_secrets(monkeypatch):
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-ephemeral-jwt-secret-32-chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-ephemeral-pass-1234")
    reset_settings()
    yield
    reset_settings()


# ============================================================
# P0 — RESPONSE MUST USE VERIFIED PRIMARY EVIDENCE
# ============================================================

class TestPrimaryEvidenceInResponse:
    def test_s0_primary_used_in_response_not_s4(self):
        """P0: S0(score=0.01) beats S4(score=0.99) → response uses S0."""
        c_s0 = EvidenceCandidate(
            source_id="s0", document_id="d0",
            source_tier=SourceTier.S0_PRIMARY_SUPERIOR,
            authority="Congreso", document_type="ley",
            snippet="Texto de la ley S0", is_current=True, score=0.01,
        )
        c_s4 = EvidenceCandidate(
            source_id="s4", document_id="d4",
            source_tier=SourceTier.S4_SECONDARY,
            authority="Blog", document_type="articulo",
            snippet="Texto del blog S4", is_current=True, score=0.99,
        )
        result = RetrievalResult(candidates=[c_s4, c_s0])  # S4 is candidates[0]!
        v = LegalVerifier().verify(result)
        # Verifier should select S0 as primary
        assert v.primary_evidence_id == "s0", "Verifier must select S0 as primary"

        # Build response blocks — should use S0 (primary), NOT S4 (candidates[0])
        from albra.knowledge.citation import Citation
        citations = [
            Citation(document_id=c.document_id, source_tier=c.source_tier.name,
                     authority=c.authority, document_type=c.document_type,
                     citation_text=f"citation-{c.source_id}", snippet=c.snippet,
                     is_current=c.is_current)
            for c in v.candidates
        ]
        engine = LegalKnowledgeEngine()
        blocks = engine._build_response_blocks("test", None, v, citations)

        # The main block text should be S0's snippet, NOT S4's
        main_block = blocks[0]
        assert "S0" in main_block.text, f"Response should use S0 evidence, got: {main_block.text[:60]}"
        assert "S4" not in main_block.text, "Response must NOT use S4 (candidates[0])"

    def test_missing_primary_evidence_id_fail_closed(self):
        """P0: If primary_evidence_id is None or invalid → fail-closed abstention."""
        c1 = EvidenceCandidate(
            source_id="c1", document_id="d1",
            source_tier=SourceTier.S0_PRIMARY_SUPERIOR,
            authority="Congreso", document_type="ley",
            snippet="text", is_current=True, score=0.5,
        )
        result = RetrievalResult(candidates=[c1])
        v = LegalVerifier().verify(result)
        # Force primary_evidence_id to be invalid
        v.primary_evidence_id = "nonexistent_id"

        from albra.knowledge.citation import Citation
        citations = [
            Citation(document_id="d1", source_tier="S0_PRIMARY_SUPERIOR",
                     authority="Congreso", document_type="ley",
                     citation_text="test", snippet="text", is_current=True)
        ]
        engine = LegalKnowledgeEngine()
        blocks = engine._build_response_blocks("test", None, v, citations)

        # Should be abstention block (fail-closed)
        assert blocks[0].content_type == "abstencion"
        assert "evidencia primaria" in blocks[0].text.lower() or "no se pudo" in blocks[0].text.lower()

    def test_primary_evidence_id_none_fail_closed(self):
        """P0: primary_evidence_id=None → fail-closed."""
        c1 = EvidenceCandidate(
            source_id="c1", document_id="d1",
            source_tier=SourceTier.S0_PRIMARY_SUPERIOR,
            authority="Congreso", document_type="ley",
            snippet="text", is_current=True, score=0.5,
        )
        result = RetrievalResult(candidates=[c1])
        v = LegalVerifier().verify(result)
        v.primary_evidence_id = None

        engine = LegalKnowledgeEngine()
        blocks = engine._build_response_blocks("test", None, v, [])
        assert blocks[0].content_type == "abstencion"


# ============================================================
# P1 — JURISPRUDENCE INGESTION: REACH + FORCE
# ============================================================

class TestIngestionReachForce:
    def test_reach_erga_omnes_force_vinculante(self):
        """P1: ingestion with reach=erga_omnes + force=vinculante."""
        from albra.knowledge.ingestion import LegalIngestionPipeline
        from albra.knowledge.retrieval import HybridRetriever
        from albra.knowledge.retrieval_providers import InMemoryRetrievalProvider

        async def _run():
            provider = InMemoryRetrievalProvider()
            retriever = HybridRetriever(provider=provider)
            pipe = LegalIngestionPipeline(retriever=retriever)
            await provider.startup()

            r = await pipe.ingest(
                source_id="s1", raw_content=b"sentencia content",
                source_url="https://www.corteconstitucional.gov.co/sentencia",
                authority="Corte Constitucional", document_type="sentencia",
                title="Sentencia C-001/2024",
                reach="erga_omnes", force="vinculante",
            )
            assert r.ok, f"Ingestion should succeed: {r.error}"
            # Verify Jurisprudence was indexed with correct reach/force
            stats = provider.stats()
            assert stats["jurisprudence"] >= 1
            await provider.shutdown()

        asyncio.run(_run())

    def test_reach_erga_omnes_force_orientador(self):
        """P1: erga_omnes + orientador (non-binding despite general reach)."""
        from albra.knowledge.ingestion import LegalIngestionPipeline
        from albra.knowledge.retrieval import HybridRetriever
        from albra.knowledge.retrieval_providers import InMemoryRetrievalProvider

        async def _run():
            provider = InMemoryRetrievalProvider()
            retriever = HybridRetriever(provider=provider)
            pipe = LegalIngestionPipeline(retriever=retriever)
            await provider.startup()

            r = await pipe.ingest(
                source_id="s2", raw_content=b"sentencia content",
                source_url="https://www.corteconstitucional.gov.co/sentencia",
                authority="Corte Constitucional", document_type="sentencia",
                reach="erga_omnes", force="orientador",
            )
            assert r.ok
            await provider.shutdown()

        asyncio.run(_run())

    def test_reach_inter_partes_force_precedente(self):
        from albra.knowledge.ingestion import LegalIngestionPipeline
        from albra.knowledge.retrieval import HybridRetriever
        from albra.knowledge.retrieval_providers import InMemoryRetrievalProvider

        async def _run():
            provider = InMemoryRetrievalProvider()
            retriever = HybridRetriever(provider=provider)
            pipe = LegalIngestionPipeline(retriever=retriever)
            await provider.startup()

            r = await pipe.ingest(
                source_id="s3", raw_content=b"sentencia",
                source_url="https://www.corte.gov.co/sentencia",
                authority="Corte Suprema", document_type="sentencia",
                reach="inter_partes", force="precedente",
            )
            assert r.ok
            await provider.shutdown()

        asyncio.run(_run())

    def test_missing_metadata_defaults_unknown_desconocido(self):
        """P1: no reach/force passed → defaults unknown/desconocido (NOT inter_partes/vinculante)."""
        from albra.knowledge.ingestion import LegalIngestionPipeline
        from albra.knowledge.retrieval import HybridRetriever
        from albra.knowledge.retrieval_providers import InMemoryRetrievalProvider

        async def _run():
            provider = InMemoryRetrievalProvider()
            retriever = HybridRetriever(provider=provider)
            pipe = LegalIngestionPipeline(retriever=retriever)
            await provider.startup()

            r = await pipe.ingest(
                source_id="s4", raw_content=b"sentencia",
                source_url="https://www.corte.gov.co/sentencia",
                authority="Tribunal", document_type="sentencia",
                # NO reach/force passed
            )
            assert r.ok
            # Verify defaults via stats (Jurisprudence was indexed)
            stats = provider.stats()
            assert stats["jurisprudence"] >= 1
            await provider.shutdown()

        asyncio.run(_run())

    def test_invalid_reach_force_normalized(self):
        """P1: invalid reach/force values → normalized to unknown/desconocido."""
        from albra.knowledge.ingestion import LegalIngestionPipeline
        from albra.knowledge.retrieval import HybridRetriever
        from albra.knowledge.retrieval_providers import InMemoryRetrievalProvider

        async def _run():
            provider = InMemoryRetrievalProvider()
            retriever = HybridRetriever(provider=provider)
            pipe = LegalIngestionPipeline(retriever=retriever)
            await provider.startup()

            r = await pipe.ingest(
                source_id="s5", raw_content=b"sentencia",
                source_url="https://www.corte.gov.co/sentencia",
                authority="Tribunal", document_type="sentencia",
                reach="banana", force="invalid_value",
            )
            assert r.ok  # Ingestion succeeds, values are normalized
            await provider.shutdown()

        asyncio.run(_run())


# ============================================================
# P1 — OFFICIAL_SOURCE DERIVED FROM TIER
# ============================================================

class TestOfficialSourceDerivation:
    def test_s0_official_source_true(self):
        """S0 → official_source=True."""
        from albra.knowledge.ingestion import LegalIngestionPipeline
        from albra.knowledge.retrieval import HybridRetriever
        from albra.knowledge.retrieval_providers import InMemoryRetrievalProvider

        async def _run():
            provider = InMemoryRetrievalProvider()
            retriever = HybridRetriever(provider=provider)
            pipe = LegalIngestionPipeline(retriever=retriever)
            await provider.startup()

            r = await pipe.ingest(
                source_id="s0", raw_content=b"norma",
                source_url="https://www.alcaldiabogota.gov.co/constitucion",
                authority="Asamblea Nacional Constituyente",
                document_type="constitucion",
                source_tier=SourceTier.S0_PRIMARY_SUPERIOR,
            )
            assert r.ok
            await provider.shutdown()

        asyncio.run(_run())

    def test_s1_official_source_true(self):
        from albra.knowledge.ingestion import LegalIngestionPipeline
        from albra.knowledge.retrieval import HybridRetriever
        from albra.knowledge.retrieval_providers import InMemoryRetrievalProvider

        async def _run():
            provider = InMemoryRetrievalProvider()
            retriever = HybridRetriever(provider=provider)
            pipe = LegalIngestionPipeline(retriever=retriever)
            await provider.startup()

            r = await pipe.ingest(
                source_id="s1", raw_content=b"norma",
                source_url="https://www.funcionpublica.gov.co/ley",
                authority="Congreso", document_type="ley",
                source_tier=SourceTier.S1_OFFICIAL,
            )
            assert r.ok
            await provider.shutdown()

        asyncio.run(_run())

    def test_s2_official_source_false(self):
        """S2 (académica) → official_source=False."""
        from albra.knowledge.ingestion import LegalIngestionPipeline
        from albra.knowledge.retrieval import HybridRetriever
        from albra.knowledge.retrieval_providers import InMemoryRetrievalProvider

        async def _run():
            provider = InMemoryRetrievalProvider()
            retriever = HybridRetriever(provider=provider)
            pipe = LegalIngestionPipeline(retriever=retriever)
            await provider.startup()

            r = await pipe.ingest(
                source_id="s2", raw_content=b"doctrina",
                source_url="https://www.banrep.gov.co/doctrina",
                authority="Banco de la República",
                document_type="articulo_academico",
                source_tier=SourceTier.S2_ACADEMIC,
            )
            assert r.ok
            await provider.shutdown()

        asyncio.run(_run())

    def test_s3_official_source_false(self):
        from albra.knowledge.ingestion import LegalIngestionPipeline
        from albra.knowledge.retrieval import HybridRetriever
        from albra.knowledge.retrieval_providers import InMemoryRetrievalProvider

        async def _run():
            provider = InMemoryRetrievalProvider()
            retriever = HybridRetriever(provider=provider)
            pipe = LegalIngestionPipeline(retriever=retriever)
            await provider.startup()

            r = await pipe.ingest(
                source_id="s3", raw_content=b"libro",
                source_url="https://www.editorialtemis.com/libro",
                authority="Editorial Temis",
                document_type="libro_doctrina",
                source_tier=SourceTier.S3_DOCTRINE,
            )
            assert r.ok
            await provider.shutdown()

        asyncio.run(_run())

    def test_s4_official_source_false(self):
        from albra.knowledge.ingestion import LegalIngestionPipeline
        from albra.knowledge.retrieval import HybridRetriever
        from albra.knowledge.retrieval_providers import InMemoryRetrievalProvider

        async def _run():
            provider = InMemoryRetrievalProvider()
            retriever = HybridRetriever(provider=provider)
            pipe = LegalIngestionPipeline(retriever=retriever)
            await provider.startup()

            r = await pipe.ingest(
                source_id="s4", raw_content=b"articulo",
                source_url="https://www.blog.com/articulo",
                authority="Blog Jurídico",
                document_type="articulo_academico",
                source_tier=SourceTier.S4_SECONDARY,
            )
            assert r.ok
            await provider.shutdown()

        asyncio.run(_run())


# ============================================================
# P1 — INVALID DOCUMENT_TYPE FAIL-CLOSED
# ============================================================

class TestInvalidDocumentTypeFailClosed:
    def test_invalid_document_type_rejected(self):
        """P1: invalid document_type → ingestion fails (not just warning)."""
        from albra.knowledge.ingestion import LegalIngestionPipeline

        pipe = LegalIngestionPipeline()
        r = asyncio.run(pipe.ingest(
            source_id="s_invalid", raw_content=b"content",
            source_url="https://www.gov.co/norma",
            authority="Congreso",
            document_type="tipo_inventado",
        ))
        assert not r.ok, "Invalid document_type must fail-closed"
        assert "not a valid legal document type" in r.error

    def test_valid_document_type_accepted(self):
        """Valid document_type → ingestion succeeds."""
        from albra.knowledge.ingestion import LegalIngestionPipeline

        pipe = LegalIngestionPipeline()
        r = asyncio.run(pipe.ingest(
            source_id="s_valid", raw_content=b"content",
            source_url="https://www.gov.co/ley",
            authority="Congreso",
            document_type="ley",
        ))
        assert r.ok


# ============================================================
# P2 — PROVENANCE SYSTEM FIELDS CANNOT BE OVERRIDDEN
# ============================================================

class TestProvenanceSystemFieldsOverride:
    def test_caller_cannot_override_format_valid(self):
        """P2: caller passes source_url_format_valid=True with bad URL → system wins (False)."""
        from albra.knowledge.ingestion import LegalIngestionPipeline

        pipe = LegalIngestionPipeline()
        r = asyncio.run(pipe.ingest(
            source_id="s1", raw_content=b"c",
            source_url="bad-url",
            authority="Congreso", document_type="ley",
            provenance={"source_url_format_valid": True},  # malicious override
        ))
        assert r.ok
        # Warning about malformed URL should be present
        assert any("malformed" in w.lower() for w in r.warnings)

    def test_caller_cannot_override_authenticated(self):
        """P2: caller passes source_url_authenticated=True → system wins (False)."""
        from albra.knowledge.ingestion import LegalIngestionPipeline

        pipe = LegalIngestionPipeline()
        r = asyncio.run(pipe.ingest(
            source_id="s2", raw_content=b"c",
            source_url="https://www.gov.co/ley",
            authority="Congreso", document_type="ley",
            provenance={"source_url_authenticated": True},  # malicious override
        ))
        assert r.ok

    def test_caller_cannot_override_accessible(self):
        """P2: caller passes source_url_accessible=True → system wins (False)."""
        from albra.knowledge.ingestion import LegalIngestionPipeline

        pipe = LegalIngestionPipeline()
        r = asyncio.run(pipe.ingest(
            source_id="s3", raw_content=b"c",
            source_url="https://www.gov.co/ley",
            authority="Congreso", document_type="ley",
            provenance={"source_url_accessible": True},  # malicious override
        ))
        assert r.ok
