"""
Corrective RAG (CRAG) - retrieval con auto-grading y fallback.

Pipeline:
1. Recuperar chunks relevantes de memoria/knowledge
2. Gradear relevancia (similarity score)
3. Si score bajo → fallback a web/external research
4. Reescribir query si es necesario
5. Reintentar
6. Devolver con confidence

Esto evita respuestas basadas en chunks irrelevantes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from albra.observability.logger import get_logger
from albra.memory.store import MemoryDV
from albra.research.engine import ResearchEngine


@dataclass
class CRAGResult:
    query: str
    items: list[dict[str, Any]] = field(default_factory=list)
    source: str = "memory"  # memory | web | none
    confidence: float = 0.0
    rewritten_query: str | None = None
    iterations: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "items": self.items,
            "source": self.source,
            "confidence": self.confidence,
            "rewritten_query": self.rewritten_query,
            "iterations": self.iterations,
        }


class CRAG:
    """Corrective RAG."""

    RELEVANCE_THRESHOLD = 0.35  # si el mejor score < threshold, fallback
    MAX_REWRITES = 2

    def __init__(
        self,
        *,
        memory: MemoryDV,
        research: ResearchEngine | None = None,
    ) -> None:
        self.memory = memory
        self.research = research
        self.log = get_logger("albra.crag")

    async def retrieve(self, query: str, *, top_k: int = 5) -> CRAGResult:
        result = CRAGResult(query=query)

        # Iteración 0: recuperar de memoria
        items = await self.memory.retrieve(query, top_k=top_k)
        result.iterations += 1
        if items:
            best_score = items[0].get("score", 0.0)
            if best_score >= self.RELEVANCE_THRESHOLD:
                result.items = items
                result.source = "memory"
                result.confidence = best_score
                self.log.info("crag.memory_hit", query=query[:50], score=best_score)
                return result

        # Iteración 1: reescribir query
        rewritten = self._rewrite_query(query)
        if rewritten and rewritten != query:
            result.rewritten_query = rewritten
            items = await self.memory.retrieve(rewritten, top_k=top_k)
            result.iterations += 1
            if items and items[0].get("score", 0.0) >= self.RELEVANCE_THRESHOLD:
                result.items = items
                result.source = "memory"
                result.confidence = items[0]["score"]
                self.log.info("crag.memory_hit_after_rewrite", query=query[:50])
                return result

        # Iteración 2: fallback a research web
        if self.research:
            try:
                web_results = await self.research.search(query, top_k=top_k)
                if web_results.get("ok") and web_results.get("findings"):
                    result.items = [
                        {
                            "text": f["snippet"],
                            "source": f["source_url"],
                            "source_type": f["source_type"],
                            "score": f["confidence"],
                            "kind": "web_finding",
                        }
                        for f in web_results["findings"]
                    ]
                    result.source = "web"
                    result.confidence = (
                        max((f["confidence"] for f in web_results["findings"]), default=0.0)
                    )
                    self.log.info("crag.web_fallback", query=query[:50])
                    return result
            except Exception as e:  # noqa: BLE001
                self.log.warning("crag.web_fallback.error", error=str(e))

        # No encontró nada
        result.source = "none"
        result.confidence = 0.0
        result.items = []
        self.log.info("crag.no_relevant", query=query[:50])
        return result

    def _rewrite_query(self, query: str) -> str | None:
        """Reescribe la query - heurística simple.

        Producción: usar LLM para reformular.
        """
        q = query.strip()
        if not q:
            return None
        # Si termina en signo de pregunta, quitarlo
        if q.endswith("?"):
            return q[:-1] + " ley vigente Colombia"
        # Si menciona "artículo", agregar contexto
        if "artículo" in q.lower() or "articulo" in q.lower():
            return q + " texto vigente"
        # Si menciona "ley", agregar "Colombia"
        if "ley" in q.lower() and "colombia" not in q.lower():
            return q + " Colombia"
        return None
