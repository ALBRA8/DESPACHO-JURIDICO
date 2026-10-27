"""
DETERMINISTIC GUARD — capa de rechazo determinista inspirada en QWED-Legal.

Recreación clean-room (sin ver el código fuente de QWED). Solo se reimplementa
el patrón arquitectónico: checks deterministas (regex + aritmética de fechas)
que rechazan antes de invocar al LLM. Si el determinista falla, el LLM no se
llama. Sin Z3, sin LLM para validar — todo simbólico y reproducible.

Dos guards:

1. **DeadlineGuard** — verifica términos procesales colombianos
   (prescripción civil/laboral, procesales del CPC, tutela).
   Recibe `claim_date`, `event_date`, `deadline_type` y devuelve:
   {ok, days_elapsed, deadline_days, remaining_days, expired, reason}.

2. **ContradictionGuard** — detecta contradicciones obvias entre cláusulas de
   un contrato usando keyword matching (TERMINO INDETERMINADO vs FIJO,
   PESOS vs DOLARES, JURISDICCIÓN COLOMBIANA vs EXTRANJERA,
   EXCLUSIVAMENTE BOGOTÁ vs TERRITORIO NACIONAL).

REGLA CRÍTICA: estos guards son **deterministas** — no usan LLM, no usan
probabilidad. Si dicen `ok=False`, el flujo se detiene sin invocar al modelo.
Si dicen `ok=True`, no es garantía de legalidad — solo pasa al siguiente check.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from albra.observability.logger import get_logger

# =========================================================================
# Tabla de términos procesales colombianos (codificados como constantes)
# =========================================================================
# None = no hay término de prescripción / plazo razonable (tutela).
# Enteros = días calendario. Para días hábiles se documentan en el reason.
COLOMBIAN_DEADLINES: dict[str, int | None] = {
    # Prescripción civil
    "prescripcion_civil_extracontractual": 20 * 365,   # 20 años (Art. 2536 C.C.)
    "prescripcion_civil_contractual": 10 * 365,        # 10 años (Art. 2512 C.C. ord. lucrativa)
    "prescripcion_civil_accion_cambio": 1 * 365,      # 1 año (acciones redhibitorias)
    # Prescripción laboral
    "prescripcion_laboral_3_years": 3 * 365,          # 3 años (Art. 151 CST)
    "prescripcion_laboral_acciones": 1 * 365,          # 1 año
    # Acción de tutela
    "tutela_presentacion": None,  # No hay término de prescripción; plazo razonable
    # Procesales
    "demanda_contestacion": 15,                         # 15 días hábiles (Art. 96 CPC)
    "recursos_sentencia": 5,                            # 5 días (reposición + apelación)
    "impugnacion_sentencia": 5,                         # 5 días
    "consulta_jerarquica": 5,                           # 5 días
    "audiencia_prueba": 30,                             # 30 días calendario
    "notificacion_estados": 5,                          # 5 días
}


# =========================================================================
# DeadlineGuard
# =========================================================================
class DeadlineGuard:
    """Verifica términos procesales colombianos (determinista)."""

    def __init__(self) -> None:
        self.log = get_logger("albra.security.deterministic_guard.deadline")

    def check(
        self,
        *,
        claim_date: datetime,
        event_date: datetime,
        deadline_type: str,
    ) -> dict[str, Any]:
        """Verifica que `event_date - claim_date` esté dentro del plazo legal.

        Args:
            claim_date: fecha en que nace el derecho/obligación (inicio del cómputo).
            event_date: fecha en que ocurre el evento a verificar (p.ej. contestación,
                        interposición de recurso, presentación de tutela).
            deadline_type: clave de COLOMBIAN_DEADLINES.

        Returns:
            dict con: ok, days_elapsed, deadline_days, remaining_days, expired, reason.
        """
        if deadline_type not in COLOMBIAN_DEADLINES:
            self.log.error("deadline.unknown_type", deadline_type=deadline_type)
            raise ValueError(
                f"Unknown deadline_type: {deadline_type!r}. "
                f"Valid types: {sorted(COLOMBIAN_DEADLINES)}"
            )

        deadline_days = COLOMBIAN_DEADLINES[deadline_type]

        # Caso especial: tutela_presentacion → no hay término fijo.
        if deadline_days is None:
            self.log.info(
                "deadline.no_prescripcion",
                deadline_type=deadline_type,
                note="tutela: no término de prescripción, plazo razonable",
            )
            return {
                "ok": True,
                "days_elapsed": (event_date - claim_date).days,
                "deadline_days": None,
                "remaining_days": None,
                "expired": False,
                "reason": (
                    f"Tipo '{deadline_type}' no tiene término de prescripción fijo. "
                    "Plazo razonable según el juez de tutela (Auto 138 de 2015 de la "
                    "Corte Constitucional). Determinista: ok=True."
                ),
            }

        if event_date < claim_date:
            return {
                "ok": False,
                "days_elapsed": (event_date - claim_date).days,
                "deadline_days": deadline_days,
                "remaining_days": None,
                "expired": False,
                "reason": (
                    "event_date anterior a claim_date — cómputo inválido."
                ),
            }

        days_elapsed = (event_date - claim_date).days
        remaining_days = deadline_days - days_elapsed
        expired = days_elapsed > deadline_days
        ok = not expired

        if ok:
            reason = (
                f"Dentro del plazo: {days_elapsed} días transcurridos de "
                f"{deadline_days} permitidos para '{deadline_type}'. "
                f"Faltan {remaining_days} días."
            )
        else:
            reason = (
                f"PLAZO VENCIDO: {days_elapsed} días transcurridos exceden el "
                f"término de {deadline_days} días para '{deadline_type}'. "
                f"Exceso: {abs(remaining_days)} días."
            )

        self.log.info(
            "deadline.check",
            deadline_type=deadline_type,
            days_elapsed=days_elapsed,
            deadline_days=deadline_days,
            remaining_days=remaining_days,
            expired=expired,
            ok=ok,
        )
        return {
            "ok": ok,
            "days_elapsed": days_elapsed,
            "deadline_days": deadline_days,
            "remaining_days": remaining_days,
            "expired": expired,
            "reason": reason,
        }


# =========================================================================
# ContradictionGuard
# =========================================================================
# Cada regla: (type, [patrones lado A], [patrones lado B], detalle)
# Si el contrato menciona al menos un patrón de A Y al menos uno de B,
# hay contradicción.
_CONTRADICTION_RULES: list[tuple[str, list[re.Pattern[str]], list[re.Pattern[str]], str]] = [
    (
        "termino",
        [re.compile(r"\bT[EÉ]RMINO\s+INDETERMINADO\b", re.IGNORECASE)],
        [re.compile(r"\bT[EÉ]RMINO\s+FIJO\b", re.IGNORECASE)],
        "El contrato fija simultáneamente término indeterminado y término fijo.",
    ),
    (
        "moneda",
        [re.compile(r"\bPESOS\b", re.IGNORECASE)],
        [re.compile(r"\bD[OÓ]LARES\b", re.IGNORECASE)],
        "El contrato menciona dos monedas incompatibles: PESOS y DOLARES.",
    ),
    (
        "jurisdiccion",
        [re.compile(r"JURISDICCI[ÓO]N\s+COLOMBIANA", re.IGNORECASE)],
        [re.compile(r"JURISDICCI[ÓO]N\s+EXTRANJERA", re.IGNORECASE)],
        "El contrato somete a jurisdicción colombiana y extranjera simultáneamente.",
    ),
    (
        "territorio",
        [re.compile(r"EXCLUSIVAMENTE\s+BOGOT[ÁA]", re.IGNORECASE)],
        [re.compile(r"TERRITORIO\s+NACIONAL", re.IGNORECASE)],
        "El contrato limita el territorio a Bogotá y simultáneamente lo extiende al territorio nacional.",
    ),
]


class ContradictionGuard:
    """Detecta contradicciones obvias entre cláusulas de un contrato (sin Z3)."""

    def __init__(self) -> None:
        self.log = get_logger("albra.security.deterministic_guard.contradiction")

    def check(self, clauses: list[dict[str, str]]) -> dict[str, Any]:
        """Verifica contradicciones entre cláusulas de un contrato.

        Args:
            clauses: lista de dicts {number: str, text: str}.

        Returns:
            dict con: ok, contradictions (list[dict]), reason.
            Cada contradiction: {clause1, clause2, type, detail}.
        """
        if not clauses:
            return {
                "ok": True,
                "contradictions": [],
                "reason": "Sin cláusulas para verificar.",
            }

        contradictions: list[dict[str, Any]] = []

        for ctype, patterns_a, patterns_b, detail in _CONTRADICTION_RULES:
            matches_a: list[tuple[str, str]] = []  # (clause_number, matched_text)
            matches_b: list[tuple[str, str]] = []
            for clause in clauses:
                number = clause.get("number", "?")
                text = clause.get("text", "")
                for pat in patterns_a:
                    m = pat.search(text)
                    if m:
                        matches_a.append((number, m.group(0)))
                for pat in patterns_b:
                    m = pat.search(text)
                    if m:
                        matches_b.append((number, m.group(0)))
            if matches_a and matches_b:
                contradictions.append({
                    "clause1": matches_a[0][0],
                    "clause2": matches_b[0][0],
                    "type": ctype,
                    "detail": detail,
                    "evidence_a": matches_a[0][1],
                    "evidence_b": matches_b[0][1],
                })

        ok = len(contradictions) == 0
        if ok:
            reason = (
                f"Sin contradicciones detectadas en {len(clauses)} cláusulas "
                f"(check determinista por keyword matching)."
            )
        else:
            reason = (
                f"BLOQUEADO: {len(contradictions)} contradicción(es) detectada(s) "
                f"por keyword matching determinista: "
                + "; ".join(c["type"] for c in contradictions)
                + "."
            )

        self.log.info(
            "contradiction.check",
            clauses_count=len(clauses),
            contradictions=len(contradictions),
            ok=ok,
        )
        return {
            "ok": ok,
            "contradictions": contradictions,
            "reason": reason,
        }
