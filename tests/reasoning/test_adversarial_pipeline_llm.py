"""Tests del AdversarialPipeline V2.2-C con LLMRouter inyectado (V2.3-G).

Cobertura (9 tests):
- Constructor acepta llm_router (V2.3+) y lo preserva en self._llm_router.
- RED phase: si router inyectado y LLM responde JSON válido → RedArgument
  objects desde el JSON (no rule-based).
- RED phase: si LLM responde texto no-JSON → fallback a rule-based (V2.2).
- RED phase: si LLM lanza excepción → fallback a rule-based.
- BLUE phase: si router inyectado y LLM responde JSON válido → BlueResponse
  desde el JSON.
- MAGISTRADO phase: si router inyectado y LLM responde JSON válido →
  MagistradoRuling desde el JSON.
- matter_context dict se pasa al RED prompt (V2.3+ feature).
- Backward compat: AdversarialPipeline() sin router → rule-based (sin LLM).
- get_default_router() (MockProvider, sin API key) → pipeline corre
  end-to-end (MockProvider devuelve texto no-JSON → fallback a rule-based).
"""
from __future__ import annotations

import json

import pytest

from albra.llm.router import get_default_router, reset_router
from albra.reasoning.adversarial_pipeline import (
    AdversarialPipeline,
    BlueResponse,
    MagistradoRuling,
    RedArgument,
    RedBluePipelineResult,
)


# =========================================================================
# Stub objects (duck-typed, no real LLM calls)
# =========================================================================
class _StubResponse:
    """Mimics LLMResponse.text attribute (only attribute used by pipeline)."""

    def __init__(self, text: str) -> None:
        self.text = text


class _StubLLMRouter:
    """Duck-typed stub mimicking LLMRouter.generate(prompt) -> {text: str}.

    Returns phase-specific canned JSON responses based on prompt keywords,
    so a single stub can drive RED/BLUE/MAGISTRADO phases in one pipeline run.
    Captures all prompts for assertions.
    """

    RED_KEY = "contra-argumentos estructurados"
    BLUE_KEY = "defensa estructurada"
    MAGISTRADO_KEY = "como magistrado"

    def __init__(
        self,
        *,
        red_resp: str = "[]",
        blue_resp: str = "{}",
        magistrado_resp: str = "{}",
        raise_on_call: bool = False,
    ) -> None:
        self.red_resp = red_resp
        self.blue_resp = blue_resp
        self.magistrado_resp = magistrado_resp
        self.raise_on_call = raise_on_call
        self.captured_prompts: list[str] = []

    def generate(self, prompt: str, **kwargs) -> _StubResponse:
        self.captured_prompts.append(prompt)
        if self.raise_on_call:
            raise RuntimeError("stub raise on purpose")
        p = prompt.lower()
        if self.RED_KEY in p:
            return _StubResponse(self.red_resp)
        if self.BLUE_KEY in p:
            return _StubResponse(self.blue_resp)
        if self.MAGISTRADO_KEY in p:
            return _StubResponse(self.magistrado_resp)
        return _StubResponse("{}")


# =========================================================================
# Fixtures
# =========================================================================
@pytest.fixture
def strong_secrets(monkeypatch):
    """Env vars requeridos para que Settings cargue sin crash."""
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-ephemeral-jwt-secret-32-chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-ephemeral-pass-1234")


@pytest.fixture
def draft_markdown() -> str:
    return (
        "El actor presenta demanda de tutela por vulneración de derechos "
        "fundamentales en el acceso a la salud del paciente.\n\n"
        "El demandado no cumplió con el contrato de prestación de servicios "
        "médicos requeridos por el paciente en tiempo razonable."
    )


@pytest.fixture
def matter_context() -> dict:
    return {
        "client": "Juan Pérez",
        "area": "tutela_salud",
        "parties": ["EPS Salud S.A."],
        "pretensions": ["Entrega del medicamento negado"],
    }


# =========================================================================
# Constructor + backward compat
# =========================================================================
def test_llm_router_injected_via_constructor(strong_secrets):
    """AdversarialPipeline(llm_router=stub) → stub stored on instance."""
    stub = _StubLLMRouter()
    pipeline = AdversarialPipeline(llm_router=stub)
    assert pipeline._llm_router is stub


def test_pipeline_without_llm_router_uses_rule_based(
    strong_secrets, draft_markdown
):
    """AdversarialPipeline() without llm_router → rule-based (V2.2 backward compat)."""
    pipeline = AdversarialPipeline()
    assert pipeline._llm_router is None
    result = pipeline.run(draft_markdown)
    assert isinstance(result, RedBluePipelineResult)
    # Rule-based path: at least 1 RED argument from "no cita norma" pattern
    assert len(result.red_arguments) >= 1
    for red in result.red_arguments:
        assert isinstance(red, RedArgument)
    assert len(result.blue_responses) == len(result.red_arguments)


