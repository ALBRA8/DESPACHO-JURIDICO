"""Tests HARDENING V1.0 — Cierre precorpus.

BLOQUE 1: Identificación de normas compuestas
BLOQUE 2: VersionHistory fechas malformadas
BLOQUE 3: Vocabulario controlado de efectos jurisprudenciales
BLOQUE 4: Validación de procedencia (source_url)
BLOQUE 5: Routing jurídico (ley de Ohm false positive)
BLOQUE 6: Docstring _select_primary coincide con implementación
"""
import asyncio
import os
import tempfile
from datetime import date

import pytest

from albra.config.settings import reset_settings


@pytest.fixture
def strong_secrets(monkeypatch):
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-ephemeral-jwt-secret-32-chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-ephemeral-pass-1234")
    reset_settings()
    yield
    reset_settings()


# ============================================================
# BLOQUE 1 — IDENTIFICACIÓN DE NORMAS COMPUESTAS
# ============================================================

class TestNormIdentification:
    def test_codigo_sustantivo_del_trabajo(self):
        """BLOQUE 1: 'Código Sustantivo del Trabajo' se captura completo."""
        from albra.knowledge.query_classifier import LegalQueryClassifier
        c = LegalQueryClassifier()
        r = c.classify("¿Qué dice el artículo 25 del Código Sustantivo del Trabajo?")
        assert r.detected_norm is not None
        assert "Sustantivo" in r.detected_norm
        assert "Trabajo" in r.detected_norm
        assert not r.needs_clarification

    def test_codigo_general_del_proceso(self):
        from albra.knowledge.query_classifier import LegalQueryClassifier
        c = LegalQueryClassifier()
        r = c.classify("¿Qué dice el artículo 100 del Código General del Proceso?")
        assert r.detected_norm is not None
        assert "General" in r.detected_norm
        assert "Proceso" in r.detected_norm

    def test_codigo_procedimiento_administrativo_completo(self):
        """Denominación muy larga - no truncar."""
        from albra.knowledge.query_classifier import LegalQueryClassifier
        c = LegalQueryClassifier()
        r = c.classify(
            "¿Qué dice el artículo 70 del Código de Procedimiento Administrativo "
            "y de lo Contencioso Administrativo?"
        )
        assert r.detected_norm is not None
        assert "Procedimiento" in r.detected_norm
        assert "Contencioso" in r.detected_norm
        assert "Administrativo" in r.detected_norm

    def test_constitucion_politica_de_colombia(self):
        from albra.knowledge.query_classifier import LegalQueryClassifier
        c = LegalQueryClassifier()
        r = c.classify("¿Qué dice la Constitución Política de Colombia?")
        assert r.detected_norm is not None
        assert "Política" in r.detected_norm or "politica" in r.detected_norm.lower()

    def test_codigo_civil_simple(self):
        """Compat: 'Código Civil' sigue funcionando."""
        from albra.knowledge.query_classifier import LegalQueryClassifier
        c = LegalQueryClassifier()
        r = c.classify("¿Qué dice el artículo 200 del Código Civil?")
        assert r.detected_norm is not None
        assert "Civil" in r.detected_norm

    def test_variaciones_mayusculas_minusculas(self):
        from albra.knowledge.query_classifier import LegalQueryClassifier
        c = LegalQueryClassifier()
        for variant in [
            "código sustantivo del trabajo",
            "CÓDIGO SUSTANTIVO DEL TRABAJO",
            "Código Sustantivo del Trabajo",
            "código Sustantivo Del trabajo",
        ]:
            r = c.classify(f"¿Qué dice el artículo 1 del {variant}?")
            assert r.detected_norm is not None, f"Failed for: {variant}"
            assert "sustantivo" in r.detected_norm.lower()

    def test_no_captura_palabras_irrelevantes(self):
        """La regex no debe capturar palabras de la pregunta como parte del nombre."""
        from albra.knowledge.query_classifier import LegalQueryClassifier
        c = LegalQueryClassifier()
        r = c.classify("¿Qué dice el Código Civil sobre contratos?")
        assert r.detected_norm is not None
        # "sobre contratos" NO debe ser parte del nombre de la norma
        assert "sobre" not in r.detected_norm.lower()
        assert "contratos" not in r.detected_norm.lower()


# ============================================================
# BLOQUE 2 — VERSIONHISTORY FECHAS MALFORMADAS
# ============================================================

