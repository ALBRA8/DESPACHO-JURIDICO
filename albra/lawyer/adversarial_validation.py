"""V8.0 Fase 2 — AdversarialValidator.

Envuelve VigencyChecker + ContradictionDetector y revisa las citas
del LawyerExam antes de declarar SUCCESS.

DISCIPLINA V8.0:
  - Revisa: vigencia de normas citadas, contradicciones detectadas,
    citas sin soporte verificable, inferencias sin base documental.
  - Resultado estructurado: ``{ok: bool, defects: [...]}``
  - Cada defecto explica: qué se detectó, qué fuente lo sustenta,
    qué elemento del caso queda afectado.
  - Si una norma citada está demostrablemente derogada → ok=False.
  - Si existe una contradicción verificable no resuelta → ok=False.
  - Si una cita carece de evidencia → marcada como defect (no bloquea
    por sí sola, pero se registra).

Severidad de defectos:
  - ``blocking``: impide SUCCESS (norma derogada, contradicción no
    resuelta).
  - ``warning``: no impide SUCCESS pero debe documentarse (norma
    modificada, cita sin evidencia suficiente).
  - ``info``: informativo (relación de modificación entre normas).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from albra.knowledge.contradiction import ContradictionDetector
from albra.knowledge.vigency import VigencyChecker
from albra.observability.logger import get_logger


@dataclass
class ValidationDefect:
    """Un defecto detectado por el AdversarialValidator."""
    defect_type: str  # "derogated_norm" | "contradiction" | "modified_norm" | "no_evidence" | "info"
    severity: str     # "blocking" | "warning" | "info"
    citation: str     # "document_slug art. N"
    detail: str
    source_evidence: str
    affected_element: str  # which part of the case is affected (e.g. "strategy", "draft", "citation")

    def as_dict(self) -> dict[str, Any]:
        return {
            "defect_type": self.defect_type,
            "severity": self.severity,
            "citation": self.citation,
            "detail": self.detail,
            "source_evidence": self.source_evidence,
            "affected_element": self.affected_element,
        }


@dataclass
class ValidationResult:
    """Resultado de la validación adversarial."""
    ok: bool
    defects: list[ValidationDefect] = field(default_factory=list)
    vigency_results: list[dict[str, Any]] = field(default_factory=list)
    contradiction_results: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "defects": [d.as_dict() for d in self.defects],
            "vigency_results": self.vigency_results,
            "contradiction_results": self.contradiction_results,
        }


class AdversarialValidator:
    """Valida adversarialmente las citas jurídicas de un caso.

    Usa VigencyChecker + ContradictionDetector. Retorna un
    ValidationResult estructurado con ``ok`` (bool) y ``defects``
    (lista de ValidationDefect).

    Uso:
        validator = AdversarialValidator()
        result = validator.validate(
            citations=citations_verified,
            corpus=ALL_DOCUMENTS_V14,
        )
        if not result.ok:
            # BLOCKED — defects contain blocking-severity items
            for d in result.defects:
                if d.severity == "blocking":
                    print(f"BLOCKING: {d.detail}")
    """

    def __init__(
        self,
        *,
        vigency_checker: VigencyChecker | None = None,
        contradiction_detector: ContradictionDetector | None = None,
    ) -> None:
        self._vigency = vigency_checker or VigencyChecker()
        self._contradiction = contradiction_detector or ContradictionDetector()
        self._log = get_logger("albra.lawyer.adversarial_validation")

    def validate(
        self,
        *,
        citations: list[dict[str, Any]],
        corpus: list[tuple[str, dict[str, Any]]],
        affected_element: str = "citation",
    ) -> ValidationResult:
        """Valida las citas y retorna un resultado estructurado.

        Args:
            citations: Lista de citas verificadas (cada una con
                ``document``, ``article``, ``article_text`` o
                ``article_text_preview``, ``provenance_status``).
            corpus: El corpus V1.4 (ALL_DOCUMENTS_V14).
            affected_element: Qué elemento del caso se ve afectado
                si se detectan defectos (ej. "strategy", "draft").

        Returns:
            ValidationResult con ``ok`` y ``defects``.
        """
        defects: list[ValidationDefect] = []
        vigency_results: list[dict[str, Any]] = []
        contradiction_results: list[dict[str, Any]] = []

        # 1. Vigency check for each citation
        for cite in citations:
            doc_slug = cite.get("document", "")
            art_num = str(cite.get("article", ""))
            label = f"{doc_slug} art. {art_num}"

            vr = self._vigency.check_citation(
                document_slug=doc_slug,
                article_number=art_num,
                corpus=corpus,
            )
            vigency_results.append({**vr.as_dict(), "citation": label})

            if vr.status == "superseded":
                # BLOCKING: a cited norm is demonstrably superseded
                defects.append(ValidationDefect(
                    defect_type="superseded_norm",
                    severity="blocking",
                    citation=label,
                    detail=f"Norma superseded: {vr.reason}",
                    source_evidence=vr.evidence_source,
                    affected_element=affected_element,
                ))
            elif vr.status == "modified":
                # WARNING: the norm has been modified — still vigent
                # but the version in the corpus may not reflect the
                # latest modification. Document but don't block.
                defects.append(ValidationDefect(
                    defect_type="modified_norm",
                    severity="warning",
                    citation=label,
                    detail=f"Norma modificada: {vr.reason}. La versión del corpus puede no reflejar la última modificación.",
                    source_evidence=vr.evidence_source,
                    affected_element=affected_element,
                ))
            elif vr.status == "uncertain":
                # WARNING: cannot determine vigency — abstention
                defects.append(ValidationDefect(
                    defect_type="vigency_uncertain",
                    severity="warning",
                    citation=label,
                    detail=f"Vigencia incierta: {vr.reason}",
                    source_evidence=vr.evidence_source,
                    affected_element=affected_element,
                ))

        # 2. Contradiction detection between citation pairs
        contradiction_list = self._contradiction.detect(citations)
        for cr in contradiction_list:
            contradiction_results.append(cr.as_dict())
            if cr.relation == "explicit_conflict":
                # BLOCKING: explicit contradiction between cited norms
                defects.append(ValidationDefect(
                    defect_type="contradiction",
                    severity="blocking",
                    citation=f"{cr.citation_a} vs {cr.citation_b}",
                    detail=cr.detail,
                    source_evidence=cr.evidence,
                    affected_element=affected_element,
                ))
            elif cr.relation == "modification":
                # INFO: modification relationship (not a contradiction)
                defects.append(ValidationDefect(
                    defect_type="modification_relationship",
                    severity="info",
                    citation=f"{cr.citation_a} vs {cr.citation_b}",
                    detail=cr.detail,
                    source_evidence=cr.evidence,
                    affected_element=affected_element,
                ))

        # 3. Check for citations without verifiable evidence
        for cite in citations:
            prov_status = cite.get("provenance_status", "")
            if prov_status and prov_status not in ("VERIFIED", "PARTIAL"):
                defects.append(ValidationDefect(
                    defect_type="no_evidence",
                    severity="warning",
                    citation=f"{cite.get('document', '?')} art. {cite.get('article', '?')}",
                    detail=f"Citation has provenance_status='{prov_status}' — not verifiable.",
                    source_evidence="provenance_status field",
                    affected_element=affected_element,
                ))

        # 4. Determine ok/block
        blocking_count = sum(1 for d in defects if d.severity == "blocking")
        ok = blocking_count == 0

        self._log.info(
            "adversarial.validate",
            citations=len(citations),
            defects=len(defects),
            blocking=blocking_count,
            ok=ok,
        )

        return ValidationResult(
            ok=ok,
            defects=defects,
            vigency_results=vigency_results,
            contradiction_results=contradiction_results,
        )
