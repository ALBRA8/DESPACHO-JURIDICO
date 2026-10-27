"""Tests del RubricRunner + Rubric/RubricResult dataclasses (V2.3-A)."""
from __future__ import annotations

import pytest

from albra.eval.rubrics import Rubric, RubricResult, RubricRunner


@pytest.fixture
def strong_secrets(monkeypatch):
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-ephemeral-jwt-secret-32-chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-ephemeral-pass-1234")


@pytest.fixture
def runner(strong_secrets):
    return RubricRunner()


# ===== Rubric dataclass =====

def test_rubric_default_factory_creates_empty_lists(strong_secrets):
    """Rubric sin listas crea essential/forbidden/bonus vacías por defecto."""
    r = Rubric(name="x")
    assert r.essential == []
    assert r.forbidden == []
    assert r.bonus == []


def test_rubric_as_dict_exposes_all_fields(strong_secrets):
    r = Rubric(name="t", essential=["a"], forbidden=["b"], bonus=["c"])
    d = r.as_dict()
    assert d["name"] == "t"
    assert d["essential"] == ["a"]
    assert d["forbidden"] == ["b"]
    assert d["bonus"] == ["c"]


def test_rubric_result_as_dict_exposes_all_fields(strong_secrets):
    r = RubricResult(
        rubric_name="t",
        passed=True,
        bonus=True,
        missing_essential=[],
        violated_forbidden=[],
        matched_bonus=["c"],
        reason="ok",
    )
    d = r.as_dict()
    assert d["rubric_name"] == "t"
    assert d["passed"] is True
    assert d["bonus"] is True
    assert d["matched_bonus"] == ["c"]
    assert d["reason"] == "ok"


# ===== evaluate() — PASS / FAIL / BONUS =====

def test_rubric_pass_when_all_essential_and_no_forbidden(runner):
    """Si todos los essential están y ningún forbidden → passed=True, bonus=False."""
    r = Rubric(
        name="t",
        essential=["foo", "bar"],
        forbidden=["baz"],
        bonus=["qux"],
    )
    text = "foo is here and bar too"
    result = runner.evaluate(text, r)
    assert result.passed is True
    assert result.bonus is False
    assert result.missing_essential == []
    assert result.violated_forbidden == []
    assert result.matched_bonus == []


def test_rubric_fail_when_missing_essential(runner):
    """Si falta al menos 1 essential → passed=False."""
    r = Rubric(name="t", essential=["foo", "bar"])
    text = "foo is here"
    result = runner.evaluate(text, r)
    assert result.passed is False
    assert result.bonus is False
    assert "bar" in result.missing_essential
    assert "foo" not in result.missing_essential


def test_rubric_fail_when_forbidden_present(runner):
    """Si aparece al menos 1 forbidden → passed=False."""
    r = Rubric(name="t", essential=["foo"], forbidden=["bad", "worse"])
    text = "foo is here and bad too"
    result = runner.evaluate(text, r)
    assert result.passed is False
    assert result.bonus is False
    assert "bad" in result.violated_forbidden
    assert "worse" not in result.violated_forbidden


def test_rubric_bonus_when_pass_and_bonus_matched(runner):
    """Si passed=True y al menos 1 bonus → bonus=True."""
    r = Rubric(name="t", essential=["foo"], forbidden=["bad"], bonus=["extra1", "extra2"])
    text = "foo is here and extra2 present"
    result = runner.evaluate(text, r)
    assert result.passed is True
    assert result.bonus is True
    assert "extra2" in result.matched_bonus
    assert "extra1" not in result.matched_bonus


def test_rubric_no_bonus_when_not_passed(runner):
    """Si passed=False, bonus debe ser False aunque bonus esté presente."""
    r = Rubric(name="t", essential=["missing"], forbidden=[], bonus=["extra"])
    text = "extra is present"
    result = runner.evaluate(text, r)
    assert result.passed is False
    assert result.bonus is False
    assert "extra" in result.matched_bonus  # matched pero no califica


# ===== Case-insensitive matching =====

def test_rubric_case_insensitive_matching(runner):
    """Case-insensitive: 'Foo' en texto y 'foo' en essential deben matchear.
    Forbidden 'BAD' no debe matchear 'good' (sin 'bad' como substring)."""
    r = Rubric(name="t", essential=["FOO", "Bar"], forbidden=["BAD"])
    text = "this has foo and BAR and good stuff"
    result = runner.evaluate(text, r)
    assert result.passed is True
    assert result.violated_forbidden == []


