"""
RUBRICS PARA DRAFTING-AGENT — evalúa drafts generados.

Tres rubrics:
1. tutela_rubric: evalúa draft de acción de tutela
2. demanda_civil_rubric: evalúa demanda civil
3. contrato_corporativo_rubric: evalúa contrato corporativo

Cada rubric tiene 5-8 essential, 3-5 forbidden, 2-3 bonus.
Matching: case-insensitive substring (ver albra.eval.rubrics.RubricRunner).
"""
from __future__ import annotations

from albra.eval.rubrics import Rubric

# ===== 1. ACCIÓN DE TUTELA =====
# Essential: hechos, norma vulnerada, pretensión, juramento, anexos.
# Forbidden: cláusulas exorbitantes, indemnizatorias, confesión.
# Bonus: cita de Constitución art 86 (jurisdicción constitucional), firma.

tutela_rubric = Rubric(
    name="tutela_rubric",
    essential=[
        "acción de tutela",
        "derecho fundamental",
        "hechos",
        "norma vulnerada",
        "pretensión",
        "juramento",
        "anexos",
    ],
    forbidden=[
        "cláusula exorbitante",
        "indemnización perjuicios",
        "confesión extrajudicial",
        "cláusula penal",
    ],
    bonus=[
        "Constitución Política de 1991",
        "artículo 86",
        "manifestación de ",
    ],
)

# ===== 2. DEMANDA CIVIL =====
# Essential: caption, partes, hechos, fundamentos de derecho, pretensiones,
# pruebas, juramento. Forbidden: juez de costumbre, cláusula penal exorbitante.
# Bonus: cita Constitución art 29 (debido proceso).

demanda_civil_rubric = Rubric(
    name="demanda_civil_rubric",
    essential=[
        "señor juez",
        "demandante",
        "demandado",
        "hechos",
        "fundamentos de derecho",
        "pretensiones",
        "pruebas",
        "juramento",
    ],
    forbidden=[
        "cláusula penal exorbitante",
        "renuncia al debido proceso",
        "juez de costumbre",
        "indemnización sin fundamento",
    ],
    bonus=[
        "Constitución Política de 1991",
        "artículo 29",
        "código general del proceso",
    ],
)

# ===== 3. CONTRATO CORPORATIVO =====
# Essential: cláusulas, partes, objeto, contraprestación, jurisdicción,
# ley aplicable. Forbidden: cláusulas abusivas (renuncia a tutela, sumisión
# extranjera sin causa, cláusula penal desproporcionada). Bonus: ley aplicable
# colombiana.

contrato_corporativo_rubric = Rubric(
    name="contrato_corporativo_rubric",
    essential=[
        "cláusulas",
        "las partes",
        "objeto del contrato",
        "contraprestación",
        "jurisdicción",
        "ley aplicable",
        "vigencia",
    ],
    forbidden=[
        "renuncia a la acción de tutela",
        "sumisión a jurisdicción extranjera sin causa",
        "cláusula penal desproporcionada",
        "indemnización ilimitada",
    ],
    bonus=[
        "Ley 80 de 1993",
        "Cámara de Comercio",
    ],
)
