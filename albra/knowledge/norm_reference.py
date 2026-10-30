"""V8.0 Fase 3 — NormReference: cross-reference resolver + hierarchy derivation.

Resolves explicit article-to-article references found in the corpus V1.4
text to structured NormReference objects. Only references where BOTH
source and target exist in V1.4 are marked as ``verified``.

DISCIPLINA V8.0 Fase 3:
  - No construir relaciones para los 105 marcadores de modificación
    (todos apuntan a leyes externas no en corpus — ya detectados por
    VigencyChecker como modified/superseded).
  - Solo resolver cross-references artículo→artículo verificables.
  - La jerarquía normativa es una propiedad DERIVADA del document_type,
    no una relación almacenada.
  - ``references`` NO es una contradicción. Una referencia es
    informativa: un artículo menciona a otro. No implica oposición,
    modificación, ni prevalencia automática.
  - ``uncertain`` nunca produce blocking en AdversarialValidator.
  - ``verified`` tampoco produce blocking por sí sola — solo aporta
    evidencia contextual.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from albra.observability.logger import get_logger


@dataclass(frozen=True)
class NormReference:
    """A cross-reference between two articles, resolved against V1.4.

    Fields:
        source_doc: slug of the source document in corpus.
        source_article: article number string.
        target_doc: slug of the target document, or "" if not in corpus.
        target_article: article number string, or "" if not identified.
        reference_type: "references" (informational mention).
        evidence: the text fragment containing the reference.
        evidence_source: "article_text_cross_reference".
        source_location: "art. N of document_slug".
        confidence: "verified" if both source and target in V1.4,
                    "uncertain" otherwise.
    """
    source_doc: str
    source_article: str
    target_doc: str
    target_article: str
    reference_type: str = "references"
    evidence: str = ""
    evidence_source: str = "article_text_cross_reference"
    source_location: str = ""
    confidence: str = "uncertain"  # "verified" | "uncertain"

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_doc": self.source_doc,
            "source_article": self.source_article,
            "target_doc": self.target_doc,
            "target_article": self.target_article,
            "reference_type": self.reference_type,
            "evidence": self.evidence,
            "evidence_source": self.evidence_source,
            "source_location": self.source_location,
            "confidence": self.confidence,
        }


# ===== Hierarchy derivation =====

# Colombian normative hierarchy derived from document_type.
# Only two levels exist in V1.4:
#   1. constitucion (highest — Constitución is norma de normas, art. 4)
#   2. ley / codigo_sustantivo (legislative rank — same level)
#
# "codigo_sustantivo" (CST = Decreto 2663 de 1950) is a Decreto-Ley
# with force of law — NOT a separate rank. "Código" is a name, not a rank.
_HIERARCHY_RANK: dict[str, int] = {
    "constitucion": 1,      # highest
    "ley": 2,               # legislative
    "codigo_sustantivo": 2,  # Decreto-Ley — same as ley
}


def get_hierarchy_rank(document_type: str) -> int:
    """Return the hierarchy rank of a document type.

    Returns:
        1 for constitucion (highest), 2 for ley/codigo_sustantivo.
        999 for unknown types (treated as lowest — conservative).
    """
    return _HIERARCHY_RANK.get(document_type, 999)


def compare_hierarchy(doc_type_a: str, doc_type_b: str) -> str:
    """Compare the hierarchy rank of two document types.

    Returns:
        "higher" if A is higher rank than B.
        "lower" if A is lower rank than B.
        "equal" if same rank.
        "unknown" if either type is not recognized.
    """
    rank_a = _HIERARCHY_RANK.get(doc_type_a)
    rank_b = _HIERARCHY_RANK.get(doc_type_b)
    if rank_a is None or rank_b is None:
        return "unknown"
    if rank_a < rank_b:
        return "higher"
    if rank_a > rank_b:
        return "lower"
    return "equal"


# ===== Cross-reference resolver =====

# Patterns for article cross-references.
# We look for "artículo N de la Constitución", "artículo N de la Ley X",
# "artículo N del Código Y", etc.
_CROSS_REF_PATTERNS = [
    # "artículo N de la Constitución" / "artículos N y M de la Constitución"
    re.compile(
        r'art[ií]culo[s]?\s+(\d+(?:\s+y\s+\d+)*)\s+de\s+(?:la\s+)?Constituci[oó]n',
        re.IGNORECASE,
    ),
    # "artículo N de la Ley X de YYYY"
    re.compile(
        r'art[ií]culo[s]?\s+(\d+(?:\s+y\s+\d+)*)\s+de\s+(?:la\s+)?Ley\s+(\d+)\s+de\s+(\d{4})',
        re.IGNORECASE,
    ),
    # "artículo N del Código Sustantivo del Trabajo"
    re.compile(
        r'art[ií]culo[s]?\s+(\d+(?:\s+y\s+\d+)*)\s+del\s+C[oó]digo\s+Sustantivo\s+del\s+Trabajo',
        re.IGNORECASE,
    ),
    # "artículo N del Código General del Proceso"
    re.compile(
        r'art[ií]culo[s]?\s+(\d+(?:\s+y\s+\d+)*)\s+del\s+C[oó]digo\s+General\s+del\s+Proceso',
        re.IGNORECASE,
    ),
    # "artículo N del Código de Procedimiento Penal"
    re.compile(
        r'art[ií]culo[s]?\s+(\d+(?:\s+y\s+\d+)*)\s+del\s+C[oó]digo\s+de\s+Procedimiento\s+Penal',
        re.IGNORECASE,
    ),
]


def _resolve_target_doc(match_text: str) -> str:
    """Determine which corpus document a reference points to.

    Returns the corpus slug if identifiable, "" otherwise.
    """
    lower = match_text.lower()
    if "constituci" in lower:
        return "constitucion"
    if "ley 1564" in lower or "código general del proceso" in lower or "codigo general del proceso" in lower:
        return "ley_1564_2012"
    if "ley 640" in lower:
        return "ley_0640_2001"
    if "ley 906" in lower or "código de procedimiento penal" in lower or "codigo de procedimiento penal" in lower:
        return "ley_0906_2004"
    if "código sustantivo" in lower or "codigo sustantivo" in lower:
        return "codigo_sustantivo_trabajo"
    return ""


def _extract_article_numbers(group: str) -> list[str]:
    """Extract individual article numbers from a match group like '237' or '18 y 58'."""
    nums = re.findall(r'\d+', group)
    return [str(int(n)) for n in nums]


def resolve_references(
    corpus: list[tuple[str, dict[str, Any]]],
) -> list[NormReference]:
    """Scan all articles in the corpus for cross-references and resolve them.

    Only statutory documents (not jurisprudencia) are scanned as sources.
    Targets are resolved against the same corpus.

    Returns:
        List of NormReference. Only references with BOTH source and
        target in the corpus are ``verified``. References to external
        documents are ``uncertain``.
    """
    log = get_logger("albra.knowledge.norm_reference")
    references: list[NormReference] = []

    # Build a lookup of which articles exist in which documents
    article_index: dict[str, set[str]] = {}
    doc_types: dict[str, str] = {}
    for slug, doc in corpus:
        if doc.get("document_type") == "jurisprudencia":
            continue
        nums = {str(a["number"]) for a in doc.get("articles", [])}
        article_index[slug] = nums
        doc_types[slug] = doc.get("document_type", "")

    for slug, doc in corpus:
        if doc.get("document_type") == "jurisprudencia":
            continue
        for art in doc.get("articles", []):
            text = art["text"]
            art_num = str(art["number"])
            for pattern in _CROSS_REF_PATTERNS:
                for match in pattern.finditer(text):
                    match_text = match.group(0)
                    # Extract article numbers from the match
                    art_nums_raw = match.group(1) if match.lastindex else ""
                    target_nums = _extract_article_numbers(art_nums_raw)
                    # Determine target document
                    target_doc = _resolve_target_doc(match_text)

                    for target_num in target_nums:
                        # Check if target exists in corpus
                        verified = False
                        if target_doc and target_doc in article_index:
                            if target_num in article_index[target_doc]:
                                verified = True

                        ref = NormReference(
                            source_doc=slug,
                            source_article=art_num,
                            target_doc=target_doc if target_doc else "",
                            target_article=target_num,
                            evidence=match_text[:200],
                            source_location=f"art. {art_num} of {slug}",
                            confidence="verified" if verified else "uncertain",
                        )
                        references.append(ref)

    verified_count = sum(1 for r in references if r.confidence == "verified")
    uncertain_count = sum(1 for r in references if r.confidence == "uncertain")
    log.info(
        "norm_reference.resolve",
        total=len(references),
        verified=verified_count,
        uncertain=uncertain_count,
    )
    return references
