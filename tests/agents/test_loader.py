"""Tests del AgentLoader (markdown + YAML frontmatter parser)."""
from __future__ import annotations

from pathlib import Path

import pytest

from albra.agents.loader import (
    AgentDefinition,
    AgentLoader,
    AgentValidationError,
    _parse_frontmatter,
)

# ===== Tests del parser _parse_frontmatter =====

def test_parse_frontmatter_basic():
    content = """---
id: test-agent
name: TEST-AGENT
tier: specialist
reports_to: filing-agent
escalates_to: nobody
delegates_to: []
tools:
  - research.run
  - knowledge.write
minimum_human_signoff: 0
practice_areas:
  - civil
---

# TEST-AGENT body
"""
    fm, body = _parse_frontmatter(content)
    assert fm["id"] == "test-agent"
    assert fm["name"] == "TEST-AGENT"
    assert fm["tier"] == "specialist"
    assert fm["reports_to"] == "filing-agent"
    assert fm["escalates_to"] == "nobody"
    assert fm["delegates_to"] == []
    assert fm["tools"] == ["research.run", "knowledge.write"]
    assert fm["minimum_human_signoff"] == 0
    assert fm["practice_areas"] == ["civil"]
    assert "# TEST-AGENT body" in body


def test_parse_frontmatter_no_frontmatter():
    content = "# Just markdown\n\nNo frontmatter."
    fm, body = _parse_frontmatter(content)
    assert fm == {}
    assert body == content


def test_parse_frontmatter_with_quotes():
    content = '---\nid: "x-agent"\nname: \'X-AGENT\'\ntier: specialist\nreports_to: nobody\nescalates_to: nobody\ndelegates_to: []\ntools: []\nminimum_human_signoff: 1\npractice_areas: []\n---\n\nbody'
    fm, _ = _parse_frontmatter(content)
    assert fm["id"] == "x-agent"
    assert fm["name"] == "X-AGENT"
    assert fm["minimum_human_signoff"] == 1


def test_parse_frontmatter_malformed_raises():
    content = """---
id: test
name: TEST
"""  # no closing ---
    with pytest.raises(AgentValidationError):
        _parse_frontmatter(content)


# ===== Tests del AgentLoader con definiciones reales =====

@pytest.fixture
def loader():
    return AgentLoader()


def test_loader_loads_all_five_agents(loader):
    agents = loader.load_all()
    assert len(agents) == 5
    expected_ids = {"intake-agent", "research-agent", "drafting-agent",
                    "review-agent", "filing-agent"}
    assert set(agents.keys()) == expected_ids


def test_loader_returns_agentdefinition_objects(loader):
    agents = loader.load_all()
    for agent in agents.values():
        assert isinstance(agent, AgentDefinition)


def test_filing_agent_is_leadership_tier(loader):
    filing = loader.get("filing-agent")
    assert filing is not None
    assert filing.tier == "leadership"
    assert filing.reports_to == "nobody"
    assert filing.escalates_to == "nobody"
    assert "intake-agent" in filing.delegates_to
    assert "research-agent" in filing.delegates_to
    assert "drafting-agent" in filing.delegates_to
    assert "review-agent" in filing.delegates_to


def test_intake_agent_is_specialist_reports_to_filing(loader):
    intake = loader.get("intake-agent")
    assert intake is not None
    assert intake.tier == "specialist"
    assert intake.reports_to == "filing-agent"
    assert intake.escalates_to == "research-agent"
    assert intake.delegates_to == []
    assert intake.minimum_human_signoff == 0


def test_research_agent_has_research_tools(loader):
    research = loader.get("research-agent")
    assert research is not None
    assert "research.run" in research.tools
    assert "knowledge.query" in research.tools
    assert research.minimum_human_signoff == 0


def test_filing_agent_has_minimum_human_signoff_1(loader):
    """El único agente con minimum_human_signoff > 0 es filing-agent."""
    agents = loader.load_all()
    for agent in agents.values():
        if agent.id == "filing-agent":
            assert agent.minimum_human_signoff == 1
        else:
            assert agent.minimum_human_signoff == 0, (
                f"{agent.id} no debería tener signoff > 0; tiene {agent.minimum_human_signoff}"
            )


def test_all_practice_areas_covered(loader):
    """Los 5 agentes deben cubrir las 7 áreas de práctica."""
    expected_areas = {"civil", "constitucional", "laboral", "penal",
                      "corporativo", "administrativo", "familia"}
    agents = loader.load_all()
    for agent in agents.values():
        assert set(agent.practice_areas) == expected_areas, (
            f"{agent.id} no cubre todas las áreas: {agent.practice_areas}"
        )


