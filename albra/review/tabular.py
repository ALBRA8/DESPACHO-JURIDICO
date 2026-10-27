"""
TABULAR REVIEW — comparación de cláusulas en tabla (due diligence).

Inspiración clean-room: Prism (tabular review multi-documento), Mike
(review documents), Lawgent (docx-redline + compare_docx blackline).

V2.4-D: comparación N-documentos × M-cláusulas en formato tabla.
Diferencia con V2.2-A Redline DOCX: aquel compara 2 DOCX paragraph por
paragraph; este compara N documentos por cláusula específica.
"""
from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from albra.observability.logger import get_logger

CLAUSE_PATTERNS: dict[str, re.Pattern[str]] = {
    "jurisdiccion": re.compile(
        r"(?:jurisdicci[oó]n|tribunal\s+competente|foro\s+competente|f[oó]ro\s+legal)",
        re.IGNORECASE,
    ),
    "ley_aplicable": re.compile(
        r"(?:ley\s+aplicable|legislaci[oó]n\s+aplicable|derecho\s+aplicable)",
        re.IGNORECASE,
    ),
    "termino": re.compile(
        r"(?:t[eé]rmino|duraci[oó]n|vigencia|plazo)",
        re.IGNORECASE,
    ),
    "precio": re.compile(
        r"(?:precio|valor\s+total|contraprestaci[oó]n|remuneraci[oó]n|pago|honorarios)",
        re.IGNORECASE,
    ),
    "confidencialidad": re.compile(
        r"(?:confidencialidad|informaci[oó]n\s+confidencial|secreto\s+profesional)",
        re.IGNORECASE,
    ),
    "no_competencia": re.compile(
        r"(?:no\s+competencia|no\s+concurrir|exclusividad|pacto\s+de\s+exclusividad)",
        re.IGNORECASE,
    ),
    "propiedad_intelectual": re.compile(
        r"(?:propiedad\s+intelectual|PI\b|derechos?\s+de\s+autor|marcas|patentes)",
        re.IGNORECASE,
    ),
    "indemnizacion": re.compile(
        r"(?:indemnizaci[oó]n|responsabilidad\s+civil|da[ñn]os\s+y\s+perjuicios)",
        re.IGNORECASE,
    ),
    "terminacion": re.compile(
        r"(?:terminaci[oó]n|resoluci[oó]n|causales\s+de\s+terminaci[oó]n|desistimiento)",
        re.IGNORECASE,
    ),
}


@dataclass
class ClauseComparison:
    """Resultado de comparar una cláusula específica en N documentos."""
    clause_name: str
    rows: list[dict[str, Any]] = field(default_factory=list)

    @property
    def present_count(self) -> int:
        return sum(1 for r in self.rows if r["present"])

    @property
    def absent_count(self) -> int:
        return sum(1 for r in self.rows if not r["present"])

    @property
    def divergence_score(self) -> float:
        """0.0 = todos presentes con mismo texto, 1.0 = todos divergentes."""
        if not self.rows:
            return 0.0
        texts = [r["clause_text"] for r in self.rows if r["present"]]
        if not texts:
            return 1.0
        unique_texts = set(texts)
        if len(unique_texts) == 1:
            return 0.0
        return (len(unique_texts) - 1) / (len(texts) - 1) if len(texts) > 1 else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "clause_name": self.clause_name,
            "rows": self.rows,
            "present_count": self.present_count,
            "absent_count": self.absent_count,
            "divergence_score": self.divergence_score,
        }


