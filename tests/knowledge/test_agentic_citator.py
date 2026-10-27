"""Tests de AgenticCitator — treatment labels para jurisprudencia colombiana."""
from __future__ import annotations

import pytest

from albra.knowledge.agentic_citator import AgenticCitator


@pytest.fixture
def citator():
    return AgenticCitator()


# ===== Treatments básicos =====

def test_treatment_followed(citator):
    """Texto con keyword suave 'aplica' (en 'aplicando') → followed."""
    text = (
        "El juez aplicando el mismo criterio de la sentencia C-251/2002 "
        "resolvió el caso concreto."
    )
    result = citator.analyze(text, cited_decision_id="C-251/2002")
    assert result["treatment"] == "followed"
    assert result["confidence"] >= 0.5
    assert result["cited_decision_id"] == "C-251/2002"


def test_treatment_distinguished(citator):
    """Texto con frase fuerte 'se distinguen los hechos' → distinguished."""
    text = "En el presente caso se distinguen los hechos del caso de la sentencia T-760/2008."
    result = citator.analyze(text, cited_decision_id="T-760/2008")
    assert result["treatment"] == "distinguished"
    assert result["confidence"] == 1.0


def test_treatment_doubted(citator):
    """Texto con frase fuerte 'se expresan reservas' → doubted."""
    text = "Se expresan reservas sobre el criterio de la sentencia C-251/2002."
    result = citator.analyze(text, cited_decision_id="C-251/2002")
    assert result["treatment"] == "doubted"
    assert result["confidence"] == 1.0


def test_treatment_overruled(citator):
    """Texto con frase fuerte 'se revoca' (sin 'la decisión') → overruled."""
    text = "En esta oportunidad se revoca el criterio de la sentencia C-251/2002."
    result = citator.analyze(text, cited_decision_id="C-251/2002")
    assert result["treatment"] == "overruled"
    assert result["confidence"] == 1.0


def test_treatment_per_incuriam(citator):
    """Texto con frase fuerte 'se dictó sin consideración' → per_incuriam."""
    text = (
        "La sentencia C-251/2002 se dictó sin consideración de norma aplicable, "
        "por lo que se invoca la doctrina per incuriam."
    )
    result = citator.analyze(text, cited_decision_id="C-251/2002")
    assert result["treatment"] == "per_incuriam"
    assert result["confidence"] == 1.0


def test_treatment_affirmed(citator):
    """Texto con frase fuerte 'se confirma' → affirmed."""
    text = "Por lo tanto, se confirma la decisión de primera instancia."
    result = citator.analyze(text, cited_decision_id="C-251/2002")
    assert result["treatment"] == "affirmed"
    assert result["confidence"] == 1.0


def test_treatment_reversed(citator):
    """Texto con frase fuerte 'se revoca la decisión' → reversed (no overruled)."""
    text = "En consecuencia, se revoca la decisión impugnada."
    result = citator.analyze(text, cited_decision_id="C-251/2002")
    assert result["treatment"] == "reversed"
    assert result["confidence"] == 1.0


def test_treatment_cited_default(citator):
    """Texto sin keywords → treatment='cited', confidence=0.3."""
    text = "Sobre el particular, véase la Sentencia C-251/2002 de la Corte Constitucional."
    result = citator.analyze(text, cited_decision_id="C-251/2002")
    assert result["treatment"] == "cited"
    assert result["confidence"] == pytest.approx(0.3)


# ===== Confidence scoring =====

def test_confidence_high_for_strong_keyword(citator):
    """Patrón fuerte → confidence 1.0."""
    text = "El juez, siguiendo el criterio de la sentencia C-251/2002, resolvió."
    result = citator.analyze(text, cited_decision_id="C-251/2002")
    assert result["treatment"] == "followed"
    assert result["confidence"] == 1.0


def test_confidence_low_for_indirect_mention(citator):
    """Solo mención indirecta → confidence baja (0.4) y treatment='cited'."""
    # Texto con 'criterio' pero sin ninguna keyword fuerte o suave para followed
    text = "El criterio de la sentencia es relevante para este asunto."
    result = citator.analyze(text, cited_decision_id="C-251/2002")
    assert result["confidence"] < 0.5
    # Fail-closed: baja confianza → treatment neutro
    assert result["treatment"] == "cited"


# ===== Evidence =====

def test_evidence_extracted_from_text(citator):
    """La evidencia se extrae del texto (no vacía cuando hay match)."""
    text = (
        "El despacho, siguiendo el criterio de la sentencia C-251/2002, "
        "decide en el mismo sentido."
    )
    result = citator.analyze(text, cited_decision_id="C-251/2002")
    assert result["treatment"] == "followed"
    assert len(result["evidence"]) >= 1
    # La evidencia debe contener el match de 'siguiendo el criterio'
    found = any("siguiendo" in e.lower() for e in result["evidence"])
    assert found, f"Expected 'siguiendo' in evidence, got: {result['evidence']}"


# ===== Fail-closed =====

def test_fail_closed_when_confidence_below_threshold(citator):
    """Confidence < 0.5 → treatment='cited' (neutro)."""
    # Texto con mención indirecta pero no fuerte ni suave
    text = "El criterio aquí mencionado es relevante."
    result = citator.analyze(text, cited_decision_id="X-001/2020")
    assert result["confidence"] < 0.5
    assert result["treatment"] == "cited"
    assert "Fail-closed" in result["reason"] or "neutro" in result["reason"].lower()


# ===== Estructura del dict retornado =====

def test_analyze_returns_dict_with_all_fields(citator):
    """El dict retornado tiene los 5 campos requeridos."""
    text = "Se confirma la decisión de primera instancia."
    result = citator.analyze(text, cited_decision_id="C-100/2010")
    assert isinstance(result, dict)
    assert "cited_decision_id" in result
    assert "treatment" in result
    assert "confidence" in result
    assert "evidence" in result
    assert "reason" in result
    assert isinstance(result["cited_decision_id"], str)
    assert isinstance(result["treatment"], str)
    assert isinstance(result["confidence"], float)
    assert isinstance(result["evidence"], list)
    assert isinstance(result["reason"], str)
    assert result["cited_decision_id"] == "C-100/2010"
    assert result["treatment"] in AgenticCitator.TREATMENT_LABELS
    assert 0.0 <= result["confidence"] <= 1.0