def test_pipeline_with_llm_router_uses_mock_when_no_api_key(
    strong_secrets, draft_markdown, matter_context, monkeypatch
):
    """get_default_router() with no API key → MockProvider → pipeline runs
    end-to-end. MockProvider returns non-JSON text for RED prompt (contains
    'contra') → fallback to rule-based. Pipeline still produces RED args."""
    # Reset singleton so env var is re-read fresh.
    reset_router()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ALBRA_LLM_DEFAULT_PROVIDER", raising=False)
    router = get_default_router()
    pipeline = AdversarialPipeline(llm_router=router)
    result = pipeline.run(draft_markdown, matter_context=matter_context)
    assert isinstance(result, RedBluePipelineResult)
    # MockProvider returns non-JSON text → pipeline falls back to rule-based.
    # We still get RED arguments (from rule-based).
    assert len(result.red_arguments) >= 1
    assert len(result.blue_responses) == len(result.red_arguments)
    assert len(result.rulings) == len(result.red_arguments)
    # Cleanup singleton so other tests get a fresh router.
    reset_router()


# =========================================================================
# RED phase — LLM success + fallbacks
# =========================================================================
def test_pipeline_with_llm_router_generates_red_arguments(
    strong_secrets, draft_markdown, matter_context
):
    """LLM returns valid JSON list → RedArgument objects from JSON."""
    red_json = json.dumps(
        [
            {
                "target_clause": 0,
                "argument": "LLM-RED: el draft carece de cita normativa.",
                "evidence": ["Constitución Política de 1991, artículo 49"],
                "severity": "high",
            },
            {
                "target_clause": 1,
                "argument": "LLM-RED: omite jurisprudencia de la Corte.",
                "evidence": ["Sentencia T-760/2008"],
                "severity": "medium",
            },
        ]
    )
    stub = _StubLLMRouter(red_resp=red_json)
    pipeline = AdversarialPipeline(llm_router=stub)
    reds = pipeline._red_phase(draft_markdown, matter_context)
    assert len(reds) == 2
    assert all(isinstance(r, RedArgument) for r in reds)
    # LLM-generated content (not rule-based pattern like "no cita norma")
    assert reds[0].argument.startswith("LLM-RED")
    assert reds[0].target_clause_index == 0
    assert reds[0].severity == "high"
    assert "Constitución" in reds[0].evidence[0]
    assert reds[1].target_clause_index == 1
    assert reds[1].severity == "medium"
    # Verify LLM was actually called
    assert len(stub.captured_prompts) == 1
    assert "contra-argumentos estructurados" in stub.captured_prompts[0]


def test_pipeline_with_llm_router_passes_matter_context_to_prompt(
    strong_secrets, draft_markdown, matter_context
):
    """matter_context dict content is embedded in the RED prompt."""
    red_json = json.dumps(
        [{"target_clause": 0, "argument": "x", "evidence": [], "severity": "low"}]
    )
    stub = _StubLLMRouter(red_resp=red_json)
    pipeline = AdversarialPipeline(llm_router=stub)
    pipeline._red_phase(draft_markdown, matter_context)
    assert len(stub.captured_prompts) == 1
    prompt = stub.captured_prompts[0]
    # matter_context fields appear in prompt
    assert "Juan Pérez" in prompt
    assert "tutela_salud" in prompt
    assert "EPS Salud S.A." in prompt
    # draft content appears too
    assert "demanda de tutela" in prompt


def test_pipeline_with_llm_router_falls_back_to_rule_based_on_json_error(
    strong_secrets, draft_markdown
):
    """LLM returns non-JSON text → fallback to rule-based."""
    stub = _StubLLMRouter(red_resp="This is not JSON at all.")
    pipeline = AdversarialPipeline(llm_router=stub)
    reds = pipeline._red_phase(draft_markdown, None)
    # Fallback: rule-based path produces RED args with "no cita norma" pattern
    assert len(reds) >= 1
    # Rule-based RED argument for paragraph 0 (tutela, no cita) → high severity
    assert reds[0].severity == "high"
    assert "no cita norma" in reds[0].argument.lower()
    # Verify LLM was called (then fallback happened)
    assert len(stub.captured_prompts) == 1


def test_pipeline_with_llm_router_falls_back_to_rule_based_on_exception(
    strong_secrets, draft_markdown
):
    """LLM raises exception → fallback to rule-based."""
    stub = _StubLLMRouter(raise_on_call=True)
    pipeline = AdversarialPipeline(llm_router=stub)
    reds = pipeline._red_phase(draft_markdown, None)
    assert len(reds) >= 1
    assert reds[0].severity == "high"
    assert "no cita norma" in reds[0].argument.lower()
    # LLM was called (and raised, then we fell back)
    assert len(stub.captured_prompts) == 1


