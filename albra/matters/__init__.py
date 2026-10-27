"""
MATTERS — unidad central del Despacho Jurídico Digital ALBRA V2.0.

Cada expediente del despacho es un "matter" con:
- identificador único (UUID v4)
- cliente, área de práctica, parties (demandante/demandado/terceros)
- deadlines procesales
- documentos asociados
- timeline de eventos (JSONL append-only)
- state machine monótono (estado terminal no retornable)

Estados:
    NUEVO → INTAKE → PLANEACIÓN → EJECUTANDO → BORRADOR-FINAL →
    EN-ESPERA-DE-APROBACIÓN → LISTO-PARA-CLIENTE → FIRMADO-Y-ENTREGADO

REGLA CRÍTICA: el state machine es MONÓTONO. No se puede retroceder.
Una vez firmado y entregado, el matter no vuelve a "borrador".
Esto garantiza audit-trail inviolable (ética abogadil colombiana,
Decreto 1967/2014 y Ley 1123/2007).
"""
from albra.matters.matter import (
    MATTER_STATES,
    MATTER_TRANSITIONS,
    InvalidTransitionError,
    Matter,
    MatterState,
)
from albra.matters.store import MatterStore
from albra.matters.timeline import MatterTimeline

__all__ = [
    "MATTER_STATES",
    "MATTER_TRANSITIONS",
    "Matter",
    "MatterState",
    "InvalidTransitionError",
    "MatterStore",
    "MatterTimeline",
]
