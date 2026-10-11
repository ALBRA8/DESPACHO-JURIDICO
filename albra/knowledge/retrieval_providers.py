"""
RETRIEVAL PROVIDERS - Implementaciones.

InMemoryRetrievalProvider: default, sin deps, hash embedding.
(futuro SQLiteRetrievalProvider, QdrantRetrievalProvider)
"""
from __future__ import annotations

import hashlib
import math
import time
from typing import Any

from albra.knowledge.retrieval import (
    RetrievalProvider,
    RetrievalQuery,
    RetrievalResult,
)
from albra.knowledge.schemas import (
    Article,
    Doctrine,
    EvidenceCandidate,
    Jurisprudence,
    Norm,
)
from albra.knowledge.temporal import is_vigente


def _hash_embedding(text: str, dim: int = 256) -> list[float]:
    """Embedding determinista vía hash - sin deps externas."""
    text = text.lower()
    vec = [0.0] * dim
    for i in range(0, len(text), 2):
        chunk = text[i : i + 2]
        h = int(hashlib.md5(chunk.encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


class InMemoryRetrievalProvider(RetrievalProvider):
    """In-memory retrieval provider - sin deps externas.

    Para producción: usar SQLiteRetrievalProvider o QdrantRetrievalProvider.
    """

    name = "inmemory"

    def __init__(self) -> None:
        self._norms: dict[str, Norm] = {}
        self._articles: dict[str, Article] = {}
        self._jurisprudence: dict[str, Jurisprudence] = {}
        self._doctrine: dict[str, Doctrine] = {}

    async def startup(self) -> None: ...
    async def shutdown(self) -> None: ...

    async def index_norm(self, norm: Norm, articles: list[Article]) -> str:
        self._norms[norm.id] = norm
        norm.article_ids = [a.id for a in articles]
        for a in articles:
            a.norm_id = norm.id
            if not a.embedding:
                a.embedding = _hash_embedding(a.text)
            self._articles[a.id] = a
        return norm.id

    async def index_jurisprudence(self, j: Jurisprudence) -> str:
        if not j.embedding:
            text = f"{j.legal_issue} {j.ratio_decidendi} {j.decision}"
            j.embedding = _hash_embedding(text)
        self._jurisprudence[j.id] = j
        return j.id

    async def index_doctrine(self, d: Doctrine) -> str:
        if not d.embedding:
            d.embedding = _hash_embedding(d.text or d.title)
        self._doctrine[d.id] = d
        return d.id

    async def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        t0 = time.time()
        candidates: list[EvidenceCandidate] = []

        # Exact retrieval
        if query.query_type == "exact" or query.norm_number or query.article_number:
            candidates.extend(self._exact_search(query))

        # Semantic retrieval
        if query.query_type in ("semantic", "hybrid") and query.query_text:
            candidates.extend(self._semantic_search(query))

        # Deduplicate by source_id
        seen = set()
        unique: list[EvidenceCandidate] = []
        for c in candidates:
            if c.source_id not in seen:
                seen.add(c.source_id)
                unique.append(c)

        result = RetrievalResult(
            candidates=unique,
            total_found=len(unique),
            query=query,
            elapsed_ms=(time.time() - t0) * 1000,
            backend=self.name,
        )

        # Abstention policy
        if not unique:
            result.abstention = True
            result.abstention_reason = (
                "No se encontró evidencia jurídica suficiente. "
                "ALBRA NO inventa conocimiento jurídico."
            )

        return result

    def _exact_search(self, query: RetrievalQuery) -> list[EvidenceCandidate]:
        """Búsqueda exacta por número de norma, artículo, expediente."""
        candidates: list[EvidenceCandidate] = []
        # Match by norm number
        if query.norm_number:
            for norm in self._norms.values():
                if norm.number and query.norm_number.lower() in norm.number.lower():
                    # Found norm - return its articles (or the specific article if requested)
                    for art_id in norm.article_ids:
                        art = self._articles.get(art_id)
                        if not art:
                            continue
                        if query.article_number and art.article_number != query.article_number:
                            continue
                        candidates.append(self._article_to_candidate(art, norm, score=1.0))

        # Match jurisprudence by file number
        if query.file_number:
            for j in self._jurisprudence.values():
                if j.file_number and query.file_number.lower() in j.file_number.lower():
                    candidates.append(self._jurisprudence_to_candidate(j, score=1.0))

        return candidates

    def _semantic_search(self, query: RetrievalQuery) -> list[EvidenceCandidate]:
        """Búsqueda semántica vía cosine similarity."""
        q_emb = _hash_embedding(query.query_text)
        candidates: list[EvidenceCandidate] = []

        # Search articles
        for art in self._articles.values():
            norm = self._norms.get(art.norm_id)
            if not norm:
                continue
            # Filter by jurisdiction
            if query.jurisdiction and norm.jurisdiction != query.jurisdiction:
                continue
            # Filter by authority
            if query.authority and query.authority.lower() not in norm.authority.lower():
                continue
            # Filter by source_tier
            if query.source_tier and norm.source_tier != query.source_tier:
                continue
            # Temporal filter
            if query.temporal and query.temporal.query_type != "any":
                from albra.knowledge.temporal import TemporalState
                ts = TemporalState(
                    status=norm.status,
                    effective_from=norm.effective_from,
                    effective_until=norm.effective_until,
                )
                if not query.temporal.matches(ts):
                    continue

            score = _cosine(q_emb, art.embedding)
            if score < query.min_score:
                continue
            candidates.append(self._article_to_candidate(art, norm, score=score))

        # Search jurisprudence
        for j in self._jurisprudence.values():
            if query.jurisdiction and j.authority and query.jurisdiction != "CO":
                continue
            score = _cosine(q_emb, j.embedding)
            if score < query.min_score:
                continue
            candidates.append(self._jurisprudence_to_candidate(j, score=score))

        # Search doctrine
        for d in self._doctrine.values():
            score = _cosine(q_emb, d.embedding)
            if score < query.min_score:
                continue
            candidates.append(self._doctrine_to_candidate(d, score=score))

        return candidates

    def _article_to_candidate(self, art: Article, norm: Norm, *, score: float) -> EvidenceCandidate:
        citation = f"{norm.number or norm.title}, art. {art.article_number}"
        is_current = is_vigente(
            status=norm.status,
            effective_from=norm.effective_from,
            effective_until=norm.effective_until,
        )
        return EvidenceCandidate(
            source_id=norm.source_id if hasattr(norm, "source_id") else norm.id,
            document_id=norm.id,
            source_tier=norm.source_tier,
            authority=norm.authority,
            document_type=norm.document_type,
            snippet=art.text[:300],
            citation=citation,
            score=score,
            is_current=is_current,
            retrieved_at=time.time(),
            provenance={
                "norm_id": norm.id,
                "article_id": art.id,
                "source_url": norm.source_url,
                "effective_from": str(norm.effective_from) if norm.effective_from else None,
                "effective_until": str(norm.effective_until) if norm.effective_until else None,
                "status": norm.status,
            },
        )

    def _jurisprudence_to_candidate(self, j: Jurisprudence, *, score: float) -> EvidenceCandidate:
        citation = f"{j.court}, {j.file_number}, {j.decision_date}"
        is_current = j.precedent_status == "vigente"
        return EvidenceCandidate(
            source_id=j.id,
            document_id=j.id,
            source_tier=j.source_tier,
            authority=j.court,
            document_type="sentencia",
            snippet=j.ratio_decidendi[:300] or j.decision[:300],
            citation=citation,
            score=score,
            is_current=is_current,
            retrieved_at=time.time(),
            provenance={
                "court": j.court,
                "file_number": j.file_number,
                "decision_date": str(j.decision_date) if j.decision_date else None,
                "ponente": j.ponente,
                "binding": j.binding,
            },
        )

    def _doctrine_to_candidate(self, d: Doctrine, *, score: float) -> EvidenceCandidate:
        citation = f"{d.author}, {d.title}, {d.publication_year}"
        return EvidenceCandidate(
            source_id=d.id,
            document_id=d.id,
            source_tier=d.source_tier,
            authority=d.authority or d.author,
            document_type=d.doctrine_type,
            snippet=d.text[:300] or d.abstract[:300],
            citation=citation,
            score=score,
            is_current=True,  # doctrine doesn't expire
            retrieved_at=time.time(),
            provenance={
                "author": d.author,
                "year": d.publication_year,
                "publisher": d.publisher,
            },
        )

    def stats(self) -> dict[str, Any]:
        return {
            "norms": len(self._norms),
            "articles": len(self._articles),
            "jurisprudence": len(self._jurisprudence),
            "doctrine": len(self._doctrine),
            "backend": self.name,
        }
