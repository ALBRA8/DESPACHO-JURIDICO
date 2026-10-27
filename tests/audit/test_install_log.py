"""Tests del InstallLog (skill installation audit con hash chain)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from albra.audit.install_log import (
    EVENT_TYPES,
    SOURCES,
    VERDICTS,
    InstallLog,
    InstallLogEntry,
)


@pytest.fixture
def install_log(tmp_path):
    return InstallLog(str(tmp_path / "install_audit.jsonl"))


# ===== Append + chain =====

def test_append_returns_entry(install_log):
    entry = install_log.append(
        event_type="skill_installed",
        skill_id="citation-auditor",
        version="2.0.0",
        source="marketplace",
        license="Apache-2.0",
        review_verdict="approved",
        reviewer="abogado1",
    )
    assert isinstance(entry, InstallLogEntry)
    assert entry.event_type == "skill_installed"
    assert entry.skill_id == "citation-auditor"
    assert entry.version == "2.0.0"
    assert entry.source == "marketplace"
    assert entry.license == "Apache-2.0"
    assert entry.review_verdict == "approved"
    assert entry.reviewer == "abogado1"
    assert entry.this_hash
    assert entry.prev_hash == InstallLog.GENESIS_HASH


def test_append_chains_hash(install_log):
    e1 = install_log.append(event_type="skill_installed", skill_id="x")
    e2 = install_log.append(event_type="skill_activated", skill_id="x")
    assert e2.prev_hash == e1.this_hash
    assert e2.this_hash != e1.this_hash


def test_append_invalid_event_type_raises(install_log):
    with pytest.raises(ValueError):
        install_log.append(event_type="invalid_event", skill_id="x")


def test_append_invalid_source_raises(install_log):
    with pytest.raises(ValueError):
        install_log.append(event_type="skill_installed", skill_id="x", source="invalid_source")


def test_append_invalid_verdict_raises(install_log):
    with pytest.raises(ValueError):
        install_log.append(event_type="skill_installed", skill_id="x", review_verdict="invalid_verdict")


# ===== Verify chain =====

def test_verify_chain_intact(install_log):
    for i in range(5):
        install_log.append(
            event_type="skill_installed", skill_id=f"skill-{i}",
            source="marketplace", license="MIT",
        )
    result = install_log.verify_chain()
    assert result["ok"] is True
    assert result["total"] == 5
    assert result["broken_at"] == []


def test_verify_chain_detects_tampering(install_log):
    for i in range(5):
        install_log.append(event_type="skill_installed", skill_id=f"skill-{i}")
    # Tamper con el segundo entry
    path = Path(install_log.log_path)
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    entry = json.loads(lines[1])
    entry["skill_id"] = "HACKED"
    lines[1] = json.dumps(entry, ensure_ascii=False) + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    install_log._prev_hash = install_log._load_last_hash()
    result = install_log.verify_chain()
    assert not result["ok"]
    assert len(result["broken_at"]) >= 1


def test_verify_chain_empty_log(install_log):
    result = install_log.verify_chain()
    assert result["ok"] is True
    assert result["total"] == 0


# ===== Read + filter =====

def test_read_all_entries(install_log):
    install_log.append(event_type="skill_installed", skill_id="x")
    install_log.append(event_type="skill_activated", skill_id="x")
    install_log.append(event_type="skill_deactivated", skill_id="x")
    entries = install_log.read()
    assert len(entries) == 3


def test_read_filter_by_event_type(install_log):
    install_log.append(event_type="skill_installed", skill_id="x")
    install_log.append(event_type="skill_activated", skill_id="x")
    install_log.append(event_type="skill_installed", skill_id="y")
    installed = install_log.read(event_type="skill_installed")
    assert len(installed) == 2


def test_read_filter_by_skill_id(install_log):
    install_log.append(event_type="skill_installed", skill_id="x")
    install_log.append(event_type="skill_installed", skill_id="y")
    install_log.append(event_type="skill_activated", skill_id="x")
    x_entries = install_log.read(skill_id="x")
    assert len(x_entries) == 2


def test_read_limit(install_log):
    for i in range(10):
        install_log.append(event_type="skill_installed", skill_id=f"skill-{i}")
    last3 = install_log.read(limit=3)
    assert len(last3) == 3
    assert last3[0].skill_id == "skill-7"
    assert last3[2].skill_id == "skill-9"


# ===== Count + fingerprint =====

def test_count(install_log):
    assert install_log.count() == 0
    install_log.append(event_type="skill_installed", skill_id="x")
    install_log.append(event_type="skill_activated", skill_id="x")
    assert install_log.count() == 2


def test_fingerprint_stable(install_log):
    install_log.append(event_type="skill_installed", skill_id="x")
    fp1 = install_log.fingerprint()
    fp2 = install_log.fingerprint()
    assert fp1 == fp2
    assert len(fp1) == 64


def test_fingerprint_changes_after_append(install_log):
    install_log.append(event_type="skill_installed", skill_id="x")
    fp1 = install_log.fingerprint()
    install_log.append(event_type="skill_activated", skill_id="x")
    fp2 = install_log.fingerprint()
    assert fp1 != fp2


# ===== Stats =====

def test_stats_returns_counts(install_log):
    install_log.append(event_type="skill_installed", skill_id="x", source="marketplace", license="MIT")
    install_log.append(event_type="skill_installed", skill_id="y", source="git_url", license="Apache-2.0")
    install_log.append(event_type="skill_activated", skill_id="x")
    stats = install_log.stats()
    assert stats["total_entries"] == 3
    assert stats["total_skills_installed"] == 2
    assert stats["by_event_type"]["skill_installed"] == 2
    assert stats["by_event_type"]["skill_activated"] == 1
    assert stats["by_skill"]["x"] == 2
    assert stats["by_skill"]["y"] == 1
    assert "fingerprint" in stats


# ===== Get install history =====

def test_get_install_history(install_log):
    install_log.append(event_type="skill_installed", skill_id="x", version="1.0")
    install_log.append(event_type="skill_activated", skill_id="x")
    install_log.append(event_type="skill_updated", skill_id="x", version="2.0")
    install_log.append(event_type="skill_deactivated", skill_id="x")
    install_log.append(event_type="skill_uninstalled", skill_id="x")
    history = install_log.get_install_history("x")
    assert len(history) == 5
    event_types = [e.event_type for e in history]
    assert "skill_installed" in event_types
    assert "skill_uninstalled" in event_types


def test_get_install_history_nonexistent_returns_empty(install_log):
    history = install_log.get_install_history("nonexistent")
    assert history == []


# ===== List installed skills =====

def test_list_installed_skills(install_log):
    install_log.append(event_type="skill_installed", skill_id="x")
    install_log.append(event_type="skill_installed", skill_id="y")
    install_log.append(event_type="skill_activated", skill_id="x")  # not install
    install_log.append(event_type="skill_installed", skill_id="x")  # duplicate install
    installed = install_log.list_installed_skills()
    assert len(installed) == 2  # x and y, deduped
    assert "x" in installed
    assert "y" in installed


def test_list_installed_skills_empty(install_log):
    assert install_log.list_installed_skills() == []


# ===== Constants =====

def test_event_types_has_6_values():
    assert len(EVENT_TYPES) == 6
    assert "skill_installed" in EVENT_TYPES
    assert "skill_uninstalled" in EVENT_TYPES
    assert "skill_updated" in EVENT_TYPES
    assert "skill_activated" in EVENT_TYPES
    assert "skill_deactivated" in EVENT_TYPES
    assert "skill_reviewed" in EVENT_TYPES


def test_sources_has_4_values():
    assert len(SOURCES) == 4
    assert "marketplace" in SOURCES
    assert "manual" in SOURCES
    assert "git_url" in SOURCES
    assert "internal" in SOURCES


def test_verdicts_has_3_values():
    assert len(VERDICTS) == 3
    assert "approved" in VERDICTS
    assert "rejected" in VERDICTS
    assert "pending" in VERDICTS


# ===== as_dict =====

def test_install_log_entry_as_dict(install_log):
    entry = install_log.append(
        event_type="skill_installed", skill_id="x",
        version="1.0", source="marketplace", license="MIT",
        review_verdict="approved", reviewer="abogado1",
        payload={"marketplace_id": "abc-123"},
    )
    d = entry.as_dict()
    assert d["event_type"] == "skill_installed"
    assert d["skill_id"] == "x"
    assert d["version"] == "1.0"
    assert d["source"] == "marketplace"
    assert d["license"] == "MIT"
    assert d["review_verdict"] == "approved"
    assert d["reviewer"] == "abogado1"
    assert d["payload"] == {"marketplace_id": "abc-123"}
    assert "ts" in d
    assert "prev_hash" in d
    assert "this_hash" in d


# ===== Persistence =====

def test_persistence_across_instances(tmp_path):
    log_path = str(tmp_path / "install_audit.jsonl")
    log1 = InstallLog(log_path)
    log1.append(event_type="skill_installed", skill_id="x")
    log1.append(event_type="skill_activated", skill_id="x")
    del log1

    log2 = InstallLog(log_path)
    assert log2.count() == 2
    # prev_hash debe reconstruirse correctamente
    log2.append(event_type="skill_deactivated", skill_id="x")
    # Verify chain intacta
    result = log2.verify_chain()
    assert result["ok"] is True
    assert result["total"] == 3
