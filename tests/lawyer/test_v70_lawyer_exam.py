"""V7.0 tests — NVIDIA provider, RealProviderGuard, LawyerExam.

Cobertura:
  - MockProvider is_mock=True explicit
  - NVIDIA provider construction (fail-closed sin API key)
  - RealProviderGuard distinción Mock vs Real
  - LawyerExam con Mock → BLOCKED con causa explícita
  - LawyerExam sin problemas jurídicos → ABSTAINED
  - LawyerExam sin fuentes en corpus → ABSTAINED
  - Corpus lookup verification (arts. 28/30/29 IN, 49/86 OUT)
  - Live NVIDIA smoke test (skip sin NVIDIA_API_KEY)
  - Live end-to-end pilot case (skip sin NVIDIA_API_KEY)
"""
from __future__ import annotations

import os

import pytest

from albra.lawyer.exam import LawyerExam
from albra.llm.providers import MockProvider, NVIDIAProvider
from albra.llm.real_provider_guard import (
    RealProviderGuard,
    RealProviderGuardError,
)


def test_mock_provider_is_mock_true():
    m = MockProvider()
    assert m.is_mock is True
    assert m.is_external is False


def test_nvidia_without_api_key_raises(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with pytest.raises(NotImplementedError, match="NVIDIA_API_KEY"):
        NVIDIAProvider()


def test_nvidia_with_api_key_constructs(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-fake-test-key-not-real-1234567890")
    n = NVIDIAProvider()
    assert n.is_mock is False
    assert n.is_external is True
    assert n.name == "nvidia"
    assert n.default_model == "z-ai/glm-5.3-flash"
    assert n.base_url == "https://integrate.api.nvidia.com/v1"


def test_guard_rejects_mock_provider():
    mock = MockProvider()
    guard = RealProviderGuard(provider=mock, role="lawyer")
    assert guard.is_mock is True
    assert guard.is_real() is False
    with pytest.raises(RealProviderGuardError, match="Real provider required"):
        guard.require_real("test")
    state = guard.explain_state()
    assert state["verdict"] == "MOCK"


def test_guard_accepts_nvidia_real(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-fake-test-key-not-real-1234567890")
    n = NVIDIAProvider()
    guard = RealProviderGuard(provider=n, role="lawyer")
    assert guard.is_mock is False
    assert guard.is_external is True
    assert guard.is_real() is True
    guard.require_real("test")
    state = guard.explain_state()
    assert state["verdict"] == "REAL"


def test_guard_run_real_with_mock_fails():
    mock = MockProvider()
    guard = RealProviderGuard(provider=mock, role="lawyer")
    with pytest.raises(RealProviderGuardError):
        guard.run_real(prompt="test")


def test_guard_is_response_failed_detection():
    from albra.llm.providers import LLMResponse
    failed = LLMResponse(
        text="", provider="nvidia", model="x",
        metadata={"failed": True, "error_category": "transient"},
    )
    assert RealProviderGuard.is_response_failed(failed) is True
    success = LLMResponse(
        text="hello", provider="nvidia", model="x",
        metadata={"attempt": 1},
    )
    assert RealProviderGuard.is_response_failed(success) is False


def test_lawyer_exam_blocks_with_mock_provider():
    """El LawyerExam con MockProvider BLOQUEA — no cae silenciosamente."""
    case = {
        "summary": "test case",
        "facts": ["fact 1"],
        "documents": ["doc 1"],
        "uncertainties": ["unc 1"],
        "legal_issues": ["issue 1"],
        "required_sources": [
            {"document": "constitucion", "article": "28"},
        ],
        "document_type": "test",
    }
    mock = MockProvider()
    guard = RealProviderGuard(provider=mock, role="lawyer")
    exam = LawyerExam(case_id="test-mock", case_facts=case, guard=guard)
    result = exam.run()
    assert result.overall_status == "BLOCKED"
    assert "Real provider unavailable" in result.overall_reason
    # Steps 1-6 (deterministic, pre-LLM) should be recorded.
    assert len(result.steps) >= 6
    # Step 7 (strategy) is where the guard raises hard — the step may
    # or may not be recorded depending on whether the guard raised
    # before or after the LLM call. The important contract is that
    # the overall status is BLOCKED with explicit cause.


def test_lawyer_exam_abstains_without_legal_issues():
    case = {
        "summary": "no issues",
        "facts": ["fact 1"],
        "legal_issues": [],
        "required_sources": [],
    }
    mock = MockProvider()
    guard = RealProviderGuard(provider=mock, role="lawyer")
    exam = LawyerExam(case_id="test-no-issues", case_facts=case, guard=guard)
    result = exam.run()
    assert result.overall_status == "ABSTAINED"


def test_lawyer_exam_abstains_when_sources_not_in_corpus():
    case = {
        "summary": "needs art. 49 — NOT in corpus",
        "facts": ["fact"],
        "legal_issues": ["tutela salud"],
        "required_sources": [
            {"document": "constitucion", "article": "49"},
        ],
    }
    mock = MockProvider()
    guard = RealProviderGuard(provider=mock, role="lawyer")
    exam = LawyerExam(case_id="test-no-corpus", case_facts=case, guard=guard)
    result = exam.run()
    assert result.overall_status == "ABSTAINED"
    step5 = next(s for s in result.steps if s.step_number == 5)
    assert step5.status == "abstained"


def test_corpus_lookup_known_articles():
    mock = MockProvider()
    guard = RealProviderGuard(provider=mock, role="lawyer")
    exam = LawyerExam(case_id="test-lookup", case_facts={}, guard=guard)
    for art in ["28", "30", "29"]:
        found = exam._lookup_in_corpus("constitucion", art)
        assert found is not None, f"Constitución art. {art} debe estar en corpus V1.3"
        assert found["provenance_status"] == "PARTIAL"
        assert "secretariasenado.gov.co" in found["source_url"]


def test_corpus_lookup_unknown_articles():
    mock = MockProvider()
    guard = RealProviderGuard(provider=mock, role="lawyer")
    exam = LawyerExam(case_id="test-lookup2", case_facts={}, guard=guard)
    for art in ["49", "86", "380"]:
        found = exam._lookup_in_corpus("constitucion", art)
        assert found is None


def test_nvidia_live_smoke_test():
    """Live smoke test con NVIDIA NIM real. Skip en CI sin NVIDIA_API_KEY."""
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        pytest.skip("Set NVIDIA_API_KEY to run the live NVIDIA NIM smoke test")
    n = NVIDIAProvider(timeout=120.0, max_tokens=600)
    resp = n.generate(
        "Responde en español con una sola palabra: hola",
        max_tokens=200, temperature=0,
    )
    assert resp.provider == "nvidia"
    assert resp.model == "z-ai/glm-5.3-flash"
    assert resp.metadata.get("is_mock") is False
    assert resp.metadata.get("is_external") is True
    assert resp.text, f"NVIDIA response text was empty. metadata: {resp.metadata}"


def test_pilot_case_end_to_end_with_real_nvidia():
    """Caso piloto end-to-end con NVIDIA NIM real. Skip sin NVIDIA_API_KEY."""
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        pytest.skip("Set NVIDIA_API_KEY to run the live pilot case")
    n = NVIDIAProvider(timeout=180.0, max_tokens=2500)
    guard = RealProviderGuard(provider=n, role="lawyer")
    case = {
        "summary": "Habeas corpus pilot V7.0",
        "facts": [
            "Juan Perez fue detenido por policia sin orden judicial exhibida",
            "La detencion duro 72 horas sin presentacion ante juez",
            "No hubo flagrancia",
        ],
        "documents": ["denuncia inicial"],
        "uncertainties": ["no se sabe si existe orden previa"],
        "missing_documents": ["orden judicial si existe"],
        "legal_issues": [
            "Vulneracion art. 28", "Habeas corpus art. 30", "Debido proceso art. 29",
        ],
        "required_sources": [
            {"document": "constitucion", "article": "28"},
            {"document": "constitucion", "article": "30"},
            {"document": "constitucion", "article": "29"},
        ],
        "document_type": "escrito de habeas corpus",
    }
    exam = LawyerExam(case_id="pilot-live-001", case_facts=case, guard=guard)
    result = exam.run()
    assert result.overall_status == "SUCCESS", (
        f"Got: {result.overall_status}. Reason: {result.overall_reason[:200]}"
    )
    assert len(result.steps) == 12
    assert len(result.citations_verified) == 3
    assert len(result.citations_unverified) == 0
    step9 = next(s for s in result.steps if s.step_number == 9)
    assert step9.status == "abstained"
    assert result.drafted_document
    assert result.provider_state["verdict"] == "REAL"
    assert result.provider_state["provider"] == "nvidia"
