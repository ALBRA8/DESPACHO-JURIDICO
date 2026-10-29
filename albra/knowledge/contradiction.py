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

        # 2. Check for modification/supersession relationship.
        # V8.0 Fase 2.2: unified regex with vigency.py. Now matches
        # ALL modification-type markers consistently:
        #   "modificado por", "adicionado por", "subrogado por",
        #   "sustituido por", "derogado por"
        mod_markers = [
            ("modificado por", _MODIFICADO_POR),
            ("adicionado por", _ADICIONADO_POR),
            ("subrogado por", _SUBROGADO_POR),
            ("sustituido/derogado por", _SUSTITUIDO_POR),
        ]
        for marker_name, pattern in mod_markers:
            match_a = pattern.search(text_a) if text_a else None
            match_b = pattern.search(text_b) if text_b else None
            if match_a or match_b:
                which = "article A" if match_a else "article B"
                return ContradictionResult(
                    citation_a=label_a, citation_b=label_b,
                    relation="modification",
                    detail=f"{which} has a '{marker_name}' marker. This indicates a hierarchical modification relationship, not a contradiction.",
                    evidence=f"{marker_name} marker found in article text",
                )

        # 3. Check for explicit textual conflict.
        # V8.0 Fase 2.2: implemented with strict, evidence-based criteria.
        # See _check_explicit_conflict_markers docstring for details.
        conflict_marker = self._check_explicit_conflict_markers(text_a, text_b, cite_a, cite_b)
        if conflict_marker:
            return ContradictionResult(
                citation_a=label_a, citation_b=label_b,
                relation="explicit_conflict",
                detail=conflict_marker,
                evidence="Explicit cross-reference indicating incompatibility found in article text",
            )

        # 4. Default: not determinable
        return ContradictionResult(
            citation_a=label_a, citation_b=label_b,
            relation="not_determinable",
            detail="No evidence of explicit conflict or modification relationship. Without a legal ontology, contradiction cannot be determined automatically.",
        )

    def _check_explicit_conflict_markers(
        self, text_a: str, text_b: str,
        cite_a: dict[str, Any] | None = None,
        cite_b: dict[str, Any] | None = None,
    ) -> str:
        """Check for explicit conflict markers between two cited articles.

        V8.0 Fase 2.2: implemented with strict, evidence-based criteria.

        This method looks for CROSS-REFERENCES where one cited article
        EXPLICITLY declares incompatibility with the OTHER cited article.
        It does NOT infer conflicts from semantic similarity, shared
        subject matter, or general opposition language.

        ACTIVATION CRITERIA (all must be met):
          1. One article's text contains a marker of explicit
             incompatibility ("incompatible con", "contraviene",
             "en contravía de").
          2. The marker is followed by a reference to a SPECIFIC
             article number that matches the OTHER cited article's
             number.
          3. The reference includes a document name/type that matches
             the other cited article's document.

        MARKERS EVALUATED:
          - "incompatible con el artículo N" → checks if N matches
            the other cited article's number.
          - "contraviene el artículo N" / "contravienen los artículos N"
            → checks if N matches.
          - "en contravía de lo dispuesto en el artículo N" → checks
            if N matches.

        MARKERS NOT TREATED AS CONFLICTS (with documented reasoning):
          - "no obstante" → creates an EXCEPTION, not a contradiction.
            The general rule and the exception coexist by design.
          - "se exceptúa" → same as "no obstante".
          - "sin perjuicio de" → means "without prejudice to" — both
            norms apply concurrently. NOT a conflict.
          - "se opone a" → in the corpus, this refers to a PERSON
            opposing an action (not a norm opposing a norm).
          - "en oposición a" → in the corpus, refers to political
            opposition, not legal norm conflict.

        Returns:
            A non-empty string describing the conflict if found.
            Empty string if no explicit conflict is detected
            (honest abstention).
        """
        if not text_a or not text_b:
            return ""
        if cite_a is None or cite_b is None:
            return ""

        art_a_num = str(cite_a.get("article", ""))
        art_b_num = str(cite_b.get("article", ""))
        str(cite_a.get("document", "")).lower()
        str(cite_b.get("document", "")).lower()

        # Patterns for explicit incompatibility + cross-reference.
        # Each pattern captures the article number(s) referenced.
        incompat_patterns = [
            # "incompatible con el artículo N" or "incompatible con los artículos N, M"
            re.compile(
                r'incompatible\s+(?:con\s+)?(?:el|los)\s+art[ií]culos?\s+(\d+(?:\s*,\s*\d+)*)',
                re.IGNORECASE,
            ),
            # "contraviene el artículo N" or "contravienen los artículos N"
            re.compile(
                r'contraviene[n]?\s+(?:el|los)\s+art[ií]culos?\s+(\d+(?:\s*,\s*\d+)*)',
                re.IGNORECASE,
            ),
            # "en contravía de lo dispuesto en el artículo N"
            re.compile(
                r'en\s+contrav[ií]a\s+de\s+(?:lo\s+dispuesto\s+en\s+)?(?:el|los)\s+art[ií]culos?\s+(\d+(?:\s*,\s*\d+)*)',
                re.IGNORECASE,
            ),
        ]

        # Check text_a for references to art_b_num
        for pat in incompat_patterns:
            match = pat.search(text_a)
            if match:
                referenced_nums = [n.strip() for n in match.group(1).split(",")]
                if art_b_num in referenced_nums:
                    return (
                        f"Article {cite_a.get('document', '')} art. {art_a_num} "
                        f"explicitly references art. {art_b_num} as incompatible "
                        f"(marker: '{match.group(0)[:80]}')."
                    )

        # Check text_b for references to art_a_num
        for pat in incompat_patterns:
            match = pat.search(text_b)
            if match:
                referenced_nums = [n.strip() for n in match.group(1).split(",")]
                if art_a_num in referenced_nums:
                    return (
                        f"Article {cite_b.get('document', '')} art. {art_b_num} "
                        f"explicitly references art. {art_a_num} as incompatible "
                        f"(marker: '{match.group(0)[:80]}')."
                    )

        # No explicit cross-reference conflict found → honest abstention
        return ""


# V8.0 Fase 2.2: unified patterns — same simplified form as vigency.py.
# This resolves HALLAZGO 2 (regex inconsistency between the two modules).
_MODIFICADO_POR = re.compile(
    r'modificado\s+por\s+(.+?)(?:\.|$)',
    re.IGNORECASE,
)
_ADICIONADO_POR = re.compile(
    r'adicionad[oa]\s+por\s+(.+?)(?:\.|$)',
    re.IGNORECASE,
)
_SUBROGADO_POR = re.compile(
    r'subrogad[oa]\s+por\s+(.+?)(?:\.|$)',
    re.IGNORECASE,
)
_SUSTITUIDO_POR = re.compile(
    r'(?:sustituid[oa]|derogad[oa])\s+por\s+(.+?)(?:\.|$)',
    re.IGNORECASE,
)
