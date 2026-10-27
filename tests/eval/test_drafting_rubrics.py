"""Tests de los 3 drafting rubrics V2.3-A: tutela, demanda civil, contrato."""
from __future__ import annotations

import pytest

from albra.eval.drafting_rubrics import (
    contrato_corporativo_rubric,
    demanda_civil_rubric,
    tutela_rubric,
)
from albra.eval.rubrics import RubricRunner


@pytest.fixture
def strong_secrets(monkeypatch):
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-ephemeral-jwt-secret-32-chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-ephemeral-pass-1234")


@pytest.fixture
def runner(strong_secrets):
    return RubricRunner()


# ===== Fixtures: sample drafts =====

TUTELA_GOOD = """\
ACCIÓN DE TUTELA

Señor Juez de la República:
Acción de tutela por vulneración del derecho fundamental a la salud.

HECHOS
1. El accionante fue privado del tratamiento médico.
2. La entidad demandada ignoró las solicitudes.

NORMA VULNERADA
Constitución Política de 1991, artículo 13.

PRETENSIÓN
Solicito amparo constitucional y restablecimiento del tratamiento.

JURAMENTO
Manifiesto bajo la gravedad del juramento que los hechos son ciertos.

ANEXOS
Historia clínica, derecho de petición.
"""

TUTELA_MISSING_PRETENSION = """\
ACCIÓN DE TUTELA

Señor Juez de la República:
Acción de tutela por vulneración del derecho fundamental a la salud.

HECHOS
1. El accionante fue privado del tratamiento médico.

NORMA VULNERADA
Constitución Política de 1991, artículo 13.

JURAMENTO
Manifiesto bajo la gravedad del juramento.

ANEXOS
Historia clínica.
"""

TUTELA_FORBIDDEN_CLAUSE = """\
ACCIÓN DE TUTELA
derecho fundamental vulnerado, hechos, norma vulnerada, pretensión, juramento, anexos.
Incluye cláusula exorbitante que renuncia garantías.
"""

DEMANDA_CIVIL_GOOD = """\
DEMANDA CIVIL
Señor Juez Civil del Circuito:
Demandante: Juan Pérez.
Demandado: Empresa XYZ S.A.S.
HECHOS
1. Hubo contrato y se incumplió.
FUNDAMENTOS DE DERECHO
Constitución Política de 1991, artículo 29.
PRETENSIONES
Primera: declaración de incumplimiento.
PRUEBAS
Contrato, facturas.
JURAMENTO
Manifiesto bajo la gravedad del juramento que los hechos son ciertos.
"""

DEMANDA_CIVIL_RENUNCIA_DEBIDO_PROCESO = """\
DEMANDA CIVIL
Señor Juez: demandante, demandado, hechos, fundamentos de derecho,
pretensiones, pruebas, juramento.
El demandado renuncia al debido proceso.
"""

CONTRATO_GOOD = """\
CONTRATO CORPORATIVO
Las partes: Sociedad A y Sociedad B.
OBJETO DEL CONTRATO: asociación inmobiliaria.
CONTRAPRESTACIÓN: aportes según anexo.
JURISDICCIÓN: jueces de Bogotá.
LEY APLICABLE: legislación colombiana. Ley 80 de 1993.
Cámara de Comercio: registro previsto.
VIGENCIA: cinco años.
cláusulas varias.
"""

CONTRATO_FORBIDDEN_RENUNCIA_TUTELA = """\
CONTRATO CORPORATIVO
cláusulas, las partes, objeto del contrato, contraprestación, jurisdicción,
ley aplicable, vigencia.
El contratista acepta la renuncia a la acción de tutela.
"""


# ===== Tests tutela_rubric =====

def test_tutela_rubric_passes_good_draft(runner):
    result = runner.evaluate(TUTELA_GOOD, tutela_rubric)
    assert result.passed, f"missing: {result.missing_essential}; violated: {result.violated_forbidden}"
    assert "Constitución Política de 1991" in result.matched_bonus
    assert result.bonus is True


def test_tutela_rubric_fails_missing_pretension(runner):
    """Falta 'pretensión' en el draft → passed=False."""
    result = runner.evaluate(TUTELA_MISSING_PRETENSION, tutela_rubric)
    assert result.passed is False
    assert "pretensión" in result.missing_essential


def test_tutela_rubric_detects_forbidden_clause(runner):
    """Una 'cláusula exorbitante' viola forbidden → passed=False."""
    result = runner.evaluate(TUTELA_FORBIDDEN_CLAUSE, tutela_rubric)
    assert result.passed is False
    assert "cláusula exorbitante" in result.violated_forbidden


# ===== Tests demanda_civil_rubric =====

def test_demanda_civil_rubric_passes_good_draft(runner):
    result = runner.evaluate(DEMANDA_CIVIL_GOOD, demanda_civil_rubric)
    assert result.passed, f"missing: {result.missing_essential}"
    # Bonus: Constitución + artículo 29 + código general del proceso
    assert "artículo 29" in result.matched_bonus
    assert result.bonus is True


def test_demanda_civil_rubric_fails_renuncia_debido_proceso(runner):
    """'renuncia al debido proceso' viola forbidden → passed=False."""
    result = runner.evaluate(DEMANDA_CIVIL_RENUNCIA_DEBIDO_PROCESO, demanda_civil_rubric)
    assert result.passed is False
    assert "renuncia al debido proceso" in result.violated_forbidden


# ===== Tests contrato_corporativo_rubric =====

def test_contrato_corporativo_rubric_passes_good_draft(runner):
    result = runner.evaluate(CONTRATO_GOOD, contrato_corporativo_rubric)
    assert result.passed, f"missing: {result.missing_essential}"
    assert "Ley 80 de 1993" in result.matched_bonus
    assert "Cámara de Comercio" in result.matched_bonus
    assert result.bonus is True


def test_contrato_corporativo_rubric_detects_forbidden_clause(runner):
    """'renuncia a la acción de tutela' viola forbidden → passed=False."""
    result = runner.evaluate(CONTRATO_FORBIDDEN_RENUNCIA_TUTELA, contrato_corporativo_rubric)
    assert result.passed is False
    assert "renuncia a la acción de tutela" in result.violated_forbidden


# ===== Tests estructura de los 3 rubrics =====

def test_tutela_rubric_has_required_field_counts():
    """tutela_rubric: 5-8 essential, 3-5 forbidden, 2-3 bonus."""
    assert 5 <= len(tutela_rubric.essential) <= 8
    assert 3 <= len(tutela_rubric.forbidden) <= 5
    assert 2 <= len(tutela_rubric.bonus) <= 3


def test_demanda_civil_rubric_has_required_field_counts():
    assert 5 <= len(demanda_civil_rubric.essential) <= 8
    assert 3 <= len(demanda_civil_rubric.forbidden) <= 5
    assert 2 <= len(demanda_civil_rubric.bonus) <= 3


def test_contrato_corporativo_rubric_has_required_field_counts():
    assert 5 <= len(contrato_corporativo_rubric.essential) <= 8
    assert 3 <= len(contrato_corporativo_rubric.forbidden) <= 5
    assert 2 <= len(contrato_corporativo_rubric.bonus) <= 3