def test_rubric_substring_matching(runner):
    """El match es substring, no palabra completa."""
    r = Rubric(name="t", essential=["Estado"])
    text = "El Estado social de derecho"
    result = runner.evaluate(text, r)
    assert result.passed is True


def test_rubric_reason_includes_missing_when_fails(runner):
    """reason describe qué essential falta."""
    r = Rubric(name="t", essential=["foo", "bar"])
    text = "foo is here"
    result = runner.evaluate(text, r)
    assert "missing" in result.reason
    assert "bar" in result.reason


def test_rubric_reason_includes_forbidden_when_violated(runner):
    """reason describe qué forbidden se violó."""
    r = Rubric(name="t", essential=["foo"], forbidden=["bad"])
    text = "foo and bad"
    result = runner.evaluate(text, r)
    assert "violated" in result.reason
    assert "bad" in result.reason


# ===== evaluate_all + summary =====

def test_rubric_evaluate_all_returns_per_rubric(runner):
    """evaluate_all devuelve un result por cada rubric en orden."""
    r1 = Rubric(name="r1", essential=["a"])
    r2 = Rubric(name="r2", essential=["b"])
    text = "a b"
    results = runner.evaluate_all(text, [r1, r2])
    assert len(results) == 2
    assert results[0].rubric_name == "r1"
    assert results[1].rubric_name == "r2"
    assert all(r.passed for r in results)


def test_rubric_summary_calculates_rates(runner):
    """summary() devuelve total/passed/bonus/failed/pass_rate/bonus_rate."""
    rubrics = [
        Rubric(name="r1", essential=["a"], forbidden=[], bonus=[]),  # passed, no bonus
        Rubric(name="r2", essential=["b"], forbidden=[], bonus=[]),  # passed
        Rubric(name="r3", essential=["z"], forbidden=[], bonus=[]),  # failed (z not in text)
    ]
    text = "a b"
    results = runner.evaluate_all(text, rubrics)
    s = runner.summary(results)
    assert s["total"] == 3
    assert s["passed"] == 2
    assert s["bonus"] == 0
    assert s["failed"] == 1
    assert s["pass_rate"] == 2 / 3
    assert s["bonus_rate"] == 0.0


def test_rubric_summary_empty_returns_zero_rates(runner):
    """summary() sobre lista vacía devuelve rates 0.0 sin dividir por cero."""
    s = runner.summary([])
    assert s["total"] == 0
    assert s["passed"] == 0
    assert s["bonus"] == 0
    assert s["failed"] == 0
    assert s["pass_rate"] == 0.0
    assert s["bonus_rate"] == 0.0


def test_rubric_summary_with_bonus(runner):
    """summary cuenta bonus_count correctamente."""
    rubrics = [
        Rubric(name="r1", essential=["a"], forbidden=[], bonus=["x"]),
        Rubric(name="r2", essential=["b"], forbidden=[], bonus=["y"]),
    ]
    text = "a b x y"
    results = runner.evaluate_all(text, rubrics)
    s = runner.summary(results)
    assert s["passed"] == 2
    assert s["bonus"] == 2
    assert s["pass_rate"] == 1.0
    assert s["bonus_rate"] == 1.0


def test_rubric_evaluate_multiple_rubrics_independent(runner):
    """evaluate_all no comparte estado entre rubrics."""
    r1 = Rubric(name="r1", essential=["a"], forbidden=["z"])
    r2 = Rubric(name="r2", essential=["z"], forbidden=[])
    text = "a z"
    results = runner.evaluate_all(text, [r1, r2])
    assert results[0].passed is False  # r1 tiene forbidden z
    assert results[1].passed is True  # r2 essential z presente


def test_rubric_evaluate_empty_text_fails_when_essential(runner):
    """Texto vacío con essential falla."""
    r = Rubric(name="t", essential=["foo"])
    result = runner.evaluate("", r)
    assert result.passed is False
    assert "foo" in result.missing_essential


def test_rubric_evaluate_empty_text_passes_when_no_essential(runner):
    """Texto vacío sin essential pasa (vacuously)."""
    r = Rubric(name="t", essential=[], forbidden=["bad"], bonus=[])
    result = runner.evaluate("", r)
    assert result.passed is True
    assert result.bonus is False
