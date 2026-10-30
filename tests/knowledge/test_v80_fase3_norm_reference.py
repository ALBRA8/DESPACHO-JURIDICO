"""V8.0 Fase 3 tests — NormReference, hierarchy, step 9 conditional.

Tests for:
  - cross-reference resolution (verified vs uncertain)
  - hierarchy derivation (constitucion > ley, ley = codigo_sustantivo)
  - security rules (references ≠ contradiction, uncertain ≠ blocking)
  - step 9 conditional activation (civil/penal/conciliación/no-type)
"""
from __future__ import annotations

import pytest

from albra.knowledge.colombia.corpus_pilot.real_corpus_v14 import ALL_DOCUMENTS_V14
from albra.knowledge.norm_reference import (
    NormReference,
    compare_hierarchy,
    get_hierarchy_rank,
    resolve_references,
)
from albra.lawyer.exam import LawyerExam
from albra.llm.providers import MockProvider
from albra.llm.real_provider_guard import RealProviderGuard

# ===== 1. Cross-reference resolution =====

def test_norm_reference_resolves_cross_references():
    """resolve_references() returns a non-empty list from V1.4."""
    refs = resolve_references(ALL_DOCUMENTS_V14)
    assert len(refs) > 0, "Expected cross-references in V1.4"


def test_norm_reference_has_verified_and_uncertain():
    """Some references should be verified (both source+target in corpus),
    others uncertain (target external)."""
    refs = resolve_references(ALL_DOCUMENTS_V14)
    verified = [r for r in refs if r.confidence == "verified"]
    uncertain = [r for r in refs if r.confidence == "uncertain"]
    assert len(verified) > 0, "Expected at least some verified references"
    assert len(uncertain) > 0, "Expected at least some uncertain references"


def test_norm_reference_constitution_internal_verified():
    """Constitución articles referencing other Constitución articles
    should be verified (both source and target in V1.4)."""
    refs = resolve_references(ALL_DOCUMENTS_V14)
    const_internal = [
        r for r in refs
        if r.source_doc == "constitucion"
        and r.target_doc == "constitucion"
        and r.confidence == "verified"
    ]
    assert len(const_internal) > 0, (
        "Expected verified internal Constitución cross-references"
    )


def test_norm_reference_cpp_to_constitution_verified():
    """CPP articles referencing Constitución articles should be verified
    (both CPP and Constitución in V1.4)."""
    refs = resolve_references(ALL_DOCUMENTS_V14)
    cpp_to_const = [
        r for r in refs
        if r.source_doc == "ley_0906_2004"
        and r.target_doc == "constitucion"
        and r.confidence == "verified"
    ]
    assert len(cpp_to_const) > 0, (
        "Expected verified CPP→Constitución cross-references"
    )


def test_norm_reference_external_target_uncertain():
    """References to Código Civil (NOT in corpus) should be uncertain."""
    refs = resolve_references(ALL_DOCUMENTS_V14)
    # CGP references many Código Civil articles — these should be uncertain
    external = [
        r for r in refs
        if r.confidence == "uncertain"
        and r.target_doc == ""  # could not resolve target doc
    ]
    assert len(external) > 0, "Expected uncertain references to external docs"


def test_norm_reference_reference_type_is_references():
    """All NormReference objects should have reference_type='references'.
    They are informational mentions, not modifications or contradictions."""
    refs = resolve_references(ALL_DOCUMENTS_V14)
    for r in refs:
        assert r.reference_type == "references", (
            f"Expected 'references', got {r.reference_type}"
        )


# ===== 2. Hierarchy derivation =====

def test_hierarchy_constitution_highest():
    """Constitución should have rank 1 (highest)."""
    assert get_hierarchy_rank("constitucion") == 1


def test_hierarchy_ley_same_as_codigo_sustantivo():
    """Ley and codigo_sustantivo should have the same rank (2).
    CST is a Decreto-Ley — NOT a separate rank."""
    assert get_hierarchy_rank("ley") == 2
    assert get_hierarchy_rank("codigo_sustantivo") == 2
    assert get_hierarchy_rank("ley") == get_hierarchy_rank("codigo_sustantivo")


