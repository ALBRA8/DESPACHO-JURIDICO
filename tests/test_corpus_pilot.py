"""CORPUS PILOT TEST SUITE V1.0 — Fases 5-13.

Tests sobre el corpus piloto real (Constitución 1991, Ley 100, Ley 80,
Ley 1480, Sentencias C-251/2002 y T-760/2008, sentencia AR, doctrina S3).

Cobertura:
- FASE 5: Temporalidad (vigente, histórica, as_of)
- FASE 6: Retrieval (exact, semantic, temporal, jurisdiction)
- FASE 7: Jurisprudencia (CO vs AR, reach/force)
- FASE 8: Response builder (primary_evidence_id)
- FASE 9: Provenance
- FASE 10: Abstention
- FASE 11: E2E
- FASE 12: Source/document/jurisprudence tests
- FASE 13: Adversarial tests
"""
import asyncio
from datetime import date

import pytest

from albra.config.settings import reset_settings
from albra.knowledge.schemas import SourceTier
from scripts.ingest_pilot import get_pilot_retriever


@pytest.fixture
def strong_secrets(monkeypatch):
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-ephemeral-jwt-secret-32-chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-ephemeral-pass-1234")
    reset_settings()
    yield
    reset_settings()


@pytest.fixture
def corpus_retriever():
    """Retriever with pilot corpus loaded."""
    return get_pilot_retriever()


# ============================================================
# FASE 5 — TEMPORALIDAD
# ============================================================

class TestTemporalidad:
    def test_norma_vigente_recuperable(self, corpus_retriever):
        """Ley 100 de 1993 vigente → recuperable."""
        from albra.knowledge.retrieval import RetrievalQuery
        async def _run():
            q = RetrievalQuery(query_type="exact", norm_number="Ley 100", jurisdiction="CO")
            result = await corpus_retriever.retrieve(q)
            assert result.total_found >= 1
            assert all(c.is_current for c in result.candidates)
        asyncio.run(_run())

    def test_norma_modificada_recuperable(self, corpus_retriever):
        """Ley 100 de 1993 modificada → recuperable, is_current=True (modificada ≠ derogada)."""
        from albra.knowledge.retrieval import RetrievalQuery
        async def _run():
            q = RetrievalQuery(query_type="exact", norm_number="Ley 100", jurisdiction="CO")
            result = await corpus_retriever.retrieve(q)
            assert result.total_found >= 1
        asyncio.run(_run())

    def test_consulta_as_of_anterior(self, corpus_retriever):
        """Consulta as_of=1992 → Constitución vigente."""
        from albra.knowledge.retrieval import RetrievalQuery
        from albra.knowledge.temporal import TemporalQuery
        async def _run():
            q = RetrievalQuery(
                query_text="estado social de derecho",
                query_type="semantic",
                jurisdiction="CO",
                temporal=TemporalQuery(query_type="as_of", as_of=date(1992, 1, 1)),
                top_k=5, min_score=0.0,
            )
            result = await corpus_retriever.retrieve(q)
            assert result.total_found >= 1, "Constitución was vigente in 1992"
        asyncio.run(_run())


# ============================================================
# FASE 6 — RETRIEVAL
# ============================================================

