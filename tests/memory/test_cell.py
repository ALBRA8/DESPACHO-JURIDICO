"""Tests de MemoryCell — capa arquitectónica separada de memoria.

V2.4-B: Memory Cell como LAYER (no FEATURE), inspirado en NewMind
(Memory Cell NoeticOS). SQLite local + TF-IDF puro (reusando _tokenize
de V2.2-B rag_local). Cross-matter: recall NO filtra por matter_id,
solo por área opcional.

Cobertura (15 tests):
- remember: returns cell_id, persists to SQLite, multiple agents
- recall: relevant results, area filter, top-k limit, empty query,
  no-match, cross-matter (different matter_ids same area recalled)
- get_patterns: aggregates event_types, filters by area
- stats: returns counts
- forget: deletes cell, nonexistent returns False
- close: releases connection
- persistence: across connections (close + reopen same db_path)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from albra.memory.cell import MemoryCell


@pytest.fixture
def strong_secrets(monkeypatch):
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-ephemeral-jwt-secret-32-chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-ephemeral-pass-1234")


@pytest.fixture
def cell(strong_secrets, tmp_path: Path) -> MemoryCell:
    db_path = tmp_path / "memory_cell.db"
    return MemoryCell(db_path=str(db_path))


# ===== remember =====

def test_remember_returns_cell_id(cell: MemoryCell):
    """remember() devuelve un cell_id str no vacío."""
    cid = cell.remember("matter-1", "matter_pattern",
                        {"sequence": "intake->discovery->trial"},
                        area="laboral", agent="intake-agent")
    assert isinstance(cid, str)
    assert len(cid) > 0
    assert cid != ""


def test_remember_persists_to_sqlite(cell: MemoryCell, tmp_path: Path):
    """remember() inserta la fila en la tabla memory_cells."""
    cid = cell.remember(
        "matter-42", "deadline_pattern",
        {"deadline_type": "prescripcion_civil"},
        area="civil", agent="intake-agent",
    )
    # Inspección directa del SQLite subyacente (sin pasar por la clase)
    conn = sqlite3.connect(str(tmp_path / "memory_cell.db"))
    try:
        cur = conn.execute(
            "SELECT id, matter_id, area, event_type, payload_json, agent "
            "FROM memory_cells WHERE id = ?",
            (cid,),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == cid
    assert row[1] == "matter-42"
    assert row[2] == "civil"
    assert row[3] == "deadline_pattern"
    assert "prescripcion_civil" in row[4]
    assert row[5] == "intake-agent"


def test_remember_multiple_agents(cell: MemoryCell):
    """Múltiples agentes pueden capturar memorias en la misma área."""
    cid_a = cell.remember("m-1", "matter_pattern", {"seq": "intake"},
                          area="laboral", agent="intake-agent")
    cid_b = cell.remember("m-2", "matter_pattern", {"seq": "intake->review"},
                          area="laboral", agent="review-agent")
    cid_c = cell.remember("m-3", "matter_pattern", {"seq": "intake"},
                          area="laboral", agent="intake-agent")
    assert cid_a != cid_b != cid_c
    assert cid_a != cid_c
    stats = cell.stats()
    assert stats["total_cells"] == 3
    # recall recupera de ambos agentes
    hits = cell.recall("intake", k=10)
    agents_seen = {h["agent"] for h in hits}
    assert agents_seen == {"intake-agent", "review-agent"}


# ===== recall =====

def test_recall_returns_relevant(cell: MemoryCell):
    """recall recupera la celda más relevante a la query."""
    cell.remember("m-1", "matter_pattern",
                  {"sequence": "intake discovery trial"},
                  area="laboral", agent="intake-agent")
    cell.remember("m-2", "deadline_pattern",
                  {"deadline_type": "prescripcion 5 años"},
                  area="civil", agent="review-agent")
    cell.remember("m-3", "citation_pattern",
                  {"corpus": "constitucion 1991"},
                  area="constitucional", agent="research-agent")
    hits = cell.recall("prescripcion 5 años", k=5)
    assert len(hits) > 0
    top = hits[0]
    assert top["event_type"] == "deadline_pattern"
    assert top["score"] > 0.0
    assert "cell_id" in top
    assert "payload" in top
    assert "area" in top
    assert "agent" in top
    assert "created_at" in top


def test_recall_filters_by_area(cell: MemoryCell):
    """recall(area=X) solo devuelve celdas de esa área, incluso si
    otras áreas tienen tokens con overlap."""
    cell.remember("m-1", "matter_pattern",
                  {"sequence": "intake discovery laboral"},
                  area="laboral", agent="intake-agent")
    cell.remember("m-2", "matter_pattern",
                  {"sequence": "intake discovery civil"},
                  area="civil", agent="intake-agent")
    hits_laboral = cell.recall("intake discovery", k=10, area="laboral")
    assert len(hits_laboral) > 0
    for h in hits_laboral:
        assert h["area"] == "laboral"
    hits_civil = cell.recall("intake discovery", k=10, area="civil")
    assert len(hits_civil) > 0
    for h in hits_civil:
        assert h["area"] == "civil"


def test_recall_top_k_limit(cell: MemoryCell):
    """recall respeta k como máximo de resultados."""
    # Insert 6 cells with overlapping tokens so all match
    for i in range(6):
        cell.remember(
            f"m-{i}", "matter_pattern",
            {"sequence": f"intake discovery step{i}"},
            area="laboral", agent="intake-agent",
        )
    hits = cell.recall("intake discovery", k=3)
    assert len(hits) <= 3
    # All returned hits should have positive score
    for h in hits:
        assert h["score"] > 0.0


def test_recall_empty_query_returns_empty(cell: MemoryCell):
    """Query vacía o solo whitespace → []."""
    cell.remember("m-1", "matter_pattern",
                  {"sequence": "intake"}, area="laboral")
    assert cell.recall("", k=5) == []
    assert cell.recall("   ", k=5) == []


def test_recall_no_match_returns_empty(cell: MemoryCell):
    """Query con tokens fuera del vocabulario → []."""
    cell.remember("m-1", "matter_pattern",
                  {"sequence": "intake discovery"},
                  area="laboral", agent="intake-agent")
    hits = cell.recall("zzzqqqxxww gibberish nonsense", k=5)
    assert hits == []


def test_recall_cross_matter_same_area(cell: MemoryCell):
    """recall recupera de multiple matter_ids en la misma área
    (cross-matter patterns por diseño)."""
    cell.remember("m-alpha", "matter_pattern",
                  {"sequence": "intake discovery"},
                  area="laboral", agent="intake-agent")
    cell.remember("m-beta", "matter_pattern",
                  {"sequence": "intake discovery"},
                  area="laboral", agent="intake-agent")
    cell.remember("m-gamma", "matter_pattern",
                  {"sequence": "intake discovery"},
                  area="laboral", agent="intake-agent")
    hits = cell.recall("intake discovery", k=10)
    matter_ids = {h["matter_id"] for h in hits}
    assert matter_ids == {"m-alpha", "m-beta", "m-gamma"}


# ===== get_patterns =====

def test_get_patterns_aggregates_event_types(cell: MemoryCell):
    """get_patterns cuenta event_types correctamente."""
    for _ in range(3):
        cell.remember("m", "matter_pattern", {"seq": "intake"},
                      area="laboral", agent="a")
    for _ in range(2):
        cell.remember("m", "deadline_pattern", {"type": "prescripcion"},
                      area="laboral", agent="a")
    cell.remember("m", "citation_pattern", {"corpus": "c"},
                  area="laboral", agent="a")
    patterns = cell.get_patterns()
    assert patterns["event_types"]["matter_pattern"] == 3
    assert patterns["event_types"]["deadline_pattern"] == 2
    assert patterns["event_types"]["citation_pattern"] == 1
    assert patterns["total_memories"] == 6
    assert isinstance(patterns["top_areas"], list)


def test_get_patterns_filters_by_area(cell: MemoryCell):
    """get_patterns(area=X) solo cuenta celdas de esa área."""
    cell.remember("m", "matter_pattern", {"seq": "intake"},
                  area="laboral", agent="a")
    cell.remember("m", "matter_pattern", {"seq": "intake"},
                  area="laboral", agent="a")
    cell.remember("m", "deadline_pattern", {"type": "prescripcion"},
                  area="civil", agent="a")
    pat_laboral = cell.get_patterns(area="laboral")
    assert pat_laboral["event_types"]["matter_pattern"] == 2
    assert "deadline_pattern" not in pat_laboral["event_types"]
    assert pat_laboral["total_memories"] == 2
    pat_civil = cell.get_patterns(area="civil")
    assert pat_civil["event_types"]["deadline_pattern"] == 1
    assert pat_civil["total_memories"] == 1


# ===== stats =====

def test_stats_returns_counts(cell: MemoryCell):
    """stats() retorna total_cells, by_event_type, by_area, db_path."""
    cell.remember("m-1", "matter_pattern", {"s": "x"},
                  area="laboral", agent="a")
    cell.remember("m-2", "deadline_pattern", {"d": "y"},
                  area="civil", agent="b")
    cell.remember("m-3", "matter_pattern", {"s": "z"},
                  area="laboral", agent="a")
    s = cell.stats()
    assert s["total_cells"] == 3
    assert s["by_event_type"]["matter_pattern"] == 2
    assert s["by_event_type"]["deadline_pattern"] == 1
    assert s["by_area"]["laboral"] == 2
    assert s["by_area"]["civil"] == 1
    assert isinstance(s["db_path"], str)
    assert "memory_cell.db" in s["db_path"]


def test_stats_empty_cell_returns_zeros(cell: MemoryCell):
    """stats() en celda vacía: 0 cells, dicts vacíos."""
    s = cell.stats()
    assert s["total_cells"] == 0
    assert s["by_event_type"] == {}
    assert s["by_area"] == {}


# ===== forget =====

def test_forget_deletes_cell(cell: MemoryCell):
    """forget(cell_id) elimina la celda y deja de aparecer en recall/stats."""
    cid = cell.remember("m-1", "matter_pattern",
                        {"sequence": "intake"},
                        area="laboral", agent="a")
    assert cell.stats()["total_cells"] == 1
    deleted = cell.forget(cid)
    assert deleted is True
    assert cell.stats()["total_cells"] == 0
    # Y la celda ya no aparece en recall
    assert cell.recall("intake", k=5) == []


def test_forget_nonexistent_returns_false(cell: MemoryCell):
    """forget(cell_id_inexistente) devuelve False (no lanza)."""
    assert cell.forget("nonexistent-cell-id-xyz") is False


# ===== close =====

def test_close_releases_connection(cell: MemoryCell):
    """close() cierra la conexión SQLite (None) sin excepción."""
    assert cell._conn is not None
    cell.close()
    assert cell._conn is None
    # stats() en conexión cerrada retorna zeros (no crashea)
    s = cell.stats()
    assert s["total_cells"] == 0
    assert s["db_path"] != ""


# ===== persistence across connections =====

def test_persistence_across_connections(strong_secrets, tmp_path: Path):
    """Datos persisten al cerrar y reabrir la misma DB."""
    db_path = tmp_path / "memory_cell.db"
    cell1 = MemoryCell(db_path=str(db_path))
    cid = cell1.remember(
        "m-1", "matter_pattern",
        {"sequence": "intake discovery trial"},
        area="laboral", agent="intake-agent",
    )
    cell1.close()
    # Reabrir la misma DB → los datos siguen ahí
    cell2 = MemoryCell(db_path=str(db_path))
    assert cell2.stats()["total_cells"] == 1
    hits = cell2.recall("intake discovery", k=5)
    assert len(hits) == 1
    assert hits[0]["cell_id"] == cid
    assert hits[0]["area"] == "laboral"
    cell2.close()


# ===== Block L: provenance / trust / authority =====


def test_remember_with_trust_level(cell: MemoryCell):
    """remember() persiste trust_level/authority_source/provenance_ref cuando
    se pasan como kwargs y los recupera vía get_cell().
    """
    cid = cell.remember(
        "m-1", "matter_pattern",
        {"sequence": "intake discovery trial"},
        area="laboral", agent="intake-agent",
        trust_level="VERIFIED",
        authority_source="intake-agent",
        provenance_ref="cite-abc-123",
    )
    cell_data = cell.get_cell(cid)
    assert cell_data is not None
    assert cell_data["trust_level"] == "VERIFIED"
    assert cell_data["authority_source"] == "intake-agent"
    assert cell_data["provenance_ref"] == "cite-abc-123"


def test_remember_defaults_to_unverified(cell: MemoryCell):
    """remember() sin trust_level explícito → UNVERIFIED (conservative)."""
    cid = cell.remember(
        "m-1", "matter_pattern",
        {"seq": "intake"},
        area="laboral", agent="intake-agent",
    )
    cell_data = cell.get_cell(cid)
    assert cell_data is not None
    assert cell_data["trust_level"] == "UNVERIFIED"
    assert cell_data["authority_source"] == ""
    assert cell_data["provenance_ref"] == ""


def test_is_trustworthy_true_when_verified(cell: MemoryCell):
    """is_trustworthy() True solo cuando trust_level == VERIFIED."""
    cid_v = cell.remember(
        "m-1", "matter_pattern", {"s": "x"},
        area="laboral", agent="a",
        trust_level="VERIFIED", authority_source="human",
        provenance_ref="doc-1",
    )
    assert cell.is_trustworthy(cid_v) is True


def test_is_trustworthy_false_when_unverified(cell: MemoryCell):
    """is_trustworthy() False para UNVERIFIED/OBSERVATION/SPECULATIVE."""
    cid_unv = cell.remember(
        "m-1", "matter_pattern", {"s": "x"},
        area="laboral", agent="a",
        trust_level="UNVERIFIED",
    )
    cid_obs = cell.remember(
        "m-2", "matter_pattern", {"s": "y"},
        area="laboral", agent="a",
        trust_level="OBSERVATION",
    )
    cid_spec = cell.remember(
        "m-3", "matter_pattern", {"s": "z"},
        area="laboral", agent="a",
        trust_level="SPECULATIVE",
    )
    assert cell.is_trustworthy(cid_unv) is False
    assert cell.is_trustworthy(cid_obs) is False
    assert cell.is_trustworthy(cid_spec) is False


def test_authority_source_stored(cell: MemoryCell):
    """authority_source se almacena tal cual — matter_id, agent_name, o "human"."""
    cid_matter = cell.remember(
        "m-1", "matter_pattern", {"s": "x"},
        area="laboral", agent="a",
        authority_source="matter-42",
    )
    cid_agent = cell.remember(
        "m-2", "matter_pattern", {"s": "x"},
        area="laboral", agent="a",
        authority_source="research-agent",
    )
    cid_human = cell.remember(
        "m-3", "matter_pattern", {"s": "x"},
        area="laboral", agent="a",
        authority_source="human",
    )
    assert cell.get_cell(cid_matter)["authority_source"] == "matter-42"
    assert cell.get_cell(cid_agent)["authority_source"] == "research-agent"
    assert cell.get_cell(cid_human)["authority_source"] == "human"


def test_is_trustworthy_false_for_nonexistent(cell: MemoryCell):
    """is_trustworthy() False cuando el cell_id no existe (no crash)."""
    assert cell.is_trustworthy("nonexistent-cell-xyz") is False


def test_remember_invalid_trust_level_raises(cell: MemoryCell):
    """remember() con trust_level inválido → ValueError."""
    with pytest.raises(ValueError):
        cell.remember(
            "m-1", "matter_pattern", {"s": "x"},
            area="laboral", agent="a",
            trust_level="BogusLevel",
        )


def test_recall_returns_provenance_fields(cell: MemoryCell):
    """recall() ahora retorna trust_level/authority_source/provenance_ref."""
    cell.remember(
        "m-1", "matter_pattern", {"sequence": "intake discovery trial"},
        area="laboral", agent="intake-agent",
        trust_level="VERIFIED", authority_source="intake-agent",
        provenance_ref="doc-001",
    )
    hits = cell.recall("intake discovery", k=5)
    assert len(hits) == 1
    h = hits[0]
    assert h["trust_level"] == "VERIFIED"
    assert h["authority_source"] == "intake-agent"
    assert h["provenance_ref"] == "doc-001"
