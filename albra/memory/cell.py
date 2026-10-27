"""
MEMORY CELL — capa arquitectónica separada de memoria del despacho.

Inspiración (clean-room): NewMind pattern (5-layer architecture:
Data Factory OntologicOS → Mecellem SemanticOS → Memory Cell NoeticOS →
Agent Factory AgenticOS → nmaistro ConducticOS). La memoria como LAYER,
no como FEATURE.

ALBRA V2.4-B: Memory Cell como capa separada entre MatterStore y los
agentes. Captura patrones longitudinales cross-matter sin fine-tuning.

Tipos de memoria capturados:
- matter_pattern: secuencias de states más comunes por área de práctica
- deadline_pattern: tipos de deadline más frecuentes por área
- citation_pattern: corpus más citado por área
- red_flag_pattern: red flags que se materializan más (V2.4-B placeholder:
  manual entry; V2.5+: learned from matter closure audit entries)

API:
- remember(matter_id, event_type, payload) -> cell_id
- recall(query, k=5) -> list[dict] (top-k memorias relevantes)
- get_patterns() -> dict (estadísticas agregadas)
- forget(cell_id) -> bool (GDPR-style deletion right; ALBRA V2.4-B: solo local)

Storage: SQLite local en data/memory_cell.db.
Cross-matter: las memorias se asocian al área de práctica, no al matter_id
(permite patrones cross-matter). matter_id se guarda como referencia pero
NO filtra recall (para patrones longitudinales).
"""
from __future__ import annotations

import json
import math
import sqlite3
import uuid
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from albra.knowledge.rag_local import _tokenize
from albra.observability.logger import get_logger


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _flatten_payload_text(payload: Any) -> str:
    """Convierte el payload dict en una cadena tokenizable.

    Extrae SOLO los valores string/número del dict, no las claves
    (para que TF-IDF puntúe por contenido, no por nombre del campo).
    Listas y dicts anidados se aplastan recursivamente.
    """
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, (int, float)):
        return str(payload)
    if isinstance(payload, dict):
        parts: list[str] = [
            _flatten_payload_text(v) for v in payload.values()
        ]
        return " ".join(p for p in parts if p)
    if isinstance(payload, (list, tuple)):
        parts_list = [_flatten_payload_text(v) for v in payload]
        return " ".join(p for p in parts_list if p)
    return str(payload)


