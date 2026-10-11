"""
CITATION MODEL - V1.0.

Modelo de respuesta jurídicamente trazable.

Estructura:
Afirmación
  ↓
Fuente
  ↓
Documento
  ↓
Artículo / sección
  ↓
Fecha / versión
  ↓
Estado de vigencia
  ↓
Evidencia

Diferencia tipos de contenido:
- texto normativo (literal)
- interpretación (del modelo, marcada)
- inferencia (del modelo, marcada)
- doctrina
- jurisprudencia
- hipótesis (marcada como no confirmada)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Citation:
    """Cita a una fuente específica."""
    document_id: str
    source_tier: str  # S0_PRIMARY_SUPERIOR | S1_OFFICIAL | etc.
    authority: str
    document_type: str  # ley | sentencia | doctrina | etc.
    citation_text: str  # "Ley 100 de 1993, art. 25"
    snippet: str  # extracto literal (no inventado)
    effective_from: str | None = None
    effective_until: str | None = None
    status: str = "vigente"
    source_url: str = ""
    is_current: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "source_tier": self.source_tier,
            "authority": self.authority,
            "document_type": self.document_type,
            "citation_text": self.citation_text,
            "snippet": self.snippet,
            "effective_from": self.effective_from,
            "effective_until": self.effective_until,
            "status": self.status,
            "source_url": self.source_url,
            "is_current": self.is_current,
        }


# Tipos de contenido en una respuesta
CONTENT_TYPES = (
    "texto_normativo",       # literal de la norma - máximo peso
    "jurisprudencia",        # ratio decidendi de sentencia
    "doctrina",              # opinión académica/doctrinal
    "interpretacion",        # interpretación del modelo (marcada)
    "inferencia",            # inferencia del modelo (marcada)
    "hipotesis",             # hipótesis no confirmada (marcada)
    "abstencion",            # el sistema no responde por falta de evidencia
    "aclaracion",            # pide aclaración al usuario
)


@dataclass
class LegalResponseBlock:
    """Bloque de respuesta con tipo y citas."""
    content_type: str  # CONTENT_TYPES
    text: str
    citations: list[Citation] = field(default_factory=list)
    confidence: float = 0.0  # 0.0-1.0
    needs_review: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "content_type": self.content_type,
            "text": self.text,
            "citations": [c.as_dict() for c in self.citations],
            "confidence": self.confidence,
            "needs_review": self.needs_review,
        }


@dataclass
class LegalResponse:
    """Respuesta jurídica completa."""
    query: str
    query_type: str = "unknown"
    blocks: list[LegalResponseBlock] = field(default_factory=list)
    abstention: bool = False
    abstention_reason: str = ""
    needs_clarification: bool = False
    clarification_question: str = ""
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    needs_hitl: bool = False
    execution_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "query_type": self.query_type,
            "blocks": [b.as_dict() for b in self.blocks],
            "abstention": self.abstention,
            "abstention_reason": self.abstention_reason,
            "needs_clarification": self.needs_clarification,
            "clarification_question": self.clarification_question,
            "conflicts": self.conflicts,
            "needs_hitl": self.needs_hitl,
            "execution_id": self.execution_id,
        }

    def format_text(self) -> str:
        """Formato plano para chat."""
        if self.abstention:
            return f"[ABSTENCIÓN] {self.abstention_reason}"
        if self.needs_clarification:
            return f"[ACLARACIÓN] {self.clarification_question}"
        parts = []
        for block in self.blocks:
            prefix = f"[{block.content_type}]"
            citations_text = ""
            if block.citations:
                citations_text = " | Citas: " + ", ".join(c.citation_text for c in block.citations)
            parts.append(f"{prefix} {block.text}{citations_text}")
        return "\n\n".join(parts)
