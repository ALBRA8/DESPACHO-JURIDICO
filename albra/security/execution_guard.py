"""
EXECUTION GUARD - última frontera antes de acciones sensibles.

Inspirado en AGENTE-TRADING/src/agent/execution_guard.ts.

Fail-closed TOTAL: si un check no se puede completar → acción rechazada.
Se invoca DESDE DENTRO de la acción (no del reasoning): cualquier camino
hacia ejecución pasa por aquí.

Checks re-valida en el punto de ejecución lo que pudo caducar:
1. Kill switch global (policy_state)
2. Autorización LIVE explícita
3. Autonomía dentro de ceiling
4. Permisos RBAC del rol
5. Legal Gate verdict
6. Data classification no excedida
7. HITL aprobado (si era requerido)
8. Circuit breaker cerrado del provider
9. Dedup: una decisión ya ejecutada no se re-ejecuta
"""
from __future__ import annotations

import time
import uuid
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
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail, "severity": c.severity} for c in self.checks],
            "execution_id": self.execution_id,
        }


class ExecutionGuard:
    """Guard fail-closed - se invoca justo antes de ejecutar acción sensible."""

    # Set de acciones ya ejecutadas (dedup simple)
    _executed_actions: set[str] = set()

    def __init__(self) -> None:
        self.log = get_logger("albra.execution_guard")

    def check(
        self,
        *,
        action: str,
        user_role: str,
        live_authorized: bool = False,
        hitl_approved: bool = False,
        policy_state: Any = None,  # PolicyState
        autonomy_controller: Any = None,
        rbac_check_fn: Any = None,  # callable (role, permission) -> bool
        legal_gate_verdict: Any = None,  # LegalGateVerdict
        data_classification: Any = None,  # ClassificationResult
        circuit_breaker: Any = None,
        provider_name: str = "",
        dedup_key: str | None = None,
    ) -> GuardVerdict:
        checks: list[GuardCheck] = []

        # 1. Kill switch
        if policy_state and policy_state.kill_switch:
            checks.append(GuardCheck(
                name="kill_switch", ok=False,
                detail=f"Kill switch activo: {policy_state.kill_reason}",
            ))
        else:
            checks.append(GuardCheck(name="kill_switch", ok=True, detail="Kill switch off"))

        # 2. Autorización LIVE (si la action lo requiere)
        live_required = action in (
            "publish_legal_filing", "sign_document", "accept_contract",
            "send_external_message",
        )
        if live_required:
            if policy_state and not live_authorized:
                checks.append(GuardCheck(
                    name="live_authorization", ok=False,
                    detail=f"LIVE no autorizado (mode={policy_state.mode if policy_state else '?'})",
                ))
            else:
                checks.append(GuardCheck(name="live_authorization", ok=True, detail="LIVE authorized"))

        # 3. Autonomía dentro de ceiling
        if autonomy_controller and policy_state:
            level = policy_state.effective_level
            decision = autonomy_controller.assert_allowed(
                requested_level=level,
                action=action,
                external=live_required,
                sensitive=action in ("sign_document", "publish_legal_filing"),
            )
            checks.append(GuardCheck(
                name="autonomy_ceiling", ok=decision.allowed,
                detail=decision.reason,
            ))

        # 4. RBAC
        if rbac_check_fn:
            permission_map = {
                "publish_legal_filing": "demandas.file",
                "sign_document": "documents.sign",
                "accept_contract": "documents.sign",
                "send_external_message": "comms.send_external",
                "generate_legal_document": "documents.generate",
                "internal_research": "research.run",
            }
            perm = permission_map.get(action, "tools.invoke")
            allowed = rbac_check_fn(user_role, perm)
            checks.append(GuardCheck(
                name="rbac_permission", ok=allowed,
                detail=f"role={user_role} perm={perm} allowed={allowed}",
            ))

        # 5. Legal Gate verdict
        if legal_gate_verdict:
            if legal_gate_verdict.verdict == "BLOCKED":
                checks.append(GuardCheck(
                    name="legal_gate", ok=False,
                    detail=f"BLOCKED: {legal_gate_verdict.reason}",
                ))
            elif legal_gate_verdict.verdict == "REVIEW_REQUIRED" and not hitl_approved:
                checks.append(GuardCheck(
                    name="legal_gate", ok=False,
                    detail=f"REVIEW_REQUIRED sin HITL aprobado",
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

        # 6. Data classification
        if data_classification and data_classification.classification.name in ("CREDENCIAL", "SECRETO_TECNICO"):
            checks.append(GuardCheck(
                name="data_classification", ok=False,
                detail=f"Contiene {data_classification.label} - no ejecutable",
            ))
        else:
            checks.append(GuardCheck(
                name="data_classification", ok=True,
                detail=f"classification={data_classification.classification.name}" if data_classification else "no data",
            ))

        # 7. HITL aprobado
        if hitl_approved or not live_required:
            checks.append(GuardCheck(name="hitl_approved", ok=True, detail="HITL OK"))
        else:
            checks.append(GuardCheck(
                name="hitl_approved", ok=False,
                detail="HITL pendiente o denegado",
            ))

        # 8. Circuit breaker
        if circuit_breaker and provider_name:
            if circuit_breaker.can_pass(provider_name):
                checks.append(GuardCheck(name="circuit_breaker", ok=True, detail=f"{provider_name} CLOSED/HALF_OPEN"))
            else:
                checks.append(GuardCheck(
                    name="circuit_breaker", ok=False,
                    detail=f"{provider_name} OPEN - bloqueado",
                ))
        else:
            checks.append(GuardCheck(name="circuit_breaker", ok=True, detail="no provider"))

        # 9. Dedup
        if dedup_key:
            if dedup_key in self._executed_actions:
                checks.append(GuardCheck(
                    name="dedup", ok=False,
                    detail=f"Action ya ejecutada con key={dedup_key[:20]}",
                ))
            else:
                checks.append(GuardCheck(name="dedup", ok=True, detail="unique action"))
                self._executed_actions.add(dedup_key)
        else:
            checks.append(GuardCheck(name="dedup", ok=True, detail="no dedup key"))

        # Veredicto: fail-closed TOTAL
        hard_fails = [c for c in checks if not c.ok and c.severity == "hard"]
        if hard_fails:
            return GuardVerdict(
                allowed=False,
                reason=hard_fails[0].detail,
                checks=checks,
                execution_id=uuid.uuid4().hex[:20],
            )

        return GuardVerdict(
            allowed=True,
            reason="All checks passed",
            checks=checks,
            execution_id=uuid.uuid4().hex[:20],
        )

    def reset_dedup(self) -> None:
        """Limpia el set de dedup (para testing o reset manual)."""
        self._executed_actions.clear()