class TestRetrieval:
    def test_exact_article_retrieval(self, corpus_retriever):
        """Búsqueda exacta: artículo 25 de la Constitución."""
        from albra.knowledge.retrieval import RetrievalQuery
        async def _run():
            q = RetrievalQuery(
                query_type="exact",
                norm_number="Constitución Política de 1991",
                article_number="25",
                jurisdiction="CO",
            )
            result = await corpus_retriever.retrieve(q)
            assert result.total_found >= 1
            assert "25" in result.candidates[0].citation
        asyncio.run(_run())

    def test_semantic_retrieval(self, corpus_retriever):
        """Búsqueda semántica: 'trabajo derecho obligación'."""
        from albra.knowledge.retrieval import RetrievalQuery
        async def _run():
            q = RetrievalQuery(
                query_text="trabajo derecho obligacion social",
                query_type="semantic",
                jurisdiction="CO",
                top_k=5, min_score=0.0,
            )
            result = await corpus_retriever.retrieve(q)
            assert result.total_found >= 1
        asyncio.run(_run())

    def test_hybrid_retrieval(self, corpus_retriever):
        from albra.knowledge.retrieval import RetrievalQuery
        async def _run():
            q = RetrievalQuery(
                query_text="seguridad social salud",
                query_type="hybrid",
                jurisdiction="CO",
                top_k=10, min_score=0.0,
            )
            result = await corpus_retriever.retrieve(q)
            assert result.total_found >= 1
        asyncio.run(_run())

    def test_jurisdiction_isolation_co(self, corpus_retriever):
        """Query CO → NO recupera sentencia AR."""
        from albra.knowledge.retrieval import RetrievalQuery
        async def _run():
            q = RetrievalQuery(
                query_text="salud derecho tutela",
                query_type="semantic",
                jurisdiction="CO",
                top_k=20, min_score=0.0,
            )
            result = await corpus_retriever.retrieve(q)
            # Ningún candidato debe ser AR
            for c in result.candidates:
                assert c.provenance.get("jurisdiction") != "AR", \
                    "Argentine sentencia must NOT appear in CO query"
        asyncio.run(_run())

    def test_s0_beats_s3_in_ranking(self, corpus_retriever):
        """S0 (Constitución) debe aparecer antes que S3 (doctrina)."""
        from albra.knowledge.retrieval import RetrievalQuery
        async def _run():
            q = RetrievalQuery(
                query_text="estado social de derecho dignidad humana",
                query_type="semantic",
                jurisdiction="CO",
                top_k=20, min_score=0.0,
            )
            result = await corpus_retriever.retrieve(q)
            if result.total_found >= 2:
                tiers = [c.source_tier for c in result.candidates]
                # First S0 should appear before first S3
                first_s0 = next((i for i, t in enumerate(tiers) if t == SourceTier.S0_PRIMARY_SUPERIOR), None)
                first_s3 = next((i for i, t in enumerate(tiers) if t == SourceTier.S3_DOCTRINE), None)
                if first_s0 is not None and first_s3 is not None:
                    assert first_s0 < first_s3, "S0 must rank before S3"
        asyncio.run(_run())


# ============================================================
# FASE 7 — JURISPRUDENCIA
# ============================================================

class TestJurisprudencia:
    def test_sentencia_co_recuperable(self, corpus_retriever):
        """V1.1: No jurisprudence in corpus (sentencias rejected - content not fetchable)."""
        pytest.skip("V1.1: No jurisprudence in corpus (sentencias rejected - content not fetchable from corteconstitucional.gov.co)")
        from albra.knowledge.retrieval import RetrievalQuery
        async def _run():
            q = RetrievalQuery(
                query_type="exact",
                file_number="C-251/2002",
                jurisdiction="CO",
            )
            result = await corpus_retriever.retrieve(q)
            assert result.total_found >= 1
            c = result.candidates[0]
            assert c.authority == "Corte Constitucional"
            assert c.provenance.get("reach") == "erga_omnes"
            assert c.provenance.get("force") == "vinculante"
        asyncio.run(_run())

    def test_sentencia_ar_excluida_en_co(self, corpus_retriever):
        """V1.1: No AR documents (synthetic eliminated)."""
        pytest.skip("V1.1: No AR documents in corpus (synthetic was eliminated)")
        from albra.knowledge.retrieval import RetrievalQuery
        async def _run():
            q = RetrievalQuery(
                query_text="salud tutela argentina",
                query_type="semantic",
                jurisdiction="CO",
                top_k=20, min_score=0.0,
            )
            result = await corpus_retriever.retrieve(q)
            for c in result.candidates:
                assert "AR" not in (c.provenance.get("jurisdiction") or ""), \
                    "Argentine sentencia must NOT appear"
        asyncio.run(_run())

    def test_reach_force_preserved(self, corpus_retriever):
        """V1.1: No jurisprudence with reach/force in corpus."""
        pytest.skip("V1.1: No jurisprudence in corpus (sentencias rejected)")
        from albra.knowledge.retrieval import RetrievalQuery
        async def _run():
            q = RetrievalQuery(
                query_type="exact",
                file_number="T-760/2008",
                jurisdiction="CO",
            )
            result = await corpus_retriever.retrieve(q)
            assert result.total_found >= 1
            c = result.candidates[0]
            assert c.provenance.get("reach") == "erga_omnes"
            assert c.provenance.get("force") == "vinculante"
        asyncio.run(_run())


# ============================================================
# FASE 8 — RESPONSE BUILDER
# ============================================================

