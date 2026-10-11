"""
TEMPORAL JURÍDICO - V1.0.

Una norma jurídica NO es simplemente "documento vigente".
Tiene que soportar:
- fecha de expedición
- fecha de publicación
- entrada en vigor
- vigencia
- derogación
- modificación
- sustitución
- suspensión
- inexequibilidad
- nulidad
- pérdida de vigencia
- versiones históricas

Consultas distintas:
- "¿Qué decía la norma?" → versión histórica
- "¿Qué dice actualmente?" → versión vigente
- "¿Cuándo entró en vigor?" → effective_from
- "¿Fue derogada?" → status + effective_until + derogating_norm
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from albra.knowledge.schemas import VALIDITY_STATUS


@dataclass
class TemporalState:
    """Estado temporal de una norma/artículo en un momento dado."""
    status: str = "vigente"  # one of VALIDITY_STATUS
    effective_from: date | None = None
    effective_until: date | None = None
    effective_date: date | None = None  # the date we're asking about (for historical queries)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "effective_from": str(self.effective_from) if self.effective_from else None,
            "effective_until": str(self.effective_until) if self.effective_until else None,
            "effective_date": str(self.effective_date) if self.effective_date else None,
        }


def is_vigente(
    *,
    status: str,
    effective_from: date | None,
    effective_until: date | None,
    when: date | None = None,
) -> bool:
    """¿La norma estaba vigente en `when`? Si when=None, ¿hoy?

    P0-3 (CIERRE): 'historica' debe ser NO vigente.
    """
    when = when or date.today()
    # P0-3 FIX: incluir 'historica' en statuses no-vigentes.
    # Si la norma se marca como histórica, NO puede aparecer como vigente.
    if status in ("derogada", "sustituida", "inexequible", "nula", "perdida_vigencia", "historica"):
        # Verificar si when cae dentro del rango [effective_from, effective_until]
        # aunque el status actual sea no-vigente (pudo haber estado vigente antes)
        if effective_until and when <= effective_until:
            # Solo es vigente-en-fecha si además when >= effective_from
            if effective_from and when >= effective_from:
                return True  # estaba vigente antes de la pérdida de vigencia
            if not effective_from:
                return True  # sin effective_from pero cuando <= effective_until
        return False
    if status == "suspendida":
        return False  # temporalmente suspendida
    if effective_from and when < effective_from:
        return False
    if effective_until and when > effective_until:
        return False
    return True


def is_currently_vigente(*, status: str, effective_from: date | None, effective_until: date | None) -> bool:
    """¿Está vigente HOY?"""
    return is_vigente(status=status, effective_from=effective_from, effective_until=effective_until, when=None)


def is_historical(*, status: str, effective_until: date | None) -> bool:
    """¿Es una versión histórica (no vigente)?"""
    if status in ("derogada", "sustituida", "inexequible", "nula", "perdida_vigencia", "historica"):
        return True
    if effective_until and effective_until < date.today():
        return True
    return False


@dataclass
class TemporalQuery:
    """Query temporal: responde 'qué decía' vs 'qué dice'."""
    query_type: str  # "current" | "historical" | "as_of" | "at_publication" | "any"
    as_of: date | None = None  # for "as_of"

    def matches(self, state: TemporalState) -> bool:
        if self.query_type == "any":
            return True
        if self.query_type == "current":
            return is_vigente(
                status=state.status,
                effective_from=state.effective_from,
                effective_until=state.effective_until,
            )
        if self.query_type == "historical":
            return is_historical(
                status=state.status,
                effective_until=state.effective_until,
            )
        if self.query_type == "as_of" and self.as_of:
            return is_vigente(
                status=state.status,
                effective_from=state.effective_from,
                effective_until=state.effective_until,
                when=self.as_of,
            )
        if self.query_type == "at_publication":
            # Devuelve cualquier versión - filtramos por fecha pub más adelante
            return True
        return True


@dataclass
class VersionHistory:
    """Historia de versiones de una norma.

    B5 HARDENING: registra diagnostics para fechas inválidas.
    No lanza excepción. No afirma vigencia. Pero NO oculta el problema.
    """
    norm_id: str
    versions: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def add_version(
        self,
        *,
        version: int,
        effective_from: date | None,
        effective_until: date | None,
        status: str,
        supersedes_id: str | None = None,
    ) -> None:
        # B5: validar fechas al agregar
        from_str = str(effective_from) if effective_from else None
        until_str = str(effective_until) if effective_until else None
        self.versions.append({
            "version": version,
            "effective_from": from_str,
            "effective_until": until_str,
            "status": status,
            "supersedes_id": supersedes_id,
        })
        self.versions.sort(key=lambda v: v["version"])

    def get_version_at(self, when: date) -> dict[str, Any] | None:
        """Devuelve la versión vigente en la fecha dada.

        B5: registra diagnostics para fechas inválidas sin crashar.
        """
        self.diagnostics.clear()  # reset diagnostics per query
        for v in reversed(self.versions):
            eff_from = self._safe_parse_date(v.get("effective_from"))
            eff_until = self._safe_parse_date(v.get("effective_until"))
            # B5: si la fecha es inválida, registrar diagnostic
            if v.get("effective_from") and eff_from is None:
                self.diagnostics.append({
                    "version": v.get("version"),
                    "field": "effective_from",
                    "value": v.get("effective_from"),
                    "issue": "invalid_date_format",
                    "message": f"Cannot parse effective_from='{v.get('effective_from')}' as ISO date",
                })
                continue
            if v.get("effective_until") and eff_until is None:
                self.diagnostics.append({
                    "version": v.get("version"),
                    "field": "effective_until",
                    "value": v.get("effective_until"),
                    "issue": "invalid_date_format",
                    "message": f"Cannot parse effective_until='{v.get('effective_until')}' as ISO date",
                })
                continue
            if is_vigente(status=v["status"], effective_from=eff_from, effective_until=eff_until, when=when):
                return v
        return None

    @staticmethod
    def _safe_parse_date(s: str | None) -> date | None:
        """Parsea una fecha ISO de forma segura. None si inválida."""
        if not s:
            return None
        try:
            return date.fromisoformat(s)
        except (ValueError, TypeError):
            return None

    def current_version(self) -> dict[str, Any] | None:
        return self.get_version_at(date.today())


def normalize_status(status: str | None) -> str:
    """Normaliza cualquier string a un VALIDITY_STATUS conocido."""
    if not status:
        return "vigente"
    s = status.lower().strip()
    if s in VALIDITY_STATUS:
        return s
    # Accept common variations
    if s in ("vigente", "current", "active"):
        return "vigente"
    if s in ("derogado", "derogada", "repealed"):
        return "derogada"
    if s in ("modificado", "modificada", "amended"):
        return "modificada"
    if s in ("sustituido", "sustituida", "replaced"):
        return "sustituida"
    if s in ("suspendido", "suspendida", "suspended"):
        return "suspendida"
    if s in ("inexequible", "unconstitutional"):
        return "inexequible"
    if s in ("nulo", "nula", "void"):
        return "nula"
    if s in ("historico", "historica", "historical"):
        return "historica"
    if s in ("pendiente", "pending"):
        return "pendiente"
    return "vigente"
