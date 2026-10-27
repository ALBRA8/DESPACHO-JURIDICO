"""Tests del state machine monótono de Matters."""
from __future__ import annotations

import pytest

from albra.matters.matter import (
    MATTER_STATES,
    MATTER_TRANSITIONS,
    TERMINAL_STATE,
    InvalidTransitionError,
    Matter,
    MatterState,
)


def test_matter_state_constants_exist():
    assert len(MATTER_STATES) == 8
    assert MATTER_STATES[0] == "NUEVO"
    assert MATTER_STATES[-1] == TERMINAL_STATE == "FIRMADO-Y-ENTREGADO"


def test_matter_initial_state_is_nuevo():
    m = Matter(client="X", area="civil", created_by="abogado1")
    assert m.state == "NUEVO"
    assert m.id  # UUID generado
    assert not m.is_terminal()
    assert len(m.state_history) == 1
    assert m.state_history[0]["state"] == "NUEVO"
    assert m.state_history[0]["reason"] == "initial"


def test_matter_full_happy_path():
    """Camino feliz: NUEVO → ... → FIRMADO-Y-ENTREGADO."""
    m = Matter(client="X", area="civil", created_by="abogado1")
    transitions = [
        ("INTAKE", "intake recopilado"),
        ("PLANEACIÓN", "research lista"),
        ("EJECUTANDO", "drafting"),
        ("BORRADOR-FINAL", "draft v1"),
        ("EN-ESPERA-DE-APROBACIÓN", "sometido a aprobación"),
        ("LISTO-PARA-CLIENTE", "aprobado"),
        ("FIRMADO-Y-ENTREGADO", "entregado al cliente"),
    ]
    for target, reason in transitions:
        m.transition_to(target, by="abogado1", reason=reason)
    assert m.is_terminal()
    assert m.state == "FIRMADO-Y-ENTREGADO"
    # 8 estados visitados: initial + 7 transiciones
    assert len(m.state_history) == 8


def test_matter_cannot_skip_states():
    """No se puede saltar estados. P.ej. NUEVO → PLANEACIÓN directo."""
    m = Matter(client="X", area="civil")
    with pytest.raises(InvalidTransitionError) as exc:
        m.transition_to("PLANEACIÓN")
    msg = str(exc.value)
    assert "Transición inválida" in msg
    assert "NUEVO" in msg
    assert "PLANEACIÓN" in msg
    # El estado no cambió
    assert m.state == "NUEVO"


def test_matter_cannot_go_backward_normal():
    """No se puede retroceder en condiciones normales (p. ej. INTAKE → NUEVO)."""
    m = Matter(client="X", area="civil")
    m.transition_to("INTAKE")
    with pytest.raises(InvalidTransitionError):
        m.transition_to("NUEVO")


def test_matter_reject_to_borrador_final_is_allowed():
    """La ÚNICA retrocesión permitida: EN-ESPERA-DE-APROBACIÓN → BORRADOR-FINAL (rechazo)."""
    m = Matter(client="X", area="civil", created_by="abogado1")
    for target in ("INTAKE", "PLANEACIÓN", "EJECUTANDO", "BORRADOR-FINAL", "EN-ESPERA-DE-APROBACIÓN"):
        m.transition_to(target)
    assert m.is_awaiting_approval()
    # Rechazo → retrabajo
    m.transition_to("BORRADOR-FINAL", by="socio", reason="rechazado: argumento débil")
    assert m.state == "BORRADOR-FINAL"
    # Volver a avanzar
    m.transition_to("EN-ESPERA-DE-APROBACIÓN")
    m.transition_to("LISTO-PARA-CLIENTE", reason="aprobado v2")
    m.transition_to("FIRMADO-Y-ENTREGADO")
    assert m.is_terminal()


def test_matter_terminal_cannot_transition():
    """Una vez firmado, ninguna transición es posible."""
    m = Matter(client="X", area="civil", created_by="abogado1")
    for target in ("INTAKE", "PLANEACIÓN", "EJECUTANDO", "BORRADOR-FINAL",
                   "EN-ESPERA-DE-APROBACIÓN", "LISTO-PARA-CLIENTE",
                   "FIRMADO-Y-ENTREGADO"):
        m.transition_to(target)
    # Cualquier transición debe fallar
    for target in MATTER_STATES:
        if target == TERMINAL_STATE:
            continue
        with pytest.raises(InvalidTransitionError) as exc:
            m.transition_to(target)
        assert "terminal" in str(exc.value).lower() or "FIRMADO-Y-ENTREGADO" in str(exc.value)


def test_matter_state_namespace():
    """MatterState namespace expone constantes y helpers."""
    assert MatterState.NUEVO == "NUEVO"
    assert MatterState.FIRMADO_Y_ENTREGADO == "FIRMADO-Y-ENTREGADO"
    assert MatterState.is_terminal("FIRMADO-Y-ENTREGADO")
    assert not MatterState.is_terminal("NUEVO")
    assert MatterState.is_valid("INTAKE")
    assert not MatterState.is_valid("INVALID")
    assert MatterState.order_of("NUEVO") == 0
    assert MatterState.order_of("FIRMADO-Y-ENTREGADO") == 7
    with pytest.raises(ValueError):
        MatterState.order_of("INVALID")


def test_matter_invalid_initial_state():
    """Estado inicial debe ser válido."""
    with pytest.raises(ValueError):
        Matter(client="X", area="civil", state="INVALID_STATE")


def test_state_history_grows_with_transitions():
    m = Matter(client="X", area="civil", created_by="abogado1")
    initial_len = len(m.state_history)
    m.transition_to("INTAKE", by="paralegal1", reason="datos recopilados")
    m.transition_to("PLANEACIÓN", by="abogado1", reason="researching")
    assert len(m.state_history) == initial_len + 2
    last = m.state_history[-1]
    assert last["state"] == "PLANEACIÓN"
    assert last["by"] == "abogado1"
    assert last["reason"] == "researching"


def test_matter_transitions_count():
    """Deben existir exactamente 8 transiciones válidas (incluida la retrabajo).

    Forward path = 7 transiciones (NUEVO → ... → FIRMADO-Y-ENTREGADO) +
    1 transición de retrabajo (EN-ESPERA → BORRADOR-FINAL) = 8 total.
    """
    assert len(MATTER_TRANSITIONS) == 8
    # Path forward feliz (7 transiciones)
    forward_path = [
        ("NUEVO", "INTAKE"),
        ("INTAKE", "PLANEACIÓN"),
        ("PLANEACIÓN", "EJECUTANDO"),
        ("EJECUTANDO", "BORRADOR-FINAL"),
        ("BORRADOR-FINAL", "EN-ESPERA-DE-APROBACIÓN"),
        ("EN-ESPERA-DE-APROBACIÓN", "LISTO-PARA-CLIENTE"),
        ("LISTO-PARA-CLIENTE", "FIRMADO-Y-ENTREGADO"),
    ]
    for tr in forward_path:
        assert tr in MATTER_TRANSITIONS, f"Falta transición forward: {tr}"
    # Retrabajo (única retrocesión permitida)
    assert ("EN-ESPERA-DE-APROBACIÓN", "BORRADOR-FINAL") in MATTER_TRANSITIONS
