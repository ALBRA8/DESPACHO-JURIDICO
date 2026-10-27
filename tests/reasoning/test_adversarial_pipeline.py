"""Tests del AdversarialPipeline RED→BLUE→MAGISTRADO (V2.2-C).

Cobertura (15 tests):
- RED phase: genera argumentos por párrafo sustantivo, salta cortos,
  asigna severity high/medium según claim + cita.
- BLUE phase: 1 respuesta por RED, cita corpus cuando encuentra norma,
  baja confianza cuando no match.
- MAGISTRADO: SUSTAINED / OVERRULED / SPLIT según (confidence, evidence).
- Recommendation: PROCEED / RETRADE / ABANDON según score.
- Pipeline completo: as_dict tiene todos los campos, empty draft → vacío.
"""
from __future__ import annotations

import pytest

from albra.reasoning.adversarial_pipeline import (
    AdversarialPipeline,
    BlueResponse,
    MagistradoRuling,
    RedArgument,
    RedBluePipelineResult,
)


# =========================================================================
# Fixtures
# =========================================================================
@pytest.fixture
def strong_secrets(monkeypatch):
    """Env vars requeridos para que Settings cargue sin crash."""
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-ephemeral-jwt-secret-32-chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-ephemeral-pass-1234")


@pytest.fixture
def pipeline(strong_secrets):
    return AdversarialPipeline()


# =========================================================================
# RED phase
# =========================================================================
def test_red_phase_generates_arguments_per_substantive_paragraph(pipeline):
    """Draft con 3 párrafos sustantivos → 3 RED arguments (1 por párrafo)."""
    draft = (
        "El actor presenta la demanda de tutela por vulneración de derechos.\n\n"
        "El demandado no cumplió con el contrato de prestación de servicios.\n\n"
        "Solicita amparo constitucional y protección del derecho fundamental."
    )
    args = pipeline._red_phase(draft, None)
    assert len(args) == 3
    for a in args:
        assert isinstance(a, RedArgument)
        assert a.role == "red"
        assert len(a.id) > 0
        assert a.argument
        assert a.severity in ("low", "medium", "high")
    # target_clause_index debe apuntar a 0, 1, 2
    indices = sorted(a.target_clause_index for a in args)
    assert indices == [0, 1, 2]


def test_red_phase_skips_short_paragraphs(pipeline):
    """Párrafos < 50 chars se ignoran (no generan RED argument)."""
    draft = (
        "Corto.\n\n"
        "Este párrafo es sustantivo y suficientemente largo para ser atacado "
        "por el pipeline adversarial sin problema de longitud."
    )
    args = pipeline._red_phase(draft, None)
    # Solo 1 RED argument: el segundo párrafo
    assert len(args) == 1
    assert args[0].target_clause_index == 1


def test_red_phase_assigns_high_severity_for_legal_claims_without_citation(
    pipeline,
):
    """Párrafo con 'demanda'/'tutela' y sin cita → severity 'high'."""
    draft = (
        "Mediante la presente demanda de tutela, el actor solicita la "
        "protección inmediata de sus derechos fundamentales vulnerados."
    )
    args = pipeline._red_phase(draft, None)
    assert len(args) == 1
    assert args[0].severity == "high"
    assert "no cita norma" in args[0].argument.lower()


def test_red_phase_assigns_medium_severity_for_claims_without_evidence(
    pipeline,
):
    """Párrafo con afirmación pero sin cita verificable → severity 'medium'."""
    # Draft sin LEGAL_CLAIM_TERMS (demanda/tutela/acción/pretensión/pretende/solicita)
    # pero con ASSERTION_TERMS (afirma/establece/derecho) y sin cita → medium
    draft = (
        "El actor afirma que se vulneraron sus derechos y establece un "
        "reclamo sin respaldo normativo en el texto del borrador jurídico."
    )
    args = pipeline._red_phase(draft, None)
    assert len(args) == 1
    assert args[0].severity == "medium"
    assert "sin evidencia" in args[0].argument.lower()


# =========================================================================
# BLUE phase
# =========================================================================
def test_blue_phase_generates_response_per_red(pipeline):
    """1 BLUE response por cada RED argument (responds_to matching)."""
    draft = (
        "El actor presenta demanda de tutela por vulneración de derechos.\n\n"
        "El demandado no cumplió con el contrato de prestación de servicios.\n\n"
        "Solicita amparo constitucional y protección del derecho fundamental."
    )
    reds = pipeline._red_phase(draft, None)
    blues = pipeline._blue_phase(draft, reds)
    assert len(blues) == len(reds)
    for b in blues:
        assert isinstance(b, BlueResponse)
        assert b.role == "blue"
        assert b.responds_to in {r.id for r in reds}
        assert 0.0 <= b.confidence <= 1.0


def test_blue_phase_cites_corpus_when_possible(pipeline):
    """Si RED dice 'no cita norma' y RAG encuentra match → BLUE cita corpus."""
    # Párrafo sobre discriminación por sexo/raza → Constitución art 13
    draft = (
        "El actor es víctima de discriminación por razones de sexo y raza "
        "en el acceso al empleo público del Estado colombiano."
    )
    reds = pipeline._red_phase(draft, None)
    assert len(reds) == 1
    assert "no cita norma" in reds[0].argument.lower()
    blues = pipeline._blue_phase(draft, reds)
    assert len(blues) == 1
    b = blues[0]
    assert b.confidence == 0.8
    assert len(b.evidence) >= 1
    # La evidencia debe mencionar Constitución o un artículo del corpus
    cite_str = b.evidence[0].lower()
    assert "constitución" in cite_str or "ley" in cite_str