class TestResponseBuilder:
    def test_response_uses_primary_evidence(self, corpus_retriever):
        """Response usa primary_evidence_id, no candidates[0]."""
        from albra.knowledge.citation import Citation
        from albra.knowledge.legal_engine import LegalKnowledgeEngine
        from albra.knowledge.retrieval import RetrievalQuery
        from albra.knowledge.verification import LegalVerifier

        async def _run():
            q = RetrievalQuery(
                query_text="trabajo derecho obligacion social estado",
                query_type="semantic",
                jurisdiction="CO",
                top_k=20, min_score=0.0,
            )
            result = await corpus_retriever.retrieve(q)
            v = LegalVerifier().verify(result)
            assert v.primary_evidence_id is not None

            citations = [
                Citation(
                    document_id=c.document_id,
                    source_tier=c.source_tier.name,
                    authority=c.authority,
                    document_type=c.document_type,
                    citation_text=c.citation,
                    snippet=c.snippet,
                    is_current=c.is_current,
                )
                for c in v.candidates
            ]

            engine = LegalKnowledgeEngine()
            blocks = engine._build_response_blocks("test", None, v, citations)

            # First block should NOT be abstencion (we have evidence)
            assert blocks[0].content_type != "abstencion"
            # The citation in the block should correspond to primary_evidence_id
            primary_c = next(c for c in v.candidates if c.source_id == v.primary_evidence_id)
            assert any(c.document_id == primary_c.document_id for c in blocks[0].citations)

        asyncio.run(_run())

    def test_no_primary_fail_closed(self, corpus_retriever):
        """Si no hay primary_evidence_id → abstención."""
        from albra.knowledge.legal_engine import LegalKnowledgeEngine
        from albra.knowledge.retrieval import RetrievalQuery
        from albra.knowledge.verification import LegalVerifier

        async def _run():
            q = RetrievalQuery(
                query_text="xyznonexistent",
                query_type="semantic",
                jurisdiction="CO",
                top_k=5, min_score=0.0,
            )
            result = await corpus_retriever.retrieve(q)
            v = LegalVerifier().verify(result)

            engine = LegalKnowledgeEngine()
            blocks = engine._build_response_blocks("test", None, v, [])

            if result.total_found == 0:
                assert blocks[0].content_type == "abstencion"
            elif v.primary_evidence_id is None:
                assert blocks[0].content_type == "abstencion"

        asyncio.run(_run())


# ============================================================
# FASE 10 — ABSTENTION
# ============================================================

class TestAbstention:
    def test_norma_inexistente_abstencion(self, corpus_retriever):
        """Norma inexistente → abstención."""
        from albra.knowledge.retrieval import RetrievalQuery
        async def _run():
            q = RetrievalQuery(query_type="exact", norm_number="Ley 99999", jurisdiction="CO")
            result = await corpus_retriever.retrieve(q)
            assert result.total_found == 0
            assert result.abstention is True
        asyncio.run(_run())

    def test_articulo_inexistente_abstencion(self, corpus_retriever):
        from albra.knowledge.retrieval import RetrievalQuery
        async def _run():
            q = RetrievalQuery(
                query_type="exact",
                norm_number="Constitución Política de 1991",
                article_number="999",
                jurisdiction="CO",
            )
            result = await corpus_retriever.retrieve(q)
            assert result.total_found == 0
        asyncio.run(_run())


# ============================================================
# FASE 11 — END TO END
# ============================================================

class TestE2E:
    def test_e2e_legal_query_through_runtime(self, strong_secrets):
        """E2E: usuario → Runtime → LegalKnowledgeEngine → respuesta."""
        from albra.identity.agent import get_agent

        # Build pilot retriever BEFORE entering async context
        pilot_retriever = get_pilot_retriever()

        async def _run():
            agent = get_agent()
            await agent.boot()

            # Wire the pilot corpus into the agent's legal_engine
            agent.organs["legal_engine"].retriever = pilot_retriever

            r = await agent.process(
                "¿Qué dice el artículo 25 de la Constitución Política de 1991?",
                user="test", user_role="admin",
            )

            assert r.get("routed_to") == "legal_engine"
            assert r["authorized"] is True
            # Should NOT abstain (we have corpus)
            assert not r.get("abstention", True), \
                f"Should find evidence, got: {r['reply'][:100]}"

            await agent.shutdown()

        asyncio.run(_run())

    def test_e2e_non_legal_not_routed(self, strong_secrets):
        """Non-legal query does NOT route to legal_engine."""
        from albra.identity.agent import get_agent

        async def _run():
            agent = get_agent()
            await agent.boot()
            r = await agent.process("hola qué más", user="test", user_role="anon")
            assert r.get("routed_to") != "legal_engine"
            await agent.shutdown()

        asyncio.run(_run())

    def test_e2e_abstention_on_unknown_article(self, strong_secrets):
        """Unknown article → abstención (not invention)."""
        from albra.identity.agent import get_agent

        # Build pilot retriever BEFORE entering async context
        pilot_retriever = get_pilot_retriever()

        async def _run():
            agent = get_agent()
            await agent.boot()
            agent.organs["legal_engine"].retriever = pilot_retriever

            r = await agent.process(
                "¿Qué dice el artículo 999 de la Constitución Política de 1991?",
                user="test", user_role="admin",
            )
            assert r.get("routed_to") == "legal_engine"
            # Should abstain (article 999 doesn't exist)
            reply_lower = r["reply"].lower()
            assert (
                "evidencia" in reply_lower
                or "no se encontró" in reply_lower
                or "abstención" in reply_lower
            ), f"Should abstain, got: {reply_lower[:100]}"

            await agent.shutdown()

        asyncio.run(_run())


