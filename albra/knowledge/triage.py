"""
Knowledge Triage - clasifica preguntas jurídicas y las enruta
al tipo de fuente correcto (normativa vs. jurisprudencia vs. doctrina).

Esto evita buscar en todo el knowledge layer cuando se sabe que la
pregunta es sobre un artículo específico de ley.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TriageResult:
    question_type: str  # statute | jurisprudence | doctrine | procedure | mixed
    suggested_sources: list[str] = field(default_factory=list)
    confidence: float = 0.0
    keywords: list[str] = field(default_factory=list)
    jurisdiction: str = "CO"


class KnowledgeTriage:
    """Clasificador heurístico de preguntas jurídicas."""

    STATUTE_KW = (
        "artículo", "articulo", "ley", "código", "codigo", "estatuto",
        "reglamento", "decreto", "resolución", "resolucion",
        "constitución", "constitucion", "norma", "parágrafo", "paragrafo",
        "numeral", "literal",
    )
    JURISPRUDENCE_KW = (
        "jurisprudencia", "sentencia", "fallos", "precedente",
        "corte suprema", "corte constitucional", "consejo de estado",
        "magistrado", "auto", "providencia",
    )
    DOCTRINE_KW = (
        "doctrina", "autor", "tratadista", "comentario",
        "estudio", "análisis", "analisis", "opinión", "opinion",
    )
    PROCEDURE_KW = (
        "procedimiento", "trámite", "tramite", "competencia",
        "término", "termino", "plazo", "oportunidad procesal",
        "recurso", "apelación", "apelacion", "sustanciación",
        "sustanciacion",
    )

    def triage(self, question: str, *, jurisdiction: str = "CO") -> TriageResult:
        q = question.lower()
        kw_statute = [k for k in self.STATUTE_KW if k in q]
        kw_jurisp = [k for k in self.JURISPRUDENCE_KW if k in q]
        kw_doctrine = [k for k in self.DOCTRINE_KW if k in q]
        kw_procedure = [k for k in self.PROCEDURE_KW if k in q]

        counts = {
            "statute": len(kw_statute),
            "jurisprudence": len(kw_jurisp),
            "doctrine": len(kw_doctrine),
            "procedure": len(kw_procedure),
        }
        total = sum(counts.values())
        if total == 0:
            return TriageResult(
                question_type="mixed",
                suggested_sources=["normative", "jurisprudence", "doctrine"],
                confidence=0.3,
                keywords=[],
                jurisdiction=jurisdiction,
            )

        max_type = max(counts, key=lambda k: counts[k])
        # Si hay varios tipos con conteo alto → mixed
        multi_high = sum(1 for v in counts.values() if v > 0)
        if multi_high >= 2:
            return TriageResult(
                question_type="mixed",
                suggested_sources=["normative", "jurisprudence", "doctrine"],
                confidence=0.6,
                keywords=kw_statute + kw_jurisp + kw_doctrine + kw_procedure,
                jurisdiction=jurisdiction,
            )

        suggested = {
            "statute": ["normative_official", "statutes"],
            "jurisprudence": ["jurisprudence_official", "courts"],
            "doctrine": ["doctrine", "academic"],
            "procedure": ["procedural_codes", "statutes"],
        }[max_type]

        all_kw = {
            "statute": kw_statute,
            "jurisprudence": kw_jurisp,
            "doctrine": kw_doctrine,
            "procedure": kw_procedure,
        }[max_type]

        confidence = min(0.95, 0.5 + (counts[max_type] / 10))
        return TriageResult(
            question_type=max_type,
            suggested_sources=suggested,
            confidence=confidence,
            keywords=all_kw,
            jurisdiction=jurisdiction,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "categories": ["statute", "jurisprudence", "doctrine", "procedure", "mixed"],
            "description": "Heurístico de triage de preguntas jurídicas",
        }
