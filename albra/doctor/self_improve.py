"""
SELF-IMPROVE ALBRA - aprendizaje operacional mediante lessons.

Inspirado en AGENTE-TRADING/src/agent/self_improve.ts.

6 fases:
1. CAPTURA → errores automáticos de tools + correcciones del usuario
2. DEDUPE → pattern_key por tipo de fallo; contar ocurrencias
3. REFLEXIÓN → destilar la lección en 2-4 frases accionables
4. REUSO → recuperar lecciones relevantes antes de una decisión
5. PROMOCIÓN → lecciones verificadas e importantes viajan en system prompt
6. TRIAGE → errores recurrentes (≥3) → lecciones automáticamente

CRÍTICO:
- LEARNING ≠ modificación de código
- SELF-IMPROVE respeta las fronteras del Constructor
- El agente puede aprender operacionalmente mediante memoria/configuración
- NO debe hacer commits ni alterar la fuente de verdad
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from albra.observability.logger import get_logger


@dataclass
class Lesson:
    id: str
    pattern_key: str
    error_type: str
    lesson_text: str
    confidence: float = 0.5
    occurrences: int = 1
    validated: bool = False
    promoted: bool = False
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AutoError:
    id: str
    tool_name: str
    error_type: str
    pattern_key: str
    message: str
    ts: float = field(default_factory=time.time)
    resolved: bool = False
    resolved_at: float | None = None
    lesson_id: str | None = None


class SelfImprove:
    """Motor de auto-mejora - captura, dedupe, reflexión, reuso, promoción, triage."""

    PROMOTION_THRESHOLD = 3  # ≥3 ocurrencias → candidate a lesson

    def __init__(self, db_path: str = "./data/self_improve.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log = get_logger("albra.self_improve")
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS auto_errors (
                id TEXT PRIMARY KEY,
                tool_name TEXT NOT NULL,
                error_type TEXT NOT NULL,
                pattern_key TEXT NOT NULL,
                message TEXT NOT NULL,
                ts REAL NOT NULL,
                resolved INTEGER DEFAULT 0,
                resolved_at REAL,
                lesson_id TEXT
            );
            CREATE TABLE IF NOT EXISTS lessons (
                id TEXT PRIMARY KEY,
                pattern_key TEXT NOT NULL,
                error_type TEXT NOT NULL,
                lesson_text TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                occurrences INTEGER DEFAULT 1,
                validated INTEGER DEFAULT 0,
                promoted INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                last_seen REAL NOT NULL,
                metadata_json TEXT DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_err_pattern ON auto_errors(pattern_key, resolved);
            CREATE INDEX IF NOT EXISTS idx_lesson_pattern ON lessons(pattern_key);
            CREATE INDEX IF NOT EXISTS idx_lesson_promoted ON lessons(promoted);
            """
        )
        self._conn.commit()

    # --- FASE 1: CAPTURA ---

    def capture_error(self, *, tool_name: str, error: Exception | str) -> str:
        msg = str(error) if isinstance(error, Exception) else error
        error_type = type(error).__name__ if isinstance(error, Exception) else "StringError"
        pattern_key = self._classify(tool_name, msg)

        eid = uuid.uuid4().hex[:16]
        self._conn.execute(
            "INSERT INTO auto_errors (id, tool_name, error_type, pattern_key, message, ts, resolved) "
            "VALUES (?, ?, ?, ?, ?, ?, 0)",
            (eid, tool_name, error_type, pattern_key, msg, time.time()),
        )
        self._conn.commit()
        self.log.info("self_improve.capture", tool=tool_name, pattern=pattern_key, error_type=error_type)

        # FASE 6: TRIAGE - si patrón recurrente → promover a lesson automáticamente
        self._maybe_promote_to_lesson(pattern_key, tool_name, error_type)
        return eid

    def _classify(self, tool_name: str, msg: str) -> str:
        """Clasifica un error en un pattern_key."""
        m = msg.lower()
        if "timeout" in m or "timed out" in m:
            return f"{tool_name}:timeout"
        if "auth" in m or "unauthorized" in m or "forbidden" in m:
            return f"{tool_name}:auth"
        if "network" in m or "connection" in m or "dns" in m:
            return f"{tool_name}:network"
        if "rate" in m and "limit" in m:
            return f"{tool_name}:rate_limit"
        if "not found" in m or "404" in m:
            return f"{tool_name}:not_found"
        if "validation" in m or "invalid" in m:
            return f"{tool_name}:validation"
        return f"{tool_name}:unknown"

    def _maybe_promote_to_lesson(self, pattern_key: str, tool_name: str, error_type: str) -> None:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM auto_errors WHERE pattern_key = ? AND resolved = 0",
            (pattern_key,),
        )
        count = cur.fetchone()[0]
        if count >= self.PROMOTION_THRESHOLD:
            # Verificar si ya existe lesson para este pattern
            cur = self._conn.execute(
                "SELECT id, occurrences FROM lessons WHERE pattern_key = ?",
                (pattern_key,),
            )
            existing = cur.fetchone()
            if existing:
                # Update occurrences
                self._conn.execute(
                    "UPDATE lessons SET occurrences = ?, last_seen = ? WHERE id = ?",
                    (existing[1] + 1, time.time(), existing[0]),
                )
            else:
                lesson_id = uuid.uuid4().hex[:16]
                lesson_text = self._draft_lesson(tool_name, pattern_key, error_type)
                self._conn.execute(
                    "INSERT INTO lessons (id, pattern_key, error_type, lesson_text, confidence, "
                    "occurrences, validated, promoted, created_at, last_seen, metadata_json) "
                    "VALUES (?, ?, ?, ?, 0.3, ?, 0, 0, ?, ?, '{}')",
                    (
                        lesson_id, pattern_key, error_type, lesson_text,
                        count, time.time(), time.time(),
                    ),
                )
                self.log.info("self_improve.lesson_drafted", pattern=pattern_key, lesson_id=lesson_id)
            # Marcar errores como resueltos
            self._conn.execute(
                "UPDATE auto_errors SET resolved = 1, resolved_at = ?, lesson_id = "
                "(SELECT id FROM lessons WHERE pattern_key = ? LIMIT 1) "
                "WHERE pattern_key = ? AND resolved = 0",
                (time.time(), pattern_key, pattern_key),
            )
            self._conn.commit()

    def _draft_lesson(self, tool_name: str, pattern_key: str, error_type: str) -> str:
        """Borrador automático de lesson. Producción: usar LLM."""
        kind = pattern_key.split(":")[-1] if ":" in pattern_key else "unknown"
        return (
            f"Patrón recurrente detectado en '{tool_name}' ({error_type}, tipo '{kind}'). "
            f"Antes de invocar '{tool_name}', validar precondiciones para evitar {kind}. "
            f"Considerar retry con backoff si {kind} es transitorio."
        )

    # --- FASE 4: REUSO ---

    def get_lessons_for_context(self, *, tool_name: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        """Recupera lecciones relevantes para una decisión futura."""
        if tool_name:
            cur = self._conn.execute(
                "SELECT * FROM lessons WHERE pattern_key LIKE ? AND validated = 1 "
                "ORDER BY last_seen DESC LIMIT ?",
                (f"{tool_name}:%", limit),
            )
        else:
            cur = self._conn.execute(
                "SELECT * FROM lessons WHERE validated = 1 ORDER BY last_seen DESC LIMIT ?",
                (limit,),
            )
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r, strict=False)) for r in rows]

    def get_promoted_lessons(self) -> list[dict[str, Any]]:
        """Lecciones promovidas para incluir en system prompt."""
        cur = self._conn.execute(
            "SELECT * FROM lessons WHERE promoted = 1 ORDER BY last_seen DESC LIMIT 10"
        )
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r, strict=False)) for r in rows]

    # --- FASE 5: PROMOCIÓN (con safety P1) ---

    def validate_lesson(self, lesson_id: str, *, validator: str = "system") -> bool:
        """Marca una lesson como validada por humano (no auto-promueve).

        P1 SAFETY: SelfImprove NO puede auto-elevar autonomía, NO puede
        modificar policy, NO puede modificar código. Solo marca lessons
        como validadas. La promoción final SIEMPRE requiere HITL explícito.
        """
        self._conn.execute(
            "UPDATE lessons SET validated = 1 WHERE id = ?",
            (lesson_id,),
        )
        self._conn.commit()
        self.log.info("self_improve.validated", lesson_id=lesson_id, validator=validator)
        return True

    def promote_lesson(self, lesson_id: str, *, hitl_request_id: str | None = None) -> dict[str, Any]:
        """P1 SAFETY: promotion SIEMPRE requiere HITL explícito.

        Sin hitl_request_id aprobado → rechazo.
        SelfImprove NUNCA puede:
        - modificar autonomía ceiling
        - modificar policy state
        - modificar código
        - auto-promover a L5
        """
        cur = self._conn.execute("SELECT validated FROM lessons WHERE id = ?", (lesson_id,))
        row = cur.fetchone()
        if not row:
            return {"ok": False, "reason": "lesson_not_found"}
        if not row[0]:
            return {"ok": False, "reason": "not_validated"}
        if not hitl_request_id:
            return {"ok": False, "reason": "hitl_required", "permanent": False}

        self._conn.execute("UPDATE lessons SET promoted = 1 WHERE id = ?", (lesson_id,))
        self._conn.commit()
        self.log.info("self_improve.promoted", lesson_id=lesson_id, hitl=hitl_request_id)
        return {"ok": True, "lesson_id": lesson_id, "hitl_request_id": hitl_request_id}

    def forbidden_actions(self) -> list[str]:
        """Lista acciones que SelfImprove NUNCA puede hacer (P1 safety)."""
        return [
            "modify_code",
            "modify_autonomy_ceiling",
            "modify_policy_state",
            "modify_kill_switch",
            "elevate_role",
            "bypass_execution_guard",
            "self_promote_to_L5",
            "delete_audit_log",
            "modify_rbac",
        ]

    def get_unresolved_errors(self, *, limit: int = 20) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT * FROM auto_errors WHERE resolved = 0 ORDER BY ts DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r, strict=False)) for r in rows]

    def stats(self) -> dict[str, Any]:
        cur = self._conn.execute("SELECT COUNT(*) FROM auto_errors")
        total_errors = cur.fetchone()[0]
        cur = self._conn.execute("SELECT COUNT(*) FROM auto_errors WHERE resolved = 0")
        unresolved = cur.fetchone()[0]
        cur = self._conn.execute("SELECT COUNT(*) FROM lessons")
        total_lessons = cur.fetchone()[0]
        cur = self._conn.execute("SELECT COUNT(*) FROM lessons WHERE validated = 1")
        validated = cur.fetchone()[0]
        cur = self._conn.execute("SELECT COUNT(*) FROM lessons WHERE promoted = 1")
        promoted = cur.fetchone()[0]
        return {
            "total_errors": total_errors,
            "unresolved_errors": unresolved,
            "total_lessons": total_lessons,
            "validated_lessons": validated,
            "promoted_lessons": promoted,
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
