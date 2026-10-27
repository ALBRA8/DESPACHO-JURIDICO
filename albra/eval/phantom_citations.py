"""
LEGAL PHANTOM CITATION TEST — verifica que CitationAuditor bloquee 100%
de las citas alucinadas.

Inspiración: Awesome Legal Benchmarks recomienda "Legal Phantom Citation:
identificar citas legales alucinadas y tramos afectados" y "Hallucination-Free?
Study: devolver respuestas de investigación legal correctas y fundamentadas".

Dataset V2.3:
- 50 REAL citations: Constitución arts 1,2,5,13,25,29 + Ley 100 arts 1,2,3 +
  Ley 80 arts 1,2,24 + variants with quotes.
- 50 PHANTOM citations: nonexistent article numbers (art 350), invented sentencias
  (Sentencia XYZ-999/2030), wrong years (Ley 100 de 2099), wrong document types.

Test:
- Para cada REAL citation, CitationAuditor debe marcar como revealed=True.
- Para cada PHANTOM citation, CitationAuditor debe marcar como revealed=False.

Métricas:
- TRUE_POSITIVE_RATE: REAL → revealed (debe ser 100%)
- TRUE_NEGATIVE_RATE: PHANTOM → blocked (debe ser 100%)
- FALSE_POSITIVE_RATE: PHANTOM → revealed (debe ser 0%)
- FALSE_NEGATIVE_RATE: REAL → blocked (debe ser 0%)
"""
from __future__ import annotations

from typing import Any

from albra.knowledge.citation_audit import CitationAuditor
from albra.observability.logger import get_logger

# ===== 50 REAL CITATIONS — todas verificables contra corpus V1.1 =====

REAL_CITATIONS: list[str] = [
    # Constitución article 1 — 6 phrasings
    "El artículo 1 de la Constitución Política de 1991 establece el Estado social de derecho.",
    "Constitución Política de 1991, artículo 1, funda el Estado social de derecho.",
    "El artículo 1 de la Constitución consagra el Estado social.",
    "Según el artículo 1 de la Constitución Política de 1991, Colombia es Estado social.",
    "La Constitución Política de 1991, en su artículo 1, define el Estado social de derecho.",
    "El artículo 1 de la Constitución Política de 1991 funda el Estado social.",
    # Constitución article 2 — 5 phrasings
    "El artículo 2 de la Constitución Política de 1991 define los fines esenciales del Estado.",
    "Constitución Política de 1991, artículo 2, lista los fines del Estado.",
    "El artículo 2 de la Constitución define los fines esenciales.",
    "Según el artículo 2 de la Constitución Política de 1991, el Estado sirve a la comunidad.",
    "La Constitución Política de 1991, en su artículo 2, enlista los fines esenciales.",
    # Constitución article 5 — 5 phrasings
    "El artículo 5 de la Constitución Política de 1991 reconoce los derechos inalienables.",
    "Constitución Política de 1991, artículo 5, ampara a la familia.",
    "El artículo 5 de la Constitución reconoce la primacía de los derechos.",
    "Según el artículo 5 de la Constitución Política de 1991, se ampara a la familia.",
    "La Constitución Política de 1991, en su artículo 5, reconoce la dignidad humana.",
    # Constitución article 13 — 6 phrasings
    "El artículo 13 de la Constitución Política de 1991 garantiza la igualdad.",
    "Constitución Política de 1991, artículo 13, prohíbe la discriminación.",
    "El artículo 13 de la Constitución consagra la igualdad ante la ley.",
    "Según el artículo 13 de la Constitución Política de 1991, todas las personas son iguales.",
    "La Constitución Política de 1991, en su artículo 13, garantiza la no discriminación.",
    "El artículo 13 de la Constitución Política de 1991 prohíbe toda discriminación.",
    # Constitución article 25 — 5 phrasings
    "El artículo 25 de la Constitución Política de 1991 protege el trabajo.",
    "Constitución Política de 1991, artículo 25, asegura trabajo digno.",
    "El artículo 25 de la Constitución da protección al trabajo.",
    "Según el artículo 25 de la Constitución Política de 1991, el trabajo es derecho.",
    "La Constitución Política de 1991, en su artículo 25, garantiza trabajo digno.",
    # Constitución article 29 — 5 phrasings
    "El artículo 29 de la Constitución Política de 1991 consagra el debido proceso.",
    "Constitución Política de 1991, artículo 29, garantiza el debido proceso.",
    "El artículo 29 de la Constitución establece el debido proceso.",
    "Según el artículo 29 de la Constitución Política de 1991, nadie podrá ser juzgado sin leyes preexistentes.",
    "La Constitución Política de 1991, en su artículo 29, protege el debido proceso.",
    # Ley 100 article 1 — 3 phrasings
    "La Ley 100 de 1993, artículo 1, crea el sistema de seguridad social integral.",
    "El artículo 1 de la Ley 100 de 1993 dispone la creación del sistema.",
    "Ley 100 de 1993, artículo 1, sobre la seguridad social integral.",
    # Ley 100 article 2 — 3 phrasings
    "Ley 100 de 1993, artículo 2, define los principios de eficiencia y solidaridad.",
    "El artículo 2 de la Ley 100 de 1993 enlista los principios.",
    "Ley 100 de 1993, artículo 2, sobre los principios del sistema.",
    # Ley 100 article 3 — 3 phrasings
    "Según la Ley 100 de 1993, artículo 3, el Estado garantiza la seguridad social.",
    "El artículo 3 de la Ley 100 de 1993 garantiza el derecho a la seguridad social.",
    "Ley 100 de 1993, artículo 3, sobre el derecho irrenunciable.",
    # Ley 80 article 1 — 3 phrasings
    "La Ley 80 de 1993, artículo 1, define el objeto de la contratación estatal.",
    "El artículo 1 de la Ley 80 de 1993 dispone el objeto.",
    "Ley 80 de 1993, artículo 1, sobre la contratación estatal.",
    # Ley 80 article 2 — 3 phrasings
    "Ley 80 de 1993, artículo 2, define las entidades estatales.",
    "El artículo 2 de la Ley 80 de 1993 define entidades estatales.",
    "Según el artículo 2 de la Ley 80 de 1993, se definen entidades estatales.",
    # Ley 80 article 24 — 3 phrasings
    "Según la Ley 80 de 1993, artículo 24, se rige el principio de transparencia.",
    "El artículo 24 de la Ley 80 de 1993 consagra la transparencia.",
    "Ley 80 de 1993, artículo 24, sobre la transparencia.",
]

