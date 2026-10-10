"""
Action Firewall Engine.

Gate determinístico: antes de ejecutar cualquier acción riesgosa,
pasa por aquí. El firewall:
1. Verifica que la acción tenga política
2. Verifica el rol del usuario
3. Verifica cooldown
4. Si requires_hitl → pide aprobación
5. Si kill_switch apagado → bloquea
6. Registra traza con hash encadenado

CRÍTICO para despacho jurídico: NUNCA deja pasar una acción crítica
sin aprobación humana explícita.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger
from albra.security.firewall.policy import (
    FIREWALL_POLICIES,
    FirewallPolicy,
    get_policy,
)


@dataclass
class FirewallDecision:
    allowed: bool
    action: str
    user: str
    role: str
    reason: str = ""
    hitl_request_id: str | None = None
    audit_hash: str | None = None
    ts: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "action": self.action,
            "user": self.user,
            "role": self.role,
            "reason": self.reason,
            "hitl_request_id": self.hitl_request_id,
            "audit_hash": self.audit_hash,
            "ts": self.ts,
        }


class ActionFirewall:
    """Firewall central de acciones."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.firewall")
        self._kill_switches: dict[str, bool] = {a: True for a in FIREWALL_POLICIES}
        self._last_call_ts: dict[tuple[str, str], float] = {}
        self._audit_chain: list[dict[str, Any]] = []
        self._previous_hash: str = "0" * 64  # génesis

    def is_allowed(
        self,
        action: str,
        *,
        user: str,
        role: str,
        payload: dict[str, Any] | None = None,
    ) -> FirewallDecision:
        policy = get_policy(action)
        if not policy:
            return FirewallDecision(
                allowed=False,
                action=action,
                user=user,
                role=role,
                reason=f"No policy for action '{action}' - DENIED by default",
            )

        # Kill switch
        if policy.kill_switch and not self._kill_switches.get(action, True):
            return FirewallDecision(
                allowed=False,
                action=action,
                user=user,
                role=role,
                reason=f"Kill switch off for '{action}'",
            )

        # Roles
        if role not in policy.allowed_roles:
            return FirewallDecision(
                allowed=False,
                action=action,
                user=user,
                role=role,
                reason=f"Role '{role}' not in allowed: {policy.allowed_roles}",
            )

        # Cooldown
        if policy.cooldown_seconds > 0:
            key = (action, user)
            last = self._last_call_ts.get(key, 0.0)
            if (time.time() - last) < policy.cooldown_seconds:
                remaining = policy.cooldown_seconds - (time.time() - last)
                return FirewallDecision(
                    allowed=False,
                    action=action,
                    user=user,
                    role=role,
                    reason=f"Cooldown: {remaining:.1f}s remaining",
                )

        # HITL
        hitl_id: str | None = None
        if policy.requires_hitl:
            hitl_id = uuid.uuid4().hex[:12]
            return FirewallDecision(
                allowed=False,
                action=action,
                user=user,
                role=role,
                reason="Pending HITL approval",
                hitl_request_id=hitl_id,
            )

        # Auditable - hash encadenado
        audit_hash = self._chain_hash(action, user, role, payload)

        self._last_call_ts[(action, user)] = time.time()
        return FirewallDecision(
            allowed=True,
            action=action,
            user=user,
            role=role,
            audit_hash=audit_hash,
        )

    def _chain_hash(self, action: str, user: str, role: str, payload: dict[str, Any] | None) -> str:
        """Hash encadenado: prev_hash + action + user + ts → new_hash."""
        block = {
            "prev": self._previous_hash,
            "action": action,
            "user": user,
            "role": role,
            "payload": payload or {},
            "ts": time.time(),
        }
        block_str = json.dumps(block, sort_keys=True, default=str)
        new_hash = hashlib.sha256(block_str.encode("utf-8")).hexdigest()
        self._previous_hash = new_hash
        self._audit_chain.append({"block": block, "hash": new_hash})
        return new_hash

    def kill_switch_off(self, action: str) -> bool:
        """Apagar un action (solo si kill_switch=True)."""
        policy = get_policy(action)
        if not policy or not policy.kill_switch:
            return False
        self._kill_switches[action] = False
        self.log.warning("firewall.kill_switch.off", action=action)
        return True

    def kill_switch_on(self, action: str) -> bool:
        policy = get_policy(action)
        if not policy:
            return False
        self._kill_switches[action] = True
        self.log.info("firewall.kill_switch.on", action=action)
        return True

    def audit_chain(self) -> list[dict[str, Any]]:
        return list(self._audit_chain)

    def verify_chain(self) -> bool:
        """Verifica integridad del hash chain."""
        prev = "0" * 64
        for entry in self._audit_chain:
            block = entry["block"]
            block_str = json.dumps(block, sort_keys=True, default=str)
            expected = hashlib.sha256(block_str.encode("utf-8")).hexdigest()
            if expected != entry["hash"]:
                return False
            if block["prev"] != prev:
                return False
            prev = entry["hash"]
        return True

    async def startup(self) -> None:
        self.log.info("firewall.startup", policies=len(FIREWALL_POLICIES))

    async def shutdown(self) -> None:
        self.log.info("firewall.shutdown")
