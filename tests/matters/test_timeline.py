"""Tests del MatterTimeline JSONL append-only."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from albra.matters.timeline import MatterTimeline


@pytest.fixture
def timeline(tmp_path):
    return MatterTimeline(str(tmp_path / "matters"))


def test_append_and_read(timeline):
    e = timeline.append(
        "matter-1",
        actor="abogado1",
        event_type="created",
        description="Matter creado para X",
    )
    assert e["actor"] == "abogado1"
    assert e["event_type"] == "created"
    assert e["ts"]
    # File exists
    path = Path(timeline.matters_dir) / "matter-1" / "timeline.jsonl"
    assert path.exists()
    events = timeline.read("matter-1")
    assert len(events) == 1
    assert events[0]["actor"] == "abogado1"


def test_read_empty_for_unknown_matter(timeline):
    assert timeline.read("nonexistent") == []
    assert timeline.count("nonexistent") == 0


def test_filter_by_event_type(timeline):
    timeline.append("m1", actor="a", event_type="created", description="x")
    timeline.append("m1", actor="b", event_type="state_change", description="y")
    timeline.append("m1", actor="c", event_type="state_change", description="z")
    sc = timeline.read("m1", event_type="state_change")
    assert len(sc) == 2
    assert sc[0]["description"] == "y"
    assert sc[1]["description"] == "z"


def test_limit_returns_last_n(timeline):
    for i in range(10):
        timeline.append("m1", actor="a", event_type="state_change", description=f"e{i}")
    last3 = timeline.read("m1", limit=3)
    assert len(last3) == 3
    assert last3[0]["description"] == "e7"
    assert last3[2]["description"] == "e9"


def test_count(timeline):
    assert timeline.count("m1") == 0
    timeline.append("m1", actor="a", event_type="created", description="x")
    timeline.append("m1", actor="a", event_type="state_change", description="y")
    assert timeline.count("m1") == 2


def test_attachments_stored(timeline):
    timeline.append(
        "m1", actor="drafting-agent", event_type="file_added",
        description="Draft v1 added",
        attachments=["drafts/tutela-v1.md", "drafts/tutela-v1.pdf"],
    )
    events = timeline.read("m1")
    assert len(events[0]["attachments"]) == 2


def test_jsonl_format_one_event_per_line(timeline):
    """Cada evento es una línea JSON válida."""
    timeline.append("m1", actor="a", event_type="created", description="x")
    timeline.append("m1", actor="b", event_type="state_change", description="y")
    path = Path(timeline.matters_dir) / "m1" / "timeline.jsonl"
    with open(path, encoding="utf-8") as f:
        lines = [ln for ln in f.readlines() if ln.strip()]
    assert len(lines) == 2
    for line in lines:
        e = json.loads(line)
        assert "ts" in e
        assert "actor" in e
        assert "event_type" in e
        assert "description" in e
