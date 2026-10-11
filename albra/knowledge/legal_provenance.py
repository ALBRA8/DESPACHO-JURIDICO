"""
LEGAL PROVENANCE - V1.0.

Cada pieza de conocimiento jurídico responde:
- ¿De dónde salió?
- ¿Qué documento es?
- ¿Quién lo emitió?
- ¿Cuándo?
- ¿Qué versión?
- ¿Dónde está publicado?
- ¿Qué autoridad tiene?
- ¿Cuándo fue recuperado?
- ¿Qué transformación sufrió?
- ¿Qué fragmento se utilizó?

Integrado con EvidenceChain existente - NO crea sistema paralelo.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LegalProvenance:
    """Provenance jurídico completo de una pieza de conocimiento."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    source_url: str = ""
    source_tier: str = ""  # S0_PRIMARY_SUPERIOR | S1_OFFICIAL | etc.
    authority: str = ""   # Congreso, Corte, etc.
    document_id: str = ""
    document_type: str = ""  # ley, sentencia, doctrina
    citation_text: str = ""  # "Ley 100 de 1993, art. 25"
    retrieved_at: float = 0.0
    content_hash: str = ""
    transformation_chain: list[str] = field(default_factory=list)
    fragment_used: str = ""  # qué extracto se utilizó
    version: str = ""  # versión de la norma
    effective_at: str = ""  # fecha de vigencia aplicable
    official_source: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_url": self.source_url,
            "source_tier": self.source_tier,
            "authority": self.authority,
            "document_id": self.document_id,
            "document_type": self.document_type,
            "citation_text": self.citation_text,
            "retrieved_at": self.retrieved_at,
            "content_hash": self.content_hash,
            "transformation_chain": self.transformation_chain,
            "fragment_used": self.fragment_used,
            "version": self.version,
            "effective_at": self.effective_at,
            "official_source": self.official_source,
        }


def build_provenance(
    *,
    source_url: str,
    source_tier: str,
    authority: str,
    document_id: str,
    document_type: str,
    citation_text: str,
    content_hash: str = "",
    fragment_used: str = "",
    version: str = "",
    effective_at: str = "",
    transformation_chain: list[str] | None = None,
    official_source: bool = True,
) -> LegalProvenance:
    """Construye un LegalProvenance completo."""
    if transformation_chain is None:
        transformation_chain = ["raw", "parsed", "indexed", "retrieved", "used"]
    return LegalProvenance(
        source_url=source_url,
        source_tier=source_tier,
        authority=authority,
        document_id=document_id,
        document_type=document_type,
        citation_text=citation_text,
        retrieved_at=time.time(),
        content_hash=content_hash,
        transformation_chain=transformation_chain,
        fragment_used=fragment_used,
        version=version,
        effective_at=effective_at,
        official_source=official_source,
    )


async def record_evidence_with_provenance(
    evidence_chain: Any,
    *,
    kind: str,
    content: str,
    source: str,
    legal_provenance: LegalProvenance,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Registra evidencia con provenance jurídico en EvidenceChain existente.

    NO crea otro sistema paralelo - usa EvidenceChain.add().
    """
    full_metadata = {
        **(metadata or {}),
        "legal_provenance": legal_provenance.as_dict(),
    }
    return await evidence_chain.add(
        kind=kind,
        content=content,
        source=source,
        metadata=full_metadata,
    )
