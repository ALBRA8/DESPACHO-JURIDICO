"""
PLAYBOOKS — plantillas por área de práctica para el despacho jurídico.

Cada playbook es un archivo markdown con YAML frontmatter que define:
- practice_area (laboral, civil, familia, constitucional, corporativo)
- typical_matter_types (lista de tipos de matter)
- workflow_states (estados del state machine que recorre típicamente)
- required_documents (documentos a generar en cada etapa)
- deadline_types (tipos de DeadlineGuard aplicables)
- citation_corpus (qué documentos del corpus V1.1 citar)
- red_flags (condiciones que disparan advierten al abogado)

Los playbooks son guías para DRAFTING-AGENT y REVIEW-AGENT, no reglas
rígidas. El abogado siempre tiene la última palabra.
"""
from albra.playbooks.loader import (
    Playbook,
    PlaybookLoader,
    PlaybookValidationError,
)

__all__ = [
    "Playbook",
    "PlaybookLoader",
    "PlaybookValidationError",
]