class TestVersionHistoryHardened:
    def test_fecha_invalida_no_crash(self):
        """BLOQUE 2: fecha malformada no crashea."""
        from albra.knowledge.temporal import VersionHistory
        vh = VersionHistory(norm_id="n1")
        vh.add_version(version=1, effective_from="not-a-date",
                       effective_until="also-bad", status="vigente")
        # No debe crashear
        result = vh.get_version_at(date(2020, 6, 15))
        # Fecha inválida → no se puede verificar → None (fail-safe)
        assert result is None

    def test_fecha_vacia_no_crash(self):
        from albra.knowledge.temporal import VersionHistory
        vh = VersionHistory(norm_id="n1")
        vh.add_version(version=1, effective_from=None,
                       effective_until=None, status="vigente")
        result = vh.get_version_at(date(2020, 6, 15))
        # Sin fechas pero status vigente → debe retornar la versión
        assert result is not None

    def test_fecha_valida_funciona(self):
        from albra.knowledge.temporal import VersionHistory
        vh = VersionHistory(norm_id="n1")
        vh.add_version(version=1, effective_from="2000-01-01",
                       effective_until="2020-12-31", status="vigente")
        result = vh.get_version_at(date(2010, 6, 15))
        assert result is not None
        assert result["version"] == 1

    def test_fecha_invalida_no_afirma_vigencia(self):
        """BLOQUE 2: fecha inválida NUNCA produce respuesta afirmativa de vigencia."""
        from albra.knowledge.temporal import VersionHistory
        vh = VersionHistory(norm_id="n1")
        vh.add_version(version=1, effective_from="BAD",
                       effective_until="ALSO-BAD", status="vigente")
        result = vh.get_version_at(date.today())
        # No debe retornar la versión como vigente
        assert result is None, "Fecha inválida no debe afirmar vigencia"

    def test_fecha_iso_format_valido(self):
        from albra.knowledge.temporal import VersionHistory
        vh = VersionHistory(norm_id="n1")
        vh.add_version(version=1, effective_from="1993-12-23",
                       effective_until=None, status="vigente")
        result = vh.current_version()
        assert result is not None


# ============================================================
# BLOQUE 3 — VOCABULARIO CONTROLADO DE EFECTOS
# ============================================================

class TestEffectControlledVocabulary:
    def test_effect_valid_values(self):
        from albra.knowledge.schemas import (
            EFFECT_VALUES,
            Jurisprudence,
            validate_effect,
        )
        for valid_effect in EFFECT_VALUES:
            if valid_effect == "desconocido":
                continue
            j = Jurisprudence(id="j", court="CC", effect=valid_effect)
            assert j.effect == valid_effect, f"Failed for: {valid_effect}"

    def test_effect_invalid_becomes_desconocido(self):
        from albra.knowledge.schemas import Jurisprudence
        j = Jurisprudence(id="j", court="CC", effect="banana")
        assert j.effect == "desconocido", "Invalid effect should become 'desconocido'"

    def test_effect_empty_becomes_desconocido(self):
        from albra.knowledge.schemas import Jurisprudence
        j = Jurisprudence(id="j", court="CC", effect="")
        assert j.effect == "desconocido"

    def test_effect_none_becomes_desconocido(self):
        from albra.knowledge.schemas import validate_effect
        assert validate_effect(None) == "desconocido"

    def test_binding_derived_from_effect(self):
        from albra.knowledge.schemas import Jurisprudence
        # erga_omnes → binding=True
        j1 = Jurisprudence(id="j1", court="CC", effect="erga_omnes")
        assert j1.binding is True
        # inter_partes → binding=False
        j2 = Jurisprudence(id="j2", court="CC", effect="inter_partes")
        assert j2.binding is False
        # vinculante → binding=True
        j3 = Jurisprudence(id="j3", court="CC", effect="vinculante")
        assert j3.binding is True
        # orientador → binding=False
        j4 = Jurisprudence(id="j4", court="CC", effect="orientador")
        assert j4.binding is False

    def test_effect_distinguishes_erga_omnes_from_inter_partes(self):
        """BLOQUE 3: el sistema distingue tipos de efecto."""
        from albra.knowledge.schemas import Jurisprudence, is_binding_effect
        j_erga = Jurisprudence(id="j1", court="Corte Constitucional",
                               effect="erga_omnes")
        j_inter = Jurisprudence(id="j2", court="Juzgado Civil",
                                effect="inter_partes")
        assert is_binding_effect(j_erga.effect) is True
        assert is_binding_effect(j_inter.effect) is False
        # NO son equivalentes
        assert j_erga.effect != j_inter.effect

    def test_verification_uses_effect_not_binding(self):
        """BLOQUE 3: verification distingue effect types en conflict detection."""
        from albra.knowledge.retrieval import RetrievalResult
        from albra.knowledge.schemas import EvidenceCandidate, SourceTier
        from albra.knowledge.verification import LegalVerifier
        c1 = EvidenceCandidate(
            source_id="c1", document_id="d1",
            source_tier=SourceTier.S0_PRIMARY_SUPERIOR,
            authority="Corte Constitucional", document_type="sentencia",
            snippet="t", is_current=True, score=0.8,
            provenance={"effect": "erga_omnes"},
        )
        c2 = EvidenceCandidate(
            source_id="c2", document_id="d2",
            source_tier=SourceTier.S0_PRIMARY_SUPERIOR,
            authority="Corte Suprema", document_type="sentencia",
            snippet="t", is_current=True, score=0.7,
            provenance={"effect": "vinculante"},
        )
        v = LegalVerifier().verify(RetrievalResult(candidates=[c1, c2]))
        # Multiple binding → high severity conflict
        high_conflicts = [c for c in v.conflicts if c.severity == "high"]
        assert len(high_conflicts) >= 1, "Should detect jurisprudence contradiction"
        # Conflict description mentions effects (check ALL conflicts, not just first)
        all_descs = " ".join(c.description for c in v.conflicts)
        assert "erga_omnes" in all_descs or "vinculante" in all_descs, \
            f"Effect types should appear in conflict descriptions: {all_descs}"

    def test_effect_desconocido_not_binding(self):
        from albra.knowledge.schemas import Jurisprudence
        j = Jurisprudence(id="j", court="CC", effect="desconocido")
        assert j.binding is False
        assert j.effect == "desconocido"


