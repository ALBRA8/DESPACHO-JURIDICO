"""
ALBRA Eval Suite V2.3-A.

Inspiración clean-room:
- Harvey LAB (rubric scoring, all-passed + LLM juez)
- CoCoBench (essential / forbidden / bonus three-part rubric)
- legal-rag-eval (citation accuracy + hallucination rate + general accuracy)
- Awesome Legal Benchmarks (Legal Phantom Citation test)

Submódulos:
- albra.eval.rubrics            — Rubric + RubricResult + RubricRunner
- albra.eval.phantom_citations  — Legal Phantom Citation test
- albra.eval.drafting_rubrics   — 3 sample rubrics (tutela, demanda, contrato)
- albra.eval.runner             — run_eval_suite entrypoint
"""
from __future__ import annotations

from albra.eval.drafting_rubrics import (
    contrato_corporativo_rubric,
    demanda_civil_rubric,
    tutela_rubric,
)
from albra.eval.phantom_citations import (
    PHANTOM_CITATIONS,
    REAL_CITATIONS,
    run_phantom_test,
    run_phantom_test_detailed,
)
from albra.eval.rubrics import (
    Rubric,
    RubricResult,
    RubricRunner,
)
from albra.eval.runner import run_eval_suite

__all__ = [
    "Rubric",
    "RubricResult",
    "RubricRunner",
    "REAL_CITATIONS",
    "PHANTOM_CITATIONS",
    "run_phantom_test",
    "run_phantom_test_detailed",
    "tutela_rubric",
    "demanda_civil_rubric",
    "contrato_corporativo_rubric",
    "run_eval_suite",
]