# ===== 50 PHANTOM CITATIONS — todas alucinadas, deben ser bloqueadas =====

PHANTOM_CITATIONS: list[str] = [
    # Constitución — nonexistent article numbers (no en corpus V1.1)
    "El artículo 3 de la Constitución Política de 1991 establece la propiedad.",
    "El artículo 4 de la Constitución Política de 1991 dispone la soberanía.",
    "El artículo 6 de la Constitución Política de 1991 consagra la libertad.",
    "El artículo 7 de la Constitución Política de 1991 protege la vida.",
    "El artículo 8 de la Constitución Política de 1991 establece la igualdad jurídica.",
    "El artículo 9 de la Constitución Política de 1991 promueve las relaciones internacionales.",
    "El artículo 10 de la Constitución Política de 1991 reconoce el castellano.",
    "El artículo 11 de la Constitución Política de 1991 garantiza el derecho a la vida.",
    "El artículo 12 de la Constitución Política de 1991 prohíbe la desaparición forzada.",
    "El artículo 14 de la Constitución Política de 1991 consagra el derecho a la petición.",
    "El artículo 15 de la Constitución Política de 1991 protege datos personales.",
    "El artículo 17 de la Constitución Política de 1991 prohíbe la esclavitud.",
    "El artículo 18 de la Constitución Política de 1991 garantiza la libertad de conciencia.",
    "El artículo 19 de la Constitución Política de 1991 protege la libertad de expresión.",
    "El artículo 30 de la Constitución Política de 1991 regula el hábeas data.",
    "El artículo 50 de la Constitución Política de 1991 establece la mayoría de edad.",
    "El artículo 99 de la Constitución Política de 1991 define la función judicial.",
    "El artículo 100 de la Constitución Política de 1991 crea la Corte Suprema.",
    "El artículo 200 de la Constitución Política de 1991 organiza el ministerio público.",
    "El artículo 350 de la Constitución Política de 1991 establece el derecho al olvido.",
    "El artículo 400 de la Constitución Política de 1991 regula el derecho al ambiente.",
    "El artículo 500 de la Constitución Política de 1991 dispone el derecho al agua.",
    "El artículo 999 de la Constitución Política de 1991 crea la renta básica.",
    # Constitución — wrong year (1886, no en corpus V1.1)
    "La Constitución Política de 1886 establece el sufragio universal.",
    "El artículo 1 de la Constitución Política de 1886 dispone el sufragio.",
    "El artículo 13 de la Constitución Política de 1886 garantiza la igualdad.",
    "El artículo 25 de la Constitución Política de 1886 protege el trabajo.",
    # Wrong Ley number / year (no en corpus V1.1)
    "Ley 9999 de 1993, artículo 1, inventa la seguridad social.",
    "Ley 47 de 1926 establece el régimen de tierras.",
    "Ley 1420 de 2011 protege los derechos de los consumidores.",
    "Ley 1480 de 2011, artículo 1, establece el estatuto de consumo.",
    "Ley 47 de 1926, artículo 2, regula la propiedad rural.",
    "Ley 1450 de 2011, artículo 1, dispone el plan nacional de desarrollo.",
    "Ley 1564 de 2012, artículo 1, crea el código general del proceso.",
    "Ley 100 de 2099, artículo 1, garantiza la seguridad social.",
    "Ley 80 de 2095, artículo 1, dispone la contratación.",
    "Ley 100 de 1994, artículo 1, modifica la seguridad social.",
    "Ley 80 de 1992, artículo 1, dispone la contratación estatal.",
    "Ley 100 de 1992, artículo 1, crea el sistema de salud.",
    "Ley 80 de 1994, artículo 1, regula la contratación.",
    # Invented Sentencias (no en corpus ni en rejected list)
    "Sentencia XYZ-999/2030 establece una nueva doctrina.",
    "Sentencia ABC-123/2099 protege el derecho a la renta.",
    "Sentencia C-999/2099 sobre el derecho al olvido.",
    "Sentencia T-999/2099 sobre la tutela urgente.",
    "Sentencia SU-999/2099 sobre la unificación jurisprudencial.",
    "Sentencia MP-999/2099 sobre el juicio político.",
    "Sentencia SL-999/2099 sobre el derecho laboral.",
    # Rejected Sentencias (en REJECTED_DOCUMENTS de V1.1)
    "Sentencia C-251/2002 sobre el derecho a la salud.",
    "Sentencia T-760/2008 sobre la tutela.",
    "Sentencia AR-001/2020 sobre la pandemia.",
]


