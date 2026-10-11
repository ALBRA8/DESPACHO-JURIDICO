"""
VERIFICATION + CONFLICT DETECTION - V1.0.

Cross-source verification: comparar candidatos para detectar
conflictos entre fuentes.

Conflictos detectados:
- norma modificada por otra
- norma derogada por otra
- jurisprudencia contradictoria
- decisiones posteriores que superan anteriores
- fuentes con diferente autoridad para mismo tema
- versiones temporales diferentes (norma vs artículo)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from albra.knowledge.retrieval import RetrievalResult
from albra.knowledge.schemas import EvidenceCandidate
from albra.observability.logger import get_logger


@dataclass
class Conflict:
    kind: str  # modified | derogated | jurisprudence_contradiction | authority_conflict | temporal_conflict
    description: str
    candidate_ids: list[str] = field(default_factory=list)
    severity: str = "low"  # low | medium | high
    recommended_action: str = ""


@dataclass
class VerificationResult:
    ok: bool
    candidates: list[EvidenceCandidate] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    primary_evidence_id: str | None = None
    needs_hitl: bool = False
    abstention: bool = False
    abstention_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "candidates": [c.as_dict() for c in self.candidates],
            "conflicts": [
                {"kind": c.kind, "description": c.description, "severity": c.severity}
                for c in self.conflicts
            ],
            "primary_evidence_id": self.primary_evidence_id,
            "needs_hitl": self.needs_hitl,
            "abstention": self.abstention,
            "abstention_reason": self.abstention_reason,
        }


class LegalVerifier:
    """Verificador de evidencia jurídica."""

    def __init__(self) -> None:
        self.log = get_logger("albra.verification")

    def verify(self, result: RetrievalResult) -> VerificationResult:
        """Verifica candidatos y detecta conflictos."""
        if result.abstention or not result.candidates:
            return VerificationResult(
                ok=False,
                abstention=True,
                abstention_reason=result.abstention_reason or (
                    "No se encontró evidencia jurídica suficiente. "
                    "ALBRA NO inventa conocimiento jurídico."
                ),
            )

        candidates = result.candidates
        conflicts: list[Conflict] = []

        # Conflict 1: temporal conflict (some current, some historical)
        current = [c for c in candidates if c.is_current]
        historical = [c for c in candidates if not c.is_current]
        if current and historical:
            conflicts.append(Conflict(
                kind="temporal_conflict",
                description=(
                    f"Found {len(current)} current and {len(historical)} historical sources. "
                    "Use current unless explicitly asking about a past version."
                ),
                candidate_ids=[c.source_id for c in historical],
                severity="low",
                recommended_action="Filter to current sources unless historical query",
            ))

        # Conflict 2: authority conflict (different authorities for same norm)
        authorities = {c.authority for c in candidates if c.authority}
        if len(authorities) > 1 and len(candidates) > 1:
            conflicts.append(Conflict(
                kind="authority_conflict",
                description=(
                    f"Multiple authorities found: {authorities}. "
                    "Verify which authority has primary jurisdiction."
                ),
                candidate_ids=[c.source_id for c in candidates],
                severity="medium",
                recommended_action="Filter to highest-tier source",
            ))

        # Conflict 3: jurisprudence contradiction
        # BLOQUE 3: usar effect (vocabulario controlado) en vez de binding:bool
        # Distingue erga_omnes de precedente de vinculante
        from albra.knowledge.schemas import BINDING_EFFECTS, validate_effect
        binding_candidates = []
        for c in candidates:
            effect = c.provenance.get("effect", "desconocido")
            validated = validate_effect(effect)
            if validated in BINDING_EFFECTS:
                binding_candidates.append((c, validated))

        if len(binding_candidates) > 1:
            effects_found = {e for _, e in binding_candidates}
            conflict_desc = (
                f"Found {len(binding_candidates)} binding decisions "
                f"(effects: {effects_found}). Check for conflicting precedents."
            )
            conflicts.append(Conflict(
                kind="jurisprudence_contradiction",
                description=conflict_desc,
                candidate_ids=[c.source_id for c, _ in binding_candidates],
                severity="high",
                recommended_action="HITL review required - legal decision may need interpretation",
            ))

        # Conflict 4: same norm, different status (modified/derogaded)
        all_statuses = {c.provenance.get("status") for c in candidates}
        non_empty_statuses = [s for s in all_statuses if s]
        if len(non_empty_statuses) > 1:
            conflicts.append(Conflict(
                kind="modified",
                description=f"Multiple status found: {non_empty_statuses}. Verify temporal validity.",
                severity="medium",
            ))

        # Select primary evidence (highest tier, highest score, current)
        primary = self._select_primary(candidates)
        needs_hitl = any(c.severity == "high" for c in conflicts)

        return VerificationResult(
            ok=True,
            candidates=candidates,
            conflicts=conflicts,
            primary_evidence_id=primary.source_id if primary else None,
            needs_hitl=needs_hitl,
        )

    def _select_primary(self, candidates: list[EvidenceCandidate]) -> EvidenceCandidate | None:
        """Selecciona la evidencia primaria.

        BLOQUE 6: Documentación precisa del comportamiento real.

        Orden de prioridad (sort ascendente por tupla):
        1. source_tier ASCENDENTE: S0=0 < S1=1 < S2=2 < S3=3 < S4=4
           → S0 SIEMPRE sortea antes que S4, sin importar score.
           Una fuente S4 NO puede superar a S0 por mayor similitud semántica.
        2. is_current DESC: preferir vigente sobre histórica (dentro del mismo tier)
        3. score DESC: mayor relevancia semántica primero (dentro del mismo tier + vigencia)
        4. doc_type_priority DESC: texto normativo > jurisprudencia > doctrina (desempate)

        Esta jerarquía garantiza que:
        - Una fuente primaria superior (S0) con score 0.3 supera a
          una fuente secundaria (S4) con score 0.95.
        - Dentro del mismo tier, se prefiere vigente sobre histórica.
        - Dentro del mismo tier + vigencia, mayor score gana.
        - En empate total, se prefiere texto normativo sobre doctrina.

        NO hay excepción donde S4 supere S0 por score.
        """
        if not candidates:
            return None
        # Sort por (tier ASC, is_current DESC, score DESC, document_type priority DESC)
        # Nota: c.source_tier es SourceTier (IntEnum), S0=0, S4=4. Sort ascendente.
        def doc_type_priority(doc_type: str) -> int:
            # texto_normativo > jurisprudencia > doctrina
            if doc_type in ("ley", "decreto", "codigo", "estatuto", "constitucion"):
                return 3
            if doc_type in ("sentencia", "auto"):
                return 2
            if doc_type in ("articulo_academico", "libro_doctrina", "tratado"):
                return 1
            return 0

        return sorted(candidates, key=lambda c: (
            c.source_tier,                # P0-2 FIX: ASCENDENTE - S0 primero
            -int(c.is_current),           # current primero
            -c.score,                     # score más alto primero
            -doc_type_priority(c.document_type),
        ))[0]
