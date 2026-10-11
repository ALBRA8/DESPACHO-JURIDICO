"""
QUERY CLASSIFICATION - V1.0.

Clasifica consultas jurídicas en 10 tipos diferentes.
Cada tipo activa diferente estrategia de retrieval.

Tipos:
- consulta normativa       → "¿Qué dice la Ley X?"
- consulta jurisprudencial → "¿Cómo interpretó la Corte?"
- consulta doctrinal       → "¿Qué dice la doctrina sobre?"
- consulta histórica       → "¿Qué decía la norma en 1995?"
- consulta de vigencia     → "¿Sigue vigente?"
- consulta comparativa     → "Comparar norma A vs B"
- consulta procesal        → "¿Cuál es el procedimiento?"
- consulta interpretativa  → "¿Cómo se interpreta?"
- consulta artículo específico → "Artículo 200" → pedir aclaración
- consulta de caso         → caso concreto
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Query types
QUERY_NORMATIVE = "consulta_normativa"
QUERY_JURISPRUDENCIAL = "consulta_jurisprudencial"
QUERY_DOCTRINAL = "consulta_doctrinal"
QUERY_HISTORICAL = "consulta_historica"
QUERY_VIGENCIA = "consulta_vigencia"
QUERY_COMPARATIVA = "consulta_comparativa"
QUERY_PROCESAL = "consulta_procesal"
QUERY_INTERPRETATIVA = "consulta_interpretativa"
QUERY_ARTICULO_ESPECIFICO = "consulta_articulo_especifico"
QUERY_CASO = "consulta_caso"
QUERY_UNKNOWN = "unknown"

ALL_QUERY_TYPES = (
    QUERY_NORMATIVE, QUERY_JURISPRUDENCIAL, QUERY_DOCTRINAL, QUERY_HISTORICAL,
    QUERY_VIGENCIA, QUERY_COMPARATIVA, QUERY_PROCESAL, QUERY_INTERPRETATIVA,
    QUERY_ARTICULO_ESPECIFICO, QUERY_CASO, QUERY_UNKNOWN,
)


@dataclass
class QueryClassification:
    query_type: str
    confidence: float = 0.5
    needs_clarification: bool = False
    clarification_question: str = ""
    detected_article: str = ""
    detected_norm: str = ""
    detected_jurisdiction: str = "CO"
    detected_authority: str = ""
    temporal_hint: str = ""  # "current", "historical", "as_of:2020-01-01"
    keywords: list[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "query_type": self.query_type,
            "confidence": self.confidence,
            "needs_clarification": self.needs_clarification,
            "clarification_question": self.clarification_question,
            "detected_article": self.detected_article,
            "detected_norm": self.detected_norm,
            "detected_jurisdiction": self.detected_jurisdiction,
            "detected_authority": self.detected_authority,
            "temporal_hint": self.temporal_hint,
            "keywords": self.keywords or [],
        }


class LegalQueryClassifier:
    """Clasificador de consultas jurídicas colombianas."""

    NORMATIVE_KW = (
        "ley", "decreto", "código", "codigo", "estatuto", "resolución",
        "resolucion", "acuerdo", "reglamento", "norma", "artículo",
        "articulo", "parágrafo", "disposición", "disposicion", "numeral",
    )
    JURISPRUDENCIAL_KW = (
        "jurisprudencia", "sentencia", "casación", "casacion", "precedente",
        "corte constitucional", "corte suprema", "consejo de estado",
        "magistrado", "ponente", "ratio decidendi", "tutela",
    )
    DOCTRINAL_KW = (
        "doctrina", "autor", "tratadista", "libro", "comentario",
                "estudio", "análisis", "opinión",
    )
    HISTORICAL_KW = (
        "decía", "decia", "antes", "versión anterior", "version anterior",
        "originalmente", "en 19", "en 20",
    )
    VIGENCIA_KW = (
        "vigente", "derogada", "derogado", "vigencia", "está vigente",
        "esta vigente", "sigue vigente", "sigue siendo vigente", "vigente aún",
    )
    COMPARATIVA_KW = (
        "comparar", "diferencia", "diferente", "versus", "vs",
        "comparación", "comparacion", "distinto",
    )
    PROCESAL_KW = (
        "procedimiento", "trámite", "tramite", "competencia",
        "término", "termino", "plazo", "recurso", "apelación",
        "sustanciación", "audiencia",
    )
    INTERPRETATIVA_KW = (
        "interpreta", "interpretación", "interpretacion", "entiende",
        "significa", "alcance", "qué quiere decir", "que quiere decir",
    )

    CASO_KW = (
        "mi caso", "este caso", "esta situación", "esta situacion",
        "mi situación", "mi situacion",
    )

    # Regex for article detection
    ARTICLE_PATTERN = re.compile(
        r"art[ií]culo\s+(?:\d+[A-Z]?|primero|segundo|tercero|cuarto|quinto|sexto|s[eé]ptimo|octavo|noveno|d[eé]cimo)",
        re.IGNORECASE,
    )
    # Norm with number (e.g. "Ley 100 de 1993")
    NORM_PATTERN_NUMBERED = re.compile(
        r"(ley|decreto|c[oó]digo|estatuto|resoluci[oó]n|acuerdo|reglamento)\s+\d+\s+de\s+\d{4}",
        re.IGNORECASE,
    )
    # Norm by name (e.g. "Código Civil", "Código Penal", "Constitución Política")
    NORM_PATTERN_NAMED = re.compile(
        r"(c[oó]digo\s+\w+|constituci[oó]n\s+\w*|estatuto\s+\w+|ley\s+\d+)",
        re.IGNORECASE,
    )
    FILE_PATTERN = re.compile(
        r"expediente\s+\w+[\-\/]?\d+|radicado\s+\w+[\-\/]?\d+|T-\d+|STC-\d+|C-\d+",
        re.IGNORECASE,
    )

    def classify(self, query: str) -> QueryClassification:
        q = query.lower().strip()
        result = QueryClassification(query_type=QUERY_UNKNOWN, keywords=[])

        # Detect article
        art_match = self.ARTICLE_PATTERN.search(query)
        if art_match:
            result.detected_article = art_match.group(0)
            # Check if norm is also specified (either numbered or named)
            norm_match = self.NORM_PATTERN_NUMBERED.search(query) or self.NORM_PATTERN_NAMED.search(query)
            if norm_match:
                result.detected_norm = norm_match.group(0)
            else:
                # Article mentioned without norm → need clarification
                result.query_type = QUERY_ARTICULO_ESPECIFICO
                result.needs_clarification = True
                result.clarification_question = (
                    "Has mencionado un artículo pero no la norma a la que pertenece. "
                    "¿Podrías especificar a qué código, ley, decreto o estatuto pertenece el artículo?"
                )
                return result

        # Detect file/radicado (jurisprudence)
        file_match = self.FILE_PATTERN.search(query)
        if file_match:
            result.detected_norm = file_match.group(0)

        # Detect temporal hint
        if any(kw in q for kw in self.HISTORICAL_KW):
            result.temporal_hint = "historical"
            # Extract year if present
            year_match = re.search(r"en\s+(19\d{2}|20\d{2})", q)
            if year_match:
                result.temporal_hint = f"as_of:{year_match.group(1)}-12-31"
        elif any(kw in q for kw in self.VIGENCIA_KW):
            result.temporal_hint = "current"

        # Classify by keywords
        scores: dict[str, int] = {
            QUERY_NORMATIVE: sum(1 for kw in self.NORMATIVE_KW if kw in q),
            QUERY_JURISPRUDENCIAL: sum(1 for kw in self.JURISPRUDENCIAL_KW if kw in q),
            QUERY_DOCTRINAL: sum(1 for kw in self.DOCTRINAL_KW if kw in q),
            QUERY_HISTORICAL: sum(1 for kw in self.HISTORICAL_KW if kw in q),
            QUERY_VIGENCIA: sum(1 for kw in self.VIGENCIA_KW if kw in q),
            QUERY_COMPARATIVA: sum(1 for kw in self.COMPARATIVA_KW if kw in q),
            QUERY_PROCESAL: sum(1 for kw in self.PROCESAL_KW if kw in q),
            QUERY_INTERPRETATIVA: sum(1 for kw in self.INTERPRETATIVA_KW if kw in q),
            QUERY_CASO: sum(1 for kw in self.CASO_KW if kw in q),
        }

        # Pick best type
        if max(scores.values(), default=0) == 0:
            result.query_type = QUERY_UNKNOWN
            result.confidence = 0.2
        else:
            # If we already classified as article-specific, keep that
            if result.query_type != QUERY_ARTICULO_ESPECIFICO:
                best_type = max(scores, key=scores.get)
                result.query_type = best_type
                result.confidence = min(1.0, 0.5 + scores[best_type] * 0.15)

            # Override based on detected patterns
            if file_match and scores[QUERY_JURISPRUDENCIAL] >= 1:
                result.query_type = QUERY_JURISPRUDENCIAL
                result.confidence = 0.85

        # Detect authority
        for auth in ("corte constitucional", "corte suprema", "consejo de estado", "congreso"):
            if auth in q:
                result.detected_authority = auth
                break

        result.keywords = [kw for kw in (
            self.NORMATIVE_KW + self.JURISPRUDENCIAL_KW + self.DOCTRINAL_KW +
            self.HISTORICAL_KW + self.VIGENCIA_KW + self.COMPARATIVA_KW +
            self.PROCESAL_KW + self.INTERPRETATIVA_KW
        ) if kw in q]

        return result

    def list_types(self) -> list[str]:
        return list(ALL_QUERY_TYPES)


# ============================================================
# ARTICLE RESOLVER - pide aclaración cuando falta la norma
# ============================================================

class ArticleResolver:
    """Resuelve referencias a artículos pidiendo aclaración cuando hace falta la norma.

    Ejemplo:
    "Artículo 200" → "¿De qué código, ley o estatuto?"
    "Artículo 200 del Código Civil colombiano" → activa recuperación específica.
    """

    AMBIGUOUS_PATTERNS = [
        re.compile(r"art[ií]culo\s+\d+[A-Z]?$", re.IGNORECASE),
        re.compile(r"^art[ií]culo\s+\d+[A-Z]?$", re.IGNORECASE),
    ]

    NORM_KEYWORDS = (
        "código", "codigo", "ley", "decreto", "estatuto", "resolución", "resolucion",
        "acuerdo", "reglamento",
    )

    def is_ambiguous(self, query: str) -> bool:
        """¿El query menciona artículo pero no la norma a la que pertenece?"""
        if not any(p.search(query) for p in self.AMBIGUOUS_PATTERNS):
            # Check if article mentioned without norm
            if not re.search(r"art[ií]culo\s+\d+", query, re.IGNORECASE):
                return False
        # Article present - check if norm is too
        if any(kw in query.lower() for kw in self.NORM_KEYWORDS):
            return False
        return True

    def ask_for_clarification(self, query: str) -> str:
        """Devuelve la pregunta de aclaración."""
        return (
            "Has mencionado un artículo pero no identifico claramente la norma "
            "(código, ley, decreto o estatuto) a la que pertenece. "
            "¿Podrías especificar la norma? Ejemplo: 'Artículo 200 del Código Civil colombiano'."
        )
