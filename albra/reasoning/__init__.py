"""Motor de razonamiento - separa DATOS, FUENTES, EVIDENCIA, INFERENCIAS, CONCLUSIONES, ACCIONES."""
from albra.reasoning.engine import ReasoningEngine
from albra.reasoning.layers import (
    LAYER_DATA,
    LAYER_SOURCES,
    LAYER_EVIDENCE,
    LAYER_INFERENCES,
    LAYER_CONCLUSIONS,
    LAYER_ACTIONS,
    LAYERS_ORDER,
)