def test_hierarchy_compare_constitution_vs_ley():
    """Constitución should be higher than Ley."""
    assert compare_hierarchy("constitucion", "ley") == "higher"
    assert compare_hierarchy("ley", "constitucion") == "lower"


def test_hierarchy_compare_ley_vs_codigo_sustantivo():
    """Ley and codigo_sustantivo should be equal rank."""
    assert compare_hierarchy("ley", "codigo_sustantivo") == "equal"


def test_hierarchy_unknown_type():
    """Unknown document_type should return rank 999 and compare as unknown."""
    assert get_hierarchy_rank("nonexistent") == 999
    assert compare_hierarchy("nonexistent", "ley") == "unknown"


# ===== 3. Security rules =====

def test_references_not_contradiction():
    """A NormReference with type='references' must NOT be treated as
    explicit_conflict by ContradictionDetector."""
    from albra.knowledge.contradiction import ContradictionDetector
    # Two articles where one references the other (informational)
    citations = [
        {"document": "constitucion", "article": "116",
         "article_text": "En los términos del artículo 237 de la Constitución."},
        {"document": "constitucion", "article": "237",
         "article_text": "Text of article 237."},
    ]
    detector = ContradictionDetector()
    results = detector.detect(citations)
    # The reference should NOT produce explicit_conflict
    for r in results:
        assert r.relation != "explicit_conflict", (
            f"Reference should not be classified as explicit_conflict: {r.detail}"
        )


def test_uncertain_reference_not_blocking():
    """An uncertain NormReference must NOT produce a blocking defect
    in AdversarialValidator."""
    from albra.lawyer.adversarial_validation import AdversarialValidator
    # Cite arts. 28/29/30 — these are vigent, no blocking expected
    doc = next(d for s, d in ALL_DOCUMENTS_V14 if s == "constitucion")
    citations = []
    for art_num in ["28", "29", "30"]:
        art = next(a for a in doc["articles"] if a["number"] == art_num)
        citations.append({
            "document": "constitucion",
            "article": art_num,
            "article_text": art["text"],
            "provenance_status": "VERIFIED",
        })
    validator = AdversarialValidator()
    result = validator.validate(citations=citations, corpus=ALL_DOCUMENTS_V14)
    blocking = [d for d in result.defects if d.severity == "blocking"]
    assert len(blocking) == 0


# ===== 4. Step 9 conditional activation =====

def test_step_9_abstain_without_procedure_type():
    """Without procedure_type → step 9 ABSTAINED.
    Uses _StubLLMProvider to reach step 9 (MockProvider blocks at 7)."""
    from tests.knowledge.test_v80_fase2_validation import _StubLLMProvider
    case = {
        "summary": "test",
        "facts": ["fact"],
        "legal_issues": ["issue"],
        "required_sources": [
            {"document": "constitucion", "article": "28"},
        ],
        "document_type": "test",
        # NO procedure_type
    }
    stub = _StubLLMProvider()
    guard = RealProviderGuard(provider=stub, role="lawyer")
    exam = LawyerExam(case_id="test-step9-no-proc", case_facts=case, guard=guard)
    result = exam.run()
    step9 = next((s for s in result.steps if s.step_number == 9), None)
    assert step9 is not None, "Step 9 must be reached with StubLLMProvider"
    assert step9.status == "abstained"
    assert "procedure_type" in step9.summary.lower()


def test_step_9_abstain_unknown_procedure_type():
    """Unknown procedure_type → ABSTAINED."""
    from tests.knowledge.test_v80_fase2_validation import _StubLLMProvider
    case = {
        "summary": "test",
        "facts": ["fact"],
        "legal_issues": ["issue"],
        "required_sources": [
            {"document": "constitucion", "article": "28"},
        ],
        "document_type": "test",
        "procedure_type": "administrativo",  # not mapped
    }
    stub = _StubLLMProvider()
    guard = RealProviderGuard(provider=stub, role="lawyer")
    exam = LawyerExam(case_id="test-step9-unknown", case_facts=case, guard=guard)
    result = exam.run()
    step9 = next((s for s in result.steps if s.step_number == 9), None)
    assert step9 is not None, "Step 9 must be reached with StubLLMProvider"
    assert step9.status == "abstained"


