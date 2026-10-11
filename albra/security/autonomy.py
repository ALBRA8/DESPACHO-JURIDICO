"""
AUTONOMÍA ALBRA - escalera L0..L5 con techo configurable.

Inspirado en RADAR-SECOP2/src/lib/autonomy.ts y AGENTE-TRADING/src/agent/policy.ts.

Reglas:
- L4/L5 SIEMPRE exigen flag manual (env ALBRA_ALLOW_L4_L5=true).
- Por defecto el agente opera en L2 (síncrono interno seguro).
- L3 (acciones externas) exige externalActionsAllowed=true.
- L4 (sensitivo) y L5 (self-improve) exigen flag manual + techo.
- Toda decisión de autonomía se registra en auditoría.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

from albra.observability.logger import get_logger

# Niveles de autonomía
LEVELS: tuple[str, ...] = (
    "L0_OBSERVE",
    "L1_RECOMMEND",
    "L2_EXECUTE_SAFE",
    "L3_EXECUTE_EXTERNAL",
    "L4_EXECUTE_SENSITIVE",
    "L5_SELF_IMPROVE",
)

SENSITIVE: tuple[str, ...] = ("L4_EXECUTE_SENSITIVE", "L5_SELF_IMPROVE")


@dataclass
class AutonomyDecision:
    allowed: bool
    reason: str
    level: str
    max_level: str
    external_actions_allowed: bool
    manual_flag_required: bool = False
    ceiling_enforced: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "level": self.level,
            "max_level": self.max_level,
            "external_actions_allowed": self.external_actions_allowed,
            "manual_flag_required": self.manual_flag_required,
            "ceiling_enforced": self.ceiling_enforced,
        }


class AutonomyController:
    """Controlador de autonomía del agente."""

    def __init__(self) -> None:
        self.log = get_logger("albra.autonomy")
        self._max_level = "L2_EXECUTE_SAFE"
        self._external_allowed = False
        self._manual_flag = os.environ.get("ALBRA_ALLOW_L4_L5", "").lower() in ("1", "true", "yes")
        self._enforce = os.environ.get("ALBRA_ENFORCE_AUTONOMY", "").lower() in ("1", "true", "yes")
        # Historial de decisiones para auditoría
        self._decisions: list[dict[str, Any]] = []

    def get_config(self) -> dict[str, Any]:
        return {
            "max_level": self._max_level,
            "external_actions_allowed": self._external_allowed,
            "manual_flag_l4_l5": self._manual_flag,
            "enforce": self._enforce,
        }

    def set_max_level(self, level: str, *, reason: str = "") -> None:
        if level not in LEVELS:
            raise ValueError(f"Nivel inválido: {level}. Válidos: {LEVELS}")
        old = self._max_level
        self._max_level = level
        self.log.info("autonomy.level_changed", old=old, new=level, reason=reason)
        self._decisions.append({
            "ts": time.time(),
            "type": "level_change",
            "old": old,
            "new": level,
            "reason": reason,
        })

    def set_external_allowed(self, allowed: bool, *, reason: str = "") -> None:
        self._external_allowed = allowed
        self.log.info("autonomy.external_set", allowed=allowed, reason=reason)
        self._decisions.append({
            "ts": time.time(),
            "type": "external_change",
            "allowed": allowed,
            "reason": reason,
        })

    def normalize_level(self, raw: str | None) -> str | None:
        if not raw:
            return None
        v = raw.strip().upper()
        if v in LEVELS:
            return v
        # Acepta "L2", "l2" → "L2_EXECUTE_SAFE"
        if v.startswith("L") and v[1:].isdigit():
            idx = int(v[1:])
            if 0 <= idx < len(LEVELS):
                return LEVELS[idx]
        return None

    def assert_allowed(
        self,
        *,
        requested_level: str,
        action: str = "",
        external: bool = False,
        sensitive: bool = False,
    ) -> AutonomyDecision:
        """Verifica si una acción al nivel solicitado está permitida."""
        level = self.normalize_level(requested_level) or "L0_OBSERVE"
        max_idx = LEVELS.index(self._max_level)
        req_idx = LEVELS.index(level)

        # Ceiling enforcement
        if req_idx > max_idx:
            decision = AutonomyDecision(
                allowed=False,
                reason=f"Level {level} exceeds ceiling {self._max_level}",
                level=level,
                max_level=self._max_level,
                external_actions_allowed=self._external_allowed,
                ceiling_enforced=True,
            )
            self._record_decision(decision, action=action)
            return decision

        # L3 o external → exige external_allowed
        if external or level == "L3_EXECUTE_EXTERNAL":
            if not self._external_allowed:
                decision = AutonomyDecision(
                    allowed=False,
                    reason="External actions not allowed (set externalActionsAllowed=true)",
                    level=level,
                    max_level=self._max_level,
                    external_actions_allowed=False,
                )
                self._record_decision(decision, action=action)
                return decision

        # L4/L5 exigen flag manual
        if level in SENSITIVE:
            if not self._manual_flag:
                decision = AutonomyDecision(
                    allowed=False,
                    reason=f"Level {level} requires manual flag ALBRA_ALLOW_L4_L5=true",
                    level=level,
                    max_level=self._max_level,
                    external_actions_allowed=self._external_allowed,
                    manual_flag_required=True,
                )
                self._record_decision(decision, action=action)
                return decision

        # Allowed
        decision = AutonomyDecision(
            allowed=True,
            reason=f"Level {level} within ceiling {self._max_level}",
            level=level,
            max_level=self._max_level,
            external_actions_allowed=self._external_allowed,
        )
        self._record_decision(decision, action=action)
        return decision

    def _record_decision(self, decision: AutonomyDecision, *, action: str) -> None:
        self._decisions.append({
            "ts": time.time(),
            "level": decision.level,
            "action": action,
            "allowed": decision.allowed,
            "reason": decision.reason,
        })
        if not decision.allowed:
            self.log.warning("autonomy.denied", level=decision.level, action=action, reason=decision.reason)
        else:
            self.log.info("autonomy.allowed", level=decision.level, action=action)

    def history(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._decisions[-limit:])

    async def startup(self) -> None:
        self.log.info("autonomy.startup", config=self.get_config())

    async def shutdown(self) -> None:
        self.log.info("autonomy.shutdown")
