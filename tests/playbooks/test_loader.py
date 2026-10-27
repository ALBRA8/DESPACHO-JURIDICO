"""Tests del PlaybookLoader (markdown + YAML frontmatter parser)."""
from __future__ import annotations

from pathlib import Path

import pytest

from albra.playbooks.loader import (
    Playbook,
    PlaybookLoader,
    PlaybookValidationError,
)


@pytest.fixture
def loader():
    return PlaybookLoader()


def test_loader_loads_all_five_playbooks(loader):
    playbooks = loader.load_all()
    assert len(playbooks) == 5
    expected_areas = {"laboral", "civil", "familia", "constitucional", "corporativo"}
    assert set(playbooks.keys()) == expected_areas


def test_loader_returns_playbook_objects(loader):
    playbooks = loader.load_all()
    for pb in playbooks.values():
        assert isinstance(pb, Playbook)


def test_laboral_playbook_fields(loader):
    laboral = loader.get("laboral")
    assert laboral is not None
    assert laboral.practice_area == "laboral"
    assert "demanda_ordinaria_laboral" in laboral.typical_matter_types
    assert "prescripcion_laboral_3_years" in laboral.deadline_types
    assert "Constitución Política de 1991" in laboral.citation_corpus
    assert "Ley 100 de 1993" in laboral.citation_corpus
    assert "NUEVO" in laboral.workflow_states
    assert "FIRMADO-Y-ENTREGADO" in laboral.workflow_states
    assert len(laboral.red_flags) >= 3


def test_civil_playbook_prescripcion_20_years(loader):
    civil = loader.get("civil")
    assert civil is not None
    assert "prescripcion_civil_extracontractual" in civil.deadline_types
    assert "prescripcion_civil_contractual" in civil.deadline_types
    assert "Constitución Política de 1991" in civil.citation_corpus


def test_constitucional_playbook_for_tutela(loader):
    const = loader.get("constitucional")
    assert const is not None
    assert "accion_de_tutela_salud" in const.typical_matter_types
    assert "tutela_presentacion" in const.deadline_types
    assert "Constitución Política de 1991" in const.citation_corpus
    assert "Ley 100 de 1993" in const.citation_corpus
    assert any("menor" in flag.lower() or "menores" in flag.lower()
               for flag in const.red_flags)


def test_familia_playbook_has_icbf_red_flag(loader):
    fam = loader.get("familia")
    assert fam is not None
    # ICBF flag debe estar presente por menores
    assert any("ICBF" in flag or "icbf" in flag.lower()
               for flag in fam.red_flags)


def test_corporativo_playbook_has_ley_80(loader):
    corp = loader.get("corporativo")
    assert corp is not None
    assert "Ley 80 de 1993" in corp.citation_corpus
    # Contratos estatales referenced
    assert any("estatal" in flag.lower() or "ley 80" in flag.lower()
               for flag in corp.red_flags)


def test_all_playbooks_have_complete_workflow_states(loader):
    """Todos los playbooks deben declarar el workflow completo de 8 estados."""
    playbooks = loader.load_all()
    expected_states = [
        "NUEVO", "INTAKE", "PLANEACIÓN", "EJECUTANDO",
        "BORRADOR-FINAL", "EN-ESPERA-DE-APROBACIÓN",
        "LISTO-PARA-CLIENTE", "FIRMADO-Y-ENTREGADO",
    ]
    for area, pb in playbooks.items():
        assert set(pb.workflow_states) == set(expected_states), (
            f"{area} no declara todos los 8 estados: {pb.workflow_states}"
        )


def test_all_playbooks_have_red_flags(loader):
    playbooks = loader.load_all()
    for area, pb in playbooks.items():
        assert len(pb.red_flags) >= 3, (
            f"{area} tiene muy pocos red_flags: {pb.red_flags}"
        )


def test_all_playbooks_have_body_markdown(loader):
    """Cada playbook debe tener body con guía de drafting."""
    playbooks = loader.load_all()
    for area, pb in playbooks.items():
        assert pb.body_markdown.strip(), f"{area} no tiene body markdown"
        # Body debe mencionar Etapa 1 INTAKE al menos
        assert "INTAKE" in pb.body_markdown


def test_list_areas_returns_sorted(loader):
    areas = loader.list_areas()
    assert areas == sorted(areas)
    assert len(areas) == 5


def test_get_unknown_returns_none(loader):
    assert loader.get("nonexistent-area") is None


def test_reload_force(loader):
    loader.load_all()
    reloaded = loader.reload()
    assert reloaded is not None
    assert len(reloaded) == 5


def test_loader_invalid_missing_definitions_dir(tmp_path):
    loader = PlaybookLoader(definitions_dir=str(tmp_path / "nonexistent"))
    playbooks = loader.load_all()
    assert playbooks == {}


def test_loader_missing_required_field_raises(tmp_path):
    bad_md = """---
practice_area: x
typical_matter_types: []
workflow_states: []
required_documents: []
deadline_types: []
citation_corpus: []
red_flags: body
---

# body
"""
    # Omitimos 'red_flags' arriba para forzar missing field — corregir:
    bad_md = """---
practice_area: x
typical_matter_types: []
workflow_states: []
required_documents: []
deadline_types: []
citation_corpus: []
---

# body
"""
    (tmp_path / "x.md").write_text(bad_md, encoding="utf-8")
    loader = PlaybookLoader(definitions_dir=str(tmp_path))
    with pytest.raises(PlaybookValidationError) as exc:
        loader.load_all()
    assert "red_flags" in str(exc.value)


def test_playbook_as_dict(loader):
    laboral = loader.get("laboral")
    d = laboral.as_dict()
    assert d["practice_area"] == "laboral"
    assert "typical_matter_types" in d
    assert "deadline_types" in d
    assert "citation_corpus" in d
    assert "red_flags" in d
    assert "body_markdown_preview" in d
    assert "file_path" in d
