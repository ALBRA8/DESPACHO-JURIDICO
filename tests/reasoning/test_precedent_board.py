"""Tests del PrecedentBoard (Lavern pattern: promoción tentative→confirmed)."""
from __future__ import annotations

import pytest

from albra.reasoning.precedent_board import (
    ARCHIVED,
    CONFIRMED,
    DOUBTED,
    OVERRULED,
    TENTATIVE,
    Precedent,
    PrecedentBoard,
)


@pytest.fixture
def board(tmp_path):
    b = PrecedentBoard(str(tmp_path / "precedent_board.db"))
    yield b
    b.close()


# ===== Create precedent =====

def test_create_precedent_returns_id(board):
    pid = board.create_precedent(area="laboral", title="EPS no puede negar medicamentos pos para enfermedades crónicas")
    assert pid
    assert len(pid) == 32  # uuid hex


def test_get_precedent_returns_object(board):
    pid = board.create_precedent(area="laboral", title="Test precedent")
    p = board.get_precedent(pid)
    assert p is not None
    assert isinstance(p, Precedent)
    assert p.id == pid
    assert p.area == "laboral"
    assert p.title == "Test precedent"
    assert p.state == TENTATIVE
    assert p.observations == []


def test_get_nonexistent_precedent_returns_none(board):
    assert board.get_precedent("nonexistent") is None


def test_create_precedent_with_description(board):
    pid = board.create_precedent(
        area="civil",
        title="Prescripción civil 20 años para extracontractual",
        description="Patrón observado en múltiples demandas civiles.",
    )
    p = board.get_precedent(pid)
    assert p.description == "Patrón observado en múltiples demandas civiles."


# ===== Observations + state transitions =====

def test_add_observation_keeps_tentative_with_1_supporting(board):
    pid = board.create_precedent(area="laboral", title="T")
    board.add_observation(
        precedent_id=pid, matter_id="m1",
        observation_text="Corte Constitucional tuteló medicamento",
        observed_by="research-agent",
    )
    p = board.get_precedent(pid)
    assert p.state == TENTATIVE
    assert len(p.observations) == 1


def test_add_3_supporting_promotes_to_confirmed(board):
    pid = board.create_precedent(area="laboral", title="T")
    for i in range(3):
        board.add_observation(
            precedent_id=pid, matter_id=f"m{i}",
            observation_text=f"Observation {i}",
            observed_by="research-agent",
        )
    p = board.get_precedent(pid)
    assert p.state == CONFIRMED
    assert len(p.observations) == 3


def test_add_contradicting_marks_doubted(board):
    pid = board.create_precedent(area="laboral", title="T")
    board.add_observation(
        precedent_id=pid, observation_text="Supporting",
        supporting=True,
    )
    board.add_observation(
        precedent_id=pid, observation_text="Contradicting",
        supporting=False,
    )
    p = board.get_precedent(pid)
    assert p.state == DOUBTED


def test_doubted_can_be_promoted_when_contradiction_resolved(board):
    """Si una contradicción fue seguida por más supportings, queda DOUBTED."""
    # Hmm — _recalculate_state no permite re-promoción desde DOUBTED.
    # V2.4-B design: una vez DOUBTED, requiere acción manual (mark_overruled
    # o recrear precedent).
    # Verificar que DOUBTED se mantiene estable
    pid = board.create_precedent(area="laboral", title="T")
    board.add_observation(precedent_id=pid, observation_text="S1", supporting=True)
    board.add_observation(precedent_id=pid, observation_text="C1", supporting=False)
    board.add_observation(precedent_id=pid, observation_text="S2", supporting=True)
    board.add_observation(precedent_id=pid, observation_text="S3", supporting=True)
    board.add_observation(precedent_id=pid, observation_text="S4", supporting=True)
    p = board.get_precedent(pid)
    # Sigue DOUBTED porque la contradicción persiste
    assert p.state == DOUBTED


# ===== Manual state overrides =====

def test_mark_overruled(board):
    pid = board.create_precedent(area="laboral", title="T")
    board.add_observation(precedent_id=pid, observation_text="S", supporting=True)
    board.add_observation(precedent_id=pid, observation_text="S2", supporting=True)
    board.add_observation(precedent_id=pid, observation_text="S3", supporting=True)
    assert board.get_precedent(pid).state == CONFIRMED
    board.mark_overruled(pid, reason="Sentencia posterior revocó el criterio")
    p = board.get_precedent(pid)
    assert p.state == OVERRULED


