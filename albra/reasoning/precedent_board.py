"""
PRECEDENT BOARD — memoria longitudinal cross-engagement sin fine-tuning.

Inspiración clean-room: Lavern pattern (Precedent Board con promoción
tentative→confirmed). ALBRA V2.4-C: board local SQLite, sin fine-tuning
de LLM.

Concepto:
- Los abogados registran un "precedent" cuando identifican un patrón
  recurrente en múltiples matters (p. ej. "Corte Constitucional tiende
  a tutelar medicamentos para enfermedades huérfanas").
- El precedent arranca como TENTATIVE (1 observación).
- Con suficientes observaciones (≥3) Y sin contradicciones, se PROMUEVE
  a CONFIRMED.
- Si una nueva observación contradice, el precedent baja a DOUBTED.
- Si se recibe una contradicción fuerte (sentencia posterior), se marca
  OVERRULED.

Estados de un precedent:
- TENTATIVE: 1-2 observaciones (sin validez estadística).
- CONFIRMED: ≥3 observaciones consistentes (válido como heurística).
- DOUBTED: contradicción detectada, requiere revisión.
- OVERRULED: contradicción fuerte (sentencia posterior).
- ARCHIVED: el precedent ya no aplica (cambio de ley, etc.).

Uso:
- REVIEW-AGENT consulta el board al evaluar un draft.
- DRAFTING-AGENT consulta para "what tends to work" por área de práctica.
- Approval chain puede exigir ≥1 precedent CONFIRMED antes de firmar
  acciones sensibles (V2.5+ enhancement).
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from albra.observability.logger import get_logger


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Estados de un precedent
TENTATIVE = "TENTATIVE"
CONFIRMED = "CONFIRMED"
DOUBTED = "DOUBTED"
OVERRULED = "OVERRULED"
ARCHIVED = "ARCHIVED"

ALL_STATES: frozenset[str] = frozenset({
    TENTATIVE, CONFIRMED, DOUBTED, OVERRULED, ARCHIVED,
})

# Threshold para promoción TENTATIVE → CONFIRMED
PROMOTION_THRESHOLD = 3  # 3 observaciones consistentes


@dataclass
class Precedent:
    """Un precedent del board."""
    id: str
    area: str  # civil, laboral, constitucional, etc.
    title: str  # descripción corta del patrón
    description: str = ""  # detalle del patrón observado
    state: str = TENTATIVE
    observations: list[dict[str, str]] = field(default_factory=list)
    # Cada observation: {matter_id, observation_text, observed_by, observed_at, supporting: bool}
    created_at: str = ""
    last_updated: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "area": self.area,
            "title": self.title,
            "description": self.description,
            "state": self.state,
            "observations_count": len(self.observations),
            "observations": self.observations,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
        }


class PrecedentBoard:
    """Board de precedents con promoción tentative→confirmed.

    SQLite local en data/precedent_board.db.
    Cross-matter (precedents se asocian al área, no al matter).
    """

    def __init__(self, db_path: str = "./data/precedent_board.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log = get_logger("albra.reasoning.precedent_board")
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS precedents (
                id TEXT PRIMARY KEY,
                area TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                state TEXT NOT NULL DEFAULT 'TENTATIVE',
                created_at TEXT NOT NULL,
                last_updated TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS observations (
                id TEXT PRIMARY KEY,
                precedent_id TEXT NOT NULL REFERENCES precedents(id) ON DELETE CASCADE,
                matter_id TEXT,
                observation_text TEXT NOT NULL,
                observed_by TEXT NOT NULL DEFAULT 'unknown',
                observed_at TEXT NOT NULL,
                supporting BOOLEAN NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_precedents_area ON precedents(area);
            CREATE INDEX IF NOT EXISTS idx_precedents_state ON precedents(state);
            CREATE INDEX IF NOT EXISTS idx_observations_precedent ON observations(precedent_id);
            CREATE INDEX IF NOT EXISTS idx_observations_matter ON observations(matter_id);
            """
        )
        self._conn.commit()

    # ===== CRUD precedents =====

    def create_precedent(
        self,
        *,
        area: str,
        title: str,
        description: str = "",
    ) -> str:
        """Crea un precedent nuevo (state=TENTATIVE, 0 observations)."""
        precedent_id = uuid.uuid4().hex
        now = _utcnow_iso()
        self._conn.execute(
            """
            INSERT INTO precedents (id, area, title, description, state, created_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (precedent_id, area, title, description, TENTATIVE, now, now),
        )
        self._conn.commit()
        self.log.info(
            "precedent.created", precedent_id=precedent_id, area=area, title=title
        )
        return precedent_id

    def get_precedent(self, precedent_id: str) -> Precedent | None:
        cur = self._conn.execute(
            "SELECT id, area, title, description, state, created_at, last_updated "
            "FROM precedents WHERE id = ?",
            (precedent_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        # Load observations
        obs_cur = self._conn.execute(
            "SELECT id, matter_id, observation_text, observed_by, observed_at, supporting "
            "FROM observations WHERE precedent_id = ? ORDER BY observed_at ASC",
            (precedent_id,),
        )
        observations = [
            {
                "id": r[0], "matter_id": r[1], "observation_text": r[2],
                "observed_by": r[3], "observed_at": r[4],
                "supporting": bool(r[5]),
            }
            for r in obs_cur.fetchall()
        ]
        return Precedent(
            id=row[0], area=row[1], title=row[2], description=row[3],
            state=row[4], created_at=row[5], last_updated=row[6],
            observations=observations,
        )

    def list_precedents(
        self,
        *,
        area: str | None = None,
        state: str | None = None,
        limit: int = 100,
    ) -> list[Precedent]:
        q = "SELECT id FROM precedents WHERE 1=1"
        args: list[Any] = []
        if area:
            q += " AND area = ?"
            args.append(area)
        if state:
            q += " AND state = ?"
            args.append(state)
        q += " ORDER BY last_updated DESC LIMIT ?"
        args.append(limit)
        cur = self._conn.execute(q, args)
        return [p for (pid,) in cur.fetchall() if (p := self.get_precedent(pid)) is not None]

    # ===== Observations =====

    def add_observation(
        self,
        *,
        precedent_id: str,
        matter_id: str | None = None,
        observation_text: str,
        observed_by: str = "unknown",
        supporting: bool = True,
    ) -> str:
        """Añade una observación a un precedent. Recalcula state automáticamente."""
        if self.get_precedent(precedent_id) is None:
            raise KeyError(f"Precedent not found: {precedent_id}")
        obs_id = uuid.uuid4().hex
        now = _utcnow_iso()
        self._conn.execute(
            """
            INSERT INTO observations
            (id, precedent_id, matter_id, observation_text, observed_by, observed_at, supporting)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (obs_id, precedent_id, matter_id, observation_text, observed_by, now, supporting),
        )
        self._conn.commit()
        # Recalcular state
        self._recalculate_state(precedent_id)
        self.log.info(
            "precedent.observation_added",
            precedent_id=precedent_id, supporting=supporting,
            observed_by=observed_by,
        )
        return obs_id

    def _recalculate_state(self, precedent_id: str) -> str:
        """Recalcula el state del precedent basado en sus observaciones.

        Reglas:
        - Si ≥3 supporting Y 0 contradicting → CONFIRMED.
        - Si ≥1 contradicting → DOUBTED.
        - Si 1-2 supporting → TENTATIVE.
        - Si contradicción fuerte (matter_id conflicto, marcado por overwrite_state):
          → OVERRULED.
        - ARCHIVED solo por mark_archived() manual.
        """
        precedent = self.get_precedent(precedent_id)
        if not precedent:
            return ""
        # Si ya está OVERRULED o ARCHIVED, no recalcular (decisión manual)
        if precedent.state in (OVERRULED, ARCHIVED):
            return precedent.state

        supporting = sum(1 for o in precedent.observations if o["supporting"])
        contradicting = sum(1 for o in precedent.observations if not o["supporting"])

        if contradicting > 0:
            new_state = DOUBTED
        elif supporting >= PROMOTION_THRESHOLD:
            new_state = CONFIRMED
        else:
            new_state = TENTATIVE

        if new_state != precedent.state:
            self._conn.execute(
                "UPDATE precedents SET state = ?, last_updated = ? WHERE id = ?",
                (new_state, _utcnow_iso(), precedent_id),
            )
            self._conn.commit()
            self.log.info(
                "precedent.state_changed",
                precedent_id=precedent_id,
                from_state=precedent.state, to_state=new_state,
            )
        return new_state

    def mark_overruled(self, precedent_id: str, reason: str = "") -> bool:
        """Marca un precedent como OVERRULED (contradicción fuerte, sentencia posterior)."""
        if self.get_precedent(precedent_id) is None:
            return False
        self._conn.execute(
            "UPDATE precedents SET state = ?, last_updated = ? WHERE id = ?",
            (OVERRULED, _utcnow_iso(), precedent_id),
        )
        self._conn.commit()
        self.log.info("precedent.overruled", precedent_id=precedent_id, reason=reason)
        return True

    def mark_archived(self, precedent_id: str, reason: str = "") -> bool:
        """Marca un precedent como ARCHIVED (cambio de ley, ya no aplica)."""
        if self.get_precedent(precedent_id) is None:
            return False
        self._conn.execute(
            "UPDATE precedents SET state = ?, last_updated = ? WHERE id = ?",
            (ARCHIVED, _utcnow_iso(), precedent_id),
        )
        self._conn.commit()
        self.log.info("precedent.archived", precedent_id=precedent_id, reason=reason)
        return True

    # ===== Stats =====

    def stats(self) -> dict[str, Any]:
        cur_p = self._conn.execute("SELECT COUNT(*) FROM precedents")
        total_precedents = cur_p.fetchone()[0]
        cur_o = self._conn.execute("SELECT COUNT(*) FROM observations")
        total_observations = cur_o.fetchone()[0]
        cur_s = self._conn.execute(
            "SELECT state, COUNT(*) FROM precedents GROUP BY state"
        )
        by_state = {r[0]: r[1] for r in cur_s.fetchall()}
        for s in ALL_STATES:
            by_state.setdefault(s, 0)
        cur_a = self._conn.execute(
            "SELECT area, COUNT(*) FROM precedents GROUP BY area ORDER BY COUNT(*) DESC LIMIT 10"
        )
        by_area = {r[0]: r[1] for r in cur_a.fetchall()}
        return {
            "total_precedents": total_precedents,
            "total_observations": total_observations,
            "by_state": by_state,
            "by_area_top10": by_area,
            "promotion_threshold": PROMOTION_THRESHOLD,
            "db_path": str(self.db_path),
        }

    def get_confirmed_by_area(self, area: str) -> list[Precedent]:
        """Devuelve los precedents CONFIRMED de un área (los útiles para drafting/review)."""
        return self.list_precedents(area=area, state=CONFIRMED)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