def _audit_one(auditor: CitationAuditor, text: str) -> dict[str, Any]:
    """Audita una sola cita y devuelve dict plano con metric fields."""
    result = auditor.audit_response(text)
    return {
        "text": text,
        "revealed": result.revealed,
        "blocked": not result.revealed,
        "verified_count": len(result.verified),
        "unverified_count": len(result.unverified),
        "rejected_count": len(result.rejected),
        "reason": result.reason,
    }


def run_phantom_test() -> dict[str, Any]:
    """Ejecuta CitationAuditor sobre las 100 citas (50 REAL + 50 PHANTOM).

    Devuelve métricas agregadas:
    - true_positive_rate: REAL → revealed (objetivo 1.0)
    - true_negative_rate: PHANTOM → blocked (objetivo 1.0)
    - false_positive_rate: PHANTOM → revealed (objetivo 0.0)
    - false_negative_rate: REAL → blocked (objetivo 0.0)
    """
    log = get_logger("albra.eval.phantom_citations")
    auditor = CitationAuditor()

    real_total = len(REAL_CITATIONS)
    phantom_total = len(PHANTOM_CITATIONS)

    true_positives = 0  # REAL → revealed
    false_negatives = 0  # REAL → blocked
    true_negatives = 0  # PHANTOM → blocked
    false_positives = 0  # PHANTOM → revealed

    for text in REAL_CITATIONS:
        r = auditor.audit_response(text)
        if r.revealed:
            true_positives += 1
        else:
            false_negatives += 1

    for text in PHANTOM_CITATIONS:
        r = auditor.audit_response(text)
        if r.revealed:
            false_positives += 1
        else:
            true_negatives += 1

    metrics = {
        "real_total": real_total,
        "phantom_total": phantom_total,
        "true_positives": true_positives,
        "true_negatives": true_negatives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "true_positive_rate": true_positives / real_total if real_total else 0.0,
        "true_negative_rate": true_negatives / phantom_total if phantom_total else 0.0,
        "false_positive_rate": false_positives / phantom_total if phantom_total else 0.0,
        "false_negative_rate": false_negatives / real_total if real_total else 0.0,
        "total": real_total + phantom_total,
    }
    log.info(
        "phantom_test.complete",
        real_total=real_total,
        phantom_total=phantom_total,
        tpr=metrics["true_positive_rate"],
        tnr=metrics["true_negative_rate"],
        fpr=metrics["false_positive_rate"],
        fnr=metrics["false_negative_rate"],
    )
    return metrics


def run_phantom_test_detailed() -> list[dict[str, Any]]:
    """Devuelve resultados por-cita (100 dicts).

    Cada dict: {label, text, revealed, blocked, verified_count,
                unverified_count, rejected_count, reason}.
    """
    auditor = CitationAuditor()
    rows: list[dict[str, Any]] = []
    for text in REAL_CITATIONS:
        row = _audit_one(auditor, text)
        row["label"] = "REAL"
        rows.append(row)
    for text in PHANTOM_CITATIONS:
        row = _audit_one(auditor, text)
        row["label"] = "PHANTOM"
        rows.append(row)
    return rows