# ============================================================
# BLOQUE 4 — VALIDACIÓN DE PROCEDENCIA
# ============================================================

class TestProvenanceValidation:
    def test_url_valida_marca_verified(self):
        from albra.knowledge.ingestion import LegalIngestionPipeline
        pipe = LegalIngestionPipeline()
        r = asyncio.run(pipe.ingest(
            source_id="s1", raw_content=b"content",
            source_url="https://www.funcionpublica.gov.co/ley-100",
            authority="Congreso", document_type="ley",
        ))
        assert r.ok
        assert "url_verified=True" in r.steps[3].detail  # normalize step

    def test_url_malformada_marca_no_verified(self):
        from albra.knowledge.ingestion import LegalIngestionPipeline
        pipe = LegalIngestionPipeline()
        r = asyncio.run(pipe.ingest(
            source_id="s2", raw_content=b"content",
            source_url="not-a-url",
            authority="Congreso", document_type="ley",
        ))
        assert r.ok  # no falla, solo warning
        assert any("malformed" in w for w in r.warnings)

    def test_url_vacia_marca_no_verified(self):
        from albra.knowledge.ingestion import LegalIngestionPipeline
        pipe = LegalIngestionPipeline()
        r = asyncio.run(pipe.ingest(
            source_id="s3", raw_content=b"content",
            source_url="",
            authority="Congreso", document_type="ley",
        ))
        assert r.ok
        assert any("empty" in w for w in r.warnings)

    def test_provenance_records_url_verified(self):
        from albra.knowledge.ingestion import LegalIngestionPipeline
        pipe = LegalIngestionPipeline()
        r = asyncio.run(pipe.ingest(
            source_id="s4", raw_content=b"content",
            source_url="https://www.gov.co/norma",
            authority="Congreso", document_type="ley",
        ))
        assert r.ok

    def test_provenance_records_url_not_verified(self):
        from albra.knowledge.ingestion import LegalIngestionPipeline
        pipe = LegalIngestionPipeline()
        r = asyncio.run(pipe.ingest(
            source_id="s5", raw_content=b"content",
            source_url="bad-url",
            authority="Congreso", document_type="ley",
        ))
        assert r.ok
        assert any("malformed" in w.lower() for w in r.warnings)


# ============================================================
# BLOQUE 5 — ROUTING JURÍDICO
# ============================================================

