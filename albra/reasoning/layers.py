"""
Capas de razonamiento ALBRA.

CRÍTICO: NUNCA mezclar estas capas.
- DATOS: hechos brutos observados
- FUENTES: origen de los datos
- EVIDENCIA: datos + fuente + timestamp + transformación
- INFERENCIAS: deducciones a partir de evidencia
- CONCLUSIONES: afirmaciones soportadas por inferencias + evidencia
- ACCIONES: pasos a ejecutar, derivados de conclusiones
"""
from __future__ import annotations

LAYER_DATA = "data"
LAYER_SOURCES = "sources"
LAYER_EVIDENCE = "evidence"
LAYER_INFERENCES = "inferences"
LAYER_CONCLUSIONS = "conclusions"
LAYER_ACTIONS = "actions"

LAYERS_ORDER: tuple[str, ...] = (
    LAYER_DATA,
    LAYER_SOURCES,
    LAYER_EVIDENCE,
    LAYER_INFERENCES,
    LAYER_CONCLUSIONS,
    LAYER_ACTIONS,
)
