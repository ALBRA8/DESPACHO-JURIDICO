"""
EVAL SUITE RUNNER — entrypoint que ejecuta todas las pruebas V2.3-A.

Inspiración: Harvey LAB (all-passed rubric scoring), CoCoBench (essential/
forbidden/bonus), legal-rag-eval (citation accuracy + hallucination rate).

run_eval_suite() ejecuta:
- 3 drafting rubrics (tutela, demanda civil, contrato corporativo) sobre
  drafts de muestra.
- 1 phantom citation test (50 REAL + 50 PHANTOM).

Devuelve dict con {rubrics: [...], phantom: {...}, summary: {...}}.
"""
from __future__ import annotations

from typing import Any

from albra.eval.drafting_rubrics import (
    contrato_corporativo_rubric,
    demanda_civil_rubric,
    tutela_rubric,
)
from albra.eval.phantom_citations import run_phantom_test
from albra.eval.rubrics import RubricRunner
from albra.observability.logger import get_logger

# ===== DRAFTS DE MUESTRA =====
# Cada draft es un ejemplo "suficientemente bueno" (pasa essential, evita
# forbidden, puede activar bonus). Sirven como referencia para evaluar la
# infraestructura de rubrics; el verdadero uso es evaluar outputs del
# DRAFTING-AGENT con rubrics reales.

_TUTELA_SAMPLE = """\
ACCION DE TUTELA

Señor Juez de la República:
Acción de tutela interpuesta por el accionante contra la entidad demandada por
vulneración del derecho fundamental a la salud.

HECHOS
1. El accionante ha sido privado del acceso a tratamiento médico.
2. La entidad demandada ha ignorado las solicitudes reiteradas.
3. La vulneración del derecho fundamental persiste a la fecha.

NORMA VULNERADA
Constitución Política de 1991, artículo 13, garantiza la igualdad ante la ley
y el acceso a los servicios sociales. El derecho fundamental vulnerado es
la salud.

PRETENSIÓN
Solicito amparo constitucional y orden a la entidad para restablecer el
tratamiento médico.

JURAMENTO
Manifiesto bajo la gravedad del juramento que los hechos son ciertos.

ANEXOS
Historia clínica, derecho de petición, respuesta de la entidad.
Firma del accionante y manifestación de no haber presentado otra tutela.
"""

_DEMANDA_CIVIL_SAMPLE = """\
DEMANDA CIVIL

Señor Juez Civil del Circuito:
Demandante: Juan Pérez.
Demandado: Empresa XYZ S.A.S.

HECHOS
1. El demandante celebró contrato de prestación de servicios.
2. El demandado incumplió las obligaciones contractuales.
3. El daño causado asciende a la suma establecida en peritaje.

FUNDAMENTOS DE DERECHO
Constitución Política de 1991, artículo 29, garantiza el debido proceso.
Código general del proceso, normas aplicables a la acción contractual.

PRENSIONES
Primera: que se declare el incumplimiento contractual.
Segunda: que se condene al demandado a pagar las sumas adeudadas.

PRUEBAS
Contrato, facturas, peritaje técnico, testimonios.

JURAMENTO
Manifiesto bajo la gravedad del juramento que los hechos son ciertos.
Pretensiones conforme a derecho.
"""

_CONTRATO_CORPORATIVO_SAMPLE = """\
CONTRATO CORPORATIVO DE ASOCIACIÓN

Conste por el presente documento, las cláusulas del contrato corporativo:

Las partes: Sociedad A y Sociedad B, identificadas en el encabezamiento.

OBJETO DEL CONTRATO
El objeto del contrato es la asociación para el desarrollo del proyecto
inmobiliario.

CONTRAPRESTACIÓN
Cada parte aportará los recursos descritos en el anexo financiero.

JURISDICCIÓN
Las partes se someten a la jurisdicción de los jueces de Bogotá D.C.

LEY APLICABLE
Ley aplicable: legislación colombiana. Ley 80 de 1993 en lo pertinente
a contratación estatal si aplica, y registro en Cámara de Comercio.

VIGENCIA
El contrato rige por el término de cinco (5) años.
"""


def _evaluate_drafts(runner: RubricRunner) -> dict[str, Any]:
    """Ejecuta 3 rubrics sobre 3 drafts de muestra."""
    cases = [
        (_TUTELA_SAMPLE, tutela_rubric),
        (_DEMANDA_CIVIL_SAMPLE, demanda_civil_rubric),
        (_CONTRATO_CORPORATIVO_SAMPLE, contrato_corporativo_rubric),
    ]
    results = []
    for draft, rubric in cases:
        result = runner.evaluate(draft, rubric)
        results.append({
            "rubric_name": rubric.name,
            "passed": result.passed,
            "bonus": result.bonus,
            "missing_essential": result.missing_essential,
            "violated_forbidden": result.violated_forbidden,
            "matched_bonus": result.matched_bonus,
            "reason": result.reason,
        })
    return {
        "results": results,
        "summary": runner.summary([
            # Re-derive summary from RubricResult instances for proper typing.
            _make_result(r) for r in results
        ]),
    }


def _make_result(d: dict[str, Any]):
    """Reconstruye un RubricResult desde un dict plano (para summary)."""
    from albra.eval.rubrics import RubricResult
    return RubricResult(
        rubric_name=d["rubric_name"],
        passed=d["passed"],
        bonus=d["bonus"],
        missing_essential=d["missing_essential"],
        violated_forbidden=d["violated_forbidden"],
        matched_bonus=d["matched_bonus"],
        reason=d["reason"],
    )


def run_eval_suite() -> dict[str, Any]:
    """Ejecuta todas las pruebas de eval suite V2.3-A.

    Returns:
        {
            "rubrics": {"results": [...], "summary": {...}},
            "phantom": {...metrics...},
            "summary": {
                "rubrics_total": 3,
                "rubrics_passed": N,
                "phantom_tpr": 1.0,
                "phantom_tnr": 1.0,
                "all_passed": bool,
            },
        }
    """
    log = get_logger("albra.eval.runner")
    runner = RubricRunner()
    rubrics_block = _evaluate_drafts(runner)
    phantom = run_phantom_test()

    rubrics_summary = rubrics_block["summary"]
    summary = {
        "rubrics_total": rubrics_summary["total"],
        "rubrics_passed": rubrics_summary["passed"],
        "rubrics_bonus": rubrics_summary["bonus"],
        "rubrics_failed": rubrics_summary["failed"],
        "rubric_pass_rate": rubrics_summary["pass_rate"],
        "phantom_tpr": phantom["true_positive_rate"],
        "phantom_tnr": phantom["true_negative_rate"],
        "phantom_fpr": phantom["false_positive_rate"],
        "phantom_fnr": phantom["false_negative_rate"],
        "all_passed": (
            rubrics_summary["failed"] == 0
            and phantom["true_positive_rate"] == 1.0
            and phantom["true_negative_rate"] == 1.0
        ),
    }
    log.info(
        "eval_suite.complete",
        rubrics_passed=summary["rubrics_passed"],
        phantom_tpr=summary["phantom_tpr"],
        phantom_tnr=summary["phantom_tnr"],
        all_passed=summary["all_passed"],
    )
    return {
        "rubrics": rubrics_block,
        "phantom": phantom,
        "summary": summary,
    }