# =========================================================================
# BLUE phase — LLM success
# =========================================================================
def test_pipeline_with_llm_router_blue_phase_uses_llm(
    strong_secrets, draft_markdown
):
    """LLM returns valid JSON for BLUE phase → BlueResponse from JSON."""
    red_json = json.dumps(
        [
            {
                "target_clause": 0,
                "argument": "RED arg from LLM",
                "evidence": [],
                "severity": "high",
            }
        ]
    )
    blue_json = json.dumps(
        {
            "argument": "LLM BLUE defense with corpus citation.",
            "evidence": ["Constitución Política de 1991, artículo 13"],
            "confidence": 0.9,
        }
    )
    magistrado_json = json.dumps(
        {"ruling": "SPLIT", "reason": "default stub ruling"}
    )
    stub = _StubLLMRouter(
        red_resp=red_json,
        blue_resp=blue_json,
        magistrado_resp=magistrado_json,
    )
    pipeline = AdversarialPipeline(llm_router=stub)
    result = pipeline.run(draft_markdown)
    blues = result.blue_responses
    assert len(blues) == 1
    assert isinstance(blues[0], BlueResponse)
    # BLUE came from LLM (not rule-based patterns like "Pendiente fortalecer")
    assert blues[0].argument == "LLM BLUE defense with corpus citation."
    assert blues[0].confidence == 0.9
    assert blues[0].evidence == ["Constitución Política de 1991, artículo 13"]
    # Verify LLM was called for BLUE (prompt has BLUE key)
    blue_prompts = [
        p for p in stub.captured_prompts if "defensa estructurada" in p.lower()
    ]
    assert len(blue_prompts) == 1


# =========================================================================
# MAGISTRADO phase — LLM success
# =========================================================================
def test_pipeline_with_llm_router_magistrado_phase_uses_llm(
    strong_secrets, draft_markdown
):
    """LLM returns valid JSON for MAGISTRADO phase → MagistradoRuling from JSON."""
    red_json = json.dumps(
        [
            {
                "target_clause": 0,
                "argument": "RED arg from LLM",
                "evidence": [],
                "severity": "high",
            }
        ]
    )
    blue_json = json.dumps(
        {
            "argument": "BLUE defense from LLM.",
            "evidence": ["Constitución Política de 1991, artículo 49"],
            "confidence": 0.85,
        }
    )
    magistrado_json = json.dumps(
        {
            "ruling": "SUSTAINED",
            "reason": "LLM magistrado: BLUE citó norma con confianza alta.",
        }
    )
    stub = _StubLLMRouter(
        red_resp=red_json,
        blue_resp=blue_json,
        magistrado_resp=magistrado_json,
    )
    pipeline = AdversarialPipeline(llm_router=stub)
    result = pipeline.run(draft_markdown)
    rulings = result.rulings
    assert len(rulings) == 1
    assert isinstance(rulings[0], MagistradoRuling)
    assert rulings[0].ruling == "SUSTAINED"
    assert "LLM magistrado" in rulings[0].reason
    # Verify LLM was called for MAGISTRADO
    mag_prompts = [
        p for p in stub.captured_prompts if "como magistrado" in p.lower()
    ]
    assert len(mag_prompts) == 1


# =========================================================================
# Full chain — all LLM-generated, complete pipeline result
# =========================================================================
def test_pipeline_with_llm_router_full_chain_produces_complete_result(
    strong_secrets, draft_markdown, matter_context
):
    """Full pipeline run with LLM router → complete RedBluePipelineResult
    where all RED/BLUE/MAGISTRADO come from LLM (not rule-based)."""
    red_json = json.dumps(
        [
            {
                "target_clause": 0,
                "argument": "RED-LLM-0",
                "evidence": ["norm-1"],
                "severity": "high",
            }
        ]
    )
    blue_json = json.dumps(
        {
            "argument": "BLUE-LLM-0",
            "evidence": ["Constitución Política de 1991, artículo 49"],
            "confidence": 0.85,
        }
    )
    magistrado_json = json.dumps(
        {"ruling": "SUSTAINED", "reason": "MAGISTRADO-LLM-0"}
    )
    stub = _StubLLMRouter(
        red_resp=red_json,
        blue_resp=blue_json,
        magistrado_resp=magistrado_json,
    )
    pipeline = AdversarialPipeline(llm_router=stub)
    result = pipeline.run(draft_markdown, matter_context=matter_context)
    assert isinstance(result, RedBluePipelineResult)
    # All from LLM (not rule-based patterns)
    assert result.red_arguments[0].argument == "RED-LLM-0"
    assert result.blue_responses[0].argument == "BLUE-LLM-0"
    assert result.rulings[0].ruling == "SUSTAINED"
    assert result.rulings[0].reason == "MAGISTRADO-LLM-0"
    # All SUSTAINED → score 1.0 → PROCEED_TO_FILE
    assert result.overall_strength_score == 1.0
    assert result.recommendation == "PROCEED_TO_FILE"
    # 3 LLM calls: RED (1) + BLUE (1) + MAGISTRADO (1)
    assert len(stub.captured_prompts) == 3
