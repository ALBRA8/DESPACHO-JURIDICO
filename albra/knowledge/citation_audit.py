"""
CITATION AUDIT PRE-REVEAL — fail-closed anti-hallucination.

Pipeline de 4 etapas antes de revelar respuesta del LLM al abogado:
1. extract_citations(text)   — regex que detecta citas jurídicas
2. validate_against_corpus() — busca en albra/knowledge/colombia/corpus_pilot/
3. retrace_quotes()          — si hay quote literal, verifica que aparece en source
4. reveal_or_block()         — si todo pasa: revela; si algo falla: marca unverified

REGLA CRÍTICA (anti-hallucination): el agente NUNCA revela respuesta con citas
no verificadas al abogado. Marca como `unverified` y pide confirmación manual.

Citas soportadas (V2.0):
- Constitución 1991, artículos 1,2,5,13,25,29
- Ley 100 de 1993, artículos 1,2,3
- Ley 80 de 1993, artículos 1,2,24

Documentos rechazados honestamente (V1.1) — no aparecen en corpus:
- Ley 1480/2011 (no fetchable)
- Sentencia C-251/2002 (no fetchable)
- Sentencia T-760/2008 (no fetchable)
- Sentencia AR-001/2020 (era sintética)
- Doctrina Temis (era sintética)

Si el LLM cita alguno de estos → BLOCKED con reason claro al abogado.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from albra.knowledge.colombia.corpus_pilot.real_corpus_v11 import (
    ALL_DOCUMENTS,
    REJECTED_DOCUMENTS,
)
from albra.observability.logger import get_logger

# Documentos rechazados (lookup rápido por nombre)
_REJECTED_NAMES: frozenset[str] = frozenset(
    r["name"] for r in REJECTED_DOCUMENTS
)


# Patrones de cita jurídica colombiana
_CITATION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Constitución: "Constitución Política [de] [1991], artículo 13"
    # o "artículo 13 de la Constitución"
    ("constitucion_articulo",
     re.compile(
         r"(?:art[ií]culo\s+(?P<art_num>\d{1,3})\s+de\s+la\s+)?"
         r"Constituci[oó]n\s*(?:Pol[ií]tica\s*)?(?:de\s+(?P<year>1991|1886))?",
         re.IGNORECASE)),
    # Constitución: "artículo 13 de la Constitución"
    ("constitucion_articulo_alt",
     re.compile(
         r"art[ií]culo\s+(?P<art_num2>\d{1,3})\s+de\s+la\s+Constituci[oó]n",
         re.IGNORECASE)),
    # Ley: "Ley 100 de 1993, artículo 3" o "Ley 100 de 1993"
    ("ley_articulo",
     re.compile(
         r"Ley\s+(?P<ley_num>\d{1,5})\s+de\s+(?P<ley_year>\d{4})"
         r"(?:[,\s]+art[ií]culo\s+(?P<art_num3>\d{1,3}))?",
         re.IGNORECASE)),
    # Sentencias: "Sentencia C-251/2002" o "Sentencia T-760/2008"
    # (acepta singular "Sentencia" o plural "Sentencias")
    ("sentencia",
     re.compile(
         r"Sentencias?\s+(?P<sent_type>[A-Z]+)-(?P<sent_num>\d{1,4})/(?P<sent_year>\d{4})",
         re.IGNORECASE)),
    # Sentencias standalone: "C-251/2002" sin prefijo "Sentencia"
    # Solo tipos colombianos comunes (C, T, SU, SL, MP, A) + año 1990-2030
    ("sentencia_standalone",
     re.compile(
         r"\b(?P<sent_type2>C|T|SU|SL|MP|A)-(?P<sent_num2>\d{1,4})/(?P<sent_year2>199\d|20[0-3]\d)\b"
     )),
]

# Quote pattern: texto entre comillas tipográficas o rectas de ≥10 chars
_QUOTE_PATTERN = re.compile(r'"([^"]{10,})"|“([^”]{10,})”|'r"'([^']{10,})'")


@dataclass
class Citation:
    """Cita jurídica extraída de un texto."""
    raw_text: str
    document_type: str  # constitucion | legislacion | jurisprudencia
    document_name: str  # "Constitución Política de 1991" / "Ley 100 de 1993" / "Sentencia C-251/2002"
    article_number: str | None = None
    quote: str | None = None  # si hay texto entre comillas asociado
    start: int = 0  # posición en el texto original
    end: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "document_type": self.document_type,
            "document_name": self.document_name,
            "article_number": self.article_number,
            "quote": self.quote,
            "start": self.start,
            "end": self.end,
        }


@dataclass
class CitationAuditResult:
    """Resultado del pipeline de citation audit."""
    revealed: bool  # True = safe to reveal; False = BLOCKED
    total_citations: int
    verified: list[Citation] = field(default_factory=list)
    unverified: list[Citation] = field(default_factory=list)
    rejected: list[Citation] = field(default_factory=list)  # docs rechazados honestamente
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "revealed": self.revealed,
            "total_citations": self.total_citations,
            "verified_count": len(self.verified),
            "unverified_count": len(self.unverified),
            "rejected_count": len(self.rejected),
            "verified": [c.as_dict() for c in self.verified],
            "unverified": [c.as_dict() for c in self.unverified],
            "rejected": [c.as_dict() for c in self.rejected],
            "reason": self.reason,
        }


class CitationAuditor:
    """Pipeline fail-closed de citation audit pre-reveal.

    Args:
        corpus_version: "v11" (default, 12 articles) o "v12" (125 articles,
            fetched with Playwright V2.3-E) o "v13" (125 articles with the
            V1.3 DocumentProvenance model applied retroactively — see
            albra.knowledge.provenance).
    """

    def __init__(self, *, corpus_version: str = "v11") -> None:
        self.log = get_logger("albra.knowledge.citation_audit")
        self.corpus_version = corpus_version
        # V1.3 provenance enforcement — default off for backward compatibility.
        # When True, citations from documents with provenance_status='NOT_VERIFIED'
        # are BLOCKED at audit_response time.
        self._provenance_required = False
        # Index corpus for fast lookup
        self._index = self._build_corpus_index()

    def _get_corpus(self) -> list[tuple[str, dict[str, Any]]]:
        """Returns the corpus list based on corpus_version."""
        if self.corpus_version == "v13":
            try:
                from albra.knowledge.colombia.corpus_pilot.real_corpus_v13 import (
                    ALL_DOCUMENTS_V13,
                )
                return ALL_DOCUMENTS_V13
            except ImportError:
                self.log.warning("citation_audit.v13_unavailable_fallback_v12")
                # Fall through to v12.
        if self.corpus_version in ("v12", "v13"):
            try:
                from albra.knowledge.colombia.corpus_pilot.real_corpus_v12 import (
                    ALL_DOCUMENTS_V12,
                )
                return ALL_DOCUMENTS_V12
            except ImportError:
                self.log.warning("citation_audit.v12_unavailable_fallback_v11")
        return ALL_DOCUMENTS

    def _build_corpus_index(self) -> dict[str, dict[str, Any]]:
        """Indexa el corpus por nombre de documento y por número de artículo.

        Handles both V1.1/V1.2 documents (which expose `raw_content`) and
        V1.3 documents (which expose `reconstructed_text`, `provenance`, and
        `provenance_status`). For V1.1/V1.2 documents we default
        `provenance_status` to None (no provenance model was applied).
        """
        index: dict[str, dict[str, Any]] = {}
        for _doc_type, doc in self._get_corpus():
            name = doc["number"]  # e.g. "Constitución Política de 1991"
            # V1.3 documents store reconstructed_text (str) instead of
            # raw_content (bytes). Both yield the same searchable plaintext.
            if "reconstructed_text" in doc:
                raw_text = doc["reconstructed_text"]
            elif "raw_content" in doc:
                raw = doc["raw_content"]
                raw_text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
            else:
                raw_text = ""
            index[name] = {
                "document_type": doc["document_type"],
                "articles": {a["number"]: a["text"] for a in doc["articles"]},
                "raw_text": raw_text,
                "source_url": doc["source_url"],
                # V1.3 provenance fields (None for V1.1/V1.2 documents).
                "provenance_status": doc.get("provenance_status"),
                "provenance": doc.get("provenance"),
            }
        return index

    # ===== Paso 1: extract_citations =====

    def extract_citations(self, text: str) -> list[Citation]:
        """Extrae todas las citas jurídicas del texto."""
        citations: list[Citation] = []
        for pattern_name, pattern in _CITATION_PATTERNS:
            for match in pattern.finditer(text):
                if pattern_name == "constitucion_articulo":
                    art_num = match.group("art_num")
                    year = match.group("year")
                    # Solo Constitución 1991 está en corpus
                    doc_name = "Constitución Política de 1991"
                    if year == "1886":
                        citations.append(Citation(
                            raw_text=match.group(0),
                            document_type="constitucion",
                            document_name="Constitución Política de 1886",
                            article_number=art_num,
                            start=match.start(),
                            end=match.end(),
                        ))
                        continue
                    citations.append(Citation(
                        raw_text=match.group(0),
                        document_type="constitucion",
                        document_name=doc_name,
                        article_number=art_num,
                        start=match.start(),
                        end=match.end(),
                    ))
                elif pattern_name == "constitucion_articulo_alt":
                    art_num = match.group("art_num2")
                    citations.append(Citation(
                        raw_text=match.group(0),
                        document_type="constitucion",
                        document_name="Constitución Política de 1991",
                        article_number=art_num,
                        start=match.start(),
                        end=match.end(),
                    ))
                elif pattern_name == "ley_articulo":
                    ley_num = match.group("ley_num")
                    ley_year = match.group("ley_year")
                    art_num = match.group("art_num3")
                    doc_name = f"Ley {ley_num} de {ley_year}"
                    citations.append(Citation(
                        raw_text=match.group(0),
                        document_type="legislacion",
                        document_name=doc_name,
                        article_number=art_num,
                        start=match.start(),
                        end=match.end(),
                    ))
                elif pattern_name == "sentencia":
                    sent_type = match.group("sent_type").upper()
                    sent_num = match.group("sent_num")
                    sent_year = match.group("sent_year")
                    doc_name = f"Sentencia {sent_type}-{sent_num}/{sent_year}"
                    citations.append(Citation(
                        raw_text=match.group(0),
                        document_type="jurisprudencia",
                        document_name=doc_name,
                        start=match.start(),
                        end=match.end(),
                    ))
                elif pattern_name == "sentencia_standalone":
                    sent_type = match.group("sent_type2").upper()
                    sent_num = match.group("sent_num2")
                    sent_year = match.group("sent_year2")
                    doc_name = f"Sentencia {sent_type}-{sent_num}/{sent_year}"
                    # Evitar duplicados: si ya hay una cita con este doc_name en
                    # posición cercana, saltar
                    already_present = any(
                        c.document_name == doc_name and
                        abs(c.start - match.start()) < 50
                        for c in citations
                    )
                    if already_present:
                        continue
                    citations.append(Citation(
                        raw_text=match.group(0),
                        document_type="jurisprudencia",
                        document_name=doc_name,
                        start=match.start(),
                        end=match.end(),
                    ))
        # Asociar quotes (texto entre comillas) a la cita más cercana
        quotes = self._extract_quotes(text)
        for q_text, q_start, q_end in quotes:
            nearest = self._nearest_citation(citations, q_start)
            if nearest and not nearest.quote:
                nearest.quote = q_text
        return citations

    def _extract_quotes(self, text: str) -> list[tuple[str, int, int]]:
        """Extrae texto entre comillas de ≥10 chars."""
        quotes: list[tuple[str, int, int]] = []
        for match in _QUOTE_PATTERN.finditer(text):
            q = match.group(1) or match.group(2) or match.group(3)
            if q and len(q) >= 10:
                quotes.append((q, match.start(), match.end()))
        return quotes

    def _nearest_citation(
        self,
        citations: list[Citation],
        pos: int,
        max_distance: int = 200,
    ) -> Citation | None:
        """Encuentra la cita más cercana a la posición dada."""
        if not citations:
            return None
        best: Citation | None = None
        best_dist = max_distance
        for c in citations:
            d = min(abs(c.start - pos), abs(c.end - pos))
            if d < best_dist:
                best_dist = d
                best = c
        return best

    # ===== Paso 2: validate_against_corpus =====

    def validate_against_corpus(self, citations: list[Citation]) -> tuple[list[Citation], list[Citation], list[Citation]]:
        """Particiona citations en (verified, unverified, rejected)."""
        verified: list[Citation] = []
        unverified: list[Citation] = []
        rejected: list[Citation] = []
        for c in citations:
            # Check si es documento rechazado
            if c.document_name in _REJECTED_NAMES:
                rejected.append(c)
                continue
            # Check si está en corpus
            if c.document_name not in self._index:
                unverified.append(c)
                continue
            doc = self._index[c.document_name]
            if c.article_number and c.article_number not in doc["articles"]:
                unverified.append(c)
                continue
            verified.append(c)
        return verified, unverified, rejected

    # ===== Paso 3: retrace_quotes =====

    def retrace_quotes(self, verified: list[Citation]) -> list[Citation]:
        """Para citas con quote, verifica que el quote aparezca en el texto fuente."""
        passed: list[Citation] = []
        failed: list[Citation] = []
        for c in verified:
            if not c.quote:
                passed.append(c)
                continue
            doc = self._index[c.document_name]
            source_text = doc["raw_text"]
            # Si hay article_number, buscar solo en ese artículo
            if c.article_number:
                source_text = doc["articles"].get(c.article_number, source_text)
            # Coincidencia exacta (case-insensitive)
            if c.quote.lower() in source_text.lower():
                passed.append(c)
            else:
                # Match parcial: ≥5 palabras consecutivas del quote
                words = c.quote.lower().split()
                if len(words) >= 5:
                    snippet = " ".join(words[:5])
                    if snippet in source_text.lower():
                        passed.append(c)
                        continue
                failed.append(c)
        return passed, failed

    # ===== Paso 4: audit_response (orquestador) =====

    def audit_response(
        self,
        text: str,
        *,
        require_provenance: bool | None = None,
    ) -> CitationAuditResult:
        """Pipeline completo: extract → validate → retrace → reveal_or_block.

        Args:
            text: Response text to audit before revealing to the lawyer.
            require_provenance: If True, citations from documents with
                `provenance_status='NOT_VERIFIED'` are BLOCKED. If None (default),
                falls back to the instance's `_provenance_required` flag (which
                defaults to False for backward compatibility).
        """
        if require_provenance is None:
            require_provenance = self._provenance_required

        citations = self.extract_citations(text)
        verified, unverified, rejected = self.validate_against_corpus(citations)

        # Re-trace quotes solo en verified
        passed_quotes, failed_quotes = self.retrace_quotes(verified)

        # Los que fallaron el retrace se mueven a unverified
        verified = passed_quotes
        unverified.extend(failed_quotes)

        # V1.3: optional provenance enforcement. When require_provenance=True,
        # citations from documents with provenance_status='NOT_VERIFIED' are
        # moved from verified to unverified (blocking the response).
        provenance_blocked: list[Citation] = []
        if require_provenance:
            still_verified: list[Citation] = []
            for c in verified:
                doc = self._index.get(c.document_name, {})
                if doc.get("provenance_status") == "NOT_VERIFIED":
                    provenance_blocked.append(c)
                else:
                    still_verified.append(c)
            verified = still_verified
            unverified.extend(provenance_blocked)

        total = len(citations)
        revealed = len(unverified) == 0 and len(rejected) == 0

        reason = ""
        if not citations:
            reason = "No citations found — no audit needed."
        elif revealed:
            reason = f"All {len(verified)} citations verified against corpus."
        else:
            parts = []
            if unverified:
                parts.append(
                    f"{len(unverified)} unverified (not in corpus or quote mismatch"
                    + (
                        "; provenance_status=NOT_VERIFIED" if provenance_blocked else ""
                    )
                    + ")"
                )
            if rejected:
                parts.append(
                    f"{len(rejected)} rejected (honestly — content not fetchable)"
                )
            reason = (
                "BLOCKED: " + "; ".join(parts) + ". Fail-closed: response not revealed."
            )

        self.log.info(
            "citation_audit.complete",
            total=total, verified=len(verified),
            unverified=len(unverified), rejected=len(rejected),
            revealed=revealed, require_provenance=require_provenance,
            provenance_blocked=len(provenance_blocked),
        )
        return CitationAuditResult(
            revealed=revealed,
            total_citations=total,
            verified=verified,
            unverified=unverified,
            rejected=rejected,
            reason=reason,
        )