def test_blue_phase_low_confidence_when_no_corpus_match(pipeline):
    """Párrafo fuera del corpus V1.1 → BLUE confidence 0.4 y sin evidence."""
    # Tema ajeno al corpus (astrofísica): RAG no encontrará match
    draft = (
        "El fenómeno astrofísico de agujeros negros supermasivos galácticos "
        "sigue estudiándose en observatorios contemporáneos australes."
    )
    reds = pipeline._red_phase(draft, None)
    assert len(reds) == 1
    blues = pipeline._blue_phase(draft, reds)
    assert len(blues) == 1
    b = blues[0]
    assert b.confidence == 0.4
    assert b.evidence == []
    assert "pendiente" in b.argument.lower()


# =========================================================================
# MAGISTRADO phase
# =========================================================================
def test_magistrado_sustained_when_blue_confidence_high_and_evidence(pipeline):
    """BLUE confidence >= 0.7 y evidence no vacía → SUSTAINED."""
    red = RedArgument(
        id="red-1",
        target_clause_index=0,
        argument="El párrafo 0 no cita norma específica.",
    )
    blue = BlueResponse(
        id="blue-1",
        responds_to="red-1",
        argument="La norma aplicable es Constitución Política de 1991, artículo 13.",
        evidence=["Constitución Política de 1991, artículo 13"],
        confidence=0.8,
    )
    rulings = pipeline._magistrado_phase([red], [blue])
    assert len(rulings) == 1
    assert rulings[0].ruling == "SUSTAINED"
    assert rulings[0].red_argument_id == "red-1"
    assert rulings[0].blue_response_id == "blue-1"


def test_magistrado_overruled_when_blue_confidence_low(pipeline):
    """BLUE confidence < 0.4 → OVERRULED (RED argument prevalece)."""
    red = RedArgument(
        id="red-1",
        target_clause_index=0,
        argument="El párrafo 0 no cita norma específica.",
    )
    blue = BlueResponse(
        id="blue-1",
        responds_to="red-1",
        argument="Pendiente fortalecer — no se identificó norma aplicable.",
        evidence=[],
        confidence=0.3,
    )
    rulings = pipeline._magistrado_phase([red], [blue])
    assert len(rulings) == 1
    assert rulings[0].ruling == "OVERRULED"


def test_magistrado_split_intermediate(pipeline):
    """BLUE confidence intermedia (0.4-0.7) con evidence → SPLIT."""
    red = RedArgument(
        id="red-1",
        target_clause_index=0,
        argument="El párrafo 0 no cita norma específica.",
    )
    blue = BlueResponse(
        id="blue-1",
        responds_to="red-1",
        argument="Defensa parcial con referencia genérica al corpus.",
        evidence=["Constitución Política de 1991"],
        confidence=0.5,
    )
    rulings = pipeline._magistrado_phase([red], [blue])
    assert len(rulings) == 1
    assert rulings[0].ruling == "SPLIT"


# =========================================================================
# Recommendation
# =========================================================================
def test_recommend_proceed_when_score_high(pipeline):
    """score = 1.0 (all SUSTAINED) → PROCEED_TO_FILE."""
    rulings = [
        MagistradoRuling("red-1", "blue-1", "SUSTAINED"),
        MagistradoRuling("red-2", "blue-2", "SUSTAINED"),
    ]
    score, rec = pipeline._recommend(rulings)
    assert score == 1.0
    assert rec == "PROCEED_TO_FILE"


def test_recommend_retrade_when_score_medium(pipeline):
    """score = 0.5 (1 SUSTAINED de 2) → RETRADE."""
    rulings = [
        MagistradoRuling("red-1", "blue-1", "SUSTAINED"),
        MagistradoRuling("red-2", "blue-2", "OVERRULED"),
    ]
    score, rec = pipeline._recommend(rulings)
    assert 0.3 <= score < 0.7
    assert rec == "RETRADE"


def test_recommend_abandon_when_score_low(pipeline):
    """score = 0.0 (all OVERRULED) → ABANDON."""
    rulings = [
        MagistradoRuling("red-1", "blue-1", "OVERRULED"),
        MagistradoRuling("red-2", "blue-2", "OVERRULED"),
    ]
    score, rec = pipeline._recommend(rulings)
    assert score < 0.3
    assert rec == "ABANDON"


# =========================================================================
# Pipeline completo
# =========================================================================
def test_pipeline_result_has_all_fields(pipeline):
    """RedBluePipelineResult.as_dict() expone todos los campos requeridos."""
    draft = (
        "El actor presenta demanda de tutela por vulneración de derechos.\n\n"
        "El demandado no cumplió con el contrato de prestación de servicios."
    )
    result = pipeline.run(draft)
    assert isinstance(result, RedBluePipelineResult)
    d = result.as_dict()
    expected_keys = {
        "red_arguments",
        "blue_responses",
        "rulings",
        "overall_strength_score",
        "recommendation",
        "draft_summary",
    }
    assert set(d.keys()) == expected_keys
    # Invariants
    assert len(result.red_arguments) == len(result.blue_responses)
    assert len(result.blue_responses) == len(result.rulings)
    assert 0.0 <= result.overall_strength_score <= 1.0
    assert result.recommendation in (
        "PROCEED_TO_FILE",
        "RETRADE",
        "ABANDON",
    )
    assert result.draft_summary


def test_pipeline_with_empty_draft_returns_empty_result(pipeline):
    """Draft vacío → resultado vacío con score 1.0 y PROCEED_TO_FILE."""
    result = pipeline.run("")
    assert isinstance(result, RedBluePipelineResult)
    assert result.red_arguments == []
    assert result.blue_responses == []
    assert result.rulings == []
    assert result.overall_strength_score == 1.0
    assert result.recommendation == "PROCEED_TO_FILE"
    assert "empty" in result.draft_summary.lower()
