"""
RETRIEVAL ABSTRACTION - V1.0.

NO acopla a Qdrant o cualquier vector DB específico.
La arquitectura depende de RetrievalProvider interface.

Soporta:
- Exact retrieval (artículo X, ley Y, expediente Z)
- Semantic retrieval (conceptos jurídicos)
- Metadata filtering (jurisdicción, autoridad, tipo, fecha, vigencia)
- Temporal filtering (vigente a fecha X)
- Hybrid retrieval (combina todo)

Decision on Qdrant:
- No es dependencia arquitectónica.
- Si en el futuro se prefiere Qdrant como backend, será un
  RetrievalProvider implementation. No la abstracción misma.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from albra.knowledge.schemas import (
    Article,
    Doctrine,
    EvidenceCandidate,
    Jurisprudence,
    Norm,
    SourceTier,
)
from albra.knowledge.temporal import TemporalQuery

# ============================================================
# QUERY MODELS
# ============================================================

@dataclass
class RetrievalQuery:
    """Query para retrieval híbrido."""
    query_text: str = ""               # texto de la consulta
    query_type: str = "semantic"      # exact | semantic | hybrid

    # Exact retrieval
    norm_number: str = ""             # "Ley 100 de 1993"
    article_number: str = ""          # "25"
    file_number: str = ""             # "T-123/2023"
    document_type: str = ""            # ley, sentencia, etc.

    # Metadata filters
    jurisdiction: str = "CO"
    authority: str = ""
    source_tier: SourceTier | None = None
    subject: str = ""                  # civil, penal, laboral

    # Temporal
    temporal: TemporalQuery | None = None

    # Ranking
    top_k: int = 10
    min_score: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "query_text": self.query_text,
            "query_type": self.query_type,
            "norm_number": self.norm_number,
            "article_number": self.article_number,
            "file_number": self.file_number,
            "document_type": self.document_type,
            "jurisdiction": self.jurisdiction,
            "authority": self.authority,
            "source_tier": self.source_tier.name if self.source_tier else None,
            "subject": self.subject,
            "temporal": self.temporal.as_dict() if self.temporal else None,
            "top_k": self.top_k,
            "min_score": self.min_score,
        }


@dataclass
class RetrievalResult:
    """Resultado de retrieval."""
    candidates: list[EvidenceCandidate] = field(default_factory=list)
    total_found: int = 0
    query: RetrievalQuery | None = None
    elapsed_ms: float = 0.0
    backend: str = "unknown"
    abstention: bool = False  # si no se encontró evidencia suficiente
    abstention_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidates": [c.as_dict() for c in self.candidates],
            "total_found": self.total_found,
            "elapsed_ms": self.elapsed_ms,
            "backend": self.backend,
            "abstention": self.abstention,
            "abstention_reason": self.abstention_reason,
        }


# ============================================================
# PROVIDER INTERFACE
# ============================================================

class RetrievalProvider(ABC):
    """Interface para backends de retrieval.

    Implementaciones conocidas:
    - InMemoryRetrievalProvider (default, sin deps)
    - (futuro) SQLiteRetrievalProvider
    - (futuro) QdrantRetrievalProvider - SI se quiere, es un backend, no la arquitectura.
    """

    name: str = "abstract"

    @abstractmethod
    async def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """Ejecuta retrieval. Devuelve candidatos."""

    @abstractmethod
    async def index_norm(self, norm: Norm, articles: list[Article]) -> str:
        """Indexa una norma con sus artículos."""

    @abstractmethod
    async def index_jurisprudence(self, j: Jurisprudence) -> str:
        """Indexa una sentencia."""

    @abstractmethod
    async def index_doctrine(self, d: Doctrine) -> str:
        """Indexa doctrina."""

    @abstractmethod
    async def startup(self) -> None: ...

    @abstractmethod
    async def shutdown(self) -> None: ...

    @abstractmethod
    def stats(self) -> dict[str, Any]: ...


# ============================================================
# HYBRID RETRIEVER - orquesta providers
# ============================================================

class HybridRetriever:
    """Orquesta retrieval combinando exact + semantic + metadata + temporal.

    NO depende de un provider específico - se le inyecta.
    Aplica ranking por:
    - source_tier (S0 > S1 > S2 > S3 > S4)
    - score de relevancia
    - vigencia temporal (current > historical)
    - autoridad
    """

    def __init__(self, *, provider: RetrievalProvider) -> None:
        self.provider = provider

    async def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """Ejecuta retrieval híbrido."""
        result = await self.provider.retrieve(query)
        # Ranking: boost S0/S1, penalize non-current
        ranked = self._rank(result.candidates)
        result.candidates = ranked[: query.top_k]
        return result

    def _rank(self, candidates: list[EvidenceCandidate]) -> list[EvidenceCandidate]:
        """Ranking: tier + score + vigencia."""
        def score(c: EvidenceCandidate) -> float:
            tier_bonus = (5 - c.source_tier) * 0.1  # S0=0.5, S1=0.4, ...
            current_bonus = 0.05 if c.is_current else -0.05
            return c.score + tier_bonus + current_bonus

        return sorted(candidates, key=score, reverse=True)
