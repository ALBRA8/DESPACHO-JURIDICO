"""
EXECUTION GUARD — fail-closed TOTAL.

Inspirado en AGENTE-TRADING/src/agent/execution_guard.ts.

REGLA CRÍTICA (P0.2):
Si un componente OBLIGATORIO de seguridad no existe → DENY (no skip).

Componentes obligatorios:
- policy_state (kill_switch, mode, ceiling)
- autonomy_controller (ceiling enforcement)
- rbac_check_fn (permisos)
- legal_gate_verdict (verdict jurídico)

Componentes opcionales:
- data_classification (si no hay texto, no clasifica)
- circuit_breaker (si no hay provider, no aplica)

REGLA CRÍTICA (P0.3):
El dedup_key SOLO se reserva DESPUÉS de que TODOS los checks pasan.
Una acción rechazada NO consume su slot.

Pipeline:
REQUEST → VALIDATE → AUTHORIZE → POLICY → RBAC → AUTONOMY →
LEGAL/RISK → CIRCUIT BREAKER → RESERVE DEDUP → EXECUTE
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from albra.observability.logger import get_logger


@dataclass
class GuardCheck:
    name: str
    ok: bool
    detail: str
    severity: str = "hard"  # hard | soft (soft no bloquea)


@dataclass
class GuardVerdict:
    allowed: bool
    reason: str
    checks: list[GuardCheck] = field(default_factory=list)
    execution_id: str | None = None
    dedup_reserved: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "checks": [
                {"name": c.name, "ok": c.ok, "detail": c.detail, "severity": c.severity}
                for c in self.checks
            ],
            "execution_id": self.execution_id,
            "dedup_reserved": self.dedup_reserved,
        }


# Acciones que requieren autorización LIVE
LIVE_REQUIRED_ACTIONS: frozenset[str] = frozenset({
    "publish_legal_filing",
    "sign_document",
    "accept_contract",
    "send_external_message",
})

# Acciones consideradas sensibles
SENSITIVE_ACTIONS: frozenset[str] = frozenset({
    "sign_document",
    "publish_legal_filing",
    "accept_contract",
    "delete_evidence",
    "memory_purge",
    "modify_permissions",
})

# Mapeo action → permiso RBAC
ACTION_PERMISSION_MAP: dict[str, str] = {
    "publish_legal_filing": "demandas.file",
    "sign_document": "documents.sign",
    "accept_contract": "documents.sign",
    "send_external_message": "comms.send_external",
    "generate_legal_document": "documents.generate",
    "internal_research": "research.run",
    "delete_evidence": "evidence.delete",
    "memory_purge": "memory.purge",
    "modify_permissions": "security.permissions",
    "tool_invocation": "tools.invoke",
    "memory_write": "memory.write",
    "knowledge_load": "knowledge.write",
}


class ExecutionGuard:
    """Guard fail-closed TOTAL. NUNCA skip chequeos obligatorios."""

    def __init__(self) -> None:
        self.log = get_logger("albra.execution_guard")
        self._executed_actions: set[str] = set()

    def check(
        self,
        *,
        action: str,
        user_role: str,
        policy_state: Any,  # OBLIGATORIO
        autonomy_controller: Any,  # OBLIGATORIO
        rbac_check_fn: Callable[[str, str], bool],  # OBLIGATORIO
        legal_gate_verdict: Any,  # OBLIGATORIO
        live_authorized: bool = False,
        hitl_approved: bool = False,
        data_classification: Any = None,  # opcional
        circuit_breaker: Any = None,  # opcional
        provider_name: str = "",
        dedup_key: str | None = None,
    ) -> GuardVerdict:
        """Pipeline fail-closed. Si deps obligatorios faltan → DENY."""
        checks: list[GuardCheck] = []
        exec_id = uuid.uuid4().hex[:20]

        # --- 0. CHECK DEPENDENCIAS OBLIGATORIAS (P0.2) ---
        missing_deps: list[str] = []
        if policy_state is None:
            missing_deps.append("policy_state")
        if autonomy_controller is None:
            missing_deps.append("autonomy_controller")
        if rbac_check_fn is None:
            missing_deps.append("rbac_check_fn")
        if legal_gate_verdict is None:
            missing_deps.append("legal_gate_verdict")

        if missing_deps:
            # FAIL-CLOSED: no continuar, no reservar dedup
            reason = f"FAIL-CLOSED: missing mandatory deps: {missing_deps}"
            for d in missing_deps:
                checks.append(GuardCheck(
                    name=f"dep:{d}", ok=False, detail=f"{d} is None"
                ))
            self.log.error("guard.missing_deps", action=action, missing=missing_deps)
            return GuardVerdict(
                allowed=False, reason=reason, checks=checks,
                execution_id=exec_id, dedup_reserved=False,
            )

        # --- 1. KILL SWITCH ---
        if policy_state.kill_switch:
            checks.append(GuardCheck(
                name="kill_switch", ok=False,
                detail=f"Kill switch activo: {policy_state.kill_reason}",
            ))
        else:
            checks.append(GuardCheck(name="kill_switch", ok=True, detail="Kill switch off"))

        # --- 2. LIVE AUTHORIZATION ---
        live_required = action in LIVE_REQUIRED_ACTIONS
        if live_required:
            if not live_authorized:
                checks.append(GuardCheck(
                    name="live_authorization", ok=False,
                    detail=f"LIVE no autorizado (mode={policy_state.mode})",
                ))
            elif not policy_state.live_authorized:
                checks.append(GuardCheck(
                    name="live_authorization", ok=False,
                    detail="policy_state.live_authorized=False",
                ))
            else:
                checks.append(GuardCheck(name="live_authorization", ok=True, detail="LIVE authorized"))

        # --- 3. AUTONOMY CEILING ---
        requested_level = policy_state.effective_level or "L0_OBSERVE"
        # Acciones live requieren L3+
        if live_required and requested_level == "L0_OBSERVE":
            requested_level = "L3_EXECUTE_EXTERNAL"
        if action in SENSITIVE_ACTIONS and requested_level < "L4_EXECUTE_SENSITIVE":
            requested_level = "L4_EXECUTE_SENSITIVE"

        auto_decision = autonomy_controller.assert_allowed(
            requested_level=requested_level,
            action=action,
            external=live_required,
            sensitive=action in SENSITIVE_ACTIONS,
        )
        checks.append(GuardCheck(
            name="autonomy_ceiling", ok=auto_decision.allowed,
            detail=auto_decision.reason,
        ))

        # --- 4. RBAC ---
        perm = ACTION_PERMISSION_MAP.get(action, "tools.invoke")
        allowed = bool(rbac_check_fn(user_role, perm))
        checks.append(GuardCheck(
            name="rbac_permission", ok=allowed,
            detail=f"role={user_role} perm={perm} allowed={allowed}",
        ))

        # --- 5. LEGAL GATE ---
        if legal_gate_verdict.verdict == "BLOCKED":
            checks.append(GuardCheck(
                name="legal_gate", ok=False,
                detail=f"BLOCKED: {legal_gate_verdict.reason}",
            ))
        elif legal_gate_verdict.verdict == "REVIEW_REQUIRED" and not hitl_approved:
            checks.append(GuardCheck(
                name="legal_gate", ok=False,
                detail="REVIEW_REQUIRED sin HITL aprobado",
            ))
        elif legal_gate_verdict.verdict == "UNKNOWN":
            checks.append(GuardCheck(
                name="legal_gate", ok=False,
                detail="UNKNOWN verdict - fail closed",
            ))
        else:
            checks.append(GuardCheck(
                name="legal_gate", ok=True,
                detail=f"verdict={legal_gate_verdict.verdict}",
            ))

        # --- 6. DATA CLASSIFICATION (opcional - solo si hay data) ---
        if data_classification is not None:
            cls = data_classification.classification.name if hasattr(data_classification, "classification") else str(data_classification)
            if cls in ("CREDENCIAL", "SECRETO_TECNICO"):
                checks.append(GuardCheck(
                    name="data_classification", ok=False,
                    detail=f"Contiene {cls} - no ejecutable externamente",
                ))
            else:
                checks.append(GuardCheck(
                    name="data_classification", ok=True,
                    detail=f"classification={cls}",
                ))
        else:
            checks.append(GuardCheck(
                name="data_classification", ok=True, detail="no data to classify",
                severity="soft",
            ))

        # --- 7. HITL APPROVED ---
        if hitl_approved or not live_required:
            checks.append(GuardCheck(name="hitl_approved", ok=True, detail="HITL OK"))
        else:
            checks.append(GuardCheck(
                name="hitl_approved", ok=False,
                detail="HITL pendiente o denegado",
            ))

        # --- 8. CIRCUIT BREAKER (opcional - solo si hay provider) ---
        if circuit_breaker is not None and provider_name:
            if circuit_breaker.can_pass(provider_name):
                checks.append(GuardCheck(
                    name="circuit_breaker", ok=True,
                    detail=f"{provider_name} CLOSED/HALF_OPEN",
                ))
            else:
                checks.append(GuardCheck(
                    name="circuit_breaker", ok=False,
                    detail=f"{provider_name} OPEN - bloqueado",
                ))
        else:
            checks.append(GuardCheck(
                name="circuit_breaker", ok=True, detail="no provider needed",
                severity="soft",
            ))

        # --- 9. DEDUP CHECK (sin reservar todavía) ---
        dedup_would_block = False
        if dedup_key:
            if dedup_key in self._executed_actions:
                checks.append(GuardCheck(
                    name="dedup", ok=False,
                    detail=f"Action ya ejecutada con key={dedup_key[:20]}",
                ))
                dedup_would_block = True
            else:
                checks.append(GuardCheck(
                    name="dedup", ok=True, detail="unique action (slot pending)",
                ))
        else:
            checks.append(GuardCheck(
                name="dedup", ok=True, detail="no dedup key",
                severity="soft",
            ))

        # --- VEREDICTO + RESERVA DEDUP SOLO SI TODO PASA (P0.3) ---
        hard_fails = [c for c in checks if not c.ok and c.severity == "hard"]
        if hard_fails:
            # NO reservar dedup - la acción fue rechazada
            self.log.warning(
                "guard.deny",
                action=action, reason=hard_fails[0].detail,
                checks_failed=len(hard_fails), dedup_reserved=False,
            )
            return GuardVerdict(
                allowed=False, reason=hard_fails[0].detail, checks=checks,
                execution_id=exec_id, dedup_reserved=False,
            )

        # Todo OK → reservar dedup slot AHORA
        if dedup_key and not dedup_would_block:
            self._executed_actions.add(dedup_key)

        return GuardVerdict(
            allowed=True, reason="All checks passed", checks=checks,
            execution_id=exec_id, dedup_reserved=bool(dedup_key),
        )

    def reset_dedup(self) -> None:
        """Limpia el set de dedup (para testing o reset manual)."""
        self._executed_actions.clear()

    def is_executed(self, dedup_key: str) -> bool:
        return dedup_key in self._executed_actions
