"""Tests del MatterStore SQLite WAL."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from albra.matters.matter import (
    TERMINAL_STATE,
    InvalidTransitionError,
    Matter,
    MatterState,
)
from albra.matters.store import MatterStore
from albra.matters.timeline import MatterTimeline


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "matters.db"
    s = MatterStore(str(db))
    yield s
    s.close()


@pytest.fixture
def timeline(tmp_path):
    return MatterTimeline(str(tmp_path / "matters"))


def test_create_matter(store):
    m = store.create_matter(
        client="Juan Pérez",
        area="civil",
        parties=["Juan Pérez", "Carlos Roa"],
        created_by="abogado1",
        deadlines=[{"label": "demanda", "date": "2026-12-01"}],
        metadata={"matter_type": "ordinario"},
    )
    assert m.id
    assert m.state == "NUEVO"
    assert m.client == "Juan Pérez"
    assert m.area == "civil"
    assert m.parties == ["Juan Pérez", "Carlos Roa"]
    assert m.created_by == "abogado1"
    assert len(m.state_history) == 1
    assert m.deadlines[0]["label"] == "demanda"


def test_get_matter_roundtrip(store):
    m = store.create_matter(
        client="María Gómez",
        area="constitucional",
        parties=["Gómez", "MinSalud"],
        created_by="abogado2",
    )
    fetched = store.get_matter(m.id)
    assert fetched is not None
    assert fetched.id == m.id
    assert fetched.client == "María Gómez"
    assert fetched.area == "constitucional"
    assert sorted(fetched.parties) == sorted(["Gómez", "MinSalud"])
    assert fetched.created_by == "abogado2"
    assert fetched.state == "NUEVO"


def test_get_matter_returns_none_for_unknown(store):
    assert store.get_matter("nonexistent-id") is None


def test_list_matters_filter_by_state(store):
    m1 = store.create_matter(client="A", area="civil", created_by="ab1")
    m2 = store.create_matter(client="B", area="civil", created_by="ab2")
    # Avanzar m1 a INTAKE
    store.advance_state(m1.id, "INTAKE", by="ab1", reason="intake")
    # Listar NUEVO
    nuevos = store.list_matters(state="NUEVO")
    assert len(nuevos) == 1
    assert nuevos[0].id == m2.id
    # Listar INTAKE
    intakes = store.list_matters(state="INTAKE")
    assert len(intakes) == 1
    assert intakes[0].id == m1.id


def test_list_matters_filter_by_area(store):
    store.create_matter(client="A", area="civil", created_by="ab1")
    store.create_matter(client="B", area="constitucional", created_by="ab2")
    civiles = store.list_matters(area="civil")
    assert len(civiles) == 1
    assert civiles[0].area == "civil"


def test_list_matters_filter_by_client(store):
    store.create_matter(client="Juan Pérez", area="civil", created_by="ab1")
    store.create_matter(client="María Gómez", area="civil", created_by="ab2")
    juanes = store.list_matters(client="Juan")
    assert len(juanes) == 1
    assert juanes[0].client == "Juan Pérez"


def test_advance_state_happy_path(store, timeline):
    m = store.create_matter(client="X", area="civil", created_by="abogado1")
    timeline.append(m.id, actor="abogado1", event_type="created",
                    description=f"Matter {m.id} creado para X")
    store.advance_state(m.id, "INTAKE", by="paralegal1", reason="intake recopilado")
    m = store.get_matter(m.id)
    assert m.state == "INTAKE"
    assert len(m.state_history) == 2
    assert m.state_history[1]["by"] == "paralegal1"
    assert m.state_history[1]["reason"] == "intake recopilado"


def test_advance_state_invalid_transition_raises(store):
    m = store.create_matter(client="X", area="civil", created_by="ab1")
    # NUEVO → PLANEACIÓN (no permitido, debe saltar INTAKE primero)
    with pytest.raises(InvalidTransitionError):
        store.advance_state(m.id, "PLANEACIÓN", by="ab1")
    # Estado debe seguir siendo NUEVO
    m_fetched = store.get_matter(m.id)
    assert m_fetched.state == "NUEVO"


def test_advance_state_to_invalid_target_raises(store):
    m = store.create_matter(client="X", area="civil", created_by="ab1")
    with pytest.raises(ValueError) as exc:
        store.advance_state(m.id, "INVALID_STATE", by="ab1")
    assert "Estado inválido" in str(exc.value)


def test_advance_state_unknown_matter_raises(store):
    with pytest.raises(KeyError):
        store.advance_state("nonexistent", "INTAKE", by="ab1")


def test_full_workflow_with_terminal(store, timeline):
    """Flujo completo: crear → avanzar por todos los estados → terminal."""
    m = store.create_matter(
        client="María Gómez",
        area="constitucional",
        parties=["Gómez", "MinSalud"],
        created_by="abogado1",
        deadlines=[{"label": "tutela", "date": "2026-12-01"}],
    )
    timeline.append(m.id, actor="abogado1", event_type="created",
                    description="Matter creado para María Gómez (tutela salud)")

    transitions = [
        ("INTAKE", "abogado1", "datos recopilados"),
        ("PLANEACIÓN", "research-agent", "research jurídica"),
        ("EJECUTANDO", "drafting-agent", "redacción tutela v1"),
        ("BORRADOR-FINAL", "drafting-agent", "draft v1 finalizado"),
        ("EN-ESPERA-DE-APROBACIÓN", "review-agent", "review interno completo"),
        ("LISTO-PARA-CLIENTE", "abogado1", "aprobado v1"),
        ("FIRMADO-Y-ENTREGADO", "abogado1", "firmado y entregado"),
    ]
    for target, by, reason in transitions:
        store.advance_state(m.id, target, by=by, reason=reason)
        timeline.append(m.id, actor=by, event_type="state_change",
                        description=f"→ {target}: {reason}")

    m_final = store.get_matter(m.id)
    assert m_final.is_terminal()
    assert m_final.state == TERMINAL_STATE
    assert len(m_final.state_history) == 8
    # Timeline: 1 created + 7 state_change = 8
    assert timeline.count(m.id) == 8


def test_retrabajo_after_reject(store):
    """Rechazo → retrabajo → volver a enviar a aprobación."""
    m = store.create_matter(client="X", area="civil", created_by="ab1")
    for t in ("INTAKE", "PLANEACIÓN", "EJECUTANDO", "BORRADOR-FINAL",
              "EN-ESPERA-DE-APROBACIÓN"):
        store.advance_state(m.id, t, by="ab1")
    # Reject → back to BORRADOR-FINAL (única retrocesión permitida)
    store.advance_state(m.id, "BORRADOR-FINAL", by="socio1", reason="rechazado: argumento débil")
    # Re-trabajo → BORRADOR-FINAL → EN-ESPERA-DE-APROBACIÓN → LISTO-PARA-CLIENTE → FIRMADO
    store.advance_state(m.id, "EN-ESPERA-DE-APROBACIÓN", by="ab1", reason="v2 listo")
    store.advance_state(m.id, "LISTO-PARA-CLIENTE", by="socio1")
    store.advance_state(m.id, "FIRMADO-Y-ENTREGADO", by="ab1")
    m_final = store.get_matter(m.id)
    assert m_final.is_terminal()
    # state_history debe reflejar el loop: NUEVO → ... → EN-ESPERA → BORRADOR → EN-ESPERA → LISTO → FIRMADO
    states_seen = [h["state"] for h in m_final.state_history]
    assert states_seen.count("EN-ESPERA-DE-APROBACIÓN") == 2
    assert states_seen.count("BORRADOR-FINAL") == 2


def test_pending_action_workflow(store):
    """Approval chain: crear acción pendiente → firmar → APPROVED."""
    m = store.create_matter(client="X", area="civil", created_by="ab1")
    # Avanzar hasta EN-ESPERA-DE-APROBACIÓN
    for t in ("INTAKE", "PLANEACIÓN", "EJECUTANDO", "BORRADOR-FINAL",
              "EN-ESPERA-DE-APROBACIÓN"):
        store.advance_state(m.id, t, by="ab1")

    # Crear acción pendiente
    action_id = store.create_pending_action(
        matter_id=m.id,
        action_type="publish_legal_filing",
        description="Presentar tutela ante juez 23 civil",
        minimum_human_signoff=1,
    )
    pending = store.list_pending(matter_id=m.id)
    assert len(pending) == 1
    assert pending[0]["status"] == "PENDING"
    assert pending[0]["minimum_human_signoff"] == 1

    # Aprobar
    updated = store.add_approval(action_id, by="abogado1", role="abogado", comment="visto bueno")
    assert updated["status"] == "APPROVED"
    assert len(updated["approvals"]) == 1
    assert updated["approvals"][0]["by"] == "abogado1"
    assert updated["decided_by"] == "abogado1"

    # Pending list ahora debe estar vacío
    assert store.list_pending(matter_id=m.id) == []


def test_pending_action_requires_multiple_signoffs(store):
    """Acción con minimum_human_signoff=2 requiere 2 firmas."""
    m = store.create_matter(client="X", area="civil", created_by="ab1")
    action_id = store.create_pending_action(
        matter_id=m.id,
        action_type="sign_document",
        description="Firmar contrato de honorarios",
        minimum_human_signoff=2,
    )
    # Primera firma — debe seguir PENDING
    a1 = store.add_approval(action_id, by="paralegal1", role="paralegal", comment="visto bueno")
    assert a1["status"] == "PENDING"
    assert len(a1["approvals"]) == 1

    # Segunda firma — debe pasar a APPROVED
    a2 = store.add_approval(action_id, by="socio1", role="socio", comment="firmo")
    assert a2["status"] == "APPROVED"
    assert len(a2["approvals"]) == 2
    assert a2["decided_by"] == "socio1"


def test_pending_action_reject(store):
    m = store.create_matter(client="X", area="civil", created_by="ab1")
    action_id = store.create_pending_action(
        matter_id=m.id,
        action_type="publish_legal_filing",
        description="X",
        minimum_human_signoff=1,
    )
    rejected = store.reject_action(action_id, by="socio1", role="socio",
                                   comment="contrargumento en missing")
    assert rejected["status"] == "REJECTED"
    assert rejected["decided_by"] == "socio1"


def test_cannot_approve_already_decided(store):
    m = store.create_matter(client="X", area="civil", created_by="ab1")
    action_id = store.create_pending_action(
        matter_id=m.id,
        action_type="sign_document",
        description="X",
        minimum_human_signoff=1,
    )
    store.add_approval(action_id, by="ab1", role="abogado")
    # Intentar aprobar de nuevo — debe fallar
    with pytest.raises(ValueError) as exc:
        store.add_approval(action_id, by="ab2", role="abogado")
    assert "not PENDING" in str(exc.value)


def test_db_persistence_across_connections(tmp_path):
    """La DB persiste entre conexiones (WAL)."""
    db = tmp_path / "matters.db"
    s1 = MatterStore(str(db))
    m = s1.create_matter(client="X", area="civil", created_by="ab1")
    s1.close()

    s2 = MatterStore(str(db))
    fetched = s2.get_matter(m.id)
    assert fetched is not None
    assert fetched.client == "X"
    s2.close()
