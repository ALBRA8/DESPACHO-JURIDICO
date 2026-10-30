"""V8.0 Fase 4 — Candidato 1: Draft Citation Audit determinista.

Tests LEGAL-SEMANTIC + ADVERSARIAL que verifican el audit
determinista post-LLM sobre el draft.

Disciplina:
- Draft con cita a norma externa NO en V1.4 → BLOCKED.
- Draft con cita a artículo adicional de norma V1.4 verificada → WARNING.
- Draft con todas las citas en citations_verified → SUCCESS.
- Draft sin citas → SUCCESS (no audit needed).
- Audit NO reemplaza step 11 (ambos corren).
- Audit NO verifica fidelidad de paráfrasis (limitación explícita).
"""
from __future__ import annotations

from typing import Any

import pytest

from albra.knowledge.colombia.corpus_pilot.real_corpus_v14 import ALL_DOCUMENTS_V14
from albra.lawyer.exam import LawyerExam
from albra.llm.providers import LLMResponse
from albra.llm.real_provider_guard import RealProviderGuard

# ===== Test fixtures =====

class _DraftControllingStubProvider:
    """Stub LLM provider that returns controlled drafts.

    Allows tests to inject a specific draft text in step 10 while
    returning generic text for steps 7, 8, 11. This lets us test the
    draft audit in isolation.

    is_mock=False, is_external=True so RealProviderGuard accepts it
    (mirrors _StubLLMProvider pattern from Fase 2 tests).
    """

    name = "draft-controlling-stub"
    is_mock = False
    is_external = True
    default_model = "stub-draft-v1"

    def __init__(self, *, draft_text: str) -> None:
        self._draft_text = draft_text
        self._call_count = 0

    def generate(self, prompt: str, *, model: str | None = None,
                 max_tokens: int = 1000, temperature: float = 0.5) -> LLMResponse:
        self._call_count += 1
        # Step 10 prompt contains "BORRADOR (en español"
        if "BORRADOR" in prompt and "en español" in prompt:
            return LLMResponse(
                text=self._draft_text,
                provider=self.name,
                model=self.default_model,
                metadata={"tokens": len(self._draft_text) // 4},
            )
        # Steps 7, 8, 11 — return generic text
        return LLMResponse(
            text="Respuesta genérica del stub para pasos no-10.",
            provider=self.name,
            model=self.default_model,
            metadata={"tokens": 50},
        )

    def chat(self, messages: list[dict[str, str]], *, model: str | None = None,
             max_tokens: int = 1000, temperature: float = 0.5) -> LLMResponse:
        prompt = messages[-1]["content"] if messages else ""
        return self.generate(prompt, model=model, max_tokens=max_tokens, temperature=temperature)


def _build_case_with_draft(draft_text: str) -> LawyerExam:
    """Build a LawyerExam that completes steps 1-10 and injects the
    given draft_text at step 10."""
    case = {
        "summary": "test draft audit",
        "facts": ["hecho 1", "hecho 2"],
        "legal_issues": ["art. 29 debido proceso"],
        "required_sources": [
            {"document": "constitucion", "article": "29"},
        ],
        "document_type": "escrito de tutela",
    }
    stub = _DraftControllingStubProvider(draft_text=draft_text)
    guard = RealProviderGuard(provider=stub, role="lawyer")
    return LawyerExam(case_id="test-draft-audit", case_facts=case, guard=guard)


# ===== 1. Draft with external norm → BLOCKED =====

def test_draft_with_external_norm_blocked():
    """Draft que cita una norma externa (Ley 812 de 2003, no en V1.4)
    debe resultar en overall_status='BLOCKED' con draft_citation_defects
    no vacío."""
    draft = (
        "BORRADOR\n\n"
        "Con base en el artículo 29 de la Constitución Política de 1991, "
        "solicito la protección de los derechos fundamentales.\n\n"
        "Adicionalmente, invoco la Ley 812 de 2003, artículo 81, "
        "que establece disposiciones sobre el plan nacional de desarrollo."
    )
    exam = _build_case_with_draft(draft)
    result = exam.run()
    assert result.overall_status == "BLOCKED", (
        f"Expected BLOCKED for draft with external norm. Got: {result.overall_status}. "
        f"Reason: {result.overall_reason}"
    )
    assert "no verificada" in result.overall_reason.lower() or "alucinación" in result.overall_reason.lower(), (
        f"overall_reason should mention unverified norm: {result.overall_reason}"
    )
    assert len(result.draft_citation_defects) >= 1, (
        f"Expected ≥1 blocking defect. Got: {result.draft_citation_defects}"
    )
    # Verify the defect mentions the external norm
    defect = result.draft_citation_defects[0]
    assert "812" in defect["raw_text"] or "812" in defect["document_name"]


def test_draft_with_external_sentencia_blocked():
    """Draft que cita una sentencia externa (Sentencia C-251/2002, no en
    V1.4) debe resultar en BLOCKED."""
    draft = (
        "BORRADOR\n\n"
        "Con base en el artículo 29 de la Constitución Política de 1991, "
        "solicito la protección.\n\n"
        "La Sentencia C-251/2002 de la Corte Constitucional establece "
        "el estándar aplicable al caso."
    )
    exam = _build_case_with_draft(draft)
    result = exam.run()
    assert result.overall_status == "BLOCKED", (
        f"Expected BLOCKED for external sentencia. Got: {result.overall_status}"
    )
    assert len(result.draft_citation_defects) >= 1


# ===== 2. Draft with all citations verified → SUCCESS =====

def test_draft_with_all_citations_verified_ok():
    """Draft con citas solo a normas en citations_verified → SUCCESS,
    draft_citation_defects vacío."""
    draft = (
        "BORRADOR\n\n"
        "Con base en el artículo 29 de la Constitución Política de 1991, "
        "solicito la protección de los derechos fundamentales al debido "
        "proceso. El artículo 29 de la Constitución garantiza el debido "
        "proceso aplicable a toda clase de actuaciones."
    )
    exam = _build_case_with_draft(draft)
    result = exam.run()
    # Should succeed — only Constitución art. 29 cited, which is verified.
    assert result.overall_status == "SUCCESS", (
        f"Expected SUCCESS for draft with all verified citations. Got: {result.overall_status}. "
        f"Reason: {result.overall_reason}. Defects: {result.draft_citation_defects}"
    )
    assert len(result.draft_citation_defects) == 0


def test_draft_with_no_citations_ok():
    """Draft sin ninguna cita jurídica → SUCCESS, audit no blocking."""
    draft = (
        "BORRADOR\n\n"
        "Solicito respetuosamente la protección de los derechos del "
        "peticionario. Los hechos del caso demuestran la vulneración "
        "evidente de garantías fundamentales."
    )
    exam = _build_case_with_draft(draft)
    result = exam.run()
    assert result.overall_status == "SUCCESS", (
        f"Expected SUCCESS for draft without citations. Got: {result.overall_status}"
    )
    assert len(result.draft_citation_defects) == 0


# ===== 3. Draft with additional article in verified norm → WARNING =====

def test_draft_with_additional_article_in_verified_norm_warns():
    """Draft que cita un artículo de una norma verificada PERO el
    artículo no estaba en citations_verified (el LLM introdujo un
    artículo nuevo de la misma norma). Debe resultar en WARNING
    (limitation), no BLOCKED."""
    # citations_verified will have Constitución art. 29.
    # The draft cites art. 29 (verified) AND art. 30 (not verified but
    # Constitución IS verified).
    draft = (
        "BORRADOR\n\n"
        "Con base en el artículo 29 de la Constitución y el artículo 30 "
        "de la Constitución, solicito la protección de los derechos "
        "fundamentales."
    )
    exam = _build_case_with_draft(draft)
    result = exam.run()
    # Should NOT be blocked — Constitución art. 30 is in V1.4 corpus,
    # and Constitución IS verified (just art. 30 wasn't declared).
    assert result.overall_status == "SUCCESS", (
        f"Expected SUCCESS for draft with additional article in verified norm. "
        f"Got: {result.overall_status}. Reason: {result.overall_reason}"
    )
    # But there should be a warning in limitations.
    warning_text = [lim for lim in result.limitations if "art. 30" in lim and "verificada" in lim.lower()]
    assert warning_text, (
        f"Expected WARNING about art. 30 not in verified list. "
        f"Limitations: {result.limitations}"
    )


# ===== 4. Audit runs between step 10 and step 11 =====

def test_draft_audit_runs_between_step_10_and_step_11():
    """When audit blocks, step 11 (review) must NOT execute."""
    draft = (
        "BORRADOR\n\n"
        "Con base en el artículo 29 de la Constitución Política de 1991, "
        "y la Ley 812 de 2003, artículo 81, solicito la protección."
    )
    exam = _build_case_with_draft(draft)
    result = exam.run()
    # Step 10 must have completed (status ok).
    step10 = next((s for s in result.steps if s.step_number == 10), None)
    assert step10 is not None, "Step 10 must execute"
    assert step10.status == "ok"
    # Step 11 must NOT have executed (audit blocked before).
    step11 = next((s for s in result.steps if s.step_number == 11), None)
    assert step11 is None, (
        f"Step 11 should NOT execute when audit blocks. Found: {step11}"
    )
    # Overall must be BLOCKED.
    assert result.overall_status == "BLOCKED"


def test_draft_audit_passes_then_step_11_executes():
    """When audit passes (no blocking defects), step 11 must execute."""
    draft = (
        "BORRADOR\n\n"
        "Con base en el artículo 29 de la Constitución Política de 1991, "
        "solicito la protección."
    )
    exam = _build_case_with_draft(draft)
    result = exam.run()
    # Audit passed → step 11 must execute.
    step11 = next((s for s in result.steps if s.step_number == 11), None)
    assert step11 is not None, "Step 11 must execute when audit passes"
    assert step11.status == "ok"


# ===== 5. Audit does not weaken existing guards =====

def test_draft_audit_does_not_weaken_step_7_validator():
    """Step 7 AdversarialValidator must still execute when draft audit
    is wired in. Pilot case (arts. 28/29/30 vigentes) → step 7 OK."""
    from tests.knowledge.test_v80_fase2_validation import _StubLLMProvider
    case = {
        "summary": "pilot habeas corpus",
        "facts": ["detenido sin orden judicial"],
        "legal_issues": ["art. 28", "art. 30", "art. 29"],
        "required_sources": [
            {"document": "constitucion", "article": "28"},
            {"document": "constitucion", "article": "30"},
            {"document": "constitucion", "article": "29"},
        ],
        "document_type": "escrito de habeas corpus",
    }
    stub = _StubLLMProvider()
    guard = RealProviderGuard(provider=stub, role="lawyer")
    exam = LawyerExam(case_id="pilot-with-audit", case_facts=case, guard=guard)
    result = exam.run()
    step7 = next((s for s in result.steps if s.step_number == 7), None)
    assert step7 is not None and step7.status == "ok"
    # Audit should pass (no external citations in stub-generated draft).
    assert len(result.draft_citation_defects) == 0


def test_draft_audit_disclaimer_in_limitations():
    """Limitations debe incluir el disclaimer explícito sobre el alcance
    del audit (no verifica fidelidad de paráfrasis)."""
    draft = "BORRADOR\n\nSin citas jurídicas."
    exam = _build_case_with_draft(draft)
    result = exam.run()
    disclaimer = [lim for lim in result.limitations if "Audit de citas del draft" in lim and "V8.0 Fase 4" in lim]
    assert disclaimer, (
        f"Expected audit disclaimer in limitations. Got: {result.limitations}"
    )
    # Disclaimer must explicitly say it does NOT verify paraphrase fidelity
    assert "fidelidad de paráfrasis" in disclaimer[0]
    assert "aplicabilidad jurídica" in disclaimer[0]


# ===== 6. Behavior: audit detects multiple external norms =====

def test_draft_with_multiple_external_norms_blocks_with_count():
    """Draft con varias normas externas → BLOCKED con count correcto."""
    draft = (
        "BORRADOR\n\n"
        "Con base en el artículo 29 de la Constitución Política de 1991, "
        "y la Ley 812 de 2003, artículo 81, "
        "y la Ley 1450 de 2011, artículo 5, "
        "y la Sentencia C-251/2002, "
        "solicito la protección."
    )
    exam = _build_case_with_draft(draft)
    result = exam.run()
    assert result.overall_status == "BLOCKED"
    # Should detect ≥3 external norms (Ley 812, Ley 1450, Sentencia C-251).
    assert len(result.draft_citation_defects) >= 3, (
        f"Expected ≥3 blocking defects. Got: {len(result.draft_citation_defects)}. "
        f"Defects: {result.draft_citation_defects}"
    )


# ===== 7. Audit field in as_dict() =====

def test_draft_citation_defects_field_in_as_dict():
    """LawyerExamResult.as_dict() debe incluir draft_citation_defects."""
    draft = (
        "BORRADOR\n\n"
        "Con base en el artículo 29 de la Constitución Política de 1991 "
        "y el artículo 81 de la Ley 812 de 2003, solicito la protección."
    )
    exam = _build_case_with_draft(draft)
    result = exam.run()
    d = result.as_dict()
    assert "draft_citation_defects" in d
    assert isinstance(d["draft_citation_defects"], list)


# ===== 8. Empty draft does not trigger audit =====

def test_empty_draft_does_not_trigger_audit():
    """Empty draft → step 10 already aborted → audit does not run."""
    # Use a stub that returns empty draft
    case = {
        "summary": "test",
        "facts": ["fact"],
        "legal_issues": ["issue"],
        "required_sources": [{"document": "constitucion", "article": "29"}],
        "document_type": "escrito",
    }

    class _EmptyDraftStub(_DraftControllingStubProvider):
        def __init__(self) -> None:
            super().__init__(draft_text="")

    stub = _EmptyDraftStub()
    guard = RealProviderGuard(provider=stub, role="lawyer")
    exam = LawyerExam(case_id="test-empty-draft", case_facts=case, guard=guard)
    result = exam.run()
    # Step 10 should block on empty draft (via LLM response check)
    # OR succeed if stub returns empty string but doesn't fail.
    # Either way, draft audit should not produce blocking defects
    # on an empty draft.
    # The exact overall_status depends on how step 10 handles empty text.
    # The audit itself returns early if draft is empty.
    assert len(result.draft_citation_defects) == 0, (
        f"Empty draft should not produce defects. Got: {result.draft_citation_defects}"
    )
