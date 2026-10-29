"""V8.0 Fase 2 — ContradictionDetector.

Detecta conflictos jurídicos explícitos o estructuralmente verificables
entre las normas citadas en un caso.

DISCIPLINA V8.0:
  - No convertir cualquier diferencia entre dos normas en una
    "contradicción".
  - Distingue entre: conflicto explícito, modificación/sustitución,
    normas complementarias, y conflicto no determinable.
  - Si no existe evidencia suficiente para afirmar contradicción,
    el sistema se abstiene.

El detector opera sobre la lista de citas verificadas (cada cita tiene
document_slug, article_number, article_text). Examina pares de citas
buscando:

  1. **Conflicto explícito**: una norma dice A, la otra dice no-A,
     y ambas regulan el mismo aspecto. Esto requiere evidencia
     textual en el corpus — el detector NO infiere conflictos.
  2. **Modificación/sustitución**: una norma modifica o sustituye a la
     otra (detectable por marcadores "modificado por" en el texto).
     Esto NO es una contradicción — es una relación jerárquica.
  3. **Normas complementarias**: las normas regulan aspectos diferentes
     del mismo tema sin oponerse. Tampoco es contradicción.
  4. **No determinable**: sin evidencia suficiente para clasificar.

El detector es conservador: por defecto, dos normas son "no determinable"
a menos que haya evidencia textual explícita de conflicto.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from albra.observability.logger import get_logger


@dataclass(frozen=True)
class ContradictionResult:
    """Resultado del análisis de contradicciones entre un par de citas."""
    citation_a: str  # "document_slug art. N"
    citation_b: str
    relation: str  # "explicit_conflict" | "modification" | "complementary" | "not_determinable"
    detail: str = ""
    evidence: str = ""  # the textual evidence supporting the classification

    def as_dict(self) -> dict[str, Any]:
        return {
            "citation_a": self.citation_a,
            "citation_b": self.citation_b,
            "relation": self.relation,
            "detail": self.detail,
            "evidence": self.evidence,
        }


def _citation_label(doc_slug: str, art_num: str) -> str:
    return f"{doc_slug} art. {art_num}"


class ContradictionDetector:
    """Detecta contradicciones jurídicas entre pares de citas.

    El detector es CONSERVADOR: clasifica como "not_determinable" por
    defecto. Solo clasifica como "explicit_conflict" cuando hay evidencia
    textual directa de oposición.
    """

    def __init__(self) -> None:
        self._log = get_logger("albra.knowledge.contradiction")

    def detect(
        self,
        citations: list[dict[str, Any]],
    ) -> list[ContradictionResult]:
        """Analiza todos los pares de citas buscando contradicciones.

        Args:
            citations: Lista de dicts con ``document``, ``article``,
                ``article_text`` (o ``article_text_preview``).

        Returns:
            Lista de ContradictionResult, uno por cada par analizado.
            Los resultados con ``relation="not_determinable"`` también
            se incluyen para transparencia.
        """
        results: list[ContradictionResult] = []
        n = len(citations)
        for i in range(n):
            for j in range(i + 1, n):
                result = self._check_pair(citations[i], citations[j])
                results.append(result)
        self._log.info(
            "contradiction.detect",
            pairs_analyzed=len(results),
            conflicts=sum(1 for r in results if r.relation == "explicit_conflict"),
            modifications=sum(1 for r in results if r.relation == "modification"),
            not_determinable=sum(1 for r in results if r.relation == "not_determinable"),
        )
        return results

    def _check_pair(
        self,
        cite_a: dict[str, Any],
        cite_b: dict[str, Any],
    ) -> ContradictionResult:
        """Analiza un par de citas."""
        doc_a = cite_a.get("document", "")
        art_a = str(cite_a.get("article", ""))
        doc_b = cite_b.get("document", "")
        art_b = str(cite_b.get("article", ""))
        label_a = _citation_label(doc_a, art_a)
        label_b = _citation_label(doc_b, art_b)

        text_a = cite_a.get("article_text", cite_a.get("article_text_preview", ""))
        text_b = cite_b.get("article_text", cite_b.get("article_text_preview", ""))

        # 1. Check if same document + same article → same norm (not a pair)
        if doc_a == doc_b and art_a == art_b:
            return ContradictionResult(
                citation_a=label_a, citation_b=label_b,
                relation="complementary",
                detail="Same article — not a contradiction.",
            )

        # 2. Check for modification relationship
        # If text_a mentions "modificado por" referencing the same document
        # type as text_b, it's a modification, not a contradiction.
        mod_a = _MODIFICADO_POR.search(text_a) if text_a else None
        mod_b = _MODIFICADO_POR.search(text_b) if text_b else None
        if mod_a or mod_b:
            return ContradictionResult(
                citation_a=label_a, citation_b=label_b,
                relation="modification",
                detail="At least one article has a 'modificado por' marker. This indicates a hierarchical modification relationship, not a contradiction.",
                evidence="modificado por marker found in article text",
            )

        # 3. Check for "sustituido por" / "derogado por"
        sust_a = _SUSTITUIDO_POR.search(text_a) if text_a else None
        sust_b = _SUSTITUIDO_POR.search(text_b) if text_b else None
        if sust_a or sust_b:
            return ContradictionResult(
                citation_a=label_a, citation_b=label_b,
                relation="modification",
                detail="At least one article has a 'sustituido/derogado por' marker. This indicates a supersession relationship, not a contradiction.",
                evidence="sustituido/derogado por marker found in article text",
            )

        # 4. Check for explicit textual conflict
        # This is the conservative check: we look for articles that
        # explicitly reference each other as conflicting, or that
        # use language like "en contravía de", "no obstante",
        # "se exceptúa", etc. — but ONLY when both articles appear
        # to regulate the same subject matter.
        # Since we don't have a legal ontology, we can't automatically
        # determine that two articles regulate the same subject.
        # Therefore, the default is "not_determinable".
        conflict_marker = self._check_explicit_conflict_markers(text_a, text_b)
        if conflict_marker:
            return ContradictionResult(
                citation_a=label_a, citation_b=label_b,
                relation="explicit_conflict",
                detail=conflict_marker,
                evidence="Explicit conflict marker found in article text",
            )

        # 5. Default: not determinable
        return ContradictionResult(
            citation_a=label_a, citation_b=label_b,
            relation="not_determinable",
            detail="No evidence of explicit conflict or modification relationship. Without a legal ontology, contradiction cannot be determined automatically.",
        )

    def _check_explicit_conflict_markers(
        self, text_a: str, text_b: str
    ) -> str:
        """Check for explicit conflict markers between two article texts.

        Returns a non-empty string if a conflict marker is found,
        empty string otherwise.

        This is VERY conservative — it only flags explicit textual
        markers that indicate opposition between the two norms.
        """
        if not text_a or not text_b:
            return ""
        # Check if text_a explicitly contradicts text_b by referencing
        # it. This is rare in statutory text — explicit contradictions
        # are usually resolved through derogation/modification.
        # We look for "no obstante lo dispuesto en" or similar phrases
        # that create exceptions, but ONLY flag as conflict if the
        # exception appears to contradict the general rule.
        #
        # For now, we don't have enough information to determine this
        # automatically. Return "" (no conflict detected).
        return ""


# Re-use the modification patterns from vigency.py for consistency.
_MODIFICADO_POR = re.compile(
    r'modificado\s+por\s+(?:el\s+art[ií]culo\s+)?(\d+)\s+de\s+(?:la\s+)?(?:Ley|Acto\s+Legislativo|Decreto)\s+(\d+\s+de\s+\d{4})',
    re.IGNORECASE,
)
_SUSTITUIDO_POR = re.compile(
    r'(?:sustituid[oa]|derogad[oa])\s+por\s+(.+?)(?:\.|$)',
    re.IGNORECASE,
)
