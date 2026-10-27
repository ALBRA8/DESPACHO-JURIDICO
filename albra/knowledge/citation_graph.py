"""
CITATION GRAPH — base de datos en grafo de citas jurídicas colombianas.

Extiende AgenticCitator (V2.1) con graph DB SQLite.
Nodes: Articles (Constitución + Leyes + Sentencias).
Edges: cites, followed, distinguished, doubted, overruled, per_incuriam,
       affirmed, reversed, cited (default neutro).

Inspiración clean-room: Moonlit Legal Research MCP (citation graph que vincula
provisiones con jurisprudencia), Gotham (agentic citator with treatment labels).
Implementación V2.3-C sobre SQLite (sin Neo4j ni DGraph para mantener dependencias
ligeros y on-prem).

Schema:
    nodes
      id TEXT PRIMARY KEY (e.g. "const_1991_art_1")
      document_type TEXT (constitucion | legislacion | jurisprudencia)
      document_name TEXT (e.g. "Constitución Política de 1991")
      article_number TEXT (e.g. "1")
      source_url TEXT
      content_hash TEXT
      created_at TEXT

    edges
      id TEXT PRIMARY KEY
      source_node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE
      target_node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE
      treatment TEXT NOT NULL (followed, distinguished, doubted, overruled,
                                per_incuriam, affirmed, reversed, cited)
      citing_text TEXT  -- snippet del texto que cita (evidence)
      confidence REAL   -- 0.0-1.0
      analyzed_at TEXT   -- ISO 8601
      analyzed_by TEXT   -- agent name (e.g. "agentic-citator")

Uso:
    graph = CitationGraph()  # SQLite en data/citation_graph.db
    graph.index_corpus_v11()  # bootstrap con corpus V1.1
    graph.analyze_citation(citing_text, target_node_id)  # crea edge
    graph.get_citation_network(node_id)  # todos los edges in/out
    graph.get_treatment_stats(node_id)  # {followed: 5, distinguished: 2, ...}
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from albra.observability.logger import get_logger


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CitationGraph:
    """Citation graph DB en SQLite para jurisprudencia colombiana.

    V2.3-C: extiende AgenticCitator (V2.1) con persistencia + traversal.
    """

    GENESIS_HASH = "0" * 64  # placeholder for future hash chain on edges

    def __init__(self, db_path: str = "./data/citation_graph.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log = get_logger("albra.knowledge.citation_graph")
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                document_type TEXT NOT NULL,
                document_name TEXT NOT NULL,
                article_number TEXT,
                source_url TEXT,
                content_hash TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS edges (
                id TEXT PRIMARY KEY,
                source_node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                target_node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                treatment TEXT NOT NULL,
                citing_text TEXT,
                confidence REAL NOT NULL DEFAULT 0.0,
                analyzed_at TEXT NOT NULL,
                analyzed_by TEXT NOT NULL DEFAULT 'agentic-citator'
            );

            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_node_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_node_id);
            CREATE INDEX IF NOT EXISTS idx_edges_treatment ON edges(treatment);
            CREATE INDEX IF NOT EXISTS idx_nodes_doc_type ON nodes(document_type);
            CREATE INDEX IF NOT EXISTS idx_nodes_doc_name ON nodes(document_name);
            """
        )
        self._conn.commit()

    # ===== Bootstrap =====

    def index_corpus_v11(self) -> int:
        """Bootstrap con corpus V1.1: Constitución 1991 + Ley 100/1993 + Ley 80/1993.
        Returns: número de nodes indexados.
        """
        from albra.knowledge.colombia.corpus_pilot.real_corpus_v11 import ALL_DOCUMENTS

        count = 0
        for _doc_type, doc in ALL_DOCUMENTS:
            for article in doc["articles"]:
                node_id = self._make_node_id(
                    doc["document_type"], doc["number"], article["number"]
                )
                if self.get_node(node_id) is None:
                    self._conn.execute(
                        """
                        INSERT INTO nodes
                        (id, document_type, document_name, article_number, source_url,
                         content_hash, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            node_id,
                            doc["document_type"],
                            doc["number"],
                            article["number"],
                            doc["source_url"],
                            doc["content_hash"],
                            _utcnow_iso(),
                        ),
                    )
                    count += 1
        self._conn.commit()
        self.log.info("citation_graph.bootstrap", nodes_indexed=count)
        return count

    def _make_node_id(
        self, document_type: str, document_name: str, article_number: str | None
    ) -> str:
        """ID canónico: <doc_type>_<doc_name_slug>_<article_number>."""
        slug = document_name.lower().replace(" ", "_").replace("á", "a").replace(
            "é", "e"
        ).replace("í", "i").replace("ó", "o").replace("ú", "u").replace("ñ", "n")
        if article_number:
            return f"{document_type}_{slug}_art_{article_number}"
        return f"{document_type}_{slug}"

    # ===== Nodes CRUD =====

    def add_node(
        self,
        *,
        node_id: str,
        document_type: str,
        document_name: str,
        article_number: str | None = None,
        source_url: str = "",
        content_hash: str = "",
    ) -> str:
        """Añade un node si no existe. Idempotente."""
        existing = self.get_node(node_id)
        if existing:
            return node_id
        self._conn.execute(
            """
            INSERT INTO nodes
            (id, document_type, document_name, article_number, source_url,
             content_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node_id,
                document_type,
                document_name,
                article_number,
                source_url,
                content_hash,
                _utcnow_iso(),
            ),
        )
        self._conn.commit()
        return node_id

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        cur = self._conn.execute(
            "SELECT id, document_type, document_name, article_number, source_url, "
            "content_hash, created_at FROM nodes WHERE id = ?",
            (node_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "document_type": row[1],
            "document_name": row[2],
            "article_number": row[3],
            "source_url": row[4],
            "content_hash": row[5],
            "created_at": row[6],
        }

    def list_nodes(
        self, *, document_type: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        q = "SELECT id FROM nodes"
        args: list[Any] = []
        if document_type:
            q += " WHERE document_type = ?"
            args.append(document_type)
        q += " LIMIT ?"
        args.append(limit)
        cur = self._conn.execute(q, args)
        return [n for (nid,) in cur.fetchall() if (n := self.get_node(nid)) is not None]

    # ===== Edges (citations with treatment) =====

    def add_edge(
        self,
        *,
        source_node_id: str,
        target_node_id: str,
        treatment: str,
        citing_text: str = "",
        confidence: float = 0.0,
        analyzed_by: str = "agentic-citator",
    ) -> str:
        """Añade un edge (citation with treatment).
        source_node_id: el documento que cita (citing decision).
        target_node_id: el documento citado.
        treatment: followed | distinguished | doubted | overruled |
                   per_incuriam | affirmed | reversed | cited.
        """
        if treatment not in (
            "followed", "distinguished", "doubted", "overruled",
            "per_incuriam", "affirmed", "reversed", "cited",
        ):
            raise ValueError(f"Treatment inválido: {treatment!r}")

        # Verificar que ambos nodes existen
        if self.get_node(source_node_id) is None:
            raise KeyError(f"Source node not found: {source_node_id}")
        if self.get_node(target_node_id) is None:
            raise KeyError(f"Target node not found: {target_node_id}")

        import uuid
        edge_id = uuid.uuid4().hex
        self._conn.execute(
            """
            INSERT INTO edges
            (id, source_node_id, target_node_id, treatment, citing_text,
             confidence, analyzed_at, analyzed_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                edge_id,
                source_node_id,
                target_node_id,
                treatment,
                citing_text,
                confidence,
                _utcnow_iso(),
                analyzed_by,
            ),
        )
        self._conn.commit()
        self.log.info(
            "citation_graph.edge_added",
            source=source_node_id, target=target_node_id,
            treatment=treatment, confidence=confidence,
        )
        return edge_id

    def get_citation_network(self, node_id: str) -> dict[str, Any]:
        """Devuelve la red de citas de un node:
        - cites_out: edges donde este node es el source (este node cita a otros)
        - cited_by_in: edges donde este node es el target (otros citan a este)
        """
        if self.get_node(node_id) is None:
            return {"node_id": node_id, "cites_out": [], "cited_by_in": []}

        # Out edges: este node cita a otros
        cur_out = self._conn.execute(
            "SELECT id, target_node_id, treatment, citing_text, confidence, "
            "analyzed_at, analyzed_by FROM edges WHERE source_node_id = ? "
            "ORDER BY analyzed_at DESC",
            (node_id,),
        )
        cites_out = [
            {
                "edge_id": r[0], "target_node_id": r[1], "treatment": r[2],
                "citing_text": r[3], "confidence": r[4],
                "analyzed_at": r[5], "analyzed_by": r[6],
                "target_node": self.get_node(r[1]),
            }
            for r in cur_out.fetchall()
        ]

        # In edges: otros citan a este node
        cur_in = self._conn.execute(
            "SELECT id, source_node_id, treatment, citing_text, confidence, "
            "analyzed_at, analyzed_by FROM edges WHERE target_node_id = ? "
            "ORDER BY analyzed_at DESC",
            (node_id,),
        )
        cited_by_in = [
            {
                "edge_id": r[0], "source_node_id": r[1], "treatment": r[2],
                "citing_text": r[3], "confidence": r[4],
                "analyzed_at": r[5], "analyzed_by": r[6],
                "source_node": self.get_node(r[1]),
            }
            for r in cur_in.fetchall()
        ]

        return {
            "node_id": node_id,
            "node": self.get_node(node_id),
            "cites_out": cites_out,
            "cited_by_in": cited_by_in,
        }

    def get_treatment_stats(self, node_id: str) -> dict[str, Any]:
        """Stats de treatment labels para un node (cuántas veces followed,
        distinguished, doubted, etc.)."""
        cur = self._conn.execute(
            "SELECT treatment, COUNT(*) FROM edges WHERE target_node_id = ? "
            "GROUP BY treatment",
            (node_id,),
        )
        stats = {r[0]: r[1] for r in cur.fetchall()}
        # Asegurar todas las treatments presentes
        for t in ("followed", "distinguished", "doubted", "overruled",
                  "per_incuriam", "affirmed", "reversed", "cited"):
            stats.setdefault(t, 0)
        total = sum(stats.values())
        stats["total_citations"] = total
        return stats

    def get_authoritative_nodes(self, min_citations: int = 5) -> list[dict[str, Any]]:
        """Nodes más citados (con ≥ min_citations incoming). Ordena desc."""
        cur = self._conn.execute(
            "SELECT target_node_id, COUNT(*) as c FROM edges "
            "GROUP BY target_node_id HAVING c >= ? ORDER BY c DESC LIMIT 50",
            (min_citations,),
        )
        result = []
        for node_id, count in cur.fetchall():
            node = self.get_node(node_id)
            if node:
                stats = self.get_treatment_stats(node_id)
                result.append({
                    "node": node,
                    "total_citations": count,
                    "treatment_breakdown": stats,
                })
        return result

    def stats(self) -> dict[str, Any]:
        cur_n = self._conn.execute("SELECT COUNT(*) FROM nodes")
        total_nodes = cur_n.fetchone()[0]
        cur_e = self._conn.execute("SELECT COUNT(*) FROM edges")
        total_edges = cur_e.fetchone()[0]
        cur_t = self._conn.execute(
            "SELECT treatment, COUNT(*) FROM edges GROUP BY treatment"
        )
        by_treatment = {r[0]: r[1] for r in cur_t.fetchall()}
        return {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "by_treatment": by_treatment,
            "db_path": str(self.db_path),
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
