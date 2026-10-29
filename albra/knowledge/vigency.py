"""V8.0 Fase 2 — VigencyChecker.

Verifica la vigencia de normas citadas en el corpus V1.4.

DISCIPLINA V8.0:
  - No confundir ausencia de información con evidencia de vigencia.
  - Si la vigencia no puede demostrarse mediante los datos disponibles,
    el sistema representa explícitamente la incertidumbre.
  - NO inventar derogaciones, fechas, normas modificatorias, vigencia
    ni efectos jurídicos.

El checker opera sobre dos fuentes de información:
  1. Document-level: ``status`` y ``effective_until`` del documento.
  2. Article-text-level: marcadores embebidos en el texto del artículo
     (ej. "modificado por el artículo X de la Ley Y", "derogado por",
     "sustituido por", "texto original revivido según Sentencia C-NNN").

Resultado estructurado: ``VigencyResult`` con:
  - ``status``: "vigent" | "modified" | "superseded" | "uncertain"
  - ``superseded_by``: str (referencia a la norma modificatoria, si
    se puede extraer del texto; "" si no se encuentra)
  - ``superseded_at``: str (fecha de la modificación, si se puede
    extraer; "" si no se encuentra)
  - ``reason``: explicación de por qué se asignó el status
  - ``evidence_source``: "document_metadata" | "article_text_marker" |
    "no_evidence"
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from albra.observability.logger import get_logger


@dataclass(frozen=True)
class VigencyResult:
    """Resultado de la verificación de vigencia de una norma."""
    status: str  # "vigent" | "modified" | "superseded" | "uncertain"
    superseded_by: str = ""
    superseded_at: str = ""
    reason: str = ""
    evidence_source: str = "no_evidence"  # "document_metadata" | "article_text_marker" | "no_evidence"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "superseded_by": self.superseded_by,
            "superseded_at": self.superseded_at,
            "reason": self.reason,
            "evidence_source": self.evidence_source,
        }


# ===== Patterns for vigency markers in article text =====

# "modificado por" — detect modification markers. We only need the
# marker itself to know the article has been modified; the exact
# reference (which law/article) is extracted for the reason text
# but is not required for classification.
_MODIFICADO_POR = re.compile(
    r'modificado\s+por\s+(.+?)(?:\.|$)',
    re.IGNORECASE,
)
# "derogado por" — explicit derogation
_DEROGADO_POR = re.compile(
    r'derogad[oa]\s+por\s+(.+?)(?:\.|$)',
    re.IGNORECASE,
)
# "sustituido por" — explicit substitution
_SUSTITUIDO_POR = re.compile(
    r'sustituid[oa]\s+por\s+(.+?)(?:\.|$)',
    re.IGNORECASE,
)
# "texto original revivido según la Sentencia C-NNN-NN" — special case
_REVIVIDO_SENTENCIA = re.compile(
    r'texto\s+original\s+revivid[oa]\s+seg[uú]n\s+(?:la\s+)?Sentencia\s+([A-Z]+-\d+-\d+)',
    re.IGNORECASE,
)


class VigencyChecker:
    """Verifica la vigencia de normas citadas en el corpus V1.4.

    El checker NO inventa información. Si no puede determinar la
    vigencia a partir de los datos disponibles, retorna ``uncertain``.
    """

    def __init__(self) -> None:
        self._log = get_logger("albra.knowledge.vigency")

    def check(
        self,
        *,
        document: dict[str, Any],
        article: dict[str, Any] | None = None,
    ) -> VigencyResult:
        """Verifica la vigencia de un documento o artículo específico.

        Args:
            document: El dict del documento del corpus V1.4.
            article: El dict del artículo (con ``number`` y ``text``).
                Si es None, verifica solo a nivel de documento.

        Returns:
            VigencyResult con el status determinado.
        """
        doc_status = document.get("status", "")
        doc_effective_until = document.get("effective_until")

        # 1. Document-level check
        if doc_effective_until is not None and doc_effective_until != "":
            # The document has an explicit end date → superseded
            return VigencyResult(
                status="superseded",
                superseded_by="document_effective_until",
                superseded_at=str(doc_effective_until),
                reason=f"Document effective_until={doc_effective_until}",
                evidence_source="document_metadata",
            )

        if doc_status and doc_status.lower() not in ("vigente", "en_vigor", "in_force"):
            # Document status is not "vigente"
            return VigencyResult(
                status="superseded",
                reason=f"Document status='{doc_status}' (not vigente)",
                evidence_source="document_metadata",
            )

        # 2. Article-level check (if article provided)
        if article is None:
            # Only document-level check done → vigent at document level
            return VigencyResult(
                status="vigent",
                reason="Document status is 'vigente' with no effective_until. No article-level check performed.",
                evidence_source="document_metadata",
            )

        article_text = article.get("text", "")
        if not article_text:
            return VigencyResult(
                status="uncertain",
                reason="Article has no text — cannot determine vigency.",
                evidence_source="no_evidence",
            )

        # Check for derogation markers
        derog_match = _DEROGADO_POR.search(article_text)
        if derog_match:
            superseded_by = derog_match.group(1).strip()[:200]
            return VigencyResult(
                status="superseded",
                superseded_by=superseded_by,
                reason="Article text contains 'derogado por' marker.",
                evidence_source="article_text_marker",
            )

        # Check for substitution markers
        sust_match = _SUSTITUIDO_POR.search(article_text)
        if sust_match:
            superseded_by = sust_match.group(1).strip()[:200]
            return VigencyResult(
                status="superseded",
                superseded_by=superseded_by,
                reason="Article text contains 'sustituido por' marker.",
                evidence_source="article_text_marker",
            )

        # Check for "texto original revivido" — special case: the article
        # was previously superseded but its original text was revived by
        # a Constitutional Court sentence. It's vigent again.
        revivido_match = _REVIVIDO_SENTENCIA.search(article_text)
        if revivido_match:
            sentencia = revivido_match.group(1)
            return VigencyResult(
                status="modified",
                superseded_by=f"Sentencia {sentencia} (texto original revivido)",
                reason=f"Article text was revived by Sentencia {sentencia}. Currently vigent but with modification history.",
                evidence_source="article_text_marker",
            )

        # Check for modification markers
        mod_match = _MODIFICADO_POR.search(article_text)
        if mod_match:
            ref_text = mod_match.group(1).strip()[:200]
            return VigencyResult(
                status="modified",
                superseded_by=ref_text,
                reason=f"Article text contains 'modificado por' marker referencing {ref_text}.",
                evidence_source="article_text_marker",
            )

        # No markers found → vigent (based on document status + absence of modification markers)
        return VigencyResult(
            status="vigent",
            reason="Document status is 'vigente'. No modification/derogation/sustitution markers found in article text.",
            evidence_source="document_metadata",
        )

    def check_citation(
        self,
        *,
        document_slug: str,
        article_number: str,
        corpus: list[tuple[str, dict[str, Any]]],
    ) -> VigencyResult:
        """Convenience method: check a citation by document slug + article number.

        Args:
            document_slug: The slug of the document in the corpus.
            article_number: The article number as a string.
            corpus: The corpus list (e.g. ALL_DOCUMENTS_V14).

        Returns:
            VigencyResult. If the document or article is not found,
            returns ``uncertain``.
        """
        # Find the document
        doc = None
        for slug, d in corpus:
            if slug == document_slug:
                doc = d
                break
        if doc is None:
            return VigencyResult(
                status="uncertain",
                reason=f"Document '{document_slug}' not found in corpus.",
                evidence_source="no_evidence",
            )

        # Find the article
        article = None
        for a in doc.get("articles", []):
            if str(a.get("number")) == str(article_number):
                article = a
                break
        if article is None:
            return VigencyResult(
                status="uncertain",
                reason=f"Article {article_number} not found in document '{document_slug}'.",
                evidence_source="no_evidence",
            )

        return self.check(document=doc, article=article)