# ============================================================
# FASE 12 — SOURCE / DOCUMENT / DEDUP TESTS
# ============================================================

class TestSourceAndDocument:
    def test_corpus_stats(self, corpus_retriever):
        """V1.1: 3 normas, 12 artículos reales, 0 jurisprudencia, 0 doctrina."""
        stats = corpus_retriever.provider.stats()
        assert stats["norms"] == 3
        assert stats["articles"] == 12
        assert stats["jurisprudence"] == 0  # V1.1: sentencias rejected (content not fetchable)
        assert stats["doctrine"] == 0  # V1.1: doctrine rejected (was synthetic)

    def test_dedup_preserves_multiple_articles(self, corpus_retriever):
        """V1.1: Constitución tiene 6 artículos reales → todos recuperables."""
        from albra.knowledge.retrieval import RetrievalQuery
        async def _run():
            q = RetrievalQuery(
                query_type="exact",
                norm_number="Constitución Política de 1991",
                jurisdiction="CO",
            )
            result = await corpus_retriever.retrieve(q)
            assert result.total_found == 6, f"Expected 6 articles, got {result.total_found}"
        asyncio.run(_run())

    def test_all_jurisdictions_present(self, corpus_retriever):
        """V1.1: Only CO present (AR was synthetic → eliminated)."""
        from albra.knowledge.retrieval import RetrievalQuery
        async def _run():
            # CO
            q_co = RetrievalQuery(query_text="seguridad social", query_type="semantic", jurisdiction="CO", top_k=20, min_score=0.0)
            r_co = await corpus_retriever.retrieve(q_co)
            assert r_co.total_found >= 1, "Should find CO norms"
            # AR should return 0 (no AR documents in V1.1)
            q_ar = RetrievalQuery(query_text="salud", query_type="semantic", jurisdiction="AR", top_k=20, min_score=0.0)
            r_ar = await corpus_retriever.retrieve(q_ar)
            assert r_ar.total_found == 0, "V1.1 has no AR documents (synthetic was eliminated)"
        asyncio.run(_run())


# ============================================================
# FASE 13 — ADVERSARIAL TESTS
# ============================================================

class TestAdversarial:
    def test_s4_cannot_displace_s0(self, corpus_retriever):
        """S3 doctrina con alta similitud NO desplaza S0 constitución."""
        from albra.knowledge.retrieval import RetrievalQuery
        from albra.knowledge.verification import LegalVerifier

        async def _run():
            q = RetrievalQuery(
                query_text="estado social de derecho dignidad humana solidaridad",
                query_type="semantic",
                jurisdiction="CO",
                top_k=20, min_score=0.0,
            )
            result = await corpus_retriever.retrieve(q)
            v = LegalVerifier().verify(result)
            # Primary must be S0 (not S3)
            if v.primary_evidence_id:
                primary = next(c for c in v.candidates if c.source_id == v.primary_evidence_id)
                assert primary.source_tier <= SourceTier.S1_OFFICIAL, \
                    f"Primary must be S0/S1, got {primary.source_tier.name}"
        asyncio.run(_run())

    def test_argentine_not_in_co(self, corpus_retriever):
        """V1.1: No AR documents (synthetic eliminated)."""
        pytest.skip("V1.1: No AR documents in corpus")
        from albra.knowledge.retrieval import RetrievalQuery
        async def _run():
            q = RetrievalQuery(
                query_text="salud tutela derecho fundamental argentina",
                query_type="semantic",
                jurisdiction="CO",
                top_k=50, min_score=0.0,
            )
            result = await corpus_retriever.retrieve(q)
            for c in result.candidates:
                assert c.provenance.get("jurisdiction") != "AR"
        asyncio.run(_run())

    def test_missing_reach_force_not_inferred(self, corpus_retriever):
        """V1.1: No doctrine in corpus (was synthetic)."""
        pytest.skip("V1.1: No doctrine in corpus (was synthetic, eliminated)")
        from albra.knowledge.retrieval import RetrievalQuery
        async def _run():
            q = RetrievalQuery(
                query_text="estado social de derecho dignidad",
                query_type="semantic",
                jurisdiction="CO",
                top_k=20, min_score=0.0,
            )
            result = await corpus_retriever.retrieve(q)
            for c in result.candidates:
                if c.document_type == "libro_doctrina":
                    # Doctrina no debe tener reach/force vinculante
                    assert c.provenance.get("force") != "vinculante"
                    assert c.provenance.get("force") != "erga_omnes"
        asyncio.run(_run())