class TestRoutingHardened:
    def test_ley_de_ohm_no_ruta_legal(self, strong_secrets):
        """BLOQUE 5: 'ley de Ohm' (física) NO debe rutear a legal_engine."""
        from albra.identity.agent import get_agent
        async def _run():
            agent = get_agent()
            await agent.boot()
            r = await agent.process("calcula la ley de ohm", user="test", user_role="admin")
            assert r.get("routed_to") != "legal_engine", "ley de Ohm should NOT route to legal_engine"
            await agent.shutdown()
        asyncio.run(_run())

    def test_consulta_ley_colombiana_si_ruta(self, strong_secrets):
        """BLOQUE 5: consulta legal colombiana SÍ rutea."""
        from albra.identity.agent import get_agent
        async def _run():
            agent = get_agent()
            await agent.boot()
            r = await agent.process("¿Qué dice la Ley 100 de 1993?", user="test", user_role="admin")
            assert r.get("routed_to") == "legal_engine"
            await agent.shutdown()
        asyncio.run(_run())

    def test_consulta_articulo_si_ruta(self, strong_secrets):
        from albra.identity.agent import get_agent
        async def _run():
            agent = get_agent()
            await agent.boot()
            r = await agent.process("¿Qué dice el artículo 25?", user="test", user_role="admin")
            assert r.get("routed_to") == "legal_engine"
            await agent.shutdown()
        asyncio.run(_run())

    def test_consulta_sentencia_si_ruta(self, strong_secrets):
        from albra.identity.agent import get_agent
        async def _run():
            agent = get_agent()
            await agent.boot()
            r = await agent.process("¿Qué dice la sentencia C-001 de 2024?", user="test", user_role="admin")
            assert r.get("routed_to") == "legal_engine"
            await agent.shutdown()
        asyncio.run(_run())

    def test_calcula_7_por_8_no_ruta(self, strong_secrets):
        from albra.identity.agent import get_agent
        async def _run():
            agent = get_agent()
            await agent.boot()
            r = await agent.process("calcula 7*8", user="test", user_role="admin")
            assert r.get("routed_to") != "legal_engine"
            await agent.shutdown()
        asyncio.run(_run())

    def test_hola_no_ruta(self, strong_secrets):
        from albra.identity.agent import get_agent
        async def _run():
            agent = get_agent()
            await agent.boot()
            r = await agent.process("hola qué más", user="test", user_role="anon")
            assert r.get("routed_to") != "legal_engine"
            await agent.shutdown()
        asyncio.run(_run())


# ============================================================
# BLOQUE 6 — DOCSTRING _select_primary
# ============================================================

class TestDocstringSelectPrimary:
    def test_docstring_no_mentiona_excepcion_s4_supera_s0(self):
        """BLOQUE 6: docstring NO dice que S4 puede superar S0 (con excepciones)."""
        import inspect

        from albra.knowledge.verification import LegalVerifier
        doc = inspect.getdoc(LegalVerifier._select_primary)
        assert doc is not None
        # Debe decir claramente que S0 SIEMPRE gana
        assert "siempre" in doc.lower() or "no hay excepción" in doc.lower(), \
            "Docstring must state S0 ALWAYS beats S4"
        # NO debe tener la frase "Solo puede superar S0 si"
        assert "solo puede superar" not in doc.lower(), \
            "Docstring still claims S4 can beat S0 in certain conditions"

    def test_docstring_describe_criterios_ordenamiento(self):
        import inspect

        from albra.knowledge.verification import LegalVerifier
        doc = inspect.getdoc(LegalVerifier._select_primary)
        assert "source_tier" in doc.lower()
        assert "is_current" in doc.lower() or "vigencia" in doc.lower()
        assert "score" in doc.lower()

    def test_s0_siempre_supera_s4_regresion(self):
        """BLOQUE 6: S0 siempre supera S4, sin importar score."""
        from albra.knowledge.retrieval import RetrievalResult
        from albra.knowledge.schemas import EvidenceCandidate, SourceTier
        from albra.knowledge.verification import LegalVerifier
        # Test con score extremo: S0=0.01 vs S4=0.99
        c_s0 = EvidenceCandidate(
            source_id="s0", document_id="d0",
            source_tier=SourceTier.S0_PRIMARY_SUPERIOR,
            authority="Congreso", document_type="ley",
            snippet="t", is_current=True, score=0.01,
        )
        c_s4 = EvidenceCandidate(
            source_id="s4", document_id="d4",
            source_tier=SourceTier.S4_SECONDARY,
            authority="Blog", document_type="articulo",
            snippet="t", is_current=True, score=0.99,
        )
        v = LegalVerifier().verify(RetrievalResult(candidates=[c_s0, c_s4]))
        assert v.primary_evidence_id == "s0", "S0 must ALWAYS beat S4 regardless of score"
