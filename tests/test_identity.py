"""Tests de identidad - criterios 1, 33, 34, 35, 36."""
from albra.identity.manifest import (
    AGENT_MANIFEST,
    AgentIdentity,
    ALBRA_DNA_ORGANS,
    ALBRA_PRINCIPLES,
)


def test_identity_exists():
    assert AGENT_MANIFEST.name == "DESPACHO JURÍDICO DIGITAL ALBRA"


def test_identity_has_30_organs():
    assert len(ALBRA_DNA_ORGANS) == 30
    # Verificar órganos clave
    for organ in ("IDENTIDAD", "RUNTIME", "MOTOR_DE_RAZONAMIENTO", "MEMORIA",
                  "MCP", "DOCTOR", "COMUNICACION", "MULTIMODALIDAD",
                  "INVESTIGACION", "EVIDENCIA", "PROVENANCE", "SEGURIDAD",
                  "EVOLUCION"):
        assert organ in ALBRA_DNA_ORGANS


def test_identity_principles_defined():
    assert len(ALBRA_PRINCIPLES) >= 5
    # Verificar que GitHub es fuente de verdad
    assert any("GitHub" in p for p in ALBRA_PRINCIPLES)


def test_identity_is_not_constructor():
    """Criterio 35: el agente NO es constructor de código."""
    assert AGENT_MANIFEST.is_constructor is False
    assert AGENT_MANIFEST.can_modify_code is False


def test_identity_jurisdiction_colombia():
    """Criterio: primera jurisdicción objetivo = Colombia."""
    assert AGENT_MANIFEST.jurisdiction == "CO"


def test_identity_specialization_generalista():
    """Criterio 33: no requiere subagentes especializados para funcionar."""
    assert "generalista" in AGENT_MANIFEST.specialization


def test_identity_can_observe_and_execute():
    """El agente puede observar, auditar, ejecutar - pero no modificar código."""
    assert AGENT_MANIFEST.can_observe is True
    assert AGENT_MANIFEST.can_audit is True
    assert AGENT_MANIFEST.can_execute is True


def test_manifest_has_metadata():
    m = AGENT_MANIFEST.manifest()
    assert "organs" in m
    assert "principles" in m
    assert m["organs_count"] == 30
