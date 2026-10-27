"""
AGENTIC CITATOR — treatment labels para jurisprudencia colombiana.

Recreación clean-room del patrón de Gotham (trygotham.io) — el único
comercial conocido que implementa treatment analysis sobre jurisprudencia.
Se recrea desde cero sin ver su código; solo se reimplementa la idea
arquitectónica: clasificar la relación entre una sentencia que cita y la
sentencia citada mediante un conjunto cerrado de etiquetas (treatments).

Treatments estándar internacional adaptado a Colombia:

- `followed`:       la sentencia posterior aplicó el mismo principio.
- `distinguished`: la sentencia posterior distinguió los hechos y no aplicó.
- `doubted`:       la sentencia posterior expresó reservas.
- `overruled`:      la sentencia posterior revocó explícitamente.
- `per_incuriam`:   la sentencia se dictó sin consideración de norma aplicable.
- `affirmed`:       confirmada en apelación.
- `reversed`:       revocada en apelación.
- `cited`:          solo mencionada sin treatment explícito (default neutro).

REGLA CRÍTICA (fail-closed): si no puede determinar el treatment con
confianza ≥0.5, returns treatment="cited" (neutro) y confidence baja.
NUNCA inventa un treatment. Ante la duda, neutraliza.

Confidence scoring:
- 1.0 si el patrón matchea con palabra clave fuerte ("siguiendo el criterio",
  "se revoca la decisión").
- 0.7 si matchea con palabra clave suave ("aplica", "revocada").
- 0.4 si solo hay menciones indirectas.
- Default 0.3 si no hay match (treatment="cited" neutro).
"""
from __future__ import annotations

import re
from typing import Any

from albra.observability.logger import get_logger

# =========================================================================
# Patrones de detección por treatment (regex simple, sin LLM)
# =========================================================================
# Estructura: cada treatment tiene tres niveles:
#   - strong:   frases específicas → confidence 1.0
#   - soft:     palabras clave suaves → confidence 0.7
#   - indirect: menciones indirectas → confidence 0.4
# El nivel más alto que matchea determina la confidence para ese treatment.
_TREATMENT_PATTERNS: dict[str, dict[str, list[str]]] = {
    "followed": {
        "strong": [
            r"se\s+aplica\s+el\s+mismo\s+criterio",
            r"siguiendo\s+el\s+criterio",
            r"en\s+aplicaci[oó]n\s+de\s+la\s+sentencia",
        ],
        "soft": [
            r"aplica(?:ndo)?",
            r"aplicaci[oó]n",
        ],
        "indirect": [
            r"\bcriterio\b",
            r"precedente",
        ],
    },
    "distinguished": {
        "strong": [
            r"se\s+distinguen\s+los\s+hechos",
            r"no\s+se\s+aplica\s+porque",
            r"los\s+hechos\s+son\s+distintos",
        ],
        "soft": [
            r"distingue(?:n|d|s)?",
            r"distintos",
        ],
        "indirect": [
            r"diferencia",
        ],
    },
    "doubted": {
        "strong": [
            r"se\s+expresan\s+reservas",
            r"criterio\s+cuestionable",
            r"no\s+se\s+comparte\s+el\s+criterio",
        ],
        "soft": [
            r"reservas?",
            r"cuestionable",
        ],
        "indirect": [
            r"discordancia",
        ],
    },
    "overruled": {
        "strong": [
            r"se\s+revoca",
            r"se\s+deroga",
            r"queda\s+sin\s+efecto",
            r"se\s+modifica\s+el\s+criterio",
        ],
        "soft": [
            r"deroga(?:da|d|s)?",
            r"sin\s+efecto",
        ],
        "indirect": [
            r"modificaci[oó]n",
        ],
    },
    "per_incuriam": {
        "strong": [
            r"se\s+dict[oó]\s+sin\s+consideraci[oó]n",
            r"omiti[oó]\s+norma\s+aplicable",
        ],
        "soft": [
            r"per\s+incuriam",
            r"omiti[oó]",
        ],
        "indirect": [
            r"omisi[oó]n",
        ],
    },
    "affirmed": {
        "strong": [
            r"se\s+confirma",
            r"se\s+mantuvo\s+la\s+decisi[oó]n",
        ],
        "soft": [
            r"confirm(?:a|ó|ada|ado)",
        ],
        "indirect": [
            r"mantenimient[oa]",
        ],
    },
    "reversed": {
        "strong": [
            r"se\s+revoca\s+la\s+decisi[oó]n",
            r"se\s+decide\s+en\s+sentido\s+contrario",
        ],
        "soft": [
            r"sentido\s+contrario",
            r"reversa",
        ],
        "indirect": [
            r"\bcontrario\b",
        ],
    },
}

