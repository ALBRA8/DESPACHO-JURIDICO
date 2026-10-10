"""Motor de razonamiento - separa DATOS, FUENTES, EVIDENCIA, INFERENCIAS, CONCLUSIONES, ACCIONES."""
from albra.reasoning.engine import ReasoningEngine
from albra.reasoning.layers import (
    LAYER_ACTIONS,
    LAYER_CONCLUSIONS,
    LAYER_DATA,
    LAYER_EVIDENCE,
    LAYER_INFERENCES,
    LAYER_SOURCES,
    LAYERS_ORDER,
)
