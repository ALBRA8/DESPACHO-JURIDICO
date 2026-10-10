"""
memorydv - Memoria vectorial ALBRA.

Soporta el ciclo completo:
  WRITE → INDEX → EMBED → STORE → RETRIEVE → RERANK → CONTEXTUALIZE → USE → UPDATE/CONSOLIDATE

Backend por defecto: sqlite + embeddings hash (sin dependencias externas).
Backends futuros: chroma, faiss, weaviate.

6 categorías SEPARADAS:
- conversacional
- operativa
- conocimiento
- documental
- evidencia
- configuración
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from albra.config.settings import Settings
from albra.memory.categories import MEMORY_CATEGORIES
from albra.observability.logger import get_logger


def _hash_embedding(text: str, dim: int = 256) -> list[float]:
    """Embedding determinista vía hash - sin deps externas.

    Producción: sustituir por OpenAI / sentence-transformers / etc.
    """
    text = text.lower()
    vec = [0.0] * dim
    for i in range(0, len(text), 2):
        chunk = text[i : i + 2]
        h = int(hashlib.md5(chunk.encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0
    # Normalizar a norma unitaria
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


class MemoryDV:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.memory")
        self._backend = settings.memory_backend
        self._path = settings.memory_path
        self._dim = settings.memory_vector_dim
        self._mem: list[dict[str, Any]] = []  # inmemory fallback
        self._conn: sqlite3.Connection | None = None

        Path(self._path).parent.mkdir(parents=True, exist_ok=True)

        if self._backend == "sqlite":
            self._init_sqlite()
        else:
            self.log.info("memory.using_inmemory")

    def _init_sqlite(self) -> None:
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_items (
                id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                text TEXT NOT NULL,
                embedding TEXT NOT NULL,
                metadata TEXT,
                ts REAL NOT NULL,
                version INTEGER DEFAULT 1,
                active INTEGER DEFAULT 1
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mem_cat ON memory_items(category, active)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mem_ts ON memory_items(ts DESC)"
        )
        self._conn.commit()
        self.log.info("memory.sqlite.ready", path=self._path)

    @contextmanager
    def _cursor(self) -> Iterator[Any]:
        if self._conn:
            cur = self._conn.cursor()
            try:
                yield cur
                self._conn.commit()
            finally:
                cur.close()
        else:
            yield None  # type: ignore[return-value]

    async def startup(self) -> None:
        self.log.info("memory.startup", backend=self._backend, dim=self._dim)

    async def shutdown(self) -> None:
        if self._conn:
            self._conn.close()
        self.log.info("memory.shutdown")

    # --- Ciclo: WRITE → INDEX → EMBED → STORE ---

    async def write(
        self,
        text: str,
        *,
        category: str = "conversational",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """WRITE → INDEX → EMBED → STORE."""
        if category not in MEMORY_CATEGORIES:
            raise ValueError(f"Categoría inválida: {category}")

        item_id = uuid.uuid4().hex[:24]
        emb = _hash_embedding(text, self._dim)
        now = time.time()

        if self._conn:
            with self._cursor() as cur:
                cur.execute(
                    "INSERT INTO memory_items (id, category, text, embedding, metadata, ts, active) "
                    "VALUES (?, ?, ?, ?, ?, ?, 1)",
                    (
                        item_id,
                        category,
                        text,
                        json.dumps(emb),
                        json.dumps(metadata or {}),
                        now,
                    ),
                )
        else:
            self._mem.append(
                {
                    "id": item_id,
                    "category": category,
                    "text": text,
                    "embedding": emb,
                    "metadata": metadata or {},
                    "ts": now,
                    "version": 1,
                    "active": 1,
                }
            )
        self.log.info("memory.write", id=item_id, category=category, len=len(text))
        return item_id

    # --- Ciclo: RETRIEVE → RERANK → CONTEXTUALIZE ---

    async def retrieve(
        self,
        query: str,
        *,
        category: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """RETRIEVE → RERANK → CONTEXTUALIZE (devuelve top-k con score)."""
        q_emb = _hash_embedding(query, self._dim)
        results: list[dict[str, Any]] = []

        if self._conn:
            with self._cursor() as cur:
                if cur is None:
                    return []
                if category:
                    cur.execute(
                        "SELECT id, category, text, embedding, metadata, ts, version "
                        "FROM memory_items WHERE category = ? AND active = 1 "
                        "ORDER BY ts DESC LIMIT 500",
                        (category,),
                    )
                else:
                    cur.execute(
                        "SELECT id, category, text, embedding, metadata, ts, version "
                        "FROM memory_items WHERE active = 1 "
                        "ORDER BY ts DESC LIMIT 500"
                    )
                rows = cur.fetchall()
            for r in rows:
                emb = json.loads(r[3])
                score = _cosine(q_emb, emb)
                results.append(
                    {
                        "id": r[0],
                        "category": r[1],
                        "text": r[2],
                        "metadata": json.loads(r[4]),
                        "ts": r[5],
                        "version": r[6],
                        "score": score,
                    }
                )
        else:
            for item in self._mem:
                if not item["active"]:
                    continue
                if category and item["category"] != category:
                    continue
                score = _cosine(q_emb, item["embedding"])
                results.append({**item, "score": score})

        # RERANK by score
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    # --- UPDATE / CONSOLIDATE ---

    async def update(self, item_id: str, new_text: str) -> bool:
        if self._conn:
            with self._cursor() as cur:
                if cur is None:
                    return False
                emb = _hash_embedding(new_text, self._dim)
                cur.execute(
                    "UPDATE memory_items SET text = ?, embedding = ?, version = version + 1 "
                    "WHERE id = ?",
                    (new_text, json.dumps(emb), item_id),
                )
                return cur.rowcount > 0
        for item in self._mem:
            if item["id"] == item_id:
                item["text"] = new_text
                item["embedding"] = _hash_embedding(new_text, self._dim)
                item["version"] += 1
                return True
        return False

    async def deactivate(self, item_id: str) -> bool:
        """Invalidate without delete - mantiene versión histórica."""
        if self._conn:
            with self._cursor() as cur:
                if cur is None:
                    return False
                cur.execute(
                    "UPDATE memory_items SET active = 0 WHERE id = ?", (item_id,)
                )
                return cur.rowcount > 0
        for item in self._mem:
            if item["id"] == item_id:
                item["active"] = 0
                return True
        return False

    async def consolidate(self, category: str, *, similarity_threshold: float = 0.95) -> int:
        """Consolida items duplicados en una categoría."""
        items = await self.retrieve("", category=category, top_k=500)
        merged = 0
        seen: list[dict[str, Any]] = []
        for item in items:
            is_dup = False
            for s in seen:
                if _cosine(item.get("embedding", []), s.get("embedding", [])) > similarity_threshold:
                    await self.deactivate(item["id"])
                    merged += 1
                    is_dup = True
                    break
            if not is_dup:
                seen.append(item)
        self.log.info("memory.consolidated", category=category, merged=merged)
        return merged

    def stats(self) -> dict[str, Any]:
        if self._conn:
            with self._cursor() as cur:
                if cur is None:
                    return {}
                cur.execute(
                    "SELECT category, COUNT(*) FROM memory_items WHERE active=1 GROUP BY category"
                )
                return {r[0]: r[1] for r in cur.fetchall()}
        return {cat: sum(1 for i in self._mem if i["category"] == cat and i["active"]) for cat in MEMORY_CATEGORIES}