# Confidence por nivel
_LEVEL_CONFIDENCE: dict[str, float] = {
    "strong": 1.0,
    "soft": 0.7,
    "indirect": 0.4,
}

# Umbral fail-closed
_FAIL_CLOSED_THRESHOLD: float = 0.5

# Confidence default cuando no hay ningún match
_DEFAULT_CONFIDENCE: float = 0.3


class AgenticCitator:
    """Citador con treatment labels para jurisprudencia colombiana.

    Inspiration (clean-room): pattern de Gotham (trygotham.io) — único
    comercial que lo hace. Se recrea desde cero sin ver su código.
    """

    TREATMENT_LABELS: tuple[str, ...] = (
        "followed", "distinguished", "doubted", "overruled",
        "per_incuriam", "affirmed", "reversed", "cited",
    )

    def __init__(self) -> None:
        self.log = get_logger("albra.knowledge.agentic_citator")
        self._compiled: dict[str, dict[str, list[re.Pattern[str]]]] = (
            self._compile_patterns()
        )

    def _compile_patterns(self) -> dict[str, dict[str, list[re.Pattern[str]]]]:
        compiled: dict[str, dict[str, list[re.Pattern[str]]]] = {}
        for treatment, levels in _TREATMENT_PATTERNS.items():
            compiled[treatment] = {}
            for level, pats in levels.items():
                compiled[treatment][level] = [
                    re.compile(p, re.IGNORECASE) for p in pats
                ]
        return compiled

    def _max_evidence_length(self, evidence: list[str]) -> int:
        """Longitud de la evidencia más larga (para desempate)."""
        return max((len(e) for e in evidence), default=0)

    def _evaluate_treatment(
        self,
        text: str,
        compiled_levels: dict[str, list[re.Pattern[str]]],
    ) -> tuple[float, list[str]]:
        """Devuelve (confidence, evidence) para un treatment sobre el texto.

        Recorre strong → soft → indirect y se queda con el nivel más alto
        que haya producido al menos un match.
        """
        for level in ("strong", "soft", "indirect"):
            patterns = compiled_levels[level]
            evidence: list[str] = []
            for pat in patterns:
                for m in pat.finditer(text):
                    matched = m.group(0)
                    if matched not in evidence:
                        evidence.append(matched)
            if evidence:
                return _LEVEL_CONFIDENCE[level], evidence
        return 0.0, []

    def analyze(self, citing_text: str, cited_decision_id: str) -> dict[str, Any]:
        """Analiza el texto de una sentencia que cita otra decisión.

        Returns:
            {
                "cited_decision_id": str,
                "treatment": str (one of TREATMENT_LABELS),
                "confidence": float (0.0-1.0),
                "evidence": list[str] (frases clave extraídas que justifican el treatment),
                "reason": str (explicación legible),
            }

        Fail-closed: si no puede determinar el treatment con confianza ≥0.5,
        returns treatment="cited" (neutro) y confidence baja.
        """
        best_treatment = "cited"
        best_confidence = _DEFAULT_CONFIDENCE
        best_evidence: list[str] = []

        for treatment, compiled_levels in self._compiled.items():
            confidence, evidence = self._evaluate_treatment(citing_text, compiled_levels)
            if confidence == 0.0:
                continue
            # Mejor confidence gana; en empate, gana el treatment con evidencia
            # más larga (más específica).
            if confidence > best_confidence:
                best_confidence = confidence
                best_treatment = treatment
                best_evidence = evidence
            elif confidence == best_confidence:
                cur_max = self._max_evidence_length(best_evidence)
                new_max = self._max_evidence_length(evidence)
                if new_max > cur_max:
                    best_treatment = treatment
                    best_evidence = evidence

        # Fail-closed: confidence < 0.5 → treatment neutro "cited"
        if best_confidence < _FAIL_CLOSED_THRESHOLD:
            reason = (
                f"Tratamiento neutro (cited) por confianza baja "
                f"({best_confidence:.1f} < {_FAIL_CLOSED_THRESHOLD:.1f}). "
                f"Sin clasificación definitiva. Fail-closed."
            )
            best_treatment = "cited"
            # Mantenemos best_evidence para trazabilidad (qué se detectó),
            # aunque el treatment final sea neutro.
        else:
            ev_preview = best_evidence[:3]
            reason = (
                f"Treatment='{best_treatment}' con confianza "
                f"{best_confidence:.1f} basado en {len(best_evidence)} "
                f"evidencia(s): {ev_preview}."
            )

        self.log.info(
            "agentic_citator.analyze",
            cited_decision_id=cited_decision_id,
            treatment=best_treatment,
            confidence=best_confidence,
            evidence_count=len(best_evidence),
        )

        return {
            "cited_decision_id": cited_decision_id,
            "treatment": best_treatment,
            "confidence": best_confidence,
            "evidence": best_evidence,
            "reason": reason,
        }
