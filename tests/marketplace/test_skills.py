"""Tests del Skills Marketplace V2.5-A.

Cobertura (15 tests):
- register_skill returns id
- list_skills returns all default 15
- list_skills filter by category / practice_area / tag
- get_skill returns object / None
- search_skills substring match / no match
- export_catalog returns list of dicts
- stats returns counts (total_skills / by_category / by_practice_area / by_author)
- register_skill duplicate id raises
- register_skill missing required field raises
- bootstrap creates 15 skills (5 agents + 5 playbooks + 5 tools)
- skills marketplace singleton (get_marketplace lazy + resettable)
"""
from __future__ import annotations

import pytest

from albra.marketplace import (
    Skill,
    SkillsMarketplace,
    SkillValidationError,
    get_marketplace,
)
from albra.marketplace import skills as mp_module

# ===== Fixtures =====


@pytest.fixture
def strong_secrets(monkeypatch):
    """Secretos efímeros requeridos por settings.Settings (V1.5 security)."""
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-ephemeral-jwt-secret-32-chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-ephemeral-pass-1234")


@pytest.fixture
def marketplace(strong_secrets):
    """Fresh SkillsMarketplace (sin contaminación del singleton)."""
    return SkillsMarketplace()


# Helper para construir una skill válida mínima.
def _make_skill(
    *,
    sid: str = "custom-skill",
    name: str = "Custom Skill",
    category: str = "drafting",
    practice_areas: list[str] | None = None,
    mcp_tool_name: str = "get_playbook",
    input_schema: dict | None = None,
    output_type: str = "dict",
    tags: list[str] | None = None,
) -> Skill:
    return Skill(
        id=sid,
        name=name,
        description="Test skill for marketplace tests.",
        category=category,
        practice_areas=practice_areas or ["civil"],
        mcp_tool_name=mcp_tool_name,
        input_schema=input_schema
        or {"type": "object", "properties": {}, "required": []},
        output_type=output_type,
        tags=tags or ["custom"],
    )


# ===== register_skill =====


def test_register_skill_returns_id(marketplace):
    """register_skill devuelve el id de la skill y la deja accesible."""
    skill = _make_skill(sid="custom-skill")
    result = marketplace.register_skill(skill)
    assert result == "custom-skill"
    assert marketplace.get_skill("custom-skill") is skill
    # Total ahora 16 (15 bootstrap + 1 custom)
    assert len(marketplace.list_skills()) == 16


# ===== list_skills =====


def test_list_skills_returns_all_default_15(marketplace):
    """Fresh SkillsMarketplace() bootstrap-registra 15 skills."""
    skills = marketplace.list_skills()
    assert len(skills) == 15


def test_list_skills_filter_by_category(marketplace):
    """Filtrar por category='deadline' → solo deadline-guard."""
    deadline_skills = marketplace.list_skills(category="deadline")
    assert len(deadline_skills) == 1
    assert deadline_skills[0].id == "deadline-guard"


def test_list_skills_filter_by_practice_area(marketplace):
    """Filtrar por practice_area='laboral'.

    5 agentes (todos listan laboral) + 1 laboral-playbook + 5 tools avanzadas
    (todas listan todas las áreas) = 11 skills.
    """
    laboral_skills = marketplace.list_skills(practice_area="laboral")
    assert len(laboral_skills) == 11
    ids = {s.id for s in laboral_skills}
    assert "laboral-playbook" in ids
    assert "intake-agent" in ids
    assert "citation-auditor" in ids


def test_list_skills_filter_by_tag(marketplace):
    """Filtrar por tag='playbook' → solo las 5 playbooks (civil/laboral/
    constitucional/familia/corporativo)."""
    playbook_skills = marketplace.list_skills(tag="playbook")
    assert len(playbook_skills) == 5
    assert all(s.id.endswith("-playbook") for s in playbook_skills)


# ===== get_skill =====


def test_get_skill_returns_object(marketplace):
    """get_skill devuelve la Skill con todos sus campos."""
    skill = marketplace.get_skill("intake-agent")
    assert skill is not None
    assert skill.id == "intake-agent"
    assert skill.category == "research"
    assert "civil" in skill.practice_areas
    assert "laboral" in skill.practice_areas
    assert skill.mcp_tool_name == "advance_matter"
    assert skill.output_type == "dict"
    assert skill.author == "ALBRA"
    assert skill.license == "Apache-2.0"


def test_get_unknown_returns_none(marketplace):
    """get_skill de id inexistente → None (sin excepción)."""
    assert marketplace.get_skill("nonexistent-skill") is None


# ===== search_skills =====


def test_search_skills_substring_match(marketplace):
    """search_skills('citation') matchea name/description/tags."""
    results = marketplace.search_skills("citation")
    # Como mínimo citation-auditor (name) + agentic-citator (tag 'citation')
    # + review-agent (description mentions 'citations').
    assert len(results) >= 2
    ids = {s.id for s in results}
    assert "citation-auditor" in ids
    assert "agentic-citator" in ids


def test_search_skills_no_match_returns_empty(marketplace):
    """search_skills con query que no matchea nada → [] (no None)."""
    results = marketplace.search_skills("xyzqq-nope-nada-12345")
    assert results == []
    assert isinstance(results, list)