def test_cross_references_valid(loader):
    """reports_to, escalates_to, delegates_to deben referir a agentes existentes."""
    agents = loader.load_all()
    ids = set(agents.keys()) | {"nobody"}
    for agent in agents.values():
        assert agent.reports_to in ids
        assert agent.escalates_to in ids
        for d in agent.delegates_to:
            assert d in ids


def test_organigrama_returns_all_as_dict(loader):
    org = loader.organigrama()
    assert len(org) == 5
    ids = [a["id"] for a in org]
    assert "filing-agent" in ids


def test_list_ids_sorted(loader):
    ids = loader.list_ids()
    assert ids == sorted(ids)
    assert len(ids) == 5


def test_reload_force(loader):
    loader.load_all()
    cached = loader._cache
    reloaded = loader.reload()
    assert reloaded is not None
    # Cache debe ser nuevo objeto (no mismo)
    assert loader._cache is not cached or len(reloaded) == 5


# ===== Tests de validación de errores =====

def test_loader_invalid_missing_definitions_dir(tmp_path):
    loader = AgentLoader(definitions_dir=str(tmp_path / "nonexistent"))
    agents = loader.load_all()
    assert agents == {}


def test_loader_invalid_missing_required_field(tmp_path):
    # Frontmatter sin campo `tier`
    bad_md = """---
id: bad-agent
name: BAD-AGENT
reports_to: nobody
escalates_to: nobody
delegates_to: []
tools: []
minimum_human_signoff: 0
practice_areas: []
---

# body
"""
    (tmp_path / "bad-agent.md").write_text(bad_md, encoding="utf-8")
    loader = AgentLoader(definitions_dir=str(tmp_path))
    with pytest.raises(AgentValidationError) as exc:
        loader.load_all()
    assert "tier" in str(exc.value).lower() or "required" in str(exc.value).lower()


def test_loader_invalid_tier_value(tmp_path):
    bad_md = """---
id: x
name: X
tier: middle-management
reports_to: nobody
escalates_to: nobody
delegates_to: []
tools: []
minimum_human_signoff: 0
practice_areas: []
---

body
"""
    (tmp_path / "x.md").write_text(bad_md, encoding="utf-8")
    loader = AgentLoader(definitions_dir=str(tmp_path))
    with pytest.raises(AgentValidationError) as exc:
        loader.load_all()
    assert "tier" in str(exc.value).lower()


def test_loader_invalid_negative_signoff(tmp_path):
    bad_md = """---
id: x
name: X
tier: leadership
reports_to: nobody
escalates_to: nobody
delegates_to: []
tools: []
minimum_human_signoff: -1
practice_areas: []
---

body
"""
    (tmp_path / "x.md").write_text(bad_md, encoding="utf-8")
    loader = AgentLoader(definitions_dir=str(tmp_path))
    with pytest.raises(AgentValidationError) as exc:
        loader.load_all()
    assert "minimum_human_signoff" in str(exc.value)


def test_loader_invalid_dangling_reference(tmp_path):
    """Agente que reporta a otro inexistente."""
    bad_md = """---
id: x
name: X
tier: specialist
reports_to: nonexistent-agent
escalates_to: nobody
delegates_to: []
tools: []
minimum_human_signoff: 0
practice_areas: []
---

body
"""
    (tmp_path / "x.md").write_text(bad_md, encoding="utf-8")
    loader = AgentLoader(definitions_dir=str(tmp_path))
    with pytest.raises(AgentValidationError) as exc:
        loader.load_all()
    assert "reports_to" in str(exc.value)


def test_loader_no_leadership_fails(tmp_path):
    """Organigrama sin leadership tier debe fallar."""
    md = """---
id: x
name: X
tier: specialist
reports_to: nobody
escalates_to: nobody
delegates_to: []
tools: []
minimum_human_signoff: 0
practice_areas: []
---

body
"""
    (tmp_path / "x.md").write_text(md, encoding="utf-8")
    loader = AgentLoader(definitions_dir=str(tmp_path))
    with pytest.raises(AgentValidationError) as exc:
        loader.load_all()
    assert "leadership" in str(exc.value)


def test_get_unknown_returns_none(loader):
    assert loader.get("nonexistent-agent") is None


def test_body_markdown_has_content(loader):
    """Cada agente debe tener body markdown con descripción."""
    agents = loader.load_all()
    for agent in agents.values():
        assert agent.body_markdown.strip(), f"{agent.id} no tiene body"
        assert "Role:" in agent.body_markdown or "Role" in agent.body_markdown
