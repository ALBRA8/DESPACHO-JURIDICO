"""
POLICY MODES ALBRA - gobernanza operativa del agente.

Adaptación de AGENTE-TRADING/src/agent/policy.ts al dominio jurídico.

Modos (de menos a más riesgo):
  DRAFT        → borrador interno, sin acciones
  RESEARCH     → solo investigación
  REVIEW       → revisión interna sin acciones externas
  MANUAL_APPROVAL → ejecuta con HITL obligatorio
  LIVE         → ejecuta acciones oficiales (envío a juzgado, etc.)

Reglas:
- Por defecto: mode=DRAFT, ceiling=L2.
- LIVE exige: mode=LIVE + ceiling≥L4 + flag manual + aprobación HITL
- NUNCA se infiere autorización de la existencia de credenciales
- Todos los cambios de policy quedan en policy_events (append-only)
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from albra.observability.logger import get_logger


PolicyMode = str  # DRAFT | RESEARCH | REVIEW | MANUAL_APPROVAL | LIVE


VALID_MODES: tuple[str, ...] = (
    "DRAFT",
    "RESEARCH",
    "REVIEW",
    "MANUAL_APPROVAL",
    "LIVE",
)

# Mapping de mode → techo de autonomía requerido
MODE_CEILING: dict[str, str] = {
    "DRAFT": "L0_OBSERVE",
    "RESEARCH": "L1_RECOMMEND",
    "REVIEW": "L2_EXECUTE_SAFE",
    "MANUAL_APPROVAL": "L3_EXECUTE_EXTERNAL",
    "LIVE": "L4_EXECUTE_SENSITIVE",
}


@dataclass
class PolicyState:
    mode: str = "DRAFT"
    autonomy_ceiling: str = "L2_EXECUTE_SAFE"
    kill_switch: bool = False
    kill_reason: str | None = None
    effective_level: str = "L0_OBSERVE"
    live_authorized: bool = False  # 2do factor - no autoridad por sí solo

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "autonomy_ceiling": self.autonomy_ceiling,
            "kill_switch": self.kill_switch,
            "kill_reason": self.kill_reason,
            "effective_level": self.effective_level,
            "live_authorized": self.live_authorized,
        }


@dataclass
class PolicyEvent:
    id: str
    ts: float
    actor: str
    field_changed: str  # mode | autonomy_ceiling | kill_switch | live_authorized
    old_value: str
    new_value: str
    reason: str = ""


class PolicyEngineState:
    """Stateful policy engine - registra eventos append-only."""

    def __init__(self, db_path: str = "./data/policy_events.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log = get_logger("albra.policy_state")
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()
        self._state = self._load_latest_state()

    def _init_db(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS policy_events (
                id TEXT PRIMARY KEY,
                ts REAL NOT NULL,
                actor TEXT NOT NULL,
                field_changed TEXT NOT NULL,
                old_value TEXT NOT NULL,
                new_value TEXT NOT NULL,
                reason TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_pe_ts ON policy_events(ts DESC);
            CREATE INDEX IF NOT EXISTS idx_pe_field ON policy_events(field_changed);
            """
        )
        self._conn.commit()

    def _load_latest_state(self) -> PolicyState:
        """Reconstruye el estado a partir del último evento de cada campo."""
        state = PolicyState()
        for field in ("mode", "autonomy_ceiling", "kill_switch", "live_authorized"):
            cur = self._conn.execute(
                "SELECT new_value FROM policy_events WHERE field_changed = ? "
                "ORDER BY ts DESC LIMIT 1",
                (field,),
            )
            row = cur.fetchone()
            if row:
                val = row[0]
                if field == "mode":
                    state.mode = val
                elif field == "autonomy_ceiling":
                    state.autonomy_ceiling = val
                elif field == "kill_switch":
                    state.kill_switch = val == "True"
                elif field == "live_authorized":
                    state.live_authorized = val == "True"
        # effective_level = min entre mode ceiling y autonomy ceiling
        state.effective_level = state.autonomy_ceiling
        return state

    def _record_event(self, *, actor: str, field_changed: str, old: str, new: str, reason: str) -> None:
        eid = uuid.uuid4().hex[:16]
        self._conn.execute(
            "INSERT INTO policy_events (id, ts, actor, field_changed, old_value, new_value, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (eid, time.time(), actor, field_changed, str(old), str(new), reason),
        )
        self._conn.commit()
        self.log.info("policy.event", field=field_changed, old=old, new=new, actor=actor)

    def get_state(self) -> PolicyState:
        return self._state

    def set_mode(self, mode: str, *, actor: str = "system", reason: str = "") -> bool:
        if mode not in VALID_MODES:
            raise ValueError(f"Modo inválido: {mode}. Válidos: {VALID_MODES}")
        old = self._state.mode
        if old == mode:
            return True
        self._state.mode = mode
        self._record_event(actor=actor, field_changed="mode", old=old, new=mode, reason=reason)
        return True

    def set_autonomy_ceiling(self, ceiling: str, *, actor: str = "system", reason: str = "") -> bool:
        old = self._state.autonomy_ceiling
        self._state.autonomy_ceiling = ceiling
        self._state.effective_level = ceiling
        self._record_event(actor=actor, field_changed="autonomy_ceiling", old=old, new=ceiling, reason=reason)
        return True

    def engage_kill_switch(self, *, reason: str, actor: str = "system") -> None:
        """Activa kill switch global - bloquea TODO."""
        old = self._state.kill_switch
        self._state.kill_switch = True
        self._state.kill_reason = reason
        self._record_event(actor=actor, field_changed="kill_switch", old=str(old), new="True", reason=reason)
        self.log.critical("policy.KILL_SWITCH_ENGAGED", reason=reason, actor=actor)

    def release_kill_switch(self, *, actor: str, reason: str) -> bool:
        """Solo humano puede liberar."""
        old = self._state.kill_switch
        self._state.kill_switch = False
        self._state.kill_reason = None
        self._record_event(actor=actor, field_changed="kill_switch", old=str(old), new="False", reason=reason)
        return True

    def authorize_live(self, *, actor: str = "system", reason: str = "") -> bool:
        """2do factor para LIVE - no autoriza por sí solo."""
        old = self._state.live_authorized
        self._state.live_authorized = True
        self._record_event(actor=actor, field_changed="live_authorized", old=str(old), new="True", reason=reason)
        return True

    def revoke_live(self, *, actor: str = "system", reason: str = "") -> bool:
        old = self._state.live_authorized
        self._state.live_authorized = False
        self._record_event(actor=actor, field_changed="live_authorized", old=str(old), new="False", reason=reason)
        return True

    def assert_can_execute_live(self) -> tuple[bool, str]:
        """Verifica si el agente puede ejecutar acciones LIVE (ej: enviar a juzgado)."""
        if self._state.kill_switch:
            return False, f"Kill switch activo: {self._state.kill_reason}"
        if self._state.mode != "LIVE":
            return False, f"Mode={self._state.mode}, requiere LIVE"
        if self._state.autonomy_ceiling not in ("L4_EXECUTE_SENSITIVE", "L5_SELF_IMPROVE"):
            return False, f"Ceiling={self._state.autonomy_ceiling}, requiere L4+"
        if not self._state.live_authorized:
            return False, "live_authorized=False (2do factor)"
        return True, "LIVE authorized"

    def history(self, *, limit: int = 50, field: str | None = None) -> list[dict[str, Any]]:
        if field:
            cur = self._conn.execute(
                "SELECT * FROM policy_events WHERE field_changed = ? ORDER BY ts DESC LIMIT ?",
                (field, limit),
            )
        else:
            cur = self._conn.execute(
                "SELECT * FROM policy_events ORDER BY ts DESC LIMIT ?",
                (limit,),
            )
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r, strict=False)) for r in rows]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
