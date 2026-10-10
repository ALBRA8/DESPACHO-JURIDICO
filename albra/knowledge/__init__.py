"""
Knowledge Layer ALBRA - preparación para carga de conocimiento jurídico.

CRÍTICO: el conocimiento se cargará DESPUÉS.
La jurisdicción objetivo es Colombia.

Soporta:
- versionado de normas (vigencia)
- actualización de políticas
- invalidación de fuentes derogadas
- asociación con fuentes oficiales
- separación por jurisdicción y fecha
"""
from albra.knowledge.loader import KnowledgeLoader
from albra.knowledge.versioner import KnowledgeVersioner

__all__ = ["KnowledgeLoader", "KnowledgeVersioner"]
