"""
EVAL SUITE — Rubrics para evaluar DRAFTING-AGENT y REVIEW-AGENT.

Inspiración clean-room: Harvey LAB (rubric scoring all-passed + LLM juez),
CoCoBench (essential / forbidden / bonus three-part rubric),
legal-rag-eval (citation accuracy + hallucination rate + general accuracy).

Cada rubric evalúa un output del agente contra:
- essential: lista de elementos obligatorios (must-have).
- forbidden: lista de errores a evitar (must-NOT-have).
- bonus: lista de elementos opcionales (nice-to-have).

Score:
- PASS si todos los essential están Y ningún forbidden está.
- BONUS si PASS y al menos 1 bonus está.
- FAIL en cualquier otro caso.

Matching: case-insensitive substring matching. Cada item en essential/forbidden/bonus
se busca como substring (lowercase) en el texto evaluado.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from albra.observability.logger import get_logger


@dataclass
class Rubric:
    """Definición de un rubric de evaluación.

    Atributos:
        name: nombre identificador del rubric (e.g. "tutela_rubric").
        essential: elementos obligatorios — todos deben aparecer en el output.
        forbidden: elementos prohibidos — ninguno debe aparecer en el output.
        bonus: elementos opcionales — al menos uno da BONUS si el rubric pasó.
    """
    name: str
    essential: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    bonus: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "essential": list(self.essential),
            "forbidden": list(self.forbidden),
            "bonus": list(self.bonus),
        }


@dataclass
class RubricResult:
    """Resultado de evaluar un texto contra un rubric.

    Atributos:
        rubric_name: nombre del rubric evaluado.
        passed: True si todos los essential están Y ningún forbidden está.
        bonus: True si passed Y al menos 1 bonus está.
        missing_essential: lista de essential que no aparecieron en el texto.
        violated_forbidden: lista de forbidden que sí aparecieron en el texto.
        matched_bonus: lista de bonus que sí aparecieron en el texto.
        reason: explicación legible del resultado.
    """
    rubric_name: str
    passed: bool = False
    bonus: bool = False
    missing_essential: list[str] = field(default_factory=list)
    violated_forbidden: list[str] = field(default_factory=list)
    matched_bonus: list[str] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "rubric_name": self.rubric_name,
            "passed": self.passed,
            "bonus": self.bonus,
            "missing_essential": list(self.missing_essential),
            "violated_forbidden": list(self.violated_forbidden),
            "matched_bonus": list(self.matched_bonus),
            "reason": self.reason,
        }


class RubricRunner:
    """Runner que evalúa un texto contra uno o varios rubrics.

    Métodos:
        evaluate(text, rubric)   — evalúa un texto contra un rubric.
        evaluate_all(text, rubrics) — evalúa un texto contra múltiples rubrics.
        summary(results)        — agrega resultados en métricas.
    """

    def __init__(self) -> None:
        self.log = get_logger("albra.eval.rubrics")

    def _matches(self, text_lower: str, item: str) -> bool:
        """Case-insensitive substring matching."""
        return item.lower() in text_lower

    def evaluate(self, text: str, rubric: Rubric) -> RubricResult:
        """Evalúa un texto contra un rubric. Devuelve RubricResult."""
        text_lower = text.lower()

        missing_essential = [
            item for item in rubric.essential
            if not self._matches(text_lower, item)
        ]
        violated_forbidden = [
            item for item in rubric.forbidden
            if self._matches(text_lower, item)
        ]
        matched_bonus = [
            item for item in rubric.bonus
            if self._matches(text_lower, item)
        ]

        passed = not missing_essential and not violated_forbidden
        bonus = passed and len(matched_bonus) > 0

        parts: list[str] = []
        if missing_essential:
            parts.append(f"missing essential: {missing_essential}")
        if violated_forbidden:
            parts.append(f"violated forbidden: {violated_forbidden}")
        if not parts:
            parts.append(
                f"all {len(rubric.essential)} essential present, "
                f"no forbidden violated"
            )
        if bonus:
            parts.append(f"bonus matched: {matched_bonus}")
        reason = "; ".join(parts)

        result = RubricResult(
            rubric_name=rubric.name,
            passed=passed,
            bonus=bonus,
            missing_essential=missing_essential,
            violated_forbidden=violated_forbidden,
            matched_bonus=matched_bonus,
            reason=reason,
        )
        self.log.info(
            "rubric.eval.complete",
            rubric=rubric.name,
            passed=passed,
            bonus=bonus,
            missing=len(missing_essential),
            violated=len(violated_forbidden),
        )
        return result

    def evaluate_all(
        self,
        text: str,
        rubrics: list[Rubric],
    ) -> list[RubricResult]:
        """Evalúa un texto contra múltiples rubrics. Devuelve lista de resultados."""
        return [self.evaluate(text, r) for r in rubrics]

    def summary(self, results: list[RubricResult]) -> dict[str, Any]:
        """Agrega resultados en métricas:
        total, passed, bonus, failed, pass_rate, bonus_rate.
        """
        total = len(results)
        if total == 0:
            return {
                "total": 0,
                "passed": 0,
                "bonus": 0,
                "failed": 0,
                "pass_rate": 0.0,
                "bonus_rate": 0.0,
            }
        passed_count = sum(1 for r in results if r.passed)
        bonus_count = sum(1 for r in results if r.bonus)
        failed_count = total - passed_count
        return {
            "total": total,
            "passed": passed_count,
            "bonus": bonus_count,
            "failed": failed_count,
            "pass_rate": passed_count / total,
            "bonus_rate": bonus_count / total,
        }
