"""Tests de DeterministicGuard — DeadlineGuard + ContradictionGuard."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from albra.security.deterministic_guard import (
    COLOMBIAN_DEADLINES,
    ContradictionGuard,
    DeadlineGuard,
)


@pytest.fixture
def deadline_guard():
    return DeadlineGuard()


@pytest.fixture
def contradiction_guard():
    return ContradictionGuard()


# ===== DeadlineGuard: prescripción civil 20 años =====

def test_deadline_prescripcion_civil_20_years_in_window(deadline_guard):
    """5 años dentro del plazo → ok, remaining_days > 0."""
    claim_date = datetime(2020, 1, 1)
    event_date = datetime(2025, 1, 1)  # 5 años = 1826 días aprox
    result = deadline_guard.check(
        claim_date=claim_date,
        event_date=event_date,
        deadline_type="prescripcion_civil_extracontractual",
    )
    assert result["ok"] is True
    assert result["expired"] is False
    assert result["days_elapsed"] > 0
    assert result["deadline_days"] == COLOMBIAN_DEADLINES["prescripcion_civil_extracontractual"]
    assert result["remaining_days"] > 0
    assert "Dentro del plazo" in result["reason"]


def test_deadline_prescripcion_civil_20_years_expired(deadline_guard):
    """25 años → expired, ok=False."""
    claim_date = datetime(2000, 1, 1)
    event_date = datetime(2025, 1, 1)  # 25 años
    result = deadline_guard.check(
        claim_date=claim_date,
        event_date=event_date,
        deadline_type="prescripcion_civil_extracontractual",
    )
    assert result["ok"] is False
    assert result["expired"] is True
    assert result["days_elapsed"] > result["deadline_days"]
    assert result["remaining_days"] < 0
    assert "PLAZO VENCIDO" in result["reason"]


# ===== DeadlineGuard: demanda_contestacion 15 días =====

def test_deadline_demanda_contestacion_15_days_in_window(deadline_guard):
    """10 días → ok."""
    claim_date = datetime(2024, 1, 1)
    event_date = datetime(2024, 1, 11)  # 10 días
    result = deadline_guard.check(
        claim_date=claim_date,
        event_date=event_date,
        deadline_type="demanda_contestacion",
    )
    assert result["ok"] is True
    assert result["expired"] is False
    assert result["days_elapsed"] == 10
    assert result["deadline_days"] == 15
    assert result["remaining_days"] == 5


def test_deadline_demanda_contestacion_15_days_expired(deadline_guard):
    """20 días → expired."""
    claim_date = datetime(2024, 1, 1)
    event_date = datetime(2024, 1, 21)  # 20 días
    result = deadline_guard.check(
        claim_date=claim_date,
        event_date=event_date,
        deadline_type="demanda_contestacion",
    )
    assert result["ok"] is False
    assert result["expired"] is True
    assert result["days_elapsed"] == 20
    assert result["remaining_days"] == -5


# ===== DeadlineGuard: unknown type raises =====

def test_deadline_unknown_type_raises(deadline_guard):
    """Tipo desconocido → ValueError."""
    with pytest.raises(ValueError, match="Unknown deadline_type"):
        deadline_guard.check(
            claim_date=datetime(2024, 1, 1),
            event_date=datetime(2024, 1, 10),
            deadline_type="nonexistent_deadline_type",
        )


# ===== DeadlineGuard: tutela (no prescripción) =====

def test_deadline_tutela_no_prescripcion(deadline_guard):
    """tutela_presentacion → ok=True (no término)."""
    claim_date = datetime(2020, 1, 1)
    event_date = datetime(2024, 1, 1)  # 4 años después
    result = deadline_guard.check(
        claim_date=claim_date,
        event_date=event_date,
        deadline_type="tutela_presentacion",
    )
    assert result["ok"] is True
    assert result["expired"] is False
    assert result["deadline_days"] is None
    assert result["remaining_days"] is None
    assert "término de prescripción" in result["reason"]


# ===== DeadlineGuard: remaining_days calculation =====

def test_deadline_remaining_days_calculation(deadline_guard):
    """Verifica el cálculo de remaining_days."""
    claim_date = datetime(2024, 1, 1)
    event_date = datetime(2024, 1, 8)  # 7 días
    result = deadline_guard.check(
        claim_date=claim_date,
        event_date=event_date,
        deadline_type="recursos_sentencia",  # 5 días
    )
    assert result["days_elapsed"] == 7
    assert result["deadline_days"] == 5
    assert result["remaining_days"] == 5 - 7  # = -2
    assert result["expired"] is True
    assert result["ok"] is False


def test_deadline_remaining_days_within_window(deadline_guard):
    """Cálculo para 3 días de 30 (audiencia_prueba)."""
    claim_date = datetime(2024, 1, 1)
    event_date = datetime(2024, 1, 4)  # 3 días
    result = deadline_guard.check(
        claim_date=claim_date,
        event_date=event_date,
        deadline_type="audiencia_prueba",
    )
    assert result["days_elapsed"] == 3
    assert result["deadline_days"] == 30
    assert result["remaining_days"] == 27
    assert result["ok"] is True


# ===== ContradictionGuard =====

def test_no_contradictions_simple_contract(contradiction_guard):
    """3 cláusulas compatibles → ok=True."""
    clauses = [
        {"number": "1", "text": "El contrato se celebra a TÉRMINO FIJO de 12 meses."},
        {"number": "2", "text": "El pago se realiza en PESOS colombianos."},
        {"number": "3", "text": "JURISDICCIÓN COLOMBIANA rige el presente contrato."},
    ]
    result = contradiction_guard.check(clauses)
    assert result["ok"] is True
    assert result["contradictions"] == []
    assert "Sin contradicciones" in result["reason"]


def test_contradiction_termino_indeterminado_vs_fijo(contradiction_guard):
    """Detecta TERMINO INDETERMINADO vs TERMINO FIJO."""
    clauses = [
        {"number": "1", "text": "El contrato se celebra a TÉRMINO INDETERMINADO."},
        {"number": "4", "text": "No obstante, el TÉRMINO FIJO será de 12 meses."},
    ]
    result = contradiction_guard.check(clauses)
    assert result["ok"] is False
    assert len(result["contradictions"]) == 1
    c = result["contradictions"][0]
    assert c["type"] == "termino"
    assert c["clause1"] == "1"
    assert c["clause2"] == "4"
    assert "indeterminado" in c["detail"].lower() or "fijo" in c["detail"].lower()


def test_contradiction_jurisdiccion(contradiction_guard):
    """Detecta JURISDICCIÓN COLOMBIANA vs EXTRANJERA."""
    clauses = [
        {"number": "5", "text": "JURISDICCIÓN COLOMBIANA"},
        {"number": "8", "text": "Las partes se someten a JURISDICCIÓN EXTRANJERA."},
    ]
    result = contradiction_guard.check(clauses)
    assert result["ok"] is False
    c = result["contradictions"][0]
    assert c["type"] == "jurisdiccion"
    assert c["clause1"] == "5"
    assert c["clause2"] == "8"


def test_contradiction_moneda(contradiction_guard):
    """Detecta PESOS vs DOLARES."""
    clauses = [
        {"number": "2", "text": "El pago será en PESOS."},
        {"number": "9", "text": "Las multas se calculan en DOLARES."},
    ]
    result = contradiction_guard.check(clauses)
    assert result["ok"] is False
    c = result["contradictions"][0]
    assert c["type"] == "moneda"
    assert c["clause1"] == "2"
    assert c["clause2"] == "9"


def test_contradiction_territorio(contradiction_guard):
    """Detecta EXCLUSIVAMENTE BOGOTÁ vs TERRITORIO NACIONAL."""
    clauses = [
        {"number": "3", "text": "Servicios prestados EXCLUSIVAMENTE BOGOTÁ."},
        {"number": "10", "text": "Cobertura en TERRITORIO NACIONAL."},
    ]
    result = contradiction_guard.check(clauses)
    assert result["ok"] is False
    c = result["contradictions"][0]
    assert c["type"] == "territorio"
    assert c["clause1"] == "3"
    assert c["clause2"] == "10"


def test_multiple_contradictions_returned(contradiction_guard):
    """Detecta múltiples contradicciones simultáneas."""
    clauses = [
        {"number": "1", "text": "TÉRMINO INDETERMINADO y TÉRMINO FIJO en este contrato."},
        {"number": "2", "text": "Pago en PESOS, multas en DOLARES."},
        {"number": "3", "text": "JURISDICCIÓN COLOMBIANA pero JURISDICCIÓN EXTRANJERA para disputas."},
    ]
    result = contradiction_guard.check(clauses)
    assert result["ok"] is False
    assert len(result["contradictions"]) >= 3
    types = {c["type"] for c in result["contradictions"]}
    assert "termino" in types
    assert "moneda" in types
    assert "jurisdiccion" in types


def test_empty_clauses_ok(contradiction_guard):
    """Lista vacía de cláusulas → ok=True."""
    result = contradiction_guard.check([])
    assert result["ok"] is True
    assert result["contradictions"] == []


def test_contradiction_evidence_includes_clause_numbers(contradiction_guard):
    """Las contradicciones incluyen los números de cláusula conflictivas."""
    clauses = [
        {"number": "PRIMERA", "text": "TÉRMINO INDETERMINADO."},
        {"number": "SEGUNDA", "text": "TÉRMINO FIJO."},
    ]
    result = contradiction_guard.check(clauses)
    assert result["ok"] is False
    c = result["contradictions"][0]
    assert c["clause1"] == "PRIMERA"
    assert c["clause2"] == "SEGUNDA"
    # Evidencia textual de cada lado
    assert "evidence_a" in c
    assert "evidence_b" in c
    assert "INDETERMINADO" in c["evidence_a"].upper()
    assert "FIJO" in c["evidence_b"].upper()