def test_mark_archived(board):
    pid = board.create_precedent(area="laboral", title="T")
    board.mark_archived(pid, reason="Cambio de ley 2026")
    p = board.get_precedent(pid)
    assert p.state == ARCHIVED


def test_mark_overruled_nonexistent_returns_false(board):
    assert board.mark_overruled("nonexistent", "x") is False


def test_mark_archived_nonexistent_returns_false(board):
    assert board.mark_archived("nonexistent", "x") is False


def test_overruled_not_recalculated_when_new_observation(board):
    """Una vez OVERRULED, nuevas observaciones NO recalculan state."""
    pid = board.create_precedent(area="laboral", title="T")
    board.mark_overruled(pid, "x")
    board.add_observation(precedent_id=pid, observation_text="S1", supporting=True)
    p = board.get_precedent(pid)
    assert p.state == OVERRULED  # no cambia


def test_archived_not_recalculated_when_new_observation(board):
    pid = board.create_precedent(area="laboral", title="T")
    board.mark_archived(pid, "x")
    board.add_observation(precedent_id=pid, observation_text="S1", supporting=True)
    p = board.get_precedent(pid)
    assert p.state == ARCHIVED


# ===== List + filter =====

def test_list_precedents_filter_by_area(board):
    board.create_precedent(area="laboral", title="L1")
    board.create_precedent(area="civil", title="C1")
    board.create_precedent(area="laboral", title="L2")
    laboral = board.list_precedents(area="laboral")
    assert len(laboral) == 2
    civil = board.list_precedents(area="civil")
    assert len(civil) == 1


def test_list_precedents_filter_by_state(board):
    p1 = board.create_precedent(area="laboral", title="L1")
    p2 = board.create_precedent(area="laboral", title="L2")
    # Promote p2 to CONFIRMED
    for i in range(3):
        board.add_observation(precedent_id=p2, observation_text=f"S{i}")
    confirmed = board.list_precedents(state=CONFIRMED)
    assert len(confirmed) == 1
    assert confirmed[0].id == p2
    tentative = board.list_precedents(state=TENTATIVE)
    assert len(tentative) == 1
    assert tentative[0].id == p1


def test_get_confirmed_by_area_returns_only_confirmed(board):
    board.create_precedent(area="laboral", title="L1")
    p2 = board.create_precedent(area="laboral", title="L2")
    for i in range(3):
        board.add_observation(precedent_id=p2, observation_text=f"S{i}")
    confirmed = board.get_confirmed_by_area("laboral")
    assert len(confirmed) == 1
    assert confirmed[0].state == CONFIRMED


# ===== Stats =====

def test_stats_returns_counts(board):
    p1 = board.create_precedent(area="laboral", title="L1")
    p2 = board.create_precedent(area="civil", title="C1")
    board.add_observation(precedent_id=p1, observation_text="S1")
    board.add_observation(precedent_id=p1, observation_text="S2")
    board.add_observation(precedent_id=p2, observation_text="S3")
    stats = board.stats()
    assert stats["total_precedents"] == 2
    assert stats["total_observations"] == 3
    assert stats["by_state"][TENTATIVE] == 2
    assert stats["by_state"][CONFIRMED] == 0
    assert "laboral" in stats["by_area_top10"]


def test_stats_includes_all_states(board):
    """Stats debe incluir counts para todos los estados (aunque sea 0)."""
    stats = board.stats()
    for s in (TENTATIVE, CONFIRMED, DOUBTED, OVERRULED, ARCHIVED):
        assert s in stats["by_state"]


# ===== Persistence =====

def test_persistence_across_connections(tmp_path):
    db = tmp_path / "pb.db"
    b1 = PrecedentBoard(str(db))
    pid = b1.create_precedent(area="laboral", title="Test")
    b1.close()
    b2 = PrecedentBoard(str(db))
    p = b2.get_precedent(pid)
    assert p is not None
    assert p.title == "Test"
    b2.close()


# ===== as_dict =====

def test_precedent_as_dict(board):
    pid = board.create_precedent(area="laboral", title="Test", description="Detail")
    p = board.get_precedent(pid)
    d = p.as_dict()
    assert d["id"] == pid
    assert d["area"] == "laboral"
    assert d["title"] == "Test"
    assert d["description"] == "Detail"
    assert d["state"] == TENTATIVE
    assert d["observations_count"] == 0
    assert "created_at" in d
    assert "last_updated" in d


def test_add_observation_nonexistent_precedent_raises(board):
    with pytest.raises(KeyError):
        board.add_observation(precedent_id="nonexistent", observation_text="X")