class TabularReview:
    """Comparación N-documentos × M-cláusulas en tabla."""

    def __init__(self, documents: list[dict[str, Any]] | None = None) -> None:
        self.log = get_logger("albra.review.tabular")
        self.documents: list[dict[str, Any]] = []
        if documents:
            for doc in documents:
                self.add_document(doc)

    def add_document(self, doc: dict[str, Any]) -> None:
        doc_id = doc.get("id") or uuid.uuid4().hex
        name = doc.get("name", doc_id)
        if "clauses" in doc:
            clauses = doc["clauses"]
        elif "full_text" in doc:
            clauses = self._extract_clauses_from_text(doc["full_text"])
        else:
            clauses = []
        self.documents.append({
            "id": doc_id,
            "name": name,
            "clauses": clauses,
        })

    def _extract_clauses_from_text(self, text: str) -> list[dict[str, str]]:
        paragraphs = re.split(r"\n\s*\n", text)
        clauses: list[dict[str, str]] = []
        for para in paragraphs:
            para = para.strip()
            if len(para) < 20:
                continue
            for clause_name, pattern in CLAUSE_PATTERNS.items():
                if pattern.search(para):
                    clauses.append({"name": clause_name, "text": para})
                    break
        return clauses

    def extract_clause(self, doc: dict[str, Any], clause_name: str) -> str | None:
        if clause_name not in CLAUSE_PATTERNS:
            raise ValueError(f"Unknown clause name: {clause_name}")
        pattern = CLAUSE_PATTERNS[clause_name]
        for clause in doc["clauses"]:
            if pattern.search(clause["text"]):
                return clause["text"]
        for clause in doc["clauses"]:
            if clause.get("name") == clause_name:
                return clause["text"]
        return None

    def compare_clauses(self, clause_name: str) -> ClauseComparison:
        comp = ClauseComparison(clause_name=clause_name)
        for doc in self.documents:
            clause_text = self.extract_clause(doc, clause_name)
            comp.rows.append({
                "doc_id": doc["id"],
                "doc_name": doc["name"],
                "clause_text": clause_text or "",
                "present": clause_text is not None,
            })
        return comp

    def export_markdown_table(self, clause_name: str) -> str:
        comp = self.compare_clauses(clause_name)
        lines = [
            f"## Tabular Review: {clause_name}",
            "",
            "| Documento | Presente | Texto |",
            "|---|---|---|",
        ]
        for row in comp.rows:
            present_emoji = "OK" if row["present"] else "—"
            text = row["clause_text"][:80].replace("|", "\\|").replace("\n", " ") if row["present"] else ""
            lines.append(f"| {row['doc_name']} | {present_emoji} | {text} |")
        lines.append("")
        lines.append(
            f"**Presentes:** {comp.present_count}/{len(comp.rows)} - "
            f"**Divergencia:** {comp.divergence_score:.2f}"
        )
        return "\n".join(lines)

    def export_csv(self, clause_name: str) -> str:
        comp = self.compare_clauses(clause_name)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["doc_id", "doc_name", "present", "clause_text"])
        for row in comp.rows:
            writer.writerow([
                row["doc_id"], row["doc_name"], row["present"],
                row["clause_text"],
            ])
        return output.getvalue()

    def divergence_report(
        self, clause_names: list[str] | None = None
    ) -> dict[str, Any]:
        if clause_names is None:
            clause_names = list(CLAUSE_PATTERNS.keys())
        results: list[ClauseComparison] = []
        for name in clause_names:
            results.append(self.compare_clauses(name))
        high_div = [c.clause_name for c in results if c.divergence_score >= 0.5]
        uniform = [c.clause_name for c in results if c.divergence_score == 0 and c.present_count > 0]
        absent = [c.clause_name for c in results if c.absent_count == len(c.rows)]
        return {
            "clauses": [c.as_dict() for c in results],
            "total_documents": len(self.documents),
            "high_divergence_clauses": high_div,
            "uniform_clauses": uniform,
            "absent_clauses": absent,
        }

    def list_supported_clause_names(self) -> list[str]:
        return sorted(CLAUSE_PATTERNS.keys())

    def stats(self) -> dict[str, Any]:
        return {
            "total_documents": len(self.documents),
            "supported_clauses": list(CLAUSE_PATTERNS.keys()),
            "supported_clauses_count": len(CLAUSE_PATTERNS),
        }
