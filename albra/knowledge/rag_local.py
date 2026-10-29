"""
RAG LOCAL — Retrieval-Augmented Generation ligero (sin dependencias ML).

V2.2: TF-IDF + cosine similarity en Python puro.
V2.3+: migrar a bge-m3 + Qdrant si se quiere embeddings densos.

Pipeline:
1. index_document(document) → agrega al índice TF-IDF (1 chunk por artículo)
2. search(query, k=5) → top-k chunks rankeados por cosine sim
3. persist()/load() → guarda/carga índice en disco (JSON)

Corpus ya existe: albra/knowledge/colombia/corpus_pilot/real_corpus_v11.py
- Constitución 1991 (6 arts), Ley 100/1993 (3 arts), Ley 80/1993 (3 arts) = 12 chunks

REGLA CRÍTICA (lightweight): no usar numpy, sklearn, sentence-transformers
ni Qdrant. Implementación 100% Python puro para permitir despliegue
zero-dependency en el despacho jurídico.

Stopwords: lista curada español + fallback inglés. Tokenizer regex
`\\b\\w{2,}\\b` (excluye 1-char). min_score filter para evitar ruido.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from albra.observability.logger import get_logger

# =========================================================================
# Stopwords español + fallback inglés
# =========================================================================
_SPANISH_STOPWORDS: frozenset[str] = frozenset({
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del",
    "y", "o", "a", "en", "que", "se", "su", "sus", "es", "son", "por",
    "para", "con", "sin", "no", "si", "al", "lo", "le", "les", "como",
    "mas", "más", "este", "esta", "estos", "estas", "ese", "esa", "eso",
    "fue", "ser", "han", "ha", "he", "esto",
    # english fallback
    "the", "and", "or", "of", "to", "in", "on", "for", "with",
})


def _tokenize(text: str) -> list[str]:
    """Tokeniza en español: lower + regex \\w{2,} + stopword filter."""
    if not text:
        return []
    lowered = text.lower()
    tokens = re.findall(r"\b\w{2,}\b", lowered, re.UNICODE)
    return [t for t in tokens if t not in _SPANISH_STOPWORDS]


# =========================================================================
# Índice TF-IDF puro (sin numpy/sklearn)
# =========================================================================
class _TFIDFIndex:
    """Índice TF-IDF con cosine similarity en Python puro.

    Cada chunk es un dict con claves: source_id, document_name,
    document_type, article_number, text. El texto indexado se augmenta
    con metadatos (document_name + 'Artículo N.') para que las consultas
    tipo "Constitución artículo 13" recuperen el chunk correcto.
    """

    def __init__(self) -> None:
        self.documents: list[dict[str, Any]] = []
        self.df: Counter[str] = Counter()
        self.tf: list[Counter[str]] = []
        self.vocabulary: set[str] = set()

    @staticmethod
    def _searchable_text(chunk: dict[str, Any]) -> str:
        """Texto indexado: metadatos + contenido del artículo."""
        parts: list[str] = []
        if chunk.get("document_name"):
            parts.append(str(chunk["document_name"]))
        if chunk.get("article_number"):
            parts.append(f"Artículo {chunk['article_number']}")
        if chunk.get("text"):
            parts.append(str(chunk["text"]))
        return ". ".join(parts)

    def add(self, chunk: dict[str, Any]) -> None:
        """Agrega un chunk al índice."""
        searchable = self._searchable_text(chunk)
        tokens = _tokenize(searchable)
        tf = Counter(tokens)
        self.tf.append(tf)
        self.documents.append(chunk)
        for token in tf.keys():
            self.df[token] += 1
            self.vocabulary.add(token)

    def search(
        self,
        query: str,
        k: int | None = 5,
    ) -> list[tuple[dict[str, Any], float]]:
        """Busca top-k chunks por cosine similarity TF-IDF.

        Returns lista de (chunk, score) ordenada desc por score.
        Solo incluye chunks con score > 0.
        k=None → devuelve todos los matches con score > 0.
        """
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []
        n_docs = len(self.documents)
        if n_docs == 0:
            return []
        # idf solo para query tokens presentes en el vocabulario
        idf: dict[str, float] = {
            t: math.log(n_docs / (1 + self.df[t]))
            for t in query_tokens
            if t in self.vocabulary
        }
        if not idf:
            return []
        query_tf = Counter(query_tokens)
        # query_vec: TF * IDF (0 si el token no está en el vocabulario)
        query_vec: dict[str, float] = {
            t: query_tf[t] * idf.get(t, 0.0) for t in query_tokens
        }
        norm_q = math.sqrt(sum(v * v for v in query_vec.values()))
        if norm_q == 0.0:
            return []
        scores: list[tuple[int, float]] = []
        for i, doc_tf in enumerate(self.tf):
            # dot product (solo tokens compartidos)
            dot = 0.0
            norm_d_sq = 0.0
            for t in doc_tf:
                if t not in idf:
                    continue
                weight = doc_tf[t] * idf[t]
                norm_d_sq += weight * weight
                qv = query_vec.get(t, 0.0)
                if qv != 0.0:
                    dot += qv * weight
            norm_d = math.sqrt(norm_d_sq) if norm_d_sq > 0 else 0.0
            score = dot / (norm_q * norm_d) if norm_d > 0 else 0.0
            scores.append((i, score))
        scores.sort(key=lambda x: -x[1])
        results = [
            (self.documents[i], s) for i, s in scores if s > 0.0
        ]
        if k is not None:
            results = results[:k]
        return results


# =========================================================================
# LocalRAG — wrapper público con persistencia
# =========================================================================
class LocalRAG:
    """RAG local ligero basado en TF-IDF + cosine similarity.

    Inspiración clean-room: patrón de Lawgent + Prism (RAG local zero-deps).
    Recreado desde cero, sin ver el código fuente. Implementación
    deliberadamente minimal: Python puro, sin numpy ni sklearn ni
    sentence-transformers ni Qdrant. Diseñado para corpus pequeños
    (≤1000 chunks); para escala mayor, migrar a V2.3+ (bge-m3 + Qdrant).
    """

    def __init__(self, persist_path: str | None = None) -> None:
        self.log = get_logger("albra.knowledge.rag_local")
        self._index = _TFIDFIndex()
        self.persist_path: str | None = persist_path

    # ===== Indexación =====

    def index_document(self, document: dict[str, Any]) -> int:
        """Indexa 1 chunk por artículo del documento.

        Acepta un dict con:
        - source_id (str)
        - document_type (str) — e.g. "constitucion", "ley"
        - number (str) — nombre humano, e.g. "Constitución Política de 1991"
        - articles (list[{number, text}])

        Returns: número de chunks indexados.
        """
        source_id = document.get("source_id", "")
        document_name = (
            document.get("number")
            or document.get("document_name")
            or ""
        )
        document_type = document.get("document_type", "")
        articles = document.get("articles", []) or []
        count = 0
        for art in articles:
            chunk = {
                "source_id": source_id,
                "document_name": document_name,
                "document_type": document_type,
                "article_number": str(art.get("number", "")),
                "text": art.get("text", ""),
            }
            self._index.add(chunk)
            count += 1
        self.log.info(
            "rag_local.index_document",
            source_id=source_id,
            document_name=document_name,
            chunks=count,
        )
        return count

    def index_corpus(self, corpus_module: Any) -> int:
        """Indexa ALL_DOCUMENTS del módulo de corpus.

        Soporta ALL_DOCUMENTS como:
        - list[tuple[type_str, doc_dict]] (formato real_corpus_v11)
        - list[doc_dict] (formato alternativo)

        Returns: número total de chunks indexados.
        """
        all_docs = getattr(corpus_module, "ALL_DOCUMENTS", None)
        if all_docs is None:
            raise AttributeError(
                f"{corpus_module.__name__} no expone ALL_DOCUMENTS"
            )
        total = 0
        for item in all_docs:
            if isinstance(item, tuple) and len(item) == 2:
                # (type_str, doc_dict)
                doc = item[1]
            else:
                doc = item
            total += self.index_document(doc)
        self.log.info(
            "rag_local.index_corpus",
            module=corpus_module.__name__,
            total_chunks=total,
        )
        return total

    # ===== Búsqueda =====

    def search(
        self,
        query: str,
        k: int = 5,
        min_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Top-k chunks rankeados por cosine similarity.

        Cada result: {source_id, document_name, document_type,
        article_number, text, score}. Filtra por min_score (inclusive)
        y devuelve máximo k resultados.
        """
        # Pedimos todos los matches al índice (k=None) para poder
        # aplicar min_score filter y luego truncar a k.
        matches = self._index.search(query, k=None)
        results: list[dict[str, Any]] = []
        for chunk, score in matches:
            if score < min_score:
                continue
            results.append({
                "source_id": chunk["source_id"],
                "document_name": chunk["document_name"],
                "document_type": chunk["document_type"],
                "article_number": chunk["article_number"],
                "text": chunk["text"],
                "score": score,
            })
            if len(results) >= k:
                break
        self.log.info(
            "rag_local.search",
            query=query[:80],
            k=k,
            min_score=min_score,
            returned=len(results),
        )
        return results

    # ===== Stats / persistencia =====

    def stats(self) -> dict[str, Any]:
        """Estadísticas del índice."""
        doc_ids = {c["source_id"] for c in self._index.documents}
        return {
            "documents": len(doc_ids),
            "chunks": len(self._index.documents),
            "vocabulary_size": len(self._index.vocabulary),
            "persist_path": self.persist_path,
        }

    def persist(self, path: str | None = None) -> str:
        """Persiste el índice a JSON. Returns ruta usada."""
        target = path or self.persist_path
        if not target:
            raise ValueError(
                "No persist path provided (set persist_path or pass path)"
            )
        target_path = Path(target)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "documents": self._index.documents,
            "df": self._index.df,
            "tf": self._index.tf,
            "vocabulary": self._index.vocabulary,
        }
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, default=str)
        self.persist_path = str(target_path)
        self.log.info(
            "rag_local.persist",
            path=str(target_path),
            chunks=len(self._index.documents),
        )
        return str(target_path)

    def load(self, path: str | None = None) -> bool:
        """Carga índice desde JSON. Returns True si cargó, False si no."""
        target = path or self.persist_path
        if not target:
            return False
        target_path = Path(target)
        if not target_path.exists():
            return False
        with open(target_path, "r", encoding="utf-8") as f:
            payload = json.load(f)  # noqa: S301 (trusted local cache)
        self._index.documents = payload["documents"]
        self._index.df = payload["df"]
        self._index.tf = payload["tf"]
        self._index.vocabulary = payload["vocabulary"]
        self.persist_path = str(target_path)
        self.log.info(
            "rag_local.load",
            path=str(target_path),
            chunks=len(self._index.documents),
        )
        return True

    def clear(self) -> None:
        """Resetea el índice a estado vacío."""
        self._index = _TFIDFIndex()
        self.log.info("rag_local.clear")


# =========================================================================
# Helper: default_rag con corpus V1.1 indexado
# =========================================================================
def default_rag() -> LocalRAG:
    """Crea LocalRAG con corpus V1.1 (real_corpus_v11) indexado."""
    rag = LocalRAG()
    from albra.knowledge.colombia.corpus_pilot.real_corpus_v11 import (
        ALL_DOCUMENTS,
    )
    for _doc_type, doc in ALL_DOCUMENTS:
        rag.index_document(doc)
    return rag
