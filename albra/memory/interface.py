"""
MEMORY INTERFACE ALBRA - abstracción backend.

Permite cambiar backend (sqlite, chroma, postgres) sin tocar el agente.

Contrato:
  MemoryProvider (interface)
    → write(item) → id
    → retrieve(query, top_k) → list[MemoryItem]
    → update(id, text)
    → deactivate(id)
    → consolidate(category)
    → stats()

Implementaciones:
- InMemoryProvider (default, sin deps)
- SQLiteProvider (sqlite + hash embedding)
- ChromaProvider (futuro - no implementado, NO inventado)
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

# --- Truth Levels (RADAR-SECOP2 evidence.ts style) ---
TRUTH_LEVELS: tuple[str, ...] = (
    "VERIFIED",       # corroborado por fuente primaria
    "OBSERVED",       # dato real observado (API, cita textual)
    "INFERRED",       # deducido a partir de otros datos
    "ESTIMATED",      # aproximación
    "UNKNOWN",        # no se sabe
)


# --- Provenance ---
PROVENANCE_TYPES: tuple[str, ...] = (
    "USER_INPUT",       # dato que vino del usuario
    "AI_MODEL",         # generado por LLM
    "CONSOLIDATED",     # destilado de varios items
    "OFFICIAL_SOURCE",  # fuente oficial
    "TOOL_OUTPUT",      # salida de una tool
    "EXTERNAL_API",     # API externa
)


# --- Status ---
STATUS_TYPES: tuple[str, ...] = (
    "active",       # en uso
    "deprecated",   # soft-delete - se conserva para auditoría
    "retired",      # archivado - no aparece en búsquedas
)


@dataclass
class MemoryItem:
    id: str
    category: str
    text: str
    truth_level: str = "UNKNOWN"
    provenance: str = "USER_INPUT"
    status: str = "active"
    source: str = ""
    confidence: float = 0.5
    relevance: float = 1.0  # decay con tiempo
    embedding: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    last_seen: float = 0.0
    version: int = 1
    depends_on: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "text": self.text,
            "truth_level": self.truth_level,
            "provenance": self.provenance,
            "status": self.status,
            "source": self.source,
            "confidence": self.confidence,
            "relevance": self.relevance,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "last_seen": self.last_seen,
            "version": self.version,
            "depends_on": self.depends_on,
        }


class MemoryProvider(ABC):
    """Interface que implementan los backends."""

    @abstractmethod
    async def write(self, item: MemoryItem) -> str: ...

    @abstractmethod
    async def retrieve(self, query: str, *, category: str | None = None, top_k: int = 5) -> list[MemoryItem]: ...

    @abstractmethod
    async def update(self, item_id: str, new_text: str) -> bool: ...

    @abstractmethod
    async def deactivate(self, item_id: str) -> bool: ...

    @abstractmethod
    async def consolidate(self, category: str, *, similarity_threshold: float = 0.95) -> int: ...

    @abstractmethod
    async def decay(self, *, days_threshold: int = 30, decay_amount: float = 0.05) -> int: ...

    @abstractmethod
    def stats(self) -> dict[str, Any]: ...


    @abstractmethod
    async def startup(self) -> None: ...

    @abstractmethod
    async def shutdown(self) -> None: ...


def _hash_embedding(text: str, dim: int = 256) -> list[float]:
    import hashlib
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


class InMemoryProvider(MemoryProvider):
    """Provider en memoria - sin deps externos."""

    def __init__(self, *, vector_dim: int = 256) -> None:
        self._items: list[MemoryItem] = []
        self._dim = vector_dim

    async def startup(self) -> None: ...
    async def shutdown(self) -> None: ...

    async def write(self, item: MemoryItem) -> str:
        if not item.embedding:
            item.embedding = _hash_embedding(item.text, self._dim)
        import time
        if not item.created_at:
            item.created_at = time.time()
            item.last_seen = item.created_at
        self._items.append(item)
        return item.id

    async def retrieve(self, query: str, *, category: str | None = None, top_k: int = 5) -> list[MemoryItem]:
        q_emb = _hash_embedding(query, self._dim)
        items = [i for i in self._items if i.status == "active"]
        if category:
            items = [i for i in items if i.category == category]
        scored = [(i, _cosine(q_emb, i.embedding) * i.relevance) for i in items]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [i for i, _ in scored[:top_k]]

    async def update(self, item_id: str, new_text: str) -> bool:
        for item in self._items:
            if item.id == item_id:
                item.text = new_text
                item.embedding = _hash_embedding(new_text, self._dim)
                item.version += 1
                import time
                item.last_seen = time.time()
                return True
        return False

    async def deactivate(self, item_id: str) -> bool:
        for item in self._items:
            if item.id == item_id:
                item.status = "deprecated"
                return True
        return False

    async def consolidate(self, category: str, *, similarity_threshold: float = 0.95) -> int:
        items = [i for i in self._items if i.category == category and i.status == "active"]
        merged = 0
        seen: list[MemoryItem] = []
        for item in items:
            is_dup = False
            for s in seen:
                if _cosine(item.embedding, s.embedding) > similarity_threshold:
                    await self.deactivate(item.id)
                    merged += 1
                    is_dup = True
                    break
            if not is_dup:
                seen.append(item)
        return merged

    async def decay(self, *, days_threshold: int = 30, decay_amount: float = 0.05) -> int:
        import time
        cutoff = time.time() - (days_threshold * 86400)
        decayed = 0
        for item in self._items:
            if item.last_seen < cutoff and item.status == "active":
                item.relevance = max(0.0, item.relevance - decay_amount)
                decayed += 1
        return decayed

    def stats(self) -> dict[str, Any]:
        from collections import Counter
        c = Counter(i.category for i in self._items if i.status == "active")
        return {
            "by_category": dict(c),
            "total": sum(c.values()),
            "deprecated": sum(1 for i in self._items if i.status == "deprecated"),
            "by_truth_level": dict(Counter(i.truth_level for i in self._items if i.status == "active")),
            "by_provenance": dict(Counter(i.provenance for i in self._items if i.status == "active")),
        }


class SQLiteProvider(MemoryProvider):
    """Provider SQLite - persistente."""

    def __init__(self, *, db_path: str, vector_dim: int = 256) -> None:
        import sqlite3
        from pathlib import Path
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._dim = vector_dim
        self._init_db()

    def _init_db(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memory_items (
                id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                text TEXT NOT NULL,
                truth_level TEXT DEFAULT 'UNKNOWN',
                provenance TEXT DEFAULT 'USER_INPUT',
                status TEXT DEFAULT 'active',
                source TEXT DEFAULT '',
                confidence REAL DEFAULT 0.5,
                relevance REAL DEFAULT 1.0,
                embedding TEXT NOT NULL,
                metadata_json TEXT DEFAULT '{}',
                created_at REAL NOT NULL,
                last_seen REAL NOT NULL,
                version INTEGER DEFAULT 1,
                depends_on_json TEXT DEFAULT '[]'
            );
            CREATE INDEX IF NOT EXISTS idx_mi_cat ON memory_items(category, status);
            CREATE INDEX IF NOT EXISTS idx_mi_ts ON memory_items(last_seen DESC);
            CREATE INDEX IF NOT EXISTS idx_mi_truth ON memory_items(truth_level);
            """
        )
        self._conn.commit()

    async def startup(self) -> None: ...
    async def shutdown(self) -> None:
        if self._conn:
            self._conn.close()

    async def write(self, item: MemoryItem) -> str:
        import json
        import time
        if not item.embedding:
            item.embedding = _hash_embedding(item.text, self._dim)
        if not item.created_at:
            item.created_at = time.time()
            item.last_seen = item.created_at
        self._conn.execute(
            "INSERT INTO memory_items (id, category, text, truth_level, provenance, status, "
            "source, confidence, relevance, embedding, metadata_json, created_at, last_seen, "
            "version, depends_on_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item.id, item.category, item.text, item.truth_level, item.provenance,
                item.status, item.source, item.confidence, item.relevance,
                json.dumps(item.embedding), json.dumps(item.metadata),
                item.created_at, item.last_seen, item.version,
                json.dumps(item.depends_on),
            ),
        )
        self._conn.commit()
        return item.id

    async def retrieve(self, query: str, *, category: str | None = None, top_k: int = 5) -> list[MemoryItem]:
        q_emb = _hash_embedding(query, self._dim)
        if category:
            cur = self._conn.execute(
                "SELECT * FROM memory_items WHERE category = ? AND status = 'active' "
                "ORDER BY last_seen DESC LIMIT 500",
                (category,),
            )
        else:
            cur = self._conn.execute(
                "SELECT * FROM memory_items WHERE status = 'active' "
                "ORDER BY last_seen DESC LIMIT 500"
            )
        rows = cur.fetchall()
        items: list[tuple[MemoryItem, float]] = []
        for r in rows:
            item = self._row_to_item(r)
            score = _cosine(q_emb, item.embedding) * item.relevance
            items.append((item, score))
        items.sort(key=lambda x: x[1], reverse=True)
        return [i for i, _ in items[:top_k]]

    def _row_to_item(self, row: tuple) -> MemoryItem:
        import json
        return MemoryItem(
            id=row[0],
            category=row[1],
            text=row[2],
            truth_level=row[3],
            provenance=row[4],
            status=row[5],
            source=row[6],
            confidence=row[7],
            relevance=row[8],
            embedding=json.loads(row[9]),
            metadata=json.loads(row[10]),
            created_at=row[11],
            last_seen=row[12],
            version=row[13],
            depends_on=json.loads(row[14]),
        )

    async def update(self, item_id: str, new_text: str) -> bool:
        import time
        new_emb = _hash_embedding(new_text, self._dim)
        import json
        cur = self._conn.execute(
            "UPDATE memory_items SET text = ?, embedding = ?, version = version + 1, "
            "last_seen = ? WHERE id = ?",
            (new_text, json.dumps(new_emb), time.time(), item_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    async def deactivate(self, item_id: str) -> bool:
        cur = self._conn.execute(
            "UPDATE memory_items SET status = 'deprecated' WHERE id = ?",
            (item_id,),
        )
        self._conn.commit()
        return cur.rowcount > 0

    async def consolidate(self, category: str, *, similarity_threshold: float = 0.95) -> int:
        items = await self.retrieve("", category=category, top_k=500)
        merged = 0
        seen: list[MemoryItem] = []
        for item in items:
            is_dup = False
            for s in seen:
                if _cosine(item.embedding, s.embedding) > similarity_threshold:
                    await self.deactivate(item.id)
                    merged += 1
                    is_dup = True
                    break
            if not is_dup:
                seen.append(item)
        return merged

    async def decay(self, *, days_threshold: int = 30, decay_amount: float = 0.05) -> int:
        import time
        cutoff = time.time() - (days_threshold * 86400)
        cur = self._conn.execute(
            "UPDATE memory_items SET relevance = MAX(0, relevance - ?) "
            "WHERE last_seen < ? AND status = 'active'",
            (decay_amount, cutoff),
        )
        self._conn.commit()
        return cur.rowcount

    def stats(self) -> dict[str, Any]:
        cur = self._conn.execute(
            "SELECT category, COUNT(*) FROM memory_items WHERE status='active' GROUP BY category"
        )
        by_cat = {r[0]: r[1] for r in cur.fetchall()}
        cur = self._conn.execute(
            "SELECT truth_level, COUNT(*) FROM memory_items WHERE status='active' GROUP BY truth_level"
        )
        by_truth = {r[0]: r[1] for r in cur.fetchall()}
        cur = self._conn.execute(
            "SELECT provenance, COUNT(*) FROM memory_items WHERE status='active' GROUP BY provenance"
        )
        by_prov = {r[0]: r[1] for r in cur.fetchall()}
        return {
            "by_category": by_cat,
            "total": sum(by_cat.values()),
            "by_truth_level": by_truth,
            "by_provenance": by_prov,
        }


class MemoryInterface:
    """Façade - selecciona backend según config."""

    def __init__(self, *, backend: str = "inmemory", db_path: str = "./data/memory.db", vector_dim: int = 256) -> None:
        self.backend_name = backend
        if backend == "sqlite":
            self._provider: MemoryProvider = SQLiteProvider(db_path=db_path, vector_dim=vector_dim)
        else:
            self._provider = InMemoryProvider(vector_dim=vector_dim)

    @property
    def provider(self) -> MemoryProvider:
        return self._provider

    async def write(
        self,
        text: str,
        *,
        category: str = "operational",
        truth_level: str = "UNKNOWN",
        provenance: str = "USER_INPUT",
        source: str = "",
        confidence: float = 0.5,
        metadata: dict[str, Any] | None = None,
        depends_on: list[str] | None = None,
    ) -> str:
        import time
        import uuid
        item = MemoryItem(
            id=uuid.uuid4().hex[:24],
            category=category,
            text=text,
            truth_level=truth_level,
            provenance=provenance,
            source=source,
            confidence=confidence,
            metadata=metadata or {},
            depends_on=depends_on or [],
            created_at=time.time(),
            last_seen=time.time(),
        )
        return await self._provider.write(item)

    async def retrieve(self, query: str, *, category: str | None = None, top_k: int = 5) -> list[MemoryItem]:
        return await self._provider.retrieve(query, category=category, top_k=top_k)

    async def update(self, item_id: str, new_text: str) -> bool:
        return await self._provider.update(item_id, new_text)

    async def deactivate(self, item_id: str) -> bool:
        return await self._provider.deactivate(item_id)

    async def consolidate(self, category: str, *, similarity_threshold: float = 0.95) -> int:
        return await self._provider.consolidate(category, similarity_threshold=similarity_threshold)

    async def decay(self, *, days_threshold: int = 30, decay_amount: float = 0.05) -> int:
        return await self._provider.decay(days_threshold=days_threshold, decay_amount=decay_amount)

    def stats(self) -> dict[str, Any]:
        return self._provider.stats()

    async def startup(self) -> None:
        await self._provider.startup()

    async def shutdown(self) -> None:
        await self._provider.shutdown()


def can_back_compliance(truth_level: str) -> bool:
    """Solo VERIFIED u OBSERVED pueden respaldar un CUMPLE definitivo."""
    return truth_level in ("VERIFIED", "OBSERVED")


def normalize_truth_level(v: str | None) -> str:
    if not v:
        return "UNKNOWN"
    up = v.strip().upper()
    return up if up in TRUTH_LEVELS else "UNKNOWN"
