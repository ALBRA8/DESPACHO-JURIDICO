"""
ABSTENTION POLICY - V1.0.

NO INVENTAR. NO COMPLETAR. NO SUPONER. NO FABRICAR.

Si no existe evidencia suficiente, el sistema debe responder:
"No se encontró evidencia suficiente para afirmar esto."

La abstención es una capacidad VÁLIDA, no un error.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from albra.knowledge.retrieval import RetrievalResult
from albra.knowledge.verification import VerificationResult

ABSTENTION_MESSAGES = {
    "no_evidence": (
        "No se encontró evidencia jurídica suficiente para responder a esta consulta. "
        "ALBRA NO inventa conocimiento jurídico. La abstención es una capacidad válida."
    ),
    "low_confidence": (
        "La evidencia encontrada tiene confianza baja. No se puede emitir una afirmación "
        "definitiva sin verificación adicional."
    ),
    "conflicting_sources": (
        "Existen conflictos entre las fuentes encontradas. Se requiere revisión humana "
        "antes de emitir una respuesta definitiva."
    ),
    "no_primary_source": (
        "No se encontró una fuente primaria superior (S0) u oficial (S1). "
        "No se puede emitir una afirmación jurídica basada únicamente en doctrina o "
        "fuentes secundarias."
    ),
    "expired_norm": (
        "La norma citada no está vigente. Se requiere verificar la versión actual."
    ),
    "ambiguous_query": (
        "La consulta es ambigua. Se requiere aclaración antes de recuperar información."
    ),
    "out_of_jurisdiction": (
        "La consulta parece referirse a otra jurisdicción. ALBRA solo responde sobre "
        "derecho colombiano (jurisdicción CO)."
    ),
}


@dataclass
class AbstentionDecision:
    abstain: bool
    reason_code: str = ""
    reason_text: str = ""
    fallback_action: str = ""  # ask_user | hitl | try_research

    def as_dict(self) -> dict[str, Any]:
        return {
            "abstain": self.abstain,
            "reason_code": self.reason_code,
            "reason_text": self.reason_text,
            "fallback_action": self.fallback_action,
        }


class AbstentionPolicy:
    """Decide si el sistema debe abstenerse de responder."""

    CONFIDENCE_THRESHOLD = 0.5  # below this → abstain

    def evaluate(
        self,
        *,
        result: RetrievalResult,
        verification: VerificationResult,
        query_classification: Any = None,
    ) -> AbstentionDecision:
        """P1-7 FIX: orden optimizado - ambiguous_query al INICIO.

        Sin debilitar fail-safe. La verificación de ambigüedad es gratuita
        y debe preceder a cualquier búsqueda de evidencia para evitar
        recuperación irrelevante.
        """
        # P1-7 FIX: 1. Ambiguous query FIRST (fail-safe, no retrieval needed)
        if query_classification and query_classification.needs_clarification:
            return AbstentionDecision(
                abstain=True,
                reason_code="ambiguous_query",
                reason_text=query_classification.clarification_question or ABSTENTION_MESSAGES["ambiguous_query"],
                fallback_action="ask_user",
            )

        # 2. No evidence at all → abstain
        if result.abstention or not result.candidates:
            return AbstentionDecision(
                abstain=True,
                reason_code="no_evidence",
                reason_text=ABSTENTION_MESSAGES["no_evidence"],
                fallback_action="try_research",
            )

        # 3. No primary source
        from albra.knowledge.schemas import SourceTier
        has_primary = any(
            c.source_tier in (SourceTier.S0_PRIMARY_SUPERIOR, SourceTier.S1_OFFICIAL)
            for c in verification.candidates
        )
        if not has_primary:
            return AbstentionDecision(
                abstain=True,
                reason_code="no_primary_source",
                reason_text=ABSTENTION_MESSAGES["no_primary_source"],
                fallback_action="hitl",
            )

        # 4. Conflicting sources → HITL
        if any(c.severity == "high" for c in verification.conflicts):
            return AbstentionDecision(
                abstain=True,
                reason_code="conflicting_sources",
                reason_text=ABSTENTION_MESSAGES["conflicting_sources"],
                fallback_action="hitl",
            )

        # 5. Expired norm (all candidates are historical)
        if not any(c.is_current for c in verification.candidates):
            return AbstentionDecision(
                abstain=True,
                reason_code="expired_norm",
                reason_text=ABSTENTION_MESSAGES["expired_norm"],
                fallback_action="ask_user",
            )

        # 6. Low confidence
        avg_score = sum(c.score for c in result.candidates) / max(1, len(result.candidates))
        if avg_score < self.CONFIDENCE_THRESHOLD:
            return AbstentionDecision(
                abstain=True,
                reason_code="low_confidence",
                reason_text=ABSTENTION_MESSAGES["low_confidence"],
                fallback_action="try_research",
            )

        # OK to respond
        return AbstentionDecision(abstain=False)
