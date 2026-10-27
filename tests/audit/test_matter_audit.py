"""Tests del MatterAudit — JSONL append-only por matter con hash chain."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from albra.audit.matter_audit import MatterAudit


@pytest.fixture
def audit(tmp_path):
    return MatterAudit(str(tmp_path / "matters"))


def test_append_first_entry_creates_genesis_chain(audit):
    entry = audit.append(
        "m1",
        actor="abogado1",
        authority="abogado",
        action_type="matter_created",
        action_payload={"client": "X", "area": "civil"},
        result={"matter_id": "m1"},
    )
    assert entry["prev_hash"] == MatterAudit.GENESIS_HASH
    assert entry["this_hash"]
    assert entry["ts"]
    assert entry["actor"] == "abogado1"
    assert entry["authority"] == "abogado"
    assert entry["action_type"] == "matter_created"
    # File exists
    path = Path(audit.matters_dir) / "m1" / "audit.jsonl"
    assert path.exists()


def test_append_second_entry_chains_hash(audit):
    e1 = audit.append("m1", actor="a", action_type="x")
    e2 = audit.append("m1", actor="b", action_type="y")
    assert e2["prev_hash"] == e1["this_hash"]
    assert e2["this_hash"] != e1["this_hash"]


def test_verify_chain_intact(audit):
    for i in range(5):
        audit.append("m1", actor=f"actor{i}", action_type="action", action_payload={"i": i})
    result = audit.verify_chain("m1")
    assert result["ok"] is True
    assert result["total"] == 5
    assert result["broken_at"] == []
    assert result["matter_id"] == "m1"


def test_verify_chain_detects_tampering(audit):
    """Modificar un entry debe romper la cadena."""
    for i in range(5):
        audit.append("m1", actor=f"actor{i}", action_type="action", action_payload={"i": i})
    # Tampering: cambiar el segundo entry
    path = Path(audit.matters_dir) / "m1" / "audit.jsonl"
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    entry = json.loads(lines[1])
    entry["actor"] = "HACKED"
    lines[1] = json.dumps(entry, ensure_ascii=False) + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    # Reset cache para forzar releer
    audit._last_hash_cache.pop("m1", None)
    result = audit.verify_chain("m1")
    assert not result["ok"]
    assert len(result["broken_at"]) >= 1


def test_verify_chain_empty_matter_returns_ok(audit):
    result = audit.verify_chain("nonexistent-matter")
    assert result["ok"] is True
    assert result["total"] == 0


def test_read_filter_by_action_type(audit):
    audit.append("m1", actor="a", action_type="matter_created")
    audit.append("m1", actor="b", action_type="state_change")
    audit.append("m1", actor="c", action_type="state_change")
    sc = audit.read("m1", action_type="state_change")
    assert len(sc) == 2


def test_read_limit_returns_last_n(audit):
    for i in range(10):
        audit.append("m1", actor="a", action_type="action")
    last3 = audit.read("m1", limit=3)
    assert len(last3) == 3


def test_count(audit):
    assert audit.count("m1") == 0
    audit.append("m1", actor="a", action_type="x")
    audit.append("m1", actor="b", action_type="y")
    assert audit.count("m1") == 2


def test_fingerprint_stable(audit):
    audit.append("m1", actor="a", action_type="x")
    fp1 = audit.fingerprint("m1")
    fp2 = audit.fingerprint("m1")
    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256 hex


def test_fingerprint_changes_after_append(audit):
    audit.append("m1", actor="a", action_type="x")
    fp1 = audit.fingerprint("m1")
    audit.append("m1", actor="b", action_type="y")
    fp2 = audit.fingerprint("m1")
    assert fp1 != fp2


def test_export_returns_complete_picture(audit):
    audit.append("m1", actor="abogado1", authority="abogado",
                 action_type="matter_created",
                 action_payload={"client": "X"},
                 result={"state": "NUEVO"})
    export = audit.export("m1")
    assert export["matter_id"] == "m1"
    assert export["total_entries"] == 1
    assert len(export["entries"]) == 1
    assert export["verification"]["ok"] is True
    assert export["fingerprint"]
    assert export["exported_at"]


def test_jsonl_one_entry_per_line(audit):
    audit.append("m1", actor="a", action_type="x")
    audit.append("m1", actor="b", action_type="y")
    path = Path(audit.matters_dir) / "m1" / "audit.jsonl"
    with open(path, encoding="utf-8") as f:
        lines = [ln for ln in f.readlines() if ln.strip()]
    assert len(lines) == 2
    for line in lines:
        e = json.loads(line)
        assert "ts" in e
        assert "actor" in e
        assert "action_type" in e
        assert "prev_hash" in e
        assert "this_hash" in e


def test_model_field_stored(audit):
    """El campo model debe guardarse cuando un LLM participó."""
    audit.append(
        "m1", actor="research-agent", authority="agent",
        model="claude-3-opus",
        action_type="research_performed",
        action_payload={"query": "test"},
        result={"citations": []},
    )
    entries = audit.read("m1")
    assert entries[0]["model"] == "claude-3-opus"


def test_model_field_empty_when_no_llm(audit):
    audit.append("m1", actor="abogado1", authority="abogado",
                 action_type="matter_created")
    entries = audit.read("m1")
    assert entries[0]["model"] == ""


def test_independent_chains_per_matter(audit):
    """Cada matter tiene su propia cadena independiente."""
    audit.append("m1", actor="a", action_type="x")
    audit.append("m2", actor="b", action_type="y")
    audit.append("m1", actor="c", action_type="z")
    audit.append("m2", actor="d", action_type="w")

    # Verificar que m1 tiene 2 entries y m2 tiene 2 entries
    assert audit.count("m1") == 2
    assert audit.count("m2") == 2

    # Las cadenas deben verificar independientemente
    assert audit.verify_chain("m1")["ok"] is True
    assert audit.verify_chain("m2")["ok"] is True

    # El primer entry de cada matter debe tener prev_hash = GENESIS
    m1_entries = audit.read("m1")
    m2_entries = audit.read("m2")
    assert m1_entries[0]["prev_hash"] == MatterAudit.GENESIS_HASH
    assert m2_entries[0]["prev_hash"] == MatterAudit.GENESIS_HASH


def test_action_payload_with_complex_data(audit):
    """El action_payload debe soportar datos complejos (nested dicts)."""
    payload = {
        "client": {"name": "María", "id": "12345678"},
        "parties": ["Gómez", "MinSalud"],
        "deadlines": [{"label": "demanda", "date": "2026-12-01"}],
    }
    audit.append(
        "m1", actor="intake-agent", authority="agent",
        action_type="intake_completed",
        action_payload=payload,
        result={"state": "INTAKE"},
    )
    entries = audit.read("m1")
    assert entries[0]["action_payload"]["client"]["name"] == "María"
    assert len(entries[0]["action_payload"]["parties"]) == 2


def test_tampering_in_prev_hash_breaks_chain(audit):
    """Si alguien cambia el prev_hash, la cadena detecta la manipulación."""
    audit.append("m1", actor="a", action_type="x")
    audit.append("m1", actor="b", action_type="y")
    audit.append("m1", actor="c", action_type="z")

    path = Path(audit.matters_dir) / "m1" / "audit.jsonl"
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    # Modificar prev_hash del segundo entry
    entry = json.loads(lines[1])
    entry["prev_hash"] = "0" * 64  # wrong prev_hash
    lines[1] = json.dumps(entry, ensure_ascii=False) + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    audit._last_hash_cache.pop("m1", None)
    result = audit.verify_chain("m1")
    assert not result["ok"]
    # El segundo entry debe estar marcado como broken
    assert 1 in result["broken_at"]
