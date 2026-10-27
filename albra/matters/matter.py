"""
MATTER — dataclass + state machine monótono.

Estados (orden estricto, monótono):
    NUEVO                       → 0  matter recién creado
    INTAKE                      → 1  recopilando datos del cliente
    PLANEACIÓN                  → 2  research + estrategia
    EJECUTANDO                  → 3  drafting activo
    BORRADOR-FINAL              → 4  draft listo para revisión interna
    EN-ESPERA-DE-APROBACIÓN    → 5  AWAITING-PARTNER gate
    LISTO-PARA-CLIENTE          → 6  aprobado, listo para entregar
    FIRMADO-Y-ENTREGADO         → 7  estado TERMINAL no retornable

Transiciones permitidas (forward-only):
    NUEVO                       → INTAKE
    INTAKE                      → PLANEACIÓN
    PLANEACIÓN                  → EJECUTANDO
    EJECUTANDO                  → BORRADOR-FINAL
    BORRADOR-FINAL              → EN-ESPERA-DE-APROBACIÓN
    EN-ESPERA-DE-APROBACIÓN    → LISTO-PARA-CLIENTE   (solo si approval firmada)
    EN-ESPERA-DE-APROBACIÓN    → BORRADOR-FINAL       (rechazado → retrabajar)
    LISTO-PARA-CLIENTE          → FIRMADO-Y-ENTREGADO  (terminal)
    FIRMADO-Y-ENTREGADO         → (none, terminal)

La transición EN-ESPERA-DE-APROBACIÓN → BORRADOR-FINAL es la ÚNICA
retrocesión permitida y se llama "retrabajo tras rechazo".
NO rompe la monotonía del audit porque el estado no retrocede al estado
de PRE-firma, sino al estado PRE-aprobación (loop de retrabajo explícito).

Una vez en FIRMADO-Y-ENTREGADO, ninguna transición es posible.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


class InvalidTransitionError(RuntimeError):
    """Levantado cuando se intenta transición no permitida."""


# Estados en orden estricto (índice = orden)
MATTER_STATES: tuple[str, ...] = (
    "NUEVO",
    "INTAKE",
    "PLANEACIÓN",
    "EJECUTANDO",
    "BORRADOR-FINAL",
    "EN-ESPERA-DE-APROBACIÓN",
    "LISTO-PARA-CLIENTE",
    "FIRMADO-Y-ENTREGADO",
)

# Estado terminal
TERMINAL_STATE = "FIRMADO-Y-ENTREGADO"

# Transiciones válidas: (from_state, to_state)
MATTER_TRANSITIONS: frozenset[tuple[str, str]] = frozenset({
    ("NUEVO", "INTAKE"),
    ("INTAKE", "PLANEACIÓN"),
    ("PLANEACIÓN", "EJECUTANDO"),
    ("EJECUTANDO", "BORRADOR-FINAL"),
    ("BORRADOR-FINAL", "EN-ESPERA-DE-APROBACIÓN"),
    # Única retrocesión permitida: rechazo de aprobación → retrabajo
    ("EN-ESPERA-DE-APROBACIÓN", "BORRADOR-FINAL"),
    # Aprobación firmada → listo
    ("EN-ESPERA-DE-APROBACIÓN", "LISTO-PARA-CLIENTE"),
    ("LISTO-PARA-CLIENTE", "FIRMADO-Y-ENTREGADO"),
})


def _utcnow_iso() -> str:
    """ISO 8601 UTC. Timezone-aware."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Matter:
    """Expediente digital. Unidad central del despacho.

    NO contiene documentos directamente — solo paths relativos a
    ``data/matters/<id>/``. El contenido vive en filesystem;
    el índice vive en SQLite (MatterStore).
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    client: str = ""
    area: str = ""  # civil | constitucional | laboral | penal | corporativo | administrativo | familia
    parties: list[str] = field(default_factory=list)
    state: str = "NUEVO"
    created_by: str = ""
    created_at: str = field(default_factory=_utcnow_iso)
    updated_at: str = field(default_factory=_utcnow_iso)
    state_history: list[dict[str, str]] = field(default_factory=list)
    deadlines: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validar estado inicial
        if self.state not in MATTER_STATES:
            raise ValueError(f"Estado inválido: {self.state!r}. Debe ser uno de {MATTER_STATES}")
        # Sembrar state_history si vacío
        if not self.state_history:
            self.state_history = [{
                "state": self.state,
                "at": self.created_at,
                "by": self.created_by or "system",
                "reason": "initial",
            }]

    def can_transition_to(self, target: str) -> bool:
        """¿Es válida la transición desde state actual a target?"""
        if self.state == TERMINAL_STATE:
            return False
        return (self.state, target) in MATTER_TRANSITIONS

    def transition_to(self, target: str, *, by: str = "system", reason: str = "") -> None:
        """Ejecuta la transición de state. Lanza InvalidTransitionError si no es válida."""
        if not self.can_transition_to(target):
            if self.state == TERMINAL_STATE:
                raise InvalidTransitionError(
                    f"Matter {self.id} ya está en estado terminal {TERMINAL_STATE}. "
                    f"No se puede transicionar a {target!r}."
                )
            raise InvalidTransitionError(
                f"Transición inválida: {self.state!r} → {target!r}. "
                f"Transiciones válidas desde {self.state!r}: "
                f"{[t for f, t in MATTER_TRANSITIONS if f == self.state]}"
            )
        self.state = target
        self.updated_at = _utcnow_iso()
        self.state_history.append({
            "state": target,
            "at": self.updated_at,
            "by": by,
            "reason": reason or "manual",
        })

    def is_terminal(self) -> bool:
        return self.state == TERMINAL_STATE

    def is_awaiting_approval(self) -> bool:
        return self.state == "EN-ESPERA-DE-APROBACIÓN"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class MatterState:
    """Namespace para constantes de estado. Uso: MatterState.NUEVO, etc."""

    NUEVO = "NUEVO"
    INTAKE = "INTAKE"
    PLANEACION = "PLANEACIÓN"
    EJECUTANDO = "EJECUTANDO"
    BORRADOR_FINAL = "BORRADOR-FINAL"
    EN_ESPERA_DE_APROBACION = "EN-ESPERA-DE-APROBACIÓN"
    LISTO_PARA_CLIENTE = "LISTO-PARA-CLIENTE"
    FIRMADO_Y_ENTREGADO = "FIRMADO-Y-ENTREGADO"

    @staticmethod
    def is_terminal(state: str) -> bool:
        return state == TERMINAL_STATE

    @staticmethod
    def is_valid(state: str) -> bool:
        return state in MATTER_STATES

    @staticmethod
    def order_of(state: str) -> int:
        try:
            return MATTER_STATES.index(state)
        except ValueError as exc:
            raise ValueError(f"Estado inválido: {state!r}") from exc