def test_search_skills_empty_query_returns_empty(marketplace):
    """search_skills con query vacío → [] (no crash)."""
    assert marketplace.search_skills("") == []
    assert marketplace.search_skills("   ") == []


# ===== export_catalog =====


def test_export_catalog_returns_list_of_dicts(marketplace):
    """export_catalog devuelve list[dict] con 13 claves por skill."""
    catalog = marketplace.export_catalog()
    assert isinstance(catalog, list)
    assert len(catalog) == 15
    expected_keys = {
        "id", "name", "description", "category",
        "practice_areas", "mcp_tool_name", "input_schema",
        "output_type", "version", "author", "license", "tags", "examples",
    }
    for entry in catalog:
        assert isinstance(entry, dict)
        assert expected_keys.issubset(entry.keys()), (
            f"missing keys in skill {entry.get('id')}: "
            f"{expected_keys - set(entry.keys())}"
        )
    # Cada dict es una copia independiente del Skill
    catalog[0]["id"] = "mutated"
    assert marketplace.get_skill("intake-agent") is not None


# ===== stats =====


def test_stats_returns_counts(marketplace):
    """stats devuelve total_skills + by_category/by_practice_area/by_author."""
    stats = marketplace.stats()
    assert stats["total_skills"] == 15
    assert isinstance(stats["by_category"], dict)
    assert isinstance(stats["by_practice_area"], dict)
    assert isinstance(stats["by_author"], dict)
    # Todas las skills son author=ALBRA (default)
    assert stats["by_author"].get("ALBRA") == 15
    # Category 'deadline' solo tiene 1 (deadline-guard)
    assert stats["by_category"].get("deadline") == 1
    # Category 'drafting' tiene drafting-agent + 5 playbooks = 6
    assert stats["by_category"].get("drafting") == 6
    # 'civil' practice_area: 5 agents + 1 civil-playbook + 5 tools = 11
    assert stats["by_practice_area"].get("civil") == 11


# ===== register_skill: error cases =====


def test_register_skill_with_duplicate_id_raises(marketplace):
    """Registrar skill con id ya existente → SkillValidationError."""
    dup = _make_skill(sid="intake-agent")  # ya en bootstrap
    with pytest.raises(SkillValidationError, match="already registered"):
        marketplace.register_skill(dup)


def test_register_skill_missing_required_field_raises(marketplace):
    """Registrar skill con id vacío → SkillValidationError."""
    skill = _make_skill(sid="")  # id vacío = missing required field
    with pytest.raises(SkillValidationError, match="missing required field: id"):
        marketplace.register_skill(skill)


def test_register_skill_invalid_category_raises(marketplace):
    """category fuera del enum válido → SkillValidationError."""
    skill = _make_skill(sid="bad-cat", category="not-a-real-category")
    with pytest.raises(SkillValidationError, match="invalid category"):
        marketplace.register_skill(skill)


def test_register_skill_empty_practice_areas_raises(marketplace):
    """practice_areas=[] → SkillValidationError."""
    skill = Skill(
        id="no-areas",
        name="No Areas",
        description="Test skill with empty practice_areas.",
        category="drafting",
        practice_areas=[],
        mcp_tool_name="get_playbook",
        input_schema={"type": "object", "properties": {}, "required": []},
        output_type="dict",
    )
    with pytest.raises(
        SkillValidationError, match="missing required field: practice_areas"
    ):
        marketplace.register_skill(skill)


# ===== bootstrap =====


def test_bootstrap_creates_15_skills(strong_secrets):
    """SkillsMarketplace() sin registro manual → 15 skills bootstrapped."""
    mp = SkillsMarketplace()
    skills = mp.list_skills()
    assert len(skills) == 15
    ids = {s.id for s in skills}
    # 5 agentes V2.0
    for agent_id in (
        "intake-agent", "research-agent", "drafting-agent",
        "review-agent", "filing-agent",
    ):
        assert agent_id in ids, f"{agent_id} not bootstrapped"
    # 5 playbooks V2.2-D
    for area in ("civil", "laboral", "constitucional", "familia", "corporativo"):
        assert f"{area}-playbook" in ids, f"{area}-playbook not bootstrapped"
    # 5 tools avanzadas
    for tool_id in (
        "citation-auditor", "local-rag", "deadline-guard",
        "agentic-citator", "precedent-board",
    ):
        assert tool_id in ids, f"{tool_id} not bootstrapped"


# ===== singleton =====


def test_skills_marketplace_singleton(strong_secrets, monkeypatch):
    """get_marketplace() devuelve la misma instancia (lazy + resettable)."""
    # Reset singleton antes del test para asegurar estado limpio
    monkeypatch.setattr(mp_module, "_marketplace", None)
    mp1 = get_marketplace()
    mp2 = get_marketplace()
    assert mp1 is mp2
    assert isinstance(mp1, SkillsMarketplace)
    # Singleton tiene las 15 skills bootstrapped
    assert len(mp1.list_skills()) == 15
    # Limpieza para no afectar a otros tests
    monkeypatch.setattr(mp_module, "_marketplace", None)