class MemoryCell:
    """Capa arquitectónica de memoria cross-matter del despacho.

    Diferente a MemoryDV (V1.6 — vector store por categoría conversacional):
    MemoryCell captura eventos del despacho (matter_pattern, deadline_pattern,
    citation_pattern, red_flag_pattern) asociados al ÁREA de práctica, NO al
    matter_id. Esto permite que el recall recupere patrones de otras materias
    del mismo área (memoria longitudinal sin fine-tuning).

    API:
        cell = MemoryCell(db_path="./data/memory_cell.db")
        cid = cell.remember("matter-1", "matter_pattern",
                            {"sequence": "intake->discovery->trial"},
                            area="laboral", agent="intake-agent")
        hits = cell.recall("intake discovery", k=5, area="laboral")
        patterns = cell.get_patterns()
        cell.forget(cid)  # GDPR-style deletion right
        cell.close()

    Implementación: SQLite local + TF-IDF puro (sin numpy/sklearn), reusando
    `_tokenize` de `albra/knowledge/rag_local.py` para mantener stopwords
    y tokenizer consistentes con el corpus indexado.
    """

    def __init__(self, db_path: str = "./data/memory_cell.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log = get_logger("albra.memory.cell")
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_cells (
                id TEXT PRIMARY KEY,
                matter_id TEXT,
                area TEXT,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                agent TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mem_cells_area ON memory_cells(area)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mem_cells_event_type "
            "ON memory_cells(event_type)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mem_cells_matter "
            "ON memory_cells(matter_id)"
        )
        self._conn.commit()
        self.log.info("memory_cell.sqlite.ready", path=str(self.db_path))

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor | None]:
        if self._conn is None:
            yield None
            return
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        finally:
            cur.close()

    # ===== WRITE: remember =====

    def remember(
        self,
        matter_id: str | None,
        event_type: str,
        payload: dict[str, Any] | None,
        area: str | None = None,
        agent: str | None = None,
    ) -> str:
        """Captura un evento del despacho como celda de memoria.

        Args:
            matter_id: referencia al matter (NO filtra recall — cross-matter).
            event_type: categoría (matter_pattern, deadline_pattern,
                citation_pattern, red_flag_pattern, u otros custom).
            payload: dict con la info del evento (e.g. {"sequence": "..."}).
            area: área de práctica del matter (e.g. "laboral", "civil").
            agent: agente que capturó la memoria (e.g. "intake-agent").

        Returns:
            cell_id (str, 24 chars hex).
        """
        cell_id = uuid.uuid4().hex[:24]
        payload_json = json.dumps(payload or {}, ensure_ascii=False)
        now = _utcnow_iso()
        with self._cursor() as cur:
            if cur is None:
                raise RuntimeError("MemoryCell is closed")
            cur.execute(
                "INSERT INTO memory_cells "
                "(id, matter_id, area, event_type, payload_json, agent, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (cell_id, matter_id, area, event_type, payload_json, agent, now),
            )
        self.log.info(
            "memory_cell.remember",
            cell_id=cell_id,
            event_type=event_type,
            area=area,
            agent=agent,
        )
        return cell_id

    # ===== RETRIEVE: recall (TF-IDF + cosine, cross-matter) =====

    def recall(
        self,
        query: str,
        k: int = 5,
        area: str | None = None,
    ) -> list[dict[str, Any]]:
        """Top-k celdas de memoria relevantes para una query (TF-IDF + cosine).

        Args:
            query: texto de la consulta (e.g. "plazo prescripción 5 años").
            k: máximo de resultados a devolver.
            area: si se especifica, filtra solo celdas de ese área.

        Returns:
            list[dict] con claves: cell_id, matter_id, area, event_type,
            payload, agent, created_at, score. Ordenado por score DESC.
            Solo incluye celdas con score > 0.

        NOTA: El recall NO filtra por matter_id (cross-matter patterns).
        El área sí filtra cuando se especifica explícitamente.
        """
        if not query or not query.strip():
            return []
        if self._conn is None:
            return []
        cur = self._conn.cursor()
        try:
            if area is not None:
                cur.execute(
                    "SELECT id, matter_id, area, event_type, payload_json, "
                    "agent, created_at FROM memory_cells WHERE area = ?",
                    (area,),
                )
            else:
                cur.execute(
                    "SELECT id, matter_id, area, event_type, payload_json, "
                    "agent, created_at FROM memory_cells"
                )
            rows = cur.fetchall()
        finally:
            cur.close()
        if not rows:
            return []
        # Tokenize query + todos los documentos
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []
        docs_tokens: list[list[str]] = []
        df: Counter[str] = Counter()
        for r in rows:
            # Texto tokenizable: event_type + area + payload values
            searchable_parts = [
                str(r[3] or ""),  # event_type
                str(r[2] or ""),  # area
                _flatten_payload_text(json.loads(r[4]) if r[4] else {}),
            ]
            searchable = " ".join(p for p in searchable_parts if p)
            tokens = _tokenize(searchable)
            docs_tokens.append(tokens)
            for t in set(tokens):
                df[t] += 1
        # Smoothed idf (sklearn-style: log((1+n)/(1+df)) + 1). Siempre
        # positivo incluso en colecciones pequeñas (n=1, df=1 → idf=1.0).
        # Difiere del idf=log(n/(1+df)) de rag_local V2.2-B porque MemoryCell
        # opera sobre colecciones típicamente pequeñas (1-50 celdes por área).
        n_docs = len(rows)
        idf: dict[str, float] = {
            t: math.log((1 + n_docs) / (1 + df_t)) + 1.0
            for t, df_t in df.items()
        }
        # Query vector: TF * IDF (solo tokens en el vocabulario indexado)
        query_tf = Counter(query_tokens)
        query_vec: dict[str, float] = {
            t: query_tf[t] * idf[t]
            for t in query_tokens
            if t in idf
        }
        norm_q = math.sqrt(sum(v * v for v in query_vec.values()))
        if norm_q == 0.0:
            return []
        # Score por cosine similarity contra cada doc
        scores: list[tuple[int, float]] = []
        for idx, tokens in enumerate(docs_tokens):
            doc_tf = Counter(tokens)
            dot = 0.0
            norm_d_sq = 0.0
            for t, tfreq in doc_tf.items():
                weight = tfreq * idf.get(t, 0.0)
                if weight == 0.0:
                    continue
                norm_d_sq += weight * weight
                qv = query_vec.get(t, 0.0)
                if qv != 0.0:
                    dot += qv * weight
            norm_d = math.sqrt(norm_d_sq) if norm_d_sq > 0 else 0.0
            score = dot / (norm_q * norm_d) if norm_d > 0 else 0.0
            scores.append((idx, score))
        # Sort desc por score, solo > 0
        scores.sort(key=lambda x: -x[1])
        results: list[dict[str, Any]] = []
        for idx, score in scores:
            if score <= 0.0:
                continue
            r = rows[idx]
            results.append({
                "cell_id": r[0],
                "matter_id": r[1],
                "area": r[2],
                "event_type": r[3],
                "payload": json.loads(r[4]) if r[4] else {},
                "agent": r[5],
                "created_at": r[6],
                "score": score,
            })
            if len(results) >= k:
                break
        self.log.info(
            "memory_cell.recall",
            query=query[:80],
            k=k,
            area=area,
            returned=len(results),
        )
        return results

    # ===== PATTERNS: aggregated stats =====

    def get_patterns(self, area: str | None = None) -> dict[str, Any]:
        """Estadísticas agregadas: event_types, top_areas, total_memories.

        Args:
            area: si se especifica, solo celdas de esa área.

        Returns:
            {
                "event_types": {type: count, ...}  # dict ordenado por count desc
                "top_areas": [{"area": str, "count": int}, ...]
                "total_memories": int
            }
        """
        if self._conn is None:
            return {"event_types": {}, "top_areas": [], "total_memories": 0}
        cur = self._conn.cursor()
        try:
            if area is not None:
                cur.execute(
                    "SELECT event_type, COUNT(*) FROM memory_cells "
                    "WHERE area = ? GROUP BY event_type "
                    "ORDER BY COUNT(*) DESC",
                    (area,),
                )
                event_rows = cur.fetchall()
                cur.execute(
                    "SELECT COUNT(*) FROM memory_cells WHERE area = ?",
                    (area,),
                )
                total = cur.fetchone()[0]
                cur.execute(
                    "SELECT area, COUNT(*) FROM memory_cells "
                    "WHERE area = ? GROUP BY area ORDER BY COUNT(*) DESC",
                    (area,),
                )
                area_rows = cur.fetchall()
            else:
                cur.execute(
                    "SELECT event_type, COUNT(*) FROM memory_cells "
                    "GROUP BY event_type ORDER BY COUNT(*) DESC"
                )
                event_rows = cur.fetchall()
                cur.execute("SELECT COUNT(*) FROM memory_cells")
                total = cur.fetchone()[0]
                cur.execute(
                    "SELECT area, COUNT(*) FROM memory_cells "
                    "WHERE area IS NOT NULL GROUP BY area "
                    "ORDER BY COUNT(*) DESC"
                )
                area_rows = cur.fetchall()
        finally:
            cur.close()
        return {
            "event_types": {et: cnt for et, cnt in event_rows},
            "top_areas": [
                {"area": a, "count": c} for a, c in area_rows if a is not None
            ],
            "total_memories": total,
        }

    # ===== STATS =====

    def stats(self) -> dict[str, Any]:
        """Snapshot de la capa de memoria: total_cells, by_event_type,
        by_area, db_path.
        """
        if self._conn is None:
            return {
                "total_cells": 0,
                "by_event_type": {},
                "by_area": {},
                "db_path": str(self.db_path),
            }
        cur = self._conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM memory_cells")
            total = cur.fetchone()[0]
            cur.execute(
                "SELECT event_type, COUNT(*) FROM memory_cells "
                "GROUP BY event_type"
            )
            by_event = {et: cnt for et, cnt in cur.fetchall()}
            cur.execute(
                "SELECT area, COUNT(*) FROM memory_cells "
                "WHERE area IS NOT NULL GROUP BY area"
            )
            by_area = {a: cnt for a, cnt in cur.fetchall()}
        finally:
            cur.close()
        return {
            "total_cells": total,
            "by_event_type": by_event,
            "by_area": by_area,
            "db_path": str(self.db_path),
        }

    # ===== GDPR-style deletion right =====

    def forget(self, cell_id: str) -> bool:
        """Elimina una celda de memoria (GDPR-style deletion right).

        Args:
            cell_id: id de la celda a eliminar.

        Returns:
            True si se eliminó, False si la celda no existía.
        """
        if self._conn is None:
            return False
        cur = self._conn.cursor()
        try:
            cur.execute(
                "DELETE FROM memory_cells WHERE id = ?", (cell_id,)
            )
            self._conn.commit()
            deleted = cur.rowcount > 0
        finally:
            cur.close()
        if deleted:
            self.log.info("memory_cell.forget", cell_id=cell_id)
        return deleted

    # ===== Lifecycle =====

    def close(self) -> None:
        """Cierra la conexión SQLite. Operaciones posteriores requieren
        reinstanciar la clase con el mismo db_path (los datos persisten).
        """
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        self.log.info("memory_cell.closed", path=str(self.db_path))