def test_step_9_activates_with_civil_procedure():
    """procedure_type='civil' → CGP in corpus → step 9 processes."""
    case = {
        "summary": "test civil procedure",
        "facts": ["fact"],
        "legal_issues": ["issue"],
        "required_sources": [
            {"document": "constitucion", "article": "29"},
        ],
        "document_type": "demanda civil",
        "procedure_type": "civil",
    }
    # Use StubLLMProvider to avoid Mock blocking
    from tests.knowledge.test_v80_fase2_validation import _StubLLMProvider
    stub = _StubLLMProvider()
    guard = RealProviderGuard(provider=stub, role="lawyer")
    exam = LawyerExam(case_id="test-step9-civil", case_facts=case, guard=guard)
    result = exam.run()
    step9 = next((s for s in result.steps if s.step_number == 9), None)
    assert step9 is not None
    assert step9.status == "ok", (
        f"Step 9 should be ok with civil procedure_type. "
        f"Got: {step9.status}. Summary: {step9.summary}"
    )
    assert "ley_1564_2012" in step9.summary


def test_step_9_activates_with_penal_procedure():
    """procedure_type='penal' → CPP in corpus → step 9 processes."""
    case = {
        "summary": "test penal procedure",
        "facts": ["fact"],
        "legal_issues": ["issue"],
        "required_sources": [
            {"document": "constitucion", "article": "29"},
        ],
        "document_type": "acción penal",
        "procedure_type": "penal",
    }
    from tests.knowledge.test_v80_fase2_validation import _StubLLMProvider
    stub = _StubLLMProvider()
    guard = RealProviderGuard(provider=stub, role="lawyer")
    exam = LawyerExam(case_id="test-step9-penal", case_facts=case, guard=guard)
    result = exam.run()
    step9 = next((s for s in result.steps if s.step_number == 9), None)
    assert step9 is not None
    assert step9.status == "ok"
    assert "ley_0906_2004" in step9.summary


def test_step_9_activates_with_conciliacion():
    """procedure_type='conciliación' → Ley 640 in corpus → step 9 processes."""
    case = {
        "summary": "test conciliacion",
        "facts": ["fact"],
        "legal_issues": ["issue"],
        "required_sources": [
            {"document": "constitucion", "article": "29"},
        ],
        "document_type": "conciliación",
        "procedure_type": "conciliación",
    }
    from tests.knowledge.test_v80_fase2_validation import _StubLLMProvider
    stub = _StubLLMProvider()
    guard = RealProviderGuard(provider=stub, role="lawyer")
    exam = LawyerExam(case_id="test-step9-conc", case_facts=case, guard=guard)
    result = exam.run()
    step9 = next((s for s in result.steps if s.step_number == 9), None)
    assert step9 is not None
    assert step9.status == "ok"
    assert "ley_0640_2001" in step9.summary


# ===== 5. Pilot case regression =====

def test_pilot_case_step_9_still_abstained_without_procedure_type():
    """The pilot case (habeas corpus) doesn't declare procedure_type →
    step 9 should still be ABSTAINED."""
    from tests.knowledge.test_v80_fase2_validation import _StubLLMProvider
    case = {
        "summary": "Habeas corpus pilot",
        "facts": ["detenido sin orden judicial"],
        "legal_issues": ["art. 28", "art. 30", "art. 29"],
        "required_sources": [
            {"document": "constitucion", "article": "28"},
            {"document": "constitucion", "article": "30"},
            {"document": "constitucion", "article": "29"},
        ],
        "document_type": "escrito de habeas corpus",
        # NO procedure_type — should abstain
    }
    stub = _StubLLMProvider()
    guard = RealProviderGuard(provider=stub, role="lawyer")
    exam = LawyerExam(case_id="pilot-step9-regression", case_facts=case, guard=guard)
    result = exam.run()
    step9 = next((s for s in result.steps if s.step_number == 9), None)
    assert step9 is not None, "Step 9 must be reached with StubLLMProvider"
    assert step9.status == "abstained", (
        "Pilot case without procedure_type should still ABSTAIN at step 9."
    )
